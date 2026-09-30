"""WhatsApp (Evolution API) gonderim katmani: istemci, OTP gonderimi ve
bildirim kuyrugu. Gercek mesaj GONDERILMEZ - Evolution API yerine
``httpx.MockTransport`` ve sahte surucu kullanilir."""

from __future__ import annotations

import dataclasses
import json
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, config, validate_config
from app.main import app
from app.models import ScheduledNotification
from app.services import messaging, notifications
from app.services.messaging import DeliveryError, EvolutionSender, SendResult, to_whatsapp_number
from app.time_utils import now_local


class FakeSender:
    name = "fake"

    def __init__(self, ready: bool = True, fail: bool = False) -> None:
        self.ready = ready
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    def send(self, phone: str, text: str) -> SendResult:
        if self.fail:
            raise DeliveryError("numara WhatsApp'ta yok")
        self.sent.append((phone, text))
        return SendResult(provider_id="fake-id")

    def is_ready(self) -> tuple[bool, str]:
        return self.ready, "open" if self.ready else "close"


@pytest.fixture()
def fake_sender(monkeypatch):
    sender = FakeSender()
    monkeypatch.setattr(messaging, "_sender", sender)
    return sender


# ---------------------------------------------------------------------
# Evolution istemcisi
# ---------------------------------------------------------------------


def _evolution(handler) -> EvolutionSender:
    client = httpx.Client(
        base_url="http://evolution.test",
        headers={"apikey": "gizli"},
        transport=httpx.MockTransport(handler),
    )
    return EvolutionSender("", "", "aurora", client=client)


@pytest.mark.parametrize(
    "raw, expected",
    [("5321234567", "905321234567"), ("05321234567", "905321234567"),
     ("905321234567", "905321234567")],
)
def test_phone_is_converted_to_whatsapp_format(raw, expected):
    assert to_whatsapp_number(raw) == expected


def test_evolution_send_request_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["apikey"] = request.headers.get("apikey")
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"key": {"id": "3EB0ABC", "fromMe": True}})

    result = _evolution(handler).send("5321234567", "Merhaba")
    assert seen == {
        "path": "/message/sendText/aurora",
        "apikey": "gizli",
        "body": {"number": "905321234567", "text": "Merhaba"},
    }
    assert result.provider_id == "3EB0ABC"


def test_evolution_error_status_raises_delivery_error():
    sender = _evolution(lambda request: httpx.Response(400, json={"exists": False}))
    with pytest.raises(DeliveryError):
        sender.send("5321234567", "Merhaba")


def test_evolution_network_error_raises_delivery_error():
    def handler(request):
        raise httpx.ConnectError("baglanti reddedildi")

    with pytest.raises(DeliveryError):
        _evolution(handler).send("5321234567", "Merhaba")


@pytest.mark.parametrize(
    "response, ready",
    [
        (httpx.Response(200, json={"instance": {"state": "open"}}), True),
        (httpx.Response(200, json={"instance": {"state": "connecting"}}), False),
        (httpx.Response(404, json={"error": "Not Found"}), False),
    ],
)
def test_evolution_readiness(response, ready):
    assert _evolution(lambda request: response).is_ready()[0] is ready


# ---------------------------------------------------------------------
# OTP gonderimi
# ---------------------------------------------------------------------


@pytest.fixture()
def client(salon):
    with TestClient(app) as test_client:
        yield test_client


def test_otp_is_sent_through_driver(client, fake_sender):
    response = client.post("/api/auth/otp/send", json={"phone": "5321010000"})
    assert response.status_code == 200
    [(phone, text)] = fake_sender.sent
    assert phone == "5321010000"
    assert "123456" in text and "Test Salon" in text


def test_otp_fails_fast_when_channel_not_ready(client, fake_sender):
    fake_sender.ready = False
    response = client.post("/api/auth/otp/send", json={"phone": "5321010000"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DELIVERY_FAILED"
    assert fake_sender.sent == []

    # Kanal kopukken yapilan istekler musterinin kod isteme hakkindan dusmez.
    fake_sender.ready = True
    for _ in range(5):
        assert client.post("/api/auth/otp/send", json={"phone": "5321010000"}).status_code == 200


def test_otp_delivery_failure_returns_502(client, fake_sender):
    fake_sender.fail = True
    response = client.post("/api/auth/otp/send", json={"phone": "5321010000"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "DELIVERY_FAILED"


# ---------------------------------------------------------------------
# Bildirim kuyrugu
# ---------------------------------------------------------------------


def _queue(db, salon, due_offset=timedelta(minutes=-1), **fields) -> int:
    n = ScheduledNotification(
        customer_id=salon["customer"].id,
        channel="WHATSAPP",
        body="Yarın 10:00 randevunuzu hatırlatırız.",
        due_at=now_local() + due_offset,
        dedupe_key=f"test-{uuid4().hex}",
        **fields,
    )
    db.add(n)
    db.commit()
    return n.id


def _reload(db, notification_id) -> ScheduledNotification:
    db.expire_all()
    return db.get(ScheduledNotification, notification_id)


def test_due_notification_is_sent(db, salon):
    sender = FakeSender()
    nid = _queue(db, salon)
    future = _queue(db, salon, due_offset=timedelta(hours=5), status="PENDING")

    result = notifications.deliver_due_notifications(db, sender=sender)
    assert result["sent"] == 1
    assert sender.sent == [("5321010000", "Yarın 10:00 randevunuzu hatırlatırız.")]
    assert _reload(db, nid).status == "SENT"
    assert _reload(db, future).status == "PENDING"


def test_failed_notification_is_retried_with_backoff_then_failed(db, salon):
    sender = FakeSender(fail=True)
    nid = _queue(db, salon)

    notifications.deliver_due_notifications(db, sender=sender)
    n = _reload(db, nid)
    assert (n.status, n.attempts) == ("PENDING", 1)
    assert n.last_error and n.next_attempt_at > now_local()

    # Geri cekilme suresi dolmadan tekrar denenmez.
    assert notifications.deliver_due_notifications(db, sender=sender)["failed"] == 0

    # Sure dolmus gibi davranarak kalan denemeleri tuket.
    for _ in range(notifications.MAX_DELIVERY_ATTEMPTS - 1):
        later = _reload(db, nid).next_attempt_at + timedelta(seconds=1)
        notifications.deliver_due_notifications(db, now=later, sender=sender)
    n = _reload(db, nid)
    assert (n.status, n.attempts) == ("FAILED", notifications.MAX_DELIVERY_ATTEMPTS)


def test_nothing_is_sent_while_channel_disconnected(db, salon):
    sender = FakeSender(ready=False)
    nid = _queue(db, salon)
    result = notifications.deliver_due_notifications(db, sender=sender)
    assert result["skipped"] is True
    n = _reload(db, nid)
    # Deneme hakki harcanmaz; baglanti gelince gonderilir.
    assert (n.status, n.attempts) == ("PENDING", 0)


def test_stale_claim_is_recovered(db, salon):
    """Surec sahiplenme ile kaydetme arasinda coktuyse kayit SENDING'de
    kalir; sahiplenme suresi dolunca yeniden gonderilir."""
    sender = FakeSender()
    stale = _queue(db, salon, status="SENDING", next_attempt_at=now_local() - timedelta(minutes=1))
    active = _queue(db, salon, status="SENDING", next_attempt_at=now_local() + timedelta(minutes=5))

    notifications.deliver_due_notifications(db, sender=sender)
    assert _reload(db, stale).status == "SENT"
    assert _reload(db, active).status == "SENDING"


# ---------------------------------------------------------------------
# Yapilandirma
# ---------------------------------------------------------------------


def test_evolution_driver_requires_settings():
    with pytest.raises(ConfigError, match="EVOLUTION_API_URL"):
        validate_config(dataclasses.replace(config, notification_driver="evolution"))

    validate_config(
        dataclasses.replace(
            config,
            notification_driver="evolution",
            evolution_api_url="http://localhost:8080",
            evolution_api_key="anahtar",
            evolution_instance="aurora",
        )
    )


def test_unknown_driver_is_rejected():
    with pytest.raises(ConfigError, match="tanınmıyor"):
        validate_config(dataclasses.replace(config, notification_driver="whatsap"))


# ---------------------------------------------------------------------
# Panel: QR ile baglama
# ---------------------------------------------------------------------


class FakeEvolution:
    """Evolution API'nin baglama uclarini taklit eden sahte sunucu."""

    def __init__(self, state: str = "missing") -> None:
        self.state = state
        self.calls: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        path = request.url.path
        if path.startswith("/instance/connectionState/"):
            if self.state == "missing":
                return httpx.Response(404, json={"error": "Not Found"})
            return httpx.Response(200, json={"instance": {"state": self.state}})
        if path == "/instance/create":
            self.state = "close"
            return httpx.Response(201, json={"instance": {"status": "created"}})
        if path.startswith("/instance/connect/"):
            self.state = "connecting"
            return httpx.Response(
                200, json={"base64": "data:image/png;base64,QUJD", "pairingCode": None}
            )
        if path.startswith("/instance/logout/"):
            self.state = "close"
            return httpx.Response(200, json={"status": "SUCCESS"})
        return httpx.Response(404)


@pytest.fixture()
def fake_evolution(monkeypatch):
    server = FakeEvolution()
    monkeypatch.setattr(messaging, "_sender", _evolution(server))
    return server


def _login(client, phone: str, password: str) -> None:
    response = client.post("/api/auth/staff/login", json={"phone": phone, "password": password})
    assert response.status_code == 200


def test_owner_can_connect_with_qr_and_logout(client, fake_evolution):
    _login(client, "5551110001", "admin123")  # OWNER

    status = client.get("/api/admin/messaging/status").json()["data"]
    assert status == {"driver": "evolution", "ready": False, "state": "missing"}

    qr = client.post("/api/admin/messaging/qr").json()["data"]
    assert qr["qr"].startswith("data:image/png;base64,")
    assert ("POST", "/instance/create") in fake_evolution.calls

    # Telefon QR'i okuttu.
    fake_evolution.state = "open"
    assert client.get("/api/admin/messaging/status").json()["data"]["ready"] is True
    already = client.post("/api/admin/messaging/qr").json()["data"]
    assert already == {"state": "open", "qr": None, "pairingCode": None}

    assert client.post("/api/admin/messaging/logout").json()["data"] == {"state": "close"}
    assert fake_evolution.state == "close"


def test_staff_role_cannot_see_whatsapp_status(client, fake_evolution):
    _login(client, "5551110002", "merve123")  # STAFF rolunde test personeli
    assert client.get("/api/admin/messaging/status").status_code == 403


def test_qr_requires_owner(client, db, salon, fake_evolution):
    salon["staff_b"].role = "MANAGER"
    db.merge(salon["staff_b"])
    db.commit()
    _login(client, "5551110002", "merve123")
    assert client.get("/api/admin/messaging/status").status_code == 200
    assert client.post("/api/admin/messaging/qr").status_code == 403
    assert client.post("/api/admin/messaging/logout").status_code == 403


def test_status_reports_console_driver(client, salon):
    _login(client, "5551110001", "admin123")
    data = client.get("/api/admin/messaging/status").json()["data"]
    assert data["driver"] == "console"
    assert client.post("/api/admin/messaging/qr").status_code == 409


def test_unreachable_gateway_is_reported(client, monkeypatch, salon):
    def handler(request):
        raise httpx.ConnectError("baglanti reddedildi")

    monkeypatch.setattr(messaging, "_sender", _evolution(handler))
    _login(client, "5551110001", "admin123")
    data = client.get("/api/admin/messaging/status").json()["data"]
    assert data["state"] == "unreachable" and data["ready"] is False
    assert client.post("/api/admin/messaging/qr").status_code == 502
