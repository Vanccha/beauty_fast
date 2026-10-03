"""Dolu saatler (``busySlots``): secilemez ama listede gorunur."""

from __future__ import annotations

from datetime import datetime

from app.core.availability import AvailabilityInput, find_available_slots
from app.core.package_layout import layout_package
from app.intervals import Interval
from app.services.availability import compute_availability
from app.services.soft_lock import acquire_slot_lock
from app.time_utils import add_days_to_key, now_local, to_date_key

from .conftest import spec_of

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)


def _starts(staff: dict, key: str) -> list[int]:
    return [s["startMin"] for s in staff[key]]


def test_engine_busy_starts_cover_blocked_grid_times():
    from .test_availability import KAS

    layout = layout_package([KAS])  # 15 dk
    result = find_available_slots(
        AvailabilityInput(
            work_windows=[Interval(540, 660)],
            staff_busy=[Interval(570, 600)],
            layout=layout,
            grid_minutes=15,
        )
    )
    free = {s.start_min for s in result.slots}
    assert result.busy_starts == [570, 585]
    assert not free & set(result.busy_starts)
    assert free | set(result.busy_starts) == set(range(540, 660, 15))


def test_lock_shows_as_busy_and_not_available(salon, db):
    layout = layout_package([spec_of(salon["manikur"])])
    acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="baska", date=TOMORROW, start_min=600, layout=layout,
    )
    result = compute_availability(
        db, date=TOMORROW, service_ids=[salon["manikur"].id],
        staff_id=salon["staff_a"].id, viewer_key="ben",
    )
    staff = result["staff"][0]
    busy = _starts(staff, "busySlots")
    free = _starts(staff, "slots")
    assert 600 in busy
    assert 600 not in free
    assert not set(busy) & set(free)
    # Yalnizca saat bilgisi: musteri verisi yok.
    assert set(staff["busySlots"][0]) == {"startMin", "label"}
    # Kendi kilidin dolu sayilmaz.
    own = compute_availability(
        db, date=TOMORROW, service_ids=[salon["manikur"].id],
        staff_id=salon["staff_a"].id, viewer_key="baska",
    )["staff"][0]
    assert 600 not in _starts(own, "busySlots")


def test_past_times_today_are_not_listed(salon, db):
    today = to_date_key(now_local())
    now = datetime.fromisoformat(f"{today}T14:00:00")
    result = compute_availability(
        db, date=today, service_ids=[salon["manikur"].id],
        staff_id=salon["staff_a"].id, now=now,
    )
    staff = result["staff"][0]
    earliest = 14 * 60 + 15
    assert all(m >= earliest for m in _starts(staff, "slots"))
    assert all(m >= earliest for m in _starts(staff, "busySlots"))
