"""Katalog uclari.

  GET /api/catalog/services - kategoriler + hizmetler (oneri sirasiyla)
  GET /api/catalog/staff    - paketin TAMAMINI yapabilen personel
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.recommendation import ServiceStat, rank_services
from ..deps import DbSession
from ..http import EnvelopeRoute
from ..models import (
    Appointment,
    AppointmentItem,
    Resource,
    Service,
    ServiceCategory,
    Staff,
)
from ..services.catalog import get_default_branch
from ..time_utils import is_date_key, now_local, to_date_key

router = APIRouter(prefix="/api/catalog", tags=["catalog"], route_class=EnvelopeRoute)

#: Populerlik/guvenilirlik istatistigi bu kadar gunluk gecmisten cikarilir.
STAT_WINDOW_DAYS = 120


@router.get("/services")
def list_services(
    db: DbSession,
    date: str | None = None,
    categoryId: int | None = None,
) -> dict:
    """Kategori + hizmet listesini **oneri sirasiyla** doner.

    Siralama ``rank_services`` ile yapilir: uyum (fit), populerlik,
    guvenilirlik ve dakika basina gelir arti; kaynak cekismesi ve takvimi
    parcalama eksi puandir.
    """
    branch = get_default_branch(db)
    date = date if (date and is_date_key(date)) else to_date_key(now_local())
    since_key = to_date_key(now_local() - timedelta(days=STAT_WINDOW_DAYS))

    categories = db.scalars(
        select(ServiceCategory)
        .where(ServiceCategory.branch_id == branch.id)
        .order_by(ServiceCategory.sort_order, ServiceCategory.id)
    ).all()

    service_query = (
        select(Service)
        .options(selectinload(Service.requirements), selectinload(Service.staff_links))
        .where(Service.branch_id == branch.id, Service.is_active.is_(True))
    )
    if categoryId:
        service_query = service_query.where(Service.category_id == categoryId)
    services = db.scalars(service_query).all()

    item_rows = db.execute(
        select(AppointmentItem.service_id, Appointment.status)
        .join(Appointment, Appointment.id == AppointmentItem.appointment_id)
        .where(Appointment.branch_id == branch.id, Appointment.date >= since_key)
    ).all()

    resource_rows = db.execute(
        select(Resource.id, Resource.capacity).where(Resource.branch_id == branch.id)
    ).all()

    bookings: dict[int, int] = {}
    no_shows: dict[int, int] = {}
    for service_id, status in item_rows:
        bookings[service_id] = bookings.get(service_id, 0) + 1
        if status == "NO_SHOW":
            no_shows[service_id] = no_shows.get(service_id, 0) + 1

    capacity_by_id = {rid: cap for rid, cap in resource_rows}
    grid_minutes = 15
    span = branch.close_minute - branch.open_minute

    stats: list[ServiceStat] = []
    for s in services:
        duration_min = s.active_before_min + s.passive_min + s.active_after_min
        total_min = duration_min + s.buffer_min

        # Kaynak cekismesi: gereken kaynaklarin kapasitesi ne kadar dusukse
        # o kadar dar bogaz (capacity 1 -> 1.0, capacity 4 -> 0.25).
        contention = (
            max((1 / capacity_by_id.get(r.resource_id, 1)) for r in s.requirements)
            if s.requirements
            else 0.0
        )
        leftover = 0 if total_min % grid_minutes == 0 else grid_minutes - (total_min % grid_minutes)

        stats.append(
            ServiceStat(
                service_id=s.id,
                name=s.name,
                bookings=bookings.get(s.id, 0),
                no_shows=no_shows.get(s.id, 0),
                duration_min=duration_min,
                price=s.price,
                resource_contention=contention,
                avg_leftover_gap_min=leftover,
                # Kaba uyum gostergesi (tam slot taramasi /api/availability'de).
                available_slots=len(s.staff_links)
                * max(0, (span - total_min) // grid_minutes),
                scanned_starts=4 * max(1, span // grid_minutes),
            )
        )

    ranked = rank_services(stats)
    rank_index = {r["serviceId"]: i for i, r in enumerate(ranked)}
    reason_by_id = {r["serviceId"]: r["reason"] for r in ranked}

    payload = sorted(
        (
            {
                "id": s.id,
                "categoryId": s.category_id,
                "name": s.name,
                "description": s.description,
                "price": s.price,
                "activeBeforeMin": s.active_before_min,
                "passiveMin": s.passive_min,
                "activeAfterMin": s.active_after_min,
                "bufferMin": s.buffer_min,
                "totalMin": s.active_before_min + s.passive_min + s.active_after_min + s.buffer_min,
                "shadowHostAllowed": s.shadow_host_allowed,
                "shadowGuestAllowed": s.shadow_guest_allowed,
                "recommendedRepeatDays": s.recommended_repeat_days,
                "staffCount": len(s.staff_links),
                "recommendationReason": reason_by_id.get(s.id),
            }
            for s in services
        ),
        key=lambda s: rank_index.get(s["id"], 999),
    )

    return {
        "date": date,
        "categories": [
            {"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon} for c in categories
        ],
        "services": payload,
    }


@router.get("/staff")
def list_staff(db: DbSession, serviceIds: str = Query(default="")) -> dict:
    """``serviceIds`` verilirse yalnizca paketin TAMAMINI yapabilen personel doner.

    Not: karsilastirma KUME kapsamasidir - ayni hizmetin listede iki kez
    gecmesi personeli elemez (bkz. README "Hata 2").
    """
    branch = get_default_branch(db)

    ids: set[int] = set()
    for part in (serviceIds or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) > 0:
            ids.add(int(part))

    staff = db.scalars(
        select(Staff)
        .options(selectinload(Staff.services), selectinload(Staff.working_hours))
        .where(Staff.branch_id == branch.id, Staff.is_active.is_(True))
        .order_by(Staff.display_order, Staff.id)
    ).all()

    filtered = (
        [s for s in staff if ids.issubset({link.service_id for link in s.services})]
        if ids
        else staff
    )

    return {
        "staff": [
            {
                "id": s.id,
                "name": s.name,
                "role": s.role,
                "photoUrl": s.photo_url,
                "serviceIds": [link.service_id for link in s.services],
                # Personelin bu paketteki en yavas carpani -> sure tahmini icin
                "speedFactor": (
                    max(
                        [link.speed_factor for link in s.services if link.service_id in ids]
                        or [1.0]
                    )
                    if ids
                    else 1.0
                ),
                "workingHours": [
                    {
                        "weekday": w.weekday,
                        "startMin": w.start_min,
                        "endMin": w.end_min,
                        "isWorking": w.is_working,
                    }
                    for w in s.working_hours
                ],
            }
            for s in filtered
        ]
    }
