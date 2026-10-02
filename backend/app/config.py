"""Ortam değişkenlerinin tek okuma noktası.

Tümü lokal çalışmaya göre varsayılana sahiptir; ``.env`` olmadan da
proje ayağa kalkar. (Next.js sürümündeki ``src/lib/config.ts`` karşılığı.)

Ortam (``APP_ENV``) ve güvenli varsayılan
------------------------------------------
Geliştirme kolaylıkları (OTP kodunun yanıtta dönmesi, sabit OTP,
``/docs``, demo sayfası) YALNIZCA ``APP_ENV`` açıkça ``development`` veya
``test`` iken açılır. Tanınmayan her değer (``prod``, ``staging``, yazım
hatası...) üretim sayılır. Üretimde sırlar eksikse veya depodaki lokal
varsayılanlarla aynıysa uygulama hiç açılmaz (bkz. ``validate_config``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Bağımlılık eklemeden küçük bir .env okuyucu.

    `python-dotenv` zaten uvicorn ile geliyor ama tek yönlü bu okuyucu
    hem testlerde hem de bağımsız betiklerde (seed) aynı davranır.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(BASE_DIR / ".env")


def _num(value: str | None, fallback: int) -> int:
    try:
        n = int(str(value))
    except (TypeError, ValueError):
        return fallback
    return n if n > 0 else fallback


#: Lokal PostgreSQL (``docker compose up -d db``).
_DEV_DATABASE_URL = "postgresql+psycopg://aurora:aurora@localhost:5432/aurora"

#: Depoda açıkça yazan lokal varsayılanlar; üretimde KULLANILAMAZ.
_DEV_SESSION_SECRET = "lokal-gelistirme-anahtari"
_DEV_PHONE_HASH_SECRET = "lokal-telefon-hash-anahtari"

#: Geliştirme kolaylıklarının açık olduğu ortamlar. Bunların dışındaki her
#: değer üretim kabul edilir.
DEV_ENVS = ("development", "test")


def _normalize_database_url(url: str) -> str:
    """Barındırma servislerinin verdiği ``postgres://`` adresini psycopg 3
    sürücüsüne yönlendirir (SQLAlchemy ``postgres://`` şemasını tanımaz)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@dataclass(frozen=True)
class Config:
    #: Soft-lock ömrü (saniye) — varsayılan 5 dakika.
    slot_lock_ttl_seconds: int
    #: Müsaitlik taramasının adım büyüklüğü (dakika).
    slot_grid_minutes: int
    #: Doluluk hücresi çözünürlüğü (dakika). OccupancyCell üzerindeki unique
    #: kısıt bu granularitede çalışır; DEĞİŞTİRİLİRSE hücreler yeniden üretilmeli.
    cell_minutes: int
    database_url: str
    session_secret: str
    phone_hash_secret: str
    #: "console" | "evolution" (WhatsApp, bkz. ``services/messaging.py``)
    notification_driver: str
    #: Geliştirmede sabit OTP; boşsa rastgele üretilir.
    dev_otp_code: str
    #: ``APP_ENV`` değeri (küçük harf).
    app_env: str
    is_production: bool
    upload_dir: Path
    #: Salonun saat dilimi. Tüm "şimdi" hesapları buna göre yapılır; sunucu
    #: UTC'de çalışsa bile randevu ızgarası ve hatırlatmalar kaymaz.
    timezone: str
    #: ``/api/cron/sweep`` için paylaşılan sır (``X-Cron-Secret`` başlığı).
    cron_secret: str
    #: Evolution API (WhatsApp) bağlantısı - yalnızca driver=evolution iken.
    evolution_api_url: str
    evolution_api_key: str
    evolution_instance: str
    #: Telefonların WhatsApp biçimine çevrilirken eklenen ülke kodu.
    whatsapp_country_code: str
    #: Kuyruk mesajları arasındaki bekleme (ms). Baileys ile bağlı numarada
    #: art arda hızlı gönderim hesabın kısıtlanma riskini artırır.
    whatsapp_send_interval_ms: int
    #: Bir bakım çalıştırmasında en fazla gönderilecek kuyruk mesajı.
    notification_batch_size: int
    #: Uygulama içi bildirim işçisinin kuyruğu kontrol aralığı (sn). 0: kapalı
    #: (o durumda ``/api/cron/sweep`` dışarıdan tetiklenmelidir).
    notification_poll_seconds: int
    #: Evolution API'nin gelen mesajları bildireceği backend adresi (Evolution
    #: konteynerinden erişilebilir olmalı). Boşsa webhook kurulmaz ve
    #: karşılama mesajı çalışmaz.
    evolution_webhook_url: str
    #: Webhook isteklerini doğrulayan sır (URL'deki ``token`` parametresi).
    evolution_webhook_secret: str
    #: Müşterilere gönderilen bağlantılar için sitenin genel adresi.
    public_site_url: str


_app_env = (os.getenv("APP_ENV") or "development").strip().lower()

config = Config(
    slot_lock_ttl_seconds=_num(os.getenv("SLOT_LOCK_TTL_SECONDS"), 300),
    slot_grid_minutes=_num(os.getenv("SLOT_GRID_MINUTES"), 15),
    cell_minutes=5,
    database_url=_normalize_database_url(
        os.getenv("DATABASE_URL") or _DEV_DATABASE_URL
    ),
    session_secret=os.getenv("SESSION_SECRET") or _DEV_SESSION_SECRET,
    phone_hash_secret=os.getenv("PHONE_HASH_SECRET") or _DEV_PHONE_HASH_SECRET,
    notification_driver=os.getenv("NOTIFICATION_DRIVER") or "console",
    dev_otp_code=os.getenv("DEV_OTP_CODE") or "",
    app_env=_app_env,
    is_production=_app_env not in DEV_ENVS,
    upload_dir=Path(os.getenv("UPLOAD_DIR") or (BASE_DIR / "uploads")),
    timezone=os.getenv("APP_TIMEZONE") or "Europe/Istanbul",
    cron_secret=os.getenv("CRON_SECRET") or "",
    evolution_api_url=os.getenv("EVOLUTION_API_URL") or "",
    evolution_api_key=os.getenv("EVOLUTION_API_KEY") or "",
    evolution_instance=os.getenv("EVOLUTION_INSTANCE") or "",
    whatsapp_country_code=os.getenv("WHATSAPP_COUNTRY_CODE") or "90",
    whatsapp_send_interval_ms=max(0, int(os.getenv("WHATSAPP_SEND_INTERVAL_MS") or 1500)),
    notification_batch_size=_num(os.getenv("NOTIFICATION_BATCH_SIZE"), 20),
    notification_poll_seconds=max(0, int(os.getenv("NOTIFICATION_POLL_SECONDS") or 60)),
    evolution_webhook_url=(os.getenv("EVOLUTION_WEBHOOK_URL") or "").rstrip("/"),
    evolution_webhook_secret=os.getenv("EVOLUTION_WEBHOOK_SECRET")
    or ("" if _app_env not in DEV_ENVS else "lokal-webhook-anahtari"),
    public_site_url=(os.getenv("PUBLIC_SITE_URL") or "http://localhost:3000").rstrip("/"),
)

NOTIFICATION_DRIVERS = ("console", "evolution")


class ConfigError(RuntimeError):
    """Üretim için güvensiz yapılandırma."""


def validate_config(cfg: Config = config) -> list[str]:
    """Yapılandırmayı doğrular.

    Üretimde güvenliği bozan her eksik ``ConfigError`` fırlatır - uygulama
    yanlış yapılandırmayla sessizce ayağa kalkmaz. Güvenliği bozmayan ama
    dikkat isteyen durumlar uyarı listesi olarak döner.
    """
    warnings: list[str] = []

    # Proje yalnızca PostgreSQL'i destekler (kilitler, SKIP LOCKED, SQLSTATE
    # kodları buna göre yazıldı); başka bir veritabanıyla sessizce açılmasın.
    if not cfg.database_url.startswith("postgresql+psycopg://"):
        raise ConfigError(
            "DATABASE_URL bir PostgreSQL adresi olmalı "
            "(postgresql://… veya postgresql+psycopg://…)."
        )

    # Sürücü ayarları her ortamda doğrulanır: yanlış yazılmış bir sürücü adı
    # sessizce "console"a düşüp mesajları yalnızca log'a yazmasın.
    if cfg.notification_driver not in NOTIFICATION_DRIVERS:
        raise ConfigError(
            f"NOTIFICATION_DRIVER={cfg.notification_driver!r} tanınmıyor "
            f"(geçerli değerler: {', '.join(NOTIFICATION_DRIVERS)})"
        )
    if cfg.notification_driver == "evolution":
        missing = [
            name
            for name, value in (
                ("EVOLUTION_API_URL", cfg.evolution_api_url),
                ("EVOLUTION_API_KEY", cfg.evolution_api_key),
                ("EVOLUTION_INSTANCE", cfg.evolution_instance),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "NOTIFICATION_DRIVER=evolution için eksik ayar: " + ", ".join(missing)
            )

    if not cfg.is_production:
        warnings.append(
            f"APP_ENV={cfg.app_env}: geliştirme modu. OTP kodları API yanıtında döner, "
            "/docs açıktır. Sunucuya çıkarken APP_ENV=production ayarlayın."
        )
        return warnings

    errors: list[str] = []
    if cfg.session_secret == _DEV_SESSION_SECRET or len(cfg.session_secret) < 32:
        errors.append(
            "SESSION_SECRET tanımlı değil, lokal varsayılanla aynı veya 32 karakterden kısa"
        )
    if cfg.phone_hash_secret == _DEV_PHONE_HASH_SECRET or len(cfg.phone_hash_secret) < 32:
        errors.append(
            "PHONE_HASH_SECRET tanımlı değil, lokal varsayılanla aynı "
            "veya 32 karakterden kısa"
        )
    if len(cfg.cron_secret) < 32:
        errors.append("CRON_SECRET tanımlı değil veya 32 karakterden kısa")
    if cfg.database_url == _DEV_DATABASE_URL:
        errors.append("DATABASE_URL tanımlı değil (lokal geliştirme veritabanı kullanılamaz)")
    if cfg.dev_otp_code:
        errors.append("DEV_OTP_CODE üretimde tanımlı olamaz")
    if cfg.evolution_webhook_url and len(cfg.evolution_webhook_secret) < 32:
        errors.append(
            "EVOLUTION_WEBHOOK_URL tanımlıyken EVOLUTION_WEBHOOK_SECRET en az 32 karakter olmalı"
        )
    if errors:
        details = "".join(f"\n  - {e}" for e in errors)
        raise ConfigError(
            f"Üretim yapılandırması güvensiz (APP_ENV={cfg.app_env}):{details}"
        )

    if cfg.notification_driver == "console":
        warnings.append(
            "NOTIFICATION_DRIVER=console: mesaj gönderilmez, müşteriler OTP ile giriş yapamaz."
        )
    if cfg.notification_driver == "evolution" and not cfg.evolution_webhook_url:
        warnings.append(
            "EVOLUTION_WEBHOOK_URL tanımlı değil: gelen mesajlar alınmaz, "
            "karşılama mesajı gitmez."
        )
    if cfg.public_site_url.startswith("http://localhost"):
        warnings.append("PUBLIC_SITE_URL localhost: müşteriye giden bağlantılar çalışmaz.")
    return warnings
