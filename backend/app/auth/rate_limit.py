"""
====================================================================
DENEME SINIRI (rate limiting)
====================================================================

Kayan pencereli basit bir sayac: her sayilan olay ``rate_limit_hit``
tablosuna bir satir yazar, sinir kontrolu penceredeki satirlari sayar.

Neden bellekte degil de veritabaninda?
  * Uretimde birden fazla worker/sunucu calisir; bellekteki sayac her
    surecte ayri olur ve sinir fiilen worker sayisiyla carpilirdi.
  * Ek altyapi (Redis) gerektirmez.

"Once say, sonra yaz" kontrolu eszamanli isteklerde siniri birkac istek
kadar asabilir; bu bilincli bir tercihtir - amac kesin kota degil, kaba
kuvvet denemesini pratikte imkansiz kilmaktir.

IP adresi ``request.client.host``tan okunur. Bir ters proxy (nginx,
Next.js rewrite) arkasinda uvicorn ``--proxy-headers
--forwarded-allow-ips=<proxy-ip>`` ile calistirilmalidir; aksi halde tum
istekler proxy'nin IP'sinden geliyor gorunur. Bu yuzden IP sinirlari
comert tutulur, asil koruma telefon numarasi bazli sinirlardir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import RateLimitHit
from ..time_utils import now_local


@dataclass(frozen=True)
class Limit:
    #: Anahtar oneki: "staff-login:phone"
    name: str
    #: Pencere icinde izin verilen olay sayisi
    max_hits: int
    window_minutes: int


#: Personel girisi - HATALI denemeler sayilir.
STAFF_LOGIN_PHONE = Limit("staff-login:phone", 5, 15)
STAFF_LOGIN_IP = Limit("staff-login:ip", 20, 15)
#: OTP gonderimi - her istek sayilir (SMS maliyeti / SMS bombardimani).
OTP_SEND_PHONE = Limit("otp-send:phone", 5, 15)
OTP_SEND_IP = Limit("otp-send:ip", 30, 15)
#: OTP dogrulama - HATALI denemeler sayilir (kod basina sinir ayrica var).
OTP_VERIFY_PHONE = Limit("otp-verify:phone", 10, 15)
OTP_VERIFY_IP = Limit("otp-verify:ip", 30, 15)

#: Sweep bu yastan eski kayitlari siler (en uzun pencereden buyuk olmali).
RETENTION = timedelta(days=1)


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _key(limit: Limit, subject: str) -> str:
    return f"{limit.name}:{subject}"[:120]


def is_limited(db: Session, limit: Limit, subject: str | None, now: datetime | None = None) -> bool:
    if not subject:
        return False
    now = now or now_local()
    count = db.scalar(
        select(func.count())
        .select_from(RateLimitHit)
        .where(
            RateLimitHit.key == _key(limit, subject),
            RateLimitHit.created_at >= now - timedelta(minutes=limit.window_minutes),
        )
    )
    return (count or 0) >= limit.max_hits


def ensure_not_limited(
    db: Session,
    checks: list[tuple[Limit, str | None]],
    message: str,
    now: datetime | None = None,
) -> None:
    """Sinirlardan biri dolmussa 429 firlatir."""
    for limit, subject in checks:
        if is_limited(db, limit, subject, now):
            raise AppError("RATE_LIMITED", message, 429)


def record_hit(
    db: Session, checks: list[tuple[Limit, str | None]], now: datetime | None = None
) -> None:
    """Olaylari kaydeder. Commit cagiranin sorumlulugundadir."""
    now = now or now_local()
    for limit, subject in checks:
        if subject:
            db.add(RateLimitHit(key=_key(limit, subject), created_at=now))


def clear_hits(db: Session, limit: Limit, subject: str | None) -> None:
    """Basarili islemden sonra sayaci sifirlar (orn. dogru sifre)."""
    if subject:
        db.execute(delete(RateLimitHit).where(RateLimitHit.key == _key(limit, subject)))


def sweep_rate_limits(db: Session, now: datetime | None = None) -> int:
    now = now or now_local()
    removed = db.execute(delete(RateLimitHit).where(RateLimitHit.created_at < now - RETENTION))
    return removed.rowcount or 0
