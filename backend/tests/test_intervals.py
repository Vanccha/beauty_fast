"""Aralik cebiri ve sweep-line doygunluk testleri."""

from __future__ import annotations

from app.intervals import (
    Interval,
    Usage,
    contained_in_any,
    intersect,
    normalize,
    overlaps,
    saturated_intervals,
    subtract,
)


def test_touching_intervals_do_not_overlap():
    # 10:00-10:30 ile 10:30-11:00 cakismaz (yari acik aralik).
    assert overlaps(Interval(600, 630), Interval(630, 660)) is False
    assert overlaps(Interval(600, 631), Interval(630, 660)) is True


def test_normalize_merges_touching_and_overlapping():
    assert normalize([Interval(600, 630), Interval(630, 660)]) == [Interval(600, 660)]
    assert normalize([Interval(600, 660), Interval(620, 700)]) == [Interval(600, 700)]
    # Gecersiz araliklar atilir.
    assert normalize([Interval(600, 600)]) == []


def test_subtract_splits_window():
    assert subtract([Interval(540, 1200)], [Interval(600, 660)]) == [
        Interval(540, 600),
        Interval(660, 1200),
    ]


def test_intersect():
    assert intersect([Interval(540, 1200)], [Interval(600, 1300)]) == [Interval(600, 1200)]


def test_contained_in_any_rejects_split_fit():
    """110 dakikalik blok, iki ayri 60 dakikalik bosluga BOLUNEREK sigmaz."""
    free = [Interval(540, 600), Interval(600, 660)]
    # normalize edilmemis iki bitisik parca -> tek parca sayilmaz
    assert contained_in_any(Interval(540, 650), free) is False
    # normalize edilince tek parca olur ve sigar
    assert contained_in_any(Interval(540, 650), normalize(free)) is True


def test_saturated_intervals_respects_capacity():
    usages = [
        Usage(Interval(600, 660), 1),
        Usage(Interval(630, 690), 1),
        Usage(Interval(640, 650), 1),
    ]
    # Kapasite 3: yalnizca uc kullanimin cakistigi 640-650 doygundur.
    assert saturated_intervals(usages, 3) == [Interval(640, 650)]
    # Kapasite 2: 630-660 boyunca doygun.
    assert saturated_intervals(usages, 2) == [Interval(630, 660)]


def test_adjacent_usages_do_not_create_fake_saturation():
    usages = [Usage(Interval(600, 660), 1), Usage(Interval(660, 720), 1)]
    assert saturated_intervals(usages, 2) == []
