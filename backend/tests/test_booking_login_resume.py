"""
=====================================================================
HATA REGRESYONLARI - "giris yaptim, hizmetleri yeniden secmem gerekti"
=====================================================================

Misafir kullanici 1-5. adimlari tamamlayip (kilit alinmis) "Randevuyu
onayla" dediginde ``MEMBERSHIP_REQUIRED`` alir ve giris sayfasina gider.
Arayuz artik secimleri saklayip girisin ardindan 5. adima geri doner; bu
testler, bunun SUNUCU tarafinda da mumkun oldugunu kilitler:

  * misafirken alinan kilit ``visitor_key`` cerezine baglidir ve giris
    bu cerezi degistirmez -> ``/api/slots/lock/active`` kilidi hala
    dondurur ve ayni kilitle randevu olusturulabilir,
  * bir UYENIN aldigi kilidi, ayni tarayicida baska bir uye onaylayamaz,
  * musterinin kendi takvimindeki cakisma "baska bir musteri aldi"
    diye degil ``CUSTOMER_OVERLAP`` olarak bildirilir,
  * istemcinin gonderdigi ``shadowParentId`` korlemesine kaydedilmez.
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Appointment
from app.time_utils import add_days_to_key, now_local, to_date_key

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)


@pytest.fixture()
def client(salon):
    with TestClient(app) as test_client:
        yield test_client


def data_of(response) -> dict:
    body = response.json()
    assert body["ok"] is True, body
    return body["data"]


def error_of(response) -> dict:
    body = response.json()
    assert body["ok"] is False, body
    return body["error"]


def _login(client, phone: str) -> dict:
    sent = data_of(client.post("/api/auth/otp/send", json={"phone": phone}))
    return data_of(
        client.post("/api/auth/otp/verify", json={"phone": phone, "code": sent["devCode"]})
    )


def _lock_body(salon, start_min: int = 600, staff: str = "staff_a", service: str = "manikur"):
    return {
        "date": TOMORROW,
        "serviceIds": [salon[service].id],
        "staffId": salon[staff].id,
        "startMin": start_min,
    }


def _confirm_body(lock: dict, body: dict, **extra) -> dict:
    return {
        "lockId": lock["lockId"],
        "date": body["date"],
        "staffId": body["staffId"],
        "startMin": body["startMin"],
        "serviceIds": body["serviceIds"],
        **extra,
    }


def test_guest_lock_survives_login_and_can_be_confirmed(client, salon):
    """★ Misafir kilidi girisin ardindan hala gecerli ve onaylanabilir."""
    body = _lock_body(salon)

    # Misafir: musaitlik -> kilit
    availability = data_of(
        client.post(
            "/api/availability",
            json={"date": TOMORROW, "serviceIds": body["serviceIds"], "staffId": body["staffId"]},
        )
    )
    assert any(s["startMin"] == 600 for s in availability["staff"][0]["slots"])
    lock = data_of(client.post("/api/slots/lock", json=body))

    # Misafir onaylayamaz
    assert error_of(client.post("/api/appointments", json=_confirm_body(lock, body)))["code"] == (
        "MEMBERSHIP_REQUIRED"
    )

    # Giris (OTP) - visitor_key cerezi degismez
    visitor_before = client.cookies.get("visitor_key")
    _login(client, "5321010000")
    assert client.cookies.get("visitor_key") == visitor_before

    # Arayuz geri dondugunde kilidi bulabilmeli
    active = data_of(client.get("/api/slots/lock/active"))["lock"]
    assert active is not None and active["lockId"] == lock["lockId"]
    assert active["staffId"] == body["staffId"] and active["startMin"] == 600

    # Saat, giristen sonra da "senin" olarak listelenir
    again = data_of(
        client.post(
            "/api/availability",
            json={"date": TOMORROW, "serviceIds": body["serviceIds"], "staffId": body["staffId"]},
        )
    )
    held = [s for s in again["staff"][0]["slots"] if s["startMin"] == 600]
    assert held and held[0]["heldByYou"] is True

    created = data_of(client.post("/api/appointments", json=_confirm_body(lock, body)))
    assert created["appointment"]["startMin"] == 600

    # Kilit tuketildi
    assert data_of(client.get("/api/slots/lock/active"))["lock"] is None


def test_other_member_cannot_confirm_members_lock_on_same_browser(client, salon):
    """Uye A'nin kilidini, ayni tarayicida giris yapan uye B onaylayamaz."""
    body = _lock_body(salon)
    _login(client, "5321010000")
    lock = data_of(client.post("/api/slots/lock", json=body))

    client.post("/api/auth/logout", json={"scope": "customer"})
    _login(client, "5321010001")

    error = error_of(client.post("/api/appointments", json=_confirm_body(lock, body)))
    assert error["code"] == "FORBIDDEN"


def test_customer_overlap_is_not_reported_as_slot_taken(client, salon):
    """Musterinin ayni saatte baska randevusu varsa hata kodu dogru olmali."""
    _login(client, "5321010000")

    first = _lock_body(salon, 600, "staff_a")
    lock = data_of(client.post("/api/slots/lock", json=first))
    data_of(client.post("/api/appointments", json=_confirm_body(lock, first)))

    # Ayni musteri, ayni saatte BASKA ustadan kilit istemek:
    second = _lock_body(salon, 600, "staff_b")
    error = error_of(client.post("/api/slots/lock", json=second))
    assert error["code"] == "CUSTOMER_OVERLAP"


def test_customer_overlap_detected_when_guest_lock_is_confirmed(client, salon):
    """Misafirken alinan (musteri hucresi yazilmamis) kilit, giristen sonra
    musterinin mevcut randevusuyla cakisiyorsa CUSTOMER_OVERLAP doner ve
    kilit bozulmaz."""
    _login(client, "5321010000")
    first = _lock_body(salon, 600, "staff_a")
    lock = data_of(client.post("/api/slots/lock", json=first))
    data_of(client.post("/api/appointments", json=_confirm_body(lock, first)))
    client.post("/api/auth/logout", json={"scope": "customer"})

    # Misafir olarak baska ustadan ayni saat - kilit alinabilir
    second = _lock_body(salon, 600, "staff_b")
    guest_lock = data_of(client.post("/api/slots/lock", json=second))

    _login(client, "5321010000")
    error = error_of(client.post("/api/appointments", json=_confirm_body(guest_lock, second)))
    assert error["code"] == "CUSTOMER_OVERLAP"

    # Transaction geri alindi: kilit hala gecerli
    active = data_of(client.get("/api/slots/lock/active"))["lock"]
    assert active and active["lockId"] == guest_lock["lockId"]


def test_relocking_same_slot_is_not_blocked_by_own_old_lock(client, salon):
    """Ayni oturumun eski kilidi, ayni saatin yeniden tutulmasini engellemez
    (arayuz suresi dolan kilidi girisin ardindan yeniden alir)."""
    _login(client, "5321010000")
    body = _lock_body(salon)
    first = data_of(client.post("/api/slots/lock", json=body))
    second = data_of(client.post("/api/slots/lock", json=body))
    assert second["expiresAt"] >= first["expiresAt"]
    assert data_of(client.get("/api/slots/lock/active"))["lock"]["lockId"] == second["lockId"]


def test_bogus_shadow_parent_is_not_stored(client, salon, db):
    """Istemcinin gonderdigi shadowParentId dogrulanir."""
    _login(client, "5321010000")
    body = _lock_body(salon, 900)
    lock = data_of(client.post("/api/slots/lock", json=body))
    created = data_of(
        client.post("/api/appointments", json=_confirm_body(lock, body, shadowParentId=999999))
    )
    db.expire_all()
    assert db.get(Appointment, created["appointment"]["id"]).shadow_parent_id is None


def test_lock_rejects_start_outside_generated_slots(client, salon):
    """Kilit ucu yalnizca motorun urettigi saatleri kabul eder."""
    # Mesai 09:00-20:00; 03:00 gecerli bir slot degil.
    error = error_of(client.post("/api/slots/lock", json=_lock_body(salon, 180)))
    assert error["code"] == "SLOT_UNAVAILABLE"

    # Mesai bitisini tasan blok (19:50 + 40 dk)
    error = error_of(client.post("/api/slots/lock", json=_lock_body(salon, 1190)))
    assert error["code"] == "SLOT_UNAVAILABLE"


def test_lock_rejects_past_date(client, salon):
    body = _lock_body(salon)
    body["date"] = add_days_to_key(to_date_key(now_local()), -1)
    assert error_of(client.post("/api/slots/lock", json=body))["code"] == "VALIDATION"


def test_other_visitors_lock_still_reports_held_until(client, salon):
    """Yapisal kontrol, kilit cakismasinin SLOT_TAKEN + heldUntil
    bilgisini bozmaz (kilitler yapisal kontrolde yok sayilir)."""
    body = _lock_body(salon, 720)
    data_of(client.post("/api/slots/lock", json=body))
    with TestClient(app) as other:
        error = error_of(other.post("/api/slots/lock", json=body))
        assert error["code"] == "SLOT_TAKEN"
        assert error["details"]["heldUntil"] is not None
