"""
====================================================================
YENILEME (TEKRAR RANDEVU) DAVETI - hizmet bazli kurallar
====================================================================

Randevu COMPLETED olunca, randevudaki her hizmet icin ``ReminderRule``
(hizmet > kategori > sube geneli) cozulur; EN ERKEN vadeli olan tek bir
WhatsApp daveti kuyruga yazilir.

Kurallar:
  * TICARI iletidir (6563 / ETK): yalniz ``marketing_consent_at`` dolu ve
    anonimlestirilmemis musteriye gider. Kuyruga alirken VE gonderirken
    (``notifications._claim_due``) kontrol edilir.
  * Mesajin sonunda cikis satiri vardir; ``RET`` yazan musterinin onayi
    ``whatsapp_inbound`` tarafindan geri alinir.
  * Musteri basina TEK bekleyen davet: yeni tamamlanan randevu, eskisini
    (bekleyen) iptal edip yerine gecer.
  * Hizmete ozel kural PASIF ise o hizmet icin davet KAPALIDIR (kategori /
    genel kurala dusmez). Hic kural kapsamiyorsa hizmetin
    ``recommended_repeat_days`` degerine (varsa) varsayilan metinle dusulur.
  * Davet gonderilmeden once musterinin gelecekte aktif randevusu varsa
    (yeniden randevu almis) gonderilmez - bkz. ``notifications._claim_due``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import config
from ..core.reminder_rules import (
    ReminderContext,
    ReminderRuleSpec,
    compute_interval_days,
    render_template,
    select_rule,
)
from ..models import Appointment, Customer, ReminderRule, Salon, ScheduledNotification
from ..time_utils import to_datetime
from .privacy import MARKETING_DEDUPE_PREFIX, is_marketing_allowed

DEFAULT_TEMPLATE = (
    "Merhaba {ad}, son {hizmet} işleminizin üzerinden epey zaman geçti. "
    "Yenileme zamanı geldiyse size uygun saati ayıralım: {randevu_linki}"
)
PLACEHOLDERS = {
    "{ad}": "Müşterinin adı",
    "{hizmet}": "Hizmetin adı",
    "{randevu_linki}": "Online randevu sayfası",
}
OPT_OUT_LINE = "Bu mesajları almak istemiyorsanız RET yazabilirsiniz."
OPT_OUT_KEYWORD = "RET"


def _spec(r: ReminderRule) -> ReminderRuleSpec:
    return ReminderRuleSpec(
        id=r.id,
        name=r.name,
        service_id=r.service_id,
        category_id=r.category_id,
        formula=r.formula,
        base_days=r.base_days,
        params=r.params,
        channel=r.channel,
        template=r.template,
        priority=r.priority,
        is_active=r.is_active,
    )


def build_body(template: str, context: ReminderContext, days: int) -> str:
    return f"{render_template(template, context, days)}\n\n{OPT_OUT_LINE}"


def queue_rebooking(
    db: Session,
    appointment: Appointment,
    customer: Customer,
    salon: Salon | None,
) -> bool:
    """Tek davet kuyruga yazilir. Yazildiysa True. Commit cagiranindir."""
    if not appointment.items or not customer.phone or not is_marketing_allowed(customer):
        return False

    rules = db.scalars(
        select(ReminderRule).where(
            ReminderRule.branch_id == appointment.branch_id)
    ).all()
    specs = [_spec(r) for r in rules]
    performed_at = to_datetime(appointment.date, appointment.end_min)
    booking_url = f"{config.public_site_url}/randevu"

    best: tuple[datetime, int, ReminderRuleSpec | None, ReminderContext] | None = None
    for item in appointment.items:
        service = item.service
        if service is None:
            continue
        # Hizmete ozel kural var ama hepsi pasifse: bu hizmet icin davet kapali.
        own = [r for r in specs if r.service_id == service.id]
        if own and not any(r.is_active for r in own):
            continue
        context = ReminderContext(
            service_id=service.id,
            category_id=service.category_id,
            service_name=service.name,
            customer_name=customer.first_name,
            performed_at=performed_at,
            salon_name=salon.name if salon else None,
            booking_url=booking_url,
        )
        rule = select_rule(specs, service.id, service.category_id)
        if rule is not None:
            days = compute_interval_days(rule, context)
        else:
            # Kural yok: hizmetin onerilen tekrar araligina (varsa) dusulur.
            days = service.recommended_repeat_days or 0
        if days <= 0:
            continue
        due_at = performed_at + timedelta(days=days)
        if best is None or due_at < best[0]:
            best = (due_at, days, rule, context)

    if best is None:
        return False
    due_at, days, rule, context = best

    key = (
        f"{MARKETING_DEDUPE_PREFIX}{appointment.id}:"
        f"{rule.id if rule else 'default'}:{context.service_id}"
    )
    if db.scalar(select(ScheduledNotification.id).where(ScheduledNotification.dedupe_key == key)):
        return False

    # Musteri basina tek bekleyen davet: eskisi yenisiyle degisir.
    db.execute(
        update(ScheduledNotification)
        .where(
            ScheduledNotification.customer_id == customer.id,
            ScheduledNotification.status == "PENDING",
            ScheduledNotification.dedupe_key.startswith(MARKETING_DEDUPE_PREFIX),
        )
        .values(status="CANCELLED")
    )
    db.add(
        ScheduledNotification(
            customer_id=customer.id,
            rule_id=rule.id if rule else None,
            channel="WHATSAPP",
            body=build_body(rule.template if rule else DEFAULT_TEMPLATE, context, days),
            due_at=due_at,
            dedupe_key=key,
        )
    )
    return True
