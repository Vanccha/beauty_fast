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
                         + risk havuzuna COMPLETED + yenileme daveti (rebooking)
                         + ziyaret sonrasi mesaj (post_visit)

Tumu TEK transaction icindedir: "stok dustu ama puan yazilmadi" gibi
yarim durumlar olusamaz. ``version`` kontrolu optimistic locking saglar.

(``src/lib/server/appointment-status.ts`` karsiligi.)
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, selectinload

from ..core.loyalty import calculate_earned_points, tier_for
from ..core.risk_score import hash_phone
from ..errors import AppError, VersionConflictError
from ..models import (
    Appointment,
    AppointmentItem,
    Branch,
    Customer,
    InventoryItem,
    LoyaltyEntry,
    OccupancyCell,
    PhoneRiskEvent,
    Salon,
    ScheduledNotification,
    StockMovement,
)
from ..time_utils import now_local, to_datetime
from . import notification_worker, push
from .booking_cancellation import queue_cancellation_notices
from .catalog import get_exclusive_resource_ids
from . import deposit
from .manual_booking import (
    ConflictReport,
    existing_cells,
    find_conflicts,
    reclaim_cells,
    release_cells,
    sync_pre_reminder,
)
from .privacy import MARKETING_DEDUPE_PREFIX
from .post_visit import cancel_post_visit, queue_post_visit
from .rebooking import queue_rebooking
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
    notify: bool = True,
    cancel_reason: str | None = None,
    deposit_forfeit: bool = False,
) -> dict:
    """``notify=False``: iptal mesaji kuyruga yazilmaz (grup iptali kendi ozet
    mesajini yazar).

    Kapora (``services/deposit.py``): ``cancel_reason="DEPOSIT_UNPAID"`` ->
    kapora yatirilmadigi icin iptal (ozel mesaj, genel iptal mesajinin yerine).
    ``deposit_forfeit`` -> odenmis kapora iade edilmez ("kapora yanar").
    Odenmis kapora iptalde varsayilan olarak IADE BEKLIYOR (48 saat)."""
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
        deposit_values, deposit_mode = deposit.transition_on_status(
            appointment, status, now, forfeit=deposit_forfeit
        )
        updated = db.execute(
            stmt.values(status=status, version=Appointment.version + 1, **deposit_values)
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
        post_visit_queued = False

        # --- Iptal / gelmedi: slotu serbest birak -------------------------
        if status in ("CANCELLED", "NO_SHOW"):
            released = release_cells(db, appointment.id)
            reclaim_cells(db, released, exclude_ids=[appointment.id])
            freed_slot = True

            # Bekleyen "yarin randevunuz var" hatirlatmasi ve henuz gitmemis
            # "randevunuz olusturuldu" onayi iptal edilir.
            db.execute(
                update(ScheduledNotification)
                .where(
                    ScheduledNotification.dedupe_key.in_(
                        (
                            f"pre:{appointment.id}:24",
                            f"confirm:{appointment.id}",
                            f"{deposit.DEPOSIT_PREFIX}{appointment.id}",
                        )
                    ),
                    ScheduledNotification.status == "PENDING",
                )
                .values(status="CANCELLED")
            )

            # "Randevunuz iptal edildi" mesaji (NO_SHOW'a gitmez); ayni transaction.
            if status == "CANCELLED" and notify:
                mode = (
                    "UNPAID"
                    if (deposit_mode == "VOID" and cancel_reason == "DEPOSIT_UNPAID")
                    else ("REFUND" if deposit_mode == "REFUND" else None)
                )
                queue_cancellation_notices(db, appointment, mode)

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

            # --- Tekrar (yenileme) daveti: hizmet kurallari, onay sartli ----
            # KVKK / 6563: ticari ileti - onay yoksa kuyruga hic alinmaz.
            reminder_queued = queue_rebooking(db, appointment, customer, salon)

            # --- Ziyaret sonrasi tesekkur / puanlama mesaji -----------------
            post_visit_queued = queue_post_visit(db, appointment, customer, salon, now)

        # Gecerli durum COMPLETED degilse bekleyen ziyaret sonrasi mesaji geri cekilir.
        if status != "COMPLETED":
            cancel_post_visit(db, appointment.id)

        db.commit()
        if (status == "CANCELLED" and notify) or post_visit_queued:
            notification_worker.kick()

        # Panel cihazlarina Web Push (commit sonrasi, arka planda).
        if status == "CANCELLED":
            push.notify_cancelled(appointment.id)
        if stock and stock.get("lines"):
            push.notify_low_stock(
                [
                    (line["itemName"], line["remaining"], line["unit"])
                    for line in stock["lines"]
                    if line.get("crossedCritical")
                ]
            )

        return {
            "id": appointment.id,
            "status": status,
            "version": new_version,
            "stock": stock,
            "loyalty": loyalty,
            "reminderQueued": reminder_queued,
            "postVisitQueued": post_visit_queued,
            "freedSlot": freed_slot,
            "depositStatus": deposit_values.get("deposit_status", appointment.deposit_status),
        }

    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------------
# GERI ALMA (yonetici): son durumdaki randevuyu tekrar "Onaylandi" yap
# ---------------------------------------------------------------------


def _remove_risk_event(db: Session, phone: str, outcome: str, occurred_at: datetime) -> bool:
    """``change_appointment_status`` ile yazilan tek risk olayini siler."""
    event = db.scalar(
        select(PhoneRiskEvent)
        .where(
            PhoneRiskEvent.phone_hash == hash_phone(phone),
            PhoneRiskEvent.outcome == outcome,
            PhoneRiskEvent.occurred_at == occurred_at,
        )
        .order_by(PhoneRiskEvent.id.desc())
        .limit(1)
    )
    if event is None:
        return False
    db.delete(event)
    return True


def _restore_stock(db: Session, appointment_id: int) -> list[dict]:
    """Tamamlandi'da dusulen stogu geri koyar.

    ``UNIQUE(appointment_id, item_id)`` yuzunden orijinal hareket randevudan
    ayrilir (``appointment_id = NULL``, denetim icin saklanir) ve karsi
    hareket (``APPOINTMENT_REVERTED``) yazilir. Boylece randevu yeniden
    tamamlanirsa stok yeniden dusulebilir."""
    movements = db.scalars(
        select(StockMovement).where(
            StockMovement.appointment_id == appointment_id,
            StockMovement.reason == "APPOINTMENT_COMPLETED",
        )
    ).all()
    lines: list[dict] = []
    for mv in sorted(movements, key=lambda m: m.item_id):
        item = db.get(InventoryItem, mv.item_id, with_for_update=True, populate_existing=True)
        qty = -mv.delta
        item.quantity = round(item.quantity + qty, 4)
        mv.appointment_id = None
        mv.note = f"Geri alınan randevu #{appointment_id}"
        db.add(
            StockMovement(
                item_id=mv.item_id,
                delta=qty,
                reason="APPOINTMENT_REVERTED",
                note=f"Randevu #{appointment_id} tamamlandı işareti geri alındı",
            )
        )
        lines.append({"itemId": item.id, "itemName": item.name, "restored": qty, "unit": item.unit})
    db.flush()
    return lines


def revert_appointment_status(
    db: Session,
    appointment_id: int,
    expected_version: int | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> dict:
    """COMPLETED / NO_SHOW / CANCELLED -> CONFIRMED, yan etkileri tersine cevirerek.

      COMPLETED : sadakat puani (karsi defter satiri), stok, risk "COMPLETED"
                  olayi, bekleyen tekrar daveti ve ziyaret sonrasi mesaj geri alinir.
      NO_SHOW   : risk "NO_SHOW" olayi silinir; slot yeniden dolar.
      CANCELLED : risk "LATE_CANCEL" olayi silinir; bekleyen iptal mesaji geri
                  cekilir; slot yeniden dolar.

    NO_SHOW / CANCELLED'da slot artik baskasina verildiyse 409 ``SLOT_CONFLICT``
    (``force``: yonetici yine de geri alir, yalnizca bos hucreler yazilir).
    Tumu tek transaction'dadir."""
    now = now or now_local()
    try:
        appointment = db.scalar(
            select(Appointment)
            .options(
                selectinload(Appointment.items).selectinload(AppointmentItem.service),
                selectinload(Appointment.resources),
                selectinload(Appointment.customer),
            )
            .where(Appointment.id == appointment_id)
        )
        if appointment is None:
            raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)
        if expected_version is not None and appointment.version != expected_version:
            raise VersionConflictError(appointment.version)
        previous = appointment.status
        if previous not in TERMINAL:
            raise AppError("VALIDATION", "Bu randevu zaten aktif; geri alınacak bir durum yok.", 409)

        starts_at = to_datetime(appointment.date, appointment.start_min)
        report = ConflictReport([], set())
        cells = []

        # --- Slotu yeniden doldur (iptal / gelmedi slotu bosaltmisti) ------
        if previous in ("CANCELLED", "NO_SHOW"):
            cells = existing_cells(appointment, get_exclusive_resource_ids(db, appointment.branch_id))
            report = find_conflicts(
                db, cells=cells, date=appointment.date, exclude_appointment_id=appointment.id, now=now
            )
            if report.any and not force:
                raise AppError(
                    "SLOT_CONFLICT",
                    "Bu saat artık dolu; randevu geri alınamıyor. " + report.message(),
                    409,
                    {"conflicts": report.conflicts, "canForce": True},
                )

        stmt = update(Appointment).where(
            Appointment.id == appointment.id, Appointment.status == previous
        )
        if expected_version is not None:
            stmt = stmt.where(Appointment.version == expected_version)
        deposit_values, new_status, deposit_warning = deposit.revert_values(appointment, previous)
        if not db.execute(
            stmt.values(status=new_status, version=Appointment.version + 1, **deposit_values)
        ).rowcount:
            raise VersionConflictError(appointment.version)
        new_version = db.scalar(select(Appointment.version).where(Appointment.id == appointment.id))

        if cells:
            db.add_all(
                [
                    OccupancyCell(
                        owner_type=c.owner_type,
                        owner_id=c.owner_id,
                        date=c.date,
                        cell_index=c.cell_index,
                        kind="APPOINTMENT",
                        appointment_id=appointment.id,
                    )
                    for c in cells
                    if (c.owner_type, c.owner_id, c.cell_index) not in report.blocked
                ]
            )

        phone = appointment.customer.phone
        undone: dict = {}
        if deposit_warning:
            undone["depositWarning"] = deposit_warning

        if previous == "COMPLETED":
            # Sadakat: bu randevuya yazilmis tum satirlarin toplami kadar karsi satir.
            net = db.scalar(
                select(func.coalesce(func.sum(LoyaltyEntry.delta), 0.0)).where(
                    LoyaltyEntry.appointment_id == appointment.id
                )
            ) or 0.0
            if net:
                customer = db.get(
                    Customer, appointment.customer_id, with_for_update=True, populate_existing=True
                )
                db.add(
                    LoyaltyEntry(
                        customer_id=customer.id,
                        appointment_id=appointment.id,
                        delta=-net,
                        reason="MANUAL",
                        breakdown=json.dumps({"reverted": True, "reversedPoints": net}),
                    )
                )
                customer.loyalty_points = round(customer.loyalty_points - net, 2)
                customer.tier = tier_for(customer.loyalty_points)
            undone["loyaltyReversed"] = net
            undone["stock"] = _restore_stock(db, appointment.id)
            _remove_risk_event(db, phone, "COMPLETED", starts_at)
            # Bekleyen tekrar (yenileme) daveti ve ziyaret sonrasi mesaj geri cekilir.
            db.execute(
                update(ScheduledNotification)
                .where(
                    ScheduledNotification.dedupe_key.startswith(
                        f"{MARKETING_DEDUPE_PREFIX}{appointment.id}:"
                    ),
                    ScheduledNotification.status == "PENDING",
                )
                .values(status="CANCELLED")
            )
            cancel_post_visit(db, appointment.id)
        elif previous == "NO_SHOW":
            _remove_risk_event(db, phone, "NO_SHOW", starts_at)
        else:  # CANCELLED
            _remove_risk_event(db, phone, "LATE_CANCEL", starts_at)
            db.execute(
                update(ScheduledNotification)
                .where(
                    ScheduledNotification.dedupe_key.startswith(f"cancel:{appointment.id}:"),
                    ScheduledNotification.status == "PENDING",
                )
                .values(status="CANCELLED")
            )

        if previous in ("CANCELLED", "NO_SHOW") and new_status == "CONFIRMED":
            # Iptalde geri cekilen "yarin randevunuz var" hatirlatmasi yeniden kurulur.
            sync_pre_reminder(
                db,
                appointment,
                appointment.customer,
                [i.service.name for i in appointment.items if i.service is not None],
                now,
            )

        db.commit()
        return {
            "id": appointment.id,
            "status": new_status,
            "depositStatus": deposit_values.get("deposit_status", appointment.deposit_status),
            "previousStatus": previous,
            "version": new_version,
            "undone": undone,
            "forced": bool(force and report.any),
        }
    except Exception:
        db.rollback()
        raise
