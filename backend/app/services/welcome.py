"""
====================================================================
KISISELLESTIRILMIS KARSILAMA + SALON ISTATISTIKLERI
====================================================================

"Tekrar hos geldin Ayşe, en son sac boyasi yaptirmistin, tekrar zamani
geldi mi?"

Metin UYDURULMAZ: son tamamlanmis randevunun hizmeti ve o hizmetin
``recommended_repeat_days`` degeri kullanilir. Tekrar zamani gelmemisse
farkli (ve durust) bir cumle kurulur; "hemen randevu al" baskisi
yapilmaz.

(``src/lib/server/welcome.ts`` + ``salon-stats.ts`` karsiligi.)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from ..core.loyalty import progress_to_next_tier
from ..models import Appointment, AppointmentItem, Customer, PortfolioItem, Staff, WorkingHour
from ..time_utils import (
    now_local,
    days_between_keys,
    format_date_tr,
    label_to_minutes,
    minutes_to_label,
    to_date_key,
    weekday_name_tr,
    weekday_of,
)
from .reviews import get_review_summary


def build_welcome(db: Session, customer_id: int, now: datetime | None = None) -> dict | None:
    now = now or now_local()
    customer = db.get(Customer, customer_id)
    if customer is None:
        return None

    today_key = to_date_key(now)

    last_completed = db.scalar(
        select(Appointment)
        .options(selectinload(Appointment.items).selectinload(AppointmentItem.service))
        .where(Appointment.customer_id == customer_id, Appointment.status == "COMPLETED")
        .order_by(Appointment.date.desc(), Appointment.start_min.desc())
        .limit(1)
    )

    upcoming = db.scalar(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.staff),
        )
        .where(
            Appointment.customer_id == customer_id,
            Appointment.status.in_(("PENDING", "CONFIRMED")),
            Appointment.date >= today_key,
        )
        .order_by(Appointment.date, Appointment.start_min)
        .limit(1)
    )

    tier_progress = progress_to_next_tier(customer.loyalty_points)

    upcoming_payload = (
        {
            "id": upcoming.id,
            "date": upcoming.date,
            "dateLabel": format_date_tr(upcoming.date),
            "startMin": upcoming.start_min,
            "serviceNames": [i.service.name for i in upcoming.items],
            "staffName": upcoming.staff.name,
        }
        if upcoming
        else None
    )

    if last_completed is None:
        return {
            "firstName": customer.first_name,
            "headline": f"Hoş geldin {customer.first_name}!",
            "subline": "İlk randevunu oluşturarak başlayabilirsin.",
            "lastVisit": None,
            "repeatServiceIds": [],
            "isDue": False,
            "tierProgress": tier_progress,
            "upcoming": upcoming_payload,
        }

    service_names = [i.service.name for i in last_completed.items]
    days_ago = max(0, days_between_keys(last_completed.date, today_key))

    # Tekrar araligi: paketteki hizmetlerin EN KISA onerisi
    repeat_days = [
        i.service.recommended_repeat_days
        for i in last_completed.items
        if i.service.recommended_repeat_days
    ]
    due_in_days = min(repeat_days) if repeat_days else None
    is_due = due_in_days is not None and days_ago >= due_in_days

    joined = " + ".join(service_names)
    if is_due:
        subline = f"En son {joined} yaptırmıştın ({days_ago} gün önce). Tekrar zamanı geldi mi?"
    elif due_in_days is not None:
        subline = (
            f"En son {joined} yaptırmıştın. Önerilen yenileme zamanına "
            f"{due_in_days - days_ago} gün var."
        )
    else:
        subline = f"En son {joined} yaptırmıştın ({days_ago} gün önce)."

    return {
        "firstName": customer.first_name,
        "headline": f"Tekrar hoş geldin {customer.first_name}!",
        "subline": subline,
        "lastVisit": {
            "date": last_completed.date,
            "dateLabel": format_date_tr(last_completed.date),
            "serviceNames": service_names,
            "daysAgo": days_ago,
        },
        "repeatServiceIds": [i.service_id for i in last_completed.items],
        "isDue": is_due,
        "tierProgress": tier_progress,
        "upcoming": upcoming_payload,
    }


def get_salon_stats(db: Session, branch_id: int) -> dict:
    """Vitrindeki "guven seridi" sayilari - hepsi gercek sayimlardan gelir.

    DURUSTLUK KURALI: hicbiri uydurulmaz; arayuz sifir olan bir sayiyi
    hic gostermez.
    """
    completed = db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.branch_id == branch_id, Appointment.status == "COMPLETED")
    )
    served_customers = db.scalar(
        select(func.count(func.distinct(Appointment.customer_id))).where(
            Appointment.branch_id == branch_id, Appointment.status == "COMPLETED"
        )
    )
    repeat_customers = db.scalar(
        select(func.count()).select_from(
            select(Appointment.customer_id)
            .where(Appointment.branch_id == branch_id, Appointment.status == "COMPLETED")
            .group_by(Appointment.customer_id)
            .having(func.count() > 1)
            .subquery()
        )
    )

    staff_count = db.scalar(
        select(func.count())
        .select_from(Staff)
        .where(Staff.branch_id == branch_id, Staff.is_active.is_(True))
    )
    portfolio_count = db.scalar(
        select(func.count())
        .select_from(PortfolioItem)
        .where(PortfolioItem.branch_id == branch_id, PortfolioItem.is_published.is_(True))
    )

    reviews = get_review_summary(db, branch_id)
    returning_rate = (
        round((repeat_customers or 0) / served_customers, 4) if served_customers else 0
    )

    return {
        "completedAppointments": completed or 0,
        "servedCustomers": served_customers or 0,
        "returningRate": returning_rate,
        # Eski ad, geriye donuk uyum icin korunuyor.
        "repeatRate": returning_rate,
        "staffCount": staff_count or 0,
        "portfolioCount": portfolio_count or 0,
        "averageRating": reviews["average"],
        "reviewCount": reviews["count"],
        "weeklyHours": _weekly_hours(db, branch_id),
    }


def get_opening_hours(db: Session, branch_id: int, now: datetime | None = None) -> list[dict]:
    """Haftalik acilis saatleri - vitrindeki "bize gel" bolumu icin.

    Cumartesi erken kapanis gibi ayrintilar elle yazilmaz; ``working_hour``
    tablosundan TURETILIR.
    """
    now = now or now_local()
    today = weekday_of(to_date_key(now))
    rows = _weekly_hours(db, branch_id)
    by_weekday = {r["weekday"]: r for r in rows}

    out: list[dict] = []
    for weekday in (1, 2, 3, 4, 5, 6, 0):  # Pazartesi'den Pazar'a
        row = by_weekday.get(weekday)
        is_open = bool(row and row["isOpen"])
        out.append(
            {
                "weekday": weekday,
                "label": weekday_name_tr(weekday),
                "isToday": weekday == today,
                "range": (
                    {
                        "startMin": label_to_minutes(row["startLabel"]),
                        "endMin": label_to_minutes(row["endLabel"]),
                    }
                    if is_open
                    else None
                ),
            }
        )
    return out


def _weekly_hours(db: Session, branch_id: int) -> list[dict]:
    """Haftalik acilis saatleri ``working_hour``dan TURETILIR.

    Cumartesi erken kapanis elle yazilmaz; veriden okunur.
    """
    rows = db.execute(
        select(
            WorkingHour.weekday,
            func.min(WorkingHour.start_min),
            func.max(WorkingHour.end_min),
            # Kac personelin o gun calistigi.
            func.sum(case((WorkingHour.is_working.is_(True), 1), else_=0)),
        )
        .join(Staff, Staff.id == WorkingHour.staff_id)
        .where(Staff.branch_id == branch_id, Staff.is_active.is_(True))
        .group_by(WorkingHour.weekday)
        .order_by(WorkingHour.weekday)
    ).all()

    out = []
    for weekday, start_min, end_min, working_count in rows:
        is_open = bool(working_count)
        out.append(
            {
                "weekday": weekday,
                "isOpen": is_open,
                "startLabel": minutes_to_label(start_min) if is_open else None,
                "endLabel": minutes_to_label(end_min) if is_open else None,
            }
        )
    return out
