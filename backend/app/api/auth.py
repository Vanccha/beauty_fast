"""Kimlik dogrulama uclari.

  POST /api/auth/otp/send    - musteri telefonuna dogrulama kodu
  POST /api/auth/otp/verify  - kodu dogrula, oturum ac (gerekirse hesap ac)
  POST /api/auth/staff/login - personel girisi (telefon + sifre)
  POST /api/auth/logout      - oturum(lari) kapat
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth.otp import issue_otp, verify_otp
from ..auth.password import verify_password
from ..auth.rate_limit import (
    STAFF_LOGIN_IP,
    STAFF_LOGIN_PHONE,
    clear_hits,
    client_ip,
    ensure_not_limited,
    record_hit,
)
from ..auth.sessions import (
    create_customer_session,
    create_staff_session,
    destroy_customer_session,
    destroy_staff_session,
    get_customer_principal,
)
from ..core.risk_score import normalize_phone
from ..deps import DbSession
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import Customer, Staff
from ..services.privacy import set_marketing_consent
from ..time_utils import now_local

router = APIRouter(prefix="/api/auth", tags=["auth"], route_class=EnvelopeRoute)


class OtpSendBody(BaseModel):
    phone: str = Field(min_length=10)


@router.post("/otp/send")
def otp_send(body: OtpSendBody, request: Request, db: DbSession) -> dict:
    """Numaranin kayitli olup olmadigi yanittan ANLASILMAZ (hesap sayimi
    saldirisina kapali). Gelistirmede kod hem konsola yazilir hem de
    ``devCode`` alaninda doner."""
    issued = issue_otp(db, body.phone, ip=client_ip(request))
    return {
        "phone": issued.phone,
        "expiresAt": issued.expires_at.isoformat(),
        "devCode": issued.dev_code,
    }


class OtpVerifyBody(BaseModel):
    phone: str = Field(min_length=10)
    code: str = Field(min_length=4, max_length=8)
    firstName: str | None = Field(default=None, max_length=60)
    lastName: str | None = Field(default=None, max_length=60)
    #: Giris formundaki ISTEGE BAGLI ticari ileti onay kutusu. Yalnizca
    #: ``True`` islenir: girişte isaretlenmemesi mevcut onayi geri almaz
    #: (geri alma Hesabim > Gizlilik'ten yapilir).
    marketingConsent: bool = False


@router.post("/otp/verify")
def otp_verify(body: OtpVerifyBody, request: Request, response: Response, db: DbSession) -> dict:
    verified = verify_otp(
        db, body.phone, body.code, body.firstName, body.lastName, ip=client_ip(request)
    )
    if body.marketingConsent:
        customer_row = db.get(Customer, verified.customer_id)
        set_marketing_consent(db, customer_row, True, now_local())
        db.commit()

    create_customer_session(db, response, verified.customer_id)
    principal = get_customer_principal(db, request)

    # Cerez bu yanitla yazildigi icin principal'i dogrudan okuyamayabiliriz;
    # bu durumda tazeledigimiz kimligi elle kurariz.
    if principal is None:
        customer = db.get(Customer, verified.customer_id)
        payload = {
            "id": customer.id,
            "firstName": customer.first_name,
            "lastName": customer.last_name,
            "phone": customer.phone,
            "tier": customer.tier,
            "loyaltyPoints": customer.loyalty_points,
            "engagementOptIn": customer.engagement_opt_in,
        }
    else:
        payload = principal.to_dict()

    return {"isNewCustomer": verified.is_new_customer, "customer": payload}


class StaffLoginBody(BaseModel):
    phone: str = Field(min_length=10)
    password: str = Field(min_length=4)
    #: True: 30 gunluk kalici cerez; False: 12 saatlik, tarayici kapaninca silinen oturum.
    rememberMe: bool = False


@router.post("/staff/login")
def staff_login(
    body: StaffLoginBody, request: Request, response: Response, db: DbSession
) -> dict:
    """Kullanici bulunamadiginda da sifre dogrulamasi CALISTIRILIR: aksi
    halde yanit suresi "bu numara kayitli mi" sorusunu ele verirdi. Hata
    mesaji her iki durumda da aynidir.

    Hatali denemeler numara ve IP basina sinirlanir. Sinir doluysa sifre
    hic hesaplanmaz - scrypt bilerek pahali oldugu icin sinirsiz deneme
    sunucuyu kilitlemenin de bir yolu olurdu."""
    phone = normalize_phone(body.phone)
    checks = [(STAFF_LOGIN_PHONE, phone), (STAFF_LOGIN_IP, client_ip(request))]
    ensure_not_limited(
        db, checks, "Çok fazla hatalı giriş denemesi. Lütfen 15 dakika sonra tekrar deneyin."
    )

    staff = db.scalar(select(Staff).where(Staff.phone == phone))

    # Zamanlama farkini kapatmak icin sahte bir hash ile de olsa dogrula.
    stored = staff.password_hash if staff else "scrypt$" + "0" * 32 + "$" + "0" * 128
    valid = verify_password(body.password, stored)

    if staff is None or not staff.is_active or not valid:
        record_hit(db, checks)
        db.commit()
        raise AppError("UNAUTHORIZED", "Telefon veya şifre hatalı.", 401)

    clear_hits(db, STAFF_LOGIN_PHONE, phone)

    create_staff_session(db, response, staff.id, remember_me=body.rememberMe)

    return {
        "staff": {
            "id": staff.id,
            "name": staff.name,
            "role": staff.role,
            "branchId": staff.branch_id,
            "photoUrl": staff.photo_url,
        }
    }


class LogoutBody(BaseModel):
    #: "staff" | "customer" | "all" - belirtilmezse ikisi de kapatilir
    scope: str | None = None


@router.post("/logout")
def logout(request: Request, response: Response, db: DbSession, body: LogoutBody | None = None):
    """Personel ve musteri oturumlari ayri cerezlerde tutuldugu icin
    hangisinin kapatilacagi secilebilir."""
    scope = (body.scope if body else None) or "all"
    if scope in ("staff", "all"):
        destroy_staff_session(db, request, response)
    if scope in ("customer", "all"):
        destroy_customer_session(db, request, response)
    return {"loggedOut": scope}
