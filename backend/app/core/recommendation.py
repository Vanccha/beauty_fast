"""
====================================================================
HIZMET ONERI SIRALAMASI
====================================================================

Hizmetleri musteriye hangi sirayla gosterecegimizi belirler. Amac
yalnizca "populer olani one almak" degil; TAKVIM SAGLIGINI korumak: bir
hizmet cok talep gorse bile, secildigi anda takvimi parcalayip
kullanilamaz bosluklar birakiyorsa veya darbogaz bir cihazi kilitliyorsa
oneri sirasinda geriye duser.

    score = W.fit           * fit
          + W.popularity    * popularity
          + W.reliability   * reliability
          + W.margin        * margin
          - W.contention    * contention
          - W.fragmentation * fragmentation

(``scheduling/recommendation.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

DEFAULT_WEIGHTS = {
    "fit": 0.30,
    "popularity": 0.22,
    "reliability": 0.15,
    "margin": 0.13,
    "contention": 0.12,
    "fragmentation": 0.08,
}

#: Kullanilamayacak kadar kisa sayilan bosluk esigi (dk).
DEAD_GAP_THRESHOLD_MIN = 30


@dataclass(frozen=True)
class ServiceStat:
    service_id: int
    name: str
    #: Son donemdeki rezervasyon sayisi
    bookings: int
    #: Gelinmeyen randevu sayisi
    no_shows: int
    #: Hizmetin ucretlendirilebilir suresi (dk)
    duration_min: int
    price: float
    #: Ihtiyac duydugu kaynaklarin ortalama dolulugu, 0..1
    resource_contention: float
    #: Hizmet yerlestirildiginde geride kalan olu bosluk (dk)
    avg_leftover_gap_min: float
    #: Zamanlama motorunun bu tarih icin urettigi uygun slot sayisi
    available_slots: int
    #: Zamanlama motorunun taradigi toplam baslangic sayisi
    scanned_starts: int


def _clamp01(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, v))


def rank_services(stats: Sequence[ServiceStat], weights: dict | None = None) -> list[dict]:
    W = {**DEFAULT_WEIGHTS, **(weights or {})}
    if not stats:
        return []

    max_bookings = max([1] + [s.bookings for s in stats])
    max_margin = max(
        [0.0001] + [(s.price / s.duration_min) if s.duration_min > 0 else 0 for s in stats]
    )

    ranked: list[dict] = []
    for s in stats:
        fit = _clamp01(s.available_slots / s.scanned_starts) if s.scanned_starts > 0 else 0.0
        popularity = _clamp01(s.bookings / max_bookings)
        # Veri yoksa notr-iyimser.
        reliability = _clamp01(1 - s.no_shows / s.bookings) if s.bookings > 0 else 0.8
        margin_per_min = (s.price / s.duration_min) if s.duration_min > 0 else 0.0
        margin = _clamp01(margin_per_min / max_margin)
        contention = _clamp01(s.resource_contention)
        fragmentation = _clamp01(s.avg_leftover_gap_min / DEAD_GAP_THRESHOLD_MIN)

        score = (
            W["fit"] * fit
            + W["popularity"] * popularity
            + W["reliability"] * reliability
            + W["margin"] * margin
            - W["contention"] * contention
            - W["fragmentation"] * fragmentation
        )

        ranked.append(
            {
                "serviceId": s.service_id,
                "name": s.name,
                "score": round(score, 4),
                "components": {
                    "fit": fit,
                    "popularity": popularity,
                    "reliability": reliability,
                    "margin": margin,
                    "contention": contention,
                    "fragmentation": fragmentation,
                },
                "reason": _explain(fit, popularity, contention, fragmentation),
            }
        )

    ranked.sort(key=lambda r: (-r["score"], r["serviceId"]))
    return ranked


def _explain(fit: float, popularity: float, contention: float, fragmentation: float) -> str:
    if fit < 0.1:
        return "Bu tarihte neredeyse hiç uygun saat yok"
    if contention > 0.7:
        return "Gerekli cihaz yoğun — alternatif gün önerilir"
    if fragmentation > 0.7:
        return "Takvimde kullanılamayan boşluk bırakıyor"
    if popularity > 0.8 and fit > 0.4:
        return "Popüler ve bu tarihte bol seçenekli"
    if fit > 0.6:
        return "Bu tarihte rahat yerleşiyor"
    return "Uygun"


def suggest_shadow_fillers(
    shadow_windows_min: Sequence[float],
    candidates: Sequence[dict],
) -> list[dict]:
    """Paket secildikten sonra kalan golge pencerelerine sigan ek hizmetler.

    Musteriye "beklerken kaslarinizi da alabiliriz" tarzi upsell icin.
    Her aday: ``{serviceId, name, totalMin, price, shadowGuestAllowed}``.
    """
    largest = max(shadow_windows_min) if shadow_windows_min else 0
    if largest <= 0:
        return []

    fitting = [
        c for c in candidates if c["shadowGuestAllowed"] and c["totalMin"] <= largest
    ]
    fitting.sort(key=lambda c: (-c["price"], c["totalMin"]))

    return [
        {
            "serviceId": c["serviceId"],
            "name": c["name"],
            "price": c["price"],
            "fitsWindowMin": largest,
        }
        for c in fitting
    ]
