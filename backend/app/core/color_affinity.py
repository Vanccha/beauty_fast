"""
====================================================================
RENK PSIKOLOJISI / EGILIM OZETI
====================================================================

Musterinin gecmis islemlerinde sectigi renklerin basit frekans analizi.
Amac falcilik degil, ustaya pratik bir hatirlatma: "bu musteri genelde
nude tonlarda kaliyor".

Renkler once bir "aileye" indirgenir (SICAK / SOGUK / NOTR / KOYU /
CANLI), sonra hem tekil renk hem aile bazinda sayilir. Son islemler daha
agir sayilir (yari-omur 90 gun) - zevk zamanla degisir.

(``crm/color-affinity.ts`` karsiligi.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from ..time_utils import now_local

FAMILY_MAP = {
    "kirmizi": "SICAK", "bordo": "SICAK", "mercan": "SICAK", "turuncu": "SICAK",
    "sarap": "SICAK", "somon": "SICAK", "terracotta": "SICAK",

    "mavi": "SOGUK", "lacivert": "SOGUK", "mor": "SOGUK", "lila": "SOGUK",
    "turkuaz": "SOGUK", "yesil": "SOGUK", "gri": "SOGUK", "gumus": "SOGUK",

    "nude": "NOTR", "bej": "NOTR", "pudra": "NOTR", "krem": "NOTR", "seffaf": "NOTR",
    "french": "NOTR", "beyaz": "NOTR", "kahve": "NOTR", "tarcin": "NOTR",

    "siyah": "KOYU", "antrasit": "KOYU", "koyu-mor": "KOYU", "koyu-yesil": "KOYU",

    "fusya": "CANLI", "neon": "CANLI", "pembe": "CANLI", "altin": "CANLI",
    "simli": "CANLI", "glitter": "CANLI", "sari": "CANLI",
}

FAMILY_LABEL = {
    "SICAK": "sıcak",
    "SOGUK": "soğuk",
    "NOTR": "nötr",
    "KOYU": "koyu",
    "CANLI": "canlı",
    "BILINMIYOR": "belirsiz",
}

COLOR_HALF_LIFE_DAYS = 90

_TR_MAP = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"})


def normalize_color_tag(tag: str | None) -> str:
    text = (tag or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    return text.translate(_TR_MAP)


def family_of(tag: str | None) -> str:
    return FAMILY_MAP.get(normalize_color_tag(tag), "BILINMIYOR")


@dataclass(frozen=True)
class ColorObservation:
    color_tag: str
    created_at: datetime


def analyze_color_affinity(
    observations: Sequence[ColorObservation],
    now: datetime | None = None,
    top_n: int = 3,
) -> dict:
    now = now or now_local()
    valid = [o for o in observations if o.color_tag and o.color_tag.strip()]

    if not valid:
        return {
            "topColors": [],
            "families": [],
            "dominantFamily": "BILINMIYOR",
            "sampleSize": 0,
            "summary": "Henüz renk tercihi kaydı yok.",
        }

    color_weights: dict[str, list[float]] = {}
    family_weights: dict[str, float] = {}
    total_weight = 0.0

    for obs in valid:
        age_days = max(0.0, (now - obs.created_at).total_seconds() / 86400.0)
        w = 0.5 ** (age_days / COLOR_HALF_LIFE_DAYS)

        tag = normalize_color_tag(obs.color_tag)
        cur = color_weights.setdefault(tag, [0.0, 0.0])
        cur[0] += w
        cur[1] += 1

        fam = family_of(tag)
        family_weights[fam] = family_weights.get(fam, 0.0) + w
        total_weight += w

    top_colors = [
        {
            "tag": tag,
            "count": int(count),
            "ratio": round(weight / total_weight, 4),
            "family": family_of(tag),
        }
        for tag, (weight, count) in sorted(
            color_weights.items(), key=lambda kv: (-kv[1][0], -kv[1][1])
        )[:top_n]
    ]

    families = [
        {"family": family, "weight": round(weight, 3), "ratio": round(weight / total_weight, 4)}
        for family, weight in sorted(family_weights.items(), key=lambda kv: -kv[1])
    ]

    dominant = families[0]["family"] if families else "BILINMIYOR"
    dominant_count = sum(1 for o in valid if family_of(o.color_tag) == dominant)
    top_names = ", ".join(c["tag"] for c in top_colors)

    if dominant == "BILINMIYOR":
        summary = f"Son {len(valid)} işlemde tercih edilen renkler: {top_names}."
    else:
        summary = (
            f"Son {len(valid)} işlemin {dominant_count} tanesinde "
            f"{FAMILY_LABEL[dominant]} tonlar tercih edildi ({top_names})."
        )

    return {
        "topColors": top_colors,
        "families": families,
        "dominantFamily": dominant,
        "sampleSize": len(valid),
        "summary": summary,
    }
