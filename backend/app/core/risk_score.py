"""
====================================================================
GOLGE RISK SKORU - Salonlar arasi no-show skorlamasi
====================================================================

Sistemi kullanan farkli salonlarin ortak havuzunda, bir telefon
numarasinin randevuya gelmeme gecmisinden gizli bir risk skoru uretir.

--------------------------------------------------------------------
KVKK / veri minimizasyonu
--------------------------------------------------------------------
- Havuzda ham telefon numarasi TUTULMAZ. Anahtar
  HMAC-SHA256(normalize(telefon), PHONE_HASH_SECRET) degeridir.
- Skoru soran salon; diger salonlarin adini, randevu tarihlerini veya
  olay kirilimini GOREMEZ.
- Donen ``RiskAssessment`` nesnesi bilerek dardir; ``salon_id`` gibi
  alanlar bu tipte hic yoktur - sizdirilmasi mumkun degildir.
- En az ``MIN_EVENTS_TO_SHOW`` olay yoksa etiket ``YETERSIZ_VERI``
  doner; tek bir olaya dayanarak musteri damgalanmaz.

--------------------------------------------------------------------
Zaman agirlikli (recency-weighted) hesap
--------------------------------------------------------------------
    w(t) = 0.5 ** (gunFarki / HALF_LIFE_DAYS)

HALF_LIFE_DAYS = 60 -> 60 gun onceki bir olay bugunkunun yarisi kadar
etkilidir; davranisini duzelten musterinin skoru zamanla iyilesir.

Az veride Laplace duzeltmesi:

    oran = (Sum w_noshow + ALPHA) / (Sum w_hepsi + ALPHA + BETA)

ALPHA=1, BETA=2. (BETA=4 ile "son 4 randevunun 2'sine gelmemis" numara
ORTA'da kaliyordu; on odeme karari icin fazla toleransliydi.)

(``risk/risk-score.ts`` karsiligi - DB sarmalayicilari
``app/services/risk.py`` icindedir.)
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence

from ..config import config
from ..time_utils import now_local

#: Agirligin yariya dustugu gun sayisi.
HALF_LIFE_DAYS = 60
#: Gec iptal, gelmemenin yarisi kadar agir sayilir.
LATE_CANCEL_WEIGHT = 0.5
ALPHA = 1.0
BETA = 2.0
MIN_EVENTS_TO_SHOW = 3
#: Varsayilan degerlendirme penceresi.
DEFAULT_WINDOW_MONTHS = 6

RISK_THRESHOLDS = {"medium": 20, "high": 45}

RiskOutcome = Literal["COMPLETED", "NO_SHOW", "LATE_CANCEL"]
RiskLabel = Literal["DUSUK", "ORTA", "YUKSEK", "YETERSIZ_VERI"]


@dataclass(frozen=True)
class RiskEventInput:
    outcome: str
    occurred_at: datetime


@dataclass(frozen=True)
class RiskAssessment:
    """Salonlara donen TEK veri yapisi - kaynak salon bilgisi icermez."""

    score: int
    label: str
    #: Pencere icindeki toplam randevu sayisi (toplulastirilmis)
    total_appointments: int
    #: Ham (agirliksiz) gelmeme orani, 0..1
    no_show_rate: float
    window_months: int
    message: str

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "label": self.label,
            "totalAppointments": self.total_appointments,
            "noShowRate": self.no_show_rate,
            "windowMonths": self.window_months,
            "message": self.message,
        }


def normalize_phone(phone: str | None) -> str:
    """Telefonu 10 haneye normalize eder: +90 555 111 22 33 -> 5551112233."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) > 10 else digits


def hash_phone(phone: str, secret: str | None = None) -> str:
    """Havuz anahtari. Tek yonludur; ham numara asla saklanmaz."""
    key = (secret or config.phone_hash_secret).encode("utf-8")
    return hmac.new(key, normalize_phone(phone).encode("utf-8"), hashlib.sha256).hexdigest()


def _weight_for(occurred_at: datetime, now: datetime) -> float:
    age_days = max(0.0, (now - occurred_at).total_seconds() / 86400.0)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def label_for(score: float, event_count: int) -> str:
    if event_count < MIN_EVENTS_TO_SHOW:
        return "YETERSIZ_VERI"
    if score >= RISK_THRESHOLDS["high"]:
        return "YUKSEK"
    if score >= RISK_THRESHOLDS["medium"]:
        return "ORTA"
    return "DUSUK"


def _subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 - months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return value.replace(year=year, month=month, day=day)


def compute_risk_score(
    events: Sequence[RiskEventInput],
    now: datetime | None = None,
    window_months: int = DEFAULT_WINDOW_MONTHS,
) -> RiskAssessment:
    """Saf skor hesabi - veritabani gerektirmez, birim testi kolaydir."""
    now = now or now_local()
    window_start = _subtract_months(now, window_months)

    in_window = [e for e in events if window_start <= e.occurred_at <= now]

    weighted_bad = 0.0
    weighted_all = 0.0
    raw_bad = 0.0

    for event in in_window:
        w = _weight_for(event.occurred_at, now)
        weighted_all += w
        if event.outcome == "NO_SHOW":
            weighted_bad += w
            raw_bad += 1
        elif event.outcome == "LATE_CANCEL":
            weighted_bad += w * LATE_CANCEL_WEIGHT
            raw_bad += LATE_CANCEL_WEIGHT

    smoothed = (weighted_bad + ALPHA) / (weighted_all + ALPHA + BETA)
    score = int(round(min(100.0, max(0.0, smoothed * 100))))

    total = len(in_window)
    no_show_rate = raw_bad / total if total > 0 else 0.0
    label = label_for(score, total)

    return RiskAssessment(
        score=score,
        label=label,
        total_appointments=total,
        no_show_rate=round(no_show_rate, 4),
        window_months=window_months,
        message=_build_message(label, no_show_rate, window_months),
    )


def _build_message(label: str, no_show_rate: float, window_months: int) -> str:
    if label == "YETERSIZ_VERI":
        return "Bu numara için yeterli geçmiş veri yok."
    pct = round(no_show_rate * 100)
    base = f"Bu numara son {window_months} ayda toplam randevularının %{pct}'ine gelmedi."
    if label == "YUKSEK":
        return f"{base} Ön ödeme istemeyi değerlendirin."
    if label == "ORTA":
        return f"{base} Randevu öncesi teyit önerilir."
    return base
