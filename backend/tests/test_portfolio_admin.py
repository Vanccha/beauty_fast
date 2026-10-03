"""Portfolyo yonetimi: duzenleme, gorsel degistirme, siralama, gizleme."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import config
from app.main import app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def data_of(response) -> dict:
    body = response.json()
    assert body["ok"] is True, body
    return body["data"]


@pytest.fixture()
def staff_client(salon):
    with TestClient(app) as client:
        data_of(
            client.post(
                "/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}
            )
        )
        yield client


def _add(client, title: str, **extra) -> int:
    data = {"title": title, **extra}
    res = client.post(
        "/api/admin/portfolio", data=data, files={"file": ("a.png", PNG, "image/png")}
    )
    item = data_of(res)["item"]
    return item["id"]


def _disk(url: str) -> Path:
    return config.upload_dir / url[len("/uploads/"):]


def _admin_item(client, item_id: int) -> dict:
    return next(i for i in data_of(client.get("/api/admin/portfolio"))["items"] if i["id"] == item_id)


def test_patch_updates_fields(staff_client, salon):
    item_id = _add(staff_client, "Eski", description="d")
    data = data_of(
        staff_client.patch(
            f"/api/admin/portfolio/{item_id}",
            data={
                "title": "  Yeni  ",
                "description": "",
                "categoryId": str(salon["category"].id),
                "staffId": str(salon["staff_b"].id),
                "isPublished": "false",
            },
        )
    )["item"]
    assert data["title"] == "Yeni"
    assert data["description"] is None
    assert data["categoryId"] == salon["category"].id
    assert data["staffId"] == salon["staff_b"].id
    assert data["isPublished"] is False

    # Gonderilmeyen alanlar degismez; bos categoryId temizler.
    data = data_of(
        staff_client.patch(f"/api/admin/portfolio/{item_id}", data={"categoryId": ""})
    )["item"]
    assert data["title"] == "Yeni" and data["categoryId"] is None
    assert data["staffId"] == salon["staff_b"].id and data["isPublished"] is False
    assert _admin_item(staff_client, item_id)["categoryName"] is None


def test_patch_replaces_image_and_deletes_old_file(staff_client):
    item_id = _add(staff_client, "Foto")
    old_url = _admin_item(staff_client, item_id)["imageUrl"]
    assert _disk(old_url).is_file()

    new = data_of(
        staff_client.patch(
            f"/api/admin/portfolio/{item_id}",
            files={"file": ("b.jpg", JPG, "image/jpeg")},
        )
    )["item"]
    assert new["imageUrl"] != old_url and new["imageUrl"].endswith(".jpg")
    assert _disk(new["imageUrl"]).is_file()
    assert not _disk(old_url).exists()

    bad = staff_client.patch(
        f"/api/admin/portfolio/{item_id}", files={"file": ("x.png", b"not an image", "image/png")}
    ).json()
    assert bad["ok"] is False and bad["error"]["code"] == "VALIDATION"
    assert _disk(new["imageUrl"]).is_file()  # basarisiz degisim eskiyi silmez

    staff_client.delete(f"/api/admin/portfolio?id={item_id}")
    assert not _disk(new["imageUrl"]).exists()


def test_patch_validation_errors(staff_client):
    item_id = _add(staff_client, "X")
    for form in ({"categoryId": "99999"}, {"staffId": "99999"}, {"title": "  "}, {"isPublished": "belki"}):
        body = staff_client.patch(f"/api/admin/portfolio/{item_id}", data=form).json()
        assert body["ok"] is False and body["error"]["code"] == "VALIDATION", form
        assert body["error"]["message"]
    missing = staff_client.patch("/api/admin/portfolio/999999", data={"title": "a"}).json()
    assert missing["ok"] is False and missing["error"]["code"] == "NOT_FOUND"


def test_portfolio_writes_require_staff(salon, staff_client):
    item_id = _add(staff_client, "Y")
    with TestClient(app) as anon:
        r = anon.patch(f"/api/admin/portfolio/{item_id}", data={"title": "h"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
        r = anon.post("/api/admin/portfolio/reorder", json={"ids": [item_id]})
        assert r.status_code == 401
        r = anon.delete(f"/api/admin/portfolio?id={item_id}")
        assert r.status_code == 401


def test_reorder_and_public_respects_order_and_visibility(staff_client):
    a = _add(staff_client, "A")
    b = _add(staff_client, "B")
    c = _add(staff_client, "C")

    res = data_of(staff_client.post("/api/admin/portfolio/reorder", json={"ids": [b, c, a]}))
    assert res["ids"] == [b, c, a]
    admin_titles = [i["title"] for i in data_of(staff_client.get("/api/admin/portfolio"))["items"]]
    assert admin_titles == ["B", "C", "A"]

    public = [i["title"] for i in data_of(staff_client.get("/api/portfolio"))["items"]]
    assert public == ["B", "C", "A"]

    # Kismi liste: eksikler sona eklenir
    res = data_of(staff_client.post("/api/admin/portfolio/reorder", json={"ids": [a]}))
    assert res["ids"][0] == a and set(res["ids"]) == {a, b, c}

    # Gizlenen is public'te gorunmez, panelde durur
    staff_client.patch(f"/api/admin/portfolio/{b}", data={"isPublished": "false"})
    public = [i["title"] for i in data_of(staff_client.get("/api/portfolio"))["items"]]
    assert "B" not in public and set(public) == {"A", "C"}
    assert _admin_item(staff_client, b)["isPublished"] is False

    bad = staff_client.post("/api/admin/portfolio/reorder", json={"ids": [a, 999999]}).json()
    assert bad["ok"] is False and bad["error"]["code"] == "NOT_FOUND"
    dup = staff_client.post("/api/admin/portfolio/reorder", json={"ids": [a, a]}).json()
    assert dup["ok"] is False and dup["error"]["code"] == "VALIDATION"
