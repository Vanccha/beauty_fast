"""Randevu uclari.

  POST  /api/appointments               - soft-lock'u kalici randevuya cevir
  GET   /api/appointments/mine          - musterinin kendi randevulari
  GET   /api/appointments/{id}          - randevu detayi
  PATCH /api/appointments/{id}          - durum degisikligi
  POST  /api/appointments/{id}/design   - tasarim gorseli / baglantisi
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..auth.sessions import read_visitor_key
from ..core.opportunity import OccupancySample, score_opportunity
from ..core.package_layout import LayoutOptions, layout_package
from ..core.reminder_rules import resolve_pre_reminder
from ..deps import AnyPrincipalDep, CustomerDep, DbSession
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import (
    Allergy,
    Appointment,
    AppointmentItem,
    DesignReference,
    OccupancyStat,
    Review,
    ScheduledNotification,
)
from ..services.appointment import confirm_appointment_from_lock
from ..services.appointment_status import change_appointment_status
from ..services.catalog import (
    assert_staff_can_do,
    get_default_branch,
    get_exclusive_resource_ids,
    load_service_specs,
    validate_service_ids,
)
from ..time_utils import format_date_tr, is_date_key, minutes_to_label, now_local, to_date_key, to_datetime, weekday_of
from ..uploads import sanitize_external_link, store_upload

router = APIRouter(prefix="/api/appointments", tags=["appointments"], route_class=EnvelopeRoute)


class CreateAppointmentBody(BaseModel):
    lockId: int = Field(gt=0)
    date: str
    staffId: int = Field(gt=0)
    startMin: int = Field(ge=0, le=1439)
    #: Tekrarlara izin verilir (ayni hizmet iki kez secilebilir).
    serviceIds: list[int] = Field(min_length=1)
    shadowParentId: int | None = None
    notes: str | None = Field(default=None, max_length=500)
    designLink: str | None = None

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        if not is_date_key(v):
            raise ValueError('Tarih "YYYY-MM-DD" biçiminde olmalı.')
        return v


@router.post("")
def create_appointment(
    body: CreateAppointmentBody, request: Request, customer: CustomerDep, db: DbSession
) -> dict:
    """Gecerli bir soft-lock'u kalici randevuya cevirir.

    Guven siniri: istemciden gelen TEK guvenilir bilgi hangi hizmetlerin
    secildigidir. Sure, fiyat ve indirim sunucuda yeniden hesaplanir;
    ``confirm_appointment_from_lock`` ayrica kilidin ``start_min/end_min``
    degerini yeni hesapla karsilastirir.

    UYELIK SARTI: misafirler katalogu ve slotlari gorebilir, randevu icin
    ``require_customer`` gecilmelidir (``MEMBERSHIP_REQUIRED``).
    """
    validate_service_ids(body.serviceIds)
    branch = get_default_branch(db)

    session_id = read_visitor_key(request)
    if not session_id:
        raise AppError(
            "LOCK_NOT_FOUND", "Rezervasyon oturumu bulunamadı. Saati yeniden seçin.", 409
        )

    # --- Sure / fiyat: SUNUCUDA yeniden hesapla -------------------------
    speed_factor = assert_staff_can_do(db, body.staffId, body.serviceIds)
    specs = load_service_specs(db, body.serviceIds)
    layout = layout_package(specs, LayoutOptions(speed_factor=speed_factor))

    # --- Firsat saati indirimi: yine SUNUCUDA ---------------------------
    weekday = weekday_of(body.date)
    hour_bucket = (body.startMin // 60) * 60
    stat = db.scalar(
        select(OccupancyStat).where(
            OccupancyStat.branch_id == branch.id,
            OccupancyStat.weekday == weekday,
            OccupancyStat.slot_min == hour_bucket,
        )
    )
    opportunity = score_opportunity(
        OccupancySample(
            weekday=weekday,
            slot_min=hour_bucket,
            occupancy=stat.occupancy if stat else 0.5,
            sample_size=stat.sample_size if stat else 0,
        )
    )

    # --- Golge (shadow) ebeveyni: istemciye korlemesine guvenilmez --------
    # Yalnizca AYNI usta + AYNI gun + aktif bir randevunun blogu icinde
    # baslayan bir slot icin gecerlidir; aksi halde bag kurulmaz (admin
    # takviminde yanlis "golge" iliskisi gosterilmesin).
    shadow_parent_id = body.shadowParentId
    if shadow_parent_id is not None:
        parent = db.get(Appointment, shadow_parent_id)
        if (
            parent is None
            or parent.staff_id != body.staffId
            or parent.date != body.date
            or parent.status not in ("PENDING", "CONFIRMED")
            or not (parent.start_min <= body.startMin < parent.end_min)
        ):
            shadow_parent_id = None

    # --- Alerji ikazi ---------------------------------------------------
    allergies = db.scalars(select(Allergy).where(Allergy.customer_id == customer.id)).all()

    appointment = confirm_appointment_from_lock(
        db,
        lock_id=body.lockId,
        session_id=session_id,
        customer_id=customer.id,
        branch_id=branch.id,
        staff_id=body.staffId,
        date=body.date,
        start_min=body.startMin,
        layout=layout,
        exclusive_resource_ids=get_exclusive_resource_ids(db, branch.id),
        discount_rate=opportunity.discount_rate,
        is_opportunity=opportunity.is_opportunity,
        notes=body.notes,
        shadow_parent_id=shadow_parent_id,
        design_refs=(
            [{"source": "LINK", "url": sanitize_external_link(body.designLink)}]
            if body.designLink
            else None
        ),
    )

    # --- Randevu oncesi hatirlatma kuyruga alinir -----------------------
    pre = resolve_pre_reminder(
        appointment_id=appointment.id,
        starts_at=to_datetime(body.date, body.startMin),
        service_name=" + ".join(s.name for s in specs),
        customer_name=customer.first_name,
        hours_before=24,
    )
    if pre:
        exists = db.scalar(
            select(ScheduledNotification.id).where(
                ScheduledNotification.dedupe_key == pre.dedupe_key
            )
        )
        if not exists:
            db.add(
                ScheduledNotification(
                    customer_id=customer.id,
                    channel=pre.channel,
                    body=pre.body,
                    due_at=pre.due_at,
                    dedupe_key=pre.dedupe_key,
                )
            )
            db.commit()

    return {
        "appointment": {
            "id": appointment.id,
            "date": appointment.date,
            "startMin": appointment.start_min,
            "endMin": appointment.end_min,
            "startLabel": minutes_to_label(appointment.start_min),
            "endLabel": minutes_to_label(appointment.end_min),
            "totalPrice": appointment.total_price,
            "discountRate": appointment.discount_rate,
            "isOpportunity": appointment.is_opportunity,
            "version": appointment.version,
        },
        "opportunity": {
            "discountRate": opportunity.discount_rate,
            "label": opportunity.label,
            "saved": round(layout.total_price * opportunity.discount_rate, 2),
        },
        #: Randevu ekraninda KIRMIZI kutuda gosterilir
        "allergyWarnings": [
            {"label": a.label, "severity": a.severity, "note": a.note} for a in allergies
        ],
        "savedMin": layout.saved_min,
    }


@router.get("/mine")
def my_appointments(customer: CustomerDep, db: DbSession) -> dict:
    """Musterinin kendi randevulari - yaklasan ve gecmis olarak ayrilmis.

    KVKK/gizlilik: yalnizca oturum sahibinin kayitlari doner ve gizli usta
    notlari bu uca HIC dahil edilmez.
    """
    today_key = to_date_key(now_local())

    rows = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.staff),
            selectinload(Appointment.design_refs),
        )
        .where(Appointment.customer_id == customer.id)
        .order_by(Appointment.date.desc(), Appointment.start_min.desc())
    ).all()

    # Hangi randevulara yorum yazilmis? (Icerik degil, yalnizca varlik.)
    reviewed = set(
        db.scalars(
            select(Review.appointment_id).where(Review.customer_id == customer.id)
        )
    )

    def shape(a: Appointment) -> dict:
        return {
            "id": a.id,
            "date": a.date,
            "dateLabel": format_date_tr(a.date),
            "startMin": a.start_min,
            "endMin": a.end_min,
            "startLabel": minutes_to_label(a.start_min),
            "endLabel": minutes_to_label(a.end_min),
            "status": a.status,
            "totalPrice": a.total_price,
            "discountRate": a.discount_rate,
            "isOpportunity": a.is_opportunity,
            "version": a.version,
            "staff": {"id": a.staff.id, "name": a.staff.name, "photoUrl": a.staff.photo_url},
            "services": [
                {"id": i.service.id, "name": i.service.name, "price": i.price} for i in a.items
            ],
            "designRefs": [
                {"id": d.id, "source": d.source, "url": d.url} for d in a.design_refs
            ],
            #: Musteri iptal edebilir mi? (gecmis ve tamamlanmislar haric)
            "cancellable": a.date >= today_key and a.status in ("PENDING", "CONFIRMED"),
            #: Bu randevuya yorum yazilmis mi? (randevu basina tek yorum)
            "hasReview": a.id in reviewed,
        }

    is_upcoming = lambda a: a.date >= today_key and a.status in ("PENDING", "CONFIRMED")  # noqa: E731

    upcoming = sorted(
        (a for a in rows if is_upcoming(a)), key=lambda a: (a.date, a.start_min)
    )
    past = [a for a in rows if not is_upcoming(a)]

    return {"upcoming": [shape(a) for a in upcoming], "past": [shape(a) for a in past]}


def _load_owned(db: DbSession, appointment_id: int) -> Appointment:
    appointment = db.scalar(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.staff),
            selectinload(Appointment.customer),
            selectinload(Appointment.design_refs),
        )
        .where(Appointment.id == appointment_id)
    )
    if appointment is None:
        raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)
    return appointment


@router.get("/{appointment_id}")
def appointment_detail(
    appointment_id: int, principal: AnyPrincipalDep, db: DbSession
) -> dict:
    """Musteri yalnizca KENDI randevusunu gorebilir; personel hepsini.

    Gizli usta notlari bu ucta HIC donmez.
    """
    appointment = _load_owned(db, appointment_id)

    if principal.kind == "customer" and appointment.customer_id != principal.customer.id:
        raise AppError("FORBIDDEN", "Bu randevuya erişiminiz yok.", 403)

    return {
        "id": appointment.id,
        "date": appointment.date,
        "dateLabel": format_date_tr(appointment.date),
        "startMin": appointment.start_min,
        "endMin": appointment.end_min,
        "startLabel": minutes_to_label(appointment.start_min),
        "endLabel": minutes_to_label(appointment.end_min),
        "status": appointment.status,
        "version": appointment.version,
        "totalPrice": appointment.total_price,
        "discountRate": appointment.discount_rate,
        "isOpportunity": appointment.is_opportunity,
        "shadowParentId": appointment.shadow_parent_id,
        "staff": {
            "id": appointment.staff.id,
            "name": appointment.staff.name,
            "photoUrl": appointment.staff.photo_url,
        },
        "services": [
            {
                "id": i.service.id,
                "name": i.service.name,
                "price": i.price,
                "offsetMin": i.offset_min,
                "activeBeforeMin": i.active_before_min,
                "passiveMin": i.passive_min,
                "activeAfterMin": i.active_after_min,
            }
            for i in appointment.items
        ],
        "designRefs": [
            {"id": d.id, "source": d.source, "url": d.url, "note": d.note}
            for d in appointment.design_refs
        ],
        # Personel gorusunde musteri bilgisi de doner.
        "customer": (
            {
                "id": appointment.customer.id,
                "firstName": appointment.customer.first_name,
                "lastName": appointment.customer.last_name,
                "phone": appointment.customer.phone,
            }
            if principal.kind == "staff"
            else None
        ),
    }


class PatchAppointmentBody(BaseModel):
    status: str
    #: Optimistic locking - istemcinin gordugu surum
    expectedVersion: int = Field(ge=0)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in ("CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW"):
            raise ValueError("Geçersiz durum.")
        return v


#: Musterinin kendi randevusunda yapabilecegi TEK degisiklik.
CUSTOMER_ALLOWED = ("CANCELLED",)


@router.patch("/{appointment_id}")
def patch_appointment(
    appointment_id: int,
    body: PatchAppointmentBody,
    principal: AnyPrincipalDep,
    db: DbSession,
) -> dict:
    """Durum degisikligi.

    Musteri YALNIZCA iptal edebilir; diger gecisler personel yetkisi ister.
    ``expectedVersion`` zorunludur: iki sekmede acik ayni randevu uzerinde
    cakisan guncelleme ``VERSION_MISMATCH`` ile reddedilir.
    """
    appointment = _load_owned(db, appointment_id)

    if principal.kind == "customer":
        if appointment.customer_id != principal.customer.id:
            raise AppError("FORBIDDEN", "Bu randevuya erişiminiz yok.", 403)
        if body.status not in CUSTOMER_ALLOWED:
            raise AppError(
                "FORBIDDEN", "Randevu durumunu yalnızca salon güncelleyebilir.", 403
            )

    return change_appointment_status(
        db,
        appointment_id=appointment.id,
        status=body.status,
        expected_version=body.expectedVersion,
    )


@router.post("/{appointment_id}/design")
async def upload_design(
    appointment_id: int,
    customer: CustomerDep,
    db: DbSession,
    file: UploadFile | None = File(default=None),
    link: str | None = Form(default=None),
    note: str | None = Form(default=None),
) -> dict:
    """TASARIM YUKLEME: musteri istedigi modelin gorselini randevuya ilistirir.

    Dosya adi istemciden ALINMAZ; sunucu rastgele isim uretir (yol
    enjeksiyonu imkansiz).
    """
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)
    if appointment.customer_id != customer.id:
        raise AppError("FORBIDDEN", "Bu randevuya erişiminiz yok.", 403)
    if appointment.status in ("CANCELLED", "COMPLETED"):
        raise AppError(
            "VALIDATION", "Tamamlanmış veya iptal edilmiş randevuya görsel eklenemez.", 400
        )

    if file is not None and file.filename:
        stored = await store_upload(file, "tasarim")
        source, url = "UPLOAD", stored.url
    elif link and link.strip():
        source, url = "LINK", sanitize_external_link(link)
    else:
        raise AppError("VALIDATION", "Bir görsel yükleyin veya bağlantı yapıştırın.", 400)

    created = DesignReference(
        appointment_id=appointment.id, source=source, url=url, note=(note or None)
    )
    db.add(created)
    db.commit()

    return {
        "designRef": {
            "id": created.id,
            "source": created.source,
            "url": created.url,
            "note": created.note,
        }
    }
