"""
====================================================================
BILDIRIM KUYRUGU - okuma ve gonderim
====================================================================

Hatirlatma kurallari ekrani, kuyruktaki en yakin bildirimleri gosterir.
``/api/cron/sweep`` zamani gelen kayitlari ``deliver_due_notifications``
ile yapilandirilmis surucu (console / WhatsApp) uzerinden gonderir.

Gonderim uc adimdir:
  1. SAHIPLEN - zamani gelen kayitlar tek transaction'da ``SENDING``
     durumuna alinir (``FOR UPDATE SKIP LOCKED``). Ayni anda
     calisan iki bakim isi (zamanlayici + paneldeki dugme) ayni mesaji iki
     kez gondermez.
  2. GONDER - ag cagrisi transaction DISINDA yapilir; yavas bir WhatsApp
     yaniti veritabani kilidi tutmaz.
  3. KAYDET - basariliysa ``SENT``; degilse deneme sayisi artar ve geri
     cekilmeli (5, 10, 20, 40 dk) yeniden denenir, sinirda ``FAILED``.

Surec sahiplenme ile kaydetme arasinda cokerse kayit ``SENDING``de kalir;
sahiplenme suresi (``CLAIM_LEASE``) dolunca tekrar sahiplenilir. Bu,
nadiren ayni mesajin iki kez gitmesi pahasina mesajin hic gitmemesini
onler (en az bir kez teslim).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import config
from ..models import Appointment, ScheduledNotification
from ..time_utils import now_local, to_date_key
from . import messaging
from .privacy import MARKETING_DEDUPE_PREFIX, is_marketing_allowed
from .whatsapp_inbound import mark_phone_known

logger = logging.getLogger("aurora.notifications")

#: Bu kadar basarisiz denemeden sonra kayit FAILED olur.
MAX_DELIVERY_ATTEMPTS = 5
#: Ilk yeniden deneme gecikmesi; her denemede iki katina cikar.
RETRY_BASE = timedelta(minutes=5)
#: SENDING durumundaki bir kaydin sahiplenme suresi.
CLAIM_LEASE = timedelta(minutes=10)


def list_notification_queue(db: Session, take: int = 25) -> list[dict]:
    """Kuyruk: vade tarihine gore artan, en fazla ``take`` kayit."""
    rows = db.scalars(
        select(ScheduledNotification)
        .options(selectinload(ScheduledNotification.customer))
        .order_by(ScheduledNotification.due_at, ScheduledNotification.id)
        .limit(take)
    ).all()

    return [
        {
            "id": n.id,
            "channel": n.channel,
            "body": n.body,
            "status": n.status,
            "dueAt": n.due_at.isoformat(),
            "sentAt": n.sent_at.isoformat() if n.sent_at else None,
            "attempts": n.attempts,
            "lastError": n.last_error,
            "customer": {"firstName": n.customer.first_name, "phone": n.customer.phone},
        }
        for n in rows
    ]


def _claim_due(db: Session, now: datetime, limit: int) -> list[tuple[int, str, str]]:
    """Zamani gelen kayitlari SENDING'e alir; (id, telefon, govde) doner."""
    due_pending = and_(
        ScheduledNotification.status == "PENDING",
        ScheduledNotification.due_at <= now,
        or_(
            ScheduledNotification.next_attempt_at.is_(None),
            ScheduledNotification.next_attempt_at <= now,
        ),
    )
    stale_claim = and_(
        ScheduledNotification.status == "SENDING",
        ScheduledNotification.next_attempt_at <= now,
    )
    rows = db.scalars(
        select(ScheduledNotification)
        .options(selectinload(ScheduledNotification.customer))
        .where(or_(due_pending, stale_claim))
        .order_by(ScheduledNotification.due_at, ScheduledNotification.id)
        .limit(limit)
        # Baska bir bakim isinin kilitledigi satirlari atla.
        .with_for_update(skip_locked=True, of=ScheduledNotification)
    ).all()

    claimed = []
    for n in rows:
        # Onay kuyruga alindiktan SONRA geri alinmis olabilir (veya hesap
        # silinmis): ticari ileti gonderilmez, kayit iptal edilir.
        if n.dedupe_key.startswith(MARKETING_DEDUPE_PREFIX) and not is_marketing_allowed(
            n.customer
        ):
            n.status = "CANCELLED"
            continue
        # Yenileme daveti: musteri bu arada yeniden randevu almissa gereksiz.
        if n.dedupe_key.startswith(MARKETING_DEDUPE_PREFIX) and db.scalar(
            select(Appointment.id)
            .where(
                Appointment.customer_id == n.customer_id,
                Appointment.status.in_(("PENDING", "CONFIRMED")),
                Appointment.date >= to_date_key(now),
            )
            .limit(1)
        ):
            n.status = "CANCELLED"
            continue
        # "Yarin randevunuz var": yalnizca ONAYLI randevuya gider. Kapora
        # beklenirken (PENDING) atlanir; sonradan odenirse vakti gectiyse
        # yeniden kurulmaz (``deposit.mark_paid`` -> ``sync_pre_reminder``).
        if n.dedupe_key.startswith("pre:"):
            try:
                appointment_id = int(n.dedupe_key.split(":")[1])
            except (IndexError, ValueError):
                appointment_id = None
            if appointment_id is not None and db.scalar(
                select(Appointment.status).where(Appointment.id == appointment_id)
            ) == "PENDING":
                n.status = "CANCELLED"
                continue
        n.status = "SENDING"
        n.next_attempt_at = now + CLAIM_LEASE
        claimed.append((n.id, n.customer.phone, n.body))
        # Mesaj gitmeden ONCE: hatirlatmaya cevap yazan musteri karsilama almasin.
        mark_phone_known(db, n.customer.phone)
    db.commit()
    return claimed


def deliver_due_notifications(
    db: Session,
    now: datetime | None = None,
    sender: messaging.Sender | None = None,
) -> dict:
    """Zamani gelen bildirimleri gonderir. Bakim isinin (sweep) parcasi."""
    now = now or now_local()
    sender = sender or messaging.get_sender()

    # Baglanti kopuksa (QR yeniden okutulmali vb.) hic deneme yapilmaz:
    # aksi halde her kayit bosuna bir deneme hakki kaybederdi.
    ready, state = sender.is_ready()
    if not ready:
        logger.warning(
            "Bildirim gonderimi atlandi: %s surucusu hazir degil (%s)", sender.name, state
        )
        return {"sent": 0, "failed": 0, "skipped": True, "driverState": state}

    claimed = _claim_due(db, now, config.notification_batch_size)
    interval = config.whatsapp_send_interval_ms / 1000.0 if sender.name == "evolution" else 0

    sent = failed = 0
    for index, (notification_id, phone, body) in enumerate(claimed):
        if index and interval:
            time.sleep(interval)

        error: str | None = None
        try:
            sender.send(phone, body)
        except messaging.DeliveryError as exc:
            error = str(exc)
            logger.warning("Bildirim %s gonderilemedi: %s", notification_id, error)

        n = db.get(ScheduledNotification, notification_id)
        if error is None:
            n.status = "SENT"
            n.sent_at = now_local()
            n.next_attempt_at = None
            n.last_error = None
            sent += 1
        else:
            n.attempts = (n.attempts or 0) + 1
            n.last_error = error[:300]
            if n.attempts >= MAX_DELIVERY_ATTEMPTS:
                n.status = "FAILED"
                n.next_attempt_at = None
            else:
                n.status = "PENDING"
                n.next_attempt_at = now_local() + RETRY_BASE * (2 ** (n.attempts - 1))
            failed += 1
        # Her sonuc hemen kaydedilir: bir sonraki gonderim sirasinda
        # transaction (ve satir kilitleri) acik kalmaz.
        db.commit()

    return {"sent": sent, "failed": failed, "skipped": False, "driverState": state}
