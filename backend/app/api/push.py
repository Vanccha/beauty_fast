"""Web Push uclari (personel oturumu gerekir).

  GET    /api/admin/push/public-key    - VAPID acik anahtari (+ push acik mi)
  GET    /api/admin/push/subscription  - bu cihazin aboneligi + tercihleri (?endpoint=)
  POST   /api/admin/push/subscribe     - abone ol / tercihleri koruyarak guncelle (upsert)
  DELETE /api/admin/push/subscribe     - bu cihazin aboneligini sil
  PUT    /api/admin/push/prefs         - olay tercihleri (cihaz basina)
  POST   /api/admin/push/test          - cagiranin tum cihazlarina deneme bildirimi
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ..deps import DbSession, StaffDep
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import PushSubscription
from ..services import push

router = APIRouter(prefix="/api/admin/push", tags=["push"], route_class=EnvelopeRoute)

_MANAGER_ROLES = push.MANAGER_ROLES


class KeysBody(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class SubscribeBody(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    keys: KeysBody


class EndpointBody(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)


class PrefsBody(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    newAppointment: bool | None = None
    cancelled: bool | None = None
    alerts: bool | None = None
    whatsapp: bool | None = None
    deposit: bool | None = None


def _prefs(sub: PushSubscription, role: str) -> dict:
    manager = role in _MANAGER_ROLES
    return {
        "newAppointment": sub.pref_new,
        "cancelled": sub.pref_cancel,
        # Yalnizca yonetici bu olaylari alabilir; diger roller icin hep false.
        "alerts": sub.pref_alerts and manager,
        "whatsapp": sub.pref_whatsapp and manager,
        "deposit": sub.pref_deposit and manager,
    }


def _own(db, staff_id: int, endpoint: str) -> PushSubscription | None:
    return db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint, PushSubscription.staff_id == staff_id
        )
    )


@router.get("/public-key")
def public_key(staff: StaffDep) -> dict:
    vapid = push.get_vapid()
    return {
        "enabled": vapid is not None,
        "publicKey": vapid.public_key if vapid else "",
        "canManage": staff.role in _MANAGER_ROLES,
    }


@router.get("/subscription")
def get_subscription(
    staff: StaffDep, db: DbSession, endpoint: str = Query(min_length=10, max_length=2000)
) -> dict:
    sub = _own(db, staff.id, endpoint)
    if sub is None:
        return {"subscribed": False, "prefs": None}
    return {"subscribed": True, "prefs": _prefs(sub, staff.role)}


@router.post("/subscribe")
def subscribe(body: SubscribeBody, request: Request, staff: StaffDep, db: DbSession) -> dict:
    if not push.is_enabled():
        raise AppError("VALIDATION", "Bildirimler sunucuda kapalı (VAPID anahtarı yok).", 409)
    user_agent = (request.headers.get("user-agent") or "")[:300] or None
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(
            staff_id=staff.id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            user_agent=user_agent,
        )
        db.add(sub)
    else:
        # Ayni cihaza baska bir personel giris yaptiysa abonelik ona gecer.
        if sub.staff_id != staff.id:
            sub.staff_id = staff.id
            sub.pref_new = sub.pref_cancel = sub.pref_alerts = sub.pref_whatsapp = True
            sub.pref_deposit = True
        sub.p256dh = body.keys.p256dh
        sub.auth = body.keys.auth
        sub.user_agent = user_agent
    db.commit()
    return {"subscribed": True, "prefs": _prefs(sub, staff.role)}


@router.delete("/subscribe")
def unsubscribe(body: EndpointBody, staff: StaffDep, db: DbSession) -> dict:
    db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.staff_id == staff.id
        )
    )
    db.commit()
    return {"subscribed": False}


@router.put("/prefs")
def put_prefs(body: PrefsBody, staff: StaffDep, db: DbSession) -> dict:
    sub = _own(db, staff.id, body.endpoint)
    if sub is None:
        raise AppError("NOT_FOUND", "Bu cihazda bildirim aboneliği yok.", 404)
    if body.newAppointment is not None:
        sub.pref_new = body.newAppointment
    if body.cancelled is not None:
        sub.pref_cancel = body.cancelled
    if staff.role in _MANAGER_ROLES:
        if body.alerts is not None:
            sub.pref_alerts = body.alerts
        if body.whatsapp is not None:
            sub.pref_whatsapp = body.whatsapp
        if body.deposit is not None:
            sub.pref_deposit = body.deposit
    db.commit()
    return {"subscribed": True, "prefs": _prefs(sub, staff.role)}


@router.post("/test")
def test_push(staff: StaffDep, db: DbSession) -> dict:
    if not push.is_enabled():
        raise AppError("VALIDATION", "Bildirimler sunucuda kapalı (VAPID anahtarı yok).", 409)
    subs = db.scalars(
        select(PushSubscription).where(PushSubscription.staff_id == staff.id)
    ).all()
    if not subs:
        raise AppError("NOT_FOUND", "Önce bu cihazda bildirimleri açın.", 404)
    payload = {
        "title": "Test bildirimi",
        "body": "Bildirimler bu cihazda çalışıyor.",
        "url": "/admin",
        "tag": "push-test",
    }
    result = {"sent": 0, "removed": 0, "failed": 0}
    for sub in subs:
        key = {"ok": "sent", "gone": "removed"}.get(push.send_one(db, sub, payload), "failed")
        result[key] += 1
    return result
