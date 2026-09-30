"""
====================================================================
PAKET YERLESIMI (Package Layout)
====================================================================

Musteri birden cok hizmeti paket olarak sectiginde, bu paketin takvimde
kapladigi KESINTISIZ blogu ve bu blok icinde ustanin hangi dakikalarda
mesgul / serbest oldugunu hesaplar.

Her hizmet uc parcaya bolunur:

    |<-- activeBefore -->|<-- passive -->|<-- activeAfter -->|<-buffer->|
    ^ usta MESGUL         ^ usta SERBEST  ^ usta MESGUL        ^ MESGUL

--------------------------------------------------------------------
SIKISTIRMA (compaction)
--------------------------------------------------------------------
``compact=True`` iken, paketteki kisa ve "misafir olabilir" isaretli
hizmetler, ayni paketteki daha onceki bir hizmetin pasif penceresine
yerlestirilir:

    Sac boyasi (30 aktif + 40 bekleme + 20 aktif = 90 dk) + Kas alma (15 dk)
      Sirali  : 105 dk
      Sikisik :  90 dk   <- kas alma, boyanin 40 dk beklemesinde yapilir

Musteri 15 dakika erken cikar, salon 15 dakika kapasite kazanir. Kalan
25 dakikalik pencere hala DIS bir musteriye aciktir.

(``scheduling/package-layout.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..intervals import Interval, length, normalize, subtract
from .types import PackageLayout, PlacedItem, ResourceUsage, ServiceSpec


@dataclass(frozen=True)
class LayoutOptions:
    #: Paket ici sikistirmayi uygula
    compact: bool = True
    #: Personel hiz carpani. 0.9 => %10 daha hizli. Yalnizca AKTIF sureleri
    #: olcekler; kimyasal bekleme suresi (pasif) ustaya gore degismez.
    speed_factor: float = 1.0
    #: Bir golge penceresinin misafire acilabilmesi icin gereken en az sure
    min_shadow_window_min: int = 10


def _scale_active(value: int, factor: float) -> int:
    if value <= 0:
        return 0
    # 5 dakikalik hucre izgarasiyla uyumlu kalmasi icin 5'e yuvarlanir.
    return max(5, round(value * factor / 5) * 5)


def layout_package(
    services: Sequence[ServiceSpec],
    options: LayoutOptions | None = None,
) -> PackageLayout:
    """Hizmet listesini tek bir kesintisiz bloga yerlestirir.

    ``services`` musterinin sectigi SIRADA gelir; sira korunur. Ayni
    hizmetin listede birden fazla kez bulunmasi gecerlidir (bkz. README,
    "Hata 2") - her tekrar ayri bir kalem olarak yerlesir.
    """
    opts = options or LayoutOptions()

    if not services:
        return PackageLayout(
            total_min=0, staff_busy=[], shadow_windows=[], customer_busy=[],
            resource_usage=[], items=[], total_price=0.0, saved_min=0,
        )

    items: list[PlacedItem] = []
    resource_usage: list[ResourceUsage] = []
    staff_busy: list[Interval] = []
    #: Paket icinde acilan tum pasif pencereler (henuz doldurulmamis olabilir)
    host_windows: list[Interval] = []

    cursor = 0
    sequential_total = 0

    for index, service in enumerate(services):
        active_before = _scale_active(service.active_before_min, opts.speed_factor)
        active_after = _scale_active(service.active_after_min, opts.speed_factor)
        # Kimyasal/fiziksel bekleme suresi ustanin hizindan bagimsizdir.
        passive = max(0, service.passive_min)
        buffer = max(0, service.buffer_min)
        total = active_before + passive + active_after + buffer

        sequential_total += total

        offset: int | None = None
        placed_in_shadow = False

        # --- Sikistirma denemesi ---------------------------------------
        # Yalnizca kendi pasif suresi olmayan, "misafir olabilir" hizmetler
        # onceki bir hizmetin bekleme penceresine sokulabilir.
        if opts.compact and index > 0 and service.shadow_guest_allowed and passive == 0:
            free = subtract(host_windows, staff_busy)
            spot = next((f for f in free if length(f) >= total), None)
            if spot is not None:
                offset = int(spot.start)
                placed_in_shadow = True

        if offset is None:
            offset = cursor
            cursor = offset + total

        # --- Ustanin mesgul oldugu dilimler -----------------------------
        if active_before > 0:
            staff_busy.append(Interval(offset, offset + active_before))
        passive_start = offset + active_before
        passive_end = passive_start + passive
        if active_after > 0:
            staff_busy.append(Interval(passive_end, passive_end + active_after))
        if buffer > 0:
            staff_busy.append(
                Interval(passive_end + active_after, passive_end + active_after + buffer)
            )

        # --- Bu hizmetin actigi golge penceresi --------------------------
        if passive >= opts.min_shadow_window_min and service.shadow_host_allowed:
            host_windows.append(Interval(passive_start, passive_end))
            host_windows = normalize(host_windows)

        # --- Kaynak kullanimi --------------------------------------------
        for need in service.resources:
            if need.only_during_active:
                if active_before > 0:
                    resource_usage.append(
                        ResourceUsage(need.resource_id, need.quantity,
                                      Interval(offset, offset + active_before))
                    )
                if active_after > 0:
                    resource_usage.append(
                        ResourceUsage(need.resource_id, need.quantity,
                                      Interval(passive_end, passive_end + active_after))
                    )
            else:
                # Pasif sure dahil tum hizmet boyunca kaynak tutulur
                # (buffer dahil: temizlik de kaynagi mesgul eder).
                resource_usage.append(
                    ResourceUsage(need.resource_id, need.quantity,
                                  Interval(offset, offset + total))
                )

        items.append(
            PlacedItem(
                service=service,
                sort_order=index,
                offset_min=offset,
                active_before_min=active_before,
                passive_min=passive,
                active_after_min=active_after,
                buffer_min=buffer,
                price=service.price,
                placed_in_shadow=placed_in_shadow,
            )
        )

    total_min = cursor
    busy = normalize(staff_busy)

    # Sikistirmadan SONRA hala bos kalan pencereler dis misafire aciktir.
    remaining_shadow = [
        w for w in subtract(host_windows, busy) if length(w) >= opts.min_shadow_window_min
    ]

    return PackageLayout(
        total_min=total_min,
        staff_busy=busy,
        shadow_windows=remaining_shadow,
        customer_busy=[Interval(0, total_min)] if total_min > 0 else [],
        resource_usage=resource_usage,
        items=items,
        total_price=round(sum(i.price for i in items), 2),
        saved_min=max(0, sequential_total - total_min),
    )


def billable_minutes(layout: PackageLayout) -> int:
    """Paketin ucretlendirilebilir (buffer haric) suresi."""
    return sum(i.active_before_min + i.passive_min + i.active_after_min for i in layout.items)
