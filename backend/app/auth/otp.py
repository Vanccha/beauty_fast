"""
====================================================================
TELEFON DOGRULAMA (OTP)
====================================================================

Musteri girisi sifresizdir: telefon -> 6 haneli kod -> oturum. Sifre
olmadigi icin "unuttum" akisi, sizinti riski ve hash saklama yuku de
yoktur.

Kod ``NOTIFICATION_DRIVER`` ile secilen kanaldan gonderilir
(``services/messaging.py``): ``console`` iken log'a yazilir, ``evolution``
iken WhatsApp mesaji olarak gider. Kanal hazir degilse 503,
gonderim basarisizsa 502 ``DELIVERY_FAILED`` doner. Kod ayrica **yalnizca gelistirme/test
modunda** API yanitinda ``devCode`` alaniyla doner; uretimde bu alan hicbir
kosulda doldurulmaz.

Kaba kuvvete karsi uc katman (bkz. ``rate_limit.py``):
  * Kod basina en fazla ``MAX_ATTEMPTS`` deneme (``verification_code.attempts``).
    Deneme hakki karsilastirmadan ONCE atomik bir UPDATE ile ayrilir; bu
    yuzden paralel istekler de siniri asamaz.
  * Numara ve IP basina hatali dogrulama siniri.
  * Numara ve IP basina kod isteme siniri (SMS bombardimani / maliyet).

(``src/lib/auth/otp.ts`` karsiligi.)
"""

from __future__ import annotations

import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..config import config
from ..core.risk_score import is_valid_mobile, normalize_phone
from ..errors import AppError
from ..models import Customer, Salon, VerificationCode
from ..services import messaging
from ..services.whatsapp_inbound import mark_phone_known
from . import rate_limit
from .rate_limit import (
    OTP_SEND_IP,
    OTP_SEND_PHONE,
    OTP_VERIFY_IP,
    OTP_VERIFY_PHONE,
    ensure_not_limited,
    record_hit,
)
from ..time_utils import now_local

logger = logging.getLogger("aurora.otp")

#: Kod omru (dakika).
CODE_TTL_MINUTES = 5
#: Bir kod en fazla bu kadar kez denenebilir (dogru deneme dahil).
MAX_ATTEMPTS = 5


def _generate_code() -> str:
    # Gelistirmede sabit kod kullanilabilir (DEV_OTP_CODE), aksi halde
    # kriptografik olarak guclu rastgele 6 hane uretilir.
    if not config.is_production and config.dev_otp_code:
        return config.dev_otp_code
    return f"{secrets.randbelow(1_000_000):06d}"


_DELIVERY_FAILED_MESSAGE = (
    "Doğrulama kodu WhatsApp üzerinden gönderilemedi. Numaranızın WhatsApp'ta "
    "kayıtlı olduğundan emin olup birkaç dakika sonra tekrar deneyin."
)


def _otp_message(salon_name: str, code: str) -> str:
    return (
        f"{salon_name} doğrulama kodunuz: *{code}*\n"
        f"Kod {CODE_TTL_MINUTES} dakika geçerlidir. Bu kodu kimseyle paylaşmayın."
    )


def _codes_match(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@dataclass(frozen=True)
class IssuedOtp:
    phone: str
    expires_at: datetime
    #: YALNIZCA gelistirmede dolar. Uretimde daima None.
    dev_code: str | None


def issue_otp(
    db: Session, raw_phone: str, now: datetime | None = None, ip: str | None = None
) -> IssuedOtp:
    """Numaraya dogrulama kodu uretir.

    Numaranin kayitli olup olmadigi **sizdirilmaz** - kayitli olmayan
    numaraya da kod uretilir, hesap dogrulama aninda acilir.
    """
    now = now or now_local()
    phone = normalize_phone(raw_phone)
    if not is_valid_mobile(phone):
        raise AppError("VALIDATION", "Geçerli bir cep telefonu numarası girin (Türkiye: 5XX XXX XX XX; yurtdışı: ülke koduyla, örn. +44 7911 123456).", 400)

    # Kanal hazir degilse (WhatsApp numarasi bagli degil) hemen reddedilir.
    # Evolution API bagli olmayan instance'a gonderilen mesajda hata donmek
    # yerine uzun sure asili kalir; ayrica boyle bir istek musterinin kod
    # isteme hakkindan dusmemelidir.
    sender = messaging.get_sender()
    ready, state = sender.is_ready()
    if not ready:
        logger.error("OTP kanali hazir degil (%s): %s", sender.name, state)
        raise AppError("DELIVERY_FAILED", _DELIVERY_FAILED_MESSAGE, 503)

    # Not: sayim ``verification_code`` uzerinden YAPILAMAZ - asagida onceki
    # kullanilmamis kodlar silindigi icin sayac hic dolmazdi.
    checks = [(OTP_SEND_PHONE, phone), (OTP_SEND_IP, ip)]
    ensure_not_limited(
        db, checks, "Çok fazla kod istediniz. Lütfen birkaç dakika sonra tekrar deneyin.", now
    )
    record_hit(db, checks, now)

    # Onceki kullanilmamis kodlari gecersiz kil - ayni anda tek gecerli kod.
    db.execute(
        delete(VerificationCode).where(
            VerificationCode.phone == phone, VerificationCode.consumed_at.is_(None)
        )
    )

    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    code = _generate_code()
    expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)

    db.add(
        VerificationCode(
            phone=phone,
            code=code,
            customer_id=customer.id if customer else None,
            expires_at=expires_at,
            created_at=now,
        )
    )
    salon_name = db.scalar(select(Salon.name).order_by(Salon.id).limit(1)) or "Aurora"
    # Kod gitmeden ONCE: musteri koda cevap yazarsa karsilama mesaji almasin.
    mark_phone_known(db, phone)
    db.commit()

    # Gonderim commit'ten SONRA yapilir: ag cagrisi surerken veritabani
    # transaction'i (ve tuttugu satir kilitleri) acik kalmaz.
    try:
        sender.send(phone, _otp_message(salon_name, code))
    except messaging.DeliveryError as error:
        logger.warning("OTP gonderilemedi (%s): %s", phone, error)
        raise AppError("DELIVERY_FAILED", _DELIVERY_FAILED_MESSAGE, 502) from error

    return IssuedOtp(
        phone=phone,
        expires_at=expires_at,
        dev_code=None if config.is_production else code,
    )


@dataclass(frozen=True)
class VerifiedOtp:
    customer_id: int
    #: Bu dogrulamada yeni hesap acildi mi?
    is_new_customer: bool


def verify_otp(
    db: Session,
    raw_phone: str,
    code: str,
    first_name: str | None = None,
    last_name: str | None = None,
    now: datetime | None = None,
    ip: str | None = None,
) -> VerifiedOtp:
    """Kodu dogrular ve musteri kaydini doner.

    Numara kayitli degilse hesap bu adimda acilir.
    """
    now = now or now_local()
    phone = normalize_phone(raw_phone)
    failure_checks = [(OTP_VERIFY_PHONE, phone), (OTP_VERIFY_IP, ip)]
    ensure_not_limited(
        db,
        failure_checks,
        "Çok fazla hatalı deneme yaptınız. Lütfen birkaç dakika sonra tekrar deneyin.",
        now,
    )

    record = db.scalar(
        select(VerificationCode)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.consumed_at.is_(None),
            VerificationCode.expires_at > now,
        )
        .order_by(VerificationCode.created_at.desc())
    )

    if record is None:
        raise AppError("UNAUTHORIZED", "Kodun süresi doldu. Lütfen yeni kod isteyin.", 401)

    # Deneme hakki karsilastirmadan ONCE ayrilir. Kosullu UPDATE atomiktir:
    # ayni koda paralel gelen istekler de toplamda MAX_ATTEMPTS'i gecemez.
    reserved = db.execute(
        update(VerificationCode)
        .where(
            VerificationCode.id == record.id,
            VerificationCode.consumed_at.is_(None),
            VerificationCode.attempts < MAX_ATTEMPTS,
        )
        .values(attempts=VerificationCode.attempts + 1)
    ).rowcount
    if reserved != 1:
        db.rollback()
        raise AppError(
            "UNAUTHORIZED", "Çok fazla hatalı deneme. Lütfen yeni kod isteyin.", 401
        )

    if not _codes_match(record.code, str(code or "").strip()):
        record_hit(db, failure_checks, now)
        db.commit()
        raise AppError("UNAUTHORIZED", "Doğrulama kodu hatalı.", 401)

    # Kodu tek kullanimlik olarak "sahiplen": ayni kodla gelen ikinci istek
    # (cift tiklama, yaris) burada elenir.
    claimed = db.execute(
        update(VerificationCode)
        .where(VerificationCode.id == record.id, VerificationCode.consumed_at.is_(None))
        .values(consumed_at=now)
    ).rowcount
    if claimed != 1:
        db.rollback()
        raise AppError("UNAUTHORIZED", "Kodun süresi doldu. Lütfen yeni kod isteyin.", 401)

    existing = db.scalar(select(Customer).where(Customer.phone == phone))

    if existing is None:
        customer = Customer(
            phone=phone,
            first_name=(first_name or "").strip() or "Yeni Üye",
            last_name=(last_name or "").strip() or None,
            is_member=True,
        )
        db.add(customer)
        db.flush()
    else:
        customer = existing
        # Baskasi adina acilmis (dogrulanmamis) kayit: sahibi simdi dogruladi.
        if not existing.is_member and existing.anonymized_at is None:
            existing.is_member = True
        # Kayitli musterinin adi ilk giriste tamamlanmamissa guncelle.
        if (first_name or "").strip() and existing.first_name == "Yeni Üye":
            existing.first_name = first_name.strip()
            existing.last_name = (last_name or "").strip() or None

    record.customer_id = customer.id
    rate_limit.clear_hits(db, OTP_VERIFY_PHONE, phone)
    db.commit()

    return VerifiedOtp(customer_id=customer.id, is_new_customer=existing is None)
