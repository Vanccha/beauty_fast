"""
====================================================================
API ZARFI
====================================================================

Tum uclar ayni yanit bicimini kullanir (Next.js surumuyle birebir ayni
sozlesme, boylece mevcut istemci kodu degismeden calisir):

    basari : {"ok": true,  "data": ...}
    hata   : {"ok": false, "error": {"code", "message", "details"}}

``code`` alani istemci icin makine-okunur sozlesmedir:
``MEMBERSHIP_REQUIRED`` giris modalini acar, ``SLOT_TAKEN`` slot
izgarasini tazeler, ``VERSION_MISMATCH`` surukle-birak hareketini
geri alir.

Zarfi ``EnvelopeRoute`` uygular: uc fonksiyonlari duz ``dict`` doner,
sarmalayici bunu ``{"ok": true, "data": ...}`` haline getirir. Cerez
yazan uclar ``response: Response`` parametresini kullanmaya devam
edebilir - basliklar korunur.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from .errors import AppError, is_unique_violation

logger = logging.getLogger("aurora.api")


def ok(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data}, status_code=status)


def fail(code: str, message: str, status: int = 400, details: Any = None) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": code, "message": message, "details": details}},
        status_code=status,
    )


class EnvelopeRoute(APIRoute):
    """Basarili JSON yanitlarini ``{ok, data}`` zarfina sarar."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def envelope_handler(request: Request) -> Response:
            response = await original(request)

            # Musteri oturumu kayan yenilemeyle uzatildiysa cerezi de tazele.
            renew = getattr(request.state, "customer_cookie_renew", None)
            if renew:
                from .auth.sessions import CUSTOMER_COOKIE, _set_cookie

                _set_cookie(response, CUSTOMER_COOKIE, renew[0], renew[1])

            content_type = response.headers.get("content-type", "")
            body = getattr(response, "body", None)
            if not content_type.startswith("application/json") or body is None:
                return response

            try:
                payload = json.loads(body)
            except (ValueError, TypeError):  # pragma: no cover - beklenmeyen govde
                return response

            # Zaten zarflanmis (orn. exception handler ciktisi) ise dokunma.
            if isinstance(payload, dict) and "ok" in payload and len(payload) <= 2:
                return response

            wrapped = json.dumps({"ok": True, "data": payload}).encode("utf-8")
            response.body = wrapped
            response.headers["content-length"] = str(len(wrapped))
            return response

        return envelope_handler


# ---------------------------------------------------------------------
# Hata isleyicileri
# ---------------------------------------------------------------------


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return fail(exc.code, exc.message, exc.status, exc.details)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return fail("VALIDATION", "Gönderilen veriler geçersiz.", 400, json.loads(
        json.dumps(exc.errors(), default=str)
    ))


async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if is_unique_violation(exc):
        return fail("SLOT_TAKEN", "Bu kayıt zaten mevcut.", 409)
    # Beklenmeyen hatalarda istemciye ic ayrinti SIZDIRILMAZ.
    logger.exception("[api] beklenmeyen hata", exc_info=exc)
    return fail("INTERNAL", "Beklenmeyen bir hata oluştu.", 500)
