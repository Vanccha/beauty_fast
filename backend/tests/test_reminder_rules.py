"""Hatirlatma kural motoru: dort formul + kural onceligi."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.core.reminder_rules import (
    ReminderContext,
    ReminderRuleSpec,
    compute_interval_days,
    resolve_pre_reminder,
    resolve_reminder,
    select_rule,
)

NOW = datetime(2026, 7, 15, 10, 0)


def rule(**kwargs) -> ReminderRuleSpec:
    base = dict(
        id=1, name="Kural", service_id=None, category_id=None, formula="FIXED",
        base_days=30, params="{}", channel="SMS", template="{ad}: {gun} gün", priority=0,
        is_active=True,
    )
    base.update(kwargs)
    return ReminderRuleSpec(**base)


def context(**kwargs) -> ReminderContext:
    base = dict(
        service_id=1, category_id=10, service_name="Saç Boyası", customer_name="Ayşe",
        performed_at=NOW,
    )
    base.update(kwargs)
    return ReminderContext(**base)


def test_fixed_formula():
    assert compute_interval_days(rule(base_days=21), context()) == 21


def test_growth_formula_uses_hair_growth_rate():
    """14 mm tolerans / ayda 12 mm -> ~35 gun."""
    growth = rule(
        formula="GROWTH", base_days=20, params='{"mmPerMonth": 12, "toleranceMm": 14}'
    )
    assert compute_interval_days(growth, context()) == 35


def test_growth_respects_base_days_as_floor():
    growth = rule(
        formula="GROWTH", base_days=40, params='{"mmPerMonth": 12, "toleranceMm": 14}'
    )
    assert compute_interval_days(growth, context()) == 40


def test_product_lifetime_formula():
    product = rule(
        formula="PRODUCT_LIFETIME",
        base_days=21,
        params='{"productDays": {"kalici_oje": 21, "jel": 28, "klasik_oje": 7}}',
    )
    assert compute_interval_days(product, context(product_key="jel")) == 28
    # Bilinmeyen urun -> base_days
    assert compute_interval_days(product, context(product_key="yok")) == 21


def test_seasonal_formula_shortens_in_summer():
    seasonal = rule(
        formula="SEASONAL", base_days=30, params='{"monthFactors": {"7": 1.3, "1": 0.8}}'
    )
    # Temmuz (7. ay): 30 * 1.3 = 39
    assert compute_interval_days(seasonal, context(performed_at=NOW)) == 39
    # Ocak: 30 * 0.8 = 24
    assert compute_interval_days(seasonal, context(performed_at=datetime(2026, 1, 10))) == 24


def test_broken_params_fall_back_to_base_days():
    broken = rule(formula="SEASONAL", base_days=30, params="{bozuk")
    assert compute_interval_days(broken, context()) == 30


def test_rule_selection_priority():
    """Hizmet eslesmesi > kategori > sube geneli; esitlikte priority."""
    rules = [
        rule(id=1, service_id=None, category_id=None, priority=50),
        rule(id=2, service_id=None, category_id=10, priority=10),
        rule(id=3, service_id=1, category_id=None, priority=0),
    ]
    assert select_rule(rules, service_id=1, category_id=10).id == 3
    assert select_rule(rules, service_id=99, category_id=10).id == 2
    assert select_rule(rules, service_id=99, category_id=99).id == 1


def test_inactive_rules_are_skipped():
    rules = [rule(id=3, service_id=1, is_active=False), rule(id=1)]
    assert select_rule(rules, service_id=1, category_id=None).id == 1


def test_resolve_reminder_renders_template_and_dedupe_key():
    reminder = resolve_reminder(
        [rule(id=7, service_id=1, base_days=35, template="{ad}, {hizmet} için {gun} gün")],
        context(),
        appointment_id=99,
    )
    assert reminder is not None
    assert reminder.body == "Ayşe, Saç Boyası için 35 gün"
    assert reminder.due_at == NOW + timedelta(days=35)
    assert reminder.dedupe_key == "repeat:99:7:1"


def test_falls_back_to_service_recommended_days_without_rule():
    reminder = resolve_reminder([], context(recommended_repeat_days=45), appointment_id=1)
    assert reminder is not None
    assert reminder.days == 45
    assert reminder.rule_id is None


def test_no_reminder_without_rule_or_recommendation():
    assert resolve_reminder([], context(), appointment_id=1) is None


def test_pre_reminder_is_skipped_for_past_appointments():
    past = resolve_pre_reminder(1, NOW - timedelta(days=1), "Fön", "Ayşe", now=NOW)
    assert past is None

    upcoming = resolve_pre_reminder(
        1, NOW + timedelta(days=2), "Fön", "Ayşe", hours_before=24, now=NOW
    )
    assert upcoming is not None
    assert upcoming.dedupe_key == "pre:1:24"
    assert "randevunuz var" in upcoming.body
