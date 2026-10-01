"""KVKK: rizalar, ticari ileti kapisi, veri dokumu, hesap silme, saklama sureleri."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import (
    Allergy,
    Appointment,
    Customer,
    CustomerNote,
    PhoneRiskEvent,
    Review,
    ScheduledNotification,
    SlotViewEvent,
)
from app.services.appointment_status import change_appointment_status
from app.services.notifications import deliver_due_notifications
from app.services.privacy import sweep_retention
from app.time_utils import now_local

from .test_status_version import _create


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


def _login(client, phone: str = "5321010000", **extra) -> dict:
    client.post("/api/auth/otp/send", json={"phone": phone})
    return data_of(
        client.post("/api/auth/otp/verify", json={"phone": phone, "code": "123456", **extra})
    )


def _staff_login(client) -> None:
    data_of(
        client.post("/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"})
    )


# ---------------------------------------------------------------------
# Ticari ileti onayi
# ---------------------------------------------------------------------


def test_marketing_consent_is_opt_in_and_not_revoked_by_plain_login(client, db):
    _login(client)
    assert data_of(client.get("/api/me/privacy"))["marketingConsent"] is False

    _login(client, marketingConsent=True)
    status = data_of(client.get("/api/me/privacy"))
    assert status["marketingConsent"] is True and status["marketingConsentAt"]

    # Kutu isaretlenmeden tekrar giris yapmak onayi GERI ALMAZ.
    _login(client)
    assert data_of(client.get("/api/me/privacy"))["marketingConsent"] is True


def test_withdrawing_marketing_consent_cancels_only_marketing_messages(client, salon, db):
    _login(client, marketingConsent=True)
    customer_id = salon["customer"].id
    due = now_local() + timedelta(days=10)
    db.add_all([
        ScheduledNotification(
            customer_id=customer_id, channel="WHATSAPP", body="Bakım zamanı",
            due_at=due, dedupe_key="repeat:1:default:1",
        ),
        ScheduledNotification(
            customer_id=customer_id, channel="WHATSAPP", body="Yarın randevun var",
            due_at=due, dedupe_key="pre:1:24",
        ),
    ])
    db.commit()

    data_of(client.patch("/api/me/privacy", json={"marketingConsent": False}))

    db.expire_all()
    statuses = dict(
        db.execute(
            select(ScheduledNotification.dedupe_key, ScheduledNotification.status).where(
                ScheduledNotification.customer_id == customer_id
            )
        ).all()
    )
    assert statuses == {"repeat:1:default:1": "CANCELLED", "pre:1:24": "PENDING"}


def test_repeat_reminder_requires_marketing_consent(salon, db):
    appointment = _create(db, salon, 600)
    result = change_appointment_status(
        db, appointment_id=appointment.id, status="COMPLETED", expected_version=0
    )
    assert result["reminderQueued"] is False

    customer = db.get(Customer, salon["customer"].id)
    customer.marketing_consent_at = now_local()
    db.commit()

    second = _create(db, salon, 720)
    result = change_appointment_status(
        db, appointment_id=second.id, status="COMPLETED", expected_version=0
    )
    assert result["reminderQueued"] is True


def test_delivery_skips_marketing_message_without_consent(salon, db):
    """Onay kuyruga alindiktan sonra geri alinmis olabilir: gonderim aninda da kontrol."""
    past = now_local() - timedelta(minutes=1)
    db.add_all([
        ScheduledNotification(
            customer_id=salon["customer"].id, channel="WHATSAPP", body="Bakım zamanı",
            due_at=past, dedupe_key="repeat:9:default:1",
        ),
        ScheduledNotification(
            customer_id=salon["customer"].id, channel="WHATSAPP", body="Yarın randevun var",
            due_at=past, dedupe_key="pre:9:24",
        ),
    ])
    db.commit()

    result = deliver_due_notifications(db)
    assert result["sent"] == 1

    db.expire_all()
    statuses = dict(
        db.execute(select(ScheduledNotification.dedupe_key, ScheduledNotification.status)).all()
    )
    assert statuses == {"repeat:9:default:1": "CANCELLED", "pre:9:24": "SENT"}


# ---------------------------------------------------------------------
# Saglik verisi (alerji)
# ---------------------------------------------------------------------


def test_allergy_requires_explicit_consent_confirmation(client, salon, db):
    _staff_login(client)
    customer_id = salon["customer"].id
    url = f"/api/admin/customers/{customer_id}/allergy"

    error = error_of(client.post(url, json={"label": "Amonyak"}))
    assert error["code"] == "CONSENT_REQUIRED"

    data_of(client.post(url, json={"label": "Amonyak", "consentConfirmed": True}))
    # Riza bir kez alindiktan sonra yeni kayitlarda tekrar istenmez.
    data_of(client.post(url, json={"label": "Lateks"}))

    db.expire_all()
    assert db.get(Customer, customer_id).health_consent_at is not None
    profile = data_of(client.get(f"/api/admin/customers/{customer_id}"))["profile"]
    assert profile["healthConsent"] is True


def test_withdrawing_health_consent_deletes_allergies(client, salon, db):
    customer = db.get(Customer, salon["customer"].id)
    customer.health_consent_at = now_local()
    db.add(Allergy(customer_id=customer.id, label="Amonyak"))
    db.commit()

    _login(client)
    assert data_of(client.get("/api/me/privacy"))["hasHealthData"] is True

    status = data_of(client.patch("/api/me/privacy", json={"healthConsent": False}))
    assert status == {**status, "healthConsent": False, "hasHealthData": False}

    # Musteri saglik rizasini kendisi "verilmis" yapamaz.
    assert error_of(client.patch("/api/me/privacy", json={"healthConsent": True}))["code"] == (
        "VALIDATION"
    )


# ---------------------------------------------------------------------
# Veri dokumu ve hesap silme
# ---------------------------------------------------------------------


def test_export_contains_own_data_but_not_staff_only_notes(client, salon, db):
    customer_id = salon["customer"].id
    db.add_all([
        CustomerNote(customer_id=customer_id, body="Gizli usta notu", visibility="STAFF_ONLY"),
        CustomerNote(customer_id=customer_id, body="Paylaşılan not", visibility="SHARED"),
    ])
    db.commit()
    _create(db, salon, 600)

    _login(client)
    export = data_of(client.get("/api/me/export"))
    assert export["profile"]["phone"] == "5321010000"
    assert len(export["appointments"]) == 1
    assert [n["body"] for n in export["sharedNotes"]] == ["Paylaşılan not"]
    assert "Gizli usta notu" not in str(export)


def test_delete_account_blocked_by_upcoming_appointment(client, salon, db):
    _create(db, salon, 600)
    _login(client)
    error = error_of(client.delete("/api/me"))
    assert "Yaklaşan randevun" in error["message"]


def test_delete_account_anonymizes_and_logs_out(client, salon, db):
    customer_id = salon["customer"].id
    appointment = _create(db, salon, 600)
    change_appointment_status(
        db, appointment_id=appointment.id, status="COMPLETED", expected_version=0
    )
    customer = db.get(Customer, customer_id)
    customer.health_consent_at = now_local()
    db.add_all([
        Allergy(customer_id=customer_id, label="Amonyak"),
        CustomerNote(customer_id=customer_id, body="Not"),
        Review(
            branch_id=salon["branch"].id, customer_id=customer_id, author_name="Ayşe Y.",
            rating=5, comment="Harika",
        ),
    ])
    db.commit()

    _login(client)
    result = data_of(client.delete("/api/me"))
    assert result["anonymized"] is True

    # Oturum kapandi.
    assert data_of(client.get("/api/me"))["customer"] is None

    db.expire_all()
    row = db.get(Customer, customer_id)
    assert row.anonymized_at is not None
    assert row.phone != "5321010000" and row.first_name == "Silinmiş üye"
    assert row.health_consent_at is None and row.marketing_consent_at is None
    for model in (Allergy, CustomerNote, Review):
        assert db.scalar(select(model.id).where(model.customer_id == customer_id)) is None
    # Randevu satiri kimliksiz olarak kalir (doluluk / ciro gecmisi).
    assert db.scalar(select(Appointment.id).where(Appointment.customer_id == customer_id))

    # Ayni numara yeniden kayit olabilir: yeni ve bos bir hesap acilir.
    fresh = _login(client)
    assert fresh["isNewCustomer"] is True
    assert fresh["customer"]["id"] != customer_id


def test_anonymized_customer_hidden_from_admin_list(client, salon, db):
    _login(client)
    data_of(client.delete("/api/me"))

    _staff_login(client)
    names = [c["firstName"] for c in data_of(client.get("/api/admin/customers"))["customers"]]
    assert "Silinmiş üye" not in names and "Zeynep" in names


# ---------------------------------------------------------------------
# Saklama sureleri
# ---------------------------------------------------------------------


def test_retention_sweep_removes_only_expired_records(salon, db):
    now = now_local()
    customer_id = salon["customer"].id
    db.add_all([
        SlotViewEvent(branch_id=1, staff_id=1, date="2026-01-01", start_min=600,
                      viewer_key="eski", viewed_at=now - timedelta(days=31)),
        SlotViewEvent(branch_id=1, staff_id=1, date="2026-01-01", start_min=600,
                      viewer_key="yeni", viewed_at=now - timedelta(days=1)),
        ScheduledNotification(customer_id=customer_id, channel="WHATSAPP", body="x",
                              due_at=now - timedelta(days=200), status="SENT",
                              dedupe_key="pre:eski"),
        ScheduledNotification(customer_id=customer_id, channel="WHATSAPP", body="x",
                              due_at=now - timedelta(days=200), status="PENDING",
                              dedupe_key="pre:bekleyen"),
        PhoneRiskEvent(phone_hash="a" * 64, outcome="NO_SHOW",
                       occurred_at=now - timedelta(days=400)),
        PhoneRiskEvent(phone_hash="b" * 64, outcome="NO_SHOW",
                       occurred_at=now - timedelta(days=100)),
    ])
    db.commit()

    result = sweep_retention(db, now)
    assert result == {"removedSlotViews": 1, "removedNotifications": 1, "removedRiskEvents": 1}
    assert db.scalars(select(SlotViewEvent.viewer_key)).all() == ["yeni"]
    assert db.scalars(select(ScheduledNotification.dedupe_key)).all() == ["pre:bekleyen"]
