"""Golge risk skorunun veritabani sarmalayicilari.

Saf hesap ``app/core/risk_score.py`` icindedir; burada yalnizca havuz
okuma/yazma yapilir.

KVKK: sorgu ``salon_id`` filtrelemez ve donmez - tum havuz
toplulastirilarak okunur; yalnizca skorlama icin gereken iki alan alinir.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.risk_score import (
    DEFAULT_WINDOW_MONTHS,
    RiskAssessment,
    RiskEventInput,
    _subtract_months,
    compute_risk_score,
    hash_phone,
)
from ..models import PhoneRiskEvent
from ..time_utils import now_local


def assess_phone_risk(
    db: Session,
    phone: str,
    now: datetime | None = None,
    window_months: int = DEFAULT_WINDOW_MONTHS,
) -> RiskAssessment:
    now = now or now_local()
    window_start = _subtract_months(now, window_months)

    rows = db.execute(
        select(PhoneRiskEvent.outcome, PhoneRiskEvent.occurred_at).where(
            PhoneRiskEvent.phone_hash == hash_phone(phone),
            PhoneRiskEvent.occurred_at >= window_start,
            PhoneRiskEvent.occurred_at <= now,
        )
    ).all()

    return compute_risk_score(
        [RiskEventInput(outcome=r.outcome, occurred_at=r.occurred_at) for r in rows],
        now=now,
        window_months=window_months,
    )


def record_risk_event(
    db: Session,
    phone: str,
    outcome: str,
    occurred_at: datetime | None = None,
    salon_id: int | None = None,
) -> PhoneRiskEvent:
    """Randevu sonucunu havuza yazar (tamamlandi / gelmedi / gec iptal)."""
    event = PhoneRiskEvent(
        phone_hash=hash_phone(phone),
        outcome=outcome,
        occurred_at=occurred_at or now_local(),
        salon_id=salon_id,
    )
    db.add(event)
    return event
