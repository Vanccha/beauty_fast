"""Grup randevusu uclari (en fazla 4 kisi, ayni saatte, farkli ustalarla).

  POST   /api/availability/group        - ortak saatler (+ onerilen gunler)
  POST   /api/slots/lock-group          - N kilit, tek transaction (hepsi ya da hicbiri)
  DELETE /api/slots/lock-group/{id}     - grubun kilitlerini birak
  POST   /api/appointments/group        - tum kilitleri tek transaction'da randevuya cevir

Grup kilidi ve onayi UYE OTURUMU ister (``MEMBERSHIP_REQUIRED``).
Kisi basina sahiplik, kayit ve gizlilik kurallari tekil "baskasi adina"
akisiyla aynidir (``services/booking_for_other.py``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select

from ..auth.sessions import get_customer_principal, get_or_create_visitor_key, read_visitor_key
from ..config import config
from ..core.opportunity import fixed_window_discount
from ..core.package_layout import LayoutOptions, layout_package
from ..core.reminder_rules import resolve_pre_reminder
from ..deps import CustomerDep, DbSession
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import Appointment, Customer, ScheduledNotification, SlotLock, Staff
from ..services import notification_worker
from ..services import deposit, push
from ..services.appointment import confirm_appointment_from_lock
from ..services.availability import compute_availability
from ..services.booking_for_other import (
    BeneficiaryBody,
    build_beneficiary_message,
    ensure_other_booking_allowed,
    find_beneficiary_id,
    find_or_create_beneficiary,
    is_self,
    record_other_booking,
    send_beneficiary_info,
)
from ..services.booking_confirmation import (
    CONFIRM_GROUP_PREFIX,
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
from ..services.group_booking import PersonQuery, find_group_options, suggest_dates
from ..services.soft_lock import acquire_slot_lock, assert_lock_valid
from ..time_utils import is_date_key, now_local, to_date_key, to_datetime, weekday_of

router = APIRouter(tags=["group-booking"], route_class=EnvelopeRoute)

MAX_PEOPLE = 4


def _check_date(v: str) -> str:
    if not is_date_key(v):
        raise ValueError('Tarih "YYYY-MM-DD" biçiminde olmalı.')
    return v


# ------------------------------------------------------------------ availability


class GroupAvailPerson(BaseModel):
    serviceIds: list[int] = Field(min_length=1)
    staffId: int | None = None


class GroupAvailabilityBody(BaseModel):
    date: str
    people: list[GroupAvailPerson] = Field(min_length=1, max_length=MAX_PEOPLE)

    _date = field_validator("date")(_check_date)


@router.post("/api/availability/group")
def availability_group(
    body: GroupAvailabilityBody, request: Request, response: Response, db: DbSession
) -> dict:
    for p in body.people:
        validate_service_ids(p.serviceIds)
    viewer_key = get_or_create_visitor_key(request, response)

    people = [PersonQuery(tuple(p.serviceIds), p.staffId) for p in body.people]
    cache: dict = {}
    today = to_date_key(now_local())

    options = (
        [] if body.date < today else find_group_options(db, body.date, people, viewer_key, cache=cache)
    )
    suggestions = [] if options else suggest_dates(db, body.date, people, viewer_key, cache)
    return {"options": options, "suggestDates": suggestions}


# ------------------------------------------------------------------ lock-group


class GroupPersonBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    self_: bool = Field(default=False, alias="self")
    beneficiary: BeneficiaryBody | None = None

    @model_validator(mode="after")
    def _exactly_one(self):
        if self.self_ == (self.beneficiary is not None):
            raise ValueError("Her kişi için 'self' ya da 'beneficiary' (yalnızca biri) verilmeli.")
        return self


class GroupLockPerson(GroupPersonBase):
    serviceIds: list[int] = Field(min_length=1)
    staffId: int = Field(gt=0)


class LockGroupBody(BaseModel):
    date: str
    startMin: int = Field(ge=0, le=1439)
    people: list[GroupLockPerson] = Field(min_length=1, max_length=MAX_PEOPLE)

    _date = field_validator("date")(_check_date)


def _require_session(db, request: Request):
    customer = get_customer_principal(db, request)
    if customer is None:
        raise AppError(
            "MEMBERSHIP_REQUIRED", "Grup randevusu için telefonunu doğrulamalısın.", 401
        )
    return customer


def _classify(booker_phone: str, people: list[GroupPersonBase]) -> list[BeneficiaryBody | None]:
    """Kisi basina alici (None = kendisi). Tekrarlayan telefon / birden fazla
    'self' dogrulama hatasidir; alanin kendi numarasi 'self' sayilir."""
    out: list[BeneficiaryBody | None] = []
    phones: set[str] = set()
    selfs = 0
    for person in people:
        ben = None if (person.self_ or is_self(booker_phone, person.beneficiary)) else person.beneficiary
        phone = booker_phone if ben is None else ben.phone
        if ben is None:
            selfs += 1
        # Alanin kendi telefonu 'self' satirina aittir; iki kez gecemez.
        if phone in phones:
            raise AppError(
                "VALIDATION", "Grupta aynı telefon numarası birden fazla kez kullanılamaz.", 400
            )
        phones.add(phone)
        out.append(ben)
    if selfs > 1:
        raise AppError("VALIDATION", "Grupta yalnızca bir kişi 'ben' olabilir.", 400)
    return out


@router.post("/api/slots/lock-group")
def lock_group(body: LockGroupBody, request: Request, response: Response, db: DbSession) -> dict:
    """Grubun TUM slotlarini tek transaction'da tutar; biri bile alinamazsa
    hicbiri tutulmaz (``SLOT_TAKEN``). TTL normalin 2 kati."""
    customer = _require_session(db, request)
    branch = get_default_branch(db)

    if body.date < to_date_key(now_local()):
        raise AppError("VALIDATION", "Geçmiş bir tarih için randevu alınamaz.", 400)

    recipients = _classify(customer.phone, list(body.people))

    staff_ids = [p.staffId for p in body.people]
    if len(set(staff_ids)) != len(staff_ids):
        raise AppError(
            "VALIDATION", "Gruptaki her kişi için farklı bir usta seçilmelidir.", 400
        )

    # Her kisi icin: yetkinlik + saatin YAPISAL gecerliligi + yerlesim (sunucuda).
    layouts = []
    for person in body.people:
        validate_service_ids(person.serviceIds)
        speed_factor = assert_staff_can_do(db, person.staffId, person.serviceIds)
        structural = compute_availability(
            db,
            date=body.date,
            service_ids=person.serviceIds,
            staff_id=person.staffId,
            limit_per_staff=500,
            ignore_locks=True,
        )
        valid = {s["startMin"] for st in structural["staff"] for s in st["slots"]}
        if body.startMin not in valid:
            raise AppError(
                "SLOT_UNAVAILABLE",
                "Bu saat artık uygun değil. Lütfen listeden yeni bir saat seç.",
                409,
            )
        specs = load_service_specs(db, person.serviceIds)
        layouts.append(layout_package(specs, LayoutOptions(speed_factor=speed_factor)))

    # Hiz sinirlari (alici basina).
    for ben in recipients:
        if ben is not None:
            ensure_other_booking_allowed(db, customer.id, ben.phone)

    session_id = get_or_create_visitor_key(request, response)
    group_id = uuid.uuid4().hex
    ttl = config.slot_lock_ttl_seconds * 2
    exclusive = get_exclusive_resource_ids(db, branch.id)
    now = now_local()

    acquired = []
    try:
        for person, layout, ben in zip(body.people, layouts, recipients):
            for_other = ben is not None
            acquired.append(
                acquire_slot_lock(
                    db,
                    branch_id=branch.id,
                    staff_id=person.staffId,
                    session_id=session_id,
                    date=body.date,
                    start_min=body.startMin,
                    layout=layout,
                    customer_id=customer.id,
                    exclusive_resource_ids=exclusive,
                    ttl_seconds=ttl,
                    now=now,
                    for_other=for_other,
                    # Self satirinda musteri hucresi alanin kendisi icin yazilir.
                    beneficiary_customer_id=(
                        find_beneficiary_id(db, customer.phone, ben) if for_other else None
                    ),
                    group_id=group_id,
                    service_ids=person.serviceIds,
                    commit=False,
                )
            )
        db.commit()
    except Exception:
        # Tek transaction: acquire_slot_lock hata aninda zaten geri alir;
        # beklenmeyen bir hatada da hicbir kilit kalmasin.
        db.rollback()
        raise

    group_discount = fixed_window_discount(
        body.date, body.startMin, get_discount_settings(db)
    )

    deposit_settings = deposit.load_settings(db)
    person_deposits = [
        deposit.deposit_for_price(
            deposit_settings, round(layout.total_price * (1 - group_discount), 2)
        )
        for layout in layouts
    ]
    return {
        "groupId": group_id,
        "deposit": {
            "enabled": deposit_settings.enabled,
            "amount": sum(d or 0 for d in person_deposits) or None,
            "policy": deposit.POLICY_TEXT if deposit_settings.enabled else None,
        },
        "expiresAt": acquired[0].expires_at.isoformat(),
        "ttlSeconds": ttl,
        "locks": [
            {
                "personIndex": i,
                "lockId": lock.lock_id,
                "staffId": lock.staff_id,
                "startMin": lock.start_min,
                "endMin": lock.end_min,
                "totalPrice": layout.total_price,
                "discountRate": group_discount,
                "discountedPrice": round(layout.total_price * (1 - group_discount), 2),
            }
            for i, (lock, layout) in enumerate(zip(acquired, layouts))
        ],
    }


@router.delete("/api/slots/lock-group/{group_id}")
def unlock_group(group_id: str, request: Request, db: DbSession) -> dict:
    """Yalnizca bu oturumun, bu gruba ait (henuz onaylanmamis) kilitlerini birakir."""
    session_id = read_visitor_key(request)
    if not session_id:
        raise AppError("FORBIDDEN", "Bu rezervasyon bu oturuma ait değil.", 403)
    # Hucreler ON DELETE CASCADE ile birlikte silinir.
    count = db.execute(
        delete(SlotLock).where(
            SlotLock.group_id == group_id,
            SlotLock.session_id == session_id,
            SlotLock.consumed_at.is_(None),
        )
    ).rowcount
    db.commit()
    return {"released": count or 0}


# ------------------------------------------------------------------ confirm


class GroupConfirmPerson(GroupPersonBase):
    lockId: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=500)


class ConfirmGroupBody(BaseModel):
    groupId: str = Field(min_length=1, max_length=36)
    people: list[GroupConfirmPerson] = Field(min_length=1, max_length=MAX_PEOPLE)
    #: KVKK Aydinlatma Metni "okudum" teyidi (zorunlu).
    privacyNoticeAck: bool = False
    #: Saglik beyani onay kutusu (zorunlu; saglik verisi icermez).
    healthDeclaration: bool = False


@router.post("/api/appointments/group")
def confirm_group(
    body: ConfirmGroupBody, request: Request, customer: CustomerDep, db: DbSession
) -> dict:
    """Grubun tum kilitlerini TEK transaction'da randevuya cevirir
    (hepsi ya da hicbiri). Bilgilendirme mesajlari commit'ten sonra gider
    ve basarisizligi randevuyu bozmaz."""
    # KVKK zorunlu onaylari: kilit/kayit islemlerinden ONCE.
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

    branch = get_default_branch(db)
    session_id = read_visitor_key(request)
    if not session_id:
        raise AppError(
            "LOCK_NOT_FOUND", "Rezervasyon oturumu bulunamadı. Saati yeniden seçin.", 409
        )

    recipients = _classify(customer.phone, list(body.people))

    lock_ids = [p.lockId for p in body.people]
    if len(set(lock_ids)) != len(lock_ids):
        raise AppError("VALIDATION", "Aynı rezervasyon birden fazla kişiye verilemez.", 400)

    # Gonderilen kilitler BU gruba ait olmali ve grubun kilitlerinin tamami olmali.
    group_lock_ids = set(
        db.scalars(
            select(SlotLock.id).where(
                SlotLock.group_id == body.groupId,
                SlotLock.session_id == session_id,
                SlotLock.consumed_at.is_(None),
            )
        )
    )
    if group_lock_ids != set(lock_ids):
        raise AppError(
            "LOCK_NOT_FOUND", "Grup rezervasyonu bulunamadı ya da süresi doldu. Saati yeniden seçin.", 409
        )

    now = now_local()
    exclusive = get_exclusive_resource_ids(db, branch.id)

    # Alici hiz sinirlari (kayit/commit yok).
    for ben in recipients:
        if ben is not None:
            ensure_other_booking_allowed(db, customer.id, ben.phone, now)

    results: list[dict] = []
    messages: list[tuple[str, str]] = []
    confirmation_lines: list[ConfirmationLine] = []
    total = 0.0
    discount_settings = get_discount_settings(db)
    deposit_settings = deposit.load_settings(db)
    created: list[Appointment] = []

    try:
        for index, (person, ben) in enumerate(zip(body.people, recipients)):
            lock = assert_lock_valid(db, person.lockId, session_id, now, customer_id=customer.id)
            service_ids = [int(x) for x in (lock.service_ids or "").split(",") if x]
            if not service_ids:
                raise AppError("LOCK_NOT_FOUND", "Rezervasyon bulunamadı.", 404)
            validate_service_ids(service_ids)

            speed_factor = assert_staff_can_do(db, lock.staff_id, service_ids)
            specs = load_service_specs(db, service_ids)
            layout = layout_package(specs, LayoutOptions(speed_factor=speed_factor))
            discount_rate = fixed_window_discount(lock.date, lock.start_min, discount_settings)

            if ben is None:
                owner_id, owner_name, owner_phone = customer.id, customer.first_name, customer.phone
                label = None
            else:
                owner = find_or_create_beneficiary(db, ben)
                if lock.beneficiary_customer_id and lock.beneficiary_customer_id != owner.id:
                    raise AppError("VALIDATION", "Rezervasyon alıcı bilgileriyle uyuşmuyor.", 400)
                owner_id, owner_name, owner_phone = owner.id, owner.first_name, owner.phone
                label = ben.firstName

            appointment = confirm_appointment_from_lock(
                db,
                lock_id=lock.id,
                session_id=session_id,
                customer_id=owner_id,
                booker_customer_id=customer.id,
                booking_group_id=body.groupId,
                beneficiary_label=label,
                branch_id=branch.id,
                staff_id=lock.staff_id,
                date=lock.date,
                start_min=lock.start_min,
                layout=layout,
                exclusive_resource_ids=exclusive,
                discount_rate=discount_rate,
                is_opportunity=discount_rate > 0,
                notes=person.notes,
                now=now,
                privacy_notice_ack_at=now,
                health_declaration_at=now,
                deposit_settings=deposit_settings,
                commit=False,
            )
            created.append(appointment)

            pre = resolve_pre_reminder(
                appointment_id=appointment.id,
                starts_at=to_datetime(lock.date, lock.start_min),
                service_name=" + ".join(s.name for s in specs),
                customer_name=owner_name,
                hours_before=24,
            )
            if pre and not db.scalar(
                select(ScheduledNotification.id).where(
                    ScheduledNotification.dedupe_key == pre.dedupe_key
                )
            ):
                db.add(
                    ScheduledNotification(
                        customer_id=owner_id,
                        channel=pre.channel,
                        body=pre.body,
                        due_at=pre.due_at,
                        dedupe_key=pre.dedupe_key,
                    )
                )

            if ben is not None:
                record_other_booking(db, customer.id, owner_phone, now)
                messages.append(
                    (
                        owner_phone,
                        build_beneficiary_message(
                            customer.first_name,
                            lock.date,
                            lock.start_min,
                            [s.name for s in specs],
                            ben.firstName,
                        ),
                    )
                )

            staff = db.get(Staff, lock.staff_id)
            confirmation_lines.append(
                ConfirmationLine(
                    date=lock.date,
                    start_min=lock.start_min,
                    service_names=[s.name for s in specs],
                    staff_name=staff.name if staff else "",
                    for_name=None if ben is None else ben.firstName,
                )
            )
            total += appointment.total_price
            results.append(
                {
                    "personIndex": index,
                    "appointmentId": appointment.id,
                    "forCustomer": {
                        "id": owner_id,
                        "firstName": owner_name if ben is None else ben.firstName,
                    },
                    "staffName": staff.name if staff else "",
                    "date": appointment.date,
                    "startMin": appointment.start_min,
                    "endMin": appointment.end_min,
                    "totalPrice": appointment.total_price,
                    "discountRate": appointment.discount_rate,
                }
            )
        # Alana TEK ozet mesaj - randevularla ayni transaction'da. Kapora aciksa
        # onay mesajinin YERINE tek kapora talebi gider (tutar = kisi basina
        # kapora toplami).
        awaiting = [a for a in created if a.deposit_status == deposit.AWAITING]
        if awaiting:
            deposit.queue_deposit_request(
                db, awaiting, db.get(Customer, customer.id), deposit_settings
            )
        else:
            queue_confirmation(
                db,
                customer.id,
                f"{CONFIRM_GROUP_PREFIX}{body.groupId}",
                build_confirmation_message(customer.first_name, confirmation_lines),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    notification_worker.kick()
    push.notify_new_appointments([r["appointmentId"] for r in results])

    for phone, text in messages:
        send_beneficiary_info(db, phone, text)

    awaiting_total = sum(float(a.deposit_amount or 0) for a in created if a.deposit_status == deposit.AWAITING)
    deposit_info = (
        deposit.customer_view(db, created[0], deposit_settings, True)
        if any(a.deposit_status == deposit.AWAITING for a in created)
        else None
    )
    return {
        "groupId": body.groupId,
        "appointments": results,
        "totalPrice": round(total, 2),
        #: Kapora bekleniyorsa grup toplami + odeme bilgileri
        "deposit": (
            {**deposit_info, "payAmount": awaiting_total} if deposit_info else None
        ),
    }
