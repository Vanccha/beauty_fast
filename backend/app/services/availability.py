"""
====================================================================
MUSAITLIK SORGUSU - motorun veritabaniyla bulustugu yer
====================================================================

Saf zamanlama motoru (``core.availability.find_available_slots``) hicbir
sey okumaz; butun girdileri burada toplanir:

    work_windows           = sube saatleri ∩ personel mesaisi − izinler
    staff_busy             = mevcut randevularin AKTIF dilimleri
                             + suresi dolmamis soft-lock hucreleri
    external_shadow_windows= mevcut randevularin misafire acik pasif pencereleri
    resource_calendars     = kaynaklarin o gunku kullanimi (kapasite ile)

Ayrica her slota firsat-saati indirimi (Bayes shrinkage) ve gercek
goruntulenme sayisi (uydurma degil, ``slot_view_event`` sayimi) iliştirilir.

--------------------------------------------------------------------
HATA DUZELTMESI 1 - "kendi kilidin seni engelliyor"
--------------------------------------------------------------------
Next.js surumunde bu fonksiyon ziyaretciyi hic tanimiyordu
(``src/lib/server/availability.ts:230-268``): suresi dolmamis TUM LOCK
hucreleri "mesgul" sayiliyordu, kilidi tutan oturumun kendisi dahil.

Sonuc: kullanici "Bu saati tut" deyip 4. adima gectikten sonra "Geri"ye
basarsa (arayuzdeki geri dugmesi kilidi serbest birakmiyor -
``booking-flow.tsx:760``), saat listesi yeniden yuklendiginde KENDI
tuttugu saat listeden kayboluyordu. Kullanicinin gordugu sey sudur:
"hizmeti/saati bir kez sectim, olmadi; bastan secmem gerekti."

Duzeltme: ``viewer_key`` (ziyaretci cerezi) parametre olarak alinir ve o
oturuma ait kilitler mesgul kumesinden CIKARILIR. Kullanici kendi
tuttugu saati gormeye devam eder; ``your_lock`` alani arayuze "bu saat
zaten senin icin tutuluyor" demesi icin geri doner. Baskalarinin
kilitleri eskisi gibi engelleyicidir.

--------------------------------------------------------------------
HATA DUZELTMESI 3 - paket ozeti hangi ustaya ait?
--------------------------------------------------------------------
Next.js surumu ``package`` ozetini ILK uygun personelin hiz carpaniyla
hesaplayip tum listeye o degeri basiyordu; musteri daha yavas bir usta
secerse ekranda yazan sure (orn. 110 dk) ile kilitlenen sure (125 dk)
ayrisiyordu. Burada:

  * ``staff_id`` verilmisse ozet DOGRUDAN o personele gore hesaplanir,
  * verilmemisse nominal (speed_factor = 1.0) ozet dondurulur ve her
    personel kendi ``totalMin`` / ``savedMin`` degerini tasir.
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import config
from ..core.availability import (
    AvailabilityInput,
    collect_shadow_windows,
    find_available_slots,
    staff_busy_intervals_of,
)
from ..core.opportunity import OccupancySample, score_day
from ..core.package_layout import LayoutOptions, layout_package
from ..core.recommendation import suggest_shadow_fillers
from ..core.types import PackageLayout, ResourceCalendar
from ..intervals import Interval, intersect, normalize, subtract
from ..models import (
    Appointment,
    AppointmentItem,
    AppointmentResource,
    OccupancyCell,
    OccupancyStat,
    Resource,
    Service,
    SlotLock,
    SlotViewEvent,
    TimeOff,
)
from ..time_utils import minutes_to_label, now_local, now_parts, weekday_of
from .catalog import (
    find_capable_staff,
    get_default_branch,
    load_service_specs,
    staff_speed_factor_for,
)

APPOINTMENT_ACTIVE_STATUSES = ("PENDING", "CONFIRMED", "COMPLETED")

INF = float("inf")


def _build_work_windows(
    branch_open: int,
    branch_close: int,
    working_hour,
    time_off: Sequence[TimeOff],
) -> list[Interval]:
    """Sube acilis/kapanis ∩ personel mesaisi − izinler."""
    if working_hour is None or not working_hour.is_working:
        return []

    base = intersect(
        [Interval(branch_open, branch_close)],
        [Interval(working_hour.start_min, working_hour.end_min)],
    )

    cuts = [
        # start_min None ise TUM GUN izinli
        Interval(0, 1440) if t.start_min is None or t.end_min is None
        else Interval(t.start_min, t.end_min)
        for t in time_off
    ]

    return subtract(base, cuts)


def _lock_intervals_from_cells(cell_indexes: Sequence[int]) -> list[Interval]:
    cm = config.cell_minutes
    return normalize([Interval(i * cm, (i + 1) * cm) for i in cell_indexes])


def compute_availability(
    db: Session,
    date: str,
    service_ids: Sequence[int],
    staff_id: int | None = None,
    limit_per_staff: int = 60,
    viewer_key: str | None = None,
    now: datetime | None = None,
    ignore_locks: bool = False,
) -> dict:
    """``ignore_locks=True``: soft-lock hucreleri hic hesaba katilmaz.
    Kilit ucu bunu "bu saat YAPISAL olarak gecerli mi" (mesai, randevular,
    kaynaklar, gecmis saat) sorusu icin kullanir; kilit cakismasini ise
    veritabani unique kisiti yakalar."""
    now = now or now_local()
    branch = get_default_branch(db)
    weekday = weekday_of(date)

    specs = load_service_specs(db, service_ids)

    # "Bugun" ise gecmis saatler elenir; ayrica hazirlik icin kucuk bir pay.
    today_key, today_minute = now_parts(now)
    earliest_start_min = (today_minute + 15) if date == today_key else -INF

    capable = find_capable_staff(db, branch.id, service_ids)
    if staff_id:
        capable = [s for s in capable if s.id == staff_id]

    # --- Ortak (personelden bagimsiz) veri ------------------------------
    needed_resource_ids = sorted({r.resource_id for s in specs for r in s.resources})

    resource_rows = (
        db.execute(
            select(Resource.id, Resource.capacity).where(Resource.id.in_(needed_resource_ids))
        ).all()
        if needed_resource_ids
        else []
    )

    resource_usage_rows = (
        db.execute(
            select(
                AppointmentResource.resource_id,
                AppointmentResource.start_min,
                AppointmentResource.end_min,
                AppointmentResource.quantity,
            )
            .join(Appointment, Appointment.id == AppointmentResource.appointment_id)
            .where(
                AppointmentResource.resource_id.in_(needed_resource_ids),
                Appointment.date == date,
                Appointment.status.in_(APPOINTMENT_ACTIVE_STATUSES),
            )
        ).all()
        if needed_resource_ids
        else []
    )

    stat_rows = db.scalars(
        select(OccupancyStat).where(
            OccupancyStat.branch_id == branch.id, OccupancyStat.weekday == weekday
        )
    ).all()

    view_rows = db.execute(
        select(SlotViewEvent.staff_id, SlotViewEvent.start_min, SlotViewEvent.viewer_key).where(
            SlotViewEvent.branch_id == branch.id, SlotViewEvent.date == date
        )
    ).all()

    resource_calendars = [
        ResourceCalendar(
            resource_id=rid,
            capacity=capacity,
            usages=tuple(
                (Interval(u.start_min, u.end_min), u.quantity)
                for u in resource_usage_rows
                if u.resource_id == rid
            ),
        )
        for rid, capacity in resource_rows
    ]

    # --- Firsat saati skorlari (saat basi kovalar) ----------------------
    hour_slots = list(range(branch.open_minute, branch.close_minute, 60))
    opportunity_by_hour = score_day(
        weekday,
        hour_slots,
        [
            OccupancySample(s.weekday, s.slot_min, s.occupancy, s.sample_size)
            for s in stat_rows
        ],
    )

    # --- Gercek goruntulenme sayilari (tekil ziyaretci) ------------------
    view_counts: dict[tuple[int, int], set[str]] = {}
    for v in view_rows:
        view_counts.setdefault((v.staff_id, v.start_min), set()).add(v.viewer_key)

    # --- Ziyaretcinin KENDI kilitleri (Hata duzeltmesi 1) ---------------
    own_lock_ids: set[int] = set()
    your_lock: dict | None = None
    if viewer_key:
        own_locks = db.scalars(
            select(SlotLock).where(
                SlotLock.session_id == viewer_key,
                SlotLock.date == date,
                SlotLock.consumed_at.is_(None),
                SlotLock.expires_at > now,
            )
        ).all()
        own_lock_ids = {lock.id for lock in own_locks}
        if own_locks:
            lock = own_locks[0]
            your_lock = {
                "lockId": lock.id,
                "staffId": lock.staff_id,
                "date": lock.date,
                "startMin": lock.start_min,
                "endMin": lock.end_min,
                "startLabel": minutes_to_label(lock.start_min),
                "endLabel": minutes_to_label(lock.end_min),
                "expiresAt": lock.expires_at.isoformat(),
            }

    # --- Personel bazli tarama ------------------------------------------
    staff_results: list[dict] = []
    reference_layout: PackageLayout | None = None

    for staff in capable:
        speed_factor = staff_speed_factor_for(staff, service_ids)
        layout = layout_package(specs, LayoutOptions(speed_factor=speed_factor))
        if reference_layout is None:
            reference_layout = layout

        appointments = db.scalars(
            select(Appointment)
            .options(selectinload(Appointment.items).selectinload(AppointmentItem.service))
            .where(
                Appointment.staff_id == staff.id,
                Appointment.date == date,
                Appointment.status.in_(APPOINTMENT_ACTIVE_STATUSES),
            )
        ).all()

        time_off = db.scalars(
            select(TimeOff).where(TimeOff.staff_id == staff.id, TimeOff.date == date)
        ).all()

        lock_cell_query = select(OccupancyCell.cell_index).where(
            OccupancyCell.owner_type == "STAFF",
            OccupancyCell.owner_id == staff.id,
            OccupancyCell.date == date,
            OccupancyCell.kind == "LOCK",
            OccupancyCell.expires_at > now,
        )
        if own_lock_ids:
            # Kendi kilidin seni engellemesin.
            lock_cell_query = lock_cell_query.where(
                OccupancyCell.lock_id.notin_(own_lock_ids)
            )
        lock_cells = [] if ignore_locks else list(db.scalars(lock_cell_query))

        working_hour = next((w for w in staff.working_hours if w.weekday == weekday), None)
        work_windows = _build_work_windows(
            branch.open_minute, branch.close_minute, working_hour, time_off
        )

        appointment_dicts = [
            {
                "id": a.id,
                "staff_id": a.staff_id,
                "start_min": a.start_min,
                "items": [
                    {
                        "offset_min": i.offset_min,
                        "active_before_min": i.active_before_min,
                        "passive_min": i.passive_min,
                        "active_after_min": i.active_after_min,
                        "buffer_min": i.buffer_min,
                        "shadow_host_allowed": i.service.shadow_host_allowed,
                    }
                    for i in a.items
                ],
            }
            for a in appointments
        ]

        # Randevularin ustayi MESGUL ettigi dilimler (pasif sure HARIC)
        busy_from_appointments = [
            i for a in appointment_dicts for i in staff_busy_intervals_of(a)
        ]
        # Baskalarinin tuttugu, suresi dolmamis kilitler
        busy_from_locks = _lock_intervals_from_cells(lock_cells)
        staff_busy = normalize(busy_from_appointments + busy_from_locks)

        external_shadow_windows = collect_shadow_windows(appointment_dicts)

        result = find_available_slots(
            AvailabilityInput(
                work_windows=work_windows,
                staff_busy=staff_busy,
                external_shadow_windows=external_shadow_windows,
                resource_calendars=resource_calendars,
                layout=layout,
                grid_minutes=config.slot_grid_minutes,
                earliest_start_min=earliest_start_min,
                limit=limit_per_staff,
            )
        )

        slots = []
        for slot in result.slots:
            hour = (slot.start_min // 60) * 60
            opportunity = opportunity_by_hour.get(hour)
            slots.append(
                {
                    "startMin": slot.start_min,
                    "endMin": slot.end_min,
                    "label": minutes_to_label(slot.start_min),
                    "endLabel": minutes_to_label(slot.end_min),
                    "isShadowFill": slot.is_shadow_fill,
                    "shadowParentAppointmentId": slot.shadow_parent_appointment_id,
                    "discountRate": opportunity.discount_rate if opportunity else 0,
                    "opportunityLabel": opportunity.label if opportunity else "Standart",
                    "isOpportunity": opportunity.is_opportunity if opportunity else False,
                    "viewCount": len(view_counts.get((staff.id, slot.start_min), ())),
                    # Bu slot su an bu ziyaretcinin kendi kilidi mi?
                    "heldByYou": bool(
                        your_lock
                        and your_lock["staffId"] == staff.id
                        and your_lock["startMin"] == slot.start_min
                    ),
                }
            )

        staff_results.append(
            {
                "staffId": staff.id,
                "staffName": staff.name,
                "photoUrl": staff.photo_url,
                "speedFactor": speed_factor,
                "totalMin": layout.total_min,
                "totalPrice": layout.total_price,
                "savedMin": layout.saved_min,
                "slots": slots,
                "diagnostics": {
                    "requiredMin": result.diagnostics.required_min,
                    "longestFreeWindowMin": result.diagnostics.longest_free_window_min,
                    "tooLongForAnyWindow": result.diagnostics.too_long_for_any_window,
                    "scannedStarts": result.diagnostics.scanned_starts,
                    "reason": _explain_empty(
                        len(result.slots), result.diagnostics, len(work_windows)
                    ),
                },
            }
        )

    # --- Paket ozeti + upsell (Hata duzeltmesi 3) ------------------------
    # staff_id verilmisse o personelin yerlesimi, degilse NOMINAL yerlesim.
    summary_layout = (
        reference_layout if (staff_id and reference_layout) else layout_package(specs)
    )

    package_summary = {
        "totalMin": summary_layout.total_min,
        "totalPrice": summary_layout.total_price,
        "savedMin": summary_layout.saved_min,
        # Hangi hiz carpaniyla hesaplandigi acikca soylenir.
        "basedOnStaffId": staff_id if staff_id else None,
        "isNominal": not bool(staff_id),
        "items": [
            {
                "serviceId": i.service.id,
                "name": i.service.name,
                "offsetMin": i.offset_min,
                "activeBeforeMin": i.active_before_min,
                "passiveMin": i.passive_min,
                "activeAfterMin": i.active_after_min,
                "bufferMin": i.buffer_min,
                "price": i.price,
                "placedInShadow": i.placed_in_shadow,
            }
            for i in summary_layout.items
        ],
        "shadowWindows": [
            {"start": w.start, "end": w.end, "minutes": w.end - w.start}
            for w in summary_layout.shadow_windows
        ],
    }

    shadow_upsell = _build_shadow_upsell(db, branch.id, summary_layout, service_ids)
    has_slots = any(s["slots"] for s in staff_results)

    return {
        "date": date,
        "weekday": weekday,
        "package": package_summary,
        "staff": staff_results,
        "shadowUpsell": shadow_upsell,
        #: Ziyaretcinin halihazirda tuttugu kilit (varsa) - arayuz geri
        #: donduğunde "saatin hala senin" diyebilsin.
        "yourLock": your_lock,
        "message": None if has_slots else _summarize_empty(
            staff_results, summary_layout.total_min
        ),
    }


def _build_shadow_upsell(
    db: Session, branch_id: int, layout: PackageLayout, selected_ids: Sequence[int]
) -> list[dict]:
    """Paketin golge pencerelerine sigabilecek ek hizmetleri onerir."""
    windows = [w.end - w.start for w in layout.shadow_windows]
    if not windows:
        return []

    candidates = db.scalars(
        select(Service).where(
            Service.branch_id == branch_id,
            Service.is_active.is_(True),
            Service.shadow_guest_allowed.is_(True),
            Service.id.notin_(set(selected_ids)),
        )
    ).all()

    return suggest_shadow_fillers(
        windows,
        [
            {
                "serviceId": c.id,
                "name": c.name,
                "totalMin": c.active_before_min + c.passive_min + c.active_after_min + c.buffer_min,
                "price": c.price,
                "shadowGuestAllowed": c.shadow_guest_allowed,
            }
            for c in candidates
        ],
    )


def _explain_empty(slot_count: int, diagnostics, work_window_count: int) -> str | None:
    if slot_count > 0:
        return None
    if work_window_count == 0:
        return "Bu tarihte çalışmıyor."
    if diagnostics.too_long_for_any_window:
        return f"{diagnostics.required_min} dakikalık paket, mesai penceresine hiç sığmıyor."
    return (
        f"Takvimde kesintisiz {diagnostics.required_min} dakika kalmadı "
        f"(en uzun boşluk {diagnostics.longest_free_window_min} dk)."
    )


def _summarize_empty(staff_results: Sequence[dict], required_min: int) -> str:
    """"110 dakikalik paket 60 dakikalik bosluga onerilmez" kuralinin
    kullaniciya gorunen yuzu: neden slot olmadigini acikca soyler."""
    if not staff_results:
        return "Seçtiğiniz hizmetlerin tamamını yapabilen personel bulunamadı."
    longest = max([0] + [s["diagnostics"]["longestFreeWindowMin"] for s in staff_results])
    if 0 < longest < required_min:
        return (
            f"Seçtiğiniz paket {required_min} dakika sürüyor; bu tarihteki en uzun "
            f"kesintisiz boşluk {longest} dakika. Paket ikiye bölünmeyeceği için "
            "başka bir gün önerilir."
        )
    return "Bu tarihte uygun saat kalmadı. Lütfen başka bir gün seçin."
