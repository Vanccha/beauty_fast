"""Personel paneli uclari (hepsi ``require_staff`` arkasinda).

  GET    /api/admin/dashboard               - bugunun ozeti
  GET    /api/admin/calendar                - gun gorunumu (usta x saat)
  PATCH  /api/admin/appointments/{id}/move  - surukle-birak tasima
  PATCH  /api/admin/appointments/{id}/status- durum guncelleme
  GET    /api/admin/customers               - musteri listesi + segment
  GET    /api/admin/customers/{id}          - CRM karti (gizli notlar dahil)
  POST   /api/admin/customers/{id}/allergy  - alerji ikazi ekle/sil
  POST   /api/admin/customers/{id}/note     - gizli usta notu ekle/sil
  POST   /api/admin/customers/{id}/photo    - albume fotograf ekle/sil
  GET    /api/admin/inventory               - stok + kritik uyarilar
  GET    /api/admin/campaigns               - kampanyalar
  GET    /api/admin/reminder-rules          - hatirlatma kurallari + onizleme
  GET    /api/admin/notifications           - bildirim kuyrugu (en yakin 25)
  GET    /api/admin/messaging/status        - mesaj surucusu / WhatsApp baglanti durumu
  POST   /api/admin/messaging/qr            - WhatsApp numarasi baglamak icin QR (OWNER)
  POST   /api/admin/messaging/logout        - WhatsApp numarasinin baglantisini kes (OWNER)
  GET    /api/admin/messaging/welcome       - ilk mesajda karsilama ayarlari
  PUT    /api/admin/messaging/welcome       - karsilama mesajini ac/kapat, metni degistir
  GET    /api/admin/reviews                 - moderasyon listesi + ozet
  PATCH  /api/admin/reviews/{id}            - yayindan kaldir / one cikar / yanitla
  GET    /api/admin/stats/opportunity       - firsat saati isi haritasi
  GET    /api/admin/portfolio               - galeri yonetimi listesi
  POST   /api/admin/portfolio               - galeriye is ekle / sil
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..config import config
from ..core.campaigns import parse_target_rule
from ..core.opportunity import (
    DEFAULT_OPPORTUNITY_CONFIG,
    OccupancySample,
    score_opportunity,
    with_global_mean,
)
from ..core.package_layout import LayoutOptions, layout_package
from ..core.reminder_rules import ReminderContext, ReminderRuleSpec, compute_interval_days
from ..deps import DbSession, ManagerDep, OwnerDep, StaffDep
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import (
    Allergy,
    Appointment,
    AppointmentItem,
    Campaign,
    CampaignGrant,
    Customer,
    CustomerNote,
    CustomerPhoto,
    InventoryItem,
    LoyaltyEntry,
    OccupancyStat,
    PortfolioItem,
    ReminderRule,
    Review,
    Salon,
    ScheduledNotification,
    Service,
    SlotLock,
    Staff,
    StockMovement,
    TimeOff,
)
from ..services.appointment import move_appointment
from ..services.appointment_status import change_appointment_status
from ..services.catalog import (
    assert_staff_can_do,
    get_default_branch,
    get_exclusive_resource_ids,
    load_service_specs,
)
from ..services.campaign_audience import campaign_match_counts
from ..services.customer_profile import build_customer_profile, list_customer_summaries
from ..services import messaging, whatsapp_inbound
from ..services.notifications import list_notification_queue
from ..services.portfolio import list_admin_portfolio
from ..services.reviews import (
    count_unanswered_low_ratings,
    get_review_summary,
    list_admin_reviews,
)
from ..services.risk import assess_phone_risk
from ..services.stock import adjust_stock, critical_items
from ..time_utils import (
    now_local,
    add_days_to_key,
    format_date_tr,
    is_date_key,
    minutes_to_label,
    to_date_key,
    weekday_name_tr,
    weekday_of,
)
from ..uploads import store_upload

router = APIRouter(prefix="/api/admin", tags=["admin"], route_class=EnvelopeRoute)

ACTIVE = ("PENDING", "CONFIRMED", "COMPLETED")


# ---------------------------------------------------------------------
# Panel ozeti
# ---------------------------------------------------------------------


@router.get("/dashboard")
def dashboard(staff: StaffDep, db: DbSession, date: str | None = None) -> dict:
    """Gunun ozeti: program, kritik stok, riskli randevular, bekleyen bildirim.

    Uc soruyu yanitlar: bugun ne var, neyi gozden kaciriyorum, neyi
    ismarlamam gerek.

    "Riskli randevular" bolumu capraz-salon skorunu KULLANIR ama yalnizca
    toplulastirilmis skoru tasir - hangi salonda ne oldugu donmez (KVKK).
    """
    branch = get_default_branch(db)
    now = now_local()
    date = date if (date and is_date_key(date)) else to_date_key(now)

    appointments = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
            selectinload(Appointment.staff),
        )
        .where(Appointment.branch_id == branch.id, Appointment.date == date)
        .order_by(Appointment.start_min)
    ).all()

    # --- Alerji ikazlari -------------------------------------------------
    customer_ids = {a.customer_id for a in appointments}
    allergies = (
        db.scalars(select(Allergy).where(Allergy.customer_id.in_(customer_ids))).all()
        if customer_ids
        else []
    )
    allergy_by_customer: dict[int, list[dict]] = {}
    for a in allergies:
        allergy_by_customer.setdefault(a.customer_id, []).append(
            {"label": a.label, "severity": a.severity}
        )

    # --- Golge risk skoru (musteri basina tek sorgu) ---------------------
    risk_by_customer: dict[int, dict] = {}
    for appointment in appointments:
        if appointment.customer_id in risk_by_customer:
            continue
        assessment = assess_phone_risk(db, appointment.customer.phone, now=now)
        risk_by_customer[appointment.customer_id] = {
            "score": assessment.score,
            "label": assessment.label,
        }

    # --- Bekleyen bildirim + son 7 gun cirosu ----------------------------
    pending_notifications = db.scalar(
        select(func.count())
        .select_from(ScheduledNotification)
        .where(
            ScheduledNotification.status == "PENDING",
            ScheduledNotification.due_at <= now,
        )
    )
    week_start = add_days_to_key(to_date_key(now), -7)
    week_rows = db.execute(
        select(func.count(), func.sum(Appointment.total_price)).where(
            Appointment.branch_id == branch.id,
            Appointment.status == "COMPLETED",
            Appointment.date >= week_start,
        )
    ).first()

    return {
        "date": date,
        "dateLabel": format_date_tr(date),
        "appointments": [
            {
                "id": a.id,
                "startMin": a.start_min,
                "endMin": a.end_min,
                "startLabel": minutes_to_label(a.start_min),
                "endLabel": minutes_to_label(a.end_min),
                "status": a.status,
                "version": a.version,
                "isOpportunity": a.is_opportunity,
                "shadowParentId": a.shadow_parent_id,
                "customerId": a.customer_id,
                "customer": {
                    "id": a.customer.id,
                    "firstName": a.customer.first_name,
                    "lastName": a.customer.last_name,
                    "phone": a.customer.phone,
                    "tier": a.customer.tier,
                },
                "customerName": f"{a.customer.first_name} {a.customer.last_name or ''}".strip(),
                "customerTier": a.customer.tier,
                "staffName": a.staff.name,
                "services": [i.service.name for i in a.items],
                "allergies": allergy_by_customer.get(a.customer_id, []),
                #: Yalnizca toplulastirilmis skor + etiket
                "risk": risk_by_customer.get(a.customer_id),
                "totalPrice": a.total_price,
            }
            for a in appointments
        ],
        "criticalStock": critical_items(db, branch.id),
        "pendingNotifications": pending_notifications or 0,
        "week": {
            "completed": (week_rows[0] if week_rows else 0) or 0,
            "revenue": round((week_rows[1] if week_rows else 0) or 0, 2),
        },
        "counts": {
            "total": len(appointments),
            "completed": sum(1 for a in appointments if a.status == "COMPLETED"),
            "cancelled": sum(1 for a in appointments if a.status == "CANCELLED"),
            "noShow": sum(1 for a in appointments if a.status == "NO_SHOW"),
            "revenue": round(
                sum(a.total_price for a in appointments if a.status == "COMPLETED"), 2
            ),
        },
    }


# ---------------------------------------------------------------------
# Takvim
# ---------------------------------------------------------------------


@router.get("/calendar")
def calendar(staff: StaffDep, db: DbSession, date: str | None = None) -> dict:
    """Gun gorunumu: dikey eksen saat, yatay eksen usta.

    Her randevu icin ustanin MESGUL ve SERBEST (pasif/golge) dilimleri
    ayri ayri doner. Arayuz pasif dilimleri cizgili gosterir; usta bir
    bakista "burada bosum, araya is alabilirim" bilgisini gorur.
    """
    branch = get_default_branch(db)
    date = date if (date and is_date_key(date)) else to_date_key(now_local())
    weekday = weekday_of(date)
    now = now_local()

    staff_rows = db.scalars(
        select(Staff)
        .options(selectinload(Staff.working_hours), selectinload(Staff.services))
        .where(Staff.branch_id == branch.id, Staff.is_active.is_(True))
        .order_by(Staff.display_order, Staff.id)
    ).all()

    appointments = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
        )
        .where(Appointment.branch_id == branch.id, Appointment.date == date)
        .order_by(Appointment.start_min)
    ).all()

    locks = db.scalars(
        select(SlotLock).where(
            SlotLock.branch_id == branch.id,
            SlotLock.date == date,
            SlotLock.consumed_at.is_(None),
            SlotLock.expires_at > now,
        )
    ).all()

    time_off = db.scalars(
        select(TimeOff)
        .join(Staff, Staff.id == TimeOff.staff_id)
        .where(TimeOff.date == date, Staff.branch_id == branch.id)
    ).all()

    # Alerjisi olan musteriler - takvim kartinda kirmizi nokta gosterilir.
    customer_ids = {a.customer_id for a in appointments}
    allergies = (
        db.scalars(select(Allergy).where(Allergy.customer_id.in_(customer_ids))).all()
        if customer_ids
        else []
    )
    allergy_by_customer: dict[int, list[dict]] = {}
    for a in allergies:
        allergy_by_customer.setdefault(a.customer_id, []).append(
            {"label": a.label, "severity": a.severity}
        )

    def intervals_of(a: Appointment) -> tuple[list[dict], list[dict]]:
        busy: list[dict] = []
        passive: list[dict] = []
        for item in a.items:
            base = a.start_min + item.offset_min
            if item.active_before_min > 0:
                busy.append({"start": base, "end": base + item.active_before_min})
            passive_start = base + item.active_before_min
            if item.passive_min > 0:
                passive.append(
                    {"start": passive_start, "end": passive_start + item.passive_min}
                )
            after_start = passive_start + item.passive_min
            after_end = after_start + item.active_after_min + item.buffer_min
            if after_end > after_start:
                busy.append({"start": after_start, "end": after_end})
        return busy, passive

    appointment_payload = []
    for a in appointments:
        busy, passive = intervals_of(a)
        appointment_payload.append(
            {
                "id": a.id,
                "staffId": a.staff_id,
                "date": a.date,
                "startMin": a.start_min,
                "endMin": a.end_min,
                "startLabel": minutes_to_label(a.start_min),
                "endLabel": minutes_to_label(a.end_min),
                "status": a.status,
                "version": a.version,
                "totalPrice": a.total_price,
                "isOpportunity": a.is_opportunity,
                "shadowParentId": a.shadow_parent_id,
                "customer": {
                    "id": a.customer.id,
                    "firstName": a.customer.first_name,
                    "lastName": a.customer.last_name,
                    "phone": a.customer.phone,
                    "tier": a.customer.tier,
                },
                "allergies": allergy_by_customer.get(a.customer_id, []),
                "services": [{"id": i.service.id, "name": i.service.name} for i in a.items],
                "serviceIds": [i.service_id for i in a.items],
                "busyIntervals": busy,
                #: Ustanin SERBEST oldugu (baska musteriye acilabilen) dilimler
                "passiveIntervals": passive,
            }
        )

    return {
        "date": date,
        "dateLabel": format_date_tr(date),
        "weekday": weekday,
        "openMinute": branch.open_minute,
        "closeMinute": branch.close_minute,
        "gridMinutes": config.slot_grid_minutes,
        "staff": [
            {
                "id": s.id,
                "name": s.name,
                "photoUrl": s.photo_url,
                "isWorking": bool(wh and wh.is_working),
                "startMin": wh.start_min if wh else branch.open_minute,
                "endMin": wh.end_min if wh else branch.close_minute,
                #: Surukle-birak on kontrolu: hedef usta bu hizmetleri yapiyor mu?
                "serviceIds": [link.service_id for link in s.services],
                "timeOff": [
                    {"startMin": t.start_min, "endMin": t.end_min, "reason": t.reason}
                    for t in time_off
                    if t.staff_id == s.id
                ],
            }
            for s in staff_rows
            for wh in [next((w for w in s.working_hours if w.weekday == weekday), None)]
        ],
        "appointments": appointment_payload,
        #: Baskasinin tuttugu, suresi dolmamis gecici rezervasyonlar
        "locks": [
            {
                "id": lock.id,
                "staffId": lock.staff_id,
                "startMin": lock.start_min,
                "endMin": lock.end_min,
                "expiresAt": lock.expires_at.isoformat(),
            }
            for lock in locks
        ],
    }


# ---------------------------------------------------------------------
# Randevu tasima / durum
# ---------------------------------------------------------------------


class MoveBody(BaseModel):
    toStaffId: int = Field(gt=0)
    toDate: str
    toStartMin: int = Field(ge=0, le=1439)
    #: Suruklemeye baslarken kartta yazan surum
    expectedVersion: int = Field(ge=0)

    @field_validator("toDate")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        if not is_date_key(v):
            raise ValueError('Tarih "YYYY-MM-DD" biçiminde olmalı.')
        return v


@router.patch("/appointments/{appointment_id}/move")
def move(appointment_id: int, body: MoveBody, staff: StaffDep, db: DbSession) -> dict:
    """SURUKLE-BIRAK TASIMA - optimistic locking ile.

    Hedef personelin hiz carpani farkliysa paket yerlesimi YENIDEN
    hesaplanir, boylece randevu blogu hedef ustaya gore dogru uzunlukta
    yerlesir.

    Cakisma iki katmanda yakalanir:
      ``VERSION_MISMATCH`` -> kayit biz okuduktan sonra degismis
      ``SLOT_TAKEN``       -> hedef slot dolu (DB unique kisiti)
    """
    branch = get_default_branch(db)

    appointment = db.scalar(
        select(Appointment)
        .options(selectinload(Appointment.items))
        .where(Appointment.id == appointment_id)
    )
    if appointment is None:
        raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)

    service_ids = [i.service_id for i in appointment.items]

    try:
        speed_factor = assert_staff_can_do(db, body.toStaffId, service_ids)
    except AppError:
        raise AppError(
            "VALIDATION", "Hedef personel bu randevudaki hizmetlerin tamamını yapmıyor.", 400
        )

    specs = load_service_specs(db, service_ids)
    layout = layout_package(specs, LayoutOptions(speed_factor=speed_factor))

    moved = move_appointment(
        db,
        appointment_id=appointment_id,
        expected_version=body.expectedVersion,
        to_staff_id=body.toStaffId,
        to_date=body.toDate,
        to_start_min=body.toStartMin,
        layout=layout,
        exclusive_resource_ids=get_exclusive_resource_ids(db, branch.id),
    )

    return {
        "id": moved.id,
        "staffId": moved.staff_id,
        "date": moved.date,
        "startMin": moved.start_min,
        "endMin": moved.end_min,
        "startLabel": minutes_to_label(moved.start_min),
        "endLabel": minutes_to_label(moved.end_min),
        "version": moved.version,
        "totalMin": layout.total_min,
    }


class StatusBody(BaseModel):
    status: str
    expectedVersion: int = Field(ge=0)

    @field_validator("status")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in ("CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW"):
            raise ValueError("Geçersiz durum.")
        return v


@router.patch("/appointments/{appointment_id}/status")
def set_status(appointment_id: int, body: StatusBody, staff: StaffDep, db: DbSession) -> dict:
    """Personel durum guncellemesi.

    Yan etkilerin tamami ``change_appointment_status`` icinde TEK
    transaction'da uygulanir: stok dusumu (idempotent), sadakat puani,
    risk olayi, tekrar hatirlatmasi ve iptal halinde slotun serbest
    birakilmasi.
    """
    return change_appointment_status(
        db,
        appointment_id=appointment_id,
        status=body.status,
        expected_version=body.expectedVersion,
    )


# ---------------------------------------------------------------------
# Musteriler
# ---------------------------------------------------------------------


def _lower_tr(text: str) -> str:
    """Turkce kucuk harf (``toLocaleLowerCase('tr')`` karsiligi): I -> ı, İ -> i."""
    return text.replace("I", "ı").replace("İ", "i").lower()


@router.get("/customers")
def customers(
    staff: StaffDep, db: DbSession, q: str | None = None, segment: str | None = None
) -> dict:
    """Musteri listesi + segment rozeti + salon ici risk gostergesi.

    NOT: Bu ucta CAPRAZ-SALON risk skoru hesaplanmaz; cok sayida hash
    sorgusu pahalidir. Capraz skor yalnizca musteri karti acildiginda
    sorgulanir.
    """
    branch = get_default_branch(db)
    rows = list_customer_summaries(db, branch.id)

    if q:
        needle = _lower_tr(q)
        rows = [
            r
            for r in rows
            if needle in _lower_tr(f"{r['firstName']} {r['lastName'] or ''} {r['phone']}")
        ]

    if segment and segment != "hepsi":
        rows = [r for r in rows if r["segment"]["segment"] == segment]

    # Degerli musteri once: harcama, sonra ziyaret.
    rows.sort(key=lambda r: (-r["totalSpend"], -r["visitCount"]))

    counts: dict[str, int] = {}
    for r in rows:
        key = r["segment"]["segment"]
        counts[key] = counts.get(key, 0) + 1

    return {"customers": rows, "segmentCounts": counts, "total": len(rows)}


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: int, staff: StaffDep, db: DbSession) -> dict:
    """CRM KARTI - yalnizca personel.

    Gizli notlar (``visibility == "STAFF_ONLY"``) bu ucun DISINDA hicbir
    yerde donmez - musteri uclarinda bu tablo hic sorgulanmaz.
    """
    branch = get_default_branch(db)
    profile = build_customer_profile(db, customer_id, branch_id=branch.id)
    if profile is None:
        raise AppError("NOT_FOUND", "Müşteri bulunamadı.", 404)

    appointments = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.staff),
        )
        .where(Appointment.customer_id == customer_id)
        .order_by(Appointment.date.desc(), Appointment.start_min.desc())
        .limit(50)
    ).all()

    notes = db.scalars(
        select(CustomerNote)
        .options(selectinload(CustomerNote.staff))
        .where(CustomerNote.customer_id == customer_id)
        .order_by(CustomerNote.created_at.desc())
    ).all()

    photos = db.scalars(
        select(CustomerPhoto)
        .options(selectinload(CustomerPhoto.staff))
        .where(CustomerPhoto.customer_id == customer_id)
        .order_by(CustomerPhoto.created_at.desc())
    ).all()

    allergies = db.scalars(
        select(Allergy).where(Allergy.customer_id == customer_id).order_by(Allergy.severity)
    ).all()

    loyalty = db.scalars(
        select(LoyaltyEntry)
        .where(LoyaltyEntry.customer_id == customer_id)
        .order_by(LoyaltyEntry.created_at.desc())
        .limit(20)
    ).all()

    return {
        "profile": {
            k: profile[k]
            for k in (
                "id", "firstName", "lastName", "phone", "email", "birthDate",
                "engagementOptIn", "marketingConsent", "healthConsent",
                "loyaltyPoints", "tier", "tierProgress",
                "totalSpend", "visitCount", "noShowCount", "lastVisitDaysAgo",
            )
        },
        "segment": profile["segment"],
        #: KVKK: yalnizca toplulastirilmis skor - baska salonun adi YOK
        "risk": profile["risk"],
        "colors": profile["colors"],
        "campaigns": profile["campaigns"],
        "allergies": [
            {"id": a.id, "label": a.label, "severity": a.severity, "note": a.note}
            for a in allergies
        ],
        #: Gizli usta notlari - bu uc disinda ASLA donmez
        "notes": [
            {
                "id": n.id,
                "body": n.body,
                "visibility": n.visibility,
                "staffName": n.staff.name if n.staff else None,
                "createdAt": n.created_at.isoformat(),
            }
            for n in notes
        ],
        "album": [
            {
                "id": p.id,
                "imageUrl": p.image_url,
                "note": p.note,
                "colorTag": p.color_tag,
                "productInfo": p.product_info,
                "staffName": p.staff.name if p.staff else None,
                "createdAt": p.created_at.isoformat(),
            }
            for p in photos
        ],
        "appointments": [
            {
                "id": a.id,
                "date": a.date,
                "dateLabel": format_date_tr(a.date),
                "startLabel": minutes_to_label(a.start_min),
                "status": a.status,
                "totalPrice": a.total_price,
                "staffName": a.staff.name,
                "services": [i.service.name for i in a.items],
            }
            for a in appointments
        ],
        "loyaltyLedger": [
            {
                "id": entry.id,
                "delta": entry.delta,
                "reason": entry.reason,
                "createdAt": entry.created_at.isoformat(),
            }
            for entry in loyalty
        ],
    }


class AllergyBody(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    severity: str = "HIGH"
    note: str | None = Field(default=None, max_length=500)
    #: KVKK m.6: alerji saglik verisidir. Musterinin ilk alerji kaydinda
    #: personel, musteriden acik riza alindigini teyit etmek ZORUNDADIR.
    consentConfirmed: bool = False

    @field_validator("severity")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in ("LOW", "MEDIUM", "HIGH"):
            raise ValueError("Geçersiz şiddet.")
        return v


@router.post("/customers/{customer_id}/allergy")
def add_allergy(customer_id: int, body: AllergyBody, staff: StaffDep, db: DbSession) -> dict:
    """ALERJI IKAZ KUTUSU'nun kaynagi.

    Kayit eklendiginde bu musterinin randevusu takvimde kirmizi isaretle
    gorunur ve randevu olusturma yanitinda ``allergyWarnings`` alaninda
    doner - usta isleme baslamadan uyariyi gorur.
    """
    customer = db.get(Customer, customer_id)
    if customer is None or customer.anonymized_at is not None:
        raise AppError("NOT_FOUND", "Müşteri bulunamadı.", 404)
    if customer.health_consent_at is None:
        if not body.consentConfirmed:
            raise AppError(
                "CONSENT_REQUIRED",
                "Alerji bilgisi sağlık verisidir. Kaydetmeden önce müşterinin açık rızasını "
                "aldığınızı onaylayın.",
                400,
            )
        customer.health_consent_at = now_local()

    allergy = Allergy(
        customer_id=customer_id, label=body.label, severity=body.severity, note=body.note
    )
    db.add(allergy)
    db.commit()
    return {
        "allergy": {
            "id": allergy.id,
            "label": allergy.label,
            "severity": allergy.severity,
            "note": allergy.note,
        }
    }


@router.delete("/customers/{customer_id}/allergy")
def delete_allergy(
    customer_id: int, staff: StaffDep, db: DbSession, allergyId: int = Query(gt=0)
) -> dict:
    from sqlalchemy import delete as sa_delete

    count = db.execute(
        sa_delete(Allergy).where(Allergy.id == allergyId, Allergy.customer_id == customer_id)
    ).rowcount
    db.commit()
    return {"deleted": count or 0}


class NoteBody(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    #: STAFF_ONLY = musteriye ASLA gosterilmez (varsayilan)
    visibility: str = "STAFF_ONLY"

    @field_validator("visibility")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in ("STAFF_ONLY", "SHARED"):
            raise ValueError("Geçersiz görünürlük.")
        return v


@router.post("/customers/{customer_id}/note")
def add_note(customer_id: int, body: NoteBody, staff: StaffDep, db: DbSession) -> dict:
    """Gizli usta notu ekler.

    Varsayilan ``STAFF_ONLY``: not yalnizca personel uclarinda gorunur.
    """
    note = CustomerNote(
        customer_id=customer_id,
        staff_id=staff.id,
        body=body.body,
        visibility=body.visibility,
    )
    db.add(note)
    db.commit()
    return {
        "note": {
            "id": note.id,
            "body": note.body,
            "visibility": note.visibility,
            "staffName": staff.name,
            "createdAt": note.created_at.isoformat(),
        }
    }


@router.delete("/customers/{customer_id}/note")
def delete_note(
    customer_id: int, staff: StaffDep, db: DbSession, noteId: int = Query(gt=0)
) -> dict:
    from sqlalchemy import delete as sa_delete

    count = db.execute(
        sa_delete(CustomerNote).where(
            CustomerNote.id == noteId, CustomerNote.customer_id == customer_id
        )
    ).rowcount
    db.commit()
    return {"deleted": count or 0}


@router.post("/customers/{customer_id}/photo")
async def add_photo(
    customer_id: int,
    staff: StaffDep,
    db: DbSession,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    colorTag: str | None = Form(default=None),
    productInfo: str | None = Form(default=None),
    appointmentId: int | None = Form(default=None),
) -> dict:
    """ISLEM GECMISI ALBUMU: usta randevu sonunda fotograf + not + urun
    bilgisini yukler.

    ``colorTag`` alani RENK EGILIMI analizinin veri kaynagidir.
    """
    stored = await store_upload(file, "album")

    photo = CustomerPhoto(
        customer_id=customer_id,
        appointment_id=appointmentId,
        staff_id=staff.id,
        image_url=stored.url,
        note=(note or None),
        color_tag=(colorTag.strip().casefold() if colorTag else None),
        product_info=(productInfo or None),
    )
    db.add(photo)
    db.commit()
    return {
        "photo": {
            "id": photo.id,
            "imageUrl": photo.image_url,
            "note": photo.note,
            "colorTag": photo.color_tag,
            "productInfo": photo.product_info,
        }
    }


@router.delete("/customers/{customer_id}/photo")
def delete_photo(
    customer_id: int, staff: StaffDep, db: DbSession, photoId: int = Query(gt=0)
) -> dict:
    from sqlalchemy import delete as sa_delete

    # Dosya diskte birakilir (geri alma imkani); yalnizca kayit silinir.
    count = db.execute(
        sa_delete(CustomerPhoto).where(
            CustomerPhoto.id == photoId, CustomerPhoto.customer_id == customer_id
        )
    ).rowcount
    db.commit()
    return {"deleted": count or 0}


# ---------------------------------------------------------------------
# Stok
# ---------------------------------------------------------------------


@router.get("/inventory")
def inventory(staff: StaffDep, db: DbSession) -> dict:
    """Stok listesi + KRITIK SEVIYE UYARILARI."""
    branch = get_default_branch(db)

    items = db.scalars(
        select(InventoryItem)
        .options(selectinload(InventoryItem.used_by))
        .where(InventoryItem.branch_id == branch.id)
        .order_by(InventoryItem.name)
    ).all()

    # Kalem basina son 5 hareket. Tek bir global "son 200" sorgusu, az
    # hareketli kalemlerin gecmisini sessizce kaybederdi.
    recent_by_item: dict[int, list[StockMovement]] = {
        i.id: list(
            db.scalars(
                select(StockMovement)
                .where(StockMovement.item_id == i.id)
                .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
                .limit(5)
            )
        )
        for i in items
    }

    service_names = {
        s.id: s.name for s in db.scalars(select(Service).where(Service.branch_id == branch.id))
    }

    return {
        "items": [
            {
                "id": i.id,
                "name": i.name,
                "unit": i.unit,
                "quantity": i.quantity,
                "criticalLevel": i.critical_level,
                "costPerUnit": i.cost_per_unit,
                "isCritical": i.quantity <= i.critical_level,
                "usedByServices": [
                    {
                        "serviceId": u.service_id,
                        "name": service_names.get(u.service_id),
                        "qtyPerUse": u.qty_per_use,
                    }
                    for u in i.used_by
                ],
                "recentMovements": [
                    {
                        "id": m.id,
                        "delta": m.delta,
                        "reason": m.reason,
                        "createdAt": m.created_at.isoformat(),
                    }
                    for m in recent_by_item[i.id]
                ],
            }
            for i in items
        ],
        "criticalWarnings": critical_items(db, branch.id),
    }


class InventoryCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    unit: str = "adet"
    quantity: float = 0
    criticalLevel: float = 0
    costPerUnit: float | None = None


@router.post("/inventory")
def create_inventory(body: InventoryCreateBody, manager: ManagerDep, db: DbSession) -> dict:
    branch = get_default_branch(db)
    item = InventoryItem(
        branch_id=branch.id,
        name=body.name,
        unit=body.unit,
        quantity=body.quantity,
        critical_level=body.criticalLevel,
        cost_per_unit=body.costPerUnit,
    )
    db.add(item)
    db.commit()
    return {"item": {"id": item.id, "name": item.name, "quantity": item.quantity}}


class InventoryPatchBody(BaseModel):
    itemId: int = Field(gt=0)
    #: Stok hareketi: pozitif = giris, negatif = dusum
    delta: float | None = None
    reason: str = "MANUAL_ADJUST"
    note: str | None = Field(default=None, max_length=300)
    criticalLevel: float | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("reason")
    @classmethod
    def _valid_reason(cls, v: str) -> str:
        if v not in ("PURCHASE", "MANUAL_ADJUST", "WASTE"):
            raise ValueError("Geçersiz hareket nedeni.")
        return v


@router.patch("/inventory")
def patch_inventory(body: InventoryPatchBody, staff: StaffDep, db: DbSession) -> dict:
    """Hem alan guncellemesi hem stok hareketi.

    Hareket ``adjust_stock`` ile yazilir: miktar ve hareket kaydi AYNI
    transaction'da degisir.
    """
    item = db.get(InventoryItem, body.itemId)
    if item is None:
        raise AppError("NOT_FOUND", "Stok kalemi bulunamadı.", 404)

    if body.name is not None:
        item.name = body.name
    if body.criticalLevel is not None:
        item.critical_level = body.criticalLevel
    db.commit()

    if body.delta:
        adjust_stock(db, body.itemId, body.delta, body.reason, body.note)

    db.refresh(item)
    return {
        "item": {
            "id": item.id,
            "name": item.name,
            "quantity": item.quantity,
            "criticalLevel": item.critical_level,
            "unit": item.unit,
        }
    }


# ---------------------------------------------------------------------
# Kampanyalar
# ---------------------------------------------------------------------


@router.get("/campaigns")
def campaigns(staff: StaffDep, db: DbSession) -> dict:
    branch = get_default_branch(db)
    rows = db.scalars(
        select(Campaign)
        .where(Campaign.branch_id == branch.id)
        .order_by(Campaign.priority.desc(), Campaign.id)
    ).all()

    grant_counts: dict[int, int] = {}
    for campaign_id in db.scalars(select(CampaignGrant.campaign_id)):
        grant_counts[campaign_id] = grant_counts.get(campaign_id, 0) + 1

    # Kapsam: kural GERCEK musteri profillerine uygulanir.
    match_counts, customer_count = campaign_match_counts(db, branch.id, rows)

    return {
        "campaigns": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "kind": c.kind,
                "value": c.value,
                # Metin yerine cozumlenmis nesne donulur.
                "targetRule": parse_target_rule(c.target_rule),
                "priority": c.priority,
                "isActive": c.is_active,
                "startsAt": c.starts_at.isoformat() if c.starts_at else None,
                "endsAt": c.ends_at.isoformat() if c.ends_at else None,
                "grantCount": grant_counts.get(c.id, 0),
                #: Su anda bu kurala uyan musteri sayisi
                "matchedCount": match_counts.get(c.id, 0),
            }
            for c in rows
        ],
        #: Kapsam oraninin paydasi
        "customerCount": customer_count,
    }


class CampaignBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    kind: str
    value: float = Field(ge=0)
    targetRule: dict = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0, le=100)
    startsAt: datetime | None = None
    endsAt: datetime | None = None

    @field_validator("kind")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in ("DISCOUNT_PERCENT", "FREE_SERVICE", "BONUS_POINTS"):
            raise ValueError("Geçersiz kampanya türü.")
        return v


@router.post("/campaigns")
def create_campaign(body: CampaignBody, manager: ManagerDep, db: DbSession) -> dict:
    branch = get_default_branch(db)
    campaign = Campaign(
        branch_id=branch.id,
        name=body.name,
        description=body.description,
        kind=body.kind,
        value=body.value,
        target_rule=json.dumps(body.targetRule),
        priority=body.priority,
        starts_at=body.startsAt,
        ends_at=body.endsAt,
    )
    db.add(campaign)
    db.commit()
    return {"campaign": {"id": campaign.id, "name": campaign.name}}


class CampaignPatchBody(BaseModel):
    id: int = Field(gt=0)
    name: str | None = None
    description: str | None = None
    kind: str | None = None
    value: float | None = None
    targetRule: dict | None = None
    priority: int | None = None
    isActive: bool | None = None
    startsAt: datetime | None = None
    endsAt: datetime | None = None


@router.patch("/campaigns")
def patch_campaign(body: CampaignPatchBody, manager: ManagerDep, db: DbSession) -> dict:
    campaign = db.get(Campaign, body.id)
    if campaign is None:
        raise AppError("NOT_FOUND", "Kampanya bulunamadı.", 404)

    for field, column in (
        ("name", "name"),
        ("description", "description"),
        ("kind", "kind"),
        ("value", "value"),
        ("priority", "priority"),
        ("isActive", "is_active"),
        ("startsAt", "starts_at"),
        ("endsAt", "ends_at"),
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(campaign, column, value)

    if body.targetRule is not None:
        campaign.target_rule = json.dumps(body.targetRule)

    db.commit()
    return {"campaign": {"id": campaign.id, "isActive": campaign.is_active}}


# ---------------------------------------------------------------------
# Hatirlatma kurallari
# ---------------------------------------------------------------------


@router.get("/reminder-rules")
def reminder_rules(staff: StaffDep, db: DbSession) -> dict:
    """Kurallar + her kural icin ORNEK HESAP.

    Yonetici "bu kural bugun kac gun sonrasina hatirlatma kurardi"
    sorusunu formulu okumadan gorur.
    """
    branch = get_default_branch(db)
    rules = db.scalars(
        select(ReminderRule)
        .options(selectinload(ReminderRule.service), selectinload(ReminderRule.category))
        .where(ReminderRule.branch_id == branch.id)
        .order_by(ReminderRule.priority.desc(), ReminderRule.id)
    ).all()

    now = now_local()

    def preview(r: ReminderRule, product_key: str | None) -> int:
        return compute_interval_days(
            ReminderRuleSpec(
                id=r.id,
                name=r.name,
                service_id=r.service_id,
                category_id=r.category_id,
                formula=r.formula,
                base_days=r.base_days,
                params=r.params,
                channel=r.channel,
                template=r.template,
                priority=r.priority,
                is_active=r.is_active,
            ),
            ReminderContext(
                service_id=r.service_id or 0,
                category_id=r.category_id,
                service_name=r.service.name if r.service else "Hizmet",
                customer_name="Örnek",
                performed_at=now,
                product_key=product_key,
            ),
        )

    return {
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "service": {"id": r.service.id, "name": r.service.name} if r.service else None,
                "category": (
                    {"id": r.category.id, "name": r.category.name} if r.category else None
                ),
                "formula": r.formula,
                "baseDays": r.base_days,
                "params": json.loads(r.params or "{}"),
                "preReminderHours": r.pre_reminder_hours,
                "channel": r.channel,
                "template": r.template,
                "priority": r.priority,
                "isActive": r.is_active,
                #: Bugun uygulansaydi kac gun sonrasina kurulurdu (urun bilinmiyor)
                "previewDays": preview(r, None),
                #: Ayni onizleme, PRODUCT_LIFETIME icin ornek urunle ("kalici_oje").
                #: Panel bu degeri gosterir - urun anahtari olmadan urun omru
                #: formulu her zaman ``baseDays``e duser ve etkisi gorunmez.
                "samplePreviewDays": preview(
                    r, "kalici_oje" if r.formula == "PRODUCT_LIFETIME" else None
                ),
            }
            for r in rules
        ]
    }


@router.get("/notifications")
def notifications(
    staff: StaffDep, db: DbSession, limit: int = Query(default=25, ge=1, le=200)
) -> dict:
    """Bildirim kuyrugu: vadesi en yakin ``limit`` kayit (varsayilan 25)."""
    return {"notifications": list_notification_queue(db, take=limit)}


@router.get("/messaging/status")
def messaging_status(manager: ManagerDep) -> dict:
    """Mesaj surucusunun durumu. WhatsApp (Evolution) icin ``state``
    ``open`` degilse numara bagli degildir: OTP ve hatirlatmalar gitmez,
    QR kodunun yeniden okutulmasi gerekir.

    ``state``: open | connecting | close | missing (instance hic
    olusturulmamis) | unreachable (Evolution API'ye ulasilamiyor)."""
    admin = messaging.get_evolution_admin()
    if admin is None:
        return {"driver": messaging.get_sender().name, "ready": True, "state": "console"}
    try:
        state = admin.state()
    except messaging.DeliveryError as error:
        return {"driver": "evolution", "ready": False, "state": "unreachable", "error": str(error)}
    return {"driver": "evolution", "ready": state == "open", "state": state}


def _require_evolution() -> messaging.EvolutionAdmin:
    admin = messaging.get_evolution_admin()
    if admin is None:
        raise AppError(
            "VALIDATION",
            "WhatsApp sürücüsü kapalı. Sunucuda NOTIFICATION_DRIVER=evolution ayarlanmalı.",
            409,
        )
    return admin


@router.post("/messaging/qr")
def messaging_qr(owner: OwnerDep) -> dict:
    """WhatsApp numarasini baglamak icin QR kodu uretir (instance yoksa
    olusturur). Numara zaten bagliysa ``qr`` null doner. QR ~40 saniye
    gecerlidir; panel suresi dolunca bu ucu yeniden cagirir."""
    admin = _require_evolution()
    try:
        qr = admin.request_qr()
    except messaging.DeliveryError as error:
        raise AppError(
            "DELIVERY_FAILED", f"WhatsApp geçidine ulaşılamadı: {error}", 502
        ) from error
    if qr is None:
        return {"state": "open", "qr": None, "pairingCode": None}
    return {"state": "connecting", "qr": qr.image, "pairingCode": qr.pairing_code}


@router.post("/messaging/logout")
def messaging_logout(owner: OwnerDep) -> dict:
    """Numaranin baglantisini keser. Sonrasinda OTP ve hatirlatmalar
    gitmez; yeniden baglamak icin QR okutulmalidir."""
    admin = _require_evolution()
    try:
        admin.logout()
    except messaging.DeliveryError as error:
        raise AppError("DELIVERY_FAILED", f"Bağlantı kesilemedi: {error}", 502) from error
    return {"state": "close"}


def _welcome_payload(salon: Salon) -> dict:
    return {
        "enabled": salon.whatsapp_welcome_enabled,
        #: Kaydedilmis ozel metin; null ise varsayilan kullaniliyor.
        "message": salon.whatsapp_welcome_message,
        "defaultMessage": whatsapp_inbound.DEFAULT_WELCOME,
        "placeholders": whatsapp_inbound.PLACEHOLDERS,
        "maxLength": whatsapp_inbound.MAX_WELCOME_LENGTH,
        #: Yer tutuculari doldurulmus hali - musteriye giden metin.
        "preview": whatsapp_inbound.render_welcome(salon),
        #: False ise gelen mesajlar alinmiyor (EVOLUTION_WEBHOOK_URL yok).
        "inboundConfigured": bool(config.evolution_webhook_url),
    }


def _salon(db: DbSession) -> Salon:
    salon = db.scalar(select(Salon).order_by(Salon.id).limit(1))
    if salon is None:
        raise AppError("NOT_FOUND", "Salon bulunamadı.", 404)
    return salon


@router.get("/messaging/welcome")
def get_welcome(manager: ManagerDep, db: DbSession) -> dict:
    """Ilk mesajda gonderilen WhatsApp karsilama mesaji ayarlari."""
    return _welcome_payload(_salon(db))


class WelcomeBody(BaseModel):
    enabled: bool
    #: Bos/null -> varsayilan metne don.
    message: str | None = Field(default=None, max_length=whatsapp_inbound.MAX_WELCOME_LENGTH)


@router.put("/messaging/welcome")
def put_welcome(body: WelcomeBody, manager: ManagerDep, db: DbSession) -> dict:
    salon = _salon(db)
    message = (body.message or "").strip()
    salon.whatsapp_welcome_enabled = body.enabled
    # Varsayilanla ayni metin kaydedilmez: varsayilan ileride guncellenirse
    # bu salon da guncel metni alir.
    salon.whatsapp_welcome_message = (
        message if message and message != whatsapp_inbound.DEFAULT_WELCOME else None
    )
    db.commit()
    return _welcome_payload(salon)


class ReminderRuleBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    serviceId: int | None = None
    categoryId: int | None = None
    formula: str
    baseDays: int = Field(ge=1, le=400)
    params: dict = Field(default_factory=dict)
    preReminderHours: int | None = Field(default=24, ge=0, le=168)
    channel: str = "SMS"
    template: str = Field(min_length=1, max_length=500)
    priority: int = Field(default=0, ge=0, le=100)

    @field_validator("formula")
    @classmethod
    def _valid_formula(cls, v: str) -> str:
        if v not in ("FIXED", "GROWTH", "PRODUCT_LIFETIME", "SEASONAL"):
            raise ValueError("Geçersiz formül.")
        return v


def _assert_params_match_formula(formula: str, params: dict) -> None:
    """Formulun gerektirdigi parametreler eksikse kural sessizce yanlis calisir."""
    if formula == "GROWTH" and not (params.get("mmPerMonth") and params.get("toleranceMm")):
        raise AppError("VALIDATION", "GROWTH formülü `mmPerMonth` ve `toleranceMm` ister.", 400)
    if formula == "PRODUCT_LIFETIME" and not params.get("productDays"):
        raise AppError("VALIDATION", "PRODUCT_LIFETIME formülü `productDays` ister.", 400)
    if formula == "SEASONAL" and not params.get("monthFactors"):
        raise AppError("VALIDATION", "SEASONAL formülü `monthFactors` ister.", 400)


@router.post("/reminder-rules")
def create_reminder_rule(body: ReminderRuleBody, manager: ManagerDep, db: DbSession) -> dict:
    branch = get_default_branch(db)
    _assert_params_match_formula(body.formula, body.params)

    rule = ReminderRule(
        branch_id=branch.id,
        name=body.name,
        service_id=body.serviceId,
        category_id=body.categoryId,
        formula=body.formula,
        base_days=body.baseDays,
        params=json.dumps(body.params),
        pre_reminder_hours=body.preReminderHours,
        channel=body.channel,
        template=body.template,
        priority=body.priority,
    )
    db.add(rule)
    db.commit()
    return {"rule": {"id": rule.id, "name": rule.name}}


class ReminderRulePatchBody(BaseModel):
    id: int = Field(gt=0)
    name: str | None = None
    formula: str | None = None
    baseDays: int | None = None
    params: dict | None = None
    preReminderHours: int | None = None
    channel: str | None = None
    template: str | None = None
    priority: int | None = None
    isActive: bool | None = None


@router.patch("/reminder-rules")
def patch_reminder_rule(body: ReminderRulePatchBody, manager: ManagerDep, db: DbSession) -> dict:
    rule = db.get(ReminderRule, body.id)
    if rule is None:
        raise AppError("NOT_FOUND", "Kural bulunamadı.", 404)

    if body.formula and body.params is not None:
        _assert_params_match_formula(body.formula, body.params)

    for field, column in (
        ("name", "name"),
        ("formula", "formula"),
        ("baseDays", "base_days"),
        ("preReminderHours", "pre_reminder_hours"),
        ("channel", "channel"),
        ("template", "template"),
        ("priority", "priority"),
        ("isActive", "is_active"),
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(rule, column, value)

    if body.params is not None:
        rule.params = json.dumps(body.params)

    db.commit()
    return {"rule": {"id": rule.id, "isActive": rule.is_active}}


# ---------------------------------------------------------------------
# Yorum moderasyonu
# ---------------------------------------------------------------------


@router.get("/reviews")
def admin_reviews(staff: StaffDep, db: DbSession) -> dict:
    """Moderasyon listesi (son 100, yayindan kaldirilanlar dahil) + ozet.

    Yanitsiz dusuk puanli yorumlar ayrica sayilir - panelde uyari olarak
    gosterilir.
    """
    branch = get_default_branch(db)
    reviews = list_admin_reviews(db, branch.id, take=100)
    pending = count_unanswered_low_ratings(db, branch.id)

    return {
        "reviews": reviews,
        #: Yayindaki yorumlarin ozeti (vitrindekiyle ayni hesap)
        "summary": get_review_summary(db, branch.id),
        #: Yayinda olup yanitlanmamis dusuk puanli (<= 3) yorumlar
        "pendingCount": pending,
        #: Geriye uyumluluk icin ``pendingCount`` ile ayni deger
        "needsReply": pending,
    }


class ReviewPatchBody(BaseModel):
    isPublished: bool | None = None
    isFeatured: bool | None = None
    #: Bos string yaniti kaldirir
    reply: str | None = Field(default=None, max_length=600)


@router.patch("/reviews/{review_id}")
def patch_review(review_id: int, body: ReviewPatchBody, staff: StaffDep, db: DbSession) -> dict:
    """Yorum moderasyonu: yayindan kaldirma, one cikarma ve salon yaniti.

    Yorumun METNI ve PUANI burada DEGISTIRILEMEZ - bilerek. Bir salonun
    musterisinin sozunu duzenleyebilmesi, yorumlarin tamamini degersiz
    kilar.
    """
    review = db.get(Review, review_id)
    if review is None:
        raise AppError("NOT_FOUND", "Yorum bulunamadı.", 404)

    if body.isPublished is not None:
        review.is_published = body.isPublished
    if body.isFeatured is not None:
        review.is_featured = body.isFeatured
    if body.reply is not None:
        review.reply = body.reply or None
        review.replied_at = now_local() if body.reply else None

    db.commit()
    return {
        "id": review.id,
        "isPublished": review.is_published,
        "isFeatured": review.is_featured,
        "reply": review.reply,
    }


# ---------------------------------------------------------------------
# Firsat saati isi haritasi
# ---------------------------------------------------------------------


@router.get("/stats/opportunity")
def opportunity_stats(staff: StaffDep, db: DbSession) -> dict:
    """FIRSAT SAATI ISI HARITASI (gun x saat).

    Ham doluluk dogrudan gosterilmez: kucuk orneklemde "sali 10:00'da %0
    doluluk" gibi yaniltici sonuclar cikar. ``score_opportunity`` Bayes
    shrinkage uygular.
    """
    branch = get_default_branch(db)
    stats = db.scalars(
        select(OccupancyStat)
        .where(OccupancyStat.branch_id == branch.id)
        .order_by(OccupancyStat.weekday, OccupancyStat.slot_min)
    ).all()

    # Sube ortalamasi, Bayes onselinin merkezi olur.
    total_samples = sum(s.sample_size for s in stats)
    global_mean = (
        sum(s.occupancy * s.sample_size for s in stats) / total_samples
        if total_samples
        else 0.5
    )
    cfg = with_global_mean(DEFAULT_OPPORTUNITY_CONFIG, global_mean)

    cells = []
    for s in stats:
        score = score_opportunity(
            OccupancySample(s.weekday, s.slot_min, s.occupancy, s.sample_size), cfg
        )
        cells.append(
            {
                "weekday": s.weekday,
                "weekdayLabel": weekday_name_tr(s.weekday),
                "slotMin": s.slot_min,
                "slotLabel": minutes_to_label(s.slot_min),
                "sampleSize": s.sample_size,
                "rawOccupancy": score.raw_occupancy,
                "adjustedOccupancy": score.adjusted_occupancy,
                "opportunityIndex": score.opportunity_index,
                "discountRate": score.discount_rate,
                "isOpportunity": score.is_opportunity,
                "label": score.label,
            }
        )

    best = sorted(
        (c for c in cells if c["discountRate"] > 0),
        key=lambda c: -c["opportunityIndex"],
    )[:8]

    return {
        "globalMeanOccupancy": round(global_mean, 4),
        "totalSamples": total_samples,
        "slotMinutes": sorted({c["slotMin"] for c in cells}),
        "cells": cells,
        #: Panelin "en olu 8 saat" ozeti
        "bestOpportunities": best,
    }


# ---------------------------------------------------------------------
# Portfolyo
# ---------------------------------------------------------------------


@router.get("/portfolio")
def admin_portfolio(staff: StaffDep, db: DbSession) -> dict:
    """Galeri yonetimi: tum isler (siralama + en yeni) ve form secenekleri."""
    branch = get_default_branch(db)
    return list_admin_portfolio(db, branch.id)


@router.post("/portfolio")
async def add_portfolio(
    staff: StaffDep,
    db: DbSession,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str | None = Form(default=None),
    categoryId: int | None = Form(default=None),
    staffId: int | None = Form(default=None),
) -> dict:
    """Galeriye is ekler.

    Yukleyen personel varsayilan olarak isin sahibi sayilir; farkli bir
    usta secilebilir (asistan yukluyorsa).
    """
    branch = get_default_branch(db)
    if not title.strip():
        raise AppError("VALIDATION", "Başlık gerekli.", 400)

    stored = await store_upload(file, "portfolyo")

    item = PortfolioItem(
        branch_id=branch.id,
        category_id=categoryId,
        staff_id=staffId or staff.id,
        title=title.strip(),
        image_url=stored.url,
        description=(description or None),
    )
    db.add(item)
    db.commit()
    return {"item": {"id": item.id, "title": item.title, "imageUrl": item.image_url}}


@router.delete("/portfolio")
def delete_portfolio(staff: StaffDep, db: DbSession, id: int = Query(gt=0)) -> dict:
    from sqlalchemy import delete as sa_delete

    branch = get_default_branch(db)
    count = db.execute(
        sa_delete(PortfolioItem).where(
            PortfolioItem.id == id, PortfolioItem.branch_id == branch.id
        )
    ).rowcount
    db.commit()
    return {"deleted": count or 0}
