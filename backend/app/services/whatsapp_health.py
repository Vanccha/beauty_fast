"""
====================================================================
WHATSAPP BAGLANTI NOBETCISI
====================================================================

Her ``WHATSAPP_HEALTH_SECONDS`` saniyede (varsayilan 300) Evolution
baglanti durumuna bakar (``/api/admin/messaging/status`` ile ayni
``EvolutionAdmin.state()``). Yalnizca ``NOTIFICATION_DRIVER=evolution``
iken calisir.

  * Kopma: ART ARDA 2 basarisiz kontrol gerekir (anlik dalgalanma
    uyari uretmez) -> yoneticilere TEK push. Kopukluk surerken tekrar
    etmez; her 6 saatte bir hatirlatma gider.
  * Yeniden baglanma: TEK push.
  * Durum (up/down, art arda hata, son uyari zamani) ``app_state``
    tablosunda tutulur; sunucu yeniden baslayinca ayni uyari tekrarlanmaz.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..config import config
from ..db import SessionLocal
from ..models import AppState
from ..time_utils import now_local
from . import messaging, push

logger = logging.getLogger("aurora.whatsapp_health")

STATE_KEY = "whatsapp_health"
FAILS_BEFORE_ALERT = 2
REMINDER_EVERY = timedelta(hours=6)


def _load(db: Session) -> dict:
    row = db.get(AppState, STATE_KEY)
    if row is None:
        return {"state": "unknown", "fails": 0, "lastAlertAt": None}
    try:
        data = json.loads(row.value)
    except ValueError:
        data = {}
    return {
        "state": data.get("state", "unknown"),
        "fails": int(data.get("fails", 0)),
        "lastAlertAt": data.get("lastAlertAt"),
    }


def _save(db: Session, data: dict) -> None:
    row = db.get(AppState, STATE_KEY)
    value = json.dumps(data)
    if row is None:
        db.add(AppState(key=STATE_KEY, value=value))
    else:
        row.value = value
    db.commit()


def _is_connected() -> bool | None:
    """True/False; surucu evolution degilse None."""
    admin = messaging.get_evolution_admin()
    if admin is None:
        return None
    try:
        return admin.state() == "open"
    except messaging.DeliveryError:
        return False
    except Exception:  # noqa: BLE001
        logger.exception("WhatsApp durumu okunamadi")
        return False


def check_once(db: Session, now: datetime | None = None) -> str | None:
    """Tek kontrol. Gonderilen uyari turunu doner: "down" | "reminder" |
    "up" | None."""
    connected = _is_connected()
    if connected is None:
        return None
    now = now or now_local()
    data = _load(db)
    alert: str | None = None

    if connected:
        if data["state"] == "down":
            alert = "up"
        data = {"state": "up", "fails": 0, "lastAlertAt": None}
    else:
        data["fails"] += 1
        if data["fails"] >= FAILS_BEFORE_ALERT:
            if data["state"] != "down":
                data["state"] = "down"
                data["lastAlertAt"] = now.isoformat()
                alert = "down"
            else:
                last = data.get("lastAlertAt")
                if not last or now - datetime.fromisoformat(last) >= REMINDER_EVERY:
                    data["lastAlertAt"] = now.isoformat()
                    alert = "reminder"

    _save(db, data)
    if alert:
        push.notify_whatsapp(connected=(alert == "up"))
    return alert


def _run_once() -> None:
    db = SessionLocal()
    try:
        check_once(db)
    except Exception:  # noqa: BLE001 - nobetci asla durmamali
        logger.exception("WhatsApp kontrolu basarisiz")
        db.rollback()
    finally:
        db.close()


async def _loop_forever(interval: float) -> None:
    while True:
        await asyncio.to_thread(_run_once)
        await asyncio.sleep(interval)


def start() -> asyncio.Task | None:
    if config.whatsapp_health_seconds <= 0 or config.notification_driver != "evolution":
        return None
    return asyncio.create_task(_loop_forever(config.whatsapp_health_seconds))


async def stop(task: asyncio.Task | None) -> None:
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
