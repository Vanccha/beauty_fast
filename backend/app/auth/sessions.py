"""
====================================================================
OTURUM YONETIMI
====================================================================

JWT yerine **opak token + veritabani kaydi** tercih edildi:

  * Oturum aninda iptal edilebilir (JWT'de imza gecerli oldugu surece
    token yasar; kara liste tutmak gerekirdi - yani yine tablo).
  * Token govdesinde hicbir bilgi tasinmaz; sizmasi halinde saldirgan
    kullanici kimligini/rolunu okuyamaz.
  * Ek bagimlilik yok (``uuid4`` standart kutuphanede).

Cerezler ``httponly`` + ``samesite=lax`` + ``path=/``. Lokal gelistirme
HTTP uzerinden yapildigi icin ``secure`` yalnizca uretimde acilir.

Personel ve musteri oturumlari AYRI cerezlerde tutulur; ayni tarayicida
hem panele hem musteri hesabina giris yapilabilir (usta kendi randevusunu
alabilir) ve yetki karismasi olmaz.

(``src/lib/auth/session.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import config
from ..models import Customer, CustomerSession, Staff, StaffSession, VerificationCode
from ..time_utils import now_local

STAFF_COOKIE = "staff_session"
CUSTOMER_COOKIE = "customer_session"
#: Kilit sahipligini belirleyen anonim tarayici anahtari.
VISITOR_COOKIE = "visitor_key"

STAFF_TTL_DAYS = 7
CUSTOMER_TTL_DAYS = 180
#: Kayan yenileme: oturumun kalan suresi bu gunun altina inince kullanimda
#: sureyi yeniden CUSTOMER_TTL_DAYS'e uzatir (her istekte yazma olmasin
#: diye en fazla ~30 gunde bir).
CUSTOMER_RENEW_BELOW_DAYS = 150
VISITOR_TTL_DAYS = 180


@dataclass(frozen=True)
class StaffPrincipal:
    id: int
    name: str
    role: str
    branch_id: int
    phone: str
    photo_url: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "branchId": self.branch_id,
            "phone": self.phone,
            "photoUrl": self.photo_url,
        }


@dataclass(frozen=True)
class CustomerPrincipal:
    id: int
    first_name: str
    last_name: str | None
    phone: str
    tier: str
    loyalty_points: float
    engagement_opt_in: bool

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "firstName": self.first_name,
            "lastName": self.last_name,
            "phone": self.phone,
            "tier": self.tier,
            "loyaltyPoints": self.loyalty_points,
            "engagementOptIn": self.engagement_opt_in,
        }


def _expiry(days: int) -> datetime:
    return now_local() + timedelta(days=days)


def _set_cookie(response: Response, name: str, value: str, expires_at: datetime, http_only=True):
    response.set_cookie(
        key=name,
        value=value,
        httponly=http_only,
        samesite="lax",
        path="/",
        secure=config.is_production,
        max_age=int((expires_at - now_local()).total_seconds()),
    )


# ---------------------------------------------------------------------
# Personel
# ---------------------------------------------------------------------


def create_staff_session(db: Session, response: Response, staff_id: int) -> str:
    token = uuid4().hex
    expires_at = _expiry(STAFF_TTL_DAYS)
    db.add(StaffSession(token=token, staff_id=staff_id, expires_at=expires_at))
    db.commit()
    _set_cookie(response, STAFF_COOKIE, token, expires_at)
    return token


def get_staff_principal(db: Session, request: Request) -> StaffPrincipal | None:
    token = request.cookies.get(STAFF_COOKIE)
    if not token:
        return None

    row = db.execute(
        select(StaffSession, Staff)
        .join(Staff, Staff.id == StaffSession.staff_id)
        .where(StaffSession.token == token)
    ).first()
    if not row:
        return None

    session, staff = row
    if session.expires_at <= now_local() or not staff.is_active:
        return None

    return StaffPrincipal(
        id=staff.id,
        name=staff.name,
        role=staff.role,
        branch_id=staff.branch_id,
        phone=staff.phone,
        photo_url=staff.photo_url,
    )


# ---------------------------------------------------------------------
# Musteri
# ---------------------------------------------------------------------


def create_customer_session(db: Session, response: Response, customer_id: int) -> str:
    token = uuid4().hex
    expires_at = _expiry(CUSTOMER_TTL_DAYS)
    db.add(CustomerSession(token=token, customer_id=customer_id, expires_at=expires_at))
    db.commit()
    _set_cookie(response, CUSTOMER_COOKIE, token, expires_at)
    return token


def get_customer_principal(db: Session, request: Request) -> CustomerPrincipal | None:
    token = request.cookies.get(CUSTOMER_COOKIE)
    if not token:
        return None

    row = db.execute(
        select(CustomerSession, Customer)
        .join(Customer, Customer.id == CustomerSession.customer_id)
        .where(CustomerSession.token == token)
    ).first()
    if not row:
        return None

    session, customer = row
    now = now_local()
    if session.expires_at <= now:
        return None

    # Kayan yenileme: cerezin yeni omru yanit olusturulurken
    # (``EnvelopeRoute``) ``request.state`` uzerinden yazilir.
    if session.expires_at - now < timedelta(days=CUSTOMER_RENEW_BELOW_DAYS):
        new_expiry = _expiry(CUSTOMER_TTL_DAYS)
        session.expires_at = new_expiry
        db.commit()
        request.state.customer_cookie_renew = (token, new_expiry)

    return CustomerPrincipal(
        id=customer.id,
        first_name=customer.first_name,
        last_name=customer.last_name,
        phone=customer.phone,
        tier=customer.tier,
        loyalty_points=customer.loyalty_points,
        engagement_opt_in=customer.engagement_opt_in,
    )


# ---------------------------------------------------------------------
# Cikis
# ---------------------------------------------------------------------


def destroy_staff_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(STAFF_COOKIE)
    if token:
        db.execute(delete(StaffSession).where(StaffSession.token == token))
        db.commit()
    response.delete_cookie(STAFF_COOKIE, path="/")


def destroy_customer_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(CUSTOMER_COOKIE)
    if token:
        db.execute(delete(CustomerSession).where(CustomerSession.token == token))
        db.commit()
    response.delete_cookie(CUSTOMER_COOKIE, path="/")


# ---------------------------------------------------------------------
# Ziyaretci anahtari
# ---------------------------------------------------------------------


def get_or_create_visitor_key(request: Request, response: Response) -> str:
    """Soft-lock sahipligi ve slot goruntuleme sayimi icin anonim anahtar.

    Kimlik dogrulamasi DEGILDIR - yalnizca "ayni tarayici mi" sorusunu
    yanitlar. Yoksa uretilip creze yazilir.
    """
    existing = request.cookies.get(VISITOR_COOKIE)
    if existing:
        return existing

    key = uuid4().hex
    _set_cookie(response, VISITOR_COOKIE, key, _expiry(VISITOR_TTL_DAYS), http_only=False)
    # Ayni istek icinde okunabilmesi icin request state'ine de koy.
    request.state.visitor_key = key
    return key


def read_visitor_key(request: Request) -> str | None:
    """Yazma yetkisi olmayan baglamlarda yalnizca okur."""
    return request.cookies.get(VISITOR_COOKIE) or getattr(request.state, "visitor_key", None)


def sweep_expired_sessions(db: Session, now: datetime | None = None) -> dict:
    """Suresi gecmis oturum kayitlarini temizler (cron/sweep tarafindan)."""
    now = now or now_local()
    staff = db.execute(delete(StaffSession).where(StaffSession.expires_at < now)).rowcount
    customer = db.execute(delete(CustomerSession).where(CustomerSession.expires_at < now)).rowcount
    codes = db.execute(delete(VerificationCode).where(VerificationCode.expires_at < now)).rowcount
    db.commit()
    return {
        "removedStaffSessions": staff or 0,
        "removedCustomerSessions": customer or 0,
        "removedCodes": codes or 0,
    }
