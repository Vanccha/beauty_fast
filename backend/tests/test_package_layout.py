"""Paket yerlesimi: sikistirma, golge penceresi, hiz carpani, tekrar eden hizmet."""

from __future__ import annotations

from app.core.package_layout import LayoutOptions, billable_minutes, layout_package
from app.core.types import ServiceSpec
from app.intervals import Interval

BOYA = ServiceSpec(
    id=1, name="Saç Boyası",
    active_before_min=30, passive_min=40, active_after_min=20, buffer_min=10,
    shadow_host_allowed=True, shadow_guest_allowed=False, price=1200,
)
KAS = ServiceSpec(
    id=2, name="Kaş Alma",
    active_before_min=15, passive_min=0, active_after_min=0, buffer_min=0,
    shadow_host_allowed=False, shadow_guest_allowed=True, price=150,
)
MANIKUR = ServiceSpec(
    id=3, name="Manikür",
    active_before_min=40, passive_min=0, active_after_min=0, buffer_min=0,
    shadow_host_allowed=False, shadow_guest_allowed=False, price=350,
)
KALICI_OJE = ServiceSpec(
    id=4, name="Kalıcı Oje",
    active_before_min=40, passive_min=0, active_after_min=0, buffer_min=0,
    shadow_host_allowed=False, shadow_guest_allowed=False, price=500,
)
NAIL_ART = ServiceSpec(
    id=5, name="Nail Art",
    active_before_min=30, passive_min=0, active_after_min=0, buffer_min=0,
    shadow_host_allowed=False, shadow_guest_allowed=False, price=250,
)


def test_single_service_total():
    layout = layout_package([BOYA])
    assert layout.total_min == 100  # 30 + 40 + 20 + 10 buffer
    assert billable_minutes(layout) == 90
    # Usta pasif 40 dakikada MESGUL degildir.
    assert layout.staff_busy == [Interval(0, 30), Interval(70, 100)]
    assert layout.shadow_windows == [Interval(30, 70)]


def test_110_minute_package():
    """Manikür + Kalıcı Oje + Nail Art = 40 + 40 + 30 = 110 dk."""
    layout = layout_package([MANIKUR, KALICI_OJE, NAIL_ART])
    assert layout.total_min == 110
    assert layout.saved_min == 0


def test_compaction_places_guest_into_passive_window():
    """Kas alma, boyanin 40 dk beklemesine yerlesir: 115 yerine 100 dk."""
    layout = layout_package([BOYA, KAS])
    assert layout.total_min == 100
    assert layout.saved_min == 15

    kas_item = layout.items[1]
    assert kas_item.placed_in_shadow is True
    assert kas_item.offset_min == 30  # pasif pencerenin basi

    # Kalan pencere (45-70) hala DIS bir misafire aciktir.
    assert layout.shadow_windows == [Interval(45, 70)]


def test_guest_flag_is_required_for_compaction():
    """shadow_guest_allowed=False hizmet, bekleme penceresine SOKULMAZ."""
    layout = layout_package([BOYA, MANIKUR])
    assert layout.total_min == 140  # 100 + 40, sirali
    assert layout.saved_min == 0
    assert layout.items[1].placed_in_shadow is False


def test_long_guest_does_not_fit_small_window():
    uzun_misafir = ServiceSpec(
        id=9, name="45 dk misafir",
        active_before_min=45, passive_min=0, active_after_min=0, buffer_min=0,
        shadow_host_allowed=False, shadow_guest_allowed=True, price=100,
    )
    layout = layout_package([BOYA, uzun_misafir])
    # 45 dk, 40 dk'lik pencereye sigmaz -> sirali yerlesir.
    assert layout.items[1].placed_in_shadow is False
    assert layout.total_min == 145


def test_speed_factor_scales_only_active_parts():
    layout = layout_package([BOYA], LayoutOptions(speed_factor=0.9))
    # 30*0.9 = 27 -> 25 (5'e yuvarlanir), 20*0.9 = 18 -> 20
    assert layout.items[0].active_before_min == 25
    # Kimyasal bekleme suresi ustanin hizindan BAGIMSIZDIR.
    assert layout.items[0].passive_min == 40


def test_slower_staff_makes_package_longer():
    normal = layout_package([BOYA])
    yavas = layout_package([BOYA], LayoutOptions(speed_factor=1.1))
    assert yavas.total_min > normal.total_min


def test_duplicate_service_is_laid_out_twice():
    """HATA 2 regresyonu: ayni hizmet iki kez secilebilir.

    Iki kas alma = iki ayri kalem, iki kat sure ve iki kat fiyat.
    """
    layout = layout_package([KAS, KAS])
    assert len(layout.items) == 2
    assert layout.total_min == 30
    assert layout.total_price == 300
    assert [i.offset_min for i in layout.items] == [0, 15]


def test_empty_package():
    layout = layout_package([])
    assert layout.total_min == 0
    assert layout.items == []
