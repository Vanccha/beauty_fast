"""Ziyaret sonrasi mesaj + hizmet bazli yenileme daveti + RET cikisi."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.package_layout import layout_package
from app.main import app
from app.models import Appointment, Customer, ReminderRule, Salon, ScheduledNotification
from app.services import messaging, post_visit, rebooking, whatsapp_inbound
from app.services.appointment import confirm_appointment_from_lock
from app.services.appointment_status import change_appointment_status
from app.services.notifications import deliver_due_notifications
from app.services.soft_lock import acquire_slot_lock
from app.time_utils import add_days_to_key, now_local, to_date_key, to_datetime

from .conftest import spec_of
from .test_whatsapp_welcome import FakeSender

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)


def _create(db, salon, services=("manikur",), start_min=600, customer=None, date=TOMORROW):
    customer = customer or salon["customer"]
    layout = layout_package([spec_of(salon[k]) for k in services])
    lock = acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="s", date=date, start_min=start_min, layout=layout,
        customer_id=customer.id,
    )
    return confirm_appointment_from_lock(
        db, lock_id=lock.lock_id, session_id="s", customer_id=customer.id,
        branch_id=salon["branch"].id, staff_id=salon["staff_a"].id, date=date,
        start_min=start_min, layout=layout,
    )


def _complete(db, appt, now=None):
    return change_appointment_status(
        db, appointment_id=appt.id, status="COMPLETED", expected_version=0, now=now
    )


def _notes(db, prefix):
    db.expire_all()
    return db.scalars(
        select(ScheduledNotification)
        .where(ScheduledNotification.dedupe_key.like(f"{prefix}%"))
        .order_by(ScheduledNotification.id)
    ).all()


def _enable_post_visit(db, salon, **kw):
    row = db.get(Salon, salon["salon"].id)
    row.post_visit_enabled = True
    for k, v in kw.items():
        setattr(row, k, v)
    db.commit()


def _rule(db, salon, service_key, days=30, active=True, formula="FIXED", params="{}"):
    rule = ReminderRule(
        branch_id=salon["branch"].id, name=f"{service_key} kural", service_id=salon[service_key].id,
        formula=formula, base_days=days, params=params, channel="WHATSAPP",
        template=rebooking.DEFAULT_TEMPLATE, priority=50, is_active=active,
    )
    db.add(rule)
    db.commit()
    return rule


def _consent(db, customer):
    c = db.get(Customer, customer.id)
    c.marketing_consent_at = now_local()
    db.commit()


@pytest.fixture()
def fake(monkeypatch):
    sender = FakeSender()
    monkeypatch.setattr(messaging, "_sender", sender)
    return sender


# ---------------------------------------------------------------------
# A) Ziyaret sonrasi mesaj
# ---------------------------------------------------------------------


def test_completion_queues_post_visit_with_links(salon, db):
    _enable_post_visit(db, salon)
    appt = _create(db, salon)
    now = now_local()
    result = _complete(db, appt, now=now)
    assert result["postVisitQueued"] is True

    [n] = _notes(db, "postvisit:")
    assert n.dedupe_key == f"postvisit:{appt.id}" and n.channel == "WHATSAPP"
    assert n.status == "PENDING"
    assert abs((n.due_at - (now + timedelta(hours=2))).total_seconds()) < 1
    assert n.body.startswith("Merhaba Ayşe, bugün bizi tercih ettiğiniz için teşekkürler!")
    assert "/randevularim" in n.body
    assert "https://g.page/r/ORNEK-GOOGLE-YORUM-LINKI/review" in n.body
    assert "https://instagram.com/ornek_salon" in n.body
    assert "indirim" not in n.body.lower()


def test_empty_links_omit_their_lines_and_delay_is_configurable(salon, db):
    _enable_post_visit(db, salon, google_review_url="", instagram_url="", post_visit_delay_hours=5)
    appt = _create(db, salon)
    now = now_local()
    _complete(db, appt, now=now)
    [n] = _notes(db, "postvisit:")
    assert "Google" not in n.body and "Instagram" not in n.body
    assert "/randevularim" in n.body
    assert abs((n.due_at - (now + timedelta(hours=5))).total_seconds()) < 1


def test_toggle_off_queues_nothing(salon, db):
    appt = _create(db, salon)  # varsayilan: kapali
    assert _complete(db, appt)["postVisitQueued"] is False
    assert _notes(db, "postvisit:") == []


def test_anonymized_customer_gets_no_post_visit(salon, db):
    _enable_post_visit(db, salon)
    appt = _create(db, salon)
    c = db.get(Customer, salon["customer"].id)
    c.anonymized_at = now_local()
    db.commit()
    _complete(db, appt)
    assert _notes(db, "postvisit:") == []


def test_post_visit_cancelled_when_status_leaves_completed(salon, db):
    _enable_post_visit(db, salon)
    appt = _create(db, salon)
    _complete(db, appt)
    assert len(_notes(db, "postvisit:")) == 1
    # Tamamlanmis randevu normal akista degistirilemez; geri alma yolu
    # (yonetici duzeltmesi) dogrudan servisle test edilir.
    post_visit.cancel_post_visit(db, appt.id)
    db.commit()
    assert _notes(db, "postvisit:")[0].status == "CANCELLED"


def test_post_visit_is_delivered_without_marketing_consent(salon, db, fake):
    _enable_post_visit(db, salon, post_visit_delay_hours=0)
    appt = _create(db, salon)
    _complete(db, appt, now=now_local() - timedelta(minutes=1))
    deliver_due_notifications(db)
    assert len(fake.sent) == 1 and "teşekkürler" in fake.sent[0][1]


# ---------------------------------------------------------------------
# B) Yenileme daveti
# ---------------------------------------------------------------------


def test_rebooking_scheduled_at_base_days_with_optout_line(salon, db):
    _consent(db, salon["customer"])
    rule = _rule(db, salon, "manikur", days=14)
    appt = _create(db, salon)
    result = _complete(db, appt)
    assert result["reminderQueued"] is True

    [n] = _notes(db, "repeat:")
    assert n.rule_id == rule.id
    performed = db.get(Appointment, appt.id)
    assert n.due_at == to_datetime(performed.date, performed.end_min) + timedelta(days=14)
    assert n.body.startswith("Merhaba Ayşe, son Manikür işleminizin üzerinden epey zaman geçti.")
    assert "/randevu" in n.body
    assert n.body.endswith("Bu mesajları almak istemiyorsanız RET yazabilirsiniz.")


def test_rebooking_requires_marketing_consent(salon, db):
    _rule(db, salon, "manikur", days=14)
    appt = _create(db, salon)
    assert _complete(db, appt)["reminderQueued"] is False
    assert _notes(db, "repeat:") == []


def test_multiple_services_queue_single_earliest(salon, db):
    _consent(db, salon["customer"])
    _rule(db, salon, "boya", days=90)
    kas_rule = _rule(db, salon, "kas", days=20)
    _rule(db, salon, "manikur", days=45)
    appt = _create(db, salon, services=("boya", "kas", "manikur"))
    _complete(db, appt)
    [n] = _notes(db, "repeat:")
    assert n.rule_id == kas_rule.id
    assert "son Kaş Alma işleminizin" in n.body


def test_inactive_service_rule_means_off_and_no_rule_uses_recommended_days(salon, db):
    _consent(db, salon["customer"])
    _rule(db, salon, "manikur", days=14, active=False)
    appt = _create(db, salon)
    assert _complete(db, appt)["reminderQueued"] is False
    # Kural hic yoksa hizmetin onerilen araligina (21 gun) varsayilan metinle dusulur.
    appt2 = _create(db, salon, services=("kas",), start_min=700)
    assert _complete(db, appt2)["reminderQueued"] is True
    [n] = _notes(db, "repeat:")
    assert n.rule_id is None and "son Kaş Alma işleminizin" in n.body


def test_new_completion_replaces_pending_rebooking(salon, db):
    _consent(db, salon["customer"])
    _rule(db, salon, "manikur", days=14)
    _rule(db, salon, "kas", days=30)
    a1 = _create(db, salon, start_min=600)
    _complete(db, a1)
    a2 = _create(db, salon, services=("kas",), start_min=700)
    _complete(db, a2)
    rows = _notes(db, "repeat:")
    assert [r.status for r in rows] == ["CANCELLED", "PENDING"]


def test_new_booking_before_due_skips_pending_rebooking(salon, db, fake):
    _consent(db, salon["customer"])
    _rule(db, salon, "manikur", days=1)
    a1 = _create(db, salon, start_min=600, date=to_date_key(now_local()))
    _complete(db, a1, now=now_local())
    # Musteri tekrar randevu almis (gelecekte aktif)
    _create(db, salon, start_min=700, date=add_days_to_key(to_date_key(now_local()), 5))
    n = _notes(db, "repeat:")[0]
    n.due_at = now_local() - timedelta(minutes=1)
    db.commit()
    deliver_due_notifications(db)
    assert fake.sent == []
    assert _notes(db, "repeat:")[0].status == "CANCELLED"


def test_marketing_withdrawn_after_queue_blocks_send(salon, db, fake):
    _consent(db, salon["customer"])
    _rule(db, salon, "manikur", days=1)
    a1 = _create(db, salon)
    _complete(db, a1, now=now_local())
    n = _notes(db, "repeat:")[0]
    n.due_at = now_local() - timedelta(minutes=1)
    c = db.get(Customer, salon["customer"].id)
    c.marketing_consent_at = None
    db.commit()
    deliver_due_notifications(db)
    assert fake.sent == []


# ---------------------------------------------------------------------
# RET cikisi
# ---------------------------------------------------------------------


def _inbound(text, jid="905321010000@s.whatsapp.net"):
    return {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": jid, "fromMe": False, "id": f"M{time.time_ns()}"},
            "message": {"conversation": text},
            "messageType": "conversation",
            "messageTimestamp": int(time.time()),
        },
    }


@pytest.mark.parametrize("text", ["RET", " ret ", "Ret.", "ret!"])
def test_ret_keyword_clears_consent_and_cancels_pending(salon, db, text):
    _consent(db, salon["customer"])
    _rule(db, salon, "manikur", days=14)
    _complete(db, _create(db, salon))
    assert _notes(db, "repeat:")[0].status == "PENDING"

    job = whatsapp_inbound.handle_event(db, _inbound(text))
    assert job is None
    db.expire_all()
    assert db.get(Customer, salon["customer"].id).marketing_consent_at is None
    assert _notes(db, "repeat:")[0].status == "CANCELLED"


def test_iptal_keyword_does_not_touch_consent(salon, db):
    _consent(db, salon["customer"])
    whatsapp_inbound.handle_event(db, _inbound("iptal"))
    db.expire_all()
    assert db.get(Customer, salon["customer"].id).marketing_consent_at is not None


# ---------------------------------------------------------------------
# Admin uclari
# ---------------------------------------------------------------------


@pytest.fixture()
def staff_client(salon):
    with TestClient(app) as c:
        assert c.post(
            "/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}
        ).status_code == 200
        yield c


def _rows(payload):
    return {s["name"]: s for g in payload["groups"] for s in g["services"]}


def test_post_visit_settings_roundtrip(staff_client, salon, db):
    r = staff_client.get("/api/admin/messaging/post-visit").json()["data"]
    assert r["enabled"] is False and r["delayHours"] == 2 and r["message"] is None
    assert r["googleReviewUrl"].startswith("https://g.page/r/ORNEK")

    r = staff_client.put(
        "/api/admin/messaging/post-visit",
        json={
            "enabled": True, "delayHours": 3, "message": "Selam {ad} {yorum_linki}",
            "googleReviewUrl": "", "instagramUrl": "https://instagram.com/x",
        },
    ).json()["data"]
    assert r["enabled"] is True and r["delayHours"] == 3 and r["googleReviewUrl"] == ""
    assert r["message"] == "Selam {ad} {yorum_linki}"

    bad = staff_client.put(
        "/api/admin/messaging/post-visit",
        json={"enabled": True, "delayHours": 2, "googleReviewUrl": "javascript:x"},
    )
    assert bad.status_code == 400

    # Varsayilanla ayni metin kaydedilmez
    r = staff_client.put(
        "/api/admin/messaging/post-visit",
        json={"enabled": True, "delayHours": 2, "message": post_visit.DEFAULT_POST_VISIT},
    ).json()["data"]
    assert r["message"] is None


def test_rebooking_admin_create_toggle_and_advanced(staff_client, salon, db):
    _consent(db, salon["customer"])
    data = staff_client.get("/api/admin/rebooking").json()["data"]
    assert data["marketingConsentCount"] == 1
    assert _rows(data)["Manikür"]["rule"] is None

    r = staff_client.put(
        "/api/admin/rebooking",
        json={"serviceId": salon["manikur"].id, "enabled": True, "baseDays": 14},
    ).json()["data"]
    rule = _rows(r)["Manikür"]["rule"]
    assert rule["baseDays"] == 14 and rule["isActive"] and not rule["advanced"]
    assert rule["template"] == rebooking.DEFAULT_TEMPLATE

    r = staff_client.put(
        "/api/admin/rebooking",
        json={"serviceId": salon["manikur"].id, "enabled": False, "baseDays": 21,
              "template": "Selam {ad}"},
    ).json()["data"]
    rule = _rows(r)["Manikür"]["rule"]
    assert rule["isActive"] is False and rule["baseDays"] == 21 and rule["template"] == "Selam {ad}"

    # Gelismis kural: sure degistirilmez, switchToSimple ile FIXED'e donusur
    db.add(ReminderRule(
        branch_id=salon["branch"].id, name="Dip", service_id=salon["boya"].id, formula="GROWTH",
        base_days=35, params='{"mmPerMonth": 12, "toleranceMm": 14}', channel="WHATSAPP",
        template="x {ad}", priority=30, is_active=True,
    ))
    db.commit()
    r = staff_client.put(
        "/api/admin/rebooking",
        json={"serviceId": salon["boya"].id, "enabled": True, "baseDays": 99},
    ).json()["data"]
    rule = _rows(r)["Saç Boyası"]["rule"]
    assert rule["advanced"] is True and rule["baseDays"] == 35
    r = staff_client.put(
        "/api/admin/rebooking",
        json={"serviceId": salon["boya"].id, "enabled": True, "baseDays": 90,
              "switchToSimple": True},
    ).json()["data"]
    rule = _rows(r)["Saç Boyası"]["rule"]
    assert rule["advanced"] is False and rule["baseDays"] == 90

    assert staff_client.put(
        "/api/admin/rebooking", json={"serviceId": 999999, "enabled": True, "baseDays": 5}
    ).status_code == 404
