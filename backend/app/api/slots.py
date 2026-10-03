"""Musaitlik ve slot kilidi uclari.

  POST   /api/availability        - zamanlama motorunun HTTP sarmalayicisi
  POST   /api/slots/lock          - secilen saati 5 dakikaligina tut
  DELETE /api/slots/lock/{id}     - kilidi hemen birak
  GET    /api/slots/lock/active   - bu oturumun acik kilidi (varsa)
  POST   /api/slots/view          - "bu saate kac kisi bakti" (gercek sayim)
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from ..auth.sessions import get_customer_principal, get_or_create_visitor_key, read_visitor_key
from ..core.opportunity import fixed_window_discount
from ..core.package_layout import LayoutOptions, layout_package
from ..deps import DbSession
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import SlotViewEvent
from ..services.availability import compute_availability
from ..services.booking_for_other import (
    BeneficiaryBody,
    ensure_other_booking_allowed,
    find_beneficiary_id,
    is_self,
)
from ..services.catalog import (
    get_discount_settings,
    assert_staff_can_do,
    get_default_branch,
    get_exclusive_resource_ids,
    load_service_specs,
    validate_service_ids,
)
from ..services import deposit
from ..services.soft_lock import acquire_slot_lock, find_active_lock, release_slot_lock
from ..time_utils import is_date_key, minutes_to_label, now_local, to_date_key

router = APIRouter(tags=["slots"], route_class=EnvelopeRoute)


class AvailabilityBody(BaseModel):
    date: str
    #: Musterinin sectigi SIRAYLA hizmet id'leri (sira paket yerlesimini etkiler).
    #: Tekrarlara izin verilir: ayni hizmet iki kez secilebilir.
    serviceIds: list[int] = Field(min_length=1)
    #: None = "farketmez"
    staffId: int | None = None
    limitPerStaff: int = Field(default=60, ge=1, le=200)

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        if not is_date_key(v):
            raise ValueError('Tarih "YYYY-MM-DD" biçiminde olmalı.')
        return v


@router.post("/api/availability")
def availability(
    body: AvailabilityBody, request: Request, response: Response, db: DbSession
) -> dict:
    """Zamanlama motorunun HTTP sarmalayicisi.

    GET degil POST: hizmet listesi **sirali** bir dizidir ve query
    string'de temsili kirilgan olurdu.

    ``viewer_key`` bilerek gecilir: kullanicinin KENDI soft-lock'u kendi
    musaitlik listesini engellemesin (bkz. ``services/availability.py``,
    "Hata duzeltmesi 1").
    """
    validate_service_ids(body.serviceIds)
    viewer_key = get_or_create_visitor_key(request, response)

    return compute_availability(
        db,
        date=body.date,
        service_ids=body.serviceIds,
        staff_id=body.staffId,
        limit_per_staff=body.limitPerStaff,
        viewer_key=viewer_key,
    )


class LockBody(BaseModel):
    date: str
    serviceIds: list[int] = Field(min_length=1)
    staffId: int = Field(gt=0)
    startMin: int = Field(ge=0, le=1439)
    shadowParentAppointmentId: int | None = None
    #: Baskasi adina randevu: alici (ad + telefon). Oturum gerektirir.
    beneficiary: BeneficiaryBody | None = None

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        if not is_date_key(v):
            raise ValueError('Tarih "YYYY-MM-DD" biçiminde olmalı.')
        return v


@router.post("/api/slots/lock")
def lock_slot(body: LockBody, request: Request, response: Response, db: DbSession) -> dict:
    """Kilit ``occupancy_cell`` satirlari yazarak alinir; cakisma
    **veritabani unique kisitiyla** reddedilir, uygulama katmaninda
    "once bak sonra yaz" yapilmaz.

    Paket yerlesimi SUNUCUDA yeniden hesaplanir - istemcinin gonderdigi
    sureye guvenilmez, aksi halde 110 dakikalik paket 15 dakika olarak
    kilitlenebilirdi.
    """
    validate_service_ids(body.serviceIds)
    branch = get_default_branch(db)

    # Yetkinlik kontrolu KUME kapsamasidir (tekrar eden hizmetler elenmez).
    speed_factor = assert_staff_can_do(db, body.staffId, body.serviceIds)

    # Hata duzeltmesi: Next.js surumunde (ve ilk portta) kilit ucu yalnizca
    # hucre cakismasina bakiyordu; mesai disi (orn. 03:00), gecmis bir gun
    # ya da bugunun gecmis bir saati icin de kilit - ve ardindan randevu -
    # alinabiliyordu. Saat, motorun bu usta icin urettigi slotlardan biri
    # olmalidir. Kilit cakismalari burada degil, asagida VERITABANINDA
    # yakalanir (``SLOT_TAKEN`` + ``heldUntil`` bilgisi korunur).
    if body.date < to_date_key(now_local()):
        raise AppError("VALIDATION", "Geçmiş bir tarih için randevu alınamaz.", 400)
    structural = compute_availability(
        db,
        date=body.date,
        service_ids=body.serviceIds,
        staff_id=body.staffId,
        limit_per_staff=500,
        ignore_locks=True,
    )
    valid_starts = {
        slot["startMin"] for staff in structural["staff"] for slot in staff["slots"]
    }
    if body.startMin not in valid_starts:
        raise AppError(
            "SLOT_UNAVAILABLE",
            "Bu saat artık uygun değil. Lütfen listeden yeni bir saat seç.",
            409,
        )

    specs = load_service_specs(db, body.serviceIds)
    layout = layout_package(specs, LayoutOptions(speed_factor=speed_factor))

    customer = get_customer_principal(db, request)
    session_id = get_or_create_visitor_key(request, response)

    # Baskasi adina: oturum sart; alici kayitliysa musteri hucresi ONUN
    # icin yazilir (cakisma kontrolu alicinin takvimine gore).
    for_other = False
    beneficiary_id = None
    if body.beneficiary is not None and customer is None:
        raise AppError(
            "MEMBERSHIP_REQUIRED", "Başkası adına randevu için telefonunu doğrulamalısın.", 401
        )
    if customer is not None and not is_self(customer.phone, body.beneficiary):
        for_other = True
        ensure_other_booking_allowed(db, customer.id, body.beneficiary.phone)
        beneficiary_id = find_beneficiary_id(db, customer.phone, body.beneficiary)

    lock = acquire_slot_lock(
        db,
        branch_id=branch.id,
        staff_id=body.staffId,
        session_id=session_id,
        date=body.date,
        start_min=body.startMin,
        layout=layout,
        customer_id=customer.id if customer else None,
        exclusive_resource_ids=get_exclusive_resource_ids(db, branch.id),
        for_other=for_other,
        beneficiary_customer_id=beneficiary_id,
    )

    lock_discount = fixed_window_discount(
        lock.date, lock.start_min, get_discount_settings(db)
    )

    deposit_settings = deposit.load_settings(db)
    deposit_amount = deposit.deposit_for_price(
        deposit_settings, round(layout.total_price * (1 - lock_discount), 2)
    )
    return {
        #: Kapora onizlemesi (kapali ise enabled=false)
        "deposit": {
            "enabled": deposit_settings.enabled,
            "amount": deposit_amount,
            "percent": deposit_settings.percent,
            "policy": deposit.POLICY_TEXT if deposit_settings.enabled else None,
        },
        "lockId": lock.lock_id,
        "date": lock.date,
        "startMin": lock.start_min,
        "endMin": lock.end_min,
        "startLabel": minutes_to_label(lock.start_min),
        "endLabel": minutes_to_label(lock.end_min),
        "expiresAt": lock.expires_at.isoformat(),
        "ttlSeconds": lock.ttl_seconds,
        "totalMin": layout.total_min,
        #: totalPrice = INDIRIMSIZ tutar. Gercek tutar randevu onayinda
        #: sunucuda (o anki ayarlarla) yeniden hesaplanir.
        "totalPrice": layout.total_price,
        "discountRate": lock_discount,
        "discountedPrice": round(layout.total_price * (1 - lock_discount), 2),
        "savedMin": layout.saved_min,
    }


@router.get("/api/slots/lock/active")
def active_lock(request: Request, db: DbSession) -> dict:
    """Bu oturumun halen gecerli kilidi.

    Arayuz adimlar arasinda geri gittiginde "saat hala senin icin
    tutuluyor" diyebilsin diye eklendi; Next.js surumunde boyle bir uc
    yoktu ve geri donen kullanici kendi kilidini goremiyordu.
    """
    session_id = read_visitor_key(request)
    lock = find_active_lock(db, session_id) if session_id else None
    if lock is None:
        return {"lock": None}
    return {
        "lock": {
            "lockId": lock.id,
            "staffId": lock.staff_id,
            "date": lock.date,
            "startMin": lock.start_min,
            "endMin": lock.end_min,
            "startLabel": minutes_to_label(lock.start_min),
            "endLabel": minutes_to_label(lock.end_min),
            "expiresAt": lock.expires_at.isoformat(),
        }
    }


@router.delete("/api/slots/lock/{lock_id}")
def unlock_slot(lock_id: int, request: Request, db: DbSession) -> dict:
    """Kullanici geri gittiginde veya vazgectiginde slotu hemen birakir.

    Yalnizca kilidi TUTAN oturum birakabilir.
    """
    if lock_id <= 0:
        raise AppError("VALIDATION", "Geçersiz rezervasyon kimliği.", 400)

    session_id = read_visitor_key(request)
    if not session_id:
        raise AppError("FORBIDDEN", "Bu rezervasyon bu oturuma ait değil.", 403)

    return {"released": release_slot_lock(db, lock_id, session_id)}


class SlotViewBody(BaseModel):
    date: str
    staffId: int = Field(gt=0)
    startMin: int = Field(ge=0, le=1439)

    @field_validator("date")
    @classmethod
    def _valid_date(cls, v: str) -> str:
        if not is_date_key(v):
            raise ValueError('Tarih "YYYY-MM-DD" biçiminde olmalı.')
        return v


@router.post("/api/slots/view")
def slot_view(body: SlotViewBody, request: Request, response: Response, db: DbSession) -> dict:
    """ETIK SINIR: bu sayac uydurulmaz.

    Kayit yalnizca kullanici bir slotu fiilen inceledinde atilir ve
    gosterim ``viewer_key`` bazinda TEKIL sayilir - ayni kisinin sayfayi
    yenilemesi sayiyi sismez.
    """
    branch = get_default_branch(db)
    viewer_key = get_or_create_visitor_key(request, response)

    since = now_local() - timedelta(hours=1)
    existing = db.scalar(
        select(SlotViewEvent.id).where(
            SlotViewEvent.branch_id == branch.id,
            SlotViewEvent.staff_id == body.staffId,
            SlotViewEvent.date == body.date,
            SlotViewEvent.start_min == body.startMin,
            SlotViewEvent.viewer_key == viewer_key,
            SlotViewEvent.viewed_at >= since,
        )
    )

    if not existing:
        db.add(
            SlotViewEvent(
                branch_id=branch.id,
                staff_id=body.staffId,
                date=body.date,
                start_min=body.startMin,
                viewer_key=viewer_key,
            )
        )
        db.commit()

    viewers = db.scalars(
        select(SlotViewEvent.viewer_key)
        .where(
            SlotViewEvent.branch_id == branch.id,
            SlotViewEvent.staff_id == body.staffId,
            SlotViewEvent.date == body.date,
            SlotViewEvent.start_min == body.startMin,
        )
        .distinct()
    ).all()

    return {"viewCount": len(viewers)}
