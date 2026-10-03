"""
====================================================================
WEB PUSH - admin paneli bildirimleri (PWA / masaustu tarayici)
====================================================================

Tasarim
  * Gonderim ASLA istek yolunu bloklamaz: ``notify_*`` fonksiyonlari isi
    kucuk bir thread havuzuna birakir; is kendi veritabani oturumunu acar,
    abonelikleri okur, ``pywebpush.webpush`` ile gonderir. Hatalar yalnizca
    loglanir.
  * Kim ne alir: OWNER/MANAGER her seyi; STAFF yalnizca kendisine atanmis
    randevularin "yeni" ve "iptal" bildirimlerini. "Uyari" ve "WhatsApp"
    olaylari yalnizca yoneticiye gider. Her abonelik ayrica kendi
    tercihlerine (pref_*) bakilarak suzulur.
  * 404/410 donen abonelik (tarayici aboneligi iptal etmis) silinir.
  * VAPID anahtarlari: ortamdan; gelistirmede (APP_ENV=development) eksikse
    ``backend/.vapid-dev.json`` dosyasina bir kez uretilir. Uretimde eksikse
    push kapali kalir (uyari logu), uygulama calismaya devam eder.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..config import BASE_DIR, config
from ..db import SessionLocal
from ..models import Allergy, Appointment, AppointmentItem, PushSubscription, Review, Staff
from ..time_utils import TR_MONTHS, minutes_to_label, now_local, parse_date_key

logger = logging.getLogger("aurora.push")

#: Olay turu -> abonelik tercih kolonu
EVENT_PREF = {
    "new": "pref_new",
    "cancel": "pref_cancel",
    "alert": "pref_alerts",
    "whatsapp": "pref_whatsapp",
    "deposit": "pref_deposit",
}
#: Yalnizca yoneticiye giden olaylar
MANAGER_ONLY = {"alert", "whatsapp", "deposit"}
MANAGER_ROLES = ("OWNER", "MANAGER")

DEV_KEY_FILE = BASE_DIR / ".vapid-dev.json"


@dataclass(frozen=True)
class Vapid:
    public_key: str
    private_key: str
    subject: str


_vapid_cache: Vapid | None = None
_vapid_resolved = False
_vapid_lock = Lock()


def get_vapid() -> Vapid | None:
    """VAPID anahtarlari; push kapaliysa None. Sonuc surec boyunca saklanir."""
    global _vapid_cache, _vapid_resolved
    with _vapid_lock:
        if _vapid_resolved:
            return _vapid_cache
        _vapid_resolved = True
        if config.vapid_public_key and config.vapid_private_key:
            _vapid_cache = Vapid(
                config.vapid_public_key, config.vapid_private_key, config.vapid_subject
            )
        elif config.app_env == "development":
            _vapid_cache = _load_or_create_dev_keys()
        else:
            logger.warning(
                "VAPID anahtarlari tanimli degil: Web Push kapali "
                "(python -m app.tools.vapid ile uretin)."
            )
        return _vapid_cache


def _load_or_create_dev_keys() -> Vapid | None:
    try:
        if DEV_KEY_FILE.exists():
            data = json.loads(DEV_KEY_FILE.read_text(encoding="utf-8"))
            return Vapid(data["public"], data["private"], config.vapid_subject)
        from ..tools.vapid import generate_keypair

        pair = generate_keypair()
        DEV_KEY_FILE.write_text(json.dumps(pair), encoding="utf-8")
        logger.info("Gelistirme icin VAPID anahtarlari uretildi: %s", DEV_KEY_FILE.name)
        return Vapid(pair["public"], pair["private"], config.vapid_subject)
    except Exception:  # noqa: BLE001 - push yoklugu uygulamayi durdurmaz
        logger.exception("Gelistirme VAPID anahtarlari hazirlanamadi")
        return None


def reset_vapid_cache() -> None:
    """Testler icin."""
    global _vapid_cache, _vapid_resolved
    with _vapid_lock:
        _vapid_cache, _vapid_resolved = None, False


def is_enabled() -> bool:
    return get_vapid() is not None


# ---------------------------------------------------------------------
# Gonderim
# ---------------------------------------------------------------------


def recipients(
    db: Session, event: str, assigned_staff_id: int | None = None
) -> list[PushSubscription]:
    """Olayi alacak abonelikler (rol + atama + tercih suzgeciyle)."""
    pref = EVENT_PREF[event]
    rows = db.execute(
        select(PushSubscription, Staff.role, Staff.id)
        .join(Staff, Staff.id == PushSubscription.staff_id)
        .where(Staff.is_active.is_(True), getattr(PushSubscription, pref).is_(True))
    ).all()
    out: list[PushSubscription] = []
    for sub, role, staff_id in rows:
        if role in MANAGER_ROLES:
            out.append(sub)
        elif (
            event not in MANAGER_ONLY
            and assigned_staff_id is not None
            and staff_id == assigned_staff_id
        ):
            out.append(sub)
    return out


def send_one(db: Session, sub: PushSubscription, payload: dict) -> str:
    """Tek aboneye gonderir. "ok" | "gone" (silindi) | "error"."""
    vapid = get_vapid()
    if vapid is None:
        return "error"
    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid.private_key,
            vapid_claims={"sub": vapid.subject},
            ttl=3600,
            timeout=10,
        )
    except WebPushException as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status in (404, 410):
            db.execute(delete(PushSubscription).where(PushSubscription.id == sub.id))
            db.commit()
            logger.info("Gecersiz push aboneligi silindi (HTTP %s)", status)
            return "gone"
        logger.warning("Push gonderilemedi (HTTP %s): %s", status, error)
        return "error"
    except Exception:  # noqa: BLE001
        logger.exception("Push gonderilemedi")
        return "error"
    sub.last_success_at = now_local()
    db.commit()
    return "ok"


def deliver(
    db: Session, event: str, payload: dict, assigned_staff_id: int | None = None
) -> dict:
    result = {"sent": 0, "removed": 0, "failed": 0}
    for sub in recipients(db, event, assigned_staff_id):
        outcome = send_one(db, sub, payload)
        key = {"ok": "sent", "gone": "removed"}.get(outcome, "failed")
        result[key] += 1
    return result


# ---------------------------------------------------------------------
# Arka plan calistirma
# ---------------------------------------------------------------------

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push")
#: Testler isi ayni thread'de, bekleyerek calistirir.
run_inline = False


def _run(job: Callable[[Session], None]) -> None:
    db = SessionLocal()
    try:
        job(db)
    except Exception:  # noqa: BLE001 - push hatasi asla yayilmaz
        logger.exception("Push isi basarisiz")
        db.rollback()
    finally:
        db.close()


def enqueue(job: Callable[[Session], None]) -> None:
    if not is_enabled():
        return
    if run_inline:
        _run(job)
        return
    try:
        _executor.submit(_run, job)
    except Exception:  # noqa: BLE001
        logger.exception("Push isi kuyruga alinamadi")


# ---------------------------------------------------------------------
# Olaylar
# ---------------------------------------------------------------------


def _date_label(date: str) -> str:
    d = parse_date_key(date)
    return f"{d.day} {TR_MONTHS[d.month - 1]}"


def _load_appointment(db: Session, appointment_id: int) -> Appointment | None:
    return db.scalar(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
            selectinload(Appointment.staff),
        )
        .where(Appointment.id == appointment_id)
    )


def _describe(a: Appointment) -> str:
    name = a.customer.first_name
    if a.customer.last_name:
        name = f"{name} {a.customer.last_name}"
    services = ", ".join(i.service.name for i in a.items)
    return (
        f"{name} · {_date_label(a.date)} {minutes_to_label(a.start_min)} · "
        f"{services} ({a.staff.name})"
    )


def notify_new_appointments(appointment_ids: list[int]) -> None:
    """Yeni randevu(lar) - commit'ten SONRA cagrilir."""
    ids = list(appointment_ids)

    def job(db: Session) -> None:
        for appointment_id in ids:
            a = _load_appointment(db, appointment_id)
            if a is None:
                continue
            body = _describe(a)
            has_allergy = db.scalar(
                select(Allergy.id).where(Allergy.customer_id == a.customer_id).limit(1)
            )
            if has_allergy:
                body += " ⚠ Alerji uyarısı"
            deliver(
                db,
                "new",
                {
                    "title": "Yeni randevu",
                    "body": body,
                    "url": f"/admin/takvim?date={a.date}",
                    "tag": f"appt-new-{a.id}",
                },
                assigned_staff_id=a.staff_id,
            )

    enqueue(job)


def notify_cancelled(appointment_id: int) -> None:
    def job(db: Session) -> None:
        a = _load_appointment(db, appointment_id)
        if a is None:
            return
        deliver(
            db,
            "cancel",
            {
                "title": "Randevu iptal edildi",
                "body": _describe(a),
                "url": f"/admin/takvim?date={a.date}",
                "tag": f"appt-cancel-{a.id}",
            },
            assigned_staff_id=a.staff_id,
        )

    enqueue(job)


def notify_low_review(review_id: int) -> None:
    """Dusuk puanli (<= 3) yeni yorum - yanit bekliyor."""

    def job(db: Session) -> None:
        review = db.get(Review, review_id)
        if review is None or review.rating > 3:
            return
        deliver(
            db,
            "alert",
            {
                "title": "Düşük puanlı yorum",
                "body": f"{review.author_name} {review.rating}/5 verdi — yanıt bekliyor",
                "url": "/admin/yorumlar",
                "tag": f"review-{review.id}",
            },
        )

    enqueue(job)


def notify_low_stock(items: list[tuple[str, float, str]]) -> None:
    """Kritik seviyenin altina dusen malzemeler: (ad, kalan, birim)."""
    items = list(items)
    if not items:
        return

    def job(db: Session) -> None:
        text = ", ".join(f"{n} ({q:g} {u})" for n, q, u in items)
        deliver(
            db,
            "alert",
            {
                "title": "Stok kritik seviyede",
                "body": text,
                "url": "/admin/stok",
                "tag": "stock-low",
            },
        )

    enqueue(job)


def notify_whatsapp(connected: bool) -> None:
    def job(db: Session) -> None:
        deliver(
            db,
            "whatsapp",
            {
                "title": "WhatsApp",
                "body": (
                    "WhatsApp bağlantısı yeniden kuruldu"
                    if connected
                    else "WhatsApp bağlantısı koptu — müşterilere kod ve hatırlatma gitmiyor"
                ),
                "url": "/admin/whatsapp",
                "tag": "whatsapp-health",
            },
        )

    enqueue(job)


def notify_deposit(title: str, body: str, tag: str, url: str = "/admin/takvim") -> None:
    """Kapora uyarilari (gecikme / iade bekliyor) - yalnizca yoneticiler,
    ``deposit`` tercihi acik olanlar."""

    def job(db: Session) -> None:
        deliver(db, "deposit", {"title": title, "body": body, "url": url, "tag": tag})

    enqueue(job)
