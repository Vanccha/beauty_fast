"""
====================================================================
RANDEVU OLUSTURMA ve TASIMA
====================================================================

Randevu, gecerli bir soft-lock'un transaction icinde kalici kayda
donusturulmesiyle olusur:

  1) Kilidin gecerliligi dogrulanir (sahibi, suresi, kullanilmamisligi)
  2) Kilidin LOCK hucreleri silinir
  3) Randevu + kalemleri + kaynak atamalari yazilir
  4) Ayni hucreler bu kez APPOINTMENT olarak yazilir

Adim 2 ile 4 ayni transaction'da oldugu icin arada baska bir istek slotu
kapamaz; buna ragmen 4. adimda unique ihlali olursa islem geri alinir ve
cakisma hatasi doner.

(``services/booking/appointment.ts`` karsiligi.)
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.occupancy import build_occupancy_cells
from ..core.types import PackageLayout
from ..errors import AppError, SlotConflictError, VersionConflictError, is_unique_violation
from ..models import (
    Appointment,
    AppointmentItem,
    AppointmentResource,
    DesignReference,
    OccupancyCell,
)
from .deposit import DepositSettings, deposit_for_price
from .manual_booking import reclaim_cells, release_cells
from .soft_lock import assert_lock_valid, conflict_error, sweep_expired_locks
from ..time_utils import now_local


def _clamp_rate(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return min(0.9, max(0.0, v))


def confirm_appointment_from_lock(
    db: Session,
    lock_id: int,
    session_id: str,
    customer_id: int,
    branch_id: int,
    staff_id: int,
    date: str,
    start_min: int,
    layout: PackageLayout,
    exclusive_resource_ids: Sequence[int] = (),
    discount_rate: float = 0.0,
    is_opportunity: bool = False,
    notes: str | None = None,
    shadow_parent_id: int | None = None,
    design_refs: Sequence[dict] | None = None,
    now: datetime | None = None,
    booker_customer_id: int | None = None,
    booking_group_id: str | None = None,
    beneficiary_label: str | None = None,
    privacy_notice_ack_at: datetime | None = None,
    health_declaration_at: datetime | None = None,
    commit: bool = True,
    deposit_settings: DepositSettings | None = None,
) -> Appointment:
    """``customer_id`` randevunun SAHIBI (alici); baskasi adina randevuda
    ``booker_customer_id`` oturumdaki alandir (kilidin sahipligi onunla
    dogrulanir). Kendi adina alinirken ikisi aynidir.

    ``deposit_settings`` (kapora): verilir VE acik ise randevu PENDING +
    AWAITING olusur (slot yine DOLU); aksi halde eskisi gibi CONFIRMED."""
    now = now or now_local()
    booker_customer_id = booker_customer_id or customer_id
    discount_rate = _clamp_rate(discount_rate)
    end_min = start_min + layout.total_min

    cells = build_occupancy_cells(
        layout=layout,
        date=date,
        start_min=start_min,
        staff_id=staff_id,
        customer_id=customer_id,
        exclusive_resource_ids=exclusive_resource_ids,
    )

    try:
        lock = assert_lock_valid(db, lock_id, session_id, now, customer_id=booker_customer_id)

        # Kilit ile talep edilen randevu birebir ortusmeli - aksi halde
        # istemci, kilitlediginden farkli/uzun bir blogu kaydettirebilirdi.
        if lock.staff_id != staff_id or lock.date != date:
            raise AppError("VALIDATION", "Rezervasyon ile randevu bilgileri uyuşmuyor.", 400)
        if lock.start_min != start_min or lock.end_min != end_min:
            raise AppError(
                "VALIDATION",
                "Seçilen hizmetler rezerve edilen süreyle uyuşmuyor. Lütfen saati yeniden seçin.",
                409,
            )

        total_price = round(layout.total_price * (1 - discount_rate), 2)
        deposit_amount = (
            deposit_for_price(deposit_settings, total_price) if deposit_settings else None
        )

        # Kilit hucrelerini birak - yerlerine randevu hucreleri yazilacak.
        db.execute(delete(OccupancyCell).where(OccupancyCell.lock_id == lock.id))

        appointment = Appointment(
            branch_id=branch_id,
            customer_id=customer_id,
            booked_by_customer_id=booker_customer_id,
            booking_group_id=booking_group_id,
            beneficiary_label=beneficiary_label,
            staff_id=staff_id,
            date=date,
            start_min=start_min,
            end_min=end_min,
            status="PENDING" if deposit_amount else "CONFIRMED",
            deposit_amount=deposit_amount or None,
            deposit_status="AWAITING" if deposit_amount else "NONE",
            deposit_requested_at=now if deposit_amount else None,
            total_price=total_price,
            discount_rate=discount_rate,
            is_opportunity=bool(is_opportunity),
            shadow_parent_id=shadow_parent_id,
            notes=notes,
            privacy_notice_ack_at=privacy_notice_ack_at,
            health_declaration_at=health_declaration_at,
            version=0,
        )
        db.add(appointment)
        db.flush()

        db.add_all(
            [
                AppointmentItem(
                    appointment_id=appointment.id,
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
                    appointment_id=appointment.id,
                    resource_id=usage.resource_id,
                    quantity=usage.quantity,
                    start_min=int(usage.interval.start + start_min),
                    end_min=int(usage.interval.end + start_min),
                )
                for usage in layout.resource_usage
            ]
        )

        for ref in design_refs or []:
            db.add(
                DesignReference(
                    appointment_id=appointment.id,
                    source=ref["source"],
                    url=ref["url"],
                    note=ref.get("note"),
                )
            )

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
            ]
        )

        lock.consumed_at = now
        lock.customer_id = booker_customer_id

        if commit:
            db.commit()
        else:
            db.flush()
        return appointment

    except IntegrityError as error:
        db.rollback()
        if is_unique_violation(error):
            # Kilidin kendi hucreleri cakisma sayilmaz; kalan cakisma
            # yalnizca musterinin kendi takvimindeyse CUSTOMER_OVERLAP.
            raise conflict_error(
                db, cells, date, [lock_id], now, booker_customer_id != customer_id
            ) from error
        raise
    except Exception:
        db.rollback()
        raise


def move_appointment(
    db: Session,
    appointment_id: int,
    expected_version: int,
    to_staff_id: int,
    to_date: str,
    to_start_min: int,
    layout: PackageLayout,
    exclusive_resource_ids: Sequence[int] = (),
    now: datetime | None = None,
) -> Appointment:
    """
    ====================================================================
    RANDEVU TASIMA - OPTIMISTIC LOCKING
    ====================================================================

    Admin panelde surukle-birak ile randevu baska saate/ustaya tasinir.
    Guncelleme ``WHERE id = ? AND version = ?`` ile yapilir: kayit biz
    okuduktan sonra baska biri tarafindan degistirildiyse etkilenen satir
    sayisi 0 doner ve islem ``VersionConflictError`` ile reddedilir.

    Hucreler silinip yeniden yazildigi icin hedef slot doluysa unique
    kisiti devreye girer ve transaction geri alinir (randevu eski yerinde
    kalir).
    """
    now = now or now_local()
    end_min = to_start_min + layout.total_min

    try:
        sweep_expired_locks(db, now)

        current = db.get(Appointment, appointment_id)
        if current is None:
            raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)
        if current.version != expected_version:
            raise VersionConflictError(current.version)
        if current.status in ("CANCELLED", "COMPLETED", "NO_SHOW"):
            raise AppError(
                "VALIDATION", "Tamamlanmış veya iptal edilmiş randevu taşınamaz.", 400
            )

        customer_id = current.customer_id

        # Eski hucreleri birak (yeni yer eskisiyle cakisiyorsa kendi kendini
        # engellemesin).
        released = release_cells(db, appointment_id)

        cells = build_occupancy_cells(
            layout=layout,
            date=to_date,
            start_min=to_start_min,
            staff_id=to_staff_id,
            customer_id=customer_id,
            exclusive_resource_ids=exclusive_resource_ids,
        )

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
            ]
        )
        db.flush()
        # Zorla ust uste eklenmis baska randevu varsa serbest kalan hucreleri sahiplenir.
        reclaim_cells(db, released, exclude_ids=[appointment_id])

        # Surum kontrollu guncelleme - asil optimistic locking adimi.
        updated = db.execute(
            update(Appointment)
            .where(Appointment.id == appointment_id, Appointment.version == expected_version)
            .values(
                staff_id=to_staff_id,
                date=to_date,
                start_min=to_start_min,
                end_min=end_min,
                version=Appointment.version + 1,
            )
        ).rowcount
        if not updated:
            raise VersionConflictError()

        # Kalem ofsetleri/sureleri hedef personele gore degistiyse yenile.
        db.execute(
            delete(AppointmentItem).where(AppointmentItem.appointment_id == appointment_id)
        )
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

        db.execute(
            delete(AppointmentResource).where(
                AppointmentResource.appointment_id == appointment_id
            )
        )
        db.add_all(
            [
                AppointmentResource(
                    appointment_id=appointment_id,
                    resource_id=usage.resource_id,
                    quantity=usage.quantity,
                    start_min=int(usage.interval.start + to_start_min),
                    end_min=int(usage.interval.end + to_start_min),
                )
                for usage in layout.resource_usage
            ]
        )

        db.commit()
        db.expire_all()
        return db.get(Appointment, appointment_id)

    except IntegrityError as error:
        db.rollback()
        if is_unique_violation(error):
            raise SlotConflictError() from error
        raise
    except Exception:
        db.rollback()
        raise
