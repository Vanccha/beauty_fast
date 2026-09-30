"""Dis servislerden gelen bildirimler.

  POST /api/webhooks/evolution?token=... - WhatsApp gelen/giden mesaj olaylari

Evolution API bu ucu, ``EvolutionAdmin.set_webhook`` ile kurulan adrese
cagirir. Kimlik dogrulama URL'deki ``token`` ile yapilir
(``EVOLUTION_WEBHOOK_SECRET``). Hatali token 401 doner; Evolution 4xx
yanitlarini yeniden denemez.

Yanit hizli doner: karsilama mesaji arka planda gonderilir. Evolution'in
zaman asimi/yeniden denemesi ayni olayi tekrar getirirse ``whatsapp_contact``
uzerindeki unique kisit karsilamanin iki kez gitmesini engeller.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse

from ..config import config
from ..deps import DbSession
from ..services.whatsapp_inbound import handle_event, send_welcome

logger = logging.getLogger("aurora.webhooks")

router = APIRouter(tags=["webhooks"], include_in_schema=False)


@router.post("/api/webhooks/evolution")
async def evolution_webhook(
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    token: str = Query(default=""),
) -> JSONResponse:
    secret = config.evolution_webhook_secret
    if not secret or not hmac.compare_digest(token.encode("utf-8"), secret.encode("utf-8")):
        return JSONResponse({"ok": False}, status_code=401)

    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"ok": False}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False}, status_code=400)

    try:
        job = handle_event(db, payload)
    except Exception:  # noqa: BLE001 - tek bir bozuk olay webhook'u durdurmasin
        logger.exception("Evolution olayi islenemedi: %s", payload.get("event"))
        db.rollback()
        # 200 donulur: ayni bozuk olayin 10 kez yeniden denenmesinin faydasi yok.
        return JSONResponse({"ok": True, "handled": False})

    if job is not None:
        background.add_task(send_welcome, job)
    return JSONResponse({"ok": True, "welcome": job is not None})
