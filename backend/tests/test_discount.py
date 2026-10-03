"""Firsat saati: hafta ici + erken saat + SABIT oran (tek kural, her yerde ayni)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.opportunity import FixedWindowSettings, fixed_window_discount
from app.main import app
from app.models import Appointment, Salon
from app.services import messaging
from app.time_utils import now_local
from tests.test_book_for_other import BOOKER, confirm_body, data_of, error_of, login
from tests.test_group_booking import C_BEN, confirm_group, lock_group
from tests.test_messaging import FakeSender


def _next_weekday(py_weekday: int) -> str:
    """Bugunden en az 7 gun sonraki, verilen gune (Pzt=0..Paz=6) denk gelen tarih."""
    d = now_local().date() + timedelta(days=7)
    while d.weekday() != py_weekday:
        d += timedelta(days=1)
    return d.isoformat()


MONDAY = _next_weekday(0)
FRIDAY = _next_weekday(4)
SATURDAY = _next_weekday(5)
SUNDAY = _next_weekday(6)


@pytest.fixture()
def fake_sender(monkeypatch):
    sender = FakeSender()
    monkeypatch.setattr(messaging, "_sender", sender)
    return sender


@pytest.fixture()
def client(salon, fake_sender):
    with TestClient(app) as c:
        yield c


def _set(db, salon, **kw):
    row = db.get(Salon, salon["salon"].id)
    for k, v in kw.items():
        setattr(row, k, v)
    db.commit()


# ------------------------------------------------------------------ kural


def test_rule_weekday_morning_gets_fixed_rate():
    assert fixed_window_discount(MONDAY, 600) == 0.10
    assert fixed_window_discount(FRIDAY, 540) == 0.10
    assert fixed_window_discount(MONDAY, 719) == 0.10


def test_rule_weekend_never_discounted():
    assert fixed_window_discount(SATURDAY, 600) == 0.0
    assert fixed_window_discount(SUNDAY, 540) == 0.0


def test_rule_cutoff_boundary_and_after_has_no_discount():
    assert fixed_window_discount(MONDAY, 720) == 0.0  # tam sinir: indirim yok
    assert fixed_window_discount(MONDAY, 721) == 0.0
    assert fixed_window_discount(MONDAY, 1000) == 0.0


def test_rule_disabled_returns_zero():
    s = FixedWindowSettings(enabled=False)
    assert fixed_window_discount(MONDAY, 600, s) == 0.0


def test_rule_custom_days_rate_and_cutoff():
    s = FixedWindowSettings(rate=0.2, cutoff_min=780, days=(6, 0))  # Cumartesi + Pazar
    assert fixed_window_discount(SATURDAY, 770, s) == 0.2
    assert fixed_window_discount(SUNDAY, 600, s) == 0.2
    assert fixed_window_discount(SATURDAY, 780, s) == 0.0
    assert fixed_window_discount(MONDAY, 600, s) == 0.0


def test_rule_bad_date_is_safe():
    assert fixed_window_discount("gecersiz", 600) == 0.0


# ------------------------------------------------------------ slot listesi


def _slots(client, salon, day):
    r = data_of(
        client.post(
            "/api/availability", json={"date": day, "serviceIds": [salon["manikur"].id]}
        )
    )
    return [s for st in r["staff"] for s in st["slots"]]


def test_availability_marks_only_weekday_morning(client, salon):
    mon = _slots(client, salon, MONDAY)
    assert mon
    for s in mon:
        if s["startMin"] < 720:
            assert s["discountRate"] == 0.10 and s["isOpportunity"] is True, s
        else:
            assert s["discountRate"] == 0 and s["isOpportunity"] is False, s
    assert any(s["startMin"] < 720 for s in mon) and any(s["startMin"] >= 720 for s in mon)

    sat = _slots(client, salon, SATURDAY)
    assert sat and all(s["discountRate"] == 0 and not s["isOpportunity"] for s in sat)


def test_availability_follows_settings(client, salon, db):
    _set(db, salon, discount_enabled=False)
    assert all(s["discountRate"] == 0 for s in _slots(client, salon, MONDAY))
    _set(db, salon, discount_enabled=True, discount_rate=0.2, discount_cutoff_min=600)
    mon = _slots(client, salon, MONDAY)
    assert {s["discountRate"] for s in mon if s["startMin"] < 600} == {0.2}
    assert {s["discountRate"] for s in mon if s["startMin"] >= 600} == {0}


# ------------------------------------------------------------- randevu


def _book(client, salon, day, start, staff="staff_a", **extra):
    body = {
        "date": day,
        "serviceIds": [salon["manikur"].id],
        "staffId": salon[staff].id,
        "startMin": start,
    }
    lock = data_of(client.post("/api/slots/lock", json=body))
    return lock, client.post("/api/appointments", json=confirm_body(lock, body, **extra))


def test_booking_stores_discounted_price(client, salon, db):
    login(client, BOOKER)
    lock, res = _book(client, salon, MONDAY, 600)
    assert lock["totalPrice"] == 350  # kilit: indirimsiz tutar
    assert lock["discountRate"] == 0.10 and lock["discountedPrice"] == 315
    appt = data_of(res)["appointment"]
    assert appt["totalPrice"] == 315 and appt["discountRate"] == 0.10 and appt["isOpportunity"]
    row = db.scalars(select(Appointment)).one()
    assert row.total_price == 315 and row.discount_rate == 0.10 and row.is_opportunity is True


def test_booking_afternoon_and_weekend_full_price(client, salon, db):
    login(client, BOOKER)
    for day, start in ((MONDAY, 720), (MONDAY, 840), (SATURDAY, 600)):
        lock, res = _book(client, salon, day, start)
        assert lock["discountRate"] == 0 and lock["discountedPrice"] == 350
        appt = data_of(res)["appointment"]
        assert appt["totalPrice"] == 350 and appt["discountRate"] == 0 and not appt["isOpportunity"]


def test_client_sent_discount_is_ignored(client, salon, db):
    login(client, BOOKER)
    _, res = _book(client, salon, SATURDAY, 600, discountRate=0.9, totalPrice=1, isOpportunity=True)
    appt = data_of(res)["appointment"]
    assert appt["totalPrice"] == 350 and appt["discountRate"] == 0
    row = db.scalars(select(Appointment)).one()
    assert row.total_price == 350 and row.discount_rate == 0


def test_settings_changed_between_lock_and_confirm_uses_confirm_time(client, salon, db):
    login(client, BOOKER)
    body = {
        "date": MONDAY,
        "serviceIds": [salon["manikur"].id],
        "staffId": salon["staff_a"].id,
        "startMin": 600,
    }
    lock = data_of(client.post("/api/slots/lock", json=body))
    assert lock["discountRate"] == 0.10
    _set(db, salon, discount_enabled=False)
    appt = data_of(client.post("/api/appointments", json=confirm_body(lock, body)))["appointment"]
    assert appt["totalPrice"] == 350 and appt["discountRate"] == 0


def test_shadow_fill_booking_uses_same_rule(client, salon, db):
    """Golge slot da ayni kurala tabidir (ayri fiyat yolu yok)."""
    login(client, BOOKER)
    # Sabah (indirimli) bir randevu sonrasi ayni usta, ayni gun ogleden sonra
    _, res = _book(client, salon, MONDAY, 600)
    parent = data_of(res)["appointment"]["id"]
    _, res2 = _book(client, salon, MONDAY, 840, shadowParentId=parent)
    assert data_of(res2)["appointment"]["totalPrice"] == 350


def test_loyalty_points_use_paid_price(client, salon, db):
    from app.models import LoyaltyEntry
    from app.services.appointment_status import change_appointment_status

    login(client, BOOKER)
    _, res = _book(client, salon, MONDAY, 600)
    appt = data_of(res)["appointment"]
    change_appointment_status(db, appointment_id=appt["id"], status="COMPLETED", expected_version=appt["version"])
    db.expire_all()
    entry = db.scalars(select(LoyaltyEntry).where(LoyaltyEntry.appointment_id == appt["id"])).one()
    assert entry.delta > 0
    assert entry.delta <= 315 * 1.5 * 1.25 + 1  # 350 uzerinden degil, odenen tutardan


# --------------------------------------------------------------- grup


def test_group_booking_applies_same_rule(client, salon, db):
    import tests.test_group_booking as g

    login(client, BOOKER)
    asg = [(salon["staff_a"], "self"), (salon["staff_b"], C_BEN)]

    def run(day, start):
        old = g.DAY
        g.DAY = day
        try:
            grp = data_of(lock_group(client, salon, asg, start=start))
            return grp, data_of(confirm_group(client, grp, asg))
        finally:
            g.DAY = old

    grp, res = run(MONDAY, 600)
    assert all(l["discountRate"] == 0.10 and l["discountedPrice"] == 315 for l in grp["locks"])
    assert res["totalPrice"] == 630
    assert all(a["totalPrice"] == 315 and a["discountRate"] == 0.10 for a in res["appointments"])

    grp, res = run(SATURDAY, 600)
    assert all(l["discountRate"] == 0 for l in grp["locks"])
    assert res["totalPrice"] == 700
    rows = db.scalars(select(Appointment).where(Appointment.date == SATURDAY)).all()
    assert rows and all(r.discount_rate == 0 and not r.is_opportunity for r in rows)


# ------------------------------------------------------------- admin ayar


def _staff_login(client, phone, password):
    assert client.post(
        "/api/auth/staff/login", json={"phone": phone, "password": password}
    ).status_code == 200


VALID = {"enabled": True, "rate": 0.15, "cutoffMin": 660, "days": [1, 2, 3]}


def test_admin_discount_get_put_roundtrip(client, salon, db):
    _staff_login(client, "5551110001", "admin123")  # OWNER
    cur = data_of(client.get("/api/admin/settings/discount"))
    assert cur["enabled"] is True and cur["rate"] == 0.10
    assert cur["cutoffMin"] == 720 and cur["days"] == [1, 2, 3, 4, 5]
    assert "Hafta içi 12:00" in cur["summary"] and "%10" in cur["summary"]

    saved = data_of(client.put("/api/admin/settings/discount", json=VALID))
    assert saved["rate"] == 0.15 and saved["cutoffMin"] == 660 and saved["days"] == [1, 2, 3]
    db.expire_all()
    row = db.get(Salon, salon["salon"].id)
    assert (row.discount_rate, row.discount_cutoff_min, row.discount_days) == (0.15, 660, "1,2,3")

    # yeni ayar fiyata yansir
    login_client = client
    slots = _slots(login_client, salon, MONDAY)
    assert {s["discountRate"] for s in slots if s["startMin"] < 660} == {0.15}
    assert {s["discountRate"] for s in slots if 660 <= s["startMin"]} == {0}
    assert all(s["discountRate"] == 0 for s in _slots(client, salon, FRIDAY))


def test_admin_discount_requires_manager(client, salon):
    assert client.get("/api/admin/settings/discount").status_code in (401, 403)
    _staff_login(client, "5551110002", "merve123")  # STAFF
    assert client.get("/api/admin/settings/discount").status_code == 403
    assert client.put("/api/admin/settings/discount", json=VALID).status_code == 403


@pytest.mark.parametrize(
    "patch",
    [
        {"rate": 0.02},
        {"rate": 0.35},
        {"rate": 0.12},
        {"cutoffMin": 725},
        {"cutoffMin": 0},
        {"days": [7]},
        {"days": [-1]},
        {"enabled": "belki"},
    ],
)
def test_admin_discount_validation(client, salon, patch):
    _staff_login(client, "5551110001", "admin123")
    res = client.put("/api/admin/settings/discount", json={**VALID, **patch})
    assert res.status_code == 400 or res.status_code == 422, res.text
    assert res.json()["ok"] is False
