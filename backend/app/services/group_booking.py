"""
====================================================================
GRUP RANDEVUSU - ortak saat bulma
====================================================================

Her kisi icin motorun (``compute_availability``) uretdigi slotlar
alinir; hepsinin AYNI baslangic dakikasinda, FARKLI ustalarla
baslayabildigi saatler aranir (geri izlemeli arama).

Kaynak cakismasi: iki kisi ayni tekil (kapasite=1) kaynagi (orn. tek
koltuk) ayni anda kullanamaz. Aday atamanin hucreleri bellekte
``build_occupancy_cells`` ile uretilir ve RESOURCE hucreleri kesismiyorsa
atama gecerli sayilir. (Veritabani ayni kisiti kilit/onay aninda zaten
unique kisitiyla yakalar; burada amac imkansiz saati HIC onermemek.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.orm import Session

from ..core.occupancy import build_occupancy_cells
from ..core.package_layout import LayoutOptions, layout_package
from ..core.types import PackageLayout
from ..time_utils import add_days_to_key, now_local, to_date_key
from .availability import compute_availability
from .catalog import get_default_branch, get_exclusive_resource_ids, load_service_specs

MAX_OPTIONS = 40
SUGGEST_DAYS = 7


@dataclass(frozen=True)
class PersonQuery:
    service_ids: tuple[int, ...]
    staff_id: int | None


@dataclass
class _StaffSlots:
    staff_id: int
    staff_name: str
    speed_factor: float
    total_min: int
    total_price: float
    starts: dict[int, int]  # startMin -> endMin


def _staff_slots(
    db: Session, date: str, query: PersonQuery, viewer_key: str | None, cache: dict
) -> list[_StaffSlots]:
    key = (date, query)
    if key in cache:
        return cache[key]
    result = compute_availability(
        db,
        date=date,
        service_ids=list(query.service_ids),
        staff_id=query.staff_id,
        limit_per_staff=500,
        viewer_key=viewer_key,
    )
    out = [
        _StaffSlots(
            staff_id=s["staffId"],
            staff_name=s["staffName"],
            speed_factor=s["speedFactor"],
            total_min=s["totalMin"],
            total_price=s["totalPrice"],
            starts={slot["startMin"]: slot["endMin"] for slot in s["slots"]},
        )
        for s in result["staff"]
        if s["slots"]
    ]
    cache[key] = out
    return out


def find_group_options(
    db: Session,
    date: str,
    people: Sequence[PersonQuery],
    viewer_key: str | None = None,
    limit: int = MAX_OPTIONS,
    cache: dict | None = None,
) -> list[dict]:
    """Ortak saatler: her biri icin kisi basina somut (farkli) usta atamasi."""
    cache = cache if cache is not None else {}
    branch = get_default_branch(db)
    exclusive = get_exclusive_resource_ids(db, branch.id)

    per_person = [_staff_slots(db, date, p, viewer_key, cache) for p in people]
    if any(not options for options in per_person):
        return []

    # Aday baslangiclar: her kisinin (herhangi bir usta ile) baslayabildigi saatlerin kesisimi.
    candidates: set[int] | None = None
    for options in per_person:
        starts = {m for o in options for m in o.starts}
        candidates = starts if candidates is None else candidates & starts
    if not candidates:
        return []

    layout_cache: dict[tuple[int, int], PackageLayout] = {}

    def layout_of(i: int, option: _StaffSlots) -> PackageLayout:
        k = (i, option.staff_id)
        if k not in layout_cache:
            specs = load_service_specs(db, list(people[i].service_ids))
            layout_cache[k] = layout_package(specs, LayoutOptions(speed_factor=option.speed_factor))
        return layout_cache[k]

    def resource_cells(i: int, option: _StaffSlots, start: int) -> set[tuple[int, int]]:
        if not exclusive:
            return set()
        cells = build_occupancy_cells(
            layout=layout_of(i, option),
            date=date,
            start_min=start,
            staff_id=option.staff_id,
            customer_id=None,
            exclusive_resource_ids=exclusive,
        )
        return {(c.owner_id, c.cell_index) for c in cells if c.owner_type == "RESOURCE"}

    def assign(start: int, i: int, used_staff: set[int], used_res: set, chosen: list) -> bool:
        if i == len(people):
            return True
        for option in per_person[i]:
            if option.staff_id in used_staff or start not in option.starts:
                continue
            cells = resource_cells(i, option, start)
            if cells & used_res:
                continue
            chosen.append(option)
            if assign(start, i + 1, used_staff | {option.staff_id}, used_res | cells, chosen):
                return True
            chosen.pop()
        return False

    options_out: list[dict] = []
    for start in sorted(candidates):
        chosen: list[_StaffSlots] = []
        if not assign(start, 0, set(), set(), chosen):
            continue
        options_out.append(
            {
                "startMin": start,
                "assignments": [
                    {
                        "personIndex": i,
                        "staffId": o.staff_id,
                        "staffName": o.staff_name,
                        "startMin": start,
                        "endMin": o.starts[start],
                        "totalMin": o.total_min,
                        "totalPrice": o.total_price,
                    }
                    for i, o in enumerate(chosen)
                ],
            }
        )
        if len(options_out) >= limit:
            break
    return options_out


def suggest_dates(
    db: Session, date: str, people: Sequence[PersonQuery], viewer_key: str | None, cache: dict
) -> list[dict]:
    """Ortak saat bulunamayinca sonraki 7 gunde ortak saati olan gunler."""
    today = to_date_key(now_local())
    out: list[dict] = []
    for offset in range(1, SUGGEST_DAYS + 1):
        day = add_days_to_key(date, offset)
        if day < today:
            continue
        count = len(
            find_group_options(db, day, people, viewer_key, limit=MAX_OPTIONS, cache=cache)
        )
        if count:
            out.append({"date": day, "optionCount": count})
    return out
