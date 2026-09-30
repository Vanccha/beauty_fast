"""Risk, sadakat, firsat, segment, renk ve kampanya skorlamalari."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.campaigns import (
    CampaignSpec,
    CustomerProfile,
    best_discount,
    evaluate_campaigns,
    matches_rule,
    parse_target_rule,
)
from app.core.color_affinity import ColorObservation, analyze_color_affinity, family_of
from app.core.loyalty import (
    calculate_decay,
    calculate_earned_points,
    progress_to_next_tier,
    tier_for,
)
from app.core.opportunity import OccupancySample, score_day, score_opportunity
from app.core.risk_score import (
    RiskEventInput,
    compute_risk_score,
    hash_phone,
    normalize_phone,
)
from app.core.segmentation import segment_customer

NOW = datetime(2026, 9, 1, 12, 0)


# ---------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------


def test_phone_is_normalized_to_ten_digits():
    assert normalize_phone("+90 555 111 22 33") == "5551112233"
    assert normalize_phone("0555 111 22 33") == "5551112233"


def test_phone_hash_is_one_way_and_stable():
    a = hash_phone("5551112233")
    b = hash_phone("+90 555 111 22 33")
    assert a == b
    assert "5551112233" not in a
    assert len(a) == 64


def test_insufficient_data_is_not_labelled():
    events = [RiskEventInput("NO_SHOW", NOW - timedelta(days=5))]
    result = compute_risk_score(events, now=NOW)
    assert result.label == "YETERSIZ_VERI"
    assert "yeterli geçmiş veri yok" in result.message


def test_recent_no_shows_outweigh_old_ones():
    recent = compute_risk_score(
        [
            RiskEventInput("NO_SHOW", NOW - timedelta(days=3)),
            RiskEventInput("NO_SHOW", NOW - timedelta(days=6)),
            RiskEventInput("COMPLETED", NOW - timedelta(days=9)),
            RiskEventInput("COMPLETED", NOW - timedelta(days=12)),
        ],
        now=NOW,
    )
    old = compute_risk_score(
        [
            RiskEventInput("NO_SHOW", NOW - timedelta(days=150)),
            RiskEventInput("NO_SHOW", NOW - timedelta(days=160)),
            RiskEventInput("COMPLETED", NOW - timedelta(days=9)),
            RiskEventInput("COMPLETED", NOW - timedelta(days=12)),
        ],
        now=NOW,
    )
    assert recent.score > old.score
    # Son donemde 4 randevunun 2'si kacirilmis: ORTA banda duser (20-45).
    assert recent.label == "ORTA"


def test_three_of_four_no_shows_is_high_risk():
    result = compute_risk_score(
        [
            RiskEventInput("NO_SHOW", NOW - timedelta(days=3)),
            RiskEventInput("NO_SHOW", NOW - timedelta(days=6)),
            RiskEventInput("NO_SHOW", NOW - timedelta(days=9)),
            RiskEventInput("COMPLETED", NOW - timedelta(days=12)),
        ],
        now=NOW,
    )
    assert result.label == "YUKSEK"
    assert "Ön ödeme" in result.message


def test_reliable_customer_is_low_risk():
    events = [RiskEventInput("COMPLETED", NOW - timedelta(days=d)) for d in (5, 20, 40, 60, 80)]
    result = compute_risk_score(events, now=NOW)
    assert result.label == "DUSUK"


def test_assessment_leaks_no_salon_information():
    result = compute_risk_score(
        [RiskEventInput("NO_SHOW", NOW - timedelta(days=d)) for d in (5, 10, 15)], now=NOW
    )
    assert set(result.to_dict()) == {
        "score", "label", "totalAppointments", "noShowRate", "windowMonths", "message"
    }


def test_events_outside_window_are_ignored():
    result = compute_risk_score(
        [RiskEventInput("NO_SHOW", NOW - timedelta(days=400))], now=NOW
    )
    assert result.total_appointments == 0


# ---------------------------------------------------------------------
# Sadakat
# ---------------------------------------------------------------------


def test_tier_thresholds():
    assert tier_for(0) == "BRONZ"
    assert tier_for(499) == "BRONZ"
    assert tier_for(500) == "GUMUS"
    assert tier_for(1500) == "ALTIN"
    assert tier_for(4000) == "VIP"


def test_frequent_visitor_earns_more():
    frequent = calculate_earned_points(1000, 10, "BRONZ")
    rare = calculate_earned_points(1000, 200, "BRONZ")
    assert frequent.points > rare.points
    assert frequent.points == 125.0  # 1000 * 0.1 * 1.25


def test_opportunity_hour_multiplier_is_capped():
    normal = calculate_earned_points(1000, 40, "BRONZ")
    opportunity = calculate_earned_points(1000, 40, "BRONZ", opportunity_discount_rate=0.25)
    assert opportunity.points > normal.points
    assert opportunity.breakdown["opportunity"] == 1.5


def test_decay_has_grace_period():
    assert calculate_decay(1000, 89)["decayAmount"] == 0
    decayed = calculate_decay(1000, 90 + 180)
    assert decayed["remaining"] == 500.0


def test_tier_progress_message():
    progress = progress_to_next_tier(400)
    assert progress["next"] == "GUMUS"
    assert progress["pointsToNext"] == 100
    assert progress_to_next_tier(5000)["next"] is None


# ---------------------------------------------------------------------
# Firsat saatleri
# ---------------------------------------------------------------------


def test_small_sample_is_shrunk_towards_mean():
    """2 gozlemde %0 doluluk, tam indirim uretmemeli."""
    sparse = score_opportunity(OccupancySample(2, 600, 0.0, 2))
    solid = score_opportunity(OccupancySample(2, 600, 0.0, 200))
    assert sparse.adjusted_occupancy > solid.adjusted_occupancy
    assert sparse.discount_rate < solid.discount_rate


def test_busy_hour_gets_no_discount():
    score = score_opportunity(OccupancySample(5, 1080, 0.95, 100))
    assert score.discount_rate == 0
    assert score.is_opportunity is False
    assert score.label == "Standart"


def test_discount_is_rounded_to_step():
    score = score_opportunity(OccupancySample(2, 600, 0.0, 500))
    assert round(score.discount_rate * 100) % 5 == 0


def test_score_day_fills_missing_slots_with_prior():
    scores = score_day(3, [540, 600, 660], [OccupancySample(3, 600, 0.9, 50)])
    assert set(scores) == {540, 600, 660}
    assert scores[600].discount_rate == 0


# ---------------------------------------------------------------------
# Segmentasyon
# ---------------------------------------------------------------------


def test_vip_requires_spend_and_reliability():
    vip = segment_customer(6000, 10, 1, 20, 10, False)
    assert vip.segment == "VIP"

    unreliable = segment_customer(6000, 10, 4, 20, 50, True)
    assert unreliable.segment == "RISKLI"


def test_vip_keeps_badge_but_shows_warning():
    """Yuksek harcama + tek gelmeme: VIP kalir ama uyari da gosterilir."""
    result = segment_customer(9000, 20, 1, 15, 50, False)
    assert result.segment == "VIP"
    assert result.warning == "Gelmeme riski yüksek"


def test_dormant_and_loyal_and_new():
    assert segment_customer(1000, 5, 0, 200, 5, False).segment == "UYUYAN"
    assert segment_customer(3000, 8, 0, 20, 5, False).segment == "SADIK"
    assert segment_customer(300, 1, 0, 10, 0, False).segment == "YENI"
    assert segment_customer(1500, 4, 0, 70, 5, False).segment == "STANDART"


# ---------------------------------------------------------------------
# Renk egilimi
# ---------------------------------------------------------------------


def test_color_family_mapping():
    assert family_of("Nude") == "NOTR"
    assert family_of("kırmızı") == "SICAK"
    assert family_of("bilinmeyen-renk") == "BILINMIYOR"


def test_recent_colors_weigh_more():
    result = analyze_color_affinity(
        [
            ColorObservation("nude", NOW - timedelta(days=5)),
            ColorObservation("nude", NOW - timedelta(days=10)),
            ColorObservation("siyah", NOW - timedelta(days=300)),
        ],
        now=NOW,
    )
    assert result["dominantFamily"] == "NOTR"
    assert result["topColors"][0]["tag"] == "nude"
    assert result["sampleSize"] == 3


def test_empty_color_history():
    result = analyze_color_affinity([], now=NOW)
    assert result["dominantFamily"] == "BILINMIYOR"
    assert result["summary"].startswith("Henüz")


# ---------------------------------------------------------------------
# Kampanyalar
# ---------------------------------------------------------------------


def _profile(**kwargs) -> CustomerProfile:
    base = dict(
        tier="GUMUS", segment="SADIK", total_spend=3000, visit_count=8, points=800,
        risk_score=10, last_visit_days_ago=100, service_ids=(1, 2), birth_month=9,
    )
    base.update(kwargs)
    return CustomerProfile(**base)


def test_rule_matching_and_reasons():
    matched, reasons = matches_rule(
        _profile(), {"minTier": "GUMUS", "maxRiskScore": 40, "minDaysSinceLastVisit": 45}, NOW
    )
    assert matched is True
    assert "düşük gelmeme riski" in reasons


def test_rule_rejects_when_condition_fails():
    matched, _ = matches_rule(_profile(risk_score=80), {"maxRiskScore": 40}, NOW)
    assert matched is False


def test_broken_rule_json_is_treated_as_empty():
    assert parse_target_rule("{bozuk json") == {}
    matched, reasons = matches_rule(_profile(), {}, NOW)
    assert matched is True
    assert reasons == ["tüm müşteriler"]


def test_campaign_priority_and_best_discount():
    campaigns = [
        CampaignSpec(1, "Düşük", None, "DISCOUNT_PERCENT", 10, "{}", 5, True, None, None),
        CampaignSpec(2, "Yüksek", None, "DISCOUNT_PERCENT", 20, "{}", 30, True, None, None),
        CampaignSpec(3, "Pasif", None, "DISCOUNT_PERCENT", 50, "{}", 90, False, None, None),
    ]
    matches = evaluate_campaigns(_profile(), campaigns, NOW)
    assert [m.campaign_id for m in matches] == [2, 1]
    assert best_discount(matches).value == 20


def test_expired_campaign_is_ignored():
    campaigns = [
        CampaignSpec(
            1, "Bitmiş", None, "DISCOUNT_PERCENT", 10, "{}", 5, True,
            NOW - timedelta(days=60), NOW - timedelta(days=30),
        )
    ]
    assert evaluate_campaigns(_profile(), campaigns, NOW) == []
