"""
====================================================================
KAPORA (DEPOSIT) - havale ile alinan, salonun elle onayladigi on odeme
====================================================================

Odeme sistemi YOKTUR: musteri IBAN'a havale eder, yonetici "Kapora odendi"
der. Sistem yalnizca izler ve hatirlatir.

Durum makinesi (``appointment.status`` + ``appointment.deposit_status``)::

    kapora kapali / istenmedi : CONFIRMED + NONE (deposit_amount = NULL)

    online (veya panelde "Kapora iste") : PENDING + AWAITING   (slot DOLU)
        |-- yonetici "Kapora odendi" ------> CONFIRMED + PAID
        |-- iptal (musteri / personel) -----> CANCELLED + NONE   (kapora yok)
        `-- yonetici onaylar/tamamlar -------> (kapora feragat) NONE, amount NULL

    CONFIRMED + PAID
        |-- iptal (>= 60 dk kala, musteri) --> CANCELLED + REFUND_DUE (48 saat)
        |-- iptal (personel, varsayilan) -----> CANCELLED + REFUND_DUE (48 saat)
        |-- iptal (personel, "kapora yanar") -> CANCELLED + FORFEITED
        |-- gelmedi (NO_SHOW) ----------------> NO_SHOW   + FORFEITED
        `-- tamamlandi ------------------------> COMPLETED + PAID

    REFUND_DUE --"Kapora iade edildi"--> REFUNDED   (sistem para GONDERMEZ)

Musteri randevuya 60 dakikadan az kala IPTAL EDEMEZ (kapora olsun olmasin).
Personel her zaman iptal edebilir.

Mesajlar ``booking_confirmation.queue_confirmation`` ile kuyruga yazilir
(``dedupe_key`` benzersiz): ``deposit:<id>`` / ``deposit-group:<grup>``,
``deposit-paid:<id>`` / ``deposit-paid-group:<grup>``, ``deposit-refund:<id>``.
Gecikme ve iade hatirlatmalari ``deposit_watch`` ile (Web Push).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ..config import config
from ..errors import AppError, VersionConflictError
from ..models import Appointment, AppointmentItem, Customer, Salon, ScheduledNotification
from ..time_utils import format_date_tr, minutes_to_label, now_local, to_datetime
from .booking_confirmation import queue_confirmation

# --- Sabitler -----------------------------------------------------------

AWAITING = "AWAITING"
PAID = "PAID"
NONE = "NONE"
REFUND_DUE = "REFUND_DUE"
REFUNDED = "REFUNDED"
FORFEITED = "FORFEITED"

#: Musteri bu kadar dakikadan az kala iptal edemez.
CANCEL_MIN_MINUTES = 60
#: Iptalden sonra iadenin yapilmasi gereken sure.
REFUND_HOURS = 48

DEPOSIT_PREFIX = "deposit:"
DEPOSIT_GROUP_PREFIX = "deposit-group:"
PAID_PREFIX = "deposit-paid:"
PAID_GROUP_PREFIX = "deposit-paid-group:"
REFUND_PREFIX = "deposit-refund:"

POLICY_TEXT = (
    "Randevuya 1 saatten az kala iptal yapılamaz; bu durumda kapora iade edilmez. "
    "Daha önce yapılan iptallerde kapora 48 saat içinde tarafınıza gönderilir."
)
CANCEL_TOO_LATE_MESSAGE = (
    "Randevuya 1 saatten az kaldığı için iptal edilemez. Kapora iade edilmez."
)
REFUND_LINE = "Kaporanız 48 saat içinde tarafınıza gönderilecektir."

DEFAULT_TEMPLATE = (
    "Merhaba {ad}, {tarih} saat {saat} - {hizmetler} randevunuz alındı. "
    "Randevunuzun kesinleşmesi için {kapora} kapora gerekmektedir.\n"
    "IBAN: {iban}\n"
    "Alıcı: {alici}\n"
    "Açıklama: {aciklama}\n"
    "Kapora ulaştığında randevunuz onaylanacak ve size bilgi verilecektir.\n"
    "Randevuya 1 saatten az kala iptal yapılamaz ve kapora iade edilmez."
)
PLACEHOLDERS = {
    "{ad}": "Müşterinin adı",
    "{tarih}": "Randevu tarihi",
    "{saat}": "Randevu saati",
    "{hizmetler}": "Hizmetler",
    "{tutar}": "Randevu tutarı",
    "{kapora}": "Kapora tutarı",
    "{iban}": "IBAN",
    "{alici}": "Hesap sahibi",
    "{banka}": "Banka (boşsa satır atılır)",
    "{aciklama}": "Havale açıklaması (R1234 Ayşe Y.)",
}
MAX_MESSAGE_LENGTH = 1000

PAID_TEMPLATE = (
    "Merhaba {ad}, kaporanız ulaştı. {tarih} saat {saat} randevunuz kesinleşti. Görüşmek üzere!"
)
UNPAID_CANCEL_TEMPLATE = (
    "Merhaba {ad}, {tarih} saat {saat} randevunuz için kapora yatırılmadığından "
    "randevunuz iptal edilmiştir. Yeni randevu için: {site}/randevu"
)
REFUNDED_TEMPLATE = "Merhaba {ad}, {kapora} tutarındaki kaporanız iade edilmiştir."


# ---------------------------------------------------------------------
# IBAN
# ---------------------------------------------------------------------


def normalize_iban(raw: str | None) -> str:
    return re.sub(r"\s+", "", raw or "").upper()


def format_iban(raw: str | None) -> str:
    iban = normalize_iban(raw)
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def _mod97(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97


def validate_iban(raw: str | None) -> str:
    """Bosluksuz buyuk harf IBAN doner; gecersizse ``ValueError`` (Turkce mesaj).

    TR: 26 karakter, ``TR`` + 24 rakam (+ mod-97). Diger ulkeler: genel
    bicim (2 harf + 2 rakam + 11-30 alfasayisal) ve mod-97."""
    iban = normalize_iban(raw)
    if not iban:
        raise ValueError("IBAN boş olamaz.")
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        raise ValueError("IBAN biçimi geçersiz.")
    if iban.startswith("TR") and not re.fullmatch(r"TR\d{24}", iban):
        raise ValueError("Türkiye IBAN'ı TR ile başlayan 26 karakter olmalıdır (TR + 24 rakam).")
    if _mod97(iban) != 1:
        raise ValueError("IBAN doğrulama basamakları hatalı; lütfen kontrol edin.")
    return iban


# ---------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class DepositSettings:
    enabled: bool
    percent: int
    min_amount: int
    iban: str
    account_name: str
    bank_name: str
    deadline_minutes: int
    message: str | None

    @property
    def template(self) -> str:
        return (self.message or "").strip() or DEFAULT_TEMPLATE


def settings_of(salon: Salon | None) -> DepositSettings:
    if salon is None:
        return DepositSettings(False, 20, 100, "", "", "", 60, None)
    return DepositSettings(
        enabled=bool(salon.deposit_enabled),
        percent=salon.deposit_percent,
        min_amount=salon.deposit_min_amount,
        iban=salon.deposit_iban or "",
        account_name=salon.deposit_account_name or "",
        bank_name=salon.deposit_bank_name or "",
        deadline_minutes=salon.deposit_deadline_minutes,
        message=salon.deposit_message,
    )


def load_settings(db: Session) -> DepositSettings:
    return settings_of(db.scalar(select(Salon).order_by(Salon.id).limit(1)))


def compute_deposit(price: float, percent: int, min_amount: int) -> int:
    """kapora = max(fiyat * yuzde, alt sinir); asla fiyati gecmez; tam TL.

    Fiyat 0 (veya negatif) ise 0 doner (kapora istenmez)."""
    if price <= 0:
        return 0
    raw = max(price * percent / 100.0, float(min_amount))
    amount = int(math.floor(raw + 0.5))
    cap = int(math.floor(price + 1e-9))
    if amount > price:
        amount = cap
    return max(0, amount)


def deposit_for_price(settings: DepositSettings, price: float) -> int | None:
    """Kapora acik ve tutar > 0 ise kapora tutari, aksi halde None."""
    if not settings.enabled:
        return None
    amount = compute_deposit(price, settings.percent, settings.min_amount)
    return amount if amount > 0 else None


def format_tl(amount: float | None) -> str:
    value = float(amount or 0)
    if abs(value - round(value)) < 0.005:
        return f"{int(round(value)):,}".replace(",", ".") + " TL"
    text = f"{value:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


# ---------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------


def _reachable(customer: Customer | None) -> bool:
    return bool(customer and customer.anonymized_at is None and customer.phone)


def payer_id_of(appointment: Appointment) -> int:
    """Kaporayi yatiran: randevuyu alan (baskasi adinaysa alan, degilse sahibi)."""
    return appointment.booked_by_customer_id or appointment.customer_id


def _short_name(customer: Customer) -> str:
    last = (customer.last_name or "").strip()
    return f"{customer.first_name} {last[0].upper()}." if last else customer.first_name


def group_members(db: Session, appointment: Appointment) -> list[Appointment]:
    """Ayni grubun (ayni alanin) randevulari; grup degilse yalniz kendisi."""
    if not appointment.booking_group_id:
        return [appointment]
    rows = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
        )
        .where(
            Appointment.booking_group_id == appointment.booking_group_id,
            Appointment.booked_by_customer_id == appointment.booked_by_customer_id,
        )
        .order_by(Appointment.start_min, Appointment.id)
    ).all()
    return list(rows) or [appointment]


def payment_reference(db: Session, appointment: Appointment, members: list[Appointment] | None = None) -> str:
    """Havale aciklamasi: "R1234 Ayşe Y." (grup: "R12-13 Ayşe Y.")."""
    members = members or group_members(db, appointment)
    ids = "-".join(str(m.id) for m in sorted(members, key=lambda m: m.id))
    payer = db.get(Customer, payer_id_of(appointment))
    name = _short_name(payer) if payer else ""
    return f"R{ids} {name}".strip()


def _services_of(a: Appointment) -> str:
    return ", ".join(i.service.name for i in a.items if i.service is not None)


def render_template(template: str, values: dict[str, str]) -> str:
    """Yer tutucular doldurulur; degeri bos olan bir yer tutucuyu iceren satir atilir."""
    lines = []
    for line in template.split("\n"):
        if any(key in line and not value for key, value in values.items()):
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def _values(
    settings: DepositSettings,
    name: str,
    date: str,
    start_min: int,
    services: str,
    total: float,
    deposit: float,
    reference: str,
) -> dict[str, str]:
    return {
        "{ad}": name,
        "{tarih}": format_date_tr(date),
        "{saat}": minutes_to_label(start_min),
        "{hizmetler}": services,
        "{tutar}": format_tl(total),
        "{kapora}": format_tl(deposit),
        "{iban}": format_iban(settings.iban),
        "{alici}": settings.account_name,
        "{banka}": settings.bank_name,
        "{aciklama}": reference,
    }


def render_preview(settings: DepositSettings) -> str:
    """Yoneticiye gosterilen ornek metin (ornek verilerle)."""
    return render_template(
        settings.template,
        _values(settings, "Ayşe", "2026-10-10", 14 * 60, "Manikür", 500, 100, "R1234 Ayşe Y."),
    )


def build_request_message(
    db: Session, settings: DepositSettings, appointments: list[Appointment], payer: Customer
) -> str:
    """Kapora talep metni. Grup: tek mesaj, kapora toplami."""
    first = appointments[0]
    if len(appointments) == 1:
        label = first.beneficiary_label if first.customer_id != payer.id else None
        services = _services_of(first) + (f" ({label} için)" if label else "")
    else:
        parts = []
        for a in appointments:
            who = (
                payer.first_name
                if a.customer_id == payer.id
                else (a.beneficiary_label or a.customer.first_name)
            )
            parts.append(f"{who}: {_services_of(a)}")
        services = "; ".join(parts)
    total = sum(a.total_price for a in appointments)
    deposit = sum(float(a.deposit_amount or 0) for a in appointments)
    return render_template(
        settings.template,
        _values(
            settings,
            payer.first_name,
            first.date,
            first.start_min,
            services,
            total,
            deposit,
            payment_reference(db, first, appointments),
        ),
    )


def queue_deposit_request(
    db: Session,
    appointments: list[Appointment],
    payer: Customer | None,
    settings: DepositSettings | None = None,
    resend_token: str | None = None,
) -> bool:
    """Kapora talep mesajini kuyruga yazar (normal "randevunuz olusturuldu"
    mesajinin YERINE). Yazildiysa True. Commit cagiranindir.

    ``appointments``: items.service + customer yuklu; grup ise hepsi."""
    if not appointments or not _reachable(payer):
        return False
    settings = settings or load_settings(db)
    first = appointments[0]
    key = (
        f"{DEPOSIT_GROUP_PREFIX}{first.booking_group_id}"
        if len(appointments) > 1 and first.booking_group_id
        else f"{DEPOSIT_PREFIX}{first.id}"
    )
    if resend_token:
        key = f"{key}:r{resend_token}"
    queue_confirmation(db, payer.id, key, build_request_message(db, settings, appointments, payer))
    return True


# ---------------------------------------------------------------------
# Musteri iptal kurali (< 60 dk)
# ---------------------------------------------------------------------


def minutes_until(appointment: Appointment, now: datetime | None = None) -> float:
    now = now or now_local()
    return (to_datetime(appointment.date, appointment.start_min) - now).total_seconds() / 60.0


def customer_cancel_locked(appointment: Appointment, now: datetime | None = None) -> bool:
    return minutes_until(appointment, now) < CANCEL_MIN_MINUTES


def assert_customer_may_cancel(appointment: Appointment, now: datetime | None = None) -> None:
    if customer_cancel_locked(appointment, now):
        raise AppError("CANCEL_TOO_LATE", CANCEL_TOO_LATE_MESSAGE, 409)


# ---------------------------------------------------------------------
# Durum gecisi (change_appointment_status icinden)
# ---------------------------------------------------------------------


def transition_on_status(
    appointment: Appointment, status: str, now: datetime, forfeit: bool = False
) -> tuple[dict, str | None]:
    """Yeni ``status`` icin kapora alanlarinin yeni degerleri ve bildirim turu.

    Doner: (UPDATE degerleri, mod) ; mod: "REFUND" | "FORFEIT" | "VOID" | None."""
    ds = appointment.deposit_status
    if ds == AWAITING:
        if status in ("CANCELLED", "NO_SHOW"):
            return {"deposit_status": NONE}, "VOID"
        if status in ("CONFIRMED", "COMPLETED"):
            # Kapora beklenirken yonetici onayladi/tamamladi: kapora feragat.
            return {"deposit_status": NONE, "deposit_amount": None}, None
    elif ds == PAID:
        if status == "CANCELLED":
            if forfeit:
                return {"deposit_status": FORFEITED}, "FORFEIT"
            return (
                {
                    "deposit_status": REFUND_DUE,
                    "deposit_refund_due_at": now + timedelta(hours=REFUND_HOURS),
                    "deposit_refund_alerted_at": None,
                },
                "REFUND",
            )
        if status == "NO_SHOW":
            return {"deposit_status": FORFEITED}, "FORFEIT"
    return {}, None


def revert_values(appointment: Appointment, previous: str) -> tuple[dict, str, str | None]:
    """Geri almada: (UPDATE degerleri, yeni randevu durumu, uyari metni)."""
    ds = appointment.deposit_status
    warning = None
    if previous in ("CANCELLED", "NO_SHOW"):
        if ds in (REFUND_DUE, FORFEITED):
            return (
                {"deposit_status": PAID, "deposit_refund_due_at": None, "deposit_refund_alerted_at": None},
                "CONFIRMED",
                None,
            )
        if ds == REFUNDED:
            warning = (
                "Kapora zaten iade edilmişti; randevu geri alındı ama kapora iade edilmiş "
                "görünüyor. Gerekirse kaporayı yeniden tahsil edin."
            )
            return {}, "CONFIRMED", warning
        if (
            ds == NONE
            and appointment.deposit_amount is not None
            and appointment.deposit_paid_at is None
            and appointment.deposit_requested_at is not None
        ):
            # Kapora beklerken iptal edilmisti: yeniden "kapora bekleniyor".
            return (
                {"deposit_status": AWAITING, "deposit_overdue_alerted_at": None},
                "PENDING",
                None,
            )
    return {}, "CONFIRMED", warning


# ---------------------------------------------------------------------
# Iptal mesajlari (booking_cancellation kullanir)
# ---------------------------------------------------------------------


def unpaid_cancel_message(name: str, appointment: Appointment) -> str:
    return (
        UNPAID_CANCEL_TEMPLATE.replace("{ad}", name)
        .replace("{tarih}", format_date_tr(appointment.date))
        .replace("{saat}", minutes_to_label(appointment.start_min))
        .replace("{site}", config.public_site_url)
    )


# ---------------------------------------------------------------------
# Yonetici islemleri
# ---------------------------------------------------------------------


def _load(db: Session, appointment_id: int) -> Appointment:
    appointment = db.scalar(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
        )
        .where(Appointment.id == appointment_id)
    )
    if appointment is None:
        raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)
    return appointment


def _withdraw_pending(db: Session, keys: list[str], prefixes: list[str]) -> None:
    from sqlalchemy import or_

    conds = [ScheduledNotification.dedupe_key.in_(keys)]
    conds += [ScheduledNotification.dedupe_key.startswith(p) for p in prefixes]
    db.execute(
        update(ScheduledNotification)
        .where(or_(*conds), ScheduledNotification.status == "PENDING")
        .values(status="CANCELLED")
    )


def mark_paid(
    db: Session,
    appointment_id: int,
    staff_id: int,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> dict:
    """"Kapora odendi": PENDING+AWAITING -> CONFIRMED+PAID. Gruptaysa ayni
    alanin kapora bekleyen TUM randevulari birlikte odenmis sayilir (havale
    toplam tutar icindir) ve alana TEK mesaj gider."""
    from .manual_booking import sync_pre_reminder

    now = now or now_local()
    try:
        appointment = _load(db, appointment_id)
        if expected_version is not None and appointment.version != expected_version:
            raise VersionConflictError(appointment.version)
        if appointment.status != "PENDING" or appointment.deposit_status != AWAITING:
            raise AppError("VALIDATION", "Bu randevu için bekleyen kapora yok.", 409)

        members = [
            m
            for m in group_members(db, appointment)
            if m.status == "PENDING" and m.deposit_status == AWAITING
        ] or [appointment]
        if appointment.id not in {m.id for m in members}:
            members.append(appointment)

        paid: list[Appointment] = []
        for m in members:
            rows = db.execute(
                update(Appointment)
                .where(
                    Appointment.id == m.id,
                    Appointment.status == "PENDING",
                    Appointment.deposit_status == AWAITING,
                )
                .values(
                    status="CONFIRMED",
                    deposit_status=PAID,
                    deposit_paid_at=now,
                    deposit_paid_by_staff_id=staff_id,
                    version=Appointment.version + 1,
                )
            ).rowcount
            if rows:
                paid.append(m)
        if not paid:
            raise VersionConflictError(appointment.version)

        db.expire_all()
        paid = [_load(db, m.id) for m in paid]
        first = paid[0]
        payer = db.get(Customer, payer_id_of(first))
        grouped = len(paid) > 1 and first.booking_group_id
        queued = False
        if _reachable(payer):
            key = (
                f"{PAID_GROUP_PREFIX}{first.booking_group_id}"
                if grouped
                else f"{PAID_PREFIX}{first.id}"
            )
            queue_confirmation(
                db,
                payer.id,
                key,
                PAID_TEMPLATE.replace("{ad}", payer.first_name)
                .replace("{tarih}", format_date_tr(first.date))
                .replace("{saat}", minutes_to_label(first.start_min)),
            )
            queued = True

        # Bekleyen (gitmemis) kapora talebi artik gereksiz.
        _withdraw_pending(
            db,
            [f"{DEPOSIT_PREFIX}{m.id}" for m in paid]
            + ([f"{DEPOSIT_GROUP_PREFIX}{first.booking_group_id}"] if first.booking_group_id else []),
            [f"{DEPOSIT_PREFIX}{m.id}:r" for m in paid],
        )
        # "Yarin randevunuz var" hatirlatmasi: vakti hala gelmediyse yeniden kur.
        for m in paid:
            sync_pre_reminder(db, m, m.customer, [i.service.name for i in m.items if i.service], now)

        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "ids": [m.id for m in paid],
        "status": "CONFIRMED",
        "depositStatus": PAID,
        "whatsappQueued": queued,
    }


def mark_refunded(
    db: Session,
    appointment_id: int,
    staff_id: int,
    notify: bool = True,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> dict:
    """"Kapora iade edildi": REFUND_DUE -> REFUNDED (+ istege bagli mesaj)."""
    now = now or now_local()
    try:
        appointment = _load(db, appointment_id)
        if expected_version is not None and appointment.version != expected_version:
            raise VersionConflictError(appointment.version)
        rows = db.execute(
            update(Appointment)
            .where(Appointment.id == appointment.id, Appointment.deposit_status == REFUND_DUE)
            .values(
                deposit_status=REFUNDED,
                deposit_refunded_at=now,
                deposit_refunded_by_staff_id=staff_id,
                version=Appointment.version + 1,
            )
        ).rowcount
        if not rows:
            raise AppError("VALIDATION", "Bu randevu için bekleyen bir kapora iadesi yok.", 409)
        queued = False
        payer = db.get(Customer, payer_id_of(appointment))
        if notify and _reachable(payer):
            queue_confirmation(
                db,
                payer.id,
                f"{REFUND_PREFIX}{appointment.id}",
                REFUNDED_TEMPLATE.replace("{ad}", payer.first_name).replace(
                    "{kapora}", format_tl(appointment.deposit_amount)
                ),
            )
            queued = True
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"id": appointment.id, "depositStatus": REFUNDED, "whatsappQueued": queued}


def resend_request(db: Session, appointment_id: int, now: datetime | None = None) -> dict:
    """"Kapora mesajini tekrar gonder" (tutar degistiyse ya da mesaj gitmediyse)."""
    now = now or now_local()
    appointment = _load(db, appointment_id)
    if appointment.status != "PENDING" or appointment.deposit_status != AWAITING:
        raise AppError("VALIDATION", "Bu randevu için bekleyen kapora yok.", 409)
    members = [
        m
        for m in group_members(db, appointment)
        if m.status == "PENDING" and m.deposit_status == AWAITING
    ] or [appointment]
    payer = db.get(Customer, payer_id_of(appointment))
    queued = queue_deposit_request(
        db, members, payer, resend_token=str(int(now.timestamp() * 1000))
    )
    if not queued:
        raise AppError("VALIDATION", "Müşteriye WhatsApp mesajı gönderilemiyor (telefon yok).", 409)
    db.commit()
    return {"queued": True}


# ---------------------------------------------------------------------
# Listeler ve gorunumler
# ---------------------------------------------------------------------


def _name(c: Customer | None) -> str:
    if c is None:
        return ""
    return f"{c.first_name} {c.last_name}".strip() if c.last_name else c.first_name


def admin_view(appointment: Appointment, settings: DepositSettings, now: datetime) -> dict | None:
    """Takvim / liste icin kapora ozeti; kapora yoksa None."""
    if appointment.deposit_amount is None and appointment.deposit_status == NONE:
        return None
    overdue = (
        appointment.status == "PENDING"
        and appointment.deposit_status == AWAITING
        and appointment.deposit_requested_at is not None
        and now >= appointment.deposit_requested_at + timedelta(minutes=settings.deadline_minutes)
    )
    return {
        "status": appointment.deposit_status,
        "amount": appointment.deposit_amount,
        "requestedAt": appointment.deposit_requested_at.isoformat()
        if appointment.deposit_requested_at
        else None,
        "paidAt": appointment.deposit_paid_at.isoformat() if appointment.deposit_paid_at else None,
        "refundDueAt": appointment.deposit_refund_due_at.isoformat()
        if appointment.deposit_refund_due_at
        else None,
        "refundedAt": appointment.deposit_refunded_at.isoformat()
        if appointment.deposit_refunded_at
        else None,
        "overdue": overdue,
    }


def customer_view(
    db: Session, appointment: Appointment, settings: DepositSettings, viewer_is_payer: bool
) -> dict | None:
    """Musteriye gosterilen kapora bilgisi. Odeme bilgileri (IBAN...) yalniz
    kaporayi yatiracak kisiye (randevuyu alan) gosterilir."""
    if appointment.deposit_amount is None and appointment.deposit_status == NONE:
        return None
    view: dict = {
        "status": appointment.deposit_status,
        "amount": appointment.deposit_amount,
        "policy": POLICY_TEXT,
        "refundDueAt": appointment.deposit_refund_due_at.isoformat()
        if appointment.deposit_refund_due_at
        else None,
    }
    if appointment.deposit_status == AWAITING and appointment.status == "PENDING" and viewer_is_payer:
        members = [
            m
            for m in group_members(db, appointment)
            if m.status == "PENDING" and m.deposit_status == AWAITING
        ] or [appointment]
        view.update(
            payAmount=sum(float(m.deposit_amount or 0) for m in members),
            iban=format_iban(settings.iban),
            accountName=settings.account_name,
            bankName=settings.bank_name,
            reference=payment_reference(db, appointment),
        )
    return view


def _row(
    a: Appointment, settings: DepositSettings, now: datetime, payer: Customer | None
) -> dict:
    return {
        "id": a.id,
        "version": a.version,
        "date": a.date,
        "dateLabel": format_date_tr(a.date),
        "startLabel": minutes_to_label(a.start_min),
        "customer": {"id": a.customer.id, "name": _name(a.customer), "phone": a.customer.phone},
        "payer": {"id": payer.id, "name": _name(payer), "phone": payer.phone} if payer else None,
        "services": [i.service.name for i in a.items if i.service is not None],
        "totalPrice": a.total_price,
        "amount": a.deposit_amount,
        "status": a.status,
        "depositStatus": a.deposit_status,
        "groupId": a.booking_group_id,
        "requestedAt": a.deposit_requested_at.isoformat() if a.deposit_requested_at else None,
        "refundDueAt": a.deposit_refund_due_at.isoformat() if a.deposit_refund_due_at else None,
    }


def list_awaiting(db: Session, now: datetime | None = None) -> list[dict]:
    now = now or now_local()
    settings = load_settings(db)
    rows = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
        )
        .where(Appointment.status == "PENDING", Appointment.deposit_status == AWAITING)
        .order_by(Appointment.deposit_requested_at, Appointment.id)
    ).all()
    group_totals: dict[str, tuple[int, float]] = {}
    for a in rows:
        if a.booking_group_id:
            n, t = group_totals.get(a.booking_group_id, (0, 0.0))
            group_totals[a.booking_group_id] = (n + 1, t + float(a.deposit_amount or 0))
    out = []
    for a in rows:
        payer = db.get(Customer, payer_id_of(a))
        row = _row(a, settings, now, payer)
        requested = a.deposit_requested_at or a.created_at
        row["ageMinutes"] = max(0, int((now - requested).total_seconds() // 60))
        row["deadlineMinutes"] = settings.deadline_minutes
        row["overdue"] = row["ageMinutes"] >= settings.deadline_minutes
        row["reference"] = payment_reference(db, a)
        if a.booking_group_id:
            n, t = group_totals[a.booking_group_id]
            row["groupSize"], row["groupAmount"] = n, t
        out.append(row)
    return out


def list_refunds(db: Session, now: datetime | None = None) -> list[dict]:
    now = now or now_local()
    settings = load_settings(db)
    rows = db.scalars(
        select(Appointment)
        .options(
            selectinload(Appointment.items).selectinload(AppointmentItem.service),
            selectinload(Appointment.customer),
        )
        .where(Appointment.deposit_status == REFUND_DUE)
        .order_by(Appointment.deposit_refund_due_at, Appointment.id)
    ).all()
    out = []
    for a in rows:
        payer = db.get(Customer, payer_id_of(a))
        row = _row(a, settings, now, payer)
        due = a.deposit_refund_due_at
        remaining = int((due - now).total_seconds() // 60) if due else 0
        row["remainingMinutes"] = remaining
        row["overdue"] = remaining < 0
        out.append(row)
    return out
