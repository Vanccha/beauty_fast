"""
====================================================================
RANDEVU DURUM DEGISIMI - tek yan etki noktasi
====================================================================

Bir randevunun durumu degistiginde birden cok alt sistem etkilenir. Bu
mantik iki ayri uca (musteri iptali + personel durum guncellemesi)
kopyalanirsa er ya da gec ayrisir; bu yuzden TEK yerde toplanmistir.

  CANCELLED / NO_SHOW -> doluluk hucreleri SILINIR (slot serbest kalir)
  NO_SHOW             -> risk havuzuna NO_SHOW olayi
  CANCELLED           -> risk havuzuna LATE_CANCEL (randevuya < 24 saat kala)
  COMPLETED           -> stok dusumu (idempotent) + sadakat puani
                         + risk havuzuna COMPLETED + tekrar hatirlatmasi

Tumu TEK transaction icindedir: "stok dustu ama puan yazilmadi" gibi
yarim durumlar olusamaz. ``version`` kontrolu optimistic locking saglar.

(``src/lib/server/appointment-status.ts`` karsiligi.)
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from ..core.loyalty import calculate_earned_points, tier_for
from ..core.reminder_rules import ReminderContext, ReminderRuleSpec, resolve_reminder
from ..errors import AppError, VersionConflictError
from ..models import (
    Appointment,
    AppointmentItem,
    Branch,
    Customer,
    LoyaltyEntry,
    OccupancyCell,
    ReminderRule,
    Salon,
    ScheduledNotification,
)
from ..time_utils import now_local, to_datetime
from .privacy import is_marketing_allowed
from .risk import record_risk_event
from .stock import consume_for_appointment

TERMINAL = ("COMPLETED", "CANCELLED", "NO_SHOW")

#: Randevuya bu kadar saatten az kala yapilan iptal "gec iptal" sayilir.
LATE_CANCEL_HOURS = 24


def change_appointment_status(
    db: Session,
    appointment_id: int,
    status: str,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> dict:
    now = now or now_local()

    try:
        appointment = db.scalar(
            select(Appointment)
            .options(
                selectinload(Appointment.items).selectinload(AppointmentItem.service),
                selectinload(Appointment.customer),
            )
            .where(Appointment.id == appointment_id)
        )
        if appointment is None:
            raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)

        if expected_version is not None and appointment.version != expected_version:
            raise VersionConflictError(appointment.version)

        if appointment.status in TERMINAL:
            raise AppError(
                "VALIDATION",
                f'Bu randevu zaten "{appointment.status}" durumunda; tekrar güncellenemez.',
                409,
            )

        # --- Surum kontrollu guncelleme (asil optimistic locking adimi) ---
        # ``status NOT IN TERMINAL`` kosulu, surum gonderilmeyen eszamanli iki
        # istegin (cift tiklama) randevuyu IKI KEZ tamamlamasini engeller:
        # ikinci UPDATE birincinin satir kilidini bekler, sonra kosulu yeniden
        # degerlendirir ve 0 satir etkiler.
        stmt = update(Appointment).where(
            Appointment.id == appointment.id, Appointment.status.not_in(TERMINAL)
        )
        if expected_version is not None:
            stmt = stmt.where(Appointment.version == expected_version)
        updated = db.execute(
            stmt.values(status=status, version=Appointment.version + 1)
        ).rowcount
        if not updated:
            raise VersionConflictError(appointment.version)

        # Yeni surum VERITABANINDAN okunur, ``appointment.version + 1`` ile
        # HESAPLANMAZ: yukaridaki ``update()`` oturumdaki nesnenin alanlarini
        # da tazeler (synchronize_session), dolayisiyla elde tutulan degere
        # bir daha +1 eklemek istemciye bir fazla surum dondururdu - sonraki
        # optimistic locking cagrisi haksiz yere VERSION_MISMATCH alirdi.
        new_version = db.scalar(
            select(Appointment.version).where(Appointment.id == appointment.id)
        )

        branch = db.get(Branch, appointment.branch_id)
        salon = db.get(Salon, branch.salon_id) if branch else None

        starts_at = to_datetime(appointment.date, appointment.start_min)
        freed_slot = False
        stock = None
        loyalty = None
        reminder_queued = False

        # --- Iptal / gelmedi: slotu serbest birak -------------------------
        if status in ("CANCELLED", "NO_SHOW"):
            db.execute(
                delete(OccupancyCell).where(OccupancyCell.appointment_id == appointment.id)
            )
            freed_slot = True

            # Bekleyen "yarin randevunuz var" hatirlatmasi iptal edilir.
            db.execute(
                update(ScheduledNotification)
                .where(
                    ScheduledNotification.dedupe_key == f"pre:{appointment.id}:24",
                    ScheduledNotification.status == "PENDING",
                )
                .values(status="CANCELLED")
            )

            hours_until = (starts_at - now).total_seconds() / 3600.0
            outcome = (
                "NO_SHOW"
                if status == "NO_SHOW"
                else ("LATE_CANCEL" if hours_until < LATE_CANCEL_HOURS else None)
            )

            # Erken iptal cezalandirilmaz - risk havuzuna yazilmaz.
            if outcome:
                record_risk_event(
                    db,
                    phone=appointment.customer.phone,
                    outcome=outcome,
                    occurred_at=starts_at,
                    salon_id=branch.salon_id if branch else None,
                )

        # --- Tamamlandi: stok + puan + risk + hatirlatma --------------------
        if status == "COMPLETED":
            stock = consume_for_appointment(db, appointment.id)

            record_risk_event(
                db,
                phone=appointment.customer.phone,
                outcome="COMPLETED",
                occurred_at=starts_at,
                salon_id=branch.salon_id if branch else None,
            )

            # Onceki ziyaret: siklik carpaninin girdisi
            previous = db.scalar(
                select(Appointment)
                .where(
                    Appointment.customer_id == appointment.customer_id,
                    Appointment.status == "COMPLETED",
                    Appointment.id != appointment.id,
                )
                .order_by(Appointment.date.desc(), Appointment.start_min.desc())
                .limit(1)
            )

            days_since_last_visit = (
                max(0, (starts_at - to_datetime(previous.date, 0)).days) if previous else None
            )

            # Puan bakiyesi oku-degistir-yaz ile guncellenir; ayni musterinin
            # iki randevusu ayni anda tamamlanirsa guncelleme kaybolmasin diye
            # satir kilitlenir (SELECT ... FOR UPDATE).
            customer: Customer = db.get(
                Customer, appointment.customer_id, with_for_update=True, populate_existing=True
            )
            current_tier = tier_for(customer.loyalty_points)
            earned = calculate_earned_points(
                amount=appointment.total_price,
                days_since_last_visit=days_since_last_visit,
                current_tier=current_tier,
                opportunity_discount_rate=appointment.discount_rate,
            )

            db.add(
                LoyaltyEntry(
                    customer_id=appointment.customer_id,
                    appointment_id=appointment.id,
                    delta=earned.points,
                    reason="OPPORTUNITY_BONUS" if appointment.is_opportunity else "SPEND",
                    breakdown=json.dumps(earned.breakdown),
                )
            )

            new_points = round(customer.loyalty_points + earned.points, 2)
            customer.loyalty_points = new_points
            customer.tier = tier_for(new_points)

            loyalty = {
                "points": earned.points,
                "explanation": earned.explanation,
                "newTier": customer.tier,
            }

            # --- Tekrar hatirlatmasi (kural motoru) ------------------------
            rules = db.scalars(
                select(ReminderRule).where(
                    ReminderRule.branch_id == appointment.branch_id,
                    ReminderRule.is_active.is_(True),
                )
            ).all()

            # KVKK / 6563: tekrar hatirlatmasi ticari iletidir - onay yoksa
            # kuyruga hic alinmaz.
            first = appointment.items[0] if appointment.items else None
            if first is not None and is_marketing_allowed(customer):
                reminder = resolve_reminder(
                    [
                        ReminderRuleSpec(
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
                        for r in rules
                    ],
                    ReminderContext(
                        service_id=first.service.id,
                        category_id=first.service.category_id,
                        service_name=first.service.name,
                        customer_name=customer.first_name,
                        performed_at=to_datetime(appointment.date, appointment.end_min),
                        product_key=None,
                        recommended_repeat_days=first.service.recommended_repeat_days,
                        salon_name=salon.name if salon else None,
                        booking_url="/randevu",
                    ),
                    appointment.id,
                )

                if reminder:
                    # dedupe_key unique -> ayni randevu iki kez tamamlanirsa tek kayit.
                    exists = db.scalar(
                        select(ScheduledNotification.id).where(
                            ScheduledNotification.dedupe_key == reminder.dedupe_key
                        )
                    )
                    if not exists:
                        db.add(
                            ScheduledNotification(
                                customer_id=appointment.customer_id,
                                rule_id=reminder.rule_id,
                                channel=reminder.channel,
                                body=reminder.body,
                                due_at=reminder.due_at,
                                dedupe_key=reminder.dedupe_key,
                            )
                        )
                        reminder_queued = True

        db.commit()

        return {
            "id": appointment.id,
            "status": status,
            "version": new_version,
            "stock": stock,
            "loyalty": loyalty,
            "reminderQueued": reminder_queued,
            "freedSlot": freed_slot,
        }

    except Exception:
        db.rollback()
        raise
