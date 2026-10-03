"""
====================================================================
PANELDEN ELLE RANDEVU - olusturma, duzenleme, cakisma denetimi
====================================================================

Personel, musteri akisindan (soft-lock + onay) bagimsiz olarak panelden
randevu ekleyebilir ve duzenleyebilir. Sure/fiyat/hucre hesabi musteri
akisiyla AYNI motoru kullanir (``load_service_specs`` + ``layout_package``
+ ``build_occupancy_cells``); farklar:

  * soft-lock yoktur; cakisma dogrudan ``occupancy_cell`` uzerinde aranir
    ve kullaniciya ANLASILIR nedenle (usta dolu / musterinin baska randevusu /
    kaynak dolu / mesai disi) bildirilir -> 409 ``SLOT_CONFLICT``.
  * ``force`` (yalnizca yonetici): cakisma olsa da randevu yazilir. Hucre
    kisiti cift rezervasyona izin vermedigi icin YALNIZCA cakisan hucreler
    atlanir (randevu kaydi + kalemler yazilir, takvimde ust uste gorunur).
    Sonradan tasima/duzenleme bu randevuyu temiz bir yere alir.
  * kaynak: ``appointment.source = 'ADMIN'`` + ``created_by_staff_id``.

Tum islemler TEK transaction'dadir; hata olursa hicbir sey yazilmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import and_, delete, or_, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..auth.sessions import StaffPrincipal
from ..config import config
from ..core.occupancy import CellSpec, build_occupancy_cells, cell_indexes, cell_indexes_of_many
from ..core.opportunity import fixed_window_discount
from ..core.package_layout import LayoutOptions, layout_package
from ..core.reminder_rules import resolve_pre_reminder
from ..core.types import PackageLayout
from ..deps import ROLE_RANK
from ..errors import AppError, SlotConflictError, VersionConflictError, is_unique_violation
from ..intervals import Interval, subtract
from ..models import (
    Appointment,
    AppointmentItem,
    AppointmentResource,
    Branch,
    Customer,
    OccupancyCell,
    ScheduledNotification,
    Staff,
    TimeOff,
)
from ..time_utils import (
    format_date_tr,
    minutes_to_label,
    now_local,
    to_datetime,
    weekday_of,
)
from . import notification_worker, push
from .availability import _build_work_windows
from . import deposit
from .booking_confirmation import (
    CONFIRM_PREFIX,
    ConfirmationLine,
    build_confirmation_message,
    queue_confirmation,
)
from .booking_for_other import BeneficiaryBody, find_or_create_beneficiary
from .catalog import (
    assert_staff_can_do,
    get_default_branch,
    get_discount_settings,
    get_exclusive_resource_ids,
    load_service_specs,
)
from .soft_lock import sweep_expired_locks

TERMINAL = ("COMPLETED", "CANCELLED", "NO_SHOW")
UPDATE_PREFIX = "update:"
_UNSET: Any = object()

STATUS_TR = {
    "COMPLETED": "Tamamlandı",
    "CANCELLED": "İptal edildi",
    "NO_SHOW": "Gelmedi",
}


def is_manager(principal: StaffPrincipal) -> bool:
    return ROLE_RANK.get(principal.role, 0) >= ROLE_RANK["MANAGER"]


def reachable(customer: Customer | None) -> bool:
    return bool(customer and customer.anonymized_at is None and customer.phone)


# ---------------------------------------------------------------------
# Hesap: sure / fiyat / hucre
# ---------------------------------------------------------------------


def compute_layout(
    db: Session, staff_id: int, service_ids: Sequence[int]
) -> tuple[PackageLayout, list]:
    """Musteri akisiyla ayni paket yerlesimi (ustanin hiz carpani dahil)."""
    speed_factor = assert_staff_can_do(db, staff_id, service_ids)
    specs = load_service_specs(db, service_ids)
    return layout_package(specs, LayoutOptions(speed_factor=speed_factor)), specs


def compute_price(
    db: Session,
    layout: PackageLayout,
    date: str,
    start_min: int,
    apply_discount: bool,
    price_override: float | None,
) -> tuple[float, float]:
    """(toplam fiyat, indirim orani). Elle fiyat verilirse indirim 0'dir."""
    if price_override is not None:
        return round(float(price_override), 2), 0.0
    rate = (
        fixed_window_discount(date, start_min, get_discount_settings(db))
        if apply_discount
        else 0.0
    )
    return round(layout.total_price * (1 - rate), 2), rate


def existing_cells(appointment: Appointment, exclusive_resource_ids: Sequence[int]) -> list[CellSpec]:
    """Kayitli bir randevunun (kalem/kaynak satirlarindan) hucreleri.

    Iptal/gelmedi geri alinirken kullanilir; hizmet tanimi sonradan degismis
    olsa bile randevunun YAZILDIGI andaki bloklar korunur."""
    cm = config.cell_minutes
    busy: list[Interval] = []
    for item in appointment.items:
        base = appointment.start_min + item.offset_min
        if item.active_before_min > 0:
            busy.append(Interval(base, base + item.active_before_min))
        after_start = base + item.active_before_min + item.passive_min
        after_end = after_start + item.active_after_min + item.buffer_min
        if after_end > after_start:
            busy.append(Interval(after_start, after_end))

    out: list[CellSpec] = []
    seen: set[tuple[str, int, int]] = set()

    def push_cells(owner_type: str, owner_id: int, indexes: Sequence[int]) -> None:
        for idx in indexes:
            key = (owner_type, owner_id, idx)
            if key not in seen:
                seen.add(key)
                out.append(CellSpec(owner_type, owner_id, appointment.date, idx))

    push_cells("STAFF", appointment.staff_id, cell_indexes_of_many(busy, cm))
    push_cells(
        "CUSTOMER",
        appointment.customer_id,
        cell_indexes(Interval(appointment.start_min, appointment.end_min), cm),
    )
    exclusive = set(exclusive_resource_ids)
    by_resource: dict[int, list[Interval]] = {}
    for usage in appointment.resources:
        if usage.resource_id in exclusive:
            by_resource.setdefault(usage.resource_id, []).append(
                Interval(usage.start_min, usage.end_min)
            )
    for resource_id, intervals in by_resource.items():
        push_cells("RESOURCE", resource_id, cell_indexes_of_many(intervals, cm))
    return out


CellKey = tuple[str, int, str, int]  # (owner_type, owner_id, date, cell_index)
ACTIVE = ("PENDING", "CONFIRMED")


def release_cells(db: Session, appointment_id: int) -> set[CellKey]:
    """Randevunun hucrelerini siler ve serbest kalan anahtarlari doner.

    TEK cikis noktasi: iptal, gelmedi, tasima ve duzenleme bunu kullanir;
    ardindan ``reclaim_cells`` cagrilmalidir (zorla eklenmis ust uste
    randevunun hucreleri baskasinin elindeydi)."""
    rows = db.execute(
        delete(OccupancyCell)
        .where(OccupancyCell.appointment_id == appointment_id)
        .returning(
            OccupancyCell.owner_type,
            OccupancyCell.owner_id,
            OccupancyCell.date,
            OccupancyCell.cell_index,
        )
    ).all()
    return {(r[0], r[1], r[2], r[3]) for r in rows}


def reclaim_cells(
    db: Session, released: set[CellKey], exclude_ids: Sequence[int] = ()
) -> int:
    """Serbest kalan hucrelerden hala AKTIF baska randevularin kapsadigi ve
    su an bos olanlari o randevulara yazar (zorla ust uste eklenmis
    randevu, ilk randevu kalkinca slotu acik birakmasin). Eklenen sayi doner."""
    if not released:
        return 0
    dates = {k[2] for k in released}
    claimed = 0
    for date in dates:
        actives = db.scalars(
            select(Appointment)
            .options(selectinload(Appointment.items), selectinload(Appointment.resources))
            .where(
                Appointment.date == date,
                Appointment.status.in_(ACTIVE),
                Appointment.id.not_in(list(exclude_ids) or [0]),
            )
        ).all()
        if not actives:
            continue
        exclusive = get_exclusive_resource_ids(db, actives[0].branch_id)
        wanted: list[tuple[int, CellSpec]] = []
        for a in actives:
            for c in existing_cells(a, exclusive):
                if (c.owner_type, c.owner_id, c.date, c.cell_index) in released:
                    wanted.append((a.id, c))
        if not wanted:
            continue
        taken = {
            (r[0], r[1], r[2])
            for r in db.execute(
                select(OccupancyCell.owner_type, OccupancyCell.owner_id, OccupancyCell.cell_index).where(
                    OccupancyCell.date == date,
                    tuple_(
                        OccupancyCell.owner_type, OccupancyCell.owner_id, OccupancyCell.cell_index
                    ).in_([(c.owner_type, c.owner_id, c.cell_index) for _, c in wanted]),
                )
            ).all()
        }
        for appt_id, c in wanted:
            key = (c.owner_type, c.owner_id, c.cell_index)
            if key in taken:
                continue
            taken.add(key)
            db.add(
                OccupancyCell(
                    owner_type=c.owner_type,
                    owner_id=c.owner_id,
                    date=c.date,
                    cell_index=c.cell_index,
                    kind="APPOINTMENT",
                    appointment_id=appt_id,
                )
            )
            claimed += 1
    db.flush()
    return claimed


def queue_update_notice(db: Session, appointment: Appointment) -> bool:
    """"Randevunuz guncellendi" mesaji; dedupe: randevu + surum. Commit cagiranindir.
    ``appointment.items[].service`` ve ``customer`` yuklu olmali."""
    if not reachable(appointment.customer):
        return False
    names = [i.service.name for i in appointment.items if i.service is not None]
    queue_confirmation(
        db,
        appointment.customer_id,
        f"{UPDATE_PREFIX}{appointment.id}:{appointment.version}",
        f"Merhaba {appointment.customer.first_name}, randevunuz güncellendi: "
        f"{format_date_tr(appointment.date)} saat {minutes_to_label(appointment.start_min)}"
        f" - {', '.join(names)}\n\n"
        f"Randevunuzu görmek veya iptal etmek için: {config.public_site_url}/randevularim",
    )
    return True


@dataclass
class ConflictReport:
    conflicts: list[dict]
    #: Yazilamayacak (zaten dolu) hucre anahtarlari: force'ta atlanir.
    blocked: set[tuple[str, int, int]]

    @property
    def any(self) -> bool:
        return bool(self.conflicts)

    def message(self) -> str:
        msgs = [c["message"] for c in self.conflicts]
        text = " ".join(msgs[:2])
        if len(msgs) > 2:
            text += f" (+{len(msgs) - 2} çakışma daha)"
        return text


def find_conflicts(
    db: Session,
    *,
    cells: Sequence[CellSpec],
    date: str,
    exclude_appointment_id: int | None = None,
    now: datetime | None = None,
) -> ConflictReport:
    """Yazilmak istenen hucrelerle cakisan mevcut hucreleri nedenleriyle toplar."""
    now = now or now_local()
    if not cells:
        return ConflictReport([], set())

    query = select(OccupancyCell).where(
        OccupancyCell.date == date,
        tuple_(
            OccupancyCell.owner_type, OccupancyCell.owner_id, OccupancyCell.cell_index
        ).in_([(c.owner_type, c.owner_id, c.cell_index) for c in cells]),
        or_(OccupancyCell.kind != "LOCK", OccupancyCell.expires_at > now),
    )
    if exclude_appointment_id is not None:
        query = query.where(
            or_(
                OccupancyCell.appointment_id.is_(None),
                OccupancyCell.appointment_id != exclude_appointment_id,
            )
        )
    rows = list(db.scalars(query))
    blocked = {(r.owner_type, r.owner_id, r.cell_index) for r in rows}

    appt_ids = {r.appointment_id for r in rows if r.appointment_id}
    appts = {
        a.id: a
        for a in db.scalars(
            select(Appointment)
            .options(selectinload(Appointment.customer))
            .where(Appointment.id.in_(appt_ids))
        )
    } if appt_ids else {}

    def who(a: Appointment | None) -> str:
        if a is None:
            return ""
        name = f"{a.customer.first_name} {a.customer.last_name or ''}".strip()
        return (
            f" ({minutes_to_label(a.start_min)}–{minutes_to_label(a.end_min)} {name})"
        )

    conflicts: list[dict] = []
    seen: set[tuple[str, int | None]] = set()
    for r in rows:
        if r.kind == "LOCK":
            key = ("LOCK", None)
            msg = "Bir müşteri bu saati şu anda rezerve ediyor (birkaç dakika içinde serbest kalır)."
            kind = "LOCK"
        elif r.owner_type == "STAFF":
            key, kind = ("STAFF", r.appointment_id), "STAFF"
            msg = f"Usta bu saatte başka bir randevuda{who(appts.get(r.appointment_id))}."
        elif r.owner_type == "CUSTOMER":
            key, kind = ("CUSTOMER", r.appointment_id), "CUSTOMER"
            msg = f"Müşterinin bu saatte başka bir randevusu var{who(appts.get(r.appointment_id))}."
        else:
            key, kind = ("RESOURCE", r.appointment_id), "RESOURCE"
            msg = f"Gerekli ekipman/koltuk bu saatte dolu{who(appts.get(r.appointment_id))}."
        if key in seen:
            continue
        seen.add(key)
        conflicts.append(
            {"kind": kind, "message": msg, "appointmentId": r.appointment_id}
        )
    return ConflictReport(conflicts, blocked)


def check_work_hours(
    db: Session,
    *,
    branch: Branch,
    staff_id: int,
    date: str,
    start_min: int,
    layout: PackageLayout,
) -> list[dict]:
    """Mesai / izin / salon saatleri disinda mi? (cakisma olarak raporlanir)"""
    staff = db.scalar(
        select(Staff).options(selectinload(Staff.working_hours)).where(Staff.id == staff_id)
    )
    if staff is None or not staff.is_active:
        return [{"kind": "OUTSIDE_HOURS", "message": "Seçilen personel aktif değil.", "appointmentId": None}]
    wh = next((w for w in staff.working_hours if w.weekday == weekday_of(date)), None)
    time_off = db.scalars(
        select(TimeOff).where(TimeOff.staff_id == staff_id, TimeOff.date == date)
    ).all()
    windows = _build_work_windows(branch.open_minute, branch.close_minute, wh, time_off)
    busy = [Interval(i.start + start_min, i.end + start_min) for i in layout.staff_busy]
    end_min = start_min + layout.total_min
    outside = bool(subtract(busy, windows)) or end_min > branch.close_minute or start_min < branch.open_minute
    if outside:
        return [
            {
                "kind": "OUTSIDE_HOURS",
                "message": "Usta bu saatte çalışmıyor (mesai dışı, izinli veya salon kapalı).",
                "appointmentId": None,
            }
        ]
    return []


def evaluate_slot(
    db: Session,
    *,
    branch: Branch,
    layout: PackageLayout,
    staff_id: int,
    customer_id: int | None,
    date: str,
    start_min: int,
    exclude_appointment_id: int | None = None,
    now: datetime | None = None,
) -> tuple[ConflictReport, list[CellSpec]]:
    cells = build_occupancy_cells(
        layout=layout,
        date=date,
        start_min=start_min,
        staff_id=staff_id,
        customer_id=customer_id,
        exclusive_resource_ids=get_exclusive_resource_ids(db, branch.id),
    )
    report = find_conflicts(
        db, cells=cells, date=date, exclude_appointment_id=exclude_appointment_id, now=now
    )
    hours = check_work_hours(
        db, branch=branch, staff_id=staff_id, date=date, start_min=start_min, layout=layout
    )
    if hours:
        report.conflicts = hours + report.conflicts
    return report, cells


def raise_if_conflict(report: ConflictReport, force: bool, can_force: bool) -> None:
    if not report.any:
        return
    if force:
        if not can_force:
            raise AppError(
                "FORBIDDEN", "Çakışmaya rağmen randevu eklemek yalnızca yönetici yetkisindedir.", 403
            )
        return
    raise AppError(
        "SLOT_CONFLICT",
        report.message(),
        409,
        {"conflicts": report.conflicts, "canForce": can_force},
    )


def preview(
    db: Session,
    *,
    principal: StaffPrincipal,
    service_ids: Sequence[int],
    staff_id: int,
    date: str,
    start_min: int,
    customer_id: int | None = None,
    exclude_appointment_id: int | None = None,
    apply_discount: bool = True,
) -> dict:
    """Formun sure/fiyat/cakisma onizlemesi (yazmaz)."""
    branch = get_default_branch(db)
    layout, _ = compute_layout(db, staff_id, service_ids)
    now = now_local()
    sweep_expired_locks(db, now)
    report, _cells = evaluate_slot(
        db,
        branch=branch,
        layout=layout,
        staff_id=staff_id,
        customer_id=customer_id,
        date=date,
        start_min=start_min,
        exclude_appointment_id=exclude_appointment_id,
        now=now,
    )
    price, rate = compute_price(db, layout, date, start_min, apply_discount, None)
    db.rollback()  # sweep silmeleri onizlemede kalici olmasin
    return {
        "totalMin": layout.total_min,
        "endMin": start_min + layout.total_min,
        "endLabel": minutes_to_label(start_min + layout.total_min),
        "basePrice": layout.total_price,
        "discountRate": rate,
        "price": price,
        "conflicts": report.conflicts,
        "canForce": is_manager(principal),
    }


# ---------------------------------------------------------------------
# Yazma yardimcilari
# ---------------------------------------------------------------------


def _write_items(db: Session, appointment_id: int, layout: PackageLayout, start_min: int) -> None:
    db.add_all(
        [
            AppointmentItem(
                appointment_id=appointment_id,
                service_id=item.service.id,
                sort_order=item.sort_order,
                offset_min=item.offset_min,
                active_before_min=item.active_before_min,
                passive_min=item.passive_min,
                active_after_min=item.active_after_min,
                buffer_min=item.buffer_min,
                price=item.price,
            )
            for item in layout.items
        ]
    )
    db.add_all(
        [
            AppointmentResource(
                appointment_id=appointment_id,
                resource_id=usage.resource_id,
                quantity=usage.quantity,
                start_min=int(usage.interval.start + start_min),
                end_min=int(usage.interval.end + start_min),
            )
            for usage in layout.resource_usage
        ]
    )


def _write_cells(
    db: Session,
    appointment_id: int,
    cells: Sequence[CellSpec],
    skip: set[tuple[str, int, int]] | None = None,
) -> None:
    skip = skip or set()
    db.add_all(
        [
            OccupancyCell(
                owner_type=c.owner_type,
                owner_id=c.owner_id,
                date=c.date,
                cell_index=c.cell_index,
                kind="APPOINTMENT",
                appointment_id=appointment_id,
            )
            for c in cells
            if (c.owner_type, c.owner_id, c.cell_index) not in skip
        ]
    )


def sync_pre_reminder(
    db: Session,
    appointment: Appointment,
    owner: Customer,
    service_names: Sequence[str],
    now: datetime | None = None,
) -> None:
    """"Yarin randevunuz var" hatirlatmasini randevunun GUNCEL saatine esler.

    Bekleyen satir guncellenir (iptal edilmisse yeniden canlandirilir), yoksa
    yazilir; vakti gectiyse bekleyen satir geri cekilir. Gonderilmis satira
    dokunulmaz."""
    if not reachable(owner):
        return
    key = f"pre:{appointment.id}:24"
    row = db.scalar(select(ScheduledNotification).where(ScheduledNotification.dedupe_key == key))
    pre = resolve_pre_reminder(
        appointment_id=appointment.id,
        starts_at=to_datetime(appointment.date, appointment.start_min),
        service_name=" + ".join(service_names),
        customer_name=owner.first_name,
        hours_before=24,
        now=now,
    )
    if pre is None:
        if row is not None and row.status == "PENDING":
            row.status = "CANCELLED"
        return
    if row is None:
        db.add(
            ScheduledNotification(
                customer_id=owner.id,
                channel=pre.channel,
                body=pre.body,
                due_at=pre.due_at,
                dedupe_key=pre.dedupe_key,
            )
        )
    elif row.status in ("PENDING", "CANCELLED"):
        row.customer_id = owner.id
        row.body = pre.body
        row.due_at = pre.due_at
        row.status = "PENDING"


def _resolve_customer(
    db: Session, customer_id: int | None, new_customer: BeneficiaryBody | None
) -> Customer:
    if customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None:
            raise AppError("NOT_FOUND", "Müşteri bulunamadı.", 404)
    elif new_customer is not None:
        customer = find_or_create_beneficiary(db, new_customer)
    else:
        raise AppError(
            "VALIDATION",
            "Müşteri seçin ya da yeni müşteri için ad ve telefon girin (telefonsuz kayıt desteklenmez).",
            400,
        )
    if customer.anonymized_at is not None:
        raise AppError("VALIDATION", "Bu müşterinin kaydı anonimleştirilmiş; randevu eklenemez.", 400)
    return customer


def _staff_guard(principal: StaffPrincipal, *staff_ids: int) -> None:
    """Normal personel yalnizca KENDI takvimine islem yapabilir."""
    if is_manager(principal):
        return
    if any(sid != principal.id for sid in staff_ids):
        raise AppError(
            "FORBIDDEN", "Başka bir personel adına randevu eklemek/düzenlemek için yönetici olmalısınız.", 403
        )


def appointment_payload(a: Appointment) -> dict:
    return {
        "id": a.id,
        "status": a.status,
        "customerId": a.customer_id,
        "staffId": a.staff_id,
        "date": a.date,
        "startMin": a.start_min,
        "endMin": a.end_min,
        "startLabel": minutes_to_label(a.start_min),
        "endLabel": minutes_to_label(a.end_min),
        "totalPrice": a.total_price,
        "discountRate": a.discount_rate,
        "isOpportunity": a.is_opportunity,
        "version": a.version,
        "source": a.source,
        "depositStatus": a.deposit_status,
        "depositAmount": a.deposit_amount,
    }


# ---------------------------------------------------------------------
# OLUSTURMA
# ---------------------------------------------------------------------


def create_manual_appointment(
    db: Session,
    *,
    creator: StaffPrincipal,
    customer_id: int | None,
    new_customer: BeneficiaryBody | None,
    staff_id: int,
    date: str,
    start_min: int,
    service_ids: Sequence[int],
    status: str = "CONFIRMED",
    apply_discount: bool = True,
    price_override: float | None = None,
    notes: str | None = None,
    send_whatsapp: bool = True,
    force: bool = False,
    request_deposit: bool = False,
    now: datetime | None = None,
) -> dict:
    now = now or now_local()
    if status not in ("PENDING", "CONFIRMED"):
        raise AppError("VALIDATION", "Yeni randevu 'Bekliyor' veya 'Onaylandı' olabilir.", 400)
    _staff_guard(creator, staff_id)
    can_force = is_manager(creator)
    if force and not can_force:
        raise AppError(
            "FORBIDDEN", "Çakışmaya rağmen randevu eklemek yalnızca yönetici yetkisindedir.", 403
        )
    deposit_settings = deposit.load_settings(db)
    if request_deposit and not deposit_settings.enabled:
        raise AppError("VALIDATION", "Kapora ayarı kapalı; önce Kapora ayarlarını açın.", 400)

    branch = get_default_branch(db)
    try:
        sweep_expired_locks(db, now)
        customer = _resolve_customer(db, customer_id, new_customer)
        layout, specs = compute_layout(db, staff_id, service_ids)
        end_min = start_min + layout.total_min

        report, cells = evaluate_slot(
            db,
            branch=branch,
            layout=layout,
            staff_id=staff_id,
            customer_id=customer.id,
            date=date,
            start_min=start_min,
            now=now,
        )
        raise_if_conflict(report, force, can_force)

        total_price, rate = compute_price(db, layout, date, start_min, apply_discount, price_override)

        # "Kapora iste": PENDING + AWAITING (slot dolu), kapora mesaji gider.
        deposit_amount = None
        if request_deposit:
            deposit_amount = deposit.deposit_for_price(deposit_settings, total_price)
            if not deposit_amount:
                raise AppError("VALIDATION", "Tutar 0 olduğu için kapora istenemez.", 400)
            status = "PENDING"

        appointment = Appointment(
            branch_id=branch.id,
            customer_id=customer.id,
            booked_by_customer_id=customer.id,
            staff_id=staff_id,
            date=date,
            start_min=start_min,
            end_min=end_min,
            status=status,
            deposit_amount=deposit_amount,
            deposit_status=deposit.AWAITING if deposit_amount else deposit.NONE,
            deposit_requested_at=now if deposit_amount else None,
            total_price=total_price,
            discount_rate=rate,
            is_opportunity=rate > 0,
            notes=(notes or "").strip() or None,
            source="ADMIN",
            created_by_staff_id=creator.id,
            version=0,
        )
        db.add(appointment)
        db.flush()
        _write_items(db, appointment.id, layout, start_min)
        _write_cells(db, appointment.id, cells, report.blocked if force else None)
        db.flush()

        service_names = [s.name for s in specs]
        sync_pre_reminder(db, appointment, customer, service_names, now)

        whatsapp_queued = False
        if deposit_amount:
            # Kapora talebi normal onay mesajinin YERINE gider.
            if send_whatsapp:
                db.refresh(appointment)
                whatsapp_queued = deposit.queue_deposit_request(
                    db, [appointment], customer, deposit_settings
                )
        elif send_whatsapp and reachable(customer):
            staff_row = db.get(Staff, staff_id)
            queue_confirmation(
                db,
                customer.id,
                f"{CONFIRM_PREFIX}{appointment.id}",
                build_confirmation_message(
                    customer.first_name,
                    [
                        ConfirmationLine(
                            date=date,
                            start_min=start_min,
                            service_names=service_names,
                            staff_name=staff_row.name if staff_row else "",
                        )
                    ],
                ),
            )
            whatsapp_queued = True

        db.commit()
    except IntegrityError as error:
        db.rollback()
        if is_unique_violation(error):
            # Esli yaris: kontrol ile yazma arasinda baska bir istek slotu aldi.
            raise SlotConflictError() from error
        raise
    except Exception:
        db.rollback()
        raise

    if whatsapp_queued:
        notification_worker.kick()
    # Atanan usta ekleyenden farkliysa ona haber ver (kendi eklediyse gereksiz).
    if staff_id != creator.id:
        push.notify_new_appointments([appointment.id])

    db.refresh(appointment)
    return {
        "appointment": appointment_payload(appointment),
        "forced": bool(force and report.any),
        "conflicts": report.conflicts if force else [],
        "whatsappQueued": whatsapp_queued,
        "depositAmount": appointment.deposit_amount,
        "customer": {
            "id": customer.id,
            "firstName": customer.first_name,
            "lastName": customer.last_name,
            "phone": customer.phone,
        },
    }


# ---------------------------------------------------------------------
# DUZENLEME
# ---------------------------------------------------------------------


def update_manual_appointment(
    db: Session,
    *,
    editor: StaffPrincipal,
    appointment_id: int,
    expected_version: int,
    service_ids: Sequence[int] | None = None,
    staff_id: int | None = None,
    date: str | None = None,
    start_min: int | None = None,
    customer_id: int | None = None,
    new_customer: BeneficiaryBody | None = None,
    notes: Any = _UNSET,
    price_override: Any = _UNSET,
    apply_discount: bool = True,
    force: bool = False,
    notify_customer: bool = False,
    now: datetime | None = None,
) -> dict:
    """Randevuyu gunceller.

    Fiyat kurali: ``price_override`` sayi ise o fiyat yazilir (indirim 0);
    ``None`` ise otomatik hesaplanir; verilmediyse yalnizca hizmet/personel/
    tarih/saat DEGISTIYSE otomatik yeniden hesaplanir, aksi halde dokunulmaz."""
    now = now or now_local()
    can_force = is_manager(editor)
    if force and not can_force:
        raise AppError(
            "FORBIDDEN", "Çakışmaya rağmen kaydetmek yalnızca yönetici yetkisindedir.", 403
        )

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
        if appointment.version != expected_version:
            raise VersionConflictError(appointment.version)
        if appointment.status in TERMINAL:
            raise AppError(
                "VALIDATION",
                f'Bu randevu "{STATUS_TR.get(appointment.status, appointment.status)}" durumunda; '
                "düzenlemek için önce \"Geri al\" yapın.",
                409,
            )

        new_staff = staff_id if staff_id is not None else appointment.staff_id
        _staff_guard(editor, appointment.staff_id, new_staff)
        new_date = date if date is not None else appointment.date
        new_start = start_min if start_min is not None else appointment.start_min
        old_service_ids = [i.service_id for i in appointment.items]
        new_service_ids = list(service_ids) if service_ids is not None else old_service_ids

        owner = appointment.customer
        customer_changed = False
        if customer_id is not None or new_customer is not None:
            owner = _resolve_customer(db, customer_id, new_customer)
            customer_changed = owner.id != appointment.customer_id

        structural = (
            customer_changed
            or new_staff != appointment.staff_id
            or new_date != appointment.date
            or new_start != appointment.start_min
            or new_service_ids != old_service_ids
        )

        values: dict[str, Any] = {}
        report = ConflictReport([], set())
        layout: PackageLayout | None = None
        cells: list[CellSpec] = []
        specs = None

        if structural:
            sweep_expired_locks(db, now)
            branch = get_default_branch(db)
            layout, specs = compute_layout(db, new_staff, new_service_ids)
            report, cells = evaluate_slot(
                db,
                branch=branch,
                layout=layout,
                staff_id=new_staff,
                customer_id=owner.id,
                date=new_date,
                start_min=new_start,
                exclude_appointment_id=appointment.id,
                now=now,
            )
            raise_if_conflict(report, force, can_force)
            values.update(
                staff_id=new_staff,
                date=new_date,
                start_min=new_start,
                end_min=new_start + layout.total_min,
            )
            if customer_changed:
                values.update(
                    customer_id=owner.id, booked_by_customer_id=owner.id, beneficiary_label=None
                )

        if price_override is not _UNSET and price_override is not None:
            values.update(total_price=round(float(price_override), 2), discount_rate=0.0, is_opportunity=False)
        elif structural or price_override is None:
            # (price_override None: acikca "otomatik hesapla")
            if price_override is None and layout is None:
                layout, specs = compute_layout(db, new_staff, new_service_ids)
            total, rate = compute_price(db, layout, new_date, new_start, apply_discount, None)
            values.update(total_price=total, discount_rate=rate, is_opportunity=rate > 0)

        # Kapora bekleniyorsa fiyat degisince kapora tutari yeniden hesaplanir
        # (mesaj OTOMATIK tekrar gonderilmez; panelde "tekrar gonder" dugmesi var).
        deposit_recomputed = False
        if "total_price" in values and appointment.deposit_status == deposit.AWAITING:
            new_amount = deposit.deposit_for_price(deposit.load_settings(db), values["total_price"])
            if new_amount and float(appointment.deposit_amount or 0) != new_amount:
                values["deposit_amount"] = new_amount
                deposit_recomputed = True

        if notes is not _UNSET:
            values["notes"] = (notes or "").strip() or None

        if not values:
            raise AppError("VALIDATION", "Değiştirilecek bir alan gönderilmedi.", 400)

        updated = db.execute(
            update(Appointment)
            .where(Appointment.id == appointment.id, Appointment.version == expected_version)
            .values(**values, version=Appointment.version + 1)
        ).rowcount
        if not updated:
            raise VersionConflictError()

        if structural:
            released = release_cells(db, appointment.id)
            db.execute(delete(AppointmentItem).where(AppointmentItem.appointment_id == appointment.id))
            db.execute(
                delete(AppointmentResource).where(AppointmentResource.appointment_id == appointment.id)
            )
            db.expire(appointment, ["items", "resources"])
            _write_items(db, appointment.id, layout, new_start)
            _write_cells(db, appointment.id, cells, report.blocked if force else None)
            db.flush()
            reclaim_cells(db, released, exclude_ids=[appointment.id])

            if customer_changed:
                # Eski musteriye bekleyen onay/hatirlatma gitmesin.
                db.execute(
                    update(ScheduledNotification)
                    .where(
                        ScheduledNotification.dedupe_key.in_(
                            (f"confirm:{appointment.id}", f"pre:{appointment.id}:24")
                        ),
                        ScheduledNotification.status == "PENDING",
                    )
                    .values(status="CANCELLED")
                )

        db.expire_all()
        appointment = db.scalar(
            select(Appointment)
            .options(
                selectinload(Appointment.items).selectinload(AppointmentItem.service),
                selectinload(Appointment.customer),
            )
            .where(Appointment.id == appointment_id)
        )
        service_names = [i.service.name for i in appointment.items]
        if structural:
            sync_pre_reminder(db, appointment, appointment.customer, service_names, now)

        notice_queued = False
        if notify_customer:
            notice_queued = queue_update_notice(db, appointment)

        db.commit()
    except IntegrityError as error:
        db.rollback()
        if is_unique_violation(error):
            raise SlotConflictError() from error
        raise
    except Exception:
        db.rollback()
        raise

    if notice_queued:
        notification_worker.kick()
    db.refresh(appointment)
    return {
        "appointment": appointment_payload(appointment),
        "forced": bool(force and report.any),
        "conflicts": report.conflicts if force else [],
        "whatsappQueued": notice_queued,
        "depositRecomputed": deposit_recomputed,
        "depositAmount": appointment.deposit_amount,
    }
