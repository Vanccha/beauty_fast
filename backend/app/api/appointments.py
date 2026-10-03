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
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from ..auth.sessions import read_visitor_key
from ..core.opportunity import fixed_window_discount, window_label
from ..core.package_layout import LayoutOptions, layout_package
from ..core.reminder_rules import resolve_pre_reminder
from ..deps import AnyPrincipalDep, CustomerDep, DbSession
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import (
    Allergy,
    Appointment,
    AppointmentItem,
    Customer,
    DesignReference,
    Review,
    ScheduledNotification,
    Staff,
)
from ..services import notification_worker
from ..services.appointment import confirm_appointment_from_lock
from ..services import push
from ..services.appointment_status import change_appointment_status
from ..services import deposit
from ..services.booking_cancellation import queue_group_cancellation_notices
from ..services.booking_for_other import (
    BeneficiaryBody,
    build_beneficiary_message,
    ensure_other_booking_allowed,
    find_or_create_beneficiary,
    is_self,
    label_for_viewer,
    record_other_booking,
    send_beneficiary_info,
)
from ..services.booking_confirmation import (
    CONFIRM_PREFIX,
    ConfirmationLine,
    build_confirmation_message,
    queue_confirmation,
)
from ..services.catalog import (
    get_discount_settings,
    assert_staff_can_do,
    get_default_branch,
    get_exclusive_resource_ids,
    load_service_specs,
    validate_service_ids,
)
from ..time_utils import format_date_tr, is_date_key, minutes_to_label, now_local, to_date_key, to_datetime, weekday_of
from ..uploads import sanitize_external_link, store_upload

router = APIRouter(prefix="/api/appointments", tags=["appointments"], route_class=EnvelopeRoute)


class AllergyInput(BaseModel):
    """Istege bagli alerji bilgisi (ozel nitelikli saglik verisi; acik riza ister)."""

    label: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Alerji adı boş olamaz.")
        return v

    @field_validator("note")
    @classmethod
    def _strip_note(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None


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
    #: Baskasi adina randevu: randevunun sahibi (ad + telefon).
    beneficiary: BeneficiaryBody | None = None
    #: KVKK Aydinlatma Metni "okudum" teyidi (zorunlu; riza degildir).
    privacyNoticeAck: bool = False
    #: Saglik beyani onay kutusu (zorunlu; saglik verisi icermez).
    healthDeclaration: bool = False
    #: Istege bagli alerji kaydi; yalnizca ``healthConsent`` ile ve kendi adina.
    allergy: AllergyInput | None = None
    #: Alerji icin AYRI, istege bagli acik riza (KVKK m.6). Randevu buna bagli degildir.
    healthConsent: bool = False

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
    # --- KVKK: zorunlu onaylar, kilit/kayit islemlerinden ONCE ------------
    if not body.privacyNoticeAck:
        raise AppError(
            "PRIVACY_NOTICE_REQUIRED",
            "Devam etmek için Aydınlatma Metni'ni okuduğunuzu onaylamalısınız.",
            400,
        )
    if not body.healthDeclaration:
        raise AppError(
            "HEALTH_DECLARATION_REQUIRED",
            "Devam etmek için sağlık beyanını onaylamalısınız.",
            400,
        )
    if body.allergy is not None:
        if not is_self(customer.phone, body.beneficiary):
            raise AppError(
                "VALIDATION",
                "Başkası adına alınan randevuda alerji bilgisi eklenemez; kişinin kendisi salona bildirebilir.",
                400,
            )
        if not body.healthConsent:
            raise AppError(
                "CONSENT_REQUIRED",
                "Alerji bilginizi kaydetmek için açık rızanız gerekir. Rıza vermeden de randevu alabilirsiniz.",
                400,
            )

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

    # --- Firsat saati indirimi: yine SUNUCUDA (istemci orani yok sayilir) --
    # Onay anindaki ayarlarla yeniden hesaplanir; yanit bu degeri tasir.
    discount_rate = fixed_window_discount(
        body.date, body.startMin, get_discount_settings(db)
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

    # --- Randevunun sahibi: kendisi mi, baskasi mi? ---------------------
    # Alici telefonla bulunur/olusturulur (kayitli adi EZILMEZ). Randevu
    # basarisiz olursa olusturulan musteri de geri alinir (commit yok).
    for_other = not is_self(customer.phone, body.beneficiary)
    owner_id = customer.id
    owner_name = customer.first_name
    owner_phone = customer.phone
    if for_other:
        ensure_other_booking_allowed(db, customer.id, body.beneficiary.phone)
        owner = find_or_create_beneficiary(db, body.beneficiary)
        owner_id, owner_name, owner_phone = owner.id, owner.first_name, owner.phone

    # --- Alerji kaydi (acik riza ile; randevuyla AYNI transaction) -------
    now = now_local()
    if body.allergy is not None and not for_other:
        row = db.get(Customer, customer.id)
        if row is not None and row.health_consent_at is None:
            row.health_consent_at = now
        db.add(
            Allergy(
                customer_id=customer.id,
                label=body.allergy.label,
                note=body.allergy.note,
                severity="HIGH",
            )
        )
        db.flush()

    # --- Alerji ikazi ---------------------------------------------------
    # Baskasi adina randevuda alicinin saglik verisi alana GOSTERILMEZ.
    allergies = (
        []
        if for_other
        else db.scalars(select(Allergy).where(Allergy.customer_id == customer.id)).all()
    )

    deposit_settings = deposit.load_settings(db)
    appointment = confirm_appointment_from_lock(
        db,
        lock_id=body.lockId,
        session_id=session_id,
        customer_id=owner_id,
        booker_customer_id=customer.id,
        beneficiary_label=body.beneficiary.firstName if for_other else None,
        branch_id=branch.id,
        staff_id=body.staffId,
        date=body.date,
        start_min=body.startMin,
        layout=layout,
        exclusive_resource_ids=get_exclusive_resource_ids(db, branch.id),
        discount_rate=discount_rate,
        is_opportunity=discount_rate > 0,
        notes=body.notes,
        shadow_parent_id=shadow_parent_id,
        privacy_notice_ack_at=now,
        health_declaration_at=now,
        deposit_settings=deposit_settings,
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
        customer_name=owner_name,
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
                    customer_id=owner_id,
                    channel=pre.channel,
                    body=pre.body,
                    due_at=pre.due_at,
                    dedupe_key=pre.dedupe_key,
                )
            )
            db.commit()

    # --- Randevuyu alana onay mesaji (kuyruk + isciyi uyandir) -----------
    # Kapora aciksa normal onay mesajinin YERINE kapora talebi gider
    # (randevu PENDING + AWAITING; havale onaylaninca kesinlesir).
    staff = db.get(Staff, body.staffId)
    if appointment.deposit_status == deposit.AWAITING:
        deposit.queue_deposit_request(
            db, [appointment], db.get(Customer, customer.id), deposit_settings
        )
    else:
        queue_confirmation(
            db,
            customer.id,
            f"{CONFIRM_PREFIX}{appointment.id}",
            build_confirmation_message(
                customer.first_name,
                [
                    ConfirmationLine(
                        date=body.date,
                        start_min=body.startMin,
                        service_names=[s.name for s in specs],
                        staff_name=staff.name if staff else "",
                        for_name=body.beneficiary.firstName if for_other else None,
                    )
                ],
            ),
        )
    db.commit()
    notification_worker.kick()
    # Panel cihazlarina Web Push (arka planda, hata istegi bozmaz).
    push.notify_new_appointments([appointment.id])

    # --- Baskasi adina: sayac + aliciya bilgilendirme (commit SONRASI) ---
    if for_other:
        record_other_booking(db, customer.id, owner_phone)
        db.commit()
        send_beneficiary_info(
            db,
            owner_phone,
            build_beneficiary_message(
                customer.first_name,
                body.date,
                body.startMin,
                [s.name for s in specs],
                body.beneficiary.firstName,
            ),
        )

    return {
        "forCustomer": {
            "id": owner_id,
            # Alana alicinin KAYITLI adi degil, kendi yazdigi ad gosterilir.
            "firstName": body.beneficiary.firstName if for_other else owner_name,
        },
        "bookedForOther": for_other,
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
            "status": appointment.status,
        },
        #: Kapora bekleniyorsa odeme bilgileri (yalnizca randevuyu alana doner)
        "deposit": deposit.customer_view(db, appointment, deposit_settings, True),
        "opportunity": {
            "discountRate": discount_rate,
            "label": window_label(discount_rate),
            "saved": round(layout.total_price * discount_rate, 2),
        },
        #: Randevu ekraninda KIRMIZI kutuda gosterilir
        "allergyWarnings": [
            {"label": a.label, "severity": a.severity, "note": a.note} for a in allergies
        ],
        "savedMin": layout.saved_min,
    }


@router.get("/mine")
def my_appointments(customer: CustomerDep, db: DbSession) -> dict:
    """Musterinin randevulari: KENDI randevulari + BASKASI ADINA aldiklari
    (``bookedByMe`` ve ``isMine=false``) - yaklasan ve gecmis olarak ayrilmis.

    KVKK/gizlilik: alici (randevunun sahibi) kendi telefonuyla girince
    yalnizca ``customer_id = kendisi`` olanlari gorur; alan kisinin
    randevulari ona gorunmez. Gizli usta notlari bu uca HIC dahil edilmez.
    """
    now = now_local()
    today_key = to_date_key(now)
    deposit_settings = deposit.load_settings(db)

    rows = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.staff),
            selectinload(Appointment.design_refs),
            selectinload(Appointment.customer),
        )
        .where(
            or_(
                Appointment.customer_id == customer.id,
                Appointment.booked_by_customer_id == customer.id,
            )
        )
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
            #: Musteri iptal edebilir mi? (gecmis, tamamlanmis ve randevuya
            #: 60 dakikadan az kalanlar haric)
            "cancellable": a.date >= today_key
            and a.status in ("PENDING", "CONFIRMED")
            and not deposit.customer_cancel_locked(a, now),
            #: Randevuya 60 dakikadan az kaldi: iptal kapali (kapora iade edilmez)
            "cancelLocked": a.status in ("PENDING", "CONFIRMED")
            and deposit.customer_cancel_locked(a, now),
            "cancelLockedMessage": deposit.CANCEL_TOO_LATE_MESSAGE,
            #: Kapora (yalnizca randevuyu alan odeme bilgisini gorur)
            "deposit": deposit.customer_view(
                db, a, deposit_settings, a.booked_by_customer_id == customer.id
            ),
            #: Bu randevuya yorum yazilmis mi? (randevu basina tek yorum)
            "hasReview": a.id in reviewed,
            #: Randevunun sahibi (baskasi adina alindiysa alici)
            "forCustomer": {"id": a.customer_id, "firstName": label_for_viewer(a, customer.id)},
            #: Bu randevuyu oturumdaki kisi mi aldi?
            "bookedByMe": a.booked_by_customer_id == customer.id,
            #: Randevu oturumdaki kisinin kendisine mi ait?
            "isMine": a.customer_id == customer.id,
            "groupId": a.booking_group_id,
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


def _is_party(appointment: Appointment, customer_id: int) -> bool:
    """Randevunun sahibi ya da randevuyu alan mi? (gorme + iptal yetkisi)"""
    return customer_id in (appointment.customer_id, appointment.booked_by_customer_id)


@router.get("/{appointment_id}")
def appointment_detail(
    appointment_id: int, principal: AnyPrincipalDep, db: DbSession
) -> dict:
    """Musteri yalnizca KENDI randevusunu gorebilir; personel hepsini.

    Gizli usta notlari bu ucta HIC donmez.
    """
    appointment = _load_owned(db, appointment_id)

    # Sahibi VEYA randevuyu alan (salt okunur) gorebilir.
    if principal.kind == "customer" and not _is_party(appointment, principal.customer.id):
        raise AppError("FORBIDDEN", "Bu randevuya erişiminiz yok.", 403)

    return {
        "forCustomer": {
            "id": appointment.customer.id,
            "firstName": (
                appointment.customer.first_name
                if principal.kind == "staff"
                else label_for_viewer(appointment, principal.customer.id)
            ),
        },
        "bookedByMe": principal.kind == "customer"
        and appointment.booked_by_customer_id == principal.customer.id,
        "isMine": principal.kind == "customer"
        and appointment.customer_id == principal.customer.id,
        "groupId": appointment.booking_group_id,
        "deposit": (
            deposit.admin_view(appointment, deposit.load_settings(db), now_local())
            if principal.kind == "staff"
            else deposit.customer_view(
                db,
                appointment,
                deposit.load_settings(db),
                appointment.booked_by_customer_id == principal.customer.id,
            )
        ),
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
        if not _is_party(appointment, principal.customer.id):
            raise AppError("FORBIDDEN", "Bu randevuya erişiminiz yok.", 403)
        if body.status not in CUSTOMER_ALLOWED:
            raise AppError(
                "FORBIDDEN", "Randevu durumunu yalnızca salon güncelleyebilir.", 403
            )
        # Randevuya 60 dakikadan az kala iptal yok (kapora olsun olmasin).
        if appointment.status in ("PENDING", "CONFIRMED"):
            deposit.assert_customer_may_cancel(appointment)

    return change_appointment_status(
        db,
        appointment_id=appointment.id,
        status=body.status,
        expected_version=body.expectedVersion,
    )


@router.post("/group/{group_id}/cancel")
def cancel_group(group_id: str, customer: CustomerDep, db: DbSession) -> dict:
    """Grubun tamamini iptal eder - YALNIZCA randevulari alan kisi.

    Yalnizca bu kisinin aldigi, henuz son durumda olmayan (PENDING /
    CONFIRMED) randevular iptal edilir. Hic eslesme yoksa 404.
    """
    rows = db.scalars(
        select(Appointment).where(
            Appointment.booking_group_id == group_id,
            Appointment.booked_by_customer_id == customer.id,
        )
    ).all()
    if not rows:
        raise AppError("NOT_FOUND", "Grup randevusu bulunamadı.", 404)

    ids = [a.id for a in rows if a.status in ("PENDING", "CONFIRMED")]
    now = now_local()
    if any(deposit.customer_cancel_locked(a, now) for a in rows if a.id in ids):
        raise AppError("CANCEL_TOO_LATE", deposit.CANCEL_TOO_LATE_MESSAGE, 409)
    # Tek tek mesaj yerine alana TEK ozet + her aliciya ayri mesaj (asagida).
    for appointment_id in ids:
        change_appointment_status(
            db, appointment_id=appointment_id, status="CANCELLED", notify=False
        )
    if ids:
        cancelled = db.scalars(
            select(Appointment)
            .options(
                selectinload(Appointment.items).selectinload(AppointmentItem.service),
                selectinload(Appointment.customer),
            )
            .where(Appointment.id.in_(ids))
            .order_by(Appointment.start_min, Appointment.id)
        ).all()
        refunds = db.scalar(
            select(Appointment.id)
            .where(Appointment.id.in_(ids), Appointment.deposit_status == deposit.REFUND_DUE)
            .limit(1)
        )
        queue_group_cancellation_notices(
            db,
            db.get(Customer, customer.id),
            group_id,
            list(cancelled),
            refund_note=refunds is not None,
        )
        db.commit()
        notification_worker.kick()
    return {"groupId": group_id, "cancelled": len(ids)}


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
