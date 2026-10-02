"""
====================================================================
BASKASI ADINA RANDEVU - ortak yardimcilar
====================================================================

Randevuyu alan (booker) ile randevunun sahibi (alici / beneficiary)
farkli olabilir. Alici telefon numarasiyla bulunur ya da olusturulur;
randevu ``customer_id = alici``, ``booked_by_customer_id = alan`` olarak
yazilir. Grup randevusu da bu modulu kullanir.

Kurallar:
  * Alicinin kayitli gercek adi ASLA ezilmez; yalnizca "Yeni Üye" yer
    tutucusu gercek adla degistirilir.
  * Alici numarasi alanin kendi numarasiyla ayniysa "kendisi" sayilir.
  * Aliciya TEK bir bilgilendirme mesaji gider (ticari icerik yok);
    gonderim commit'ten sonradir ve basarisizligi randevuyu bozmaz.

Gunluk sinirlar (24 saatlik kayan pencere, ``rate_limit_hit`` satirlari):
  * alan basina    : 10 baskasi adina randevu
  * hedef numaraya : 3 randevu
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.rate_limit import Limit, ensure_not_limited, record_hit
from ..config import config
from ..core.risk_score import is_valid_mobile, normalize_phone
from ..errors import AppError
from ..models import Customer
from ..time_utils import format_date_tr, minutes_to_label, now_local
from . import messaging
from .whatsapp_inbound import mark_phone_known

logger = logging.getLogger("aurora.booking_other")

PLACEHOLDER_NAME = "Yeni Üye"

OTHER_BOOK_BOOKER = Limit("other-book:booker", 10, 24 * 60)
OTHER_BOOK_TARGET = Limit("other-book:target", 3, 24 * 60)

_NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '’\-][^\W\d_]+)*$", re.UNICODE)


def clean_person_name(value: str | None, *, required: bool) -> str | None:
    """Ad/soyad dogrulama: 1-40 karakter, harf/bosluk/kesme/tire."""
    name = " ".join((value or "").split())
    if not name:
        if required:
            raise ValueError("Ad boş olamaz.")
        return None
    if len(name) > 40:
        raise ValueError("Ad en fazla 40 karakter olabilir.")
    if not _NAME_RE.match(name):
        raise ValueError("Ad yalnızca harf, boşluk, kesme işareti ve tire içerebilir.")
    return name


class BeneficiaryBody(BaseModel):
    """Randevunun asil sahibi (baskasi adina randevuda)."""

    firstName: str = Field(min_length=1, max_length=60)
    lastName: str | None = Field(default=None, max_length=60)
    phone: str = Field(min_length=10, max_length=20)

    @field_validator("firstName")
    @classmethod
    def _first(cls, v: str) -> str:
        return clean_person_name(v, required=True)  # type: ignore[return-value]

    @field_validator("lastName")
    @classmethod
    def _last(cls, v: str | None) -> str | None:
        return clean_person_name(v, required=False)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        phone = normalize_phone(v)
        if not is_valid_mobile(phone):
            raise ValueError("Geçerli bir cep telefonu numarası girin (Türkiye: 5XX XXX XX XX; yurtdışı: ülke koduyla, örn. +44 7911 123456).")
        return phone


def is_self(booker_phone: str, beneficiary: BeneficiaryBody | None) -> bool:
    return beneficiary is None or beneficiary.phone == normalize_phone(booker_phone)


def find_beneficiary_id(db: Session, booker_phone: str, beneficiary: BeneficiaryBody | None) -> int | None:
    """Kilit asamasi: alici kayitliysa id'si, degilse None (olusturulmaz)."""
    if is_self(booker_phone, beneficiary):
        return None
    return db.scalar(select(Customer.id).where(Customer.phone == beneficiary.phone))


def find_or_create_beneficiary(db: Session, beneficiary: BeneficiaryBody) -> Customer:
    """Aliciyi telefona gore bulur ya da olusturur. Commit ETMEZ (flush)."""
    customer = db.scalar(select(Customer).where(Customer.phone == beneficiary.phone))
    if customer is None:
        try:
            with db.begin_nested():
                customer = Customer(
                    phone=beneficiary.phone,
                    first_name=beneficiary.firstName,
                    last_name=beneficiary.lastName,
                    # Telefonunu henuz kendisi dogrulamadi.
                    is_member=False,
                )
                db.add(customer)
                db.flush()
        except IntegrityError:
            customer = db.scalar(select(Customer).where(Customer.phone == beneficiary.phone))
            if customer is None:
                raise
        return customer

    if customer.first_name == PLACEHOLDER_NAME:
        customer.first_name = beneficiary.firstName
        customer.last_name = beneficiary.lastName
        db.flush()
    return customer


def ensure_other_booking_allowed(
    db: Session, booker_id: int, target_phone: str, now: datetime | None = None
) -> None:
    ensure_not_limited(
        db,
        [(OTHER_BOOK_BOOKER, str(booker_id)), (OTHER_BOOK_TARGET, target_phone)],
        "Başkası adına çok fazla randevu aldınız. Lütfen yarın tekrar deneyin.",
        now,
    )


def record_other_booking(
    db: Session, booker_id: int, target_phone: str, now: datetime | None = None
) -> None:
    """Sayaci artirir. Commit cagiranindir."""
    record_hit(db, [(OTHER_BOOK_BOOKER, str(booker_id)), (OTHER_BOOK_TARGET, target_phone)], now)


@dataclass(frozen=True)
class InfoMessage:
    phone: str
    text: str


def build_beneficiary_message(
    booker_name: str,
    date: str,
    start_min: int,
    service_names: list[str],
    beneficiary_name: str | None = None,
) -> str:
    """Aliciya giden bilgilendirme metni (islemsel, ticari icerik yok)."""
    greeting = f"Merhaba {beneficiary_name}, " if beneficiary_name else ""
    services = ", ".join(service_names)
    return (
        f"{greeting}{booker_name} senin için {format_date_tr(date)} saat "
        f"{minutes_to_label(start_min)} için {services} randevusu oluşturdu. "
        f"Randevunu görmek veya iptal etmek için: {config.public_site_url}/randevularim"
    )


def send_beneficiary_info(db: Session, phone: str, text: str) -> bool:
    """Bilgilendirme mesajini gonderir; ASLA istisna firlatmaz (randevu
    zaten commit edilmistir). Basari durumunu doner."""
    try:
        sender = messaging.get_sender()
        ready, state = sender.is_ready()
        if not ready:
            logger.warning("Alici bilgilendirmesi atlandi: kanal hazir degil (%s)", state)
            return False
        mark_phone_known(db, phone)
        db.commit()
        sender.send(phone, text)
        return True
    except Exception as error:  # noqa: BLE001 - mesaj hatasi randevuyu bozmamali
        logger.warning("Alici bilgilendirmesi gonderilemedi (%s): %s", phone, error)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def label_for_viewer(appointment, viewer_customer_id: int | None) -> str:
    """Goruntuleyene gosterilecek "kimin icin" adi.

    Sahibi kendi KAYITLI adini gorur. Randevuyu ALAN (ama sahibi olmayan)
    kisi yalnizca KENDI yazdigi etiketi gorur; alicinin kayitli adi hicbir
    sekilde sizmaz (telefon numarasiyla isim tarama onlenir).
    """
    if viewer_customer_id is not None and appointment.customer_id == viewer_customer_id:
        return appointment.customer.first_name
    return appointment.beneficiary_label or "Misafir"
