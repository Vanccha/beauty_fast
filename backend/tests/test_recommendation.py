"""Hizmet oneri siralamasi ve golge upsell."""

from __future__ import annotations

from app.core.recommendation import ServiceStat, rank_services, suggest_shadow_fillers


def stat(**kwargs) -> ServiceStat:
    base = dict(
        service_id=1, name="Hizmet", bookings=50, no_shows=2, duration_min=60, price=600,
        resource_contention=0.0, avg_leftover_gap_min=0, available_slots=40,
        scanned_starts=44,
    )
    base.update(kwargs)
    return ServiceStat(**base)


def test_service_without_slots_falls_behind():
    ranked = rank_services(
        [
            stat(service_id=1, name="Dolu gün", available_slots=0),
            stat(service_id=2, name="Boş gün", available_slots=40),
        ]
    )
    assert ranked[0]["serviceId"] == 2
    assert ranked[-1]["reason"] == "Bu tarihte neredeyse hiç uygun saat yok"


def test_resource_contention_is_a_penalty():
    ranked = rank_services(
        [
            stat(service_id=1, name="Darboğaz cihaz", resource_contention=1.0),
            stat(service_id=2, name="Cihaz gerekmez", resource_contention=0.0),
        ]
    )
    assert ranked[0]["serviceId"] == 2


def test_fragmentation_is_a_penalty():
    ranked = rank_services(
        [
            stat(service_id=1, name="Izgaraya oturmaz", avg_leftover_gap_min=25),
            stat(service_id=2, name="Tam oturur", avg_leftover_gap_min=0),
        ]
    )
    assert ranked[0]["serviceId"] == 2


def test_no_show_history_lowers_reliability():
    ranked = rank_services(
        [
            stat(service_id=1, name="Gelinmiyor", bookings=50, no_shows=25),
            stat(service_id=2, name="Güvenilir", bookings=50, no_shows=0),
        ]
    )
    assert ranked[0]["serviceId"] == 2


def test_empty_stats():
    assert rank_services([]) == []


def test_shadow_upsell_only_fitting_guests():
    candidates = [
        {"serviceId": 1, "name": "Kaş Alma", "totalMin": 15, "price": 150, "shadowGuestAllowed": True},
        {"serviceId": 2, "name": "Bıyık Ağdası", "totalMin": 10, "price": 100, "shadowGuestAllowed": True},
        {"serviceId": 3, "name": "Kirpik Lifting", "totalMin": 45, "price": 700, "shadowGuestAllowed": True},
        {"serviceId": 4, "name": "Manikür", "totalMin": 20, "price": 350, "shadowGuestAllowed": False},
    ]
    result = suggest_shadow_fillers([40], candidates)

    ids = [r["serviceId"] for r in result]
    assert 3 not in ids  # 45 dk, 40 dk'lik pencereye sigmaz
    assert 4 not in ids  # misafir olamaz
    # Pahali olan once onerilir (salon geliri)
    assert ids == [1, 2]
    assert result[0]["fitsWindowMin"] == 40


def test_no_shadow_window_means_no_upsell():
    assert suggest_shadow_fillers([], [{"serviceId": 1, "name": "x", "totalMin": 5, "price": 1, "shadowGuestAllowed": True}]) == []
