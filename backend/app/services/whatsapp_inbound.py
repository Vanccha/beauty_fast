"""
====================================================================
WHATSAPP GELEN MESAJLAR - ilk mesajda karsilama
====================================================================

Evolution API, salon numarasina gelen/giden mesajlari webhook ile
``/api/webhooks/evolution`` ucuna bildirir. Bu modul olaylari yorumlar:

  * ``messages.upsert`` (fromMe=false) - biri salona yazdi. Kisi
    ``whatsapp_contact`` defterinde yoksa "ilk mesaj"dir: deftere eklenir
    ve karsilama mesaji gonderilir.
  * ``messages.upsert`` / ``send.message`` (fromMe=true) - salon o kisiye
    yazdi (personel telefondan ya da sistem). Kisi "tanidik" olur.
  * ``messages.set`` / ``chats.set`` - numara baglanirken telefondaki
    sohbet gecmisi. Bu kisiler de "tanidik"tir; halihazirda yazisilan
    musteriye sonradan karsilama gitmez.

Sistemin gonderdigi OTP ve hatirlatmalar da kisiyi tanidik yapar
(``mark_known``); hatirlatmaya "tesekkurler" diye cevap veren musteriye
karsilama gitmez.

Karsilama yalnizca bire bir sohbetlere gider; gruplar, durum (status)
paylasimlari ve kanallar yok sayilir. Son ``MAX_MESSAGE_AGE`` icindeki
mesajlar dikkate alinir: telefon uzun sure kapali kaldiysa biriken eski
mesajlara toplu karsilama gitmez.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import config
from ..errors import is_unique_violation
from ..models import Salon, WhatsappContact
from ..time_utils import now_local

logger = logging.getLogger("aurora.whatsapp")

DEFAULT_WELCOME = (
    "Merhaba! 👋 Mesajınız için teşekkürler, "
    "{salon} ekibi en kısa sürede size dönüş yapacak.\n"
    "\n"
    "Online randevu almak için: {link}"
)
PLACEHOLDERS = {
    "{salon}": "Salon adı",
    "{link}": "Online randevu sayfasının adresi",
}
MAX_WELCOME_LENGTH = 1000
#: Bundan eski gelen mesajlara karsilama gonderilmez.
MAX_MESSAGE_AGE = timedelta(minutes=10)

#: Webhook'ta dinlenen Evolution olaylari (bkz. ``EvolutionAdmin.set_webhook``).
WEBHOOK_EVENTS = ["MESSAGES_UPSERT", "SEND_MESSAGE", "MESSAGES_SET", "CHATS_SET"]

_IGNORED_SUFFIXES = ("@g.us", "@broadcast", "@newsletter")
_IGNORED_TYPES = {"protocolMessage", "reactionMessage", "senderKeyDistributionMessage"}


def contact_key(*jids: str | None) -> str | None:
    """Kisi anahtari: gercek numara (``905321234567``) varsa o, yoksa lid kimligi.

    WhatsApp bazi kisilerin numarasini ``...@lid`` kimligiyle gizler; Evolution
    bu durumda gercek numarayi ``remoteJidAlt`` alaninda gonderir (her zaman
    degil). Ayni kisinin iki farkli anahtarla iki kez karsilanmamasi icin
    numara her zaman tercih edilir.
    """
    lid = None
    for jid in jids:
        if not jid or not isinstance(jid, str):
            continue
        if jid.endswith("@s.whatsapp.net"):
            return jid.split("@", 1)[0].split(":", 1)[0]
        if jid.endswith("@lid") and lid is None:
            lid = jid
    return lid


def _is_direct_chat(jid: str | None) -> bool:
    return bool(jid) and not jid.endswith(_IGNORED_SUFFIXES) and jid != "status@broadcast"


def mark_known(db: Session, key: str | None, source: str) -> bool:
    """Kisiyi deftere ekler. Yeni eklendiyse True; zaten varsa False.

    Unique kisit sayesinde ayni kisi icin es zamanli iki istek varsa
    yalnizca biri True alir. Commit cagiranin sorumlulugundadir.
    """
    if not key:
        return False
    if db.scalar(select(WhatsappContact.id).where(WhatsappContact.contact_key == key)):
        return False
    try:
        with db.begin_nested():
            db.add(WhatsappContact(contact_key=key, source=source, first_seen_at=now_local()))
    except IntegrityError as error:
        if is_unique_violation(error):
            return False
        raise
    return True


def mark_phone_known(db: Session, phone: str) -> None:
    """Sistemin mesaj gonderdigi numarayi tanidik yapar (OTP, hatirlatma)."""
    from .messaging import to_whatsapp_number

    mark_known(db, to_whatsapp_number(phone), "OUTBOUND")


def render_welcome(salon: Salon) -> str:
    template = (salon.whatsapp_welcome_message or "").strip() or DEFAULT_WELCOME
    return template.replace("{salon}", salon.name).replace(
        "{link}", f"{config.public_site_url}/randevu"
    )


@dataclass(frozen=True)
class WelcomeJob:
    contact_id: int
    #: Yanitin gidecegi adres (numara ya da lid kimligi).
    reply_to: str
    text: str


def _history_jids(data) -> list[str]:
    """``messages.set`` / ``chats.set`` govdesinden sohbet kimliklerini toplar."""
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for field in ("messages", "chats", "data"):
            if isinstance(data.get(field), list):
                items.extend(data[field])
    jids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key") if isinstance(item.get("key"), dict) else {}
        candidates = (
            key.get("remoteJidAlt"),
            key.get("senderPn"),
            key.get("remoteJid"),
            item.get("remoteJid"),
            item.get("id"),
        )
        found = contact_key(*candidates)
        chat_id = key.get("remoteJid") or item.get("remoteJid") or item.get("id")
        if found and _is_direct_chat(chat_id):
            jids.append(found)
    return jids


def handle_event(db: Session, payload: dict, now: datetime | None = None) -> WelcomeJob | None:
    """Tek bir webhook olayini isler. Karsilama gerekiyorsa gorevi doner
    (gonderim, webhook yaniti geciktirilmesin diye ayrica yapilir)."""
    now = now or now_local()
    event = str(payload.get("event") or "").lower().replace("_", ".")
    data = payload.get("data")

    if event in ("messages.set", "chats.set"):
        added = sum(mark_known(db, key, "HISTORY") for key in _history_jids(data))
        db.commit()
        if added:
            logger.info("WhatsApp gecmisinden %s kisi tanidik olarak eklendi", added)
        return None

    if event not in ("messages.upsert", "send.message") or not isinstance(data, dict):
        return None

    key = data.get("key") if isinstance(data.get("key"), dict) else {}
    remote_jid = key.get("remoteJid")
    if not _is_direct_chat(remote_jid):
        return None
    who = contact_key(key.get("remoteJidAlt"), key.get("senderPn"), remote_jid)

    if key.get("fromMe") or event == "send.message":
        mark_known(db, who, "OUTBOUND")
        db.commit()
        return None

    if data.get("messageType") in _IGNORED_TYPES:
        return None
    try:
        sent_at = datetime.fromtimestamp(int(data.get("messageTimestamp") or 0))
    except (TypeError, ValueError, OverflowError, OSError):
        sent_at = None
    # Sunucu saat dilimi ile salon saati farkli olabilir; zaman damgasi UTC
    # epoch oldugu icin karsilastirma sistem saatiyle yapilir.
    if sent_at is None or datetime.now() - sent_at > MAX_MESSAGE_AGE:
        mark_known(db, who, "HISTORY")
        db.commit()
        return None

    if not mark_known(db, who, "INBOUND"):
        return None  # tanidik kisi

    salon = db.scalar(select(Salon).order_by(Salon.id).limit(1))
    contact_id = db.scalar(select(WhatsappContact.id).where(WhatsappContact.contact_key == who))
    db.commit()
    if salon is None or not salon.whatsapp_welcome_enabled:
        return None

    # Numara biliniyorsa numaraya, bilinmiyorsa (yalnizca lid) gelen adrese yanitla.
    reply_to = who if not who.endswith("@lid") else remote_jid
    return WelcomeJob(contact_id=contact_id, reply_to=reply_to, text=render_welcome(salon))


def send_welcome(job: WelcomeJob) -> None:
    """Karsilama mesajini gonderir (arka plan gorevi; kendi oturumunu acar)."""
    from ..db import SessionLocal
    from . import messaging

    try:
        messaging.get_sender().send(job.reply_to, job.text)
    except messaging.DeliveryError as error:
        # Yeniden denenmez: kisi tanidik olarak kaldi, bir sonraki mesajinda
        # personel cevap verir. Karsilamanin iki kez gitmesi daha kotu.
        logger.warning("Karsilama mesaji gonderilemedi (%s): %s", job.reply_to, error)
        return

    db = SessionLocal()
    try:
        contact = db.get(WhatsappContact, job.contact_id)
        if contact is not None:
            contact.welcomed_at = now_local()
            db.commit()
    finally:
        db.close()
