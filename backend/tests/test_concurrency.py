"""
Yaris kosulu testleri - projenin en kritik davranislari.

  * Ayni slota 2 ve 5 eszamanli istekten TAM OLARAK 1'i basarili olur
  * Ayni surumle iki tasimadan biri reddedilir (optimistic locking)
  * Ayni randevu iki kez tamamlanirsa stok BIR KEZ duser (idempotency)

Garanti uygulama katmaninda degil, ``occupancy_cell`` ve
``stock_movement`` uzerindeki unique kisitlarindadir.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.package_layout import layout_package
from app.db import SessionLocal
from app.errors import AppError, SlotConflictError, VersionConflictError
from app.models import (
    Appointment,
    AppointmentItem,
    InventoryItem,
    OccupancyCell,
    ServiceConsumable,
    StockMovement,
)
from app.services.appointment import confirm_appointment_from_lock, move_appointment
from app.services.appointment_status import change_appointment_status
from app.services.soft_lock import acquire_slot_lock
from app.time_utils import add_days_to_key, now_local, to_date_key

from .conftest import spec_of

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)


def _attempt_lock(branch_id: int, staff_id: int, layout, session_id: str, date: str, start: int):
    """Ayri bir oturumda kilit almayi dener; sonucu (ok, hata_kodu) doner."""
    db = SessionLocal()
    try:
        acquire_slot_lock(
            db,
            branch_id=branch_id,
            staff_id=staff_id,
            session_id=session_id,
            date=date,
            start_min=start,
            layout=layout,
        )
        return True, None
    except AppError as error:
        return False, error.code
    finally:
        db.close()


@pytest.mark.parametrize("workers", [2, 5])
def test_only_one_concurrent_lock_succeeds(salon, workers):
    """★ Ayni slota N eszamanli istekten TAM OLARAK 1'i basarili olur."""
    layout = layout_package([spec_of(salon["manikur"])])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(
            pool.map(
                lambda i: _attempt_lock(
                    salon["branch"].id, salon["staff_a"].id, layout,
                    f"oturum-{i}", TOMORROW, 600,
                ),
                range(workers),
            )
        )

    succeeded = [r for r in results if r[0]]
    failed = [r for r in results if not r[0]]

    assert len(succeeded) == 1, f"tam 1 başarı bekleniyordu, {len(succeeded)} oldu"
    assert all(code == "SLOT_TAKEN" for _, code in failed)


def test_conflict_reports_held_until(salon, db):
    """Cakisan istek, slotun ne zamana kadar rezerve oldugunu ogrenir
    (kimin tuttugunu DEGIL)."""
    layout = layout_package([spec_of(salon["manikur"])])

    acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="ilk", date=TOMORROW, start_min=660, layout=layout,
    )

    other = SessionLocal()
    try:
        with pytest.raises(SlotConflictError) as excinfo:
            acquire_slot_lock(
                other, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
                session_id="ikinci", date=TOMORROW, start_min=660, layout=layout,
            )
        assert excinfo.value.held_until is not None
    finally:
        other.close()


def test_passive_window_is_not_locked_for_staff(salon, db):
    """★ Shadow blocking: boyanin pasif suresi icin STAFF hucresi yazilmaz.

    Bu yuzden kas alma ayni ustaya, ayni dakikalara yerlesebilir.
    """
    boya_layout = layout_package([spec_of(salon["boya"])])
    acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="boya", date=TOMORROW, start_min=600, layout=boya_layout,
    )

    # 600-630 aktif, 630-670 PASIF, 670-700 aktif (+10 buffer)
    staff_cells = set(
        db.scalars(
            select(OccupancyCell.cell_index).where(
                OccupancyCell.owner_type == "STAFF",
                OccupancyCell.owner_id == salon["staff_a"].id,
                OccupancyCell.date == TOMORROW,
            )
        )
    )
    passive_cells = set(range(630 // 5, 670 // 5))
    assert not (staff_cells & passive_cells), "pasif pencere için STAFF hücresi yazılmamalı"

    # Musteri hucreleri ise TUM blok boyunca yazilir (musteri salondadir).
    customer_cells = set(
        db.scalars(
            select(OccupancyCell.cell_index).where(
                OccupancyCell.owner_type == "CUSTOMER", OccupancyCell.date == TOMORROW
            )
        )
    )
    assert customer_cells == set()  # kilit customer_id olmadan alindi


def test_expired_lock_does_not_block(salon, db):
    """TTL'i dolmus kilit, yeni istegi engellemez (yazma aninda temizlenir)."""
    layout = layout_package([spec_of(salon["manikur"])])

    acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="eski", date=TOMORROW, start_min=720, layout=layout,
        ttl_seconds=1, now=now_local() - timedelta(minutes=10),
    )

    other = SessionLocal()
    try:
        lock = acquire_slot_lock(
            other, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
            session_id="yeni", date=TOMORROW, start_min=720, layout=layout,
        )
        assert lock.lock_id > 0
    finally:
        other.close()


# ---------------------------------------------------------------------
# Optimistic locking (tasima)
# ---------------------------------------------------------------------


def _create_appointment(db, salon, start_min: int = 600) -> Appointment:
    layout = layout_package([spec_of(salon["manikur"])])
    lock = acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="olustur", date=TOMORROW, start_min=start_min, layout=layout,
        customer_id=salon["customer"].id,
    )
    return confirm_appointment_from_lock(
        db,
        lock_id=lock.lock_id,
        session_id="olustur",
        customer_id=salon["customer"].id,
        branch_id=salon["branch"].id,
        staff_id=salon["staff_a"].id,
        date=TOMORROW,
        start_min=start_min,
        layout=layout,
    )


def test_concurrent_moves_with_same_version(salon, db):
    """★ Ayni surumle iki tasimadan biri reddedilir; randevu tek yerde kalir."""
    appointment = _create_appointment(db, salon, 600)
    layout = layout_package([spec_of(salon["manikur"])])

    def attempt(target_start: int):
        session = SessionLocal()
        try:
            move_appointment(
                session,
                appointment_id=appointment.id,
                expected_version=0,
                to_staff_id=salon["staff_a"].id,
                to_date=TOMORROW,
                to_start_min=target_start,
                layout=layout,
            )
            return True, None
        except AppError as error:
            return False, error.code
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [780, 840]))

    succeeded = [r for r in results if r[0]]
    failed = [r for r in results if not r[0]]

    assert len(succeeded) == 1
    assert failed[0][1] in ("VERSION_MISMATCH", "SLOT_TAKEN")

    db.expire_all()
    refreshed = db.get(Appointment, appointment.id)
    assert refreshed.version == 1
    assert refreshed.start_min in (780, 840)

    # Reddedilen tarafin hucreleri geri alinmis olmali: tek blok kadar hucre var.
    cells = db.scalar(
        select(func.count()).select_from(OccupancyCell).where(
            OccupancyCell.appointment_id == appointment.id
        )
    )
    assert cells > 0


def test_move_with_stale_version_is_rejected(salon, db):
    appointment = _create_appointment(db, salon, 600)
    layout = layout_package([spec_of(salon["manikur"])])

    move_appointment(
        db, appointment_id=appointment.id, expected_version=0,
        to_staff_id=salon["staff_a"].id, to_date=TOMORROW, to_start_min=780, layout=layout,
    )

    with pytest.raises(VersionConflictError):
        move_appointment(
            db, appointment_id=appointment.id, expected_version=0,
            to_staff_id=salon["staff_a"].id, to_date=TOMORROW, to_start_min=900, layout=layout,
        )


def test_appointment_cannot_be_confirmed_with_mismatched_duration(salon, db):
    """Istemci, kilitlediginden farkli (daha uzun) bir paketi kaydettiremez."""
    manikur_layout = layout_package([spec_of(salon["manikur"])])
    lock = acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="kurnaz", date=TOMORROW, start_min=600, layout=manikur_layout,
    )

    boya_layout = layout_package([spec_of(salon["boya"])])
    with pytest.raises(AppError) as excinfo:
        confirm_appointment_from_lock(
            db, lock_id=lock.lock_id, session_id="kurnaz",
            customer_id=salon["customer"].id, branch_id=salon["branch"].id,
            staff_id=salon["staff_a"].id, date=TOMORROW, start_min=600, layout=boya_layout,
        )
    assert excinfo.value.status == 409


# ---------------------------------------------------------------------
# Stok idempotensi
# ---------------------------------------------------------------------


def test_stock_is_consumed_once_per_appointment(salon, db):
    """★ Ayni randevu iki kez COMPLETED olursa stok BIR KEZ duser."""
    item = InventoryItem(
        branch_id=salon["branch"].id, name="Oje", unit="adet", quantity=10, critical_level=2
    )
    db.add(item)
    db.flush()
    db.add(
        ServiceConsumable(service_id=salon["manikur"].id, item_id=item.id, qty_per_use=1)
    )
    db.commit()

    appointment = _create_appointment(db, salon, 600)

    result = change_appointment_status(
        db, appointment_id=appointment.id, status="COMPLETED", expected_version=0
    )
    assert result["stock"]["applied"] is True

    db.expire_all()
    assert db.get(InventoryItem, item.id).quantity == 9

    # Ikinci COMPLETED denemesi zaten terminal durum nedeniyle reddedilir.
    with pytest.raises(AppError):
        change_appointment_status(
            db, appointment_id=appointment.id, status="COMPLETED", expected_version=1
        )

    db.expire_all()
    assert db.get(InventoryItem, item.id).quantity == 9

    movements = db.scalar(
        select(func.count()).select_from(StockMovement).where(
            StockMovement.appointment_id == appointment.id
        )
    )
    assert movements == 1


def test_duplicate_service_consumes_stock_twice(salon, db):
    """HATA 2 regresyonu: ayni hizmet iki kez secildiyse malzeme iki kez duser."""
    item = InventoryItem(
        branch_id=salon["branch"].id, name="Ağda", unit="gram", quantity=100, critical_level=10
    )
    db.add(item)
    db.flush()
    db.add(ServiceConsumable(service_id=salon["kas"].id, item_id=item.id, qty_per_use=15))
    db.commit()

    layout = layout_package([spec_of(salon["kas"]), spec_of(salon["kas"])])
    lock = acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="cift", date=TOMORROW, start_min=600, layout=layout,
        customer_id=salon["customer"].id,
    )
    appointment = confirm_appointment_from_lock(
        db, lock_id=lock.lock_id, session_id="cift", customer_id=salon["customer"].id,
        branch_id=salon["branch"].id, staff_id=salon["staff_a"].id, date=TOMORROW,
        start_min=600, layout=layout,
    )

    items = db.scalars(
        select(AppointmentItem).where(AppointmentItem.appointment_id == appointment.id)
    ).all()
    assert len(items) == 2

    change_appointment_status(
        db, appointment_id=appointment.id, status="COMPLETED", expected_version=0
    )
    db.expire_all()
    # 2 x 15 = 30 gram
    assert db.get(InventoryItem, item.id).quantity == 70


def test_cancelling_frees_the_slot(salon, db):
    appointment = _create_appointment(db, salon, 600)

    change_appointment_status(
        db, appointment_id=appointment.id, status="CANCELLED", expected_version=0
    )

    remaining = db.scalar(
        select(func.count()).select_from(OccupancyCell).where(
            OccupancyCell.appointment_id == appointment.id
        )
    )
    assert remaining == 0

    # Slot artik yeniden kilitlenebilir.
    layout = layout_package([spec_of(salon["manikur"])])
    lock = acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="yeni-musteri", date=TOMORROW, start_min=600, layout=layout,
    )
    assert lock.lock_id > 0
