"""Studyo gelir raporu (yalnizca salon sahibi).

Gelir = TAMAMLANAN randevularin ``total_price`` toplami (indirimler dusulmus,
kapora ayri bir gelir kalemi sayilmaz). Personel payi, personelin GUNCEL
kazanc yuzdesiyle hesaplanir; ``net`` = gelir - personel payi.
"""

from __future__ import annotations

import calendar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Appointment, AppointmentItem, Service, Staff


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def _bounds(year: int, month: int | None) -> tuple[str, str]:
    return _month_bounds(year, month) if month else (f"{year:04d}-01-01", f"{year:04d}-12-31")


def _previous(year: int, month: int | None) -> tuple[int, int | None]:
    if month is None:
        return year - 1, None
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _totals(db: Session, branch_id: int, start: str, end: str, commission_by_staff: dict[int, float]) -> dict:
    rows = db.execute(
        select(Appointment.staff_id, func.count(Appointment.id), func.coalesce(func.sum(Appointment.total_price), 0))
        .where(
            Appointment.branch_id == branch_id,
            Appointment.status == "COMPLETED",
            Appointment.date >= start,
            Appointment.date <= end,
        )
        .group_by(Appointment.staff_id)
    ).all()
    count = sum(int(n) for _, n, _ in rows)
    revenue = sum(float(t) for _, _, t in rows)
    commission = sum(float(t) * commission_by_staff.get(sid, 0) / 100 for sid, _, t in rows)
    return {"count": count, "revenue": revenue, "commission": round(commission, 2)}


def build_report(db: Session, branch_id: int, year: int, month: int | None) -> dict:
    staff_rows = db.scalars(select(Staff).where(Staff.branch_id == branch_id)).all()
    pct = {s.id: float(s.commission_percent or 0) for s in staff_rows}
    names = {s.id: s.name for s in staff_rows}

    start, end = _bounds(year, month)

    # --- Secili donem ozeti + onceki donemle kiyas -----------------------
    cur = _totals(db, branch_id, start, end, pct)
    py, pm = _previous(year, month)
    prev = _totals(db, branch_id, *_bounds(py, pm), pct)
    change = None if prev["revenue"] <= 0 else round((cur["revenue"] - prev["revenue"]) / prev["revenue"] * 100, 1)

    def status_count(status: str) -> int:
        return int(
            db.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.branch_id == branch_id,
                    Appointment.status == status,
                    Appointment.date >= start,
                    Appointment.date <= end,
                )
            )
            or 0
        )

    summary = {
        **cur,
        "net": round(cur["revenue"] - cur["commission"], 2),
        "average": round(cur["revenue"] / cur["count"], 2) if cur["count"] else 0,
        "cancelled": status_count("CANCELLED"),
        "noShow": status_count("NO_SHOW"),
        "previous": {**prev, "year": py, "month": pm},
        "changePercent": change,
    }

    # --- Yilin 12 ayi (gecmis aylar) ------------------------------------
    by_month = {m: {"month": m, "count": 0, "revenue": 0.0, "commission": 0.0} for m in range(1, 13)}
    month_expr = func.substr(Appointment.date, 6, 2).label("m")
    for sid, ym, n, total in db.execute(
        select(
            Appointment.staff_id,
            month_expr,
            func.count(Appointment.id),
            func.coalesce(func.sum(Appointment.total_price), 0),
        )
        .where(
            Appointment.branch_id == branch_id,
            Appointment.status == "COMPLETED",
            Appointment.date >= f"{year:04d}-01-01",
            Appointment.date <= f"{year:04d}-12-31",
        )
        .group_by(Appointment.staff_id, month_expr)
    ):
        row = by_month[int(ym)]
        row["count"] += int(n)
        row["revenue"] += float(total)
        row["commission"] += float(total) * pct.get(sid, 0) / 100
    months = [
        {**r, "commission": round(r["commission"], 2), "net": round(r["revenue"] - r["commission"], 2)}
        for r in by_month.values()
    ]

    # --- Gunluk kirilim (yalnizca ay secilince) --------------------------
    days: list[dict] = []
    if month:
        last = calendar.monthrange(year, month)[1]
        per_day = {
            d: (int(n), float(t))
            for d, n, t in db.execute(
                select(Appointment.date, func.count(Appointment.id), func.coalesce(func.sum(Appointment.total_price), 0))
                .where(
                    Appointment.branch_id == branch_id,
                    Appointment.status == "COMPLETED",
                    Appointment.date >= start,
                    Appointment.date <= end,
                )
                .group_by(Appointment.date)
            )
        }
        for day in range(1, last + 1):
            key = f"{year:04d}-{month:02d}-{day:02d}"
            n, t = per_day.get(key, (0, 0.0))
            days.append({"date": key, "count": n, "revenue": t})

    # --- Personel ve hizmet kirilimi ------------------------------------
    by_staff = []
    for sid, n, total in db.execute(
        select(Appointment.staff_id, func.count(Appointment.id), func.coalesce(func.sum(Appointment.total_price), 0))
        .where(
            Appointment.branch_id == branch_id,
            Appointment.status == "COMPLETED",
            Appointment.date >= start,
            Appointment.date <= end,
        )
        .group_by(Appointment.staff_id)
    ):
        share = float(total) * pct.get(sid, 0) / 100
        by_staff.append(
            {
                "staffId": sid,
                "name": names.get(sid, "—"),
                "count": int(n),
                "revenue": float(total),
                "commissionPercent": pct.get(sid, 0),
                "commission": round(share, 2),
            }
        )
    by_staff.sort(key=lambda r: r["revenue"], reverse=True)

    # Hizmet geliri: randevu toplami, kalem fiyatlarina oranla dagitilir
    # (indirim/ozel fiyat kalemlere yansitilmis olur; toplam rapora esittir).
    appts = {
        a.id: float(a.total_price)
        for a in db.scalars(
            select(Appointment).where(
                Appointment.branch_id == branch_id,
                Appointment.status == "COMPLETED",
                Appointment.date >= start,
                Appointment.date <= end,
            )
        )
    }
    by_service: dict[int, dict] = {}
    if appts:
        items: dict[int, list[tuple[int, float]]] = {}
        for appt_id, service_id, price in db.execute(
            select(AppointmentItem.appointment_id, AppointmentItem.service_id, AppointmentItem.price).where(
                AppointmentItem.appointment_id.in_(list(appts))
            )
        ):
            items.setdefault(appt_id, []).append((service_id, float(price)))
        service_names = dict(db.execute(select(Service.id, Service.name)).all())
        for appt_id, total in appts.items():
            lines = items.get(appt_id, [])
            base = sum(p for _, p in lines)
            for service_id, price in lines:
                part = total * (price / base) if base > 0 else total / len(lines)
                row = by_service.setdefault(
                    service_id, {"serviceId": service_id, "name": service_names.get(service_id, "—"), "count": 0, "revenue": 0.0}
                )
                row["count"] += 1
                row["revenue"] += part
    services = sorted(by_service.values(), key=lambda r: r["revenue"], reverse=True)
    for r in services:
        r["revenue"] = round(r["revenue"], 2)

    years = sorted(
        {int(y) for (y,) in db.execute(select(func.substr(Appointment.date, 1, 4)).where(Appointment.branch_id == branch_id).distinct())}
        | {year}
    )

    return {
        "year": year,
        "month": month,
        "availableYears": years,
        "summary": summary,
        "months": months,
        "days": days,
        "byStaff": by_staff,
        "byService": services,
    }
