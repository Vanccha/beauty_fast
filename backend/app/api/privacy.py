"""KVKK uclari - musterinin kendi verisi uzerindeki haklari (KVKK m.11).

  GET    /api/me/privacy  - riza durumu
  PATCH  /api/me/privacy  - ticari ileti onayi ver/geri al, saglik rizasini geri al
  GET    /api/me/export   - verilerimin dokumu (JSON)
  DELETE /api/me          - hesabimi sil (anonimlestirme)

Is kurallari: ``services/privacy.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from ..auth.sessions import destroy_customer_session
from ..deps import CustomerDep, DbSession
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import Customer
from ..services import privacy
from ..time_utils import now_local

router = APIRouter(prefix="/api/me", tags=["privacy"], route_class=EnvelopeRoute)


@router.get("/privacy")
def get_privacy(customer: CustomerDep, db: DbSession) -> dict:
    return privacy.privacy_status(db, customer.id)


class PrivacyBody(BaseModel):
    marketingConsent: bool | None = None
    #: Yalnizca ``False`` (geri alma) kabul edilir: saglik verisi rizasi
    #: salonda, kayit girilirken alinir (bkz. admin alerji ucu).
    healthConsent: bool | None = None


@router.patch("/privacy")
def update_privacy(body: PrivacyBody, customer: CustomerDep, db: DbSession) -> dict:
    if body.healthConsent is True:
        raise AppError(
            "VALIDATION", "Sağlık bilgisi rızası salonda, kayıt sırasında verilir.", 400
        )

    row = db.get(Customer, customer.id)
    if body.marketingConsent is not None:
        privacy.set_marketing_consent(db, row, body.marketingConsent, now_local())
    if body.healthConsent is False:
        privacy.withdraw_health_consent(db, row)
    db.commit()
    return privacy.privacy_status(db, customer.id)


@router.get("/export")
def export_data(customer: CustomerDep, db: DbSession) -> dict:
    return privacy.export_customer_data(db, customer.id)


@router.delete("")
def delete_account(customer: CustomerDep, request: Request, response: Response, db: DbSession):
    result = privacy.anonymize_customer(db, customer.id)
    # Oturum kayitlari anonimlestirmede silindi; cerez de temizlenir.
    destroy_customer_session(db, request, response)
    return result
