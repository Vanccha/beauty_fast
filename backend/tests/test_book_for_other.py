"""Baskasi adina randevu, ``PATCH /api/me`` ve oturum omru testleri."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.sessions import CUSTOMER_TTL_DAYS
from app.main import app
from app.models import Appointment, Customer, CustomerSession, RateLimitHit, ScheduledNotification
from app.services import messaging
from app.time_utils import add_days_to_key, now_local, to_date_key
from tests.test_messaging import FakeSender

TOMORROW = add_days_to_key(to_date_key(now_local()), 3)
BOOKER = "5321010000"  # salon fixture: Ayse
OTHER = "5321010001"  # salon fixture: Zeynep (kayitli)
NEWPHONE = "5329998877"


@pytest.fixture()
def fake_sender(monkeypatch):
    sender = FakeSender()
    monkeypatch.setattr(messaging, "_sender", sender)
    return sender


@pytest.fixture()
def client(salon, fake_sender):
    with TestClient(app) as c:
        yield c


def data_of(r) -> dict:
    body = r.json()
    assert body["ok"] is True, body
    return body["data"]


def error_of(r) -> dict:
    body = r.json()
    assert body["ok"] is False, body
    return body["error"]


def login(client, phone: str) -> dict:
    sent = data_of(client.post("/api/auth/otp/send", json={"phone": phone}))
    return data_of(client.post("/api/auth/otp/verify", json={"phone": phone, "code": sent["devCode"]}))


def new_client():
    return TestClient(app)


def lock_body(salon, start=600, staff="staff_a", service="manikur", **extra):
    return {
        "date": TOMORROW,
        "serviceIds": [salon[service].id],
        "staffId": salon[staff].id,
        "startMin": start,
        **extra,
    }


def confirm_body(lock, body, **extra):
    return {
        "lockId": lock["lockId"],
        "date": body["date"],
        "staffId": body["staffId"],
        "startMin": body["startMin"],
        "serviceIds": body["serviceIds"],
        "privacyNoticeAck": True,
        "healthDeclaration": True,
        **extra,
    }


def book(client, salon, beneficiary=None, start=600, staff="staff_a"):
    extra = {"beneficiary": beneficiary} if beneficiary else {}
    body = lock_body(salon, start=start, staff=staff, **extra)
    lock = data_of(client.post("/api/slots/lock", json=body))
    return client.post("/api/appointments", json=confirm_body(lock, body, **extra))


BEN = {"firstName": "Deniz", "lastName": "Aksoy", "phone": NEWPHONE}


# ---------------------------------------------------------------- PATCH /api/me


def test_patch_me_updates_name(client):
    login(client, BOOKER)
    res = data_of(client.patch("/api/me", json={"firstName": "  Ayşegül  ", "lastName": "Demir"}))
    assert res["customer"]["firstName"] == "Ayşegül"
    assert res["customer"]["lastName"] == "Demir"
    assert data_of(client.get("/api/me"))["customer"]["firstName"] == "Ayşegül"


@pytest.mark.parametrize("bad", ["", "   ", "A1", "x" * 41, "<b>", "Ali_Veli"])
def test_patch_me_validation(client, bad):
    login(client, BOOKER)
    r = client.patch("/api/me", json={"firstName": bad})
    assert r.status_code == 400
    assert error_of(r)["code"] == "VALIDATION"


def test_patch_me_requires_session(client):
    r = client.patch("/api/me", json={"firstName": "Ali"})
    assert r.status_code == 401


def test_patch_me_allows_hyphen_apostrophe(client):
    login(client, BOOKER)
    res = data_of(client.patch("/api/me", json={"firstName": "Ayşe-Nur", "lastName": "O'Neil"}))
    assert res["customer"]["firstName"] == "Ayşe-Nur"


# ---------------------------------------------------------- book for another


def test_book_for_new_beneficiary(client, salon, fake_sender, db):
    login(client, BOOKER)
    r = data_of(book(client, salon, BEN))
    assert r["bookedForOther"] is True
    assert r["forCustomer"]["firstName"] == "Deniz"
    assert r["allergyWarnings"] == []

    ben = db.scalar(select(Customer).where(Customer.phone == NEWPHONE))
    assert ben is not None and ben.first_name == "Deniz" and ben.is_member is False
    appt = db.get(Appointment, r["appointment"]["id"])
    assert appt.customer_id == ben.id
    assert appt.booked_by_customer_id == salon["customer"].id

    # alicinin telefonuna bilgilendirme gitti (OTP mesajindan sonra)
    phone, text = fake_sender.sent[-1]
    assert phone == NEWPHONE
    assert "Ayşe" in text and "randevularim" in text and "Manikür" in text

    # 24 saat hatirlatmasi alicinin kaydina
    rem = db.scalar(
        select(ScheduledNotification).where(ScheduledNotification.dedupe_key == f"pre:{appt.id}:24")
    )
    assert rem.customer_id == ben.id
    assert rem.body.startswith("Deniz")


def test_existing_beneficiary_name_not_overwritten(client, salon, db):
    login(client, BOOKER)
    r = data_of(book(client, salon, {"firstName": "Baska", "phone": OTHER}))
    # Alana kayitli ad degil, kendi yazdigi etiket doner (isim sizdirma yok).
    assert r["forCustomer"]["firstName"] == "Baska"
    assert db.scalar(select(Customer.first_name).where(Customer.phone == OTHER)) == "Zeynep"


def test_placeholder_name_is_replaced(client, salon, db):
    db.add(Customer(phone=NEWPHONE, first_name="Yeni Üye"))
    db.commit()
    login(client, BOOKER)
    data_of(book(client, salon, BEN))
    assert db.scalar(select(Customer.first_name).where(Customer.phone == NEWPHONE)) == "Deniz"


def test_beneficiary_same_phone_is_self(client, salon, fake_sender, db):
    login(client, BOOKER)
    n = len(fake_sender.sent)
    r = data_of(book(client, salon, {"firstName": "Ben", "phone": "+90 532 101 00 00"}))
    assert r["bookedForOther"] is False
    appt = db.get(Appointment, r["appointment"]["id"])
    assert appt.customer_id == appt.booked_by_customer_id == salon["customer"].id
    assert len(fake_sender.sent) == n  # kendine bilgilendirme yok


def test_beneficiary_requires_login_and_valid_phone(client, salon):
    body = lock_body(salon, beneficiary=BEN)
    assert client.post("/api/slots/lock", json=body).status_code == 401
    login(client, BOOKER)
    bad = lock_body(salon, beneficiary={"firstName": "Deniz", "phone": "12345"})
    assert client.post("/api/slots/lock", json=bad).status_code == 400


def test_message_failure_does_not_fail_booking(client, salon, fake_sender):
    login(client, BOOKER)
    fake_sender.fail = True
    assert book(client, salon, BEN).status_code == 200


def test_message_channel_not_ready_does_not_fail_booking(client, salon, fake_sender):
    login(client, BOOKER)
    fake_sender.ready = False
    assert book(client, salon, BEN).status_code == 200


def test_overlap_uses_beneficiary_calendar(client, salon):
    """Alicinin ayni saatteki baska randevusu (baska usta) -> CUSTOMER_OVERLAP."""
    login(client, BOOKER)
    data_of(book(client, salon, BEN, start=600, staff="staff_a"))
    body = lock_body(salon, start=600, staff="staff_b", beneficiary=BEN)
    lock = client.post("/api/slots/lock", json=body)
    if lock.status_code == 200:
        r = client.post("/api/appointments", json=confirm_body(data_of(lock), body, beneficiary=BEN))
        assert error_of(r)["code"] == "CUSTOMER_OVERLAP"
    else:
        assert error_of(lock)["code"] == "CUSTOMER_OVERLAP"
    # Alanin KENDI takvimi bos: kendine ayni saatte alabilir
    assert book(client, salon, None, start=600, staff="staff_b").status_code == 200


# ----------------------------------------------------------- visibility


def test_mine_visibility_and_cancel_rights(client, salon, db):
    login(client, BOOKER)
    for_other = data_of(book(client, salon, BEN, start=600))
    own = data_of(book(client, salon, None, start=720))
    oid, mid = for_other["appointment"]["id"], own["appointment"]["id"]

    mine = data_of(client.get("/api/appointments/mine"))["upcoming"]
    by_id = {a["id"]: a for a in mine}
    assert set(by_id) == {oid, mid}
    assert by_id[oid]["bookedByMe"] and not by_id[oid]["isMine"]
    assert by_id[oid]["forCustomer"]["firstName"] == "Deniz"
    assert by_id[mid]["isMine"] and by_id[mid]["bookedByMe"]
    assert by_id[oid]["groupId"] is None and by_id[oid]["cancellable"]

    # alici (kendi telefonuyla) yalnizca kendisininkini gorur
    recipient = new_client()
    login(recipient, NEWPHONE)
    rmine = data_of(recipient.get("/api/appointments/mine"))["upcoming"]
    assert [a["id"] for a in rmine] == [oid]
    assert rmine[0]["isMine"] is True and rmine[0]["bookedByMe"] is False
    # alici baska birinin randevusunu goremez / iptal edemez
    assert recipient.get(f"/api/appointments/{mid}").status_code == 403
    patch = recipient.patch(
        f"/api/appointments/{mid}", json={"status": "CANCELLED", "expectedVersion": 0}
    )
    assert patch.status_code == 403
    # booker detay okuyabilir
    d = data_of(client.get(f"/api/appointments/{oid}"))
    assert d["bookedByMe"] and d["forCustomer"]["firstName"] == "Deniz"

    # tasarim yukleme: booker yapamaz (yalnizca sahibi)
    up = client.post(f"/api/appointments/{oid}/design", data={"link": "https://example.com/x.jpg"})
    assert up.status_code == 403

    # booker baskasi adina alinani iptal edebilir
    r = data_of(client.patch(f"/api/appointments/{oid}", json={"status": "CANCELLED", "expectedVersion": 0}))
    assert r["status"] == "CANCELLED"
    rem = db.scalar(
        select(ScheduledNotification).where(ScheduledNotification.dedupe_key == f"pre:{oid}:24")
    )
    assert rem.status == "CANCELLED"


def test_recipient_can_cancel_own(client, salon):
    login(client, BOOKER)
    oid = data_of(book(client, salon, BEN))["appointment"]["id"]
    recipient = new_client()
    login(recipient, NEWPHONE)
    r = data_of(
        recipient.patch(f"/api/appointments/{oid}", json={"status": "CANCELLED", "expectedVersion": 0})
    )
    assert r["status"] == "CANCELLED"


def test_group_cancel_booker_only(client, salon, db):
    login(client, BOOKER)
    a = data_of(book(client, salon, BEN, start=600))["appointment"]["id"]
    b = data_of(book(client, salon, {"firstName": "Cem", "phone": "5327776655"}, start=720))[
        "appointment"
    ]["id"]
    c = data_of(book(client, salon, None, start=840))["appointment"]["id"]
    table = Appointment.__table__
    for i in (a, b):
        db.execute(table.update().where(table.c.id == i).values(booking_group_id="grp1"))
    db.execute(table.update().where(table.c.id == c).values(booking_group_id="grp-other"))
    db.commit()

    # alici grubu iptal edemez
    recipient = new_client()
    login(recipient, NEWPHONE)
    assert recipient.post("/api/appointments/group/grp1/cancel").status_code == 404

    res = data_of(client.post("/api/appointments/group/grp1/cancel"))
    assert res["cancelled"] == 2
    db.expire_all()
    assert db.get(Appointment, a).status == "CANCELLED"
    assert db.get(Appointment, b).status == "CANCELLED"
    assert db.get(Appointment, c).status == "CONFIRMED"
    assert data_of(client.post("/api/appointments/group/grp1/cancel"))["cancelled"] == 0
    assert client.post("/api/appointments/group/yok/cancel").status_code == 404


# ---------------------------------------------------------- rate limits


def test_rate_limit_per_target_phone(client, salon):
    login(client, BOOKER)
    for i in range(3):
        data_of(book(client, salon, BEN, start=600 + i * 60))
    r = client.post("/api/slots/lock", json=lock_body(salon, start=1080, beneficiary=BEN))
    assert r.status_code == 429 and error_of(r)["code"] == "RATE_LIMITED"


def test_rate_limit_per_booker(client, salon, db):
    from app.services.booking_for_other import OTHER_BOOK_BOOKER

    login(client, BOOKER)
    for _ in range(OTHER_BOOK_BOOKER.max_hits):
        db.add(
            RateLimitHit(
                key=f"{OTHER_BOOK_BOOKER.name}:{salon['customer'].id}", created_at=now_local()
            )
        )
    db.commit()
    r = client.post("/api/slots/lock", json=lock_body(salon, beneficiary=BEN))
    assert r.status_code == 429
    assert book(client, salon, None).status_code == 200  # kendi adina serbest


# ---------------------------------------------------------- session TTL


def test_customer_session_is_180_days_and_slides(client, db):
    assert CUSTOMER_TTL_DAYS == 180
    login(client, BOOKER)
    sess = db.scalar(select(CustomerSession))
    assert sess.expires_at - now_local() > timedelta(days=179)

    # Taze oturumda yazma yok
    before = sess.expires_at
    client.get("/api/me")
    db.expire_all()
    assert db.scalar(select(CustomerSession)).expires_at == before

    # 100 gun kalmis -> kullanimda 180 gune uzar ve cerez tazelenir
    sess = db.scalar(select(CustomerSession))
    sess.expires_at = now_local() + timedelta(days=100)
    db.commit()
    r = client.get("/api/me")
    db.expire_all()
    assert db.scalar(select(CustomerSession)).expires_at - now_local() > timedelta(days=179)
    assert "customer_session=" in r.headers.get("set-cookie", "")
