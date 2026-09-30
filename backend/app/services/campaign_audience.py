"""
====================================================================
KAMPANYA KAPSAMI - "su anda kac musteri eslesiyor?"
====================================================================

Kampanya yonetim ekrani her kural icin kapsam sayisini GERCEK musteri
profilleriyle hesaplar; yonetici kurali yayinlamadan once kac kisiye
dokunacagini gorur.

Profil, liste ekraniyla ayni hafif ozetten (``list_customer_summaries``)
kurulur: capraz-salon risk yerine salon ici gelmeme orani kullanilir,
hizmet gecmisi ve dogum ayi bu hesaba katilmaz (orijinal panel sayfasi
ile birebir ayni varsayimlar).
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy.orm import Session

from ..core.campaigns import CampaignSpec, CustomerProfile, evaluate_campaigns
from ..core.loyalty import tier_for
from ..models import Campaign
from .customer_profile import list_customer_summaries
from ..time_utils import now_local


def campaign_spec_of(campaign: Campaign) -> CampaignSpec:
    return CampaignSpec(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        kind=campaign.kind,
        value=campaign.value,
        target_rule=campaign.target_rule,
        priority=campaign.priority,
        is_active=campaign.is_active,
        starts_at=campaign.starts_at,
        ends_at=campaign.ends_at,
    )


def campaign_match_counts(
    db: Session,
    branch_id: int,
    campaigns: Sequence[Campaign],
    now: datetime | None = None,
) -> tuple[dict[int, int], int]:
    """Kampanya basina eslesen musteri sayisi + toplam musteri sayisi.

    Pasif veya tarih araligi disindaki kampanyalar ``evaluate_campaigns``
    tarafindan zaten elenir - bu kampanyalarin kapsami 0 gorunur.
    """
    now = now or now_local()
    specs = [campaign_spec_of(c) for c in campaigns]
    summaries = list_customer_summaries(db, branch_id, now=now)

    counts: dict[int, int] = {}
    for summary in summaries:
        profile = CustomerProfile(
            tier=tier_for(summary["loyaltyPoints"]),
            segment=summary["segment"]["segment"],
            total_spend=summary["totalSpend"],
            visit_count=summary["visitCount"],
            points=summary["loyaltyPoints"],
            risk_score=summary["localRiskScore"],
            last_visit_days_ago=summary["lastVisitDaysAgo"],
            service_ids=(),
            birth_month=None,
        )
        for match in evaluate_campaigns(profile, specs, now):
            counts[match.campaign_id] = counts.get(match.campaign_id, 0) + 1

    return counts, len(summaries)
