"""Panel sayfalarini besleyen personel uclari.

Next.js paneli veritabanina dokunmaz; her sayfa bu uclardan beslenir.
Testler, sayfalarin ihtiyac duydugu alanlarin (kapsam sayisi, ornek
onizleme, kuyruk, ozet, isi haritasi bayraklari...) dogru dondugunu
dogrular.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.models import (
    Campaign,
    InventoryItem,
    OccupancyStat,
    PortfolioItem,
    ReminderRule,
    Review,
    ScheduledNotification,
    StockMovement,
)
from app.time_utils import add_days_to_key, now_local, to_date_key

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)

NEW_ENDPOINTS = (
    "/api/admin/notifications",
    "/api/admin/portfolio",
    "/api/admin/reviews",
    "/api/admin/campaigns",
    "/api/admin/reminder-rules",
    "/api/admin/stats/opportunity",
)


def data_of(response) -> dict:
    body = response.json()
    assert body["ok"] is True, body
    return body["data"]


@pytest.fixture()
def staff_client(salon, db):
    # OccupancyStat'in sube FK'si yok; kalintilar elle temizlenir.
    db.execute(delete(OccupancyStat))
    db.commit()
    with TestClient(app) as client:
        data_of(
            client.post(
                "/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}
            )
        )
        yield client
    db.execute(delete(OccupancyStat))
    db.commit()


def test_new_admin_views_require_staff(salon):
    with TestClient(app) as client:
        for path in NEW_ENDPOINTS:
            body = client.get(path).json()
            assert body["ok"] is False and body["error"]["code"] == "UNAUTHORIZED", path


def test_campaigns_include_live_audience(staff_client, salon, db):
    branch_id = salon["branch"].id
    db.add_all(
        [
            Campaign(branch_id=branch_id, name="Herkese", kind="BONUS_POINTS", value=50,
                     target_rule="{}", priority=5),
            Campaign(branch_id=branch_id, name="Sadik", kind="DISCOUNT_PERCENT", value=10,
                     target_rule=json.dumps({"minVisits": 3}), priority=3),
            Campaign(branch_id=branch_id, name="Pasif", kind="DISCOUNT_PERCENT", value=20,
                     target_rule="{}", priority=1, is_active=False),
        ]
    )
    db.commit()

    payload = data_of(staff_client.get("/api/admin/campaigns"))
    assert payload["customerCount"] == 2
    by_name = {c["name"]: c for c in payload["campaigns"]}
    assert [c["name"] for c in payload["campaigns"]] == ["Herkese", "Sadik", "Pasif"]
    assert by_name["Herkese"]["matchedCount"] == 2
    assert by_name["Sadik"]["matchedCount"] == 0
    # Pasif kampanya kimseye eslesmez.
    assert by_name["Pasif"]["matchedCount"] == 0
    assert by_name["Sadik"]["targetRule"] == {"minVisits": 3}


def test_reminder_rules_sample_preview_uses_sample_product(staff_client, salon, db):
    db.add(
        ReminderRule(
            branch_id=salon["branch"].id, name="Oje", service_id=salon["manikur"].id,
            formula="PRODUCT_LIFETIME", base_days=30,
            params=json.dumps({"productDays": {"kalici_oje": 21, "jel": 28}}),
            template="Merhaba {ad}", priority=1,
        )
    )
    db.commit()

    rule = data_of(staff_client.get("/api/admin/reminder-rules"))["rules"][0]
    assert rule["service"]["name"] == "Manikür"
    assert rule["params"]["productDays"]["kalici_oje"] == 21
    # Urun bilinmeden formul baseDays'e duser; ornek urunle urun omru kullanilir.
    assert rule["previewDays"] != rule["samplePreviewDays"]
    assert rule["samplePreviewDays"] == 21


def test_notification_queue_is_ordered_and_limited(staff_client, salon, db):
    now = now_local()
    customer_id = salon["customer"].id
    for i in range(30):
        db.add(
            ScheduledNotification(
                customer_id=customer_id, channel="SMS", body=f"Mesaj {i}",
                due_at=now + timedelta(hours=30 - i), dedupe_key=f"test-queue-{i}",
                status="SENT" if i == 29 else "PENDING",
            )
        )
    db.commit()

    queue = data_of(staff_client.get("/api/admin/notifications"))["notifications"]
    assert len(queue) == 25
    due = [n["dueAt"] for n in queue]
    assert due == sorted(due)
    assert queue[0]["body"] == "Mesaj 29" and queue[0]["status"] == "SENT"
    assert queue[0]["customer"] == {"firstName": "Ayşe", "phone": "5321010000"}

    assert len(data_of(staff_client.get("/api/admin/notifications?limit=5"))["notifications"]) == 5


def test_admin_reviews_include_summary_and_hidden_reviews(staff_client, salon, db):
    branch_id = salon["branch"].id
    db.add_all(
        [
            Review(branch_id=branch_id, staff_id=salon["staff_a"].id, author_name="Ayşe Y.",
                   rating=5, comment="Harika", is_verified=True),
            Review(branch_id=branch_id, author_name="Zeynep K.", rating=2, comment="Olmadı"),
            # Yayindan kaldirilmis: listede gorunur, ozete ve bekleyen sayisina girmez.
            Review(branch_id=branch_id, author_name="Gizli", rating=1, comment="Spam",
                   is_published=False),
        ]
    )
    db.commit()

    payload = data_of(staff_client.get("/api/admin/reviews"))
    assert len(payload["reviews"]) == 3
    assert payload["summary"]["count"] == 2
    assert payload["summary"]["average"] == 3.5
    assert payload["pendingCount"] == 1
    first = next(r for r in payload["reviews"] if r["authorName"] == "Ayşe Y.")
    assert first["staffName"] == "Elif"
    assert first["appointmentDate"] is None
    hidden = next(r for r in payload["reviews"] if r["authorName"] == "Gizli")
    assert hidden["isPublished"] is False


def test_opportunity_cells_carry_flag_and_sample_total(staff_client, salon, db):
    branch_id = salon["branch"].id
    db.add_all(
        [
            OccupancyStat(branch_id=branch_id, weekday=2, slot_min=600, occupancy=0.05,
                          sample_size=40),
            OccupancyStat(branch_id=branch_id, weekday=5, slot_min=600, occupancy=0.95,
                          sample_size=40),
        ]
    )
    db.commit()

    payload = data_of(staff_client.get("/api/admin/stats/opportunity"))
    assert payload["totalSamples"] == 80
    cells = {c["weekday"]: c for c in payload["cells"]}
    assert cells[2]["isOpportunity"] is True and cells[2]["discountRate"] > 0
    assert cells[5]["isOpportunity"] is False
    assert [c["weekday"] for c in payload["bestOpportunities"]] == [2]


def test_admin_portfolio_listing(staff_client, salon, db):
    branch_id = salon["branch"].id
    db.add_all(
        [
            PortfolioItem(branch_id=branch_id, title="Eski", image_url="/u/1.jpg",
                          category_id=salon["category"].id, staff_id=salon["staff_b"].id),
            PortfolioItem(branch_id=branch_id, title="Yeni", image_url="/u/2.jpg"),
        ]
    )
    db.commit()

    payload = data_of(staff_client.get("/api/admin/portfolio"))
    assert [i["title"] for i in payload["items"]] == ["Yeni", "Eski"]
    eski = payload["items"][1]
    assert eski["categoryName"] == "Genel" and eski["staffName"] == "Merve"
    assert payload["items"][0]["categoryName"] is None
    assert payload["categories"] == [{"id": salon["category"].id, "name": "Genel"}]
    assert [s["name"] for s in payload["staff"]] == ["Elif", "Merve"]


def test_calendar_staff_carry_service_ids(staff_client, salon):
    calendar = data_of(staff_client.get(f"/api/admin/calendar?date={TOMORROW}"))
    expected = sorted(salon[k].id for k in ("boya", "kas", "manikur"))
    for staff in calendar["staff"]:
        assert sorted(staff["serviceIds"]) == expected


def test_customer_search_is_turkish_case_aware(staff_client, salon):
    # "YILMAZ" Turkce kucuk harfle "yılmaz" olur (casefold "yilmaz" derdi).
    rows = data_of(staff_client.get("/api/admin/customers?q=YILMAZ"))["customers"]
    assert [r["firstName"] for r in rows] == ["Ayşe"]


def test_inventory_recent_movements_are_per_item(staff_client, salon, db):
    branch_id = salon["branch"].id
    quiet = InventoryItem(branch_id=branch_id, name="Az hareketli", quantity=5)
    busy = InventoryItem(branch_id=branch_id, name="Cok hareketli", quantity=500)
    db.add_all([quiet, busy])
    db.flush()

    old = now_local() - timedelta(days=30)
    db.add(StockMovement(item_id=quiet.id, delta=5, reason="PURCHASE", created_at=old))
    # Global "son 200" sorgusu az hareketli kalemin gecmisini kaybederdi.
    for i in range(210):
        db.add(StockMovement(item_id=busy.id, delta=-1, reason="WASTE",
                             created_at=now_local() - timedelta(minutes=i)))
    db.commit()

    items = {i["name"]: i for i in data_of(staff_client.get("/api/admin/inventory"))["items"]}
    assert len(items["Az hareketli"]["recentMovements"]) == 1
    assert len(items["Cok hareketli"]["recentMovements"]) == 5

    bad = staff_client.patch(
        "/api/admin/inventory", json={"itemId": quiet.id, "delta": 1, "reason": "HIRSIZLIK"}
    ).json()
    assert bad["ok"] is False and bad["error"]["code"] == "VALIDATION"
