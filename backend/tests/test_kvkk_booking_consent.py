"""Randevuda KVKK aydinlatma teyidi, saglik beyani ve istege bagli alerji rizasi."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Allergy, Appointment, Customer, SlotLock
from app.services import messaging
from app.time_utils import add_days_to_key, now_local, to_date_key
from tests.test_book_for_other import BEN, BOOKER, confirm_body, data_of, error_of, lock_body, login
from tests.test_group_booking import DAY, confirm_group, lock_group
from tests.test_messaging import FakeSender


@pytest.fixture()
def client(salon, monkeypatch):
    monkeypatch.setattr(messaging, "_sender", FakeSender())
    with TestClient(app) as c:
        login(c, BOOKER)
        yield c


def _lock(client, salon, **extra):
    body = lock_body(salon, **extra)
    return data_of(client.post("/api/slots/lock", json=body)), body


def _post(client, lock, body, **extra):
    payload = confirm_body(lock, body)
    payload.update(extra)
    return client.post("/api/appointments", json=payload)


def _count(db, model) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model))


def test_missing_privacy_ack_rejected_and_lock_kept(client, salon, db):
    lock, body = _lock(client, salon)
    before = _count(db, Appointment)
    r = _post(client, lock, body, privacyNoticeAck=False)
    assert r.status_code == 400 and error_of(r)["code"] == "PRIVACY_NOTICE_REQUIRED"
    assert _count(db, Appointment) == before
    db.expire_all()
    assert db.get(SlotLock, lock["lockId"]).consumed_at is None
    # Ayni kilitle duzeltilmis istek basarili olur.
    assert data_of(_post(client, lock, body))["appointment"]["id"]


def test_missing_health_declaration_rejected(client, salon, db):
    lock, body = _lock(client, salon)
    r = _post(client, lock, body, healthDeclaration=False)
    assert r.status_code == 400 and error_of(r)["code"] == "HEALTH_DECLARATION_REQUIRED"
    assert _count(db, Appointment) == 0
    db.expire_all()
    assert db.get(SlotLock, lock["lockId"]).consumed_at is None


def test_timestamps_stored_on_appointment(client, salon, db):
    lock, body = _lock(client, salon)
    created = data_of(_post(client, lock, body))
    db.expire_all()
    a = db.get(Appointment, created["appointment"]["id"])
    assert a.privacy_notice_ack_at is not None and a.health_declaration_at is not None
    assert created["allergyWarnings"] == []


def test_allergy_without_consent_rejected(client, salon, db):
    lock, body = _lock(client, salon)
    r = _post(client, lock, body, allergy={"label": "Lateks"})
    assert r.status_code == 400 and error_of(r)["code"] == "CONSENT_REQUIRED"
    assert _count(db, Appointment) == 0 and _count(db, Allergy) == 0
    db.expire_all()
    assert db.get(SlotLock, lock["lockId"]).consumed_at is None


def test_allergy_with_consent_saved_and_warned(client, salon, db):
    lock, body = _lock(client, salon)
    created = data_of(
        _post(client, lock, body, allergy={"label": "  Lateks  ", "note": "Eldiven"}, healthConsent=True)
    )
    assert [w["label"] for w in created["allergyWarnings"]] == ["Lateks"]
    assert created["allergyWarnings"][0]["severity"] == "HIGH"
    db.expire_all()
    customer = db.scalar(select(Customer).where(Customer.phone == BOOKER))
    assert customer.health_consent_at is not None
    rows = db.scalars(select(Allergy).where(Allergy.customer_id == customer.id)).all()
    assert [(r.label, r.note, r.severity) for r in rows] == [("Lateks", "Eldiven", "HIGH")]


def test_allergy_for_other_rejected(client, salon, db):
    body = lock_body(salon, beneficiary=BEN)
    lock = data_of(client.post("/api/slots/lock", json=body))
    r = client.post(
        "/api/appointments",
        json=confirm_body(
            lock, body, beneficiary=BEN, allergy={"label": "Lateks"}, healthConsent=True
        ),
    )
    assert r.status_code == 400
    assert _count(db, Appointment) == 0 and _count(db, Allergy) == 0
    db.expire_all()
    assert db.get(SlotLock, lock["lockId"]).consumed_at is None


def test_group_requires_both_flags(client, salon, db):
    assignments = [(salon["staff_a"], "self"), (salon["staff_b"], BEN)]
    group = data_of(lock_group(client, salon, assignments))
    r = confirm_group(client, group, assignments, privacyNoticeAck=False)
    assert r.status_code == 400 and error_of(r)["code"] == "PRIVACY_NOTICE_REQUIRED"
    r = confirm_group(client, group, assignments, healthDeclaration=False)
    assert r.status_code == 400 and error_of(r)["code"] == "HEALTH_DECLARATION_REQUIRED"
    assert _count(db, Appointment) == 0
    db.expire_all()
    assert all(
        db.get(SlotLock, l["lockId"]).consumed_at is None for l in group["locks"]
    )
    # Bayraklarla ayni kilitler kullanilabilir ve her randevuya damga yazilir.
    data_of(confirm_group(client, group, assignments))
    db.expire_all()
    rows = db.scalars(select(Appointment)).all()
    assert len(rows) == 2
    assert all(a.privacy_notice_ack_at and a.health_declaration_at for a in rows)
