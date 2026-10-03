"""
====================================================================
BITISIK BLOK BULMA (Contiguous Block Search)
====================================================================

Bir paketin takvime sigabilecegi baslangic saatlerini bulur. Uc boyut
AYNI ANDA degerlendirilir:

  1) Hizmet suresi   -> paketin kesintisiz ``total_min``lik blogu
  2) Usta musaitligi -> yalnizca paketin AKTIF dilimleri ustayi mesgul eder
  3) Kaynak/cihaz    -> kapasiteye gore doygunluk kontrolu

Kritik kural: 110 dakikalik bir paket, 60 dakikalik bir bosluga ASLA
onerilmez. Blok, calisma penceresi icinde TEK PARCA olarak yer almalidir
(``contained_in_any``).

Ters yonlu golge kullanimi: paketin KENDI pasif penceresi, mevcut baska
bir randevunun aktif calismasiyla cakisabilir (usta o sirada baska
musteriyle ilgilenir). Kontrol yalnizca ``layout.staff_busy`` dilimleri
uzerinden yapildigi icin bu kendiliginden desteklenir.

(``scheduling/availability.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..intervals import (
    Interval,
    Usage,
    contained_in_any,
    normalize,
    overlaps,
    overlaps_any,
    saturated_intervals,
    shift,
)
from ..time_utils import ceil_to_grid
from .types import ExternalShadowWindow, PackageLayout, ResourceCalendar, SlotCandidate

INF = float("inf")


@dataclass
class Diagnostics:
    required_min: int
    longest_free_window_min: int
    #: Paket, calisma penceresine hic sigmiyor mu?
    too_long_for_any_window: bool
    scanned_starts: int = 0
    reason: str | None = None


@dataclass
class AvailabilityResult:
    slots: list[SlotCandidate]
    diagnostics: Diagnostics
    #: Mesai icinde, izgaraya oturan ama paketin SIGMADIGI (dolu) baslangic
    #: dakikalari. Yalnizca saat bilgisi; musteri bilgisi tasimaz.
    busy_starts: list[int] = field(default_factory=list)


@dataclass
class AvailabilityInput:
    #: Sube saatleri kesisim personel calisma saatleri eksi izinler
    work_windows: Sequence[Interval]
    #: Mevcut randevularin ustayi MESGUL ettigi dilimler (pasif sureler HARIC)
    staff_busy: Sequence[Interval]
    layout: PackageLayout
    grid_minutes: int
    external_shadow_windows: Sequence[ExternalShadowWindow] = field(default_factory=tuple)
    resource_calendars: Sequence[ResourceCalendar] = field(default_factory=tuple)
    #: Bu dakikadan once baslayan slotlar elenir (bugun icin "su an")
    earliest_start_min: float = -INF
    #: Bu dakikadan sonra biten slotlar elenir
    latest_end_min: float = INF
    limit: int = 200


def find_available_slots(data: AvailabilityInput) -> AvailabilityResult:
    layout = data.layout
    work_windows = normalize(data.work_windows)
    staff_busy = normalize(data.staff_busy)
    external_shadow = list(data.external_shadow_windows)
    shadow_intervals = [w.interval for w in external_shadow]

    # Ustanin hic isi olmadigi (dolayisiyla paketin sigabilecegi) bosluklar.
    from ..intervals import subtract

    staff_free = subtract(work_windows, staff_busy)
    longest_free = int(max((w.end - w.start for w in staff_free), default=0))

    required = layout.total_min
    diagnostics = Diagnostics(
        required_min=required,
        longest_free_window_min=longest_free,
        too_long_for_any_window=all((w.end - w.start) < required for w in work_windows)
        if work_windows
        else True,
        scanned_starts=0,
    )

    if required <= 0:
        return AvailabilityResult([], diagnostics)

    # --- Kaynak doygunluk haritasi -------------------------------------
    # Her kaynak icin "yeni is alamayacagi" araliklar onceden hesaplanir.
    blocked_by_resource: dict[int, list[Interval]] = {}
    for cal in data.resource_calendars:
        blocked_by_resource[cal.resource_id] = saturated_intervals(
            [Usage(interval, qty) for interval, qty in cal.usages], cal.capacity
        )

    # Paketin misafir olarak yerlesebilmesi icin TUM hizmetlerin
    # shadow_guest_allowed olmasi gerekir.
    package_can_be_guest = bool(layout.items) and all(
        i.service.shadow_guest_allowed for i in layout.items
    )

    slots: list[SlotCandidate] = []
    busy_starts: list[int] = []

    for window in work_windows:
        start = ceil_to_grid(max(window.start, data.earliest_start_min), data.grid_minutes)

        while start + required <= window.end:
            block = Interval(start, start + required)
            if block.end > data.latest_end_min:
                break

            diagnostics.scanned_starts += 1

            # (1) Blok, calisma penceresi icinde TEK PARCA olmali.
            if not contained_in_any(block, work_windows):
                busy_starts.append(int(start))
                start += data.grid_minutes
                continue

            # (2) Paketin aktif dilimleri, ustanin mevcut isleriyle cakismamali.
            #     Paketin pasif dilimleri serbesttir - cakisabilir.
            shifted_busy = shift(layout.staff_busy, start)
            if any(overlaps_any(i, staff_busy) for i in shifted_busy):
                busy_starts.append(int(start))
                start += data.grid_minutes
                continue

            # (3) Kaynak kapasitesi
            resource_ok = True
            for usage in layout.resource_usage:
                blocked = blocked_by_resource.get(usage.resource_id)
                if not blocked:
                    continue
                probe = Interval(usage.interval.start + start, usage.interval.end + start)
                if overlaps_any(probe, blocked):
                    resource_ok = False
                    break
            if not resource_ok:
                busy_starts.append(int(start))
                start += data.grid_minutes
                continue

            # (4) Golge doldurma tespiti: paketin AKTIF calismasi mevcut bir
            #     randevunun pasif penceresine dusuyorsa bu bir "shadow fill"dir.
            host_window = next(
                (
                    w
                    for w in external_shadow
                    if any(overlaps(i, w.interval) for i in shifted_busy)
                ),
                None,
            )
            is_shadow_fill = host_window is not None or overlaps_any(block, shadow_intervals)

            if is_shadow_fill and not package_can_be_guest:
                busy_starts.append(int(start))
                start += data.grid_minutes
                continue

            slots.append(
                SlotCandidate(
                    start_min=int(block.start),
                    end_min=int(block.end),
                    is_shadow_fill=is_shadow_fill,
                    shadow_parent_appointment_id=host_window.appointment_id if host_window else None,
                )
            )

            if len(slots) >= data.limit:
                return AvailabilityResult(slots, diagnostics, busy_starts)

            start += data.grid_minutes

    return AvailabilityResult(slots, diagnostics, busy_starts)


def collect_shadow_windows(
    appointments: Sequence[dict],
    min_minutes: int = 15,
) -> list[ExternalShadowWindow]:
    """Mevcut randevulardan, baska musteriye acilabilecek pasif pencereler.

    ``min_minutes`` altindaki pencereler pratikte kullanilamaz.
    Her randevu sozlugu ``{id, staff_id, start_min, items:[...]}`` seklindedir.
    """
    out: list[ExternalShadowWindow] = []
    for appt in appointments:
        for item in appt["items"]:
            if not item["shadow_host_allowed"] or item["passive_min"] < min_minutes:
                continue
            start = appt["start_min"] + item["offset_min"] + item["active_before_min"]
            out.append(
                ExternalShadowWindow(
                    appointment_id=appt["id"],
                    staff_id=appt["staff_id"],
                    interval=Interval(start, start + item["passive_min"]),
                )
            )
    return out


def staff_busy_intervals_of(appointment: dict) -> list[Interval]:
    """Bir randevunun ustayi mesgul ettigi dilimler.

    Pasif (bekleme) sureleri DAHIL EDILMEZ - shadow blocking'in ozu budur.
    """
    out: list[Interval] = []
    for item in appointment["items"]:
        base = appointment["start_min"] + item["offset_min"]
        if item["active_before_min"] > 0:
            out.append(Interval(base, base + item["active_before_min"]))
        after_start = base + item["active_before_min"] + item["passive_min"]
        after_end = after_start + item["active_after_min"] + item["buffer_min"]
        if after_end > after_start:
            out.append(Interval(after_start, after_end))
    return normalize(out)
