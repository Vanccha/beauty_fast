"""
=====================================================================
HATA REGRESYONLARI - "randevuyu iki kez seçmek zorunda kalmak"
=====================================================================

Next.js surumunde randevu akisinda iki ayri kusur, kullaniciya ayni
sekilde gorunuyordu: secim tutmuyor, bastan yapmak gerekiyor.

HATA 1 - kendi soft-lock'un, kendi musaitlik listeni engelliyor
    ``src/lib/server/availability.ts:230-268`` suresi dolmamis TUM LOCK
    hucrelerini mesgul sayiyordu; kilidi tutan oturumun kendisi dahil.
    Arayuzdeki "Geri" dugmesi de kilidi birakmadigi icin
    (``booking-flow.tsx:760``) kullanici bir adim geri gidince kendi
    tuttugu saat listeden kayboluyordu.

HATA 2 - ayni hizmeti iki kez secmek imkansiz
    Yetkinlik kontrolu SAYI karsilastirmasiyla yapiliyordu
    (``catalog.ts:118``, ``slots/lock/route.ts:46``,
    ``appointments/route.ts:62``). ``serviceIds`` icinde tekrar eden bir
    id varsa yetkinlik satiri sayisi eksik kalip istek reddediliyordu -
    oysa stok katmani tekrari acikca destekliyordu.
"""

from __future__ import annotations


import pytest

from app.core.package_layout import layout_package
from app.errors import AppError
from app.services.availability import compute_availability
from app.services.catalog import assert_staff_can_do, find_capable_staff, load_service_specs
from app.services.soft_lock import acquire_slot_lock
from app.time_utils import add_days_to_key, now_local, to_date_key

from .conftest import spec_of

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)


# ---------------------------------------------------------------------
# HATA 1
# ---------------------------------------------------------------------


def test_own_lock_does_not_hide_own_slot(salon, db):
    """★ Kendi tuttugun saat, kendi listenden kaybolmaz."""
    layout = layout_package([spec_of(salon["manikur"])])

    acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="ziyaretci-1", date=TOMORROW, start_min=600, layout=layout,
    )

    result = compute_availability(
        db,
        date=TOMORROW,
        service_ids=[salon["manikur"].id],
        staff_id=salon["staff_a"].id,
        viewer_key="ziyaretci-1",
    )

    starts = [s["startMin"] for s in result["staff"][0]["slots"]]
    assert 600 in starts, "kullanıcı kendi tuttuğu saati görmeye devam etmeli"

    held = next(s for s in result["staff"][0]["slots"] if s["startMin"] == 600)
    assert held["heldByYou"] is True

    # Arayuz "saat hala senin" diyebilsin diye kilit bilgisi de doner.
    assert result["yourLock"]["startMin"] == 600
    assert result["yourLock"]["staffId"] == salon["staff_a"].id


def test_other_visitors_lock_still_blocks(salon, db):
    """Baskasinin kilidi eskisi gibi engelleyicidir."""
    layout = layout_package([spec_of(salon["manikur"])])

    acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="baska-ziyaretci", date=TOMORROW, start_min=600, layout=layout,
    )

    result = compute_availability(
        db,
        date=TOMORROW,
        service_ids=[salon["manikur"].id],
        staff_id=salon["staff_a"].id,
        viewer_key="ziyaretci-1",
    )

    starts = [s["startMin"] for s in result["staff"][0]["slots"]]
    assert 600 not in starts
    assert result["yourLock"] is None


def test_anonymous_request_sees_all_locks_as_busy(salon, db):
    """``viewer_key`` yoksa davranis eski surumle aynidir (guvenli taraf)."""
    layout = layout_package([spec_of(salon["manikur"])])
    acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="birisi", date=TOMORROW, start_min=600, layout=layout,
    )

    result = compute_availability(
        db, date=TOMORROW, service_ids=[salon["manikur"].id],
        staff_id=salon["staff_a"].id, viewer_key=None,
    )
    assert 600 not in [s["startMin"] for s in result["staff"][0]["slots"]]


# ---------------------------------------------------------------------
# HATA 2
# ---------------------------------------------------------------------


def test_duplicate_services_keep_capable_staff(salon, db):
    """★ Ayni hizmet iki kez secilirse personel ELENMEZ."""
    ids = [salon["kas"].id, salon["kas"].id]

    capable = find_capable_staff(db, salon["branch"].id, ids)
    assert {s.id for s in capable} == {salon["staff_a"].id, salon["staff_b"].id}


def test_duplicate_services_pass_capability_check(salon, db):
    speed = assert_staff_can_do(db, salon["staff_a"].id, [salon["kas"].id, salon["kas"].id])
    assert speed == 1.0


def test_duplicate_services_produce_two_items(salon, db):
    specs = load_service_specs(db, [salon["kas"].id, salon["kas"].id])
    assert len(specs) == 2

    layout = layout_package(specs)
    assert layout.total_min == 30
    assert layout.total_price == 300


def test_availability_supports_duplicate_services(salon, db):
    """Musaitlik sorgusu tekrar eden hizmetle de slot uretir."""
    result = compute_availability(
        db,
        date=TOMORROW,
        service_ids=[salon["kas"].id, salon["kas"].id],
        staff_id=salon["staff_a"].id,
        viewer_key="ziyaretci-1",
    )
    assert result["staff"], "yetkin personel bulunmalı"
    assert result["staff"][0]["totalMin"] == 30
    assert result["staff"][0]["slots"]
    assert result["message"] is None


def test_unknown_service_is_still_rejected(salon, db):
    with pytest.raises(AppError) as excinfo:
        load_service_specs(db, [salon["kas"].id, 99999])
    assert excinfo.value.code == "NOT_FOUND"


def test_staff_without_skill_is_still_rejected(salon, db):
    """Tekrarlara tolerans, yetkinlik kontrolunu gevsetmez."""
    from app.models import StaffService
    from sqlalchemy import delete

    db.execute(
        delete(StaffService).where(
            StaffService.staff_id == salon["staff_b"].id,
            StaffService.service_id == salon["boya"].id,
        )
    )
    db.commit()

    with pytest.raises(AppError) as excinfo:
        assert_staff_can_do(db, salon["staff_b"].id, [salon["boya"].id, salon["boya"].id])
    assert excinfo.value.code == "VALIDATION"


def test_package_size_is_capped(salon, db):
    with pytest.raises(AppError) as excinfo:
        load_service_specs(db, [salon["kas"].id] * 11)
    assert excinfo.value.code == "VALIDATION"


# ---------------------------------------------------------------------
# HATA 3 - paket ozeti hangi ustaya ait?
# ---------------------------------------------------------------------


def test_package_summary_is_nominal_without_staff_choice(salon, db):
    """Usta secilmemisse ozet NOMINAL (speed_factor = 1.0) doner."""
    result = compute_availability(
        db, date=TOMORROW, service_ids=[salon["boya"].id], viewer_key="z"
    )
    assert result["package"]["isNominal"] is True
    assert result["package"]["basedOnStaffId"] is None
    assert result["package"]["totalMin"] == 100


def test_package_summary_follows_selected_staff(salon, db):
    """Usta secilmisse ozet O USTAYA gore hesaplanir."""
    from sqlalchemy import update

    from app.models import StaffService

    # Selin tarzi yavas usta: aktif sureler %10 uzun.
    db.execute(
        update(StaffService)
        .where(StaffService.staff_id == salon["staff_b"].id)
        .values(speed_factor=1.1)
    )
    db.commit()

    result = compute_availability(
        db,
        date=TOMORROW,
        service_ids=[salon["boya"].id],
        staff_id=salon["staff_b"].id,
        viewer_key="z",
    )
    assert result["package"]["isNominal"] is False
    assert result["package"]["basedOnStaffId"] == salon["staff_b"].id
    # Ekranda yazan sure ile kilitlenecek sure ARTIK AYNI.
    assert result["package"]["totalMin"] == result["staff"][0]["totalMin"]
    assert result["package"]["totalMin"] > 100
