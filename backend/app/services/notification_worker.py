"""
====================================================================
BILDIRIM ISCISI - kuyrugu uygulama icinde surekli bosaltir
====================================================================

Uygulama acikken arka planda calisir: her ``NOTIFICATION_POLL_SECONDS``
saniyede bir (varsayilan 60) zamani gelmis bildirimleri gonderir.
``kick()`` ile beklemeden uyandirilabilir (orn. randevu onayi).

Kuyruk veritabanindadir: sunucu kapaliyken vadesi gelen hatirlatmalar
kaybolmaz, sunucu tekrar acildiginda ilk turda gonderilir. WhatsApp
baglantisi kopuksa tur atlanir ve kayitlar deneme hakki kaybetmez
(``deliver_due_notifications``). Birden fazla worker ayni anda
calisabilir - sahiplenme ``FOR UPDATE SKIP LOCKED`` ile yapilir.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from ..config import config
from ..db import SessionLocal
from .notifications import deliver_due_notifications

logger = logging.getLogger("aurora.notification_worker")

_loop: asyncio.AbstractEventLoop | None = None
_wake: asyncio.Event | None = None


def _run_once() -> None:
    db = SessionLocal()
    try:
        result = deliver_due_notifications(db)
        if result["sent"] or result["failed"]:
            logger.info(
                "Bildirim kuyrugu: %s gonderildi, %s basarisiz", result["sent"], result["failed"]
            )
    except Exception:  # noqa: BLE001 - isci asla durmamali
        logger.exception("Bildirim kuyrugu islenemedi")
        db.rollback()
    finally:
        db.close()


async def _loop_forever(interval: float) -> None:
    assert _wake is not None
    while True:
        await asyncio.to_thread(_run_once)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(_wake.wait(), timeout=interval)
        _wake.clear()


def start() -> asyncio.Task | None:
    """Isciyi baslatir (lifespan icinden). Kapaliysa None doner."""
    global _loop, _wake
    if config.notification_poll_seconds <= 0:
        logger.info("Bildirim iscisi kapali (NOTIFICATION_POLL_SECONDS=0)")
        return None
    _loop = asyncio.get_running_loop()
    _wake = asyncio.Event()
    return asyncio.create_task(_loop_forever(config.notification_poll_seconds))


async def stop(task: asyncio.Task | None) -> None:
    global _loop, _wake
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    _loop = _wake = None


def kick() -> None:
    """Isciyi hemen uyandirir. Herhangi bir thread'den cagrilabilir; isci
    calismiyorsa (testler, cron'la calisan kurulum) hicbir sey yapmaz."""
    loop, wake = _loop, _wake
    if loop is None or wake is None or loop.is_closed():
        return
    loop.call_soon_threadsafe(wake.set)
