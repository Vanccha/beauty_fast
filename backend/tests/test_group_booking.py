"""Grup randevusu: ortak saat, atomik kilit/onay, gorunurluk, iptal ve gizlilik."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth.password import hash_password
from app.core.opportunity import fixed_window_discount
from app.main import app
from app.models import Appointment, SlotLock, Staff, StaffService, TimeOff, WorkingHour
from app.services import messaging
from app.time_utils import add_days_to_key, now_local, to_date_key
from tests.test_book_for_other import BEN, BOOKER, NEWPHONE, OTHER, data_of, error_of, login, new_client
from tests.test_messaging import FakeSender

DAY = add_days_to_key(to_date_key(now_local()), 3)
PHONE_C = "5327776655"
C_BEN = {"firstName": "Cem", "phone": PHONE_C}


@pytest.fixture()
def fake_sender(monkeypatch):
    sender = FakeSender()
    monkeypatch.setattr(messaging, "_sender", sender)
    return sender


@pytest.fixture()
def client(salon, fake_sender):
    with TestClient(app) as c:
        yield c


def add_staff(db, salon, name="Selin", phone="5551110003"):
    staff = Staff(
        branch_id=salon["branch"].id, name=name, phone=phone,
        password_hash=hash_password("x12345"), role="STAFF", display_order=2,
    )
    db.add(staff)
    db.flush()
    for weekday in range(7):
        db.add(WorkingHour(staff_id=staff.id, weekday=weekday, start_min=540, end_min=1200, is_working=True))
    for key in ("boya", "kas", "manikur"):
        db.add(StaffService(staff_id=staff.id, service_id=salon[key].id, speed_factor=1.0))
    db.commit()
    return staff


def avail(client, people, date=DAY):
    return client.post("/api/availability/group", json={"date": date, "people": people})


def person_q(salon, staff=None, service="manikur"):
    return {"serviceIds": [salon[service].id], "staffId": staff.id if staff else None}


def lock_people(salon, assignments, service="manikur"):
    """assignments: [(staff, 'self' | beneficiary dict)]"""
    out = []
    for staff, who in assignments:
        p = {"serviceIds": [salon[service].id], "staffId": staff.id}
        if who == "self":
            p["self"] = True
        else:
            p["beneficiary"] = who
        out.append(p)
    return out


def lock_group(client, salon, assignments, start=600):
    return client.post(
        "/api/slots/lock-group",
        json={"date": DAY, "startMin": start, "people": lock_people(salon, assignments)},
    )


def confirm_group(client, group, assignments, notes=None, **flags):
    people = []
    for lock, (_staff, who) in zip(group["locks"], assignments):
        p = {"lockId": lock["lockId"]}
        if who == "self":
            p["self"] = True
        else:
            p["beneficiary"] = who
        if notes:
            p["notes"] = notes
        people.append(p)
    return client.post("/api/appointments/group", json={"groupId": group["groupId"], "people": people, "privacyNoticeAck": True, "healthDeclaration": True, **flags},)


# ----------------------------------------------------------------- availability


def test_common_slot_with_distinct_staff(client, salon):
    data = data_of(avail(client, [person_q(salon), person_q(salon)]))
    assert data["options"] and data["suggestDates"] == []
    starts = [o["startMin"] for o in data["options"]]
    assert starts == sorted(starts) and len(starts) <= 40
    for opt in data["options"]:
        ids = [a["staffId"] for a in opt["assignments"]]
        assert len(ids) == 2 and len(set(ids)) == 2
        assert [a["personIndex"] for a in opt["assignments"]] == [0, 1]
        for a in opt["assignments"]:
            assert a["startMin"] == opt["startMin"] and a["endMin"] - a["startMin"] == a["totalMin"]
            assert a["staffName"] and a["totalPrice"] == 350


def test_staff_preference_is_respected(client, salon):
    data = data_of(avail(client, [person_q(salon, salon["staff_b"]), person_q(salon)]))
    assert data["options"]
    for opt in data["options"]:
        by_person = {a["personIndex"]: a["staffId"] for a in opt["assignments"]}
        assert by_person[0] == salon["staff_b"].id
        assert by_person[1] == salon["staff_a"].id


def test_three_people_need_three_staff(client, salon, db):
    two = data_of(avail(client, [person_q(salon)] * 3))
    assert two["options"] == []  # yalnizca 2 usta var
    add_staff(db, salon)
    three = data_of(avail(client, [person_q(salon)] * 3))
    assert three["options"]
    assert all(len({a["staffId"] for a in o["assignments"]}) == 3 for o in three["options"])


def test_same_preferred_staff_twice_has_no_option(client, salon):
    data = data_of(avail(client, [person_q(salon, salon["staff_a"])] * 2))
    assert data["options"] == []


def test_shared_exclusive_resource_is_not_double_booked(client, salon):
    # Iki kisi de "Sac Boyasi" (tek koltuk) istiyor: ayni anda mumkun degil.
    data = data_of(avail(client, [person_q(salon, service="boya")] * 2))
    assert data["options"] == []


def test_none_returns_suggest_dates(client, salon, db):
    # Merve o gun izinli -> tek usta kaldi -> o gun ortak saat yok, ertesi gun var.
    db.add(TimeOff(staff_id=salon["staff_b"].id, date=DAY, start_min=None, end_min=None))
    db.commit()
    data = data_of(avail(client, [person_q(salon)] * 2))
    assert data["options"] == []
    dates = {d["date"]: d["optionCount"] for d in data["suggestDates"]}
    assert dates and DAY not in dates
    assert add_days_to_key(DAY, 1) in dates and all(c > 0 for c in dates.values())
    assert all(DAY < d <= add_days_to_key(DAY, 7) for d in dates)


def test_availability_rejects_more_than_four(client, salon):
    r = avail(client, [person_q(salon)] * 5)
    assert r.status_code == 400 and error_of(r)["code"] == "VALIDATION"


# ------------------------------------------------------------------- lock-group


def test_group_endpoints_require_session(client, salon):
    r = lock_group(client, salon, [(salon["staff_a"], BEN), (salon["staff_b"], C_BEN)])
    assert r.status_code == 401 and error_of(r)["code"] == "MEMBERSHIP_REQUIRED"
    r = client.post(
        "/api/appointments/group", json={"groupId": "x", "people": [{"lockId": 1, "self": True}]}
    )
    assert r.status_code == 401


def test_lock_group_success_and_release(client, salon, db):
    login(client, BOOKER)
    asg = [(salon["staff_a"], "self"), (salon["staff_b"], BEN)]
    g = data_of(lock_group(client, salon, asg))
    assert g["ttlSeconds"] == 600 and len(g["groupId"]) == 32
    assert [lk["personIndex"] for lk in g["locks"]] == [0, 1]
    assert g["locks"][0]["staffId"] == salon["staff_a"].id and g["locks"][0]["totalPrice"] == 350
    assert db.scalar(select(func.count()).select_from(SlotLock).where(SlotLock.group_id == g["groupId"])) == 2

    # baska oturum birakamaz; sahibi birakir
    stranger = new_client()
    assert stranger.delete(f"/api/slots/lock-group/{g['groupId']}").status_code == 403
    avail(stranger, [person_q(salon)])  # ziyaretci cerezi alir
    assert data_of(stranger.delete(f"/api/slots/lock-group/{g['groupId']}"))["released"] == 0
    assert data_of(client.delete(f"/api/slots/lock-group/{g['groupId']}"))["released"] == 2
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(SlotLock)) == 0


def test_lock_group_is_atomic_on_conflict(client, salon, db):
    # Baska bir ziyaretci Merve'nin 10:00'ini tutuyor.
    other = new_client()
    body = {"date": DAY, "serviceIds": [salon["manikur"].id], "staffId": salon["staff_b"].id, "startMin": 600}
    data_of(other.post("/api/slots/lock", json=body))
    assert db.scalar(select(func.count()).select_from(SlotLock)) == 1

    login(client, BOOKER)
    r = lock_group(client, salon, [(salon["staff_a"], "self"), (salon["staff_b"], BEN)])
    assert r.status_code == 409 and error_of(r)["code"] == "SLOT_TAKEN"
    db.expire_all()
    # Hicbir grup kilidi kalmadi (Elif icin alinan da geri alindi)
    assert db.scalar(select(func.count()).select_from(SlotLock)) == 1
    assert db.scalar(select(func.count()).select_from(SlotLock).where(SlotLock.group_id.is_not(None))) == 0


def test_lock_group_validation(client, salon):
    login(client, BOOKER)
    a, b = salon["staff_a"], salon["staff_b"]
    # ayni telefon iki kez
    r = lock_group(client, salon, [(a, BEN), (b, {"firstName": "Baska", "phone": NEWPHONE})])
    assert r.status_code == 400 and error_of(r)["code"] == "VALIDATION"
    # alanin kendi numarasi + self
    r = lock_group(client, salon, [(a, "self"), (b, {"firstName": "Ben", "phone": BOOKER})])
    assert r.status_code == 400
    # iki self
    assert lock_group(client, salon, [(a, "self"), (b, "self")]).status_code == 400
    # ne self ne beneficiary
    bad = {"date": DAY, "startMin": 600, "people": [{"serviceIds": [salon["manikur"].id], "staffId": a.id}]}
    assert client.post("/api/slots/lock-group", json=bad).status_code == 400
    # 5 kisi
    five = {
        "date": DAY, "startMin": 600,
        "people": [{"serviceIds": [salon["manikur"].id], "staffId": a.id, "self": True}] * 5,
    }
    assert client.post("/api/slots/lock-group", json=five).status_code == 400


def test_new_lock_group_replaces_previous_group(client, salon, db):
    login(client, BOOKER)
    asg = [(salon["staff_a"], BEN), (salon["staff_b"], C_BEN)]
    g1 = data_of(lock_group(client, salon, asg))
    g2 = data_of(lock_group(client, salon, asg))  # ayni saat: eski grup serbest birakilir
    assert g1["groupId"] != g2["groupId"]
    db.expire_all()
    assert set(db.scalars(select(SlotLock.group_id))) == {g2["groupId"]}


# ---------------------------------------------------------------------- confirm


def test_confirm_group_books_all(client, salon, fake_sender, db):
    login(client, BOOKER)
    asg = [(salon["staff_a"], "self"), (salon["staff_b"], BEN)]
    g = data_of(lock_group(client, salon, asg))
    res = data_of(confirm_group(client, g, asg, notes="selam"))
    assert res["groupId"] == g["groupId"] and res["totalPrice"] == 700 * (1 - fixed_window_discount(DAY, 600))
    assert [a["personIndex"] for a in res["appointments"]] == [0, 1]
    assert res["appointments"][0]["forCustomer"]["firstName"] == "Ayşe"
    assert res["appointments"][1]["forCustomer"]["firstName"] == "Deniz"
    assert res["appointments"][1]["staffName"] == "Merve"

    rows = db.scalars(select(Appointment).order_by(Appointment.id)).all()
    assert len(rows) == 2 and {r.booking_group_id for r in rows} == {g["groupId"]}
    me, ben = rows
    assert me.customer_id == salon["customer"].id and me.beneficiary_label is None
    assert ben.customer_id != me.customer_id and ben.booked_by_customer_id == salon["customer"].id
    assert ben.beneficiary_label == "Deniz"
    # kilitler tuketildi
    assert db.scalar(select(func.count()).select_from(SlotLock).where(SlotLock.consumed_at.is_(None))) == 0
    # yalnizca aliciya mesaj; yazilan ad kullanildi
    texts = [t for p, t in fake_sender.sent if p == NEWPHONE]
    assert len(texts) == 1 and "Deniz" in texts[0] and "Ayşe" in texts[0]
    assert not [1 for p, t in fake_sender.sent if p == BOOKER and "randevusu oluşturdu" in t]


def test_confirm_group_is_atomic(client, salon, db):
    login(client, BOOKER)
    asg = [(salon["staff_a"], BEN), (salon["staff_b"], C_BEN)]
    g = data_of(lock_group(client, salon, asg))
    # ikinci kilidin suresi doluyor -> onay tamamen basarisiz olmali
    lock2 = db.get(SlotLock, g["locks"][1]["lockId"])
    lock2.expires_at = now_local().replace(year=2020)
    db.commit()
    r = confirm_group(client, g, asg)
    assert r.status_code == 409
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Appointment)) == 0
    assert db.get(SlotLock, g["locks"][0]["lockId"]).consumed_at is None


def test_confirm_group_rejects_incomplete_or_foreign_locks(client, salon):
    login(client, BOOKER)
    asg = [(salon["staff_a"], BEN), (salon["staff_b"], C_BEN)]
    g = data_of(lock_group(client, salon, asg))
    partial = client.post(
        "/api/appointments/group",
        json={"groupId": g["groupId"], "people": [{"lockId": g["locks"][0]["lockId"], "beneficiary": BEN}],
              "privacyNoticeAck": True, "healthDeclaration": True},
    )
    assert partial.status_code == 409
    wrong = client.post(
        "/api/appointments/group",
        json={"groupId": "nope", "people": [{"lockId": g["locks"][0]["lockId"], "beneficiary": BEN}],
              "privacyNoticeAck": True, "healthDeclaration": True},
    )
    assert wrong.status_code == 409


def test_confirm_group_message_failure_is_tolerated(client, salon, fake_sender):
    login(client, BOOKER)
    fake_sender.fail = True
    asg = [(salon["staff_a"], BEN), (salon["staff_b"], C_BEN)]
    g = data_of(lock_group(client, salon, asg))
    assert confirm_group(client, g, asg).status_code == 200


# ---------------------------------------------------- visibility / privacy / cancel


def test_booker_sees_all_recipient_sees_own_and_labels_are_typed(client, salon):
    login(client, BOOKER)
    # OTHER (Zeynep) kayitli; booker onun icin "Takma" yazdi: gercek ad sizmamali.
    typed = {"firstName": "Takma", "phone": OTHER}
    asg = [(salon["staff_a"], "self"), (salon["staff_b"], typed)]
    g = data_of(lock_group(client, salon, asg))
    res = data_of(confirm_group(client, g, asg))
    appt_other = res["appointments"][1]
    assert appt_other["forCustomer"]["firstName"] == "Takma"  # kayitli "Zeynep" degil

    mine = data_of(client.get("/api/appointments/mine"))["upcoming"]
    assert len(mine) == 2 and {a["groupId"] for a in mine} == {g["groupId"]}
    by = {a["forCustomer"]["firstName"]: a for a in mine}
    assert set(by) == {"Ayşe", "Takma"}
    assert by["Takma"]["bookedByMe"] and not by["Takma"]["isMine"]
    assert "Zeynep" not in str(mine)
    detail = data_of(client.get(f"/api/appointments/{appt_other['appointmentId']}"))
    assert detail["forCustomer"]["firstName"] == "Takma" and "Zeynep" not in str(detail)

    # alici kendi kaydini kendi adiyla gorur, digerini gormez
    rec = new_client()
    login(rec, OTHER)
    rmine = data_of(rec.get("/api/appointments/mine"))["upcoming"]
    assert [a["id"] for a in rmine] == [appt_other["appointmentId"]]
    assert rmine[0]["forCustomer"]["firstName"] == "Zeynep" and rmine[0]["isMine"]
    assert rec.get(f"/api/appointments/{res['appointments'][0]['appointmentId']}").status_code == 403


def test_single_booking_label_does_not_leak_stored_name(client, salon):
    login(client, BOOKER)
    typed = {"firstName": "Takma", "phone": OTHER}
    body = {
        "date": DAY, "serviceIds": [salon["manikur"].id], "staffId": salon["staff_a"].id,
        "startMin": 600, "beneficiary": typed,
    }
    lock = data_of(client.post("/api/slots/lock", json=body))
    r = data_of(
        client.post(
            "/api/appointments",
            json={
                "lockId": lock["lockId"], "date": DAY, "staffId": body["staffId"], "startMin": 600,
                "serviceIds": body["serviceIds"], "beneficiary": typed,
                "privacyNoticeAck": True, "healthDeclaration": True,
            },
        )
    )
    assert r["forCustomer"]["firstName"] == "Takma"
    mine = data_of(client.get("/api/appointments/mine"))["upcoming"]
    assert mine[0]["forCustomer"]["firstName"] == "Takma" and "Zeynep" not in str(mine)


def test_group_cancel(client, salon, db):
    login(client, BOOKER)
    asg = [(salon["staff_a"], "self"), (salon["staff_b"], BEN)]
    g = data_of(lock_group(client, salon, asg))
    data_of(confirm_group(client, g, asg))

    rec = new_client()
    login(rec, NEWPHONE)
    assert rec.post(f"/api/appointments/group/{g['groupId']}/cancel").status_code == 404

    assert data_of(client.post(f"/api/appointments/group/{g['groupId']}/cancel"))["cancelled"] == 2
    db.expire_all()
    assert {a.status for a in db.scalars(select(Appointment))} == {"CANCELLED"}
    # slotlar yeniden bos
    again = data_of(avail(client, [person_q(salon)] * 2))
    assert 600 in [o["startMin"] for o in again["options"]]
