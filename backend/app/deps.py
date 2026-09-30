"""
====================================================================
YETKI KAPILARI (FastAPI bagimliliklari)
====================================================================

API uclari bu bagimliliklarin ARKASINDA durur. Hepsi hata firlatir
(``None`` donmez) - boylece "kontrol etmeyi unutma" hatasi sessizce veri
sizdirmaya degil, 401/403 yanitina donusur.

GIZLI USTA NOTLARI (``customer_note.visibility == "STAFF_ONLY"``) ve risk
skoru gibi hassas alanlar YALNIZCA ``require_staff`` arkasindadir.

(``src/lib/auth/guards.ts`` karsiligi.)
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .auth.sessions import (
    CustomerPrincipal,
    StaffPrincipal,
    get_customer_principal,
    get_staff_principal,
)
from .config import config
from .db import get_session
from .errors import AppError

DbSession = Annotated[Session, Depends(get_session)]

#: Rol hiyerarsisi: OWNER > MANAGER > STAFF
ROLE_RANK = {"STAFF": 1, "MANAGER": 2, "OWNER": 3}


def optional_staff(request: Request, db: DbSession) -> StaffPrincipal | None:
    return get_staff_principal(db, request)


def optional_customer(request: Request, db: DbSession) -> CustomerPrincipal | None:
    return get_customer_principal(db, request)


def require_staff(request: Request, db: DbSession) -> StaffPrincipal:
    staff = get_staff_principal(db, request)
    if staff is None:
        raise AppError("UNAUTHORIZED", "Bu işlem için personel girişi gerekiyor.", 401)
    return staff


def require_role(minimum: str):
    """En az verilen rolu ister. ``require_role("MANAGER")`` cagrisini OWNER de gecer."""

    def dependency(request: Request, db: DbSession) -> StaffPrincipal:
        staff = require_staff(request, db)
        if ROLE_RANK.get(staff.role, 0) < ROLE_RANK.get(minimum, 0):
            raise AppError("FORBIDDEN", "Bu işlem için yetkiniz yok.", 403)
        return staff

    return dependency


def require_cron_or_manager(request: Request, db: DbSession) -> str:
    """Bakim isi (``/api/cron/sweep``) kapisi.

    Iki yoldan biri gerekir:
      * ``X-Cron-Secret`` basligi ``CRON_SECRET`` ile eslesir (zamanlayici),
      * en az MANAGER rolunde personel oturumu (paneldeki elle tetikleme).

    ``CRON_SECRET`` bos ise yalnizca personel yolu aciktir.
    """
    provided = request.headers.get("x-cron-secret") or ""
    if config.cron_secret and hmac.compare_digest(
        provided.encode("utf-8"), config.cron_secret.encode("utf-8")
    ):
        return "cron"
    require_role("MANAGER")(request, db)
    return "staff"


def require_customer(request: Request, db: DbSession) -> CustomerPrincipal:
    """Musteri oturumu ister.

    Misafirler katalogu, portfolyoyu ve musaitlik ekranini gorebilir;
    randevu almak UYELIK gerektirir (``MEMBERSHIP_REQUIRED`` kodu
    istemcide giris modalini acar).
    """
    customer = get_customer_principal(db, request)
    if customer is None:
        raise AppError(
            "MEMBERSHIP_REQUIRED", "Randevu oluşturmak için üye girişi yapmalısınız.", 401
        )
    return customer


class Principal:
    """Personel VEYA musteri oturumu.

    Randevu detayi gibi iki tarafin da erisebildigi kaynaklarda kullanilir;
    cagiran taraf ``kind`` alanina bakarak hangi alanlari donecegine
    karar verir.
    """

    def __init__(
        self, staff: StaffPrincipal | None = None, customer: CustomerPrincipal | None = None
    ) -> None:
        self.staff = staff
        self.customer = customer

    @property
    def kind(self) -> str:
        return "staff" if self.staff else "customer"


def require_any_principal(request: Request, db: DbSession) -> Principal:
    staff = get_staff_principal(db, request)
    if staff:
        return Principal(staff=staff)
    customer = get_customer_principal(db, request)
    if customer:
        return Principal(customer=customer)
    raise AppError("UNAUTHORIZED", "Oturum bulunamadı.", 401)


StaffDep = Annotated[StaffPrincipal, Depends(require_staff)]
ManagerDep = Annotated[StaffPrincipal, Depends(require_role("MANAGER"))]
OwnerDep = Annotated[StaffPrincipal, Depends(require_role("OWNER"))]
CustomerDep = Annotated[CustomerPrincipal, Depends(require_customer)]
AnyPrincipalDep = Annotated[Principal, Depends(require_any_principal)]
OptionalStaffDep = Annotated[StaffPrincipal | None, Depends(optional_staff)]
OptionalCustomerDep = Annotated[CustomerPrincipal | None, Depends(optional_customer)]
