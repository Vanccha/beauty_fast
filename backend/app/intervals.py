"""Aralik cebiri - zamanlama motorunun matematiksel tabani.

Tum araliklar **yari acik**tir: [start, end). Yani 10:00-10:30 ile
10:30-11:00 cakismaz. Birimler "gun ici dakika"dir (09:30 -> 570).

Bu modul tamamen saftir (I/O yok, ORM yok) - birim testi kolaydir.
(``src/lib/intervals.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, NamedTuple, Sequence


class Interval(NamedTuple):
    start: float
    end: float


def iv(start: float, end: float) -> Interval:
    return Interval(start, end)


def is_valid(i: Interval) -> bool:
    return i.end > i.start


def length(i: Interval) -> float:
    return max(0.0, i.end - i.start)


def total_length(items: Iterable[Interval]) -> float:
    return sum(length(i) for i in items)


def overlaps(a: Interval, b: Interval) -> bool:
    """Kesisiyor mu? *Dokunma* cakisma degildir."""
    return a.start < b.end and b.start < a.end


def contains(outer: Interval, inner: Interval) -> bool:
    return inner.start >= outer.start and inner.end <= outer.end


def shift(items: Sequence[Interval], delta: float) -> list[Interval]:
    return [Interval(i.start + delta, i.end + delta) for i in items]


def normalize(items: Sequence[Interval]) -> list[Interval]:
    """Siralar, gecersizleri atar, bitisik/cakisanlari birlestirir."""
    valid = sorted((i for i in items if is_valid(i)), key=lambda i: (i.start, i.end))
    out: list[list[float]] = []
    for cur in valid:
        if out and cur.start <= out[-1][1]:
            # Bitisik (cur.start == last.end) olanlar da birlesir.
            out[-1][1] = max(out[-1][1], cur.end)
        else:
            out.append([cur.start, cur.end])
    return [Interval(s, e) for s, e in out]


def subtract(base: Sequence[Interval], cuts: Sequence[Interval]) -> list[Interval]:
    """Kume farki: base eksi cuts. Her iki taraf da normalize edilir."""
    result = normalize(base)
    for cut in normalize(cuts):
        nxt: list[Interval] = []
        for piece in result:
            if not overlaps(piece, cut):
                nxt.append(piece)
                continue
            if piece.start < cut.start:
                nxt.append(Interval(piece.start, cut.start))
            if cut.end < piece.end:
                nxt.append(Interval(cut.end, piece.end))
        result = nxt
    return result


def intersect(a: Sequence[Interval], b: Sequence[Interval]) -> list[Interval]:
    an, bn = normalize(a), normalize(b)
    out: list[Interval] = []
    i = j = 0
    while i < len(an) and j < len(bn):
        start = max(an[i].start, bn[j].start)
        end = min(an[i].end, bn[j].end)
        if end > start:
            out.append(Interval(start, end))
        if an[i].end < bn[j].end:
            i += 1
        else:
            j += 1
    return out


def contained_in_any(inner: Interval, free: Sequence[Interval]) -> bool:
    """``inner`` TEK bir bosluğun icinde tamamen yer aliyor mu?

    "Kesintisiz blok" sartinin uygulandigi yer burasidir: iki ayri bosluğa
    bolunerek sigmasi kabul edilmez.
    """
    return any(contains(f, inner) for f in free)


def overlaps_any(probe: Interval, items: Sequence[Interval]) -> bool:
    return any(overlaps(probe, i) for i in items)


def find_container(probe: Interval, items: Sequence[Interval]) -> Interval | None:
    for i in items:
        if contains(i, probe):
            return i
    return None


@dataclass(frozen=True)
class Usage:
    interval: Interval
    quantity: float


def saturated_intervals(usages: Sequence[Usage], capacity: float) -> list[Interval]:
    """Kapasiteli kaynaklar icin "doygun" araliklar (sweep-line, O(n log n)).

    Eszamanli kullanim ``capacity``'ye ulasmis, yani yeni is alamayacak
    zaman dilimlerini doner.
    """
    if capacity <= 0:
        return normalize([u.interval for u in usages]) if usages else []

    events: list[tuple[float, float]] = []
    for u in usages:
        if not is_valid(u.interval) or u.quantity <= 0:
            continue
        events.append((u.interval.start, u.quantity))
        events.append((u.interval.end, -u.quantity))
    if not events:
        return []

    # Ayni noktada once cikislar islenir ki bitisik randevular yapay
    # doygunluk yaratmasin.
    events.sort(key=lambda e: (e[0], e[1]))

    out: list[Interval] = []
    load = 0.0
    sat_start: float | None = None

    k = 0
    while k < len(events):
        at = events[k][0]
        while k < len(events) and events[k][0] == at:
            load += events[k][1]
            k += 1
        if load >= capacity and sat_start is None:
            sat_start = at
        elif load < capacity and sat_start is not None:
            out.append(Interval(sat_start, at))
            sat_start = None

    return normalize(out)
