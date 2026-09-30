"""Bitisik blok bulma: kesintisiz blok sarti, golge doldurma, kaynak kapasitesi."""

from __future__ import annotations

from app.core.availability import (
    AvailabilityInput,
    collect_shadow_windows,
    find_available_slots,
    staff_busy_intervals_of,
)
from app.core.package_layout import layout_package
from app.core.types import ExternalShadowWindow, ResourceCalendar, ResourceNeed, ServiceSpec
from app.intervals import Interval

PAKET_110 = [
    ServiceSpec(
        id=i, name=f"S{i}", active_before_min=mins, passive_min=0, active_after_min=0,
        buffer_min=0, shadow_host_allowed=False, shadow_guest_allowed=False, price=100,
    )
    for i, mins in ((1, 40), (2, 40), (3, 30))
]

KAS = ServiceSpec(
    id=9, name="Kaş Alma", active_before_min=15, passive_min=0, active_after_min=0,
    buffer_min=0, shadow_host_allowed=False, shadow_guest_allowed=True, price=150,
)


def _input(layout, work_windows, staff_busy=(), **kwargs) -> AvailabilityInput:
    return AvailabilityInput(
        work_windows=work_windows,
        staff_busy=staff_busy,
        layout=layout,
        grid_minutes=15,
        **kwargs,
    )


def test_110_minute_package_never_offered_for_60_minute_gap():
    """★ 110 dakikalik paket, 60 dakikalik bosluga ONERILMEZ."""
    layout = layout_package(PAKET_110)
    assert layout.total_min == 110

    result = find_available_slots(
        _input(layout, [Interval(540, 1200)], [Interval(600, 1200)])
    )
    # 540-600 arasi yalnizca 60 dakika -> hicbir slot yok.
    assert result.slots == []
    assert result.diagnostics.longest_free_window_min == 60
    assert result.diagnostics.required_min == 110


def test_package_is_not_split_across_two_windows():
    """Iki ayri 60 dakikalik bosluk, 110 dakikalik paketi TASIYAMAZ."""
    layout = layout_package(PAKET_110)
    result = find_available_slots(
        _input(layout, [Interval(540, 600), Interval(660, 720)])
    )
    assert result.slots == []


def test_slots_are_found_in_a_large_window():
    layout = layout_package(PAKET_110)
    result = find_available_slots(_input(layout, [Interval(540, 1200)]))
    assert result.slots
    assert result.slots[0].start_min == 540
    assert result.slots[0].end_min == 650
    # 15 dakikalik izgara
    assert result.slots[1].start_min == 555


def test_guest_service_fills_existing_shadow_window():
    """★ Kas alma, mevcut bir boyanin 40 dk'lik bekleme penceresine girer."""
    layout = layout_package([KAS])

    # Mevcut randevu: 10:00 boya (aktif 600-630, pasif 630-670, aktif 670-700)
    existing = {
        "id": 42,
        "staff_id": 1,
        "start_min": 600,
        "items": [
            {
                "offset_min": 0, "active_before_min": 30, "passive_min": 40,
                "active_after_min": 20, "buffer_min": 10, "shadow_host_allowed": True,
            }
        ],
    }
    staff_busy = staff_busy_intervals_of(existing)
    shadow = collect_shadow_windows([existing])

    assert staff_busy == [Interval(600, 630), Interval(670, 700)]
    assert shadow[0].interval == Interval(630, 670)

    result = find_available_slots(
        _input(
            layout,
            [Interval(540, 1200)],
            staff_busy,
            external_shadow_windows=shadow,
        )
    )
    fills = [s for s in result.slots if s.is_shadow_fill]
    assert fills, "gölge penceresine yerleşen slot bulunmalı"
    assert fills[0].start_min in (630, 645)
    assert fills[0].shadow_parent_appointment_id == 42


def test_non_guest_package_cannot_use_shadow_window():
    """shadow_guest_allowed=False paket, baskasinin bekleme penceresine giremez."""
    non_guest = ServiceSpec(
        id=10, name="Manikür", active_before_min=30, passive_min=0, active_after_min=0,
        buffer_min=0, shadow_host_allowed=False, shadow_guest_allowed=False, price=350,
    )
    layout = layout_package([non_guest])
    shadow = [ExternalShadowWindow(appointment_id=7, staff_id=1, interval=Interval(630, 670))]

    result = find_available_slots(
        _input(
            layout,
            [Interval(600, 700)],
            [Interval(600, 630), Interval(670, 700)],
            external_shadow_windows=shadow,
        )
    )
    assert result.slots == []


def test_saturated_resource_blocks_slot():
    service = ServiceSpec(
        id=11, name="Cilt Bakımı", active_before_min=60, passive_min=0, active_after_min=0,
        buffer_min=0, shadow_host_allowed=False, shadow_guest_allowed=False, price=900,
        resources=(ResourceNeed(5, 1, False),),
    )
    layout = layout_package([service])

    # Tek kapasiteli cihaz 09:00-12:00 arasi dolu.
    calendars = [
        ResourceCalendar(resource_id=5, capacity=1, usages=((Interval(540, 720), 1),))
    ]
    result = find_available_slots(
        _input(layout, [Interval(540, 780)], resource_calendars=calendars)
    )
    assert all(s.start_min >= 720 for s in result.slots)


def test_earliest_start_filters_past_slots():
    layout = layout_package([KAS])
    result = find_available_slots(
        _input(layout, [Interval(540, 1200)], earliest_start_min=700)
    )
    assert result.slots[0].start_min == 705  # 700 -> 15'lik izgaraya yuvarlanir
