"""
====================================================================
KAPORA NOBETCISI - gecikme ve iade hatirlatmalari (Web Push)
====================================================================

``DEPOSIT_WATCH_SECONDS`` (varsayilan 60 sn) aralikla ``check_once`` calisir
(``whatsapp_health`` ile ayni desen). Otomatik IPTAL YOKTUR; yalnizca
yoneticilere push gider (``deposit`` tercihi acik olanlara).

  1) GECIKME: PENDING + AWAITING kapora, talepten ``deposit_deadline_minutes``
     sonra hala odenmediyse TEK uyari (``deposit_overdue_alerted_at``).
     Grup randevusunda grup basina tek uyari (toplam tutar).
  2) IADE: REFUND_DUE kapora icin iptalden 24 saat sonra, 48 saatlik sure
     dolunca ve sonra her 24 saatte bir (``deposit_refund_alerted_at``),
     "iade edildi" isaretlenene kadar.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ..config import config
from ..db import SessionLocal
from ..models import Appointment, AppointmentItem
from ..time_utils import format_date_tr, minutes_to_label, now_local
from . import deposit, push

logger = logging.getLogger("aurora.deposit_watch")

REMIND_EVERY = timedelta(hours=24)


def _elapsed_text(minutes: int) -> str:
    if minutes % 60 == 0 and minutes >= 60:
        return f"{minutes // 60} saattir"
    return f"{minutes} dakikadır"


def _client_name(a: Appointment) -> str:
    c = a.customer
    return f"{c.first_name} {c.last_name}".strip() if c.last_name else c.first_name


def next_refund_reminder(due_at: datetime, alerted_at: datetime | None) -> datetime:
    """Siradaki iade hatirlatma zamani: due-24sa, due, sonra due + 24sa*k."""
    first = due_at - REMIND_EVERY
    if alerted_at is None:
        return first
    if alerted_at < due_at:
        return due_at
    steps = int((alerted_at - due_at) // REMIND_EVERY) + 1
    return due_at + REMIND_EVERY * steps


def remaining_text(due_at: datetime, now: datetime) -> str:
    minutes = int((due_at - now).total_seconds() // 60)
    if minutes >= 0:
        hours = max(1, -(-minutes // 60))
        return f"{hours} saat kaldı"
    late_hours = max(1, (-minutes) // 60)
    return f"süre doldu ({late_hours} saat gecikti)"


def check_overdue(db: Session, now: datetime) -> int:
    settings = deposit.load_settings(db)
    cutoff = now - timedelta(minutes=settings.deadline_minutes)
    rows = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
        )
        .where(
            Appointment.status == "PENDING",
            Appointment.deposit_status == deposit.AWAITING,
            Appointment.deposit_overdue_alerted_at.is_(None),
            Appointment.deposit_requested_at.is_not(None),
            Appointment.deposit_requested_at <= cutoff,
        )
        .order_by(Appointment.id)
    ).all()
    alerts = 0
    done_groups: set[str] = set()
    for a in rows:
        gid = a.booking_group_id
        if gid and gid in done_groups:
            continue
        members = [m for m in rows if gid and m.booking_group_id == gid] or [a]
        # Atomik isaret: es zamanli iki tur ayni uyariyi iki kez gondermesin.
        claimed = 0
        for m in members:
            claimed += db.execute(
                update(Appointment)
                .where(Appointment.id == m.id, Appointment.deposit_overdue_alerted_at.is_(None))
                .values(deposit_overdue_alerted_at=now)
            ).rowcount
        db.commit()
        if gid:
            done_groups.add(gid)
        if not claimed:
            continue
        amount = sum(float(m.deposit_amount or 0) for m in members)
        push.notify_deposit(
            "Kapora bekleniyor",
            f"{_client_name(a)} · {format_date_tr(a.date)} {minutes_to_label(a.start_min)} · "
            f"{deposit.format_tl(amount)} — {_elapsed_text(settings.deadline_minutes)} onaylanmadı",
            tag=f"deposit-overdue-{gid or a.id}",
        )
        alerts += 1
    return alerts


def check_refunds(db: Session, now: datetime) -> int:
    rows = db.scalars(
        select(Appointment)
        .options(selectinload(Appointment.customer))
        .where(
            Appointment.deposit_status == deposit.REFUND_DUE,
            Appointment.deposit_refund_due_at.is_not(None),
        )
        .order_by(Appointment.id)
    ).all()
    alerts = 0
    for a in rows:
        due = a.deposit_refund_due_at
        previous = a.deposit_refund_alerted_at
        if now < next_refund_reminder(due, previous):
            continue
        claimed = db.execute(
            update(Appointment)
            .where(
                Appointment.id == a.id,
                Appointment.deposit_status == deposit.REFUND_DUE,
                Appointment.deposit_refund_alerted_at.is_(None)
                if previous is None
                else Appointment.deposit_refund_alerted_at == previous,
            )
            .values(deposit_refund_alerted_at=now)
        ).rowcount
        db.commit()
        if not claimed:
            continue
        push.notify_deposit(
            "Kapora iadesi bekliyor",
            f"Kapora iadesi bekliyor: {_client_name(a)} · {deposit.format_tl(a.deposit_amount)} · "
            f"iade süresi {remaining_text(due, now)}",
            tag=f"deposit-refund-{a.id}",
        )
        alerts += 1
    return alerts


def check_once(db: Session, now: datetime | None = None) -> dict:
    now = now or now_local()
    return {"overdue": check_overdue(db, now), "refunds": check_refunds(db, now)}


def _run_once() -> None:
    db = SessionLocal()
    try:
        check_once(db)
    except Exception:  # noqa: BLE001 - nobetci asla durmamali
        logger.exception("Kapora kontrolu basarisiz")
        db.rollback()
    finally:
        db.close()


async def _loop_forever(interval: float) -> None:
    while True:
        await asyncio.to_thread(_run_once)
        await asyncio.sleep(interval)


def start() -> asyncio.Task | None:
    if config.deposit_watch_seconds <= 0:
        return None
    return asyncio.create_task(_loop_forever(config.deposit_watch_seconds))


async def stop(task: asyncio.Task | None) -> None:
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
