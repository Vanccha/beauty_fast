"""WhatsApp'ta ilk mesaja karsilama: webhook, "tanidik kisi" kurallari ve
panel ayarlari. Gercek mesaj gonderilmez (sahte surucu)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import config
from app.main import app
from app.models import ScheduledNotification, WhatsappContact
from app.services import messaging, notifications, whatsapp_inbound
from app.services.messaging import SendResult
from app.time_utils import now_local

PHONE_JID = "905329998877@s.whatsapp.net"


class FakeSender:
    name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, phone: str, text: str) -> SendResult:
        self.sent.append((phone, text))
        return SendResult()

    def is_ready(self) -> tuple[bool, str]:
        return True, "open"


@pytest.fixture()
def sender(monkeypatch):
    fake = FakeSender()
    monkeypatch.setattr(messaging, "_sender", fake)
    return fake


@pytest.fixture()
def client(salon, sender):
    with TestClient(app) as test_client:
        yield test_client


def _event(
    remote_jid: str = PHONE_JID,
    *,
    from_me: bool = False,
    event: str = "messages.upsert",
    alt: str | None = None,
    age_seconds: int = 0,
    message_type: str = "conversation",
) -> dict:
    key = {"remoteJid": remote_jid, "fromMe": from_me, "id": f"MSG{time.time_ns()}"}
    if alt:
        key["remoteJidAlt"] = alt
    return {
        "event": event,
        "instance": "aurora",
        "data": {
            "key": key,
            "pushName": "Deniz",
            "message": {"conversation": "Merhaba, fiyat alabilir miyim?"},
            "messageType": message_type,
            "messageTimestamp": int(time.time()) - age_seconds,
        },
        "date_time": "2026-09-30T14:00:00.000Z",
        "sender": "905551112233@s.whatsapp.net",
        "apikey": "instance-token",
    }


def _post(client, payload, token: str | None = None):
    token = config.evolution_webhook_secret if token is None else token
    return client.post(f"/api/webhooks/evolution?token={token}", json=payload)


# ---------------------------------------------------------------------
# Webhook ve ilk mesaj
# ---------------------------------------------------------------------


def test_webhook_rejects_wrong_token(client, sender):
    assert _post(client, _event(), token="yanlis").status_code == 401
    assert sender.sent == []


def test_first_message_gets_welcome_once(client, sender, db):
    assert _post(client, _event()).json()["welcome"] is True
    [(to, text)] = sender.sent
    assert to == "905329998877"
    assert "Test Salon" in text and f"{config.public_site_url}/randevu" in text

    contact = db.scalar(select(WhatsappContact).where(WhatsappContact.contact_key == to))
    assert contact.source == "INBOUND" and contact.welcomed_at is not None
    db.rollback()  # test oturumunun okuma transaction'ini kapat

    # Ikinci mesaj ve Evolution'in ayni olayi yeniden denemesi: tekrar gitmez.
    assert _post(client, _event()).json()["welcome"] is False
    assert len(sender.sent) == 1


def test_contact_we_wrote_to_is_not_welcomed(client, sender):
    """Personel telefondan yazdiysa (fromMe) kisi tanidiktir."""
    _post(client, _event(from_me=True))
    _post(client, _event(event="send.message", remote_jid="905320000001@s.whatsapp.net"))
    _post(client, _event())
    _post(client, _event("905320000001@s.whatsapp.net"))
    assert sender.sent == []


def test_otp_recipient_replying_is_not_welcomed(client, sender):
    """Kod alan musteri "tesekkurler" diye yazarsa karsilama almaz."""
    assert client.post("/api/auth/otp/send", json={"phone": "5329998877"}).status_code == 200
    sender.sent.clear()
    _post(client, _event())
    assert sender.sent == []


def test_reminder_recipient_replying_is_not_welcomed(client, sender, db, salon):
    db.add(
        ScheduledNotification(
            customer_id=salon["customer"].id, channel="WHATSAPP", body="Yarın randevunuz var.",
            due_at=now_local(), dedupe_key="hatirlatma-1",
        )
    )
    db.commit()
    notifications.deliver_due_notifications(db, sender=sender)
    sender.sent.clear()

    _post(client, _event("905321010000@s.whatsapp.net"))  # salon["customer"]
    assert sender.sent == []


def test_hidden_number_uses_real_number_when_available(client, sender):
    """WhatsApp numarayi @lid ile gizlese de gercek numara biliniyorsa
    anahtar numaradir: ayni kisi iki kez karsilanmaz."""
    _post(client, _event("123456789012345@lid", alt=PHONE_JID))
    _post(client, _event(PHONE_JID))
    assert [to for to, _ in sender.sent] == ["905329998877"]


def test_hidden_number_without_alt_replies_to_lid(client, sender):
    _post(client, _event("123456789012345@lid"))
    assert [to for to, _ in sender.sent] == ["123456789012345@lid"]


@pytest.mark.parametrize(
    "jid",
    ["120363012345678901@g.us", "status@broadcast", "120363000000000000@newsletter"],
)
def test_groups_status_and_channels_are_ignored(client, sender, jid):
    _post(client, _event(jid))
    assert sender.sent == []


def test_old_messages_are_not_welcomed(client, sender):
    """Telefon kapaliyken biriken eski mesajlara toplu karsilama gitmez."""
    _post(client, _event(age_seconds=3600))
    assert sender.sent == []
    _post(client, _event())  # yeni mesaj da gitmez: kisi artik tanidik
    assert sender.sent == []


def test_reactions_do_not_trigger_welcome(client, sender):
    _post(client, _event(message_type="reactionMessage"))
    assert sender.sent == []


def test_history_sync_marks_existing_chats_known(client, sender):
    """Numara baglanirken telefondaki mevcut sohbetler tanidik sayilir."""
    _post(
        client,
        {
            "event": "chats.set",
            "data": [{"id": PHONE_JID}, {"remoteJid": "905320000002@s.whatsapp.net"}],
        },
    )
    _post(
        client,
        {
            "event": "messages.set",
            "data": {"messages": [{"key": {"remoteJid": "905320000003@s.whatsapp.net"}}]},
        },
    )
    for jid in (PHONE_JID, "905320000002@s.whatsapp.net", "905320000003@s.whatsapp.net"):
        _post(client, _event(jid))
    assert sender.sent == []


def test_disabled_welcome_records_contact_without_sending(client, sender, db, salon):
    salon["salon"].whatsapp_welcome_enabled = False
    db.merge(salon["salon"])
    db.commit()

    assert _post(client, _event()).json()["welcome"] is False
    assert sender.sent == []
    # Sonradan acilsa bile bu kisi artik "ilk mesaj" degildir.
    assert db.scalar(select(WhatsappContact).where(WhatsappContact.contact_key == "905329998877"))


def test_malformed_event_does_not_break_webhook(client, sender):
    response = _post(client, {"event": "messages.upsert", "data": "bozuk"})
    assert response.status_code == 200
    assert sender.sent == []


def test_contact_key_prefers_phone():
    assert whatsapp_inbound.contact_key("1@lid", PHONE_JID) == "905329998877"
    assert whatsapp_inbound.contact_key("905329998877:12@s.whatsapp.net") == "905329998877"
    assert whatsapp_inbound.contact_key("1@lid") == "1@lid"
    assert whatsapp_inbound.contact_key(None) is None


# ---------------------------------------------------------------------
# Panel ayarlari
# ---------------------------------------------------------------------


def _login(client, phone="5551110001", password="admin123"):
    assert client.post(
        "/api/auth/staff/login", json={"phone": phone, "password": password}
    ).status_code == 200


def test_welcome_settings_roundtrip(client, sender):
    _login(client)
    data = client.get("/api/admin/messaging/welcome").json()["data"]
    assert data["enabled"] is True and data["message"] is None
    assert "Test Salon" in data["preview"]

    custom = "Hoş geldiniz! {salon} için randevu: {link}"
    saved = client.put(
        "/api/admin/messaging/welcome", json={"enabled": True, "message": custom}
    ).json()["data"]
    assert saved["message"] == custom
    link = f"{config.public_site_url}/randevu"
    assert saved["preview"] == f"Hoş geldiniz! Test Salon için randevu: {link}"

    _post(client, _event())
    assert sender.sent[-1][1] == saved["preview"]

    # Bos metin varsayilana doner; kapatma kaydedilir.
    reset = client.put(
        "/api/admin/messaging/welcome", json={"enabled": False, "message": ""}
    ).json()["data"]
    assert reset["message"] is None and reset["enabled"] is False


def test_welcome_settings_require_manager(client):
    _login(client, "5551110002", "merve123")  # STAFF
    assert client.get("/api/admin/messaging/welcome").status_code == 403
    assert client.put(
        "/api/admin/messaging/welcome", json={"enabled": False}
    ).status_code == 403


def test_welcome_message_length_is_limited(client):
    _login(client)
    too_long = "a" * (whatsapp_inbound.MAX_WELCOME_LENGTH + 1)
    response = client.put(
        "/api/admin/messaging/welcome", json={"enabled": True, "message": too_long}
    )
    assert response.status_code == 400
