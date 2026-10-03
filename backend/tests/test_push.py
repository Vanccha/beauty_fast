"""Web Push: abonelik uclari, kime ne gittigi, tercihler, 410 temizligi,
WhatsApp nobetcisi ve VAPID'siz calisma. ``pywebpush.webpush`` taklit edilir."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pywebpush import WebPushException
from sqlalchemy import select

from app.auth.password import hash_password
from app.main import app
from app.models import Allergy, AppState, InventoryItem, PushSubscription, Review, Staff
from app.services import messaging, push, whatsapp_health
from app.services.stock import adjust_stock
from app.time_utils import now_local
from tests.test_book_for_other import BOOKER, book, data_of, fake_sender, login  # noqa: F401
from tests.test_booking_cancellation import _cancel


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class WebPushSpy:
    def __init__(self):
        self.calls: list[dict] = []
        self.fail_status: dict[str, int] = {}

    def __call__(self, subscription_info, data, **kwargs):
        endpoint = subscription_info["endpoint"]
        status = self.fail_status.get(endpoint)
        if status:
            raise WebPushException("boom", response=FakeResponse(status))
        self.calls.append({"endpoint": endpoint, "payload": json.loads(data), **kwargs})

    def endpoints(self):
        return sorted(c["endpoint"] for c in self.calls)


@pytest.fixture()
def spy(monkeypatch):
    from app.tools.vapid import generate_keypair

    pair = generate_keypair()
    monkeypatch.setattr(
        push, "get_vapid", lambda: push.Vapid(pair["public"], pair["private"], "mailto:t@t.t")
    )
    monkeypatch.setattr(push, "run_inline", True)
    s = WebPushSpy()
    monkeypatch.setattr(push, "webpush", s)
    return s


def ep(name: str) -> str:
    return f"https://push.example.test/{name}"


def sub_body(name: str) -> dict:
    return {"endpoint": ep(name), "keys": {"p256dh": "p" * 20, "auth": "a" * 8}}


def staff_client(phone: str, password: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/staff/login", json={"phone": phone, "password": password})
    assert r.status_code == 200
    return c


@pytest.fixture()
def team(salon, db, spy):
    """owner (Elif), staff_b (Merve), manager, other staff - hepsi abone."""
    manager = Staff(
        branch_id=salon["branch"].id, name="Mudur", phone="5551110005",
        password_hash=hash_password("mudur123"), role="MANAGER", display_order=2,
    )
    other = Staff(
        branch_id=salon["branch"].id, name="Diger", phone="5551110006",
        password_hash=hash_password("diger123"), role="STAFF", display_order=3,
    )
    db.add_all([manager, other])
    db.commit()
    clients = {
        "owner": staff_client("5551110001", "admin123"),
        "staff_b": staff_client("5551110002", "merve123"),
        "manager": staff_client("5551110005", "mudur123"),
        "other": staff_client("5551110006", "diger123"),
    }
    for name, c in clients.items():
        data_of(c.post("/api/admin/push/subscribe", json=sub_body(name)))
    spy.calls.clear()
    return clients


# ------------------------------------------------------------- uclar


def test_endpoints_require_staff(salon, spy):
    with TestClient(app) as c:
        for method, path in (
            ("get", "/api/admin/push/public-key"),
            ("post", "/api/admin/push/subscribe"),
            ("put", "/api/admin/push/prefs"),
            ("post", "/api/admin/push/test"),
        ):
            kwargs = {} if method == "get" else {"json": {}}
            r = getattr(c, method)(path, **kwargs)
            assert r.status_code == 401, path


def test_subscribe_upsert_prefs_unsubscribe(salon, db, spy):
    owner = staff_client("5551110001", "admin123")
    key = data_of(owner.get("/api/admin/push/public-key"))
    assert key["enabled"] and key["publicKey"] and key["canManage"]

    res = data_of(owner.post("/api/admin/push/subscribe", json=sub_body("x")))
    assert res["subscribed"] and res["prefs"] == {
        "newAppointment": True, "cancelled": True, "alerts": True, "whatsapp": True, "deposit": True,
    }
    # ayni endpoint tekrar -> tek satir
    data_of(owner.post("/api/admin/push/subscribe", json=sub_body("x")))
    assert len(db.scalars(select(PushSubscription)).all()) == 1

    prefs = data_of(
        owner.put("/api/admin/push/prefs", json={"endpoint": ep("x"), "cancelled": False})
    )
    assert prefs["prefs"]["cancelled"] is False and prefs["prefs"]["newAppointment"] is True
    got = data_of(owner.get("/api/admin/push/subscription", params={"endpoint": ep("x")}))
    assert got["subscribed"] and got["prefs"]["cancelled"] is False

    out = data_of(owner.request("DELETE", "/api/admin/push/subscribe", json={"endpoint": ep("x")}))
    assert out == {"subscribed": False}
    db.expire_all()
    assert db.scalars(select(PushSubscription)).all() == []
    r = owner.put("/api/admin/push/prefs", json={"endpoint": ep("x"), "alerts": False})
    assert r.status_code == 404


def test_regular_staff_cannot_enable_manager_events(salon, spy):
    c = staff_client("5551110002", "merve123")
    assert data_of(c.get("/api/admin/push/public-key"))["canManage"] is False
    data_of(c.post("/api/admin/push/subscribe", json=sub_body("m")))
    res = data_of(
        c.put("/api/admin/push/prefs", json={"endpoint": ep("m"), "alerts": True, "whatsapp": True})
    )
    assert res["prefs"]["alerts"] is False and res["prefs"]["whatsapp"] is False


def test_test_push_goes_to_own_devices_only(team, spy):
    res = data_of(team["owner"].post("/api/admin/push/test"))
    assert res["sent"] == 1
    assert spy.endpoints() == [ep("owner")]
    assert spy.calls[0]["payload"]["title"] == "Test bildirimi"


# ------------------------------------------------------------- olaylar


def test_new_appointment_goes_to_managers_and_assigned_staff(team, salon, spy, fake_sender, db):
    db.add(Allergy(customer_id=salon["customer"].id, label="Lateks", severity="HIGH"))
    db.commit()
    with TestClient(app) as cust:
        login(cust, BOOKER)
        data_of(book(cust, salon, staff="staff_b"))
    assert spy.endpoints() == sorted([ep("owner"), ep("manager"), ep("staff_b")])
    payload = spy.calls[0]["payload"]
    assert payload["title"] == "Yeni randevu"
    assert "Ayşe" in payload["body"] and "Manikür" in payload["body"]
    assert "(Merve)" in payload["body"]
    assert "⚠ Alerji uyarısı" in payload["body"]
    assert payload["url"].startswith("/admin/takvim?date=")

    spy.calls.clear()
    with TestClient(app) as cust:
        login(cust, BOOKER)
        data_of(book(cust, salon, staff="staff_a", start=720))
    # Merve'ye (atanmayan) ve diger personele gitmez
    assert spy.endpoints() == sorted([ep("owner"), ep("manager")])


def test_cancellation_push_and_prefs_respected(team, salon, spy, fake_sender, db):
    data_of(
        team["owner"].put("/api/admin/push/prefs", json={"endpoint": ep("owner"), "cancelled": False})
    )
    with TestClient(app) as cust:
        login(cust, BOOKER)
        appt = data_of(book(cust, salon, staff="staff_b"))["appointment"]
        spy.calls.clear()
        data_of(_cancel(cust, appt["id"]))
    assert spy.endpoints() == sorted([ep("manager"), ep("staff_b")])  # owner kapatmisti
    assert spy.calls[0]["payload"]["title"] == "Randevu iptal edildi"


def test_gone_subscription_is_removed(team, salon, spy, fake_sender, db):
    spy.fail_status[ep("manager")] = 410
    spy.fail_status[ep("staff_b")] = 500  # gecici hata: silinmez
    with TestClient(app) as cust:
        login(cust, BOOKER)
        data_of(book(cust, salon, staff="staff_b"))
    db.expire_all()
    left = {s.endpoint for s in db.scalars(select(PushSubscription))}
    assert ep("manager") not in left and ep("staff_b") in left and ep("owner") in left


def test_low_review_and_stock_alerts_go_to_managers_only(team, salon, spy, db):
    review = Review(
        branch_id=salon["branch"].id, author_name="Ayşe K.", rating=2,
        comment="Memnun kalmadım ama",
    )
    item = InventoryItem(
        branch_id=salon["branch"].id, name="Oksidan", unit="ml", quantity=500, critical_level=300
    )
    db.add_all([review, item])
    db.commit()
    push.notify_low_review(review.id)
    assert spy.endpoints() == sorted([ep("owner"), ep("manager")])
    spy.calls.clear()
    adjust_stock(db, item.id, -100)  # 400: hala ustunde
    assert spy.calls == []
    adjust_stock(db, item.id, -150)  # 250: kritik altina indi
    assert spy.endpoints() == sorted([ep("owner"), ep("manager")])
    assert "Oksidan" in spy.calls[0]["payload"]["body"]
    spy.calls.clear()
    adjust_stock(db, item.id, -10)  # zaten altinda: tekrar bildirim yok
    assert spy.calls == []


def test_missing_vapid_disables_push_without_crash(salon, db, fake_sender, monkeypatch):
    monkeypatch.setattr(push, "get_vapid", lambda: None)
    called = []
    monkeypatch.setattr(push, "webpush", lambda *a, **k: called.append(1))
    owner = staff_client("5551110001", "admin123")
    key = data_of(owner.get("/api/admin/push/public-key"))
    assert key == {"enabled": False, "publicKey": "", "canManage": True}
    assert owner.post("/api/admin/push/subscribe", json=sub_body("z")).status_code == 409
    assert owner.post("/api/admin/push/test").status_code == 409
    with TestClient(app) as cust:
        login(cust, BOOKER)
        data_of(book(cust, salon))
    assert called == []


def test_vapid_resolution_without_keys_in_test_env():
    push.reset_vapid_cache()
    try:
        assert push.get_vapid() is None  # APP_ENV=test: dosya uretilmez, push kapali
    finally:
        push.reset_vapid_cache()


# ------------------------------------------------------------- WhatsApp nobetcisi


class FakeAdmin:
    def __init__(self):
        self.next = "open"

    def state(self):
        if self.next == "error":
            raise messaging.DeliveryError("ulasilamiyor")
        return self.next


@pytest.fixture()
def wa(monkeypatch):
    admin = FakeAdmin()
    monkeypatch.setattr(messaging, "get_evolution_admin", lambda: admin)
    return admin


def test_whatsapp_health_transitions(team, spy, wa, db):
    t0 = now_local()

    def check(state, at=t0):
        wa.next = state
        spy.calls.clear()
        return whatsapp_health.check_once(db, now=at), list(spy.calls)

    assert check("open")[0] is None  # ilk baglanti sessiz
    alert, calls = check("close")  # 1. hata: bekle
    assert alert is None and calls == []
    alert, calls = check("error")  # 2. hata: TEK uyari
    assert alert == "down"
    assert sorted(c["endpoint"] for c in calls) == sorted([ep("owner"), ep("manager")])
    assert "koptu" in calls[0]["payload"]["body"]
    assert calls[0]["payload"]["url"] == "/admin/whatsapp"
    for _ in range(3):  # kopukluk suruyor: tekrar yok
        assert check("close", t0 + timedelta(minutes=30)) == (None, [])
    alert, calls = check("close", t0 + timedelta(hours=7))  # 6 saat hatirlatma
    assert alert == "reminder" and len(calls) == 2
    alert, calls = check("open", t0 + timedelta(hours=8))
    assert alert == "up" and len(calls) == 2
    assert "yeniden kuruldu" in calls[0]["payload"]["body"]
    assert check("open", t0 + timedelta(hours=9)) == (None, [])
    # tek seferlik dalgalanma uyari uretmez
    assert check("close")[0] is None
    assert check("open") == (None, [])
    assert db.get(AppState, whatsapp_health.STATE_KEY) is not None


def test_whatsapp_health_state_survives_restart(team, spy, wa, db):
    wa.next = "close"
    whatsapp_health.check_once(db)
    assert whatsapp_health.check_once(db) == "down"
    spy.calls.clear()
    # "yeniden baslatma": durum DB'den okunur, ayni uyari tekrarlanmaz
    assert whatsapp_health.check_once(db) is None
    assert spy.calls == []


def test_whatsapp_health_skips_console_driver(team, spy, db, monkeypatch):
    monkeypatch.setattr(messaging, "get_evolution_admin", lambda: None)
    assert whatsapp_health.check_once(db) is None
