"""Tarih/saat yardimcilari (``src/lib/time.ts`` karsiligi).

Sistem randevulari "YYYY-MM-DD" (yerel gun) + **gun ici dakika** olarak
saklar. Bu, saat dilimi / yaz saati kaymalarinin randevu izgarasini
bozmasini engeller: 10:00 randevusu her zaman 600'dur.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import config

MINUTES_PER_DAY = 1440

DateKey = str

_TZ = ZoneInfo(config.timezone)


def now_local() -> datetime:
    """Salonun saat dilimine gore "simdi" (``tzinfo`` olmadan).

    Veritabanindaki tum zaman damgalari salon yerel saatiyle, saat dilimi
    bilgisi olmadan saklanir. ``datetime.now()`` sunucunun saat dilimini
    kullandigi icin UTC'de calisan bir sunucuda her sey 3 saat kayardi;
    uygulama kodunda "simdi" icin YALNIZCA bu fonksiyon kullanilir.
    """
    return datetime.now(_TZ).replace(tzinfo=None)

_DATE_KEY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TR_WEEKDAYS = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"]
TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def to_date_key(value: datetime | date) -> DateKey:
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


def parse_date_key(key: DateKey) -> date:
    return date.fromisoformat(key)


def is_date_key(value: str) -> bool:
    if not isinstance(value, str) or not _DATE_KEY_RE.match(value):
        return False
    try:
        parse_date_key(value)
    except ValueError:
        return False
    return True


def weekday_of(key: DateKey) -> int:
    """0 = Pazar ... 6 = Cumartesi (JavaScript Date.getDay() ile ayni)."""
    # Python: Pazartesi=0 ... Pazar=6  ->  JS: Pazar=0 ... Cumartesi=6
    return (parse_date_key(key).weekday() + 1) % 7


def add_days_to_key(key: DateKey, days: int) -> DateKey:
    return to_date_key(parse_date_key(key) + timedelta(days=days))


def days_between_keys(a: DateKey, b: DateKey) -> int:
    return (parse_date_key(b) - parse_date_key(a)).days


def minutes_to_label(minute: int) -> str:
    """570 -> "09:30"."""
    minute = int(minute)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def label_to_minutes(label: str) -> int:
    hour, _, minute = label.partition(":")
    return int(hour or 0) * 60 + int(minute or 0)


def to_datetime(key: DateKey, minute: int) -> datetime:
    """Gun + dakikadan gercek bir ``datetime`` uretir (yerel saat)."""
    return datetime.combine(parse_date_key(key), datetime.min.time()) + timedelta(minutes=minute)


def now_parts(now: datetime | None = None) -> tuple[DateKey, int]:
    now = now or now_local()
    return to_date_key(now), now.hour * 60 + now.minute


def ceil_to_grid(minute: float, grid: int) -> int:
    """Bir degeri izgaraya yukari yuvarlar (17 dk, 15'lik izgara -> 30)."""
    if grid <= 1:
        return int(minute)
    return int(math.ceil(minute / grid) * grid)


def floor_to_grid(minute: float, grid: int) -> int:
    if grid <= 1:
        return int(minute)
    return int(math.floor(minute / grid) * grid)


def format_date_tr(key: DateKey) -> str:
    d = parse_date_key(key)
    return f"{d.day} {TR_MONTHS[d.month - 1]} {d.year}, {TR_WEEKDAYS[weekday_of(key)]}"


def weekday_name_tr(weekday: int) -> str:
    return TR_WEEKDAYS[weekday] if 0 <= weekday < 7 else ""
