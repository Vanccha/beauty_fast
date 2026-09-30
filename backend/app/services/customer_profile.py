"""
====================================================================
MUSTERI PROFILI - CRM kartinin tek okuma noktasi
====================================================================

Segment, risk, sadakat, renk egilimi ve kampanya eslesmesi tek yerde
toplanir. Boylece admin karti, kampanya motoru ve musteri karsilama
ekrani AYNI hesaplamayi kullanir - uc farkli yerde ayrisan "toplam
harcama" tanimi olusmaz.

KVKK siniri: ``risk`` alani yalnizca toplulastirilmis skoru icerir ve bu
profil **musteri API'lerine verilmez**, yalnizca personel uclarinda
kullanilir.

(``src/lib/server/customer-profile.ts`` karsiligi.)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.campaigns import CampaignSpec, CustomerProfile, evaluate_campaigns
from ..core.color_affinity import ColorObservation, analyze_color_affinity
from ..core.loyalty import progress_to_next_tier, tier_for
from ..core.segmentation import segment_customer
from ..models import Appointment, Campaign, Customer, CustomerPhoto
from ..time_utils import now_local, to_datetime
from .risk import assess_phone_risk

COMPLETED = "COMPLETED"
NO_SHOW = "NO_SHOW"


def build_customer_profile(
    db: Session,
    customer_id: int,
    branch_id: int | None = None,
    now: datetime | None = None,
) -> dict | None:
    now = now or now_local()

    customer = db.get(Customer, customer_id)
    if customer is None:
        return None

    appointments = db.scalars(
        select(Appointment)
        .options(selectinload(Appointment.items))
        .where(Appointment.customer_id == customer_id)
        .order_by(Appointment.date.desc(), Appointment.start_min.desc())
    ).all()

    photos = db.scalars(
        select(CustomerPhoto).where(CustomerPhoto.customer_id == customer_id)
    ).all()

    completed = [a for a in appointments if a.status == COMPLETED]
    no_shows = [a for a in appointments if a.status == NO_SHOW]

    total_spend = round(sum(a.total_price for a in completed), 2)
    visit_count = len(completed)

    last_visit = completed[0] if completed else None
    last_visit_at = to_datetime(last_visit.date, 0) if last_visit else None
    last_visit_days_ago = (
        max(0, (now - last_visit_at).days) if last_visit_at else None
    )

    # Son randevusuna gelmedi mi? (tarih sirasi zaten azalan)
    last_finished = next((a for a in appointments if a.status in (COMPLETED, NO_SHOW)), None)
    last_appointment_no_show = bool(last_finished and last_finished.status == NO_SHOW)

    risk = assess_phone_risk(db, customer.phone, now=now)
    tier = tier_for(customer.loyalty_points)

    segment = segment_customer(
        total_spend=total_spend,
        visit_count=visit_count,
        no_show_count=len(no_shows),
        last_visit_days_ago=last_visit_days_ago,
        risk_score=risk.score,
        last_appointment_no_show=last_appointment_no_show,
        tier=tier,
    )

    colors = analyze_color_affinity(
        [
            ColorObservation(color_tag=p.color_tag, created_at=p.created_at)
            for p in photos
            if p.color_tag
        ],
        now=now,
    )

    raw = CustomerProfile(
        tier=tier,
        segment=segment.segment,
        total_spend=total_spend,
        visit_count=visit_count,
        points=customer.loyalty_points,
        risk_score=risk.score,
        last_visit_days_ago=last_visit_days_ago,
        service_ids=tuple({i.service_id for a in appointments for i in a.items}),
        birth_month=int(customer.birth_date[5:7]) if customer.birth_date else None,
    )

    campaign_query = select(Campaign).where(Campaign.is_active.is_(True))
    if branch_id:
        campaign_query = campaign_query.where(Campaign.branch_id == branch_id)
    campaign_rows = db.scalars(campaign_query).all()

    campaigns = evaluate_campaigns(
        raw,
        [
            CampaignSpec(
                id=c.id,
                name=c.name,
                description=c.description,
                kind=c.kind,
                value=c.value,
                target_rule=c.target_rule,
                priority=c.priority,
                is_active=c.is_active,
                starts_at=c.starts_at,
                ends_at=c.ends_at,
            )
            for c in campaign_rows
        ],
        now,
    )

    return {
        "id": customer.id,
        "firstName": customer.first_name,
        "lastName": customer.last_name,
        "phone": customer.phone,
        "email": customer.email,
        "birthDate": customer.birth_date,
        "engagementOptIn": customer.engagement_opt_in,
        "loyaltyPoints": customer.loyalty_points,
        "tier": tier,
        "tierProgress": progress_to_next_tier(customer.loyalty_points),
        "totalSpend": total_spend,
        "visitCount": visit_count,
        "noShowCount": len(no_shows),
        "lastVisitAt": last_visit_at.isoformat() if last_visit_at else None,
        "lastVisitDaysAgo": last_visit_days_ago,
        "segment": segment.to_dict(),
        "risk": risk.to_dict(),
        "colors": colors,
        "campaigns": [c.to_dict() for c in campaigns],
    }


def list_customer_summaries(db: Session, branch_id: int, now: datetime | None = None) -> list[dict]:
    """Liste ekrani icin hafif ozet.

    Her musteri icin tam profil kurmak (N+1 risk sorgusu) pahali
    oldugundan CAPRAZ-SALON risk skoru burada hesaplanmaz; yalnizca salon
    ici gelmeme oranindan turetilen yerel gosterge kullanilir.
    """
    now = now or now_local()

    customers = db.scalars(select(Customer).order_by(Customer.id)).all()
    rows = db.execute(
        select(
            Appointment.customer_id,
            Appointment.status,
            Appointment.total_price,
            Appointment.date,
        ).where(Appointment.branch_id == branch_id)
    ).all()

    by_customer: dict[int, list] = {}
    for r in rows:
        by_customer.setdefault(r.customer_id, []).append(r)

    out: list[dict] = []
    for customer in customers:
        appts = sorted(by_customer.get(customer.id, []), key=lambda r: r.date, reverse=True)
        completed = [a for a in appts if a.status == COMPLETED]
        no_shows = [a for a in appts if a.status == NO_SHOW]
        total_spend = round(sum(a.total_price for a in completed), 2)

        last_visit_date = completed[0].date if completed else None
        last_visit_days_ago = (
            max(0, (now - to_datetime(last_visit_date, 0)).days) if last_visit_date else None
        )

        finished = len(completed) + len(no_shows)
        local_risk = round((len(no_shows) / finished) * 100) if finished > 0 else 0

        tier = tier_for(customer.loyalty_points)
        last_finished = next((a for a in appts if a.status in (COMPLETED, NO_SHOW)), None)

        segment = segment_customer(
            total_spend=total_spend,
            visit_count=len(completed),
            no_show_count=len(no_shows),
            last_visit_days_ago=last_visit_days_ago,
            risk_score=local_risk,
            last_appointment_no_show=bool(last_finished and last_finished.status == NO_SHOW),
            tier=tier,
        )

        out.append(
            {
                "id": customer.id,
                "firstName": customer.first_name,
                "lastName": customer.last_name,
                "phone": customer.phone,
                "tier": tier,
                "loyaltyPoints": customer.loyalty_points,
                "totalSpend": total_spend,
                "visitCount": len(completed),
                "noShowCount": len(no_shows),
                "lastVisitDaysAgo": last_visit_days_ago,
                "localRiskScore": local_risk,
                "segment": segment.to_dict(),
            }
        )

    return out
