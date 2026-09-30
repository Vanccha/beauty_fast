"""
====================================================================
DOLULUK HUCRELERI
====================================================================

Zaman ``config.cell_minutes`` (5 dk) uzunlugunda hucrelere bolunur.
Bir randevu veya soft-lock, kapladigi HER hucre icin ``occupancy_cell``
tablosuna bir satir yazar. Tablodaki

    UNIQUE (owner_type, owner_id, date, cell_index)

kisiti sayesinde ayni ustanin (kaynagin / musterinin) ayni 5 dakikasina
ikinci bir kayit yazmak VERITABANI TARAFINDAN reddedilir. Boylece iki
eszamanli istekten yalnizca biri basarili olur - uygulama katmanindaki
"once kontrol et, sonra yaz" mantigina guvenilmez (TOCTOU acigi).

--------------------------------------------------------------------
SHADOW BLOCKING burada dogal olarak calisir
--------------------------------------------------------------------
Pasif (bekleme) sureler icin STAFF hucresi YAZILMAZ - usta o dakikalarda
serbesttir. Buna karsilik CUSTOMER hucreleri tum blok boyunca yazilir
(musteri salondadir) ve gerekiyorsa RESOURCE hucreleri de yazilir.

--------------------------------------------------------------------
Kapasiteli kaynaklar
--------------------------------------------------------------------
Hucre kisiti dogasi geregi "tekil sahiplik" ifade eder. Bu yuzden
yalnizca ``capacity == 1`` olan kaynaklar icin hucre yazilir; digerleri
sorgu zamaninda ``saturated_intervals`` ile korunur.

(``booking/occupancy.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

from ..config import config
from ..intervals import Interval, normalize
from .types import PackageLayout

OwnerType = Literal["STAFF", "RESOURCE", "CUSTOMER"]
CellKind = Literal["APPOINTMENT", "LOCK"]


@dataclass(frozen=True)
class CellSpec:
    owner_type: str
    owner_id: int
    date: str
    cell_index: int


def cell_indexes(interval: Interval, cell_minutes: int | None = None) -> list[int]:
    """Bir araligin kapsadigi hucre indeksleri.

    Kismi hucreler de talep edilir (temkinli davranis): 12 dk'lik bir
    aralik 3 hucre kaplar.
    """
    cm = cell_minutes or config.cell_minutes
    if interval.end <= interval.start:
        return []
    first = int(interval.start // cm)
    last = int(-(-interval.end // cm)) - 1  # ceil - 1
    return list(range(first, last + 1))


def cell_indexes_of_many(
    intervals: Sequence[Interval], cell_minutes: int | None = None
) -> list[int]:
    cm = cell_minutes or config.cell_minutes
    seen: set[int] = set()
    for i in normalize(intervals):
        seen.update(cell_indexes(i, cm))
    return sorted(seen)


def build_occupancy_cells(
    layout: PackageLayout,
    date: str,
    start_min: int,
    staff_id: int,
    customer_id: int | None = None,
    exclusive_resource_ids: Iterable[int] = (),
    cell_minutes: int | None = None,
) -> list[CellSpec]:
    """Bir paket yerlesiminin yazmasi gereken tum hucreleri uretir.

    Sonuc tekillestirilmistir (ayni hucre iki kez uretilmez).
    """
    cm = cell_minutes or config.cell_minutes
    exclusive = set(exclusive_resource_ids)

    seen: set[tuple[str, int, int]] = set()
    out: list[CellSpec] = []

    def push(owner_type: str, owner_id: int, indexes: Sequence[int]) -> None:
        for cell_index in indexes:
            key = (owner_type, owner_id, cell_index)
            if key in seen:
                continue
            seen.add(key)
            out.append(CellSpec(owner_type, owner_id, date, cell_index))

    # --- USTA: yalnizca AKTIF dilimler (pasif sure haric!) --------------
    staff_intervals = [Interval(i.start + start_min, i.end + start_min) for i in layout.staff_busy]
    push("STAFF", staff_id, cell_indexes_of_many(staff_intervals, cm))

    # --- MUSTERI: tum blok ----------------------------------------------
    if customer_id:
        push(
            "CUSTOMER",
            customer_id,
            cell_indexes(Interval(start_min, start_min + layout.total_min), cm),
        )

    # --- KAYNAK: yalnizca tekil (capacity == 1) kaynaklar ----------------
    by_resource: dict[int, list[Interval]] = {}
    for usage in layout.resource_usage:
        if usage.resource_id not in exclusive:
            continue
        by_resource.setdefault(usage.resource_id, []).append(
            Interval(usage.interval.start + start_min, usage.interval.end + start_min)
        )
    for resource_id, intervals in by_resource.items():
        push("RESOURCE", resource_id, cell_indexes_of_many(intervals, cm))

    return out


def cell_to_minute(cell_index: int, cell_minutes: int | None = None) -> int:
    return cell_index * (cell_minutes or config.cell_minutes)
