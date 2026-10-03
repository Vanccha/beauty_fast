"""
====================================================================
FIRSAT SAATLERI - Dinamik doluluk bazli indirim
====================================================================

Gecmis doluluk verisinden bir saat diliminin ne kadar "ucuz" oldugunu
hesaplar: o dilimin tarihsel dolulugu ne kadar dusukse indirim o kadar
cazip olur.

1) Bayes daraltmasi (shrinkage)
   Ham doluluk orani az ornekte oynaktir: 2 randevudan 0'i dolduysa
   "doluluk %0" demek yaniltcidir. Gozlem, subenin genel ortalamasina
   dogru cekilir:

       adjusted = (occupancy * n + globalMean * K) / (n + K)

2) Indirim egrisi
       deficit  = max(0, threshold - adjusted) / threshold
       discount = maxDiscount * deficit ** curve

   ``curve > 1`` indirimi yalnizca gercekten olu saatlerde comertlestirir.
   Indirim, salonun belirledigi adima (orn. %5) yuvarlanir.

(``pricing/opportunity.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date as _date
from typing import Sequence


@dataclass(frozen=True)
class OpportunityConfig:
    #: Bu dolulugun UZERI indirimsizdir (0..1)
    threshold: float = 0.55
    #: Uygulanabilecek en yuksek indirim orani (0..1)
    max_discount: float = 0.25
    #: Indirim egrisinin disbukeyligi (>1 = daha secici)
    curve: float = 1.5
    #: Indirimin yuvarlanacagi adim (0.05 = %5)
    step: float = 0.05
    #: Sube geneli ortalama doluluk (Bayes onseli)
    global_mean_occupancy: float = 0.5
    #: Onselin gucu: kac sanal gozleme denk
    prior_strength: float = 8.0


DEFAULT_OPPORTUNITY_CONFIG = OpportunityConfig()


@dataclass(frozen=True)
class OccupancySample:
    weekday: int
    slot_min: int
    #: 0..1 arasi ham doluluk
    occupancy: float
    sample_size: int


@dataclass(frozen=True)
class OpportunityScore:
    weekday: int
    slot_min: int
    raw_occupancy: float
    #: Bayes ile daraltilmis doluluk
    adjusted_occupancy: float
    #: 0..1 - 1 = en olu saat
    opportunity_index: float
    discount_rate: float
    is_opportunity: bool
    label: str


def _clamp01(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return min(1.0, max(0.0, v))


def score_opportunity(
    sample: OccupancySample,
    cfg: OpportunityConfig | None = None,
) -> OpportunityScore:
    cfg = cfg or DEFAULT_OPPORTUNITY_CONFIG

    raw = _clamp01(sample.occupancy)
    n = max(0, sample.sample_size)

    adjusted = _clamp01(
        (raw * n + cfg.global_mean_occupancy * cfg.prior_strength) / (n + cfg.prior_strength)
    )

    deficit = _clamp01((cfg.threshold - adjusted) / cfg.threshold) if cfg.threshold > 0 else 0.0
    opportunity_index = deficit ** cfg.curve

    raw_discount = cfg.max_discount * opportunity_index
    stepped = (raw_discount // cfg.step) * cfg.step if cfg.step > 0 else raw_discount
    discount_rate = round(_clamp01(stepped), 4)

    return OpportunityScore(
        weekday=sample.weekday,
        slot_min=sample.slot_min,
        raw_occupancy=raw,
        adjusted_occupancy=round(adjusted, 4),
        opportunity_index=round(opportunity_index, 4),
        discount_rate=discount_rate,
        is_opportunity=discount_rate > 0,
        label=_label_for(discount_rate),
    )


def _label_for(discount: float) -> str:
    if discount >= 0.2:
        return "Süper fırsat"
    if discount >= 0.1:
        return "Fırsat saati"
    if discount > 0:
        return "Küçük indirim"
    return "Standart"


def score_day(
    weekday: int,
    slot_minutes: Sequence[int],
    samples: Sequence[OccupancySample],
    cfg: OpportunityConfig | None = None,
) -> dict[int, OpportunityScore]:
    """Bir gun icin tum slotlari skorlar.

    Ornek bulunmayan slotlar, onsel ortalamayla (n=0) degerlendirilir.
    """
    cfg = cfg or DEFAULT_OPPORTUNITY_CONFIG
    by_slot = {s.slot_min: s for s in samples if s.weekday == weekday}

    out: dict[int, OpportunityScore] = {}
    for slot_min in slot_minutes:
        sample = by_slot.get(
            slot_min,
            OccupancySample(weekday, slot_min, cfg.global_mean_occupancy, 0),
        )
        out[slot_min] = score_opportunity(sample, cfg)
    return out


def build_occupancy_samples(observations: Sequence[dict]) -> list[OccupancySample]:
    """Gecmis randevulardan doluluk ornekleri.

    occupancy = (o slotta dolu gecen dakika) / (o slotta calisilabilir dakika)
    Her gozlem ``{weekday, slot_min, busy_minutes, capacity_minutes}``.
    """
    acc: dict[tuple[int, int], list[float]] = {}
    for o in observations:
        key = (o["weekday"], o["slot_min"])
        cur = acc.setdefault(key, [0.0, 0.0, 0.0])
        cur[0] += o["busy_minutes"]
        cur[1] += o["capacity_minutes"]
        cur[2] += 1

    return [
        OccupancySample(
            weekday=weekday,
            slot_min=slot_min,
            occupancy=_clamp01(busy / capacity) if capacity > 0 else 0.0,
            sample_size=int(n),
        )
        for (weekday, slot_min), (busy, capacity, n) in acc.items()
    ]


def with_global_mean(cfg: OpportunityConfig, mean: float) -> OpportunityConfig:
    return replace(cfg, global_mean_occupancy=mean)


# ---------------------------------------------------------------------
# SABIT PENCERE INDIRIMI (fiyati belirleyen TEK kural)
# ---------------------------------------------------------------------
# Yukaridaki Bayes/doluluk skoru artik FIYATI etkilemez; yalniz yonetici
# panelindeki "doluluk isi haritasi" icgorusu icin kullanilir.
# Fiyat: hafta ici + erken saat + sabit oran. Slot listesi, randevu
# onayi ve grup randevusu AYNI fonksiyonu cagirir.

#: Gun numaralari JS ile ayni: 0 = Pazar ... 6 = Cumartesi
DEFAULT_DISCOUNT_DAYS: tuple[int, ...] = (1, 2, 3, 4, 5)
DEFAULT_DISCOUNT_RATE = 0.10
DEFAULT_DISCOUNT_CUTOFF_MIN = 12 * 60
DISCOUNT_MIN_RATE = 0.05
DISCOUNT_MAX_RATE = 0.30


@dataclass(frozen=True)
class FixedWindowSettings:
    enabled: bool = True
    rate: float = DEFAULT_DISCOUNT_RATE
    #: Bu dakikadan ONCE baslayan randevulara indirim (esitlik = indirim yok)
    cutoff_min: int = DEFAULT_DISCOUNT_CUTOFF_MIN
    days: tuple[int, ...] = field(default_factory=lambda: DEFAULT_DISCOUNT_DAYS)


DEFAULT_FIXED_WINDOW = FixedWindowSettings()


def parse_discount_days(raw: str | None) -> tuple[int, ...]:
    """'1,2,3,4,5' -> (1, 2, 3, 4, 5). Gecersiz parcalar atlanir."""
    out: set[int] = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit() and 0 <= int(part) <= 6:
            out.add(int(part))
    return tuple(sorted(out))


def format_discount_days(days: Sequence[int]) -> str:
    return ",".join(str(d) for d in sorted({int(d) for d in days}))


def fixed_window_settings_from_salon(salon) -> FixedWindowSettings:
    if salon is None:
        return DEFAULT_FIXED_WINDOW
    return FixedWindowSettings(
        enabled=bool(salon.discount_enabled),
        rate=float(salon.discount_rate),
        cutoff_min=int(salon.discount_cutoff_min),
        days=parse_discount_days(salon.discount_days),
    )


def fixed_window_discount(
    date: str, start_min: int, settings: FixedWindowSettings | None = None
) -> float:
    """Randevu tarihi secili gunlerden biriyse VE baslangic saati kesintiden
    once ise sabit oran, degilse 0 dondurur. ``date``: 'YYYY-MM-DD'."""
    s = settings or DEFAULT_FIXED_WINDOW
    if not s.enabled or s.rate <= 0:
        return 0.0
    try:
        y, m, d = (int(x) for x in date.split("-"))
        js_weekday = (_date(y, m, d).weekday() + 1) % 7
    except (ValueError, AttributeError):
        return 0.0
    if js_weekday not in s.days:
        return 0.0
    if start_min >= s.cutoff_min:
        return 0.0
    return round(_clamp01(s.rate), 4)


def window_label(discount: float) -> str:
    return "Fırsat saati" if discount > 0 else "Standart"
