"""Randevuyu alana "randevunuz olusturuldu" onayi: kuyruga yazilir, kuyruktan gider."""

from __future__ import annotations

from sqlalchemy import select

from app.models import Appointment, ScheduledNotification
from app.services.notifications import deliver_due_notifications
from tests.test_book_for_other import BEN, BOOKER, book, client, data_of, fake_sender, login  # noqa: F401
from tests.test_group_booking import C_BEN, confirm_group, lock_group


def _confirmations(db):
    db.expire_all()
    return db.scalars(
        select(ScheduledNotification).where(ScheduledNotification.dedupe_key.like("confirm%"))
    ).all()


def _sent_confirmations(sender):
    return [(p, t) for p, t in sender.sent if "oluşturuldu ✅" in t]


def test_self_booking_queues_and_delivers_confirmation(client, salon, fake_sender, db):
    login(client, BOOKER)
    appt = data_of(book(client, salon))["appointment"]

    rows = _confirmations(db)
    assert [r.dedupe_key for r in rows] == [f"confirm:{appt['id']}"]
    assert rows[0].status == "PENDING"

    assert deliver_due_notifications(db)["sent"] == 1
    [(phone, text)] = _sent_confirmations(fake_sender)
    assert phone == BOOKER
    assert "randevunuz oluşturuldu" in text and "Manikür" in text and "/randevularim" in text
    assert _confirmations(db)[0].status == "SENT"


def test_booking_for_other_confirms_booker_and_informs_recipient(client, salon, fake_sender, db):
    login(client, BOOKER)
    data_of(book(client, salon, beneficiary=BEN))

    deliver_due_notifications(db)
    [(phone, text)] = _sent_confirmations(fake_sender)
    assert phone == BOOKER and "Deniz için" in text
    # Aliciya ayrica bilgilendirme gider (degismedi).
    assert any(p == BEN["phone"] for p, _ in fake_sender.sent)


def test_confirmation_waits_while_channel_down(client, salon, fake_sender, db):
    login(client, BOOKER)
    data_of(book(client, salon))
    fake_sender.ready = False
    assert deliver_due_notifications(db)["skipped"] is True
    assert _confirmations(db)[0].status == "PENDING"

    fake_sender.ready = True
    assert deliver_due_notifications(db)["sent"] == 1
    assert len(_sent_confirmations(fake_sender)) == 1


def test_cancel_withdraws_unsent_confirmation(client, salon, db):
    login(client, BOOKER)
    appt = data_of(book(client, salon))["appointment"]
    data_of(client.patch(f"/api/appointments/{appt['id']}", json={"status": "CANCELLED", "expectedVersion": 0}))
    assert _confirmations(db)[0].status == "CANCELLED"


def test_group_booking_sends_single_summary_to_booker(client, salon, fake_sender, db):
    login(client, BOOKER)
    assignments = [(salon["staff_a"], "self"), (salon["staff_b"], C_BEN)]
    group = data_of(lock_group(client, salon, assignments))
    data_of(confirm_group(client, group, assignments))

    rows = _confirmations(db)
    assert [r.dedupe_key for r in rows] == [f"confirm-group:{group['groupId']}"]
    deliver_due_notifications(db)
    [(phone, text)] = _sent_confirmations(fake_sender)
    assert phone == BOOKER
    assert "2 kişilik grup randevunuz" in text and "Cem için" in text
    assert db.scalar(select(Appointment.id).where(Appointment.booking_group_id == group["groupId"]))
