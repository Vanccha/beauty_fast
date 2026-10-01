"""
====================================================================
KVKK - riza yonetimi, veri dokumu, hesap silme, saklama sureleri
====================================================================

Musteri arayuzundeki "Gizlilik ve verilerim" bolumunun ve bakim isinin
(``/api/cron/sweep``) saklama suresi temizliginin kaynagi. Metinler:
arayuzde ``/kvkk``, ``/acik-riza``, ``/cerez-politikasi``.

Rizalar iki ayri alandir ve BIRBIRINE BAGLANMAZ (KVKK: riza hizmet
kosulu yapilamaz):
  * ``marketing_consent_at`` - ticari ileti (tekrar hatirlatmalari)
  * ``health_consent_at``    - alerji kaydi (ozel nitelikli saglik verisi)

Hesap silme satiri SILMEZ, ANONIMLESTIRIR: ``appointment.customer_id``
CASCADE oldugu icin satir silinirse salonun doluluk ve ciro gecmisi de
giderdi. Kimlik bilgileri, saglik verisi, notlar, fotograflar ve
yorumlar silinir; randevu satirlari kimliksiz kalir.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import config
from ..errors import AppError
from ..models import (
    Allergy,
    Appointment,
    CampaignGrant,
    Customer,
    CustomerNote,
    CustomerPhoto,
    CustomerSession,
    DesignReference,
    LoyaltyEntry,
    PhoneRiskEvent,
    Review,
    ScheduledNotification,
    SlotViewEvent,
    VerificationCode,
)
from ..time_utils import now_local, to_date_key

logger = logging.getLogger("aurora.privacy")

#: Tekrar hatirlatmalarinin ``dedupe_key`` oneki (bkz. core/reminder_rules.py).
#: Bunlar ticari iletidir; randevu oncesi hatirlatma (``pre:``) degildir.
MARKETING_DEDUPE_PREFIX = "repeat:"

ANONYMIZED_NAME = "Silinmiş üye"

# Saklama sureleri. Metinlerdeki sureler (/kvkk) bunlarla AYNI olmalidir.
#: Slot goruntuleme sayaci yalnizca "su an kac kisi bakiyor" icindir.
SLOT_VIEW_RETENTION = timedelta(days=30)
#: Gonderilmis / iptal / basarisiz bildirimlerin govdesi ad icerir.
NOTIFICATION_RETENTION = timedelta(days=180)
#: Risk skoru son 6 ayi kullanir (core/risk_score.py); pay birakilarak 1 yil.
RISK_EVENT_RETENTION = timedelta(days=365)

_UPCOMING_STATUSES = ("PENDING", "CONFIRMED")


# ---------------------------------------------------------------------
# Rizalar
# ---------------------------------------------------------------------


def privacy_status(db: Session, customer_id: int) -> dict:
    customer = _get(db, customer_id)
    allergies = db.scalar(
        select(Allergy.id).where(Allergy.customer_id == customer_id).limit(1)
    )
    return {
        "marketingConsent": customer.marketing_consent_at is not None,
        "marketingConsentAt": _iso(customer.marketing_consent_at),
        "healthConsent": customer.health_consent_at is not None,
        "healthConsentAt": _iso(customer.health_consent_at),
        "hasHealthData": allergies is not None,
    }


def set_marketing_consent(db: Session, customer: Customer, granted: bool, now: datetime) -> None:
    """Onay verilirse zaman damgasi yazilir (zaten varsa korunur). Geri
    alinirsa kuyrukta bekleyen tekrar hatirlatmalari iptal edilir."""
    if granted:
        customer.marketing_consent_at = customer.marketing_consent_at or now
        return
    customer.marketing_consent_at = None
    db.execute(
        update(ScheduledNotification)
        .where(
            ScheduledNotification.customer_id == customer.id,
            ScheduledNotification.status == "PENDING",
            ScheduledNotification.dedupe_key.startswith(MARKETING_DEDUPE_PREFIX),
        )
        .values(status="CANCELLED")
    )


def withdraw_health_consent(db: Session, customer: Customer) -> int:
    """Riza geri alininca saglik verisi isleme dayanagi kalmaz: kayitlar silinir."""
    removed = db.execute(delete(Allergy).where(Allergy.customer_id == customer.id)).rowcount
    customer.health_consent_at = None
    return removed or 0


def is_marketing_allowed(customer: Customer) -> bool:
    return customer.marketing_consent_at is not None and customer.anonymized_at is None


# ---------------------------------------------------------------------
# Veri dokumu (KVKK m.11 - "verilerimi indir")
# ---------------------------------------------------------------------


def export_customer_data(db: Session, customer_id: int) -> dict:
    """Musterinin kendisine ait kayitlarin okunabilir dokumu.

    Personelin ``STAFF_ONLY`` notlari bu self-servis dokume girmez; yazili
    basvuruda (``/kvkk`` - basvuru yontemi) salon tarafindan ayrica verilir.
    """
    customer = _get(db, customer_id)

    appointments = db.scalars(
        select(Appointment)
        .where(Appointment.customer_id == customer_id)
        .order_by(Appointment.date.desc(), Appointment.start_min.desc())
    ).all()

    return {
        "exportedAt": now_local().isoformat(),
        "profile": {
            "firstName": customer.first_name,
            "lastName": customer.last_name,
            "phone": customer.phone,
            "email": customer.email,
            "birthDate": customer.birth_date,
            "memberSince": _iso(customer.created_at),
            "tier": customer.tier,
            "loyaltyPoints": customer.loyalty_points,
        },
        "consents": {
            "marketingConsentAt": _iso(customer.marketing_consent_at),
            "healthConsentAt": _iso(customer.health_consent_at),
        },
        "appointments": [
            {
                "date": a.date,
                "startMin": a.start_min,
                "endMin": a.end_min,
                "status": a.status,
                "staff": a.staff.name if a.staff else None,
                "services": [i.service.name for i in a.items],
                "totalPrice": a.total_price,
                "notes": a.notes,
            }
            for a in appointments
        ],
        "allergies": [
            {"label": x.label, "severity": x.severity, "note": x.note, "createdAt": _iso(x.created_at)}
            for x in db.scalars(select(Allergy).where(Allergy.customer_id == customer_id)).all()
        ],
        "sharedNotes": [
            {"body": n.body, "createdAt": _iso(n.created_at)}
            for n in db.scalars(
                select(CustomerNote).where(
                    CustomerNote.customer_id == customer_id, CustomerNote.visibility == "SHARED"
                )
            ).all()
        ],
        "photos": [
            {"imageUrl": p.image_url, "note": p.note, "createdAt": _iso(p.created_at)}
            for p in db.scalars(
                select(CustomerPhoto).where(CustomerPhoto.customer_id == customer_id)
            ).all()
        ],
        "reviews": [
            {"rating": r.rating, "comment": r.comment, "createdAt": _iso(r.created_at)}
            for r in db.scalars(select(Review).where(Review.customer_id == customer_id)).all()
        ],
        "loyalty": [
            {"delta": e.delta, "reason": e.reason, "createdAt": _iso(e.created_at)}
            for e in db.scalars(
                select(LoyaltyEntry).where(LoyaltyEntry.customer_id == customer_id)
            ).all()
        ],
    }


# ---------------------------------------------------------------------
# Hesap silme (anonimlestirme)
# ---------------------------------------------------------------------


def anonymize_customer(db: Session, customer_id: int, now: datetime | None = None) -> dict:
    """Musteri hesabini kimliksizlestirir.

    Tum veritabani degisiklikleri tek commit'tedir (yarim kalmis silme
    olmaz). Dosyalar commit'ten SONRA silinir: commit basarisiz olursa
    kayitlar geri doner ve dosyalari da yerinde kalir."""
    now = now or now_local()
    customer = _get(db, customer_id)

    upcoming = db.scalar(
        select(Appointment.id)
        .where(
            Appointment.customer_id == customer_id,
            Appointment.status.in_(_UPCOMING_STATUSES),
            Appointment.date >= to_date_key(now),
        )
        .limit(1)
    )
    if upcoming is not None:
        raise AppError(
            "VALIDATION",
            "Yaklaşan randevun var. Hesabını silmeden önce randevunu iptal etmelisin.",
            409,
        )

    files = [
        *db.scalars(
            select(CustomerPhoto.image_url).where(CustomerPhoto.customer_id == customer_id)
        ).all(),
        *db.scalars(
            select(DesignReference.url)
            .join(Appointment, Appointment.id == DesignReference.appointment_id)
            .where(Appointment.customer_id == customer_id, DesignReference.source == "UPLOAD")
        ).all(),
    ]

    appointment_ids = select(Appointment.id).where(Appointment.customer_id == customer_id)
    for statement in (
        delete(Allergy).where(Allergy.customer_id == customer_id),
        delete(CustomerNote).where(CustomerNote.customer_id == customer_id),
        delete(CustomerPhoto).where(CustomerPhoto.customer_id == customer_id),
        delete(DesignReference).where(DesignReference.appointment_id.in_(appointment_ids)),
        delete(Review).where(Review.customer_id == customer_id),
        delete(ScheduledNotification).where(ScheduledNotification.customer_id == customer_id),
        delete(CampaignGrant).where(CampaignGrant.customer_id == customer_id),
        delete(CustomerSession).where(CustomerSession.customer_id == customer_id),
        delete(VerificationCode).where(VerificationCode.phone == customer.phone),
    ):
        db.execute(statement)

    db.execute(
        update(Appointment)
        .where(Appointment.customer_id == customer_id)
        .values(notes=None)
    )

    # Telefon unique ve 10 karakter: gercek numarayla cakismayan yer tutucu.
    customer.phone = f"X{customer.id:09d}"[-10:]
    customer.first_name = ANONYMIZED_NAME
    customer.last_name = None
    customer.email = None
    customer.birth_date = None
    customer.is_member = False
    customer.engagement_opt_in = False
    customer.marketing_consent_at = None
    customer.health_consent_at = None
    customer.anonymized_at = now
    db.commit()

    removed_files = sum(_remove_upload(url) for url in files)
    return {"anonymized": True, "removedFiles": removed_files}


# ---------------------------------------------------------------------
# Saklama suresi temizligi (bakim isi)
# ---------------------------------------------------------------------


def sweep_retention(db: Session, now: datetime | None = None) -> dict:
    now = now or now_local()
    views = db.execute(
        delete(SlotViewEvent).where(SlotViewEvent.viewed_at < now - SLOT_VIEW_RETENTION)
    ).rowcount
    notifications = db.execute(
        delete(ScheduledNotification).where(
            ScheduledNotification.status.in_(("SENT", "FAILED", "CANCELLED")),
            ScheduledNotification.due_at < now - NOTIFICATION_RETENTION,
        )
    ).rowcount
    risk = db.execute(
        delete(PhoneRiskEvent).where(PhoneRiskEvent.occurred_at < now - RISK_EVENT_RETENTION)
    ).rowcount
    db.commit()
    return {
        "removedSlotViews": views or 0,
        "removedNotifications": notifications or 0,
        "removedRiskEvents": risk or 0,
    }


# ---------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------


def _get(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.anonymized_at is not None:
        raise AppError("NOT_FOUND", "Hesap bulunamadı.", 404)
    return customer


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _remove_upload(url: str | None) -> int:
    """``/uploads/...`` adresli dosyayi siler. Yukleme klasoru disina
    cikan bir yol (``..``) asla silinmez."""
    if not url or not url.startswith("/uploads/"):
        return 0
    root = Path(config.upload_dir).resolve()
    target = (root / url.removeprefix("/uploads/")).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return 0
    try:
        target.unlink()
        return 1
    except OSError:
        logger.warning("Yuklenen dosya silinemedi: %s", target)
        return 0
