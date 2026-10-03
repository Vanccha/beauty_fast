"""Iptalde "randevunuz iptal edildi" WhatsApp mesaji kuyruga yazilir."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Customer, ScheduledNotification
from app.services.notifications import deliver_due_notifications
from tests.test_book_for_other import BEN, BOOKER, book, client, data_of, fake_sender, login  # noqa: F401
from tests.test_group_booking import C_BEN, confirm_group, lock_group


def _cancels(db):
    db.expire_all()
    return db.scalars(
        select(ScheduledNotification)
        .where(ScheduledNotification.dedupe_key.like("cancel%"))
        .order_by(ScheduledNotification.id)
    ).all()


def _phone_of(db, customer_id):
    return db.get(Customer, customer_id).phone


def _cancel(client, appt_id):
    return client.patch(
        f"/api/appointments/{appt_id}", json={"status": "CANCELLED", "expectedVersion": 0}
    )


def test_customer_cancel_queues_message(client, salon, fake_sender, db):
    login(client, BOOKER)
    appt = data_of(book(client, salon))["appointment"]
    data_of(_cancel(client, appt["id"]))

    rows = _cancels(db)
    assert len(rows) == 1 and rows[0].status == "PENDING"
    assert rows[0].dedupe_key.startswith(f"cancel:{appt['id']}:")
    deliver_due_notifications(db)
    sent = [(p, t) for p, t in fake_sender.sent if "iptal edildi" in t]
    assert len(sent) == 1
    phone, text = sent[0]
    assert phone == BOOKER
    assert text.startswith("Merhaba ") and "Manikür" in text and "saat 10:00" in text
    assert "randevunuz iptal edildi. Yeni randevu almak için: " in text
    assert text.endswith("/randevu")


def test_staff_cancel_queues_message_and_noshow_does_not(client, salon, db):
    login(client, BOOKER)
    a1 = data_of(book(client, salon))["appointment"]
    a2 = data_of(book(client, salon, start=720))["appointment"]
    staff = TestClient(app)
    assert staff.post(
        "/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}
    ).status_code == 200
    r = staff.patch(
        f"/api/admin/appointments/{a1['id']}/status",
        json={"status": "CANCELLED", "expectedVersion": 0},
    )
    assert r.json()["ok"] is True
    r = staff.patch(
        f"/api/admin/appointments/{a2['id']}/status",
        json={"status": "NO_SHOW", "expectedVersion": 0},
    )
    assert r.json()["ok"] is True
    rows = _cancels(db)
    assert [r.dedupe_key.split(":")[1] for r in rows] == [str(a1["id"])]


def test_booked_for_other_informs_both(client, salon, fake_sender, db):
    login(client, BOOKER)
    appt = data_of(book(client, salon, beneficiary=BEN))["appointment"]
    data_of(_cancel(client, appt["id"]))
    rows = _cancels(db)
    assert len(rows) == 2
    deliver_due_notifications(db)
    sent = {p: t for p, t in fake_sender.sent if "iptal edildi" in t}
    assert set(sent) == {BOOKER, BEN["phone"]}
    assert "Deniz için" in sent[BOOKER]
    assert "Deniz için" not in sent[BEN["phone"]]


def test_cancel_twice_single_message(client, salon, db):
    login(client, BOOKER)
    appt = data_of(book(client, salon))["appointment"]
    data_of(_cancel(client, appt["id"]))
    assert _cancel(client, appt["id"]).status_code == 409
    assert len(_cancels(db)) == 1


def test_withdraws_pending_reminder_and_confirmation(client, salon, db):
    login(client, BOOKER)
    appt = data_of(book(client, salon))["appointment"]
    data_of(_cancel(client, appt["id"]))
    db.expire_all()
    leftovers = db.scalars(
        select(ScheduledNotification).where(
            ScheduledNotification.status == "PENDING",
            ScheduledNotification.dedupe_key.in_((f"pre:{appt['id']}:24", f"confirm:{appt['id']}")),
        )
    ).all()
    assert leftovers == []


def test_anonymized_customer_gets_no_message(client, salon, db):
    from app.time_utils import now_local

    login(client, BOOKER)
    appt = data_of(book(client, salon))["appointment"]
    cid = db.scalar(select(Customer.id).where(Customer.phone == BOOKER))
    db.get(Customer, cid).anonymized_at = now_local()
    db.commit()
    from app.services.appointment_status import change_appointment_status

    change_appointment_status(db, appt["id"], "CANCELLED")
    assert _cancels(db) == []


def test_group_cancel_summary_plus_one_per_beneficiary(client, salon, fake_sender, db):
    login(client, BOOKER)
    asg = [(salon["staff_a"], "self"), (salon["staff_b"], C_BEN)]
    group = data_of(lock_group(client, salon, asg))
    data_of(confirm_group(client, group, asg))
    r = client.post(f"/api/appointments/group/{group['groupId']}/cancel")
    assert data_of(r)["cancelled"] == 2

    rows = _cancels(db)
    keys = sorted(r.dedupe_key.split(":")[0] for r in rows)
    assert keys == ["cancel", "cancel-group"]
    deliver_due_notifications(db)
    sent = [(p, t) for p, t in fake_sender.sent if "iptal edildi" in t]
    assert len(sent) == 2
    by_phone = dict(sent)
    assert "2 kişilik grup randevunuz iptal edildi" in by_phone[BOOKER]
    assert "Cem için" in by_phone[BOOKER]
    assert C_BEN["phone"] in by_phone and "grup" not in by_phone[C_BEN["phone"]]

    # Ikinci iptal yeni mesaj uretmez.
    client.post(f"/api/appointments/group/{group['groupId']}/cancel")
    assert len(_cancels(db)) == 2
