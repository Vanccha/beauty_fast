"""
====================================================================
SADAKAT PUANI MOTORU
====================================================================

"Her harcamaya 1 puan" yerine salonun gercek ekonomisini yansitan
carpanli bir formul:

    puan = BASE_RATE * tutar
         * frequency_multiplier(son ziyaretten bu yana gun)
         * opportunity_multiplier(firsat saati indirimi)
         * tier_multiplier(seviye)

BASE_RATE = 1 puan / 10 TL  -> 1 puan yaklasik 0.10 TL degerindedir.

frequency_multiplier (ziyaret sikligi)
    < 30 gun : 1.25 | < 60: 1.10 | < 120: 1.00 | >= 120: 0.90
    Ilk ziyarette (gecmis yok) 1.00.

opportunity_multiplier (olu saat tesviki)
    1 + OPPORTUNITY_GAIN * (indirim / MAX_DISCOUNT), tavan 1.5

tier_multiplier: BRONZ 1.00 / GUMUS 1.05 / ALTIN 1.12 / VIP 1.20

DECAY (puan erimesi)
    kalan = puan * 0.5 ** ((atilGun - GRACE_DAYS) / DECAY_HALF_LIFE_DAYS)
    Ilk 90 gun erime yoktur; sonrasinda her 6 ayda yarilanir. Erime
    defterde negatif "DECAY" kaydi olarak gorunur - bakiye asla sessizce
    degismez.

(``loyalty/loyalty.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_RATE = 0.1  # 1 puan / 10 TL
OPPORTUNITY_GAIN = 0.5
MAX_DISCOUNT_REFERENCE = 0.25
OPPORTUNITY_CAP = 1.5
GRACE_DAYS = 90
DECAY_HALF_LIFE_DAYS = 180

TIER_THRESHOLDS = [
    {"tier": "BRONZ", "min": 0, "multiplier": 1.0, "label": "Bronz"},
    {"tier": "GUMUS", "min": 500, "multiplier": 1.05, "label": "Gümüş"},
    {"tier": "ALTIN", "min": 1500, "multiplier": 1.12, "label": "Altın"},
    {"tier": "VIP", "min": 4000, "multiplier": 1.2, "label": "VIP"},
]


def tier_for(points: float) -> str:
    current = "BRONZ"
    for t in TIER_THRESHOLDS:
        if points >= t["min"]:
            current = t["tier"]
    return current


def tier_multiplier(tier: str) -> float:
    for t in TIER_THRESHOLDS:
        if t["tier"] == tier:
            return t["multiplier"]
    return 1.0


def tier_label(tier: str) -> str:
    for t in TIER_THRESHOLDS:
        if t["tier"] == tier:
            return t["label"]
    return "Bronz"


def progress_to_next_tier(points: float) -> dict:
    """Bir sonraki seviyeye kalan puan - engagement gostergesi icin."""
    current = tier_for(points)
    index = next(i for i, t in enumerate(TIER_THRESHOLDS) if t["tier"] == current)
    nxt = TIER_THRESHOLDS[index + 1] if index + 1 < len(TIER_THRESHOLDS) else None

    if nxt is None:
        return {
            "current": current,
            "next": None,
            "pointsToNext": 0,
            "ratio": 1,
            "message": "En üst seviyedesiniz — VIP ayrıcalıkları aktif.",
        }

    floor = TIER_THRESHOLDS[index]["min"]
    span = nxt["min"] - floor
    points_to_next = max(0, int(-(-(nxt["min"] - points) // 1)))  # ceil
    ratio = min(1.0, max(0.0, (points - floor) / span)) if span > 0 else 1.0

    return {
        "current": current,
        "next": nxt["tier"],
        "pointsToNext": points_to_next,
        "ratio": round(ratio, 4),
        "message": f"{nxt['label']} seviyesine {points_to_next} puan kaldı.",
    }


def frequency_multiplier(days_since_last_visit: int | None) -> float:
    if days_since_last_visit is None:
        return 1.0
    if days_since_last_visit < 30:
        return 1.25
    if days_since_last_visit < 60:
        return 1.1
    if days_since_last_visit < 120:
        return 1.0
    return 0.9


def opportunity_multiplier(discount_rate: float) -> float:
    if not discount_rate or discount_rate <= 0:
        return 1.0
    gain = OPPORTUNITY_GAIN * (discount_rate / MAX_DISCOUNT_REFERENCE)
    return min(OPPORTUNITY_CAP, 1 + gain)


@dataclass(frozen=True)
class EarnResult:
    points: float
    breakdown: dict
    explanation: str


def calculate_earned_points(
    amount: float,
    days_since_last_visit: int | None,
    current_tier: str,
    opportunity_discount_rate: float = 0.0,
) -> EarnResult:
    amount = max(0.0, amount)
    base = amount * BASE_RATE
    freq = frequency_multiplier(days_since_last_visit)
    opp = opportunity_multiplier(opportunity_discount_rate)
    tier = tier_multiplier(current_tier)

    points = round(base * freq * opp * tier, 2)

    notes: list[str] = []
    if freq > 1:
        notes.append(f"sık ziyaret x{freq}")
    if freq < 1:
        notes.append(f"uzun aradan sonra x{freq}")
    if opp > 1:
        notes.append(f"fırsat saati x{opp:.2f}")
    if tier > 1:
        notes.append(f"{tier_label(current_tier)} seviye x{tier}")

    return EarnResult(
        points=points,
        breakdown={
            "base": round(base, 2),
            "frequency": freq,
            "opportunity": opp,
            "tier": tier,
        },
        explanation=f"{points} puan ({', '.join(notes)})" if notes else f"{points} puan",
    )


def calculate_decay(points: float, days_idle: float) -> dict:
    """Atil kalan puanin erimesi. ``GRACE_DAYS`` icinde erime yoktur."""
    if points <= 0 or days_idle <= GRACE_DAYS:
        return {"remaining": points, "decayAmount": 0, "halfLives": 0}
    effective_days = days_idle - GRACE_DAYS
    half_lives = effective_days / DECAY_HALF_LIFE_DAYS
    remaining = round(points * (0.5 ** half_lives), 2)
    return {
        "remaining": remaining,
        "decayAmount": round(remaining - points, 2),
        "halfLives": round(half_lives, 3),
    }


def points_to_currency(points: float) -> float:
    """Puanin TL karsiligi (1 puan = 0.10 TL)."""
    return round(points * 0.1, 2)
