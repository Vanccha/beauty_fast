"""
====================================================================
HATIRLATMA KURAL MOTORU
====================================================================

"Sac boyasina 5 hafta sonra hatirlatma gonder" gibi mantiklar koda
gomulmez; ``reminder_rule`` tablosunda yapilandirilir ve burada
degerlendirilir. Yeni bir hizmet turu eklemek icin kod degismez.

Formuller
---------
FIXED             - ``base_days`` kadar sonra.

GROWTH            - Dip boya buyumesi. Sac ortalama ayda ~12 mm uzar:
                       gun = (toleranceMm / mmPerMonth) * 30
                    params: {"mmPerMonth": 12, "toleranceMm": 14} -> ~35 gun
                    ``base_days`` alt sinir olarak uygulanir.

PRODUCT_LIFETIME  - Kullanilan urune gore:
                    {"productDays": {"kalici_oje": 21, "jel": 28}}

SEASONAL          - Mevsimsel carpan:
                    {"monthFactors": {"6": 0.8, "12": 1.2}}

Kural secim onceligi
--------------------
  1) Hizmete ozel kural (service_id eslesmesi)
  2) Kategoriye ait kural (category_id eslesmesi)
  3) Sube geneli kural (ikisi de None)
Esitlikte ``priority`` yuksek olan kazanir.

(``notifications/reminder-rules.ts`` karsiligi.)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Sequence
from ..time_utils import now_local


@dataclass(frozen=True)
class ReminderRuleSpec:
    id: int
    name: str
    service_id: int | None
    category_id: int | None
    formula: str
    base_days: int
    #: JSON metni
    params: str
    channel: str
    template: str
    priority: int
    is_active: bool


@dataclass(frozen=True)
class ReminderContext:
    service_id: int
    category_id: int | None
    service_name: str
    customer_name: str
    #: Randevunun gerceklestigi an
    performed_at: datetime
    #: Kullanilan urun anahtari (orn. "kalici_oje")
    product_key: str | None = None
    #: Hizmet tanimindaki oneri (kural yoksa yedek)
    recommended_repeat_days: int | None = None
    salon_name: str | None = None
    booking_url: str | None = None


@dataclass(frozen=True)
class ResolvedReminder:
    rule_id: int | None
    channel: str
    due_at: datetime
    days: int
    body: str
    #: Ayni kural + randevu icin tekrar uretimi engeller
    dedupe_key: str


def _parse_params(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def select_rule(
    rules: Sequence[ReminderRuleSpec],
    service_id: int,
    category_id: int | None,
) -> ReminderRuleSpec | None:
    """Baglama en uygun kurali secer."""
    active = [r for r in rules if r.is_active]

    by_service = sorted(
        (r for r in active if r.service_id == service_id), key=lambda r: -r.priority
    )
    if by_service:
        return by_service[0]

    if category_id is not None:
        by_category = sorted(
            (r for r in active if r.service_id is None and r.category_id == category_id),
            key=lambda r: -r.priority,
        )
        if by_category:
            return by_category[0]

    generic = sorted(
        (r for r in active if r.service_id is None and r.category_id is None),
        key=lambda r: -r.priority,
    )
    return generic[0] if generic else None


def compute_interval_days(rule: ReminderRuleSpec, context: ReminderContext) -> int:
    """Kuralin ongordugu gun sayisini hesaplar."""
    params = _parse_params(rule.params)

    if rule.formula == "GROWTH":
        mm_per_month = float(params.get("mmPerMonth") or 12)
        tolerance_mm = float(params.get("toleranceMm") or 14)
        days = (tolerance_mm / mm_per_month) * 30
        return max(rule.base_days, int(round(days)))

    if rule.formula == "PRODUCT_LIFETIME":
        table = params.get("productDays") or {}
        found = table.get(context.product_key or "")
        try:
            found = float(found)
        except (TypeError, ValueError):
            found = None
        return int(round(found)) if found and found > 0 else rule.base_days

    if rule.formula == "SEASONAL":
        factors = params.get("monthFactors") or {}
        factor = factors.get(str(context.performed_at.month))
        try:
            factor = float(factor)
        except (TypeError, ValueError):
            factor = None
        applied = factor if factor and factor > 0 else 1.0
        return max(1, int(round(rule.base_days * applied)))

    # FIXED ve bilinmeyen formuller
    return rule.base_days


def _render_template(template: str, context: ReminderContext, days: int) -> str:
    return (
        template.replace("{ad}", context.customer_name)
        .replace("{hizmet}", context.service_name)
        .replace("{gun}", str(days))
        .replace("{salon}", context.salon_name or "Salonumuz")
        .replace("{link}", context.booking_url or "")
    )


def resolve_reminder(
    rules: Sequence[ReminderRuleSpec],
    context: ReminderContext,
    appointment_id: int,
) -> ResolvedReminder | None:
    """Randevu tamamlandiginda gonderilecek "tekrar zamani" hatirlatmasi.

    Uygun kural yoksa hizmetin ``recommended_repeat_days`` alani kullanilir;
    o da yoksa hatirlatma uretilmez.
    """
    rule = select_rule(rules, context.service_id, context.category_id)

    days = (
        compute_interval_days(rule, context)
        if rule
        else (context.recommended_repeat_days or 0)
    )

    if not days or days <= 0:
        return None

    template = rule.template if rule else (
        "{ad}, {hizmet} işleminizin üzerinden {gun} gün geçti. Yenileme zamanı geldi 🙂 {link}"
    )

    return ResolvedReminder(
        rule_id=rule.id if rule else None,
        channel=rule.channel if rule else "SMS",
        due_at=context.performed_at + timedelta(days=days),
        days=days,
        body=_render_template(template, context, days),
        dedupe_key=f"repeat:{appointment_id}:{rule.id if rule else 'default'}:{context.service_id}",
    )


def resolve_pre_reminder(
    appointment_id: int,
    starts_at: datetime,
    service_name: str,
    customer_name: str,
    hours_before: int = 24,
    channel: str = "SMS",
    now: datetime | None = None,
) -> ResolvedReminder | None:
    """Randevu oncesi ("yarin saat 14:00'te randevunuz var") hatirlatmasi."""
    now = now or now_local()
    due_at = starts_at - timedelta(hours=hours_before)
    if due_at <= now:
        return None

    time_label = f"{starts_at.hour:02d}:{starts_at.minute:02d}"

    return ResolvedReminder(
        rule_id=None,
        channel=channel,
        due_at=due_at,
        days=0,
        body=(
            f"{customer_name}, yarın saat {time_label} randevunuz var "
            f"({service_name}). Görüşmek üzere!"
        ),
        dedupe_key=f"pre:{appointment_id}:{hours_before}",
    )
