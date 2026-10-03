"""Uctan uca API testleri: zarf sozlesmesi, yetki kapilari, randevu akisi."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.time_utils import add_days_to_key, now_local, to_date_key

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)


@pytest.fixture()
def client(salon):
    with TestClient(app) as test_client:
        yield test_client


def data_of(response) -> dict:
    """Basarili yanitin zarfini acar; sozlesmeyi de dogrular."""
    body = response.json()
    assert body["ok"] is True, body
    return body["data"]


def error_of(response) -> dict:
    body = response.json()
    assert body["ok"] is False, body
    return body["error"]


# ---------------------------------------------------------------------
# Sozlesme ve herkese acik uclar
# ---------------------------------------------------------------------


def test_response_envelope(client):
    response = client.get("/api/catalog/services")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"ok", "data"}
    assert "services" in payload["data"]


def test_guest_can_browse_catalog_and_portfolio(client, salon):
    services = data_of(client.get("/api/catalog/services"))["services"]
    assert {s["name"] for s in services} >= {"Saç Boyası", "Kaş Alma", "Manikür"}

    portfolio = data_of(client.get("/api/portfolio"))
    assert portfolio["items"] == []  # is yoksa bos doner (sahte vitrin yok)

    me = data_of(client.get("/api/me"))
    assert me["customer"] is None and me["staff"] is None


def test_catalog_staff_filter_accepts_duplicate_ids(client, salon):
    """HATA 2: ``serviceIds=3,3`` personeli elememeli."""
    service_id = salon["kas"].id
    payload = data_of(
        client.get(f"/api/catalog/staff?serviceIds={service_id},{service_id}")
    )
    assert len(payload["staff"]) == 2


# ---------------------------------------------------------------------
# Yetki kapilari
# ---------------------------------------------------------------------


def test_admin_endpoints_require_staff_session(client):
    for path in ("/api/admin/calendar", "/api/admin/customers", "/api/admin/inventory"):
        assert error_of(client.get(path))["code"] == "UNAUTHORIZED"


def test_booking_requires_membership(client, salon):
    response = client.post(
        "/api/appointments",
        json={
            "lockId": 1,
            "date": TOMORROW,
            "staffId": salon["staff_a"].id,
            "startMin": 600,
            "serviceIds": [salon["manikur"].id],
        },
    )
    assert error_of(response)["code"] == "MEMBERSHIP_REQUIRED"


def test_staff_login_rejects_wrong_password(client):
    response = client.post(
        "/api/auth/staff/login", json={"phone": "5551110001", "password": "yanlis"}
    )
    error = error_of(response)
    assert error["code"] == "UNAUTHORIZED"
    # Kayitli olmayan numarada da AYNI mesaj doner (hesap sayimi engellenir).
    other = client.post(
        "/api/auth/staff/login", json={"phone": "5559999999", "password": "yanlis"}
    )
    assert error_of(other)["message"] == error["message"]


def test_staff_login_and_calendar(client, salon):
    login = data_of(
        client.post(
            "/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}
        )
    )
    assert login["staff"]["role"] == "OWNER"

    calendar = data_of(client.get(f"/api/admin/calendar?date={TOMORROW}"))
    assert len(calendar["staff"]) == 2
    assert calendar["appointments"] == []

    client.post("/api/auth/logout", json={"scope": "staff"})
    assert error_of(client.get("/api/admin/calendar"))["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------
# Musteri randevu akisi (uctan uca)
# ---------------------------------------------------------------------


def _login_customer(client, phone: str = "5321010000") -> dict:
    sent = data_of(client.post("/api/auth/otp/send", json={"phone": phone}))
    assert sent["devCode"] == "123456"
    return data_of(
        client.post("/api/auth/otp/verify", json={"phone": phone, "code": sent["devCode"]})
    )


def test_full_booking_flow(client, salon):
    verified = _login_customer(client)
    assert verified["customer"]["phone"] == "5321010000"

    availability = data_of(
        client.post(
            "/api/availability",
            json={
                "date": TOMORROW,
                "serviceIds": [salon["boya"].id],
                "staffId": salon["staff_a"].id,
            },
        )
    )
    assert availability["package"]["totalMin"] == 100
    slot = availability["staff"][0]["slots"][0]

    lock = data_of(
        client.post(
            "/api/slots/lock",
            json={
                "date": TOMORROW,
                "serviceIds": [salon["boya"].id],
                "staffId": salon["staff_a"].id,
                "startMin": slot["startMin"],
            },
        )
    )
    assert lock["endMin"] - lock["startMin"] == 100

    # HATA 1: kilit alindiktan sonra ayni saat HALA listede gorunur.
    again = data_of(
        client.post(
            "/api/availability",
            json={
                "date": TOMORROW,
                "serviceIds": [salon["boya"].id],
                "staffId": salon["staff_a"].id,
            },
        )
    )
    held = [s for s in again["staff"][0]["slots"] if s["startMin"] == slot["startMin"]]
    assert held and held[0]["heldByYou"] is True
    assert again["yourLock"]["lockId"] == lock["lockId"]

    # Acik kilit ucu de ayni bilgiyi verir.
    active = data_of(client.get("/api/slots/lock/active"))
    assert active["lock"]["lockId"] == lock["lockId"]

    created = data_of(
        client.post(
            "/api/appointments",
            json={
                "lockId": lock["lockId"],
                "privacyNoticeAck": True,
                "healthDeclaration": True,
                "date": TOMORROW,
                "staffId": salon["staff_a"].id,
                "startMin": slot["startMin"],
                "serviceIds": [salon["boya"].id],
            },
        )
    )
    appointment = created["appointment"]
    assert appointment["endMin"] - appointment["startMin"] == 100

    mine = data_of(client.get("/api/appointments/mine"))
    assert [a["id"] for a in mine["upcoming"]] == [appointment["id"]]
    assert mine["upcoming"][0]["cancellable"] is True

    # Musteri yalnizca IPTAL edebilir.
    forbidden = client.patch(
        f"/api/appointments/{appointment['id']}",
        json={"status": "COMPLETED", "expectedVersion": appointment["version"]},
    )
    assert error_of(forbidden)["code"] == "FORBIDDEN"

    cancelled = data_of(
        client.patch(
            f"/api/appointments/{appointment['id']}",
            json={"status": "CANCELLED", "expectedVersion": appointment["version"]},
        )
    )
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["freedSlot"] is True


def test_booking_the_same_service_twice(client, salon):
    """★ HATA 2 uctan uca: ayni hizmet iki kez secilerek randevu alinabilir."""
    _login_customer(client)
    ids = [salon["kas"].id, salon["kas"].id]

    availability = data_of(
        client.post(
            "/api/availability",
            json={"date": TOMORROW, "serviceIds": ids, "staffId": salon["staff_a"].id},
        )
    )
    assert availability["staff"], availability["message"]
    assert availability["package"]["totalMin"] == 30
    slot = availability["staff"][0]["slots"][0]

    lock = data_of(
        client.post(
            "/api/slots/lock",
            json={
                "date": TOMORROW,
                "serviceIds": ids,
                "staffId": salon["staff_a"].id,
                "startMin": slot["startMin"],
            },
        )
    )

    created = data_of(
        client.post(
            "/api/appointments",
            json={
                "lockId": lock["lockId"],
                "privacyNoticeAck": True,
                "healthDeclaration": True,
                "date": TOMORROW,
                "staffId": salon["staff_a"].id,
                "startMin": slot["startMin"],
                "serviceIds": ids,
            },
        )
    )
    assert created["appointment"]["totalPrice"] == 300

    detail = data_of(client.get(f"/api/appointments/{created['appointment']['id']}"))
    assert len(detail["services"]) == 2


def test_second_lock_on_same_slot_is_rejected(client, salon):
    """Farkli bir tarayici oturumu ayni saati alamaz."""
    _login_customer(client)
    body = {
        "date": TOMORROW,
        "serviceIds": [salon["manikur"].id],
        "staffId": salon["staff_a"].id,
        "startMin": 600,
    }
    assert data_of(client.post("/api/slots/lock", json=body))["startMin"] == 600

    with TestClient(app) as other:
        error = error_of(other.post("/api/slots/lock", json=body))
        assert error["code"] == "SLOT_TAKEN"
        assert error["details"]["heldUntil"] is not None


def test_releasing_lock_frees_the_slot(client, salon):
    _login_customer(client)
    body = {
        "date": TOMORROW,
        "serviceIds": [salon["manikur"].id],
        "staffId": salon["staff_a"].id,
        "startMin": 660,
    }
    lock = data_of(client.post("/api/slots/lock", json=body))
    assert data_of(client.delete(f"/api/slots/lock/{lock['lockId']}"))["released"] is True

    with TestClient(app) as other:
        assert data_of(other.post("/api/slots/lock", json=body))["lockId"] > 0


def test_review_requires_completed_appointment(client, salon):
    """Yorumun dort kapisi: uyelik, sahiplik, tamamlanmislik, tekillik."""
    _login_customer(client)

    body = {
        "date": TOMORROW,
        "serviceIds": [salon["manikur"].id],
        "staffId": salon["staff_a"].id,
        "startMin": 720,
    }
    lock = data_of(client.post("/api/slots/lock", json=body))
    created = data_of(
        client.post(
            "/api/appointments",
            json={
                "lockId": lock["lockId"],
                "privacyNoticeAck": True,
                "healthDeclaration": True,
                **body,
            },
        )
    )
    appointment_id = created["appointment"]["id"]

    not_completed = client.post(
        "/api/reviews",
        json={"appointmentId": appointment_id, "rating": 5, "comment": "Harika bir deneyimdi."},
    )
    assert error_of(not_completed)["code"] == "NOT_COMPLETED"

    # Personel randevuyu tamamlar.
    with TestClient(app) as staff_client:
        staff_client.post(
            "/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}
        )
        data_of(
            staff_client.patch(
                f"/api/admin/appointments/{appointment_id}/status",
                json={"status": "COMPLETED", "expectedVersion": 0},
            )
        )

    review = data_of(
        client.post(
            "/api/reviews",
            json={
                "appointmentId": appointment_id,
                "rating": 5,
                "comment": "Randevu saatinde başladı, sonuçtan memnunum.",
            },
        )
    )
    assert review["rating"] == 5

    duplicate = client.post(
        "/api/reviews",
        json={"appointmentId": appointment_id, "rating": 4, "comment": "Bir kez daha yazayım."},
    )
    assert error_of(duplicate)["code"] == "ALREADY_REVIEWED"

    showcase = data_of(client.get("/api/showcase"))
    assert showcase["reviews"]["summary"]["count"] == 1
    assert showcase["stats"]["completedAppointments"] == 1


def test_validation_errors_use_envelope(client, salon):
    response = client.post(
        "/api/availability", json={"date": "dün", "serviceIds": [salon["kas"].id]}
    )
    assert error_of(response)["code"] == "VALIDATION"


def test_cron_sweep_runs(client):
    from app.config import config

    payload = data_of(
        client.post("/api/cron/sweep", headers={"X-Cron-Secret": config.cron_secret})
    )
    assert "sweptAt" in payload
    assert payload["notificationsSent"] >= 0
