"""Kapora (deposit): ayarlar, hesap, online/grup/manuel akis, odendi, gecikme
push'u, iptal/iade/yanma kurallari, iade hatirlatmalari, geri alma."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.models import Appointment, ScheduledNotification
from app.services import deposit, deposit_watch
from app.services.notifications import deliver_due_notifications
from app.time_utils import now_local, to_date_key
from tests.test_book_for_other import (  # noqa: F401
    BEN,
    BOOKER,
    book,
    client,
    data_of,
    error_of,
    fake_sender,
    login,
)
from tests.test_group_booking import C_BEN, DAY, confirm_group, lock_group
from tests.test_push import spy, staff_client, team  # noqa: F401

TR_IBAN = "TR330006100519786457841326"
TR_IBAN_SPACED = "TR33 0006 1005 1978 6457 8413 26"
GB_IBAN = "GB82 WEST 1234 5698 7654 32"

SETTINGS_BODY = {
    "enabled": True,
    "percent": 20,
    "minAmount": 100,
    "iban": TR_IBAN_SPACED,
    "accountName": "Aurora Güzellik",
    "bankName": "Ziraat",
    "deadlineMinutes": 60,
    "message": None,
}


# ------------------------------------------------------------------ yardimcilar


def enable(db, salon, **over):
    row = salon["salon"]
    db.refresh(row)
    row.deposit_enabled = True
    row.deposit_iban = TR_IBAN
    row.deposit_account_name = "Aurora Güzellik"
    for key, value in over.items():
        setattr(row, key, value)
    db.commit()


def appt_of(db, appointment_id) -> Appointment:
    db.expire_all()
    return db.get(Appointment, appointment_id)


def version_of(db, appointment_id) -> int:
    return appt_of(db, appointment_id).version


def customer_cancel(client, db, appointment_id):
    return client.patch(
        f"/api/appointments/{appointment_id}",
        json={"status": "CANCELLED", "expectedVersion": version_of(db, appointment_id)},
    )


def staff_status(staff, db, appointment_id, status, **extra):
    return staff.patch(
        f"/api/admin/appointments/{appointment_id}/status",
        json={"status": status, "expectedVersion": version_of(db, appointment_id), **extra},
    )


def start_in(db, appointment_id, minutes):
    t = now_local() + timedelta(minutes=minutes)
    db.execute(
        update(Appointment)
        .where(Appointment.id == appointment_id)
        .values(date=to_date_key(t), start_min=t.hour * 60 + t.minute)
    )
    db.commit()


def texts(fake_sender, needle=""):
    return [t for _p, t in fake_sender.sent if needle in t]


def book_deposit(client, db, salon, **kw):
    enable(db, salon)
    login(client, BOOKER)
    return data_of(book(client, salon, **kw))


def paid_appointment(client, db, salon, team, **kw):
    """Kapora acik, online randevu alinmis ve yonetici 'odendi' demis."""
    data = book_deposit(client, db, salon, **kw)
    aid = data["appointment"]["id"]
    data_of(team["manager"].post(f"/api/admin/appointments/{aid}/deposit/paid", json={}))
    return aid


# ------------------------------------------------------------------ IBAN + hesap


def test_iban_validation():
    assert deposit.validate_iban(TR_IBAN_SPACED) == TR_IBAN
    assert deposit.validate_iban("tr33 0006 1005 1978 6457 8413 26") == TR_IBAN
    assert deposit.validate_iban(GB_IBAN) == "GB82WEST12345698765432"  # TR olmayan: mod-97
    assert deposit.validate_iban("DE89370400440532013000")
    for bad in (
        "TR330006100519786457841327",  # kontrol basamagi hatali
        "TR3300061005197864578413",  # kisa
        "GB82WEST12345698765433",  # TR disi, mod-97 hatali
        "",
        "123",
        "TR33000610051978645784132A",
    ):
        with pytest.raises(ValueError):
            deposit.validate_iban(bad)
    assert deposit.format_iban(TR_IBAN) == TR_IBAN_SPACED


def test_compute_deposit_percent_min_cap_rounding():
    assert deposit.compute_deposit(1000, 20, 100) == 200  # yuzde
    assert deposit.compute_deposit(350, 20, 100) == 100  # alt sinir
    assert deposit.compute_deposit(80, 20, 100) == 80  # fiyati gecmez
    assert deposit.compute_deposit(333, 20, 0) == 67  # 66.6 -> tam TL
    assert deposit.compute_deposit(0, 20, 100) == 0
    assert deposit.compute_deposit(99.5, 20, 100) == 99  # tavan: fiyatin tam kismi
    assert deposit.format_tl(1200) == "1.200 TL"


# ------------------------------------------------------------------ ayarlar


def test_settings_default_off_and_manager_only(salon, team):
    got = data_of(team["manager"].get("/api/admin/settings/deposit"))
    assert got["enabled"] is False and got["percent"] == 20 and got["minAmount"] == 100
    assert got["deadlineMinutes"] == 60 and got["iban"] == ""
    assert "Kapora ulaştığında" in got["defaultMessage"]
    assert "{aciklama}" in got["placeholders"]
    assert team["staff_b"].get("/api/admin/settings/deposit").status_code == 403
    assert team["staff_b"].put("/api/admin/settings/deposit", json=SETTINGS_BODY).status_code == 403


def test_settings_put_validates_iban(salon, team, db):
    owner = team["owner"]
    saved = data_of(owner.put("/api/admin/settings/deposit", json=SETTINGS_BODY))
    assert saved["enabled"] and saved["iban"] == TR_IBAN_SPACED
    assert "IBAN" in saved["preview"] and "Ayşe" in saved["preview"]

    bad = owner.put("/api/admin/settings/deposit", json={**SETTINGS_BODY, "iban": "TR330006100519786457841327"})
    assert bad.status_code == 400 and "doğrulama" in error_of(bad)["message"]
    assert owner.put("/api/admin/settings/deposit", json={**SETTINGS_BODY, "iban": ""}).status_code == 400
    assert owner.put("/api/admin/settings/deposit", json={**SETTINGS_BODY, "accountName": " "}).status_code == 400
    assert owner.put("/api/admin/settings/deposit", json={**SETTINGS_BODY, "percent": 0}).status_code == 400
    # Kapali iken bos IBAN kabul edilir; yabanci IBAN da gecer.
    data_of(owner.put("/api/admin/settings/deposit", json={**SETTINGS_BODY, "enabled": False, "iban": ""}))
    out = data_of(owner.put("/api/admin/settings/deposit", json={**SETTINGS_BODY, "iban": GB_IBAN}))
    assert out["iban"].startswith("GB82")
    # Varsayilan metin kaydedilirse null'a doner.
    out = data_of(owner.put("/api/admin/settings/deposit", json={**SETTINGS_BODY, "message": deposit.DEFAULT_TEMPLATE}))
    assert out["message"] is None


def test_public_info_and_lock_preview(client, salon, db):
    info = data_of(client.get("/api/deposit/info"))
    assert info["enabled"] is False and info["policy"] is None
    enable(db, salon)
    info = data_of(client.get("/api/deposit/info"))
    assert info["enabled"] and "1 saatten az kala iptal yapılamaz" in info["policy"]
    assert "iban" not in str(info).lower()
    from tests.test_book_for_other import lock_body

    lock = data_of(client.post("/api/slots/lock", json=lock_body(salon)))
    assert lock["deposit"]["enabled"] is True and lock["deposit"]["amount"] == 100


# ------------------------------------------------------------------ online randevu


def test_deposit_off_keeps_old_behavior(client, salon, fake_sender, db):
    login(client, BOOKER)
    data = data_of(book(client, salon))
    assert data["deposit"] is None and data["appointment"]["status"] == "CONFIRMED"
    a = appt_of(db, data["appointment"]["id"])
    assert a.status == "CONFIRMED" and a.deposit_status == "NONE" and a.deposit_amount is None
    deliver_due_notifications(db)
    assert texts(fake_sender, "oluşturuldu ✅") and not texts(fake_sender, "kapora")


def test_online_booking_with_deposit_is_pending_awaiting(client, salon, fake_sender, db):
    data = book_deposit(client, db, salon)
    aid = data["appointment"]["id"]
    a = appt_of(db, aid)
    assert (a.status, a.deposit_status, float(a.deposit_amount)) == ("PENDING", "AWAITING", 100.0)
    assert a.deposit_requested_at is not None
    dep = data["deposit"]
    assert dep["status"] == "AWAITING" and dep["payAmount"] == 100
    assert dep["iban"] == TR_IBAN_SPACED and dep["accountName"] == "Aurora Güzellik"
    assert dep["reference"] == f"R{aid} Ayşe Y." and "iade edilmez" in dep["policy"]

    keys = [r.dedupe_key for r in db.scalars(select(ScheduledNotification))]
    assert f"deposit:{aid}" in keys and f"confirm:{aid}" not in keys
    deliver_due_notifications(db)
    [text] = texts(fake_sender, "kapora gerekmektedir")
    assert "100 TL kapora" in text and f"IBAN: {TR_IBAN_SPACED}" in text
    assert "Alıcı: Aurora Güzellik" in text and f"Açıklama: R{aid} Ayşe Y." in text
    assert "Manikür" in text and "Merhaba Ayşe" in text
    assert not texts(fake_sender, "oluşturuldu ✅")

    # Slot dolu: ayni saat baskasi tarafindan alinamaz.
    mine = data_of(client.get("/api/appointments/mine"))["upcoming"][0]
    assert mine["status"] == "PENDING" and mine["deposit"]["status"] == "AWAITING"
    assert mine["deposit"]["iban"] == TR_IBAN_SPACED and mine["cancellable"] is True
    cal = data_of(
        staff_client("5551110001", "admin123").get("/api/admin/calendar", params={"date": a.date})
    )
    item = next(x for x in cal["appointments"] if x["id"] == aid)
    assert item["deposit"]["status"] == "AWAITING" and cal["depositEnabled"] is True


def test_custom_template_and_bank_line(client, salon, fake_sender, db):
    enable(db, salon, deposit_message="{ad}: {kapora} / {tutar}\n{banka}\n{aciklama}", deposit_bank_name="")
    login(client, BOOKER)
    aid = data_of(book(client, salon))["appointment"]["id"]
    deliver_due_notifications(db)
    total = deposit.format_tl(appt_of(db, aid).total_price)  # firsat indirimi gune gore degisir
    [text] = texts(fake_sender, f"100 TL / {total}")
    assert text == f"Ayşe: 100 TL / {total}\nR{aid} Ayşe Y."  # bos banka satiri atildi


def test_booked_for_other_booker_pays(client, salon, fake_sender, db):
    enable(db, salon)
    login(client, BOOKER)
    aid = data_of(book(client, salon, beneficiary=BEN))["appointment"]["id"]
    assert appt_of(db, aid).deposit_status == "AWAITING"
    deliver_due_notifications(db)
    to_booker = [t for p, t in fake_sender.sent if p == BOOKER and "kapora" in t]
    assert len(to_booker) == 1 and "(Deniz için)" in to_booker[0]
    # Alici yine mevcut bilgilendirmeyi alir (kapora mesaji almaz).
    to_ben = [t for p, t in fake_sender.sent if p == BEN["phone"]]
    assert to_ben and not any("IBAN" in t for t in to_ben)
    mine = data_of(client.get("/api/appointments/mine"))["upcoming"][0]
    assert mine["deposit"]["iban"]  # alan kisi odeme bilgisini gorur


def test_group_booking_combined_deposit(client, salon, fake_sender, db):
    enable(db, salon)
    login(client, BOOKER)
    assignments = [(salon["staff_a"], "self"), (salon["staff_b"], C_BEN)]
    group = data_of(lock_group(client, salon, assignments))
    assert group["deposit"]["enabled"] and group["deposit"]["amount"] == 200
    res = data_of(confirm_group(client, group, assignments))
    ids = [r["appointmentId"] for r in res["appointments"]]
    assert res["deposit"]["payAmount"] == 200 and res["deposit"]["reference"] == f"R{ids[0]}-{ids[1]} Ayşe Y."
    assert all(appt_of(db, i).status == "PENDING" and appt_of(db, i).deposit_status == "AWAITING" for i in ids)
    keys = [r.dedupe_key for r in db.scalars(select(ScheduledNotification))]
    assert f"deposit-group:{group['groupId']}" in keys
    assert not any(k.startswith("confirm") for k in keys)
    deliver_due_notifications(db)
    [text] = texts(fake_sender, "kapora gerekmektedir")
    assert "200 TL kapora" in text and "Cem" in text

    # Havale toplam icindir: biri 'odendi' denince grubun tamami kesinlesir, tek mesaj.
    manager = staff_client("5551110001", "admin123")
    out = data_of(manager.post(f"/api/admin/appointments/{ids[0]}/deposit/paid", json={}))
    assert sorted(out["ids"]) == sorted(ids)
    assert all(appt_of(db, i).status == "CONFIRMED" and appt_of(db, i).deposit_status == "PAID" for i in ids)
    deliver_due_notifications(db)
    assert len(texts(fake_sender, "kaporanız ulaştı")) == 1


# ------------------------------------------------------------------ odendi


def test_mark_paid_manager_only_confirms_and_messages(client, salon, fake_sender, db, team):
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    deliver_due_notifications(db)
    fake_sender.sent.clear()

    r = team["staff_b"].post(f"/api/admin/appointments/{aid}/deposit/paid", json={})
    assert r.status_code == 403
    assert appt_of(db, aid).status == "PENDING"

    out = data_of(team["manager"].post(f"/api/admin/appointments/{aid}/deposit/paid", json={}))
    assert out["status"] == "CONFIRMED" and out["depositStatus"] == "PAID"
    a = appt_of(db, aid)
    assert a.status == "CONFIRMED" and a.deposit_status == "PAID"
    assert a.deposit_paid_at is not None and a.deposit_paid_by_staff_id is not None
    deliver_due_notifications(db)
    [text] = texts(fake_sender, "kaporanız ulaştı")
    assert text.startswith("Merhaba Ayşe, kaporanız ulaştı.") and "randevunuz kesinleşti" in text
    assert not texts(fake_sender, "oluşturuldu")  # normal onay cift gitmez

    again = team["manager"].post(f"/api/admin/appointments/{aid}/deposit/paid", json={})
    assert again.status_code == 409
    keys = [r.dedupe_key for r in db.scalars(select(ScheduledNotification))]
    assert keys.count(f"deposit-paid:{aid}") == 1


def test_staff_cannot_confirm_awaiting_manager_can_waive(client, salon, db, team):
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    r = staff_status(team["staff_b"], db, aid, "CONFIRMED")
    assert r.status_code == 403
    data_of(staff_status(team["manager"], db, aid, "CONFIRMED"))
    a = appt_of(db, aid)
    assert a.status == "CONFIRMED" and a.deposit_status == "NONE" and a.deposit_amount is None


# ------------------------------------------------------------------ gecikme push


def test_overdue_push_once_to_managers(client, salon, db, team, spy):  # noqa: F811
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    spy.calls.clear()
    now = now_local()

    assert deposit_watch.check_once(db, now) == {"overdue": 0, "refunds": 0}  # henuz 60 dk dolmadi
    assert not spy.calls

    assert deposit_watch.check_once(db, now + timedelta(minutes=61))["overdue"] == 1
    assert sorted(c["endpoint"].rsplit("/", 1)[1] for c in spy.calls) == ["manager", "owner"]
    payload = spy.calls[0]["payload"]
    assert payload["title"] == "Kapora bekleniyor"
    assert payload["body"].startswith("Ayşe Yılmaz · ")
    assert "100 TL — 1 saattir onaylanmadı" in payload["body"]
    assert len(spy.calls) == 2  # owner + manager (STAFF almaz)

    spy.calls.clear()
    assert deposit_watch.check_once(db, now + timedelta(hours=5))["overdue"] == 0  # tek sefer
    assert not spy.calls
    assert appt_of(db, aid).deposit_overdue_alerted_at is not None


def test_overdue_respects_deposit_pref_and_deadline(client, salon, db, team, spy):  # noqa: F811
    enable(db, salon, deposit_deadline_minutes=90)
    login(client, BOOKER)
    data_of(book(client, salon))
    data_of(
        team["owner"].put(
            "/api/admin/push/prefs", json={"endpoint": "https://push.example.test/owner", "deposit": False}
        )
    )
    spy.calls.clear()
    now = now_local()
    assert deposit_watch.check_once(db, now + timedelta(minutes=70))["overdue"] == 0  # 90 dk ayari
    assert deposit_watch.check_once(db, now + timedelta(minutes=91))["overdue"] == 1
    assert len(spy.calls) == 1 and spy.calls[0]["endpoint"].endswith("/manager")
    assert "90 dakikadır onaylanmadı" in spy.calls[0]["payload"]["body"]


# ------------------------------------------------------------------ admin iptal (kapora yok)


def test_admin_cancel_awaiting_sends_unpaid_message(client, salon, fake_sender, db, team):
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    deliver_due_notifications(db)
    fake_sender.sent.clear()
    data_of(staff_status(team["owner"], db, aid, "CANCELLED", reason="DEPOSIT_UNPAID"))
    a = appt_of(db, aid)
    assert a.status == "CANCELLED" and a.deposit_status == "NONE"
    deliver_due_notifications(db)
    [text] = texts(fake_sender, "kapora yatırılmadığından")
    assert text.startswith("Merhaba Ayşe, ") and text.endswith("/randevu")
    assert "randevunuz iptal edildi." not in "".join(t for _p, t in fake_sender.sent)  # genel mesaj YOK
    assert team["owner"].patch(
        f"/api/admin/appointments/{aid}/status",
        json={"status": "CANCELLED", "expectedVersion": 99, "reason": "x"},
    ).status_code == 400


def test_admin_cancel_awaiting_generic_without_reason(client, salon, fake_sender, db, team):
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    data_of(staff_status(team["owner"], db, aid, "CANCELLED"))
    deliver_due_notifications(db)
    assert texts(fake_sender, "randevunuz iptal edildi") and not texts(fake_sender, "yatırılmadığından")


def test_customer_cancel_awaiting_just_cancels(client, salon, fake_sender, db):
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    data_of(customer_cancel(client, db, aid))
    a = appt_of(db, aid)
    assert a.status == "CANCELLED" and a.deposit_status == "NONE"
    deliver_due_notifications(db)
    assert texts(fake_sender, "randevunuz iptal edildi") and not texts(fake_sender, "Kaporanız 48")


# ------------------------------------------------------------------ musteri iptali: < 60 dk


@pytest.mark.parametrize("with_deposit", [False, True])
def test_customer_cancel_within_hour_forbidden(client, salon, db, with_deposit):
    if with_deposit:
        enable(db, salon)
    login(client, BOOKER)
    aid = data_of(book(client, salon))["appointment"]["id"]
    start_in(db, aid, 30)
    r = customer_cancel(client, db, aid)
    assert r.status_code == 409
    err = error_of(r)
    assert err["code"] == "CANCEL_TOO_LATE"
    assert err["message"] == "Randevuya 1 saatten az kaldığı için iptal edilemez. Kapora iade edilmez."
    assert appt_of(db, aid).status in ("PENDING", "CONFIRMED")
    mine = data_of(client.get("/api/appointments/mine"))["upcoming"][0]
    assert mine["cancellable"] is False and mine["cancelLocked"] is True

    # 90 dk kala hala iptal edilebilir.
    start_in(db, aid, 90)
    assert data_of(customer_cancel(client, db, aid))["status"] == "CANCELLED"


def test_group_cancel_within_hour_forbidden_and_refund_line(client, salon, fake_sender, db, team):
    enable(db, salon)
    login(client, BOOKER)
    assignments = [(salon["staff_a"], "self"), (salon["staff_b"], C_BEN)]
    group = data_of(lock_group(client, salon, assignments))
    res = data_of(confirm_group(client, group, assignments))
    ids = [r["appointmentId"] for r in res["appointments"]]
    data_of(team["manager"].post(f"/api/admin/appointments/{ids[0]}/deposit/paid", json={}))

    start_in(db, ids[1], 20)
    r = client.post(f"/api/appointments/group/{group['groupId']}/cancel")
    assert r.status_code == 409 and error_of(r)["code"] == "CANCEL_TOO_LATE"
    assert all(appt_of(db, i).status == "CONFIRMED" for i in ids)

    start_in(db, ids[1], 24 * 60 * 3)
    fake_sender.sent.clear()
    out = data_of(client.post(f"/api/appointments/group/{group['groupId']}/cancel"))
    assert out["cancelled"] == 2
    assert all(appt_of(db, i).deposit_status == "REFUND_DUE" for i in ids)
    deliver_due_notifications(db)
    [summary] = [t for p, t in fake_sender.sent if p == BOOKER and "grup randevunuz iptal" in t]
    assert summary.endswith("Kaporanız 48 saat içinde tarafınıza gönderilecektir.")


# ------------------------------------------------------------------ iptal / iade / yanma


def test_customer_cancel_paid_becomes_refund_due_with_line(client, salon, fake_sender, db, team):
    aid = paid_appointment(client, db, salon, team)
    deliver_due_notifications(db)
    fake_sender.sent.clear()
    before = now_local()
    data_of(customer_cancel(client, db, aid))
    a = appt_of(db, aid)
    assert a.status == "CANCELLED" and a.deposit_status == "REFUND_DUE"
    assert before + timedelta(hours=47, minutes=59) < a.deposit_refund_due_at < now_local() + timedelta(hours=48, minutes=1)
    deliver_due_notifications(db)
    [text] = texts(fake_sender, "randevunuz iptal edildi")
    assert text.endswith("Kaporanız 48 saat içinde tarafınıza gönderilecektir.")


def test_staff_cancel_paid_defaults_to_refund_or_forfeit(client, salon, fake_sender, db, team):
    a1 = paid_appointment(client, db, salon, team)
    data_of(staff_status(team["staff_b"], db, a1, "CANCELLED"))  # personel de iptal edebilir
    assert appt_of(db, a1).deposit_status == "REFUND_DUE"
    deliver_due_notifications(db)
    assert texts(fake_sender, "Kaporanız 48 saat içinde")

    login(client, BOOKER)
    a2 = data_of(book(client, salon, start=720))["appointment"]["id"]
    data_of(team["manager"].post(f"/api/admin/appointments/{a2}/deposit/paid", json={}))
    r = staff_status(team["staff_b"], db, a2, "CANCELLED", depositForfeit=True)
    assert r.status_code == 403  # kapora yakmak yalniz yonetici
    fake_sender.sent.clear()
    data_of(staff_status(team["manager"], db, a2, "CANCELLED", depositForfeit=True))
    assert appt_of(db, a2).deposit_status == "FORFEITED"
    assert appt_of(db, a2).deposit_refund_due_at is None
    deliver_due_notifications(db)
    assert texts(fake_sender, "randevunuz iptal edildi") and not texts(fake_sender, "Kaporanız 48")


def test_no_show_with_paid_deposit_is_forfeited(client, salon, db, team):
    aid = paid_appointment(client, db, salon, team)
    data_of(staff_status(team["owner"], db, aid, "NO_SHOW"))
    assert appt_of(db, aid).deposit_status == "FORFEITED"


def test_completed_keeps_paid(client, salon, db, team):
    aid = paid_appointment(client, db, salon, team)
    data_of(staff_status(team["owner"], db, aid, "COMPLETED"))
    assert appt_of(db, aid).deposit_status == "PAID"


def test_mark_refunded(client, salon, fake_sender, db, team):
    aid = paid_appointment(client, db, salon, team)
    data_of(customer_cancel(client, db, aid))
    deliver_due_notifications(db)
    fake_sender.sent.clear()

    lists = data_of(team["manager"].get("/api/admin/deposits"))
    assert [r["id"] for r in lists["refunds"]] == [aid] and lists["awaiting"] == []
    assert lists["refunds"][0]["overdue"] is False and lists["refunds"][0]["amount"] == 100
    assert team["staff_b"].get("/api/admin/deposits").status_code == 403
    assert team["staff_b"].post(f"/api/admin/appointments/{aid}/deposit/refunded", json={}).status_code == 403

    data_of(team["manager"].post(f"/api/admin/appointments/{aid}/deposit/refunded", json={}))
    a = appt_of(db, aid)
    assert a.deposit_status == "REFUNDED" and a.deposit_refunded_at and a.deposit_refunded_by_staff_id
    deliver_due_notifications(db)
    assert texts(fake_sender, "iade edilmiştir")
    assert team["manager"].post(f"/api/admin/appointments/{aid}/deposit/refunded", json={}).status_code == 409
    assert data_of(team["manager"].get("/api/admin/deposits"))["refunds"] == []


def test_mark_refunded_without_message(client, salon, fake_sender, db, team):
    aid = paid_appointment(client, db, salon, team)
    data_of(customer_cancel(client, db, aid))
    deliver_due_notifications(db)
    fake_sender.sent.clear()
    data_of(team["manager"].post(f"/api/admin/appointments/{aid}/deposit/refunded", json={"notifyCustomer": False}))
    deliver_due_notifications(db)
    assert not texts(fake_sender, "iade edilmiştir")


# ------------------------------------------------------------------ iade hatirlatmalari


def test_refund_reminders_24h_deadline_then_daily(client, salon, db, team, spy):  # noqa: F811
    aid = paid_appointment(client, db, salon, team)
    data_of(customer_cancel(client, db, aid))
    due = appt_of(db, aid).deposit_refund_due_at
    cancelled_at = due - timedelta(hours=48)
    spy.calls.clear()

    def tick(at):
        db.expire_all()
        return deposit_watch.check_once(db, at)["refunds"]

    assert tick(cancelled_at + timedelta(hours=23)) == 0
    assert spy.calls == []
    assert tick(cancelled_at + timedelta(hours=24, minutes=1)) == 1  # 24. saat
    body = spy.calls[0]["payload"]["body"]
    assert body.startswith("Kapora iadesi bekliyor: Ayşe Yılmaz · 100 TL · iade süresi ")
    assert body.endswith("24 saat kaldı")
    assert spy.calls[0]["payload"]["title"] == "Kapora iadesi bekliyor"
    assert len(spy.calls) == 2  # owner + manager
    assert tick(cancelled_at + timedelta(hours=30)) == 0
    assert tick(due - timedelta(minutes=1)) == 0
    assert tick(due + timedelta(minutes=1)) == 1  # 48 saat doldu
    assert "süre doldu" in spy.calls[-1]["payload"]["body"]
    assert tick(due + timedelta(hours=10)) == 0
    assert tick(due + timedelta(hours=24, minutes=2)) == 1  # sonra gunluk
    assert tick(due + timedelta(hours=30)) == 0
    assert tick(due + timedelta(hours=48, minutes=3)) == 1

    data_of(team["manager"].post(f"/api/admin/appointments/{aid}/deposit/refunded", json={}))
    assert tick(due + timedelta(hours=100)) == 0  # iade edilince durur


# ------------------------------------------------------------------ 24 saat hatirlatmasi


def test_pre_reminder_skipped_while_pending_sent_when_confirmed(client, salon, fake_sender, db, team):
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    row = db.scalar(select(ScheduledNotification).where(ScheduledNotification.dedupe_key == f"pre:{aid}:24"))
    assert row is not None and row.status == "PENDING"
    fake_sender.sent.clear()
    # Vadesi gelmis gibi: randevu hala PENDING -> gitmez, iptal edilir.
    deliver_due_notifications(db, now=row.due_at + timedelta(minutes=1))
    db.expire_all()
    assert db.get(ScheduledNotification, row.id).status == "CANCELLED"
    assert not texts(fake_sender, "yarın saat")

    # Ayni randevu odendikten sonra (vade gelmeden) hatirlatma normal gider.
    login(client, BOOKER)
    a2 = data_of(book(client, salon, start=720))["appointment"]["id"]
    data_of(team["manager"].post(f"/api/admin/appointments/{a2}/deposit/paid", json={}))
    row2 = db.scalar(select(ScheduledNotification).where(ScheduledNotification.dedupe_key == f"pre:{a2}:24"))
    assert row2.status == "PENDING"
    deliver_due_notifications(db, now=row2.due_at + timedelta(minutes=1))
    assert texts(fake_sender, "yarın saat")


# ------------------------------------------------------------------ geri alma


def test_revert_cancelled_refund_due_back_to_paid(client, salon, db, team):
    aid = paid_appointment(client, db, salon, team)
    data_of(customer_cancel(client, db, aid))
    out = data_of(
        team["manager"].post(f"/api/admin/appointments/{aid}/revert", json={"expectedVersion": version_of(db, aid)})
    )
    assert out["status"] == "CONFIRMED" and out["depositStatus"] == "PAID"
    a = appt_of(db, aid)
    assert a.deposit_status == "PAID" and a.deposit_refund_due_at is None


def test_revert_no_show_forfeited_back_to_paid(client, salon, db, team):
    aid = paid_appointment(client, db, salon, team)
    data_of(staff_status(team["owner"], db, aid, "NO_SHOW"))
    data_of(team["manager"].post(f"/api/admin/appointments/{aid}/revert", json={"expectedVersion": version_of(db, aid)}))
    assert appt_of(db, aid).deposit_status == "PAID"


def test_revert_already_refunded_keeps_and_warns(client, salon, db, team):
    aid = paid_appointment(client, db, salon, team)
    data_of(customer_cancel(client, db, aid))
    data_of(team["manager"].post(f"/api/admin/appointments/{aid}/deposit/refunded", json={}))
    out = data_of(
        team["manager"].post(f"/api/admin/appointments/{aid}/revert", json={"expectedVersion": version_of(db, aid)})
    )
    assert out["status"] == "CONFIRMED" and out["depositStatus"] == "REFUNDED"
    assert "iade edilmişti" in out["undone"]["depositWarning"]
    assert appt_of(db, aid).deposit_status == "REFUNDED"


def test_revert_cancelled_awaiting_restores_pending(client, salon, db, team):
    aid = book_deposit(client, db, salon)["appointment"]["id"]
    data_of(staff_status(team["owner"], db, aid, "CANCELLED", reason="DEPOSIT_UNPAID"))
    out = data_of(
        team["manager"].post(f"/api/admin/appointments/{aid}/revert", json={"expectedVersion": version_of(db, aid)})
    )
    assert out["status"] == "PENDING" and out["depositStatus"] == "AWAITING"
    a = appt_of(db, aid)
    assert (a.status, a.deposit_status) == ("PENDING", "AWAITING")
    assert [r["id"] for r in data_of(team["manager"].get("/api/admin/deposits"))["awaiting"]] == [aid]


# ------------------------------------------------------------------ panelden olusturma


def _manual(salon, **kw):
    from tests.test_manual_booking import _body

    return _body(salon, **kw)


def test_manual_create_with_and_without_deposit(salon, fake_sender, db, team):
    owner = team["owner"]
    # Kapora kapaliyken 'Kapora iste' reddedilir.
    r = owner.post("/api/admin/appointments", json={**_manual(salon), "requestDeposit": True})
    assert r.status_code == 400
    enable(db, salon)

    plain = data_of(owner.post("/api/admin/appointments", json=_manual(salon)))["appointment"]
    assert plain["status"] == "CONFIRMED" and plain["depositStatus"] == "NONE"

    out = data_of(
        owner.post("/api/admin/appointments", json={**_manual(salon, startMin=720), "requestDeposit": True})
    )
    appt = out["appointment"]
    assert appt["status"] == "PENDING" and appt["depositStatus"] == "AWAITING" and appt["depositAmount"] == 100
    assert out["whatsappQueued"] is True
    deliver_due_notifications(db)
    assert texts(fake_sender, "kapora gerekmektedir")
    assert len(texts(fake_sender, "oluşturuldu ✅")) == 1  # yalnizca kaporasiz olan icin
    keys = [r.dedupe_key for r in db.scalars(select(ScheduledNotification))]
    assert f"confirm:{plain['id']}" in keys and f"confirm:{appt['id']}" not in keys

    listed = data_of(owner.get("/api/admin/deposits"))["awaiting"]
    assert [x["id"] for x in listed] == [appt["id"]] and listed[0]["reference"] == f"R{appt['id']} Ayşe Y."


def test_manual_edit_recomputes_deposit_and_resend(salon, fake_sender, db, team):
    owner = team["owner"]
    enable(db, salon)
    appt = data_of(
        owner.post("/api/admin/appointments", json={**_manual(salon), "requestDeposit": True})
    )["appointment"]
    deliver_due_notifications(db)
    fake_sender.sent.clear()

    out = data_of(
        owner.patch(
            f"/api/admin/appointments/{appt['id']}",
            json={"expectedVersion": appt["version"], "priceOverride": 2000},
        )
    )
    assert out["depositRecomputed"] is True and out["depositAmount"] == 400
    deliver_due_notifications(db)
    assert fake_sender.sent == []  # mesaj otomatik tekrar gonderilmez

    assert team["staff_b"].post(f"/api/admin/appointments/{appt['id']}/deposit/resend").status_code == 403
    data_of(team["manager"].post(f"/api/admin/appointments/{appt['id']}/deposit/resend"))
    deliver_due_notifications(db)
    [text] = texts(fake_sender, "kapora gerekmektedir")
    assert "400 TL kapora" in text
