"""Hizmet sarf recetesi (service_consumable) duzenleme uclari."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import (
    Branch,
    InventoryItem,
    Salon,
    Service,
    ServiceConsumable,
    StockMovement,
)
from app.time_utils import now_local


def data_of(response) -> dict:
    body = response.json()
    assert body["ok"] is True, body
    return body["data"]


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


@pytest.fixture()
def stock(salon, db):
    branch = salon["branch"]
    a = InventoryItem(branch_id=branch.id, name="Aseton", unit="ml", quantity=1000, critical_level=10)
    b = InventoryItem(branch_id=branch.id, name="Boya", unit="gram", quantity=1000, critical_level=10)
    c = InventoryItem(branch_id=branch.id, name="Cila", unit="adet", quantity=1000, critical_level=10)
    db.add_all([a, b, c])
    db.flush()
    db.add(ServiceConsumable(service_id=salon["manikur"].id, item_id=a.id, qty_per_use=5))
    db.add(ServiceConsumable(service_id=salon["manikur"].id, item_id=b.id, qty_per_use=2))
    db.commit()
    return {"a": a.id, "b": b.id, "c": c.id}


def _put(client, service_id, lines):
    return client.put(f"/api/admin/recipes/{service_id}", json={"consumables": lines})


def _svc(client, service_id):
    return next(s for s in data_of(client.get("/api/admin/recipes"))["services"] if s["id"] == service_id)


def test_get_returns_seeded_recipes(owner, salon, stock):
    data = data_of(owner.get("/api/admin/recipes"))
    assert [i["name"] for i in data["items"]] == ["Aseton", "Boya", "Cila"]
    assert data["items"][0] == {"id": stock["a"], "name": "Aseton", "unit": "ml"}
    manikur = next(s for s in data["services"] if s["id"] == salon["manikur"].id)
    assert manikur["isActive"] is True
    assert manikur["consumables"] == [
        {"itemId": stock["a"], "itemName": "Aseton", "unit": "ml", "qtyPerUse": 5},
        {"itemId": stock["b"], "itemName": "Boya", "unit": "gram", "qtyPerUse": 2},
    ]
    kas = next(s for s in data["services"] if s["id"] == salon["kas"].id)
    assert kas["consumables"] == []


def test_put_replaces_add_update_remove(owner, salon, stock):
    sid = salon["manikur"].id
    out = data_of(_put(owner, sid, [
        {"itemId": stock["b"], "qtyPerUse": 3.5},   # guncelle
        {"itemId": stock["c"], "qtyPerUse": 1},     # ekle
    ]))["service"]
    assert out["id"] == sid and out["isActive"] is True
    assert [(c["itemId"], c["qtyPerUse"]) for c in out["consumables"]] == [
        (stock["b"], 3.5), (stock["c"], 1),
    ]
    assert _svc(owner, sid)["consumables"] == out["consumables"]


def test_put_empty_clears(owner, salon, stock):
    sid = salon["manikur"].id
    assert data_of(_put(owner, sid, []))["service"]["consumables"] == []
    assert _svc(owner, sid)["consumables"] == []


def test_put_unknown_item_400(owner, salon, stock, db):
    sid = salon["manikur"].id
    r = _put(owner, sid, [{"itemId": 999999, "qtyPerUse": 1}])
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION"
    # Baska subedeki kalem de gecersiz
    other_salon = Salon(name="Diger", slug="diger", phone="5550000001")
    db.add(other_salon)
    db.flush()
    other_branch = Branch(salon_id=other_salon.id, name="Sube2", open_minute=540, close_minute=1200)
    db.add(other_branch)
    db.flush()
    foreign = InventoryItem(branch_id=other_branch.id, name="Yabanci", unit="adet", quantity=1)
    db.add(foreign)
    db.commit()
    r = _put(owner, sid, [{"itemId": foreign.id, "qtyPerUse": 1}])
    assert r.status_code == 400
    # Recete degismedi
    assert len(_svc(owner, sid)["consumables"]) == 2


def test_put_duplicate_400(owner, salon, stock):
    r = _put(owner, salon["manikur"].id, [
        {"itemId": stock["a"], "qtyPerUse": 1}, {"itemId": stock["a"], "qtyPerUse": 2},
    ])
    assert r.status_code == 400


@pytest.mark.parametrize("qty", [0, -1])
def test_put_nonpositive_qty_rejected(owner, salon, stock, qty):
    r = _put(owner, salon["manikur"].id, [{"itemId": stock["a"], "qtyPerUse": qty}])
    assert r.status_code == 400
    assert len(_svc(owner, salon["manikur"].id)["consumables"]) == 2


def test_put_too_many_lines_rejected(owner, salon, stock):
    lines = [{"itemId": stock["a"] + i, "qtyPerUse": 1} for i in range(51)]
    assert _put(owner, salon["manikur"].id, lines).status_code == 400


def test_put_unknown_service_404(owner, salon, stock):
    r = _put(owner, 999999, [])
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_non_manager_staff_forbidden_but_can_read(staff_user, salon, stock):
    assert staff_user.get("/api/admin/recipes").status_code == 200
    r = _put(staff_user, salon["manikur"].id, [])
    assert r.status_code == 403


def test_completion_uses_new_recipe(owner, salon, stock, db):
    sid = salon["manikur"].id
    data_of(_put(owner, sid, [{"itemId": stock["c"], "qtyPerUse": 7}]))

    d = now_local().date() + timedelta(days=7)
    body = {
        "customerId": salon["customer"].id,
        "staffId": salon["staff_a"].id,
        "date": d.isoformat(),
        "startMin": 600,
        "serviceIds": [sid],
    }
    appt = data_of(owner.post("/api/admin/appointments", json=body))["appointment"]
    data_of(owner.patch(
        f"/api/admin/appointments/{appt['id']}/status",
        json={"status": "COMPLETED", "expectedVersion": appt["version"]},
    ))

    db.expire_all()
    moves = db.scalars(select(StockMovement).where(StockMovement.appointment_id == appt["id"])).all()
    assert [(m.item_id, m.delta) for m in moves] == [(stock["c"], -7)]
    assert db.get(InventoryItem, stock["c"]).quantity == 993
    assert db.get(InventoryItem, stock["a"]).quantity == 1000
