"""
====================================================================
ALGORITMIK KAMPANYA HEDEFLEME
====================================================================

Kampanyalar manuel kupon kodu yerine, musteri profiline uygulanan
kurallarla otomatik tetiklenir. Kural ``campaign.target_rule`` alaninda
JSON olarak saklanir; bu modul onu saf bir fonksiyonla degerlendirir.

Ornek kural:
    {"minTier":"GUMUS","maxRiskScore":40,"minDaysSinceLastVisit":45}
    -> "Gumus ve ustu, riski dusuk, 45 gundur ugramamis musteriler"

Taninmayan anahtarlar sessizce yok sayilir (ileri uyumluluk).

(``loyalty/campaigns.ts`` karsiligi.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from .loyalty import TIER_THRESHOLDS
from ..time_utils import now_local


@dataclass(frozen=True)
class CustomerProfile:
    tier: str
    segment: str
    total_spend: float
    visit_count: int
    points: float
    risk_score: float
    last_visit_days_ago: int | None
    service_ids: tuple[int, ...]
    birth_month: int | None


@dataclass(frozen=True)
class CampaignSpec:
    id: int
    name: str
    description: str | None
    kind: str
    value: float
    target_rule: str
    priority: int
    is_active: bool
    starts_at: datetime | None
    ends_at: datetime | None


@dataclass(frozen=True)
class CampaignMatch:
    campaign_id: int
    name: str
    kind: str
    value: float
    #: Neden eslesti - seffaflik icin
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "campaignId": self.campaign_id,
            "name": self.name,
            "kind": self.kind,
            "value": self.value,
            "reasons": list(self.reasons),
        }


def _tier_rank(tier: str) -> int:
    for i, t in enumerate(TIER_THRESHOLDS):
        if t["tier"] == tier:
            return i
    return -1


def parse_target_rule(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def matches_rule(
    profile: CustomerProfile,
    rule: dict[str, Any],
    now: datetime | None = None,
) -> tuple[bool, list[str]]:
    """Profil kurala uyuyor mu? Tanimlanmamis kosullar "serbest" sayilir."""
    now = now or now_local()
    reasons: list[str] = []

    def fail() -> tuple[bool, list[str]]:
        return False, []

    if "minTier" in rule:
        if _tier_rank(profile.tier) < _tier_rank(rule["minTier"]):
            return fail()
        reasons.append(f"{rule['minTier']} ve üzeri seviye")
    if "maxTier" in rule and _tier_rank(profile.tier) > _tier_rank(rule["maxTier"]):
        return fail()

    if rule.get("segments"):
        if profile.segment not in rule["segments"]:
            return fail()
        reasons.append(f"{profile.segment} segmenti")

    if "minTotalSpend" in rule:
        if profile.total_spend < rule["minTotalSpend"]:
            return fail()
        reasons.append(f"toplam harcama >= {rule['minTotalSpend']} TL")
    if "maxTotalSpend" in rule and profile.total_spend > rule["maxTotalSpend"]:
        return fail()

    if "minVisits" in rule:
        if profile.visit_count < rule["minVisits"]:
            return fail()
        reasons.append(f"{rule['minVisits']}+ ziyaret")
    if "maxVisits" in rule and profile.visit_count > rule["maxVisits"]:
        return fail()

    if "minPoints" in rule:
        if profile.points < rule["minPoints"]:
            return fail()
        reasons.append(f"{rule['minPoints']}+ puan")

    if "maxRiskScore" in rule:
        if profile.risk_score > rule["maxRiskScore"]:
            return fail()
        reasons.append("düşük gelmeme riski")

    if "minDaysSinceLastVisit" in rule:
        if (
            profile.last_visit_days_ago is None
            or profile.last_visit_days_ago < rule["minDaysSinceLastVisit"]
        ):
            return fail()
        reasons.append(f"{rule['minDaysSinceLastVisit']} gündür ziyaret yok")
    if "maxDaysSinceLastVisit" in rule and (
        profile.last_visit_days_ago is None
        or profile.last_visit_days_ago > rule["maxDaysSinceLastVisit"]
    ):
        return fail()

    if rule.get("anyServiceIds"):
        if not any(sid in profile.service_ids for sid in rule["anyServiceIds"]):
            return fail()
        reasons.append("ilgili hizmet geçmişi")

    if rule.get("birthdayMonth"):
        if profile.birth_month is None or profile.birth_month != now.month:
            return fail()
        reasons.append("doğum günü ayı")

    return True, reasons or ["tüm müşteriler"]


def evaluate_campaigns(
    profile: CustomerProfile,
    campaigns: Sequence[CampaignSpec],
    now: datetime | None = None,
) -> list[CampaignMatch]:
    """Aktif ve tarih araligindaki kampanyalardan eslesenleri oncelik sirasiyla doner."""
    now = now or now_local()
    matched: list[tuple[CampaignSpec, list[str]]] = []

    for c in campaigns:
        if not c.is_active:
            continue
        if c.starts_at and c.starts_at > now:
            continue
        if c.ends_at and c.ends_at < now:
            continue
        ok, reasons = matches_rule(profile, parse_target_rule(c.target_rule), now)
        if ok:
            matched.append((c, reasons))

    matched.sort(key=lambda x: (-x[0].priority, x[0].id))
    return [
        CampaignMatch(c.id, c.name, c.kind, c.value, tuple(reasons)) for c, reasons in matched
    ]


def best_discount(matches: Sequence[CampaignMatch]) -> CampaignMatch | None:
    """Eslesen kampanyalardan en iyi indirimi secer (indirimler birlestirilmez)."""
    discounts = [m for m in matches if m.kind == "DISCOUNT_PERCENT"]
    if not discounts:
        return None
    return max(discounts, key=lambda m: m.value)
