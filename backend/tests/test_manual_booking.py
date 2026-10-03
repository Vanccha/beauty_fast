"""Panelden elle randevu: olustur / duzenle / durum / geri alma."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.risk_score import hash_phone
from app.main import app
from app.models import (
    Appointment,
    Customer,
    InventoryItem,
    LoyaltyEntry,
    OccupancyCell,
    PhoneRiskEvent,
    Salon,
    ScheduledNotification,
    ServiceConsumable,
    StockMovement,
)
from app.time_utils import now_local


def _next_weekday(py_weekday: int) -> str:
    d = now_local().date() + timedelta(days=7)
    while d.weekday() != py_weekday:
        d += timedelta(days=1)
    return d.isoformat()


MONDAY = _next_weekday(0)  # firsat indirimi: hafta ici + 12:00 oncesi
SATURDAY = _next_weekday(5)  # indirim yok


def data_of(response) -> dict:
    body = response.json()
    assert body["ok"] is True, body
    return body["data"]


def error_of(response) -> dict:
    body = response.json()
    assert body["ok"] is False, body
    return body["error"]


@pytest.fixture()
def owner(salon):
    with TestClient(app) as c:
        data_of(c.post("/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}))
        yield c


@pytest.fixture()
def staff_user(salon):
    with TestClient(app) as c:
        data_of(c.post("/api/auth/staff/login", json={"phone": "5551110002", "password": "merve123"}))
        yield c


def _body(salon, **kw):
    body = {
        "customerId": salon["customer"].id,
        "staffId": salon["staff_a"].id,
        "date": MONDAY,
        "startMin": 600,
        "serviceIds": [salon["manikur"].id],
    }
    body.update(kw)
    return body


def _create(client, salon, **kw):
    return data_of(client.post("/api/admin/appointments", json=_body(salon, **kw)))["appointment"]


def _cells(db, appointment_id):
    db.expire_all()
    return db.scalar(
        select(func.count()).select_from(OccupancyCell).where(
            OccupancyCell.appointment_id == appointment_id
        )
    )


def _notes(db, prefix):
    db.expire_all()
    return db.scalars(
        select(ScheduledNotification).where(ScheduledNotification.dedupe_key.like(f"{prefix}%"))
    ).all()


def _row(db, appointment_id) -> Appointment:
    db.expire_all()
    return db.get(Appointment, appointment_id)


def _status(client, appt, status, **kw):
    return client.patch(
        f"/api/admin/appointments/{appt['id']}/status",
        json={"status": status, "expectedVersion": appt["version"], **kw},
    )


# ---------------------------------------------------------------------
# Olusturma
# ---------------------------------------------------------------------


def test_create_for_existing_customer_writes_cells_and_confirmation(owner, salon, db):
    appt = _create(owner, salon)
    assert appt["status"] == "CONFIRMED" and appt["source"] == "ADMIN"
    assert appt["endMin"] == 640
    row = _row(db, appt["id"])
    assert row.created_by_staff_id == salon["staff_a"].id
    assert _cells(db, appt["id"]) > 0
    assert len(_notes(db, f"confirm:{appt['id']}")) == 1
    assert len(_notes(db, f"pre:{appt['id']}")) == 1


def test_create_new_customer_is_find_or_create(owner, salon, db):
    new = {"firstName": "Elena", "phone": "+44 7911 123456"}
    first = data_of(owner.post("/api/admin/appointments", json=_body(salon, customerId=None, newCustomer=new)))
    assert first["customer"]["phone"] == "+447911123456"
    second = data_of(
        owner.post(
            "/api/admin/appointments",
            json=_body(salon, customerId=None, newCustomer=new, startMin=720),
        )
    )
    assert second["customer"]["id"] == first["customer"]["id"]
    assert db.scalar(select(func.count()).select_from(Customer).where(Customer.phone == "+447911123456")) == 1


def test_create_requires_exactly_one_customer_source(owner, salon):
    r = owner.post("/api/admin/appointments", json=_body(salon, customerId=None))
    assert r.status_code == 400
    r = owner.post(
        "/api/admin/appointments",
        json=_body(salon, newCustomer={"firstName": "A", "phone": "5329998877"}),
    )
    assert r.status_code == 400


def test_conflict_returns_409_with_reason(owner, salon):
    _create(owner, salon)
    r = owner.post(
        "/api/admin/appointments",
        json=_body(salon, customerId=salon["other_customer"].id, startMin=620),
    )
    assert r.status_code == 409
    err = error_of(r)
    assert err["code"] == "SLOT_CONFLICT"
    assert "Usta bu saatte başka bir randevuda" in err["message"]
    assert err["details"]["canForce"] is True
    assert err["details"]["conflicts"][0]["kind"] == "STAFF"


def test_customer_overlap_with_other_staff_is_reported(owner, salon):
    _create(owner, salon)
    r = owner.post(
        "/api/admin/appointments", json=_body(salon, staffId=salon["staff_b"].id, startMin=610)
    )
    assert r.status_code == 409
    assert any(c["kind"] == "CUSTOMER" for c in error_of(r)["details"]["conflicts"])


def test_outside_working_hours_is_a_conflict(owner, salon):
    r = owner.post("/api/admin/appointments", json=_body(salon, startMin=1190))
    assert r.status_code == 409
    assert error_of(r)["details"]["conflicts"][0]["kind"] == "OUTSIDE_HOURS"


def test_manager_force_books_anyway(owner, salon, db):
    first = _create(owner, salon)
    forced = data_of(
        owner.post(
            "/api/admin/appointments",
            json=_body(salon, customerId=salon["other_customer"].id, startMin=620, force=True),
        )
    )
    assert forced["forced"] is True and forced["conflicts"]
    second = forced["appointment"]
    assert second["id"] != first["id"]
    # Hucre kisiti cift rezervasyonu engeller: ortak hucreler ilkinde kalir.
    assert _cells(db, second["id"]) < _cells(db, first["id"]) + 4
    assert db.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.date == MONDAY)
    ) == 2


def test_staff_cannot_force(staff_user, owner, salon):
    _create(owner, salon, staffId=salon["staff_b"].id)
    r = staff_user.post(
        "/api/admin/appointments",
        json=_body(salon, staffId=salon["staff_b"].id, customerId=salon["other_customer"].id, force=True),
    )
    assert r.status_code == 403


def test_staff_creates_only_for_self(staff_user, salon):
    r = staff_user.post("/api/admin/appointments", json=_body(salon, staffId=salon["staff_a"].id))
    assert r.status_code == 403
    ok = staff_user.post("/api/admin/appointments", json=_body(salon, staffId=salon["staff_b"].id))
    assert ok.status_code == 200


def test_discount_default_toggle_and_override(owner, salon):
    auto = _create(owner, salon, startMin=600)
    assert auto["discountRate"] == 0.10 and auto["totalPrice"] == 315.0

    off = _create(owner, salon, customerId=salon["other_customer"].id, startMin=700, applyDiscount=False)
    assert off["discountRate"] == 0 and off["totalPrice"] == 350.0

    manual = _create(owner, salon, startMin=800, priceOverride=200)
    assert manual["totalPrice"] == 200.0 and manual["discountRate"] == 0

    saturday = _create(owner, salon, date=SATURDAY)
    assert saturday["discountRate"] == 0


def test_whatsapp_queued_or_suppressed(owner, salon, db):
    on = _create(owner, salon, startMin=600)
    off = _create(owner, salon, startMin=700, sendWhatsapp=False)
    assert len(_notes(db, f"confirm:{on['id']}")) == 1
    assert _notes(db, f"confirm:{off['id']}") == []


def test_pending_status_on_create(owner, salon):
    assert _create(owner, salon, status="PENDING")["status"] == "PENDING"
    r = owner.post("/api/admin/appointments", json=_body(salon, status="COMPLETED", startMin=900))
    assert r.status_code == 400


def test_preview_reports_duration_price_and_conflicts(owner, salon):
    _create(owner, salon)
    p = data_of(
        owner.post(
            "/api/admin/appointments/preview",
            json={
                "serviceIds": [salon["manikur"].id, salon["kas"].id],
                "staffId": salon["staff_a"].id,
                "date": MONDAY,
                "startMin": 610,
            },
        )
    )
    assert p["totalMin"] >= 55 and p["discountRate"] == 0.10
    assert p["conflicts"] and p["canForce"] is True


def test_customer_search(owner, salon):
    rows = data_of(owner.get("/api/admin/customers/search?q=yılmaz"))["customers"]
    assert [r["phone"] for r in rows] == ["5321010000"]
    rows = data_of(owner.get("/api/admin/customers/search?q=532101"))["customers"]
    assert len(rows) == 2
    assert data_of(owner.get("/api/admin/customers/search?q=a"))["customers"] == []


# ---------------------------------------------------------------------
# Duzenleme
# ---------------------------------------------------------------------


def test_edit_time_staff_services_updates_occupancy(owner, salon, db):
    appt = _create(owner, salon)
    r = data_of(
        owner.patch(
            f"/api/admin/appointments/{appt['id']}",
            json={
                "expectedVersion": appt["version"],
                "staffId": salon["staff_b"].id,
                "startMin": 780,
                "serviceIds": [salon["manikur"].id, salon["kas"].id],
                "notes": "Acil",
            },
        )
    )["appointment"]
    assert r["version"] == appt["version"] + 1
    assert r["staffId"] == salon["staff_b"].id and r["startMin"] == 780 and r["endMin"] == 835
    row = _row(db, appt["id"])
    assert row.notes == "Acil" and len(row.items) == 2
    cells = db.scalars(select(OccupancyCell).where(OccupancyCell.appointment_id == appt["id"])).all()
    staff_cells = {c.cell_index for c in cells if c.owner_type == "STAFF"}
    assert min(staff_cells) == 780 // 5 and max(staff_cells) == 835 // 5 - 1
    assert all(c.owner_id == salon["staff_b"].id for c in cells if c.owner_type == "STAFF")
    # Eski slot bosaldi: ayni yere yeni randevu girebilir.
    _create(owner, salon, customerId=salon["other_customer"].id, startMin=600)
    # Fiyat yeniden hesaplandi (13:00 -> indirim yok): 350 + 150
    assert r["totalPrice"] == 500.0


def test_edit_price_override_and_notes_only_keeps_cells(owner, salon, db):
    appt = _create(owner, salon)
    before = _cells(db, appt["id"])
    r = data_of(
        owner.patch(
            f"/api/admin/appointments/{appt['id']}",
            json={"expectedVersion": appt["version"], "priceOverride": 100},
        )
    )["appointment"]
    assert r["totalPrice"] == 100.0 and r["discountRate"] == 0
    assert _cells(db, appt["id"]) == before


def test_edit_conflict_409_and_manager_force(owner, salon):
    a = _create(owner, salon, startMin=600)
    b = _create(owner, salon, customerId=salon["other_customer"].id, startMin=700)
    url = f"/api/admin/appointments/{b['id']}"
    r = owner.patch(url, json={"expectedVersion": b["version"], "startMin": 610})
    assert r.status_code == 409 and error_of(r)["code"] == "SLOT_CONFLICT"
    ok = owner.patch(url, json={"expectedVersion": b["version"], "startMin": 610, "force": True})
    assert ok.status_code == 200
    assert a["id"] != b["id"]


def test_edit_own_slot_is_not_a_conflict(owner, salon):
    appt = _create(owner, salon)
    r = owner.patch(
        f"/api/admin/appointments/{appt['id']}",
        json={"expectedVersion": appt["version"], "startMin": 615},
    )
    assert r.status_code == 200


def test_edit_rejected_for_final_states_and_stale_version(owner, salon):
    appt = _create(owner, salon)
    stale = owner.patch(
        f"/api/admin/appointments/{appt['id']}", json={"expectedVersion": 99, "notes": "x"}
    )
    assert error_of(stale)["code"] == "VERSION_MISMATCH"
    assert _status(owner, appt, "CANCELLED", notifyCustomer=False).status_code == 200
    r = owner.patch(f"/api/admin/appointments/{appt['id']}", json={"expectedVersion": 1, "notes": "x"})
    assert r.status_code == 409 and "Geri al" in error_of(r)["message"]


def test_edit_notify_customer_queues_update_message_once_per_change(owner, salon, db):
    appt = _create(owner, salon)
    r = data_of(
        owner.patch(
            f"/api/admin/appointments/{appt['id']}",
            json={"expectedVersion": appt["version"], "startMin": 660, "notifyCustomer": True},
        )
    )["appointment"]
    [n] = _notes(db, f"update:{appt['id']}:")
    assert n.dedupe_key == f"update:{appt['id']}:{r['version']}"
    assert "randevunuz güncellendi" in n.body and "11:00" in n.body
    # Hatirlatma yeni saate tasindi.
    [pre] = _notes(db, f"pre:{appt['id']}")
    assert "11:00" in pre.body


def test_staff_cannot_edit_other_staffs_appointment(owner, staff_user, salon):
    appt = _create(owner, salon)
    r = staff_user.patch(
        f"/api/admin/appointments/{appt['id']}", json={"expectedVersion": appt["version"], "notes": "x"}
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------
# Durum
# ---------------------------------------------------------------------


def test_cancel_pending_with_and_without_message(owner, salon, db):
    a = _create(owner, salon, status="PENDING", startMin=600)
    b = _create(owner, salon, status="PENDING", customerId=salon["other_customer"].id, startMin=700)
    assert _status(owner, a, "CANCELLED", notifyCustomer=False).status_code == 200
    assert _status(owner, b, "CANCELLED").status_code == 200
    assert _row(db, a["id"]).status == "CANCELLED" and _cells(db, a["id"]) == 0
    assert _notes(db, f"cancel:{a['id']}:") == []
    assert len(_notes(db, f"cancel:{b['id']}:")) == 1


def test_confirm_pending(owner, salon, db):
    a = _create(owner, salon, status="PENDING")
    assert _status(owner, a, "CONFIRMED").status_code == 200
    assert _row(db, a["id"]).status == "CONFIRMED"


# ---------------------------------------------------------------------
# Geri alma
# ---------------------------------------------------------------------


def _revert(client, appt_id, version, **kw):
    return client.post(
        f"/api/admin/appointments/{appt_id}/revert", json={"expectedVersion": version, **kw}
    )


def test_revert_completed_reverses_loyalty_stock_and_messages(owner, salon, db):
    row = db.get(Salon, salon["salon"].id)
    row.post_visit_enabled = True
    item = InventoryItem(
        branch_id=salon["branch"].id, name="Oje", unit="adet", quantity=10, critical_level=2
    )
    db.add(item)
    db.flush()
    db.add(ServiceConsumable(service_id=salon["manikur"].id, item_id=item.id, qty_per_use=1))
    db.commit()
    item_id = item.id

    appt = _create(owner, salon)
    done = data_of(_status(owner, appt, "COMPLETED"))
    assert done["loyalty"]["points"] > 0
    db.expire_all()
    assert db.get(InventoryItem, item_id).quantity == 9
    assert len(_notes(db, "postvisit:")) == 1 and _notes(db, "postvisit:")[0].status == "PENDING"
    assert db.get(Customer, salon["customer"].id).loyalty_points > 0

    r = data_of(_revert(owner, appt["id"], done["version"]))
    assert r["status"] == "CONFIRMED" and r["previousStatus"] == "COMPLETED"
    db.expire_all()
    assert db.get(Customer, salon["customer"].id).loyalty_points == 0
    assert db.get(InventoryItem, item_id).quantity == 10
    assert _notes(db, "postvisit:")[0].status == "CANCELLED"
    assert db.scalar(
        select(func.coalesce(func.sum(LoyaltyEntry.delta), 0.0)).where(
            LoyaltyEntry.appointment_id == appt["id"]
        )
    ) == 0
    assert db.scalar(
        select(func.count()).select_from(PhoneRiskEvent).where(
            PhoneRiskEvent.phone_hash == hash_phone(salon["customer"].phone)
        )
    ) == 0
    reasons = [m.reason for m in db.scalars(select(StockMovement).order_by(StockMovement.id))]
    assert reasons == ["APPOINTMENT_COMPLETED", "APPOINTMENT_REVERTED"]

    # Yeniden tamamlayinca stok ve puan tekrar islenir (idempotency engeline takilmaz).
    again = data_of(_status(owner, {"id": appt["id"], "version": r["version"]}, "COMPLETED"))
    assert again["stock"]["applied"] is True
    db.expire_all()
    assert db.get(InventoryItem, item_id).quantity == 9


def test_revert_cancelled_slot_free_and_slot_taken(owner, salon, db):
    appt = _create(owner, salon)
    cancelled = data_of(_status(owner, appt, "CANCELLED"))
    assert _cells(db, appt["id"]) == 0
    assert len(_notes(db, f"cancel:{appt['id']}:")) == 1

    # Slot bos: geri alinir, hucreler yeniden dolar, bekleyen iptal mesaji geri cekilir.
    ok = data_of(_revert(owner, appt["id"], cancelled["version"]))
    assert ok["status"] == "CONFIRMED" and _cells(db, appt["id"]) > 0
    assert _notes(db, f"cancel:{appt['id']}:")[0].status == "CANCELLED"
    assert _notes(db, f"pre:{appt['id']}")[0].status == "PENDING"

    # Tekrar iptal et, slotu baskasina ver -> geri alma 409.
    again = data_of(_status(owner, {"id": appt["id"], "version": ok["version"]}, "CANCELLED", notifyCustomer=False))
    other = _create(owner, salon, customerId=salon["other_customer"].id, startMin=610)
    r = _revert(owner, appt["id"], again["version"])
    assert r.status_code == 409 and error_of(r)["code"] == "SLOT_CONFLICT"
    assert _row(db, appt["id"]).status == "CANCELLED"

    forced = _revert(owner, appt["id"], again["version"], force=True)
    assert forced.status_code == 200
    assert _row(db, appt["id"]).status == "CONFIRMED"
    assert other["id"] != appt["id"]


def test_revert_no_show_removes_risk_event_and_reoccupies(owner, salon, db):
    appt = _create(owner, salon)
    ns = data_of(_status(owner, appt, "NO_SHOW"))
    phone_hash = hash_phone(salon["customer"].phone)

    def risk_count():
        db.expire_all()
        return db.scalar(
            select(func.count()).select_from(PhoneRiskEvent).where(
                PhoneRiskEvent.phone_hash == phone_hash, PhoneRiskEvent.outcome == "NO_SHOW"
            )
        )

    assert risk_count() == 1 and _cells(db, appt["id"]) == 0
    r = data_of(_revert(owner, appt["id"], ns["version"]))
    assert r["previousStatus"] == "NO_SHOW"
    assert risk_count() == 0 and _cells(db, appt["id"]) > 0


def test_revert_requires_manager_and_final_state(owner, staff_user, salon):
    appt = _create(owner, salon, staffId=salon["staff_b"].id)
    cancelled = data_of(_status(owner, appt, "CANCELLED", notifyCustomer=False))
    assert _revert(staff_user, appt["id"], cancelled["version"]).status_code == 403
    active = _create(owner, salon, customerId=salon["other_customer"].id, startMin=900)
    r = _revert(owner, active["id"], active["version"])
    assert r.status_code == 409


# ---------------------------------------------------------------------
# Zorla ust uste randevu: serbest kalan hucreler B'ye gecmeli
# ---------------------------------------------------------------------


def _staff_cell_count(db, appointment_id):
    db.expire_all()
    return db.scalar(
        select(func.count()).select_from(OccupancyCell).where(
            OccupancyCell.appointment_id == appointment_id, OccupancyCell.owner_type == "STAFF"
        )
    )


def _assert_still_blocked(owner, db, salon, start=625):
    from app.core.package_layout import layout_package
    from app.errors import AppError
    from app.services.soft_lock import acquire_slot_lock
    from tests.conftest import spec_of

    r = owner.post(
        "/api/admin/appointments",
        json=_body(salon, customerId=salon["other_customer"].id, startMin=start),
    )
    assert r.status_code == 409, r.text
    with pytest.raises(AppError):
        acquire_slot_lock(
            db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id, session_id="x",
            date=MONDAY, start_min=start, layout=layout_package([spec_of(salon["kas"])]),
        )


def _forced_pair(owner, salon):
    a = _create(owner, salon, startMin=600)  # 600-640
    b = data_of(
        owner.post(
            "/api/admin/appointments",
            json=_body(salon, customerId=salon["other_customer"].id, startMin=620, force=True),
        )
    )["appointment"]  # 620-660, 620-640 A'nin elinde
    return a, b


def test_cancel_of_first_appointment_keeps_forced_overlap_blocked(owner, salon, db):
    a, b = _forced_pair(owner, salon)
    assert _staff_cell_count(db, b["id"]) < 8
    assert _status(owner, a, "CANCELLED", notifyCustomer=False).status_code == 200
    assert _staff_cell_count(db, b["id"]) == 8
    _assert_still_blocked(owner, db, salon)


def test_no_show_of_first_appointment_keeps_overlap_blocked(owner, salon, db):
    a, b = _forced_pair(owner, salon)
    assert _status(owner, a, "NO_SHOW").status_code == 200
    assert _staff_cell_count(db, b["id"]) == 8
    _assert_still_blocked(owner, db, salon)


def test_move_of_first_appointment_keeps_overlap_blocked(owner, salon, db):
    a, b = _forced_pair(owner, salon)
    r = owner.patch(
        f"/api/admin/appointments/{a['id']}/move",
        json={"toStaffId": salon["staff_b"].id, "toDate": MONDAY, "toStartMin": 900,
              "expectedVersion": a["version"]},
    )
    assert r.status_code == 200, r.text
    assert _staff_cell_count(db, b["id"]) == 8
    _assert_still_blocked(owner, db, salon)


def test_edit_of_first_appointment_keeps_overlap_blocked(owner, salon, db):
    a, b = _forced_pair(owner, salon)
    r = owner.patch(
        f"/api/admin/appointments/{a['id']}", json={"expectedVersion": a["version"], "startMin": 900}
    )
    assert r.status_code == 200, r.text
    assert _staff_cell_count(db, b["id"]) == 8
    _assert_still_blocked(owner, db, salon)


# ---------------------------------------------------------------------
# Surukle-birak: hatirlatma yenilenir, istege bagli bildirim
# ---------------------------------------------------------------------


def _move(client, appt, start, **kw):
    return client.patch(
        f"/api/admin/appointments/{appt['id']}/move",
        json={"toStaffId": appt["staffId"], "toDate": MONDAY, "toStartMin": start,
              "expectedVersion": appt["version"], **kw},
    )


def test_drag_move_refreshes_pre_reminder_without_notice_by_default(owner, salon, db):
    appt = _create(owner, salon, startMin=600)
    [pre] = _notes(db, f"pre:{appt['id']}")
    assert "10:00" in pre.body
    r = data_of(_move(owner, appt, 660))
    assert r["noticeQueued"] is False
    [pre] = _notes(db, f"pre:{appt['id']}")
    assert "11:00" in pre.body and pre.status == "PENDING"
    assert _notes(db, f"update:{appt['id']}:") == []


def test_drag_move_notify_and_followup_endpoint(owner, salon, db):
    a = _create(owner, salon, startMin=600)
    r = data_of(_move(owner, a, 660, notifyCustomer=True))
    assert r["noticeQueued"] is True
    [n] = _notes(db, f"update:{a['id']}:")
    assert "11:00" in n.body

    b = _create(owner, salon, customerId=salon["other_customer"].id, startMin=800)
    moved = data_of(_move(owner, b, 840))
    assert _notes(db, f"update:{b['id']}:") == []
    ok = data_of(owner.post(f"/api/admin/appointments/{b['id']}/notify-update"))
    assert ok["queued"] is True and moved["version"] == b["version"] + 1
    assert len(_notes(db, f"update:{b['id']}:")) == 1
    data_of(owner.post(f"/api/admin/appointments/{b['id']}/notify-update"))
    assert len(_notes(db, f"update:{b['id']}:")) == 1  # surum basina tek mesaj
