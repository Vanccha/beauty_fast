"""
====================================================================
MUSTERI SEGMENTASYONU (CRM rozetleri)
====================================================================

Musteri kartindaki rozet uc eksenin kurallı birlesimidir:
  1) Deger        - toplam harcama
  2) Guvenilirlik - gelme orani / risk skoru
  3) Tazelik      - son ziyaretten bu yana gecen gun

Kurallar oncelik sirasiyla degerlendirilir; ilk eslesen kazanir. Boylece
"riskli" etiketi yuksek harcamayi golgelemez ama gizlenmez de: VIP bir
musteri son randevusuna gelmediyse VIP kalir, kartta ayrica risk uyarisi
gosterilir (iki bilgi birbirini ezmez).

(``crm/segmentation.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass

VIP_SPEND_THRESHOLD = 5000
VIP_MIN_SHOW_RATE = 0.85
LOYAL_MIN_VISITS = 6
LOYAL_MAX_DAYS = 60
DORMANT_DAYS = 120
NEW_MAX_VISITS = 2
RISK_SEGMENT_THRESHOLD = 45


@dataclass(frozen=True)
class SegmentResult:
    segment: str
    #: Kartta gosterilecek rozet metni
    badge: str
    #: Renk anahtari (arayuz temasina birakilir)
    tone: str
    #: Gelme orani 0..1
    show_rate: float
    #: Riskli olsa bile ayrica gosterilecek ikincil uyari
    warning: str | None

    def to_dict(self) -> dict:
        return {
            "segment": self.segment,
            "badge": self.badge,
            "tone": self.tone,
            "showRate": round(self.show_rate, 4),
            "warning": self.warning,
        }


def _format_tl(value: float) -> str:
    return f"{round(value):,}".replace(",", ".")


def segment_customer(
    total_spend: float,
    visit_count: int,
    no_show_count: int,
    last_visit_days_ago: int | None,
    risk_score: float,
    last_appointment_no_show: bool,
    tier: str | None = None,
) -> SegmentResult:
    visits = max(0, visit_count)
    no_shows = max(0, no_show_count)
    show_rate = max(0.0, (visits - no_shows) / visits) if visits > 0 else 1.0

    if last_appointment_no_show:
        warning = "Son randevusuna gelmedi"
    elif risk_score >= RISK_SEGMENT_THRESHOLD:
        warning = "Gelmeme riski yüksek"
    else:
        warning = None

    # 1) VIP - yuksek harcama VE guvenilir
    if total_spend >= VIP_SPEND_THRESHOLD and show_rate >= VIP_MIN_SHOW_RATE:
        return SegmentResult(
            "VIP", f"VIP Müşteri – Toplam {_format_tl(total_spend)} TL", "violet", show_rate, warning
        )

    # 2) Riskli - dusuk degerli ve guvenilmez
    if last_appointment_no_show or risk_score >= RISK_SEGMENT_THRESHOLD:
        badge = (
            "Riskli / Son randevuya gelmedi"
            if last_appointment_no_show
            else "Riskli – gelmeme geçmişi var"
        )
        return SegmentResult("RISKLI", badge, "red", show_rate, warning)

    # 3) Uyuyan - uzun suredir yok
    if last_visit_days_ago is not None and last_visit_days_ago >= DORMANT_DAYS:
        return SegmentResult(
            "UYUYAN", f"Uyuyan – {last_visit_days_ago} gündür gelmedi", "amber", show_rate, warning
        )

    # 4) Sadik - duzenli ve taze
    if (
        visits >= LOYAL_MIN_VISITS
        and last_visit_days_ago is not None
        and last_visit_days_ago <= LOYAL_MAX_DAYS
    ):
        return SegmentResult(
            "SADIK",
            f"Sadık – {visits} ziyaret, {_format_tl(total_spend)} TL",
            "emerald",
            show_rate,
            warning,
        )

    # 5) Yeni
    if visits <= NEW_MAX_VISITS:
        badge = "Yeni – ilk randevu" if visits == 0 else f"Yeni – {visits}. ziyaret"
        return SegmentResult("YENI", badge, "sky", show_rate, warning)

    return SegmentResult(
        "STANDART", f"Müşteri – {_format_tl(total_spend)} TL", "slate", show_rate, warning
    )
