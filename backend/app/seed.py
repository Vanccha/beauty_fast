"""
=====================================================================
SEED - "Aurora Beauty Studio" demo verisi
=====================================================================

Amac: arayuz ve algoritmalarin BOS veritabaninda degil, gercekci bir
salonun 6 aylik gecmisi uzerinde calistigini gosterebilmek.

DETERMINISTIK: tum rastgelelik sabit tohumlu bir LCG'den gelir. Ayni
tohum -> ayni veri. Boylece "seed'i yenile, ekran degisti" durumu
yasanmaz ve hata ayiklama tekrarlanabilir olur.

CAKISMASIZLIK: gecmis randevular dogrudan tabloya yazilmaz; once bellekte
``build_occupancy_cells`` ile hucreleri uretilir ve global bir kume
uzerinden cakisma kontrolu yapilir. Boylece uretilen veri
``occupancy_cell`` uzerindeki unique kisitini ihlal etmez - yani seed,
uygulamanin kendi eszamanlilik kurallarina uyar.

Calistirma:  python -m app.seed
"""

from __future__ import annotations

import json
import math
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete

from .auth.password import hash_password
from .config import config
from .core.loyalty import calculate_earned_points, tier_for
from .core.occupancy import build_occupancy_cells
from .core.package_layout import LayoutOptions, layout_package
from .core.reminder_rules import ReminderContext, ReminderRuleSpec, resolve_reminder
from .core.risk_score import hash_phone
from .core.types import ResourceNeed, ServiceSpec
from .db import SessionLocal, init_db
from .models import (
    Allergy,
    Appointment,
    AppointmentItem,
    AppointmentResource,
    Branch,
    Campaign,
    Customer,
    CustomerNote,
    CustomerPhoto,
    InventoryItem,
    LoyaltyEntry,
    OccupancyCell,
    OccupancyStat,
    PhoneRiskEvent,
    PortfolioItem,
    ReminderRule,
    Resource,
    Review,
    ScheduledNotification,
    Salon,
    Service,
    ServiceCategory,
    ServiceConsumable,
    ServiceResource,
    Staff,
    StaffService,
    StockMovement,
    TimeOff,
    WorkingHour,
)
from .time_utils import add_days_to_key, now_local, to_date_key, to_datetime, weekday_of

OPEN_MIN = 540  # 09:00
CLOSE_MIN = 1200  # 20:00
GRID = 15

#: Gecmis verinin kapsadigi gun sayisi (risk skoru penceresi 6 ay).
HISTORY_DAYS = 180
#: Uretilecek gecmis randevu hedefi. 450: saat basina anlamli orneklem
#: olusur ve firsat-saati (Bayes) analizi duz bir isi haritasi uretmez.
HISTORY_APPOINTMENT_TARGET = 450

#: Randevu baslangic saatlerinin gercekci yogunlugu (aksam daha dolu).
START_HOUR_WEIGHTS = [
    (9, 1), (10, 2), (11, 2), (12, 2), (13, 3),
    (14, 5), (15, 6), (16, 7), (17, 8), (18, 6), (19, 3),
]

#: Firsat saati indirimi: oglene kadar olan randevulara uygulanir.
OPPORTUNITY_BEFORE_MIN = 12 * 60
OPPORTUNITY_DISCOUNT = 0.15

FIRST_NAMES = [
    "Ayşe", "Elif", "Zeynep", "Merve", "Selin", "Büşra", "Ecem", "Deniz",
    "Nihan", "Pınar", "Gamze", "Sude", "İrem", "Melis", "Ceren", "Dilara",
    "Aslı", "Esra", "Naz", "Beren", "Öykü", "Yaren", "Damla", "Sıla", "Tuğçe",
]
LAST_NAMES = [
    "Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Aydın", "Öztürk",
    "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç", "Kurt",
    "Özdemir", "Şimşek", "Polat", "Erdoğan", "Güneş", "Ateş", "Bulut", "Toprak", "Akın",
]


class Rng:
    """Deterministik rastgelelik (LCG - Numerical Recipes katsayilari)."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state / 0x100000000

    def int(self, lo: int, hi: int) -> int:
        return lo + int(self.next() * (hi - lo + 1))

    def pick(self, items):
        return items[int(self.next() * len(items))]

    def chance(self, p: float) -> bool:
        return self.next() < p

    def weighted(self, entries):
        total = sum(w for _, w in entries)
        r = self.next() * total
        for value, weight in entries:
            r -= weight
            if r <= 0:
                return value
        return entries[-1][0]

    def shuffle(self, items: list):
        for i in range(len(items) - 1, 0, -1):
            j = int(self.next() * (i + 1))
            items[i], items[j] = items[j], items[i]
        return items


rng = Rng(20260814)


# ---------------------------------------------------------------------
# Gorsel yer tutucular
# ---------------------------------------------------------------------
#
# Depoya ikili (binary) dosya koymamak icin portfolyo ve albüm görselleri
# seed sirasinda SVG olarak uretilir. Boylece galeri ekranlari gercek bir
# dosyayla calisir, ama repo temiz kalir (``uploads/`` .gitignore'da).

#: Salon estetigine yakin, uc duraklı degrade paletleri.
#: [koyu taban, orta ton, acik vurgu]
PALETTES: list[tuple[str, str, str]] = [
    ("#8c4a3f", "#c98b7a", "#f7ded3"),  # terrakota
    ("#4a3560", "#8f7bb0", "#e5dcf2"),  # lavanta
    ("#26564f", "#6f9e97", "#d6ece7"),  # adacayi
    ("#7a5c19", "#c2a253", "#f6e9c4"),  # altin
    ("#6d2f47", "#b0768f", "#f2d9e3"),  # gul
    ("#2f3f5c", "#7787a8", "#dbe4f2"),  # gece mavisi
    ("#5c3326", "#a9705a", "#efd9cc"),  # bakir
    ("#3f4a2e", "#8b9a6f", "#e3ead4"),  # zeytin
]

#: `frontend/public/photos` altina inen gercek fotograflarin bulundugu klasor.
_PHOTOS_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public" / "photos"


def write_placeholder_image(
    relative_path: str,
    label: str,
    seed: int,
    *,
    show_label: bool = False,
) -> str:
    """Deterministik SVG yer tutucu uretir; ``config.upload_dir`` altina yazar.

    Next.js surumundeki ``writePlaceholderImage`` ile birebir aynı
    kompozisyonu uretir (ayni tohum -> ayni gorsel): yumusatilmis renk
    lekeleri, ince isik halkalari ve hafif bir doku gurultusu.

    Donen deger ``/uploads/...`` bicimli bir URL'dir; dosya ise
    ``config.upload_dir / relative_path`` konumuna yazilir.
    """
    deep, mid, light = PALETTES[abs(seed) % len(PALETTES)]
    safe = label.replace("<", "").replace(">", "").replace("&", "")

    def p(n: int, lo: float, hi: float) -> float:
        x = abs(math.sin(seed * 12.9898 + n * 78.233)) * 43758.5453
        return lo + (x - math.floor(x)) * (hi - lo)

    angle = f"{p(1, 0, 360):.0f}"
    blob_fills = [light, mid, "#ffffff", light]
    blobs = ""
    for i in range(4):
        cx = f"{p(i * 4 + 2, 40, 560):.0f}"
        cy = f"{p(i * 4 + 3, 40, 560):.0f}"
        r = f"{p(i * 4 + 4, 110, 260):.0f}"
        fill = blob_fills[i]
        op = f"{0.22 + p(i * 4 + 5, 0, 0.3):.2f}"
        blobs += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" opacity="{op}"/>'

    label_markup = ""
    if show_label:
        label_markup = (
            '  <text x="300" y="312" text-anchor="middle" font-family="system-ui,sans-serif"\n'
            f'        font-size="46" font-weight="600" fill="#ffffff" fill-opacity="0.92">{safe}</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600">
  <defs>
    <linearGradient id="bg" gradientTransform="rotate({angle} 0.5 0.5)">
      <stop offset="0%" stop-color="{deep}"/>
      <stop offset="55%" stop-color="{mid}"/>
      <stop offset="100%" stop-color="{light}"/>
    </linearGradient>
    <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="55"/>
    </filter>
    <filter id="grain">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" stitchTiles="stitch"/>
      <feColorMatrix type="saturate" values="0"/>
    </filter>
    <radialGradient id="vignette">
      <stop offset="55%" stop-color="#000000" stop-opacity="0"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0.35"/>
    </radialGradient>
  </defs>

  <rect width="600" height="600" fill="url(#bg)"/>
  <g filter="url(#soft)">{blobs}</g>

  <!-- ince isik halkalari: kompozisyona derinlik katar -->
  <circle cx="{p(20, 120, 480):.0f}" cy="{p(21, 120, 480):.0f}"
          r="{p(22, 150, 240):.0f}" fill="none" stroke="#ffffff"
          stroke-opacity="0.20" stroke-width="1.5"/>
  <circle cx="{p(30, 120, 480):.0f}" cy="{p(31, 120, 480):.0f}"
          r="{p(32, 60, 130):.0f}" fill="none" stroke="#ffffff"
          stroke-opacity="0.14" stroke-width="1"/>

  <rect width="600" height="600" filter="url(#grain)" opacity="0.07"/>
  <rect width="600" height="600" fill="url(#vignette)"/>
{label_markup}
</svg>"""

    full = config.upload_dir / relative_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(svg, encoding="utf-8")
    return f"/uploads/{relative_path.replace(chr(92), '/')}"


def site_photo(file_name: str) -> str | None:
    """``npm run photos`` ile inen vitrin fotografini arar.

    Seed, gercek fotograf VARSA onu kullanir; yoksa cizilmis yer
    tutucuya duser. Boylece fotograflar indirilmemis bir makinede de
    seed calisir, indirilmisse salon ilk acilista gercek bir vitrinle
    karsilar.
    """
    full = _PHOTOS_DIR / file_name
    return f"/photos/{file_name}" if full.exists() else None


# ---------------------------------------------------------------------
# Sabit tanimlar
# ---------------------------------------------------------------------

CATEGORY_DEFS = [
    {"slug": "tirnak", "name": "Tırnak", "icon": "💅", "sort_order": 1},
    {"slug": "sac", "name": "Saç", "icon": "💇", "sort_order": 2},
    {"slug": "kas-kirpik", "name": "Kaş & Kirpik", "icon": "👁️", "sort_order": 3},
    {"slug": "cilt", "name": "Cilt Bakımı", "icon": "🧖", "sort_order": 4},
]

RESOURCE_DEFS = [
    {"key": "uv", "name": "UV Lamba", "kind": "DEVICE", "capacity": 2},
    {"key": "koltuk", "name": "Boya Koltuğu", "kind": "CHAIR", "capacity": 3},
    {"key": "yikama", "name": "Yıkama Ünitesi", "kind": "SINK", "capacity": 2},
    {"key": "cilt", "name": "Cilt Cihazı", "kind": "DEVICE", "capacity": 1},
]

SERVICE_DEFS = [
    {
        "key": "manikur", "name": "Manikür", "category": "tirnak", "price": 350,
        "active_before_min": 40, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": False,
        "recommended_repeat_days": 21,
        "description": "Tırnak şekillendirme, kütikül bakımı ve nemlendirme.",
        "resources": [],
    },
    {
        "key": "kalici-oje", "name": "Kalıcı Oje", "category": "tirnak", "price": 500,
        "active_before_min": 40, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": False,
        "recommended_repeat_days": 21,
        "description": "UV kürlemeli kalıcı oje uygulaması.",
        "resources": [("uv", True)],
    },
    {
        "key": "nail-art", "name": "Nail Art", "category": "tirnak", "price": 250,
        "active_before_min": 30, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": False,
        "recommended_repeat_days": 21,
        "description": "Elle çizim, taş ve folyo süsleme.",
        "resources": [("uv", True)],
    },
    {
        # Golge bloklamanin vitrin hizmeti: ortadaki 40 dk usta serbest.
        "key": "sac-boyasi", "name": "Saç Boyası", "category": "sac", "price": 1200,
        "active_before_min": 30, "passive_min": 40, "active_after_min": 20, "buffer_min": 10,
        "shadow_host_allowed": True, "shadow_guest_allowed": False,
        "recommended_repeat_days": 35,
        "description": "Boya sürme (30 dk) + bekleme (40 dk) + yıkama & fön (20 dk).",
        "resources": [("koltuk", False)],
    },
    {
        "key": "keratin", "name": "Keratin Bakımı", "category": "sac", "price": 2500,
        "active_before_min": 40, "passive_min": 60, "active_after_min": 30, "buffer_min": 10,
        "shadow_host_allowed": True, "shadow_guest_allowed": False,
        "recommended_repeat_days": 120,
        "description": "Keratin sürme + 60 dk işlem süresi + düzleştirme.",
        "resources": [("koltuk", False)],
    },
    {
        # Golge penceresine yerlesebilen kisa hizmet.
        "key": "kas-alma", "name": "Kaş Alma", "category": "kas-kirpik", "price": 150,
        "active_before_min": 15, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": True,
        "recommended_repeat_days": 21,
        "description": "İplik veya ağda ile kaş şekillendirme.",
        "resources": [],
    },
    {
        "key": "biyik-agda", "name": "Bıyık Ağdası", "category": "kas-kirpik", "price": 100,
        "active_before_min": 10, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": True,
        "recommended_repeat_days": 21,
        "description": "Üst dudak ağda uygulaması.",
        "resources": [],
    },
    {
        "key": "kirpik-lifting", "name": "Kirpik Lifting", "category": "kas-kirpik", "price": 700,
        "active_before_min": 45, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": False,
        "recommended_repeat_days": 60,
        "description": "Kirpik kaldırma ve besleyici bakım.",
        "resources": [],
    },
    {
        "key": "fon", "name": "Fön", "category": "sac", "price": 300,
        "active_before_min": 30, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": False,
        "recommended_repeat_days": 10,
        "description": "Yıkama + şekillendirme.",
        "resources": [("yikama", True)],
    },
    {
        "key": "sac-kesimi", "name": "Saç Kesimi", "category": "sac", "price": 450,
        "active_before_min": 30, "passive_min": 0, "active_after_min": 0, "buffer_min": 0,
        "shadow_host_allowed": False, "shadow_guest_allowed": False,
        "recommended_repeat_days": 45,
        "description": "Kişiye özel kesim ve şekillendirme.",
        "resources": [("yikama", True)],
    },
    {
        "key": "cilt-bakimi", "name": "Cilt Bakımı", "category": "cilt", "price": 900,
        "active_before_min": 20, "passive_min": 30, "active_after_min": 10, "buffer_min": 5,
        "shadow_host_allowed": True, "shadow_guest_allowed": False,
        "recommended_repeat_days": 30,
        "description": "Derin temizlik + maske bekleme (30 dk) + bakım.",
        "resources": [("cilt", False)],
    },
]

STAFF_DEFS = [
    {
        "name": "Elif Aydın", "phone": "5551110001", "password": "admin123", "role": "OWNER",
        # Deneyimli usta: aktif sureleri %10 kisa (pasif/kimyasal sure degismez).
        "speed_factor": 0.9,
        "skills": ["sac-boyasi", "keratin", "sac-kesimi", "fon", "cilt-bakimi", "kas-alma"],
        "off_weekdays": [0],
    },
    {
        "name": "Merve Kaya", "phone": "5551110002", "password": "merve123", "role": "MANAGER",
        "speed_factor": 1.0,
        "skills": ["sac-boyasi", "sac-kesimi", "fon", "cilt-bakimi", "kas-alma", "biyik-agda"],
        "off_weekdays": [0],
    },
    {
        "name": "Zeynep Demir", "phone": "5551110003", "password": "zeynep123", "role": "STAFF",
        "speed_factor": 1.0,
        "skills": ["manikur", "kalici-oje", "nail-art", "kas-alma", "biyik-agda", "kirpik-lifting"],
        "off_weekdays": [0, 1],
    },
    {
        "name": "Selin Yılmaz", "phone": "5551110004", "password": "selin123", "role": "STAFF",
        # Yeni usta: aktif sureleri %10 uzun.
        "speed_factor": 1.1,
        "skills": ["manikur", "kalici-oje", "nail-art", "kas-alma", "fon"],
        "off_weekdays": [0],
    },
]

INVENTORY_DEFS = [
    {"key": "oje", "name": "Kalıcı Oje (şişe)", "unit": "adet", "quantity": 38, "critical": 10, "cost": 120},
    {"key": "baz-jel", "name": "Baz Jel", "unit": "adet", "quantity": 12, "critical": 5, "cost": 180},
    {"key": "boya", "name": "Saç Boyası Tüpü", "unit": "adet", "quantity": 26, "critical": 8, "cost": 210},
    {"key": "oksidan", "name": "Oksidan", "unit": "ml", "quantity": 5200, "critical": 1200, "cost": 0.04},
    {"key": "keratin", "name": "Keratin Solüsyonu", "unit": "ml", "quantity": 2800, "critical": 800, "cost": 0.35},
    {"key": "agda", "name": "Sir Ağda", "unit": "gram", "quantity": 4200, "critical": 1000, "cost": 0.02},
    {"key": "sampuan", "name": "Şampuan", "unit": "ml", "quantity": 6400, "critical": 1500, "cost": 0.03},
    # Bilerek kritik seviyenin ALTINDA: admin panelde uyari gorunsun.
    {"key": "havlu", "name": "Tek Kullanımlık Havlu", "unit": "adet", "quantity": 14, "critical": 25, "cost": 6},
    {"key": "maske", "name": "Cilt Maskesi", "unit": "adet", "quantity": 9, "critical": 12, "cost": 95},
]

CONSUMABLE_DEFS = [
    ("kalici-oje", "oje", 0.15),
    ("kalici-oje", "baz-jel", 0.1),
    ("nail-art", "oje", 0.05),
    ("sac-boyasi", "boya", 1),
    ("sac-boyasi", "oksidan", 90),
    ("sac-boyasi", "sampuan", 30),
    ("sac-boyasi", "havlu", 2),
    ("keratin", "keratin", 80),
    ("keratin", "havlu", 2),
    ("kas-alma", "agda", 15),
    ("biyik-agda", "agda", 8),
    ("fon", "sampuan", 25),
    ("fon", "havlu", 1),
    ("sac-kesimi", "sampuan", 20),
    ("cilt-bakimi", "maske", 1),
]

PACKAGE_DEFS = [
    (["manikur", "kalici-oje", "nail-art"], 3),   # 110 dk ornek paket
    (["kalici-oje"], 8),
    (["manikur"], 5),
    (["sac-boyasi"], 7),
    (["sac-boyasi", "kas-alma"], 3),              # golge sikistirma ornegi
    (["sac-kesimi", "fon"], 4),
    (["fon"], 6),
    (["kas-alma"], 5),
    (["kas-alma", "biyik-agda"], 2),
    (["cilt-bakimi"], 4),
    (["keratin"], 2),
    (["kirpik-lifting"], 3),
]

REVIEW_TEXTS = [
    "Randevu saatinde başladık, beklemedim. Sonuçtan çok memnunum.",
    "Rengi tam istediğim gibi tutturdular, dipler doğal göründü.",
    "Salon çok temiz, kullanılan ürünler hakkında tek tek bilgi verdiler.",
    "Kaşlarım ilk kez bu kadar simetrik oldu, teşekkürler.",
    "Boya beklerken kaşlarımı da aldılar; iki işi tek randevuda bitirdim.",
    "Kalıcı ojem üç haftadır hiç kalkmadı, işçilik çok temiz.",
    "Alerjimi kayıtlarında tutmuşlar, ürünü ona göre seçtiler. Güven verdi.",
    "Fiyat baştan söylendi, sürpriz çıkmadı.",
    "Cilt bakımından sonra kızarıklık olmadı, aynı gün dışarı çıkabildim.",
    "Ekip çok ilgili, bir dahaki randevumu çıkarken aldım.",
    "Saçımın uzunluğuna rağmen söylenen sürede bitti.",
    "Nail art detayları fotoğraftaki gibi çıktı.",
]


def reset_database(db) -> None:
    """Silme sirasi yabanci anahtarlari ters yonde takip eder."""
    for model in (
        OccupancyCell, OccupancyStat, ScheduledNotification, StockMovement, LoyaltyEntry,
        Review, CustomerPhoto, CustomerNote, Allergy, AppointmentResource, AppointmentItem,
        Appointment, PhoneRiskEvent, ReminderRule, Campaign, PortfolioItem,
        ServiceConsumable, InventoryItem, ServiceResource, StaffService, TimeOff,
        WorkingHour, Resource, Service, ServiceCategory, Staff, Customer, Branch, Salon,
    ):
        db.execute(delete(model))
    from .models import CustomerSession, SlotLock, SlotViewEvent, StaffSession, VerificationCode

    for model in (SlotLock, SlotViewEvent, CustomerSession, StaffSession, VerificationCode):
        db.execute(delete(model))
    db.commit()


def main() -> None:
    # Windows konsolu varsayilan olarak cp1254; Turkce cikti bozulmasin.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - platforma bagli
        pass

    # Seed veritabanini SIFIRLAR (tum tablolar silinir). Uretimde yanlislikla
    # calistirilmasi gercek musteri verisinin kaybi demektir.
    if config.is_production:
        sys.exit(
            f"Seed üretim ortamında çalıştırılamaz (APP_ENV={config.app_env}). "
            "Veritabanındaki TÜM veriyi siler."
        )

    init_db()
    db = SessionLocal()
    now = now_local()
    today_key = to_date_key(now)

    print("▸ Veritabanı temizleniyor...")
    reset_database(db)

    # -----------------------------------------------------------------
    # 1. Salon + sube
    # -----------------------------------------------------------------
    salon = Salon(
        name="Aurora Beauty Studio", slug="aurora-beauty-studio", phone="5551110001"
    )
    db.add(salon)
    db.flush()

    branch = Branch(
        salon_id=salon.id,
        name="Merkez Şube",
        address="Bağdat Cad. No: 128, Kadıköy / İstanbul",
        open_minute=OPEN_MIN,
        close_minute=CLOSE_MIN,
    )
    db.add(branch)
    db.flush()

    # -----------------------------------------------------------------
    # 2. Kategoriler
    # -----------------------------------------------------------------
    categories: dict[str, int] = {}
    for definition in CATEGORY_DEFS:
        row = ServiceCategory(branch_id=branch.id, **definition)
        db.add(row)
        db.flush()
        categories[definition["slug"]] = row.id

    # -----------------------------------------------------------------
    # 3. Kaynaklar (capacity == 1 olanlar hucre yazar)
    # -----------------------------------------------------------------
    resources: dict[str, Resource] = {}
    for definition in RESOURCE_DEFS:
        row = Resource(
            branch_id=branch.id,
            name=definition["name"],
            kind=definition["kind"],
            capacity=definition["capacity"],
        )
        db.add(row)
        db.flush()
        resources[definition["key"]] = row

    exclusive_resource_ids = [r.id for r in resources.values() if r.capacity == 1]

    # -----------------------------------------------------------------
    # 4. Hizmetler
    # -----------------------------------------------------------------
    services: dict[str, dict] = {}
    for definition in SERVICE_DEFS:
        row = Service(
            branch_id=branch.id,
            category_id=categories[definition["category"]],
            name=definition["name"],
            description=definition["description"],
            price=definition["price"],
            active_before_min=definition["active_before_min"],
            passive_min=definition["passive_min"],
            active_after_min=definition["active_after_min"],
            buffer_min=definition["buffer_min"],
            shadow_host_allowed=definition["shadow_host_allowed"],
            shadow_guest_allowed=definition["shadow_guest_allowed"],
            recommended_repeat_days=definition["recommended_repeat_days"],
        )
        db.add(row)
        db.flush()

        needs: list[ResourceNeed] = []
        for key, only_active in definition["resources"]:
            db.add(
                ServiceResource(
                    service_id=row.id,
                    resource_id=resources[key].id,
                    quantity=1,
                    only_during_active=only_active,
                )
            )
            needs.append(ResourceNeed(resources[key].id, 1, only_active))

        services[definition["key"]] = {
            "id": row.id,
            "category_id": row.category_id,
            "def": definition,
            "spec": ServiceSpec(
                id=row.id,
                name=definition["name"],
                active_before_min=definition["active_before_min"],
                passive_min=definition["passive_min"],
                active_after_min=definition["active_after_min"],
                buffer_min=definition["buffer_min"],
                shadow_host_allowed=definition["shadow_host_allowed"],
                shadow_guest_allowed=definition["shadow_guest_allowed"],
                price=definition["price"],
                resources=tuple(needs),
            ),
        }

    # -----------------------------------------------------------------
    # 5. Personel + calisma saatleri + yetkinlikler
    # -----------------------------------------------------------------
    staff_list: list[dict] = []
    for index, definition in enumerate(STAFF_DEFS):
        # Personel avatari: `photos` klasorune inen gercek portre varsa o
        # kullanilir - ekip bolumu bir salonun yuzudur, bas harfli daire
        # pazarlama acisindan zayif kalir. Fotograf yoksa soyut kompozisyon
        # + bas harfler.
        photo_url = site_photo(f"ekip-{index + 1}.jpg") or write_placeholder_image(
            f"staff/{index + 1}.svg",
            "".join(part[0] for part in definition["name"].split(" ") if part),
            index * 7 + 3,
            show_label=True,
        )
        row = Staff(
            branch_id=branch.id,
            name=definition["name"],
            phone=definition["phone"],
            password_hash=hash_password(definition["password"]),
            role=definition["role"],
            photo_url=photo_url,
            display_order=index,
        )
        db.add(row)
        db.flush()

        for weekday in range(7):
            db.add(
                WorkingHour(
                    staff_id=row.id,
                    weekday=weekday,
                    start_min=OPEN_MIN,
                    # Cumartesi kapanis 18:00
                    end_min=1080 if weekday == 6 else CLOSE_MIN,
                    is_working=weekday not in definition["off_weekdays"],
                )
            )

        for skill in definition["skills"]:
            db.add(
                StaffService(
                    staff_id=row.id,
                    service_id=services[skill]["id"],
                    speed_factor=definition["speed_factor"],
                )
            )

        staff_list.append(
            {
                "id": row.id,
                "name": definition["name"],
                "speed_factor": definition["speed_factor"],
                "skills": definition["skills"],
                "off_weekdays": definition["off_weekdays"],
            }
        )

    # Ornek izin: Selin gelecek hafta bir gun tam gun izinli.
    db.add(
        TimeOff(
            staff_id=staff_list[3]["id"],
            date=add_days_to_key(today_key, 4),
            reason="Yıllık izin",
        )
    )

    # -----------------------------------------------------------------
    # 6. Stok kalemleri + receteler
    # -----------------------------------------------------------------
    inventory: dict[str, int] = {}
    for definition in INVENTORY_DEFS:
        row = InventoryItem(
            branch_id=branch.id,
            name=definition["name"],
            unit=definition["unit"],
            quantity=definition["quantity"],
            critical_level=definition["critical"],
            cost_per_unit=definition["cost"],
        )
        db.add(row)
        db.flush()
        inventory[definition["key"]] = row.id

    for service_key, item_key, qty in CONSUMABLE_DEFS:
        db.add(
            ServiceConsumable(
                service_id=services[service_key]["id"],
                item_id=inventory[item_key],
                qty_per_use=qty,
            )
        )

    # Birkac satin alma hareketi (stok gecmisi bos gorunmesin).
    for key, delta in (("boya", 20), ("oksidan", 3000), ("havlu", 50)):
        db.add(
            StockMovement(
                item_id=inventory[key],
                delta=delta,
                reason="PURCHASE",
                note="Dönemsel tedarik",
                created_at=now - timedelta(days=40),
            )
        )

    # -----------------------------------------------------------------
    # 7. Kampanyalar (algoritmik hedefleme - manuel kupon yok)
    # -----------------------------------------------------------------
    campaign_defs = [
        {
            "name": "Seni Özledik",
            "description": "90 günden uzun süredir gelmeyen, riski düşük müşterilere %15 indirim.",
            "kind": "DISCOUNT_PERCENT",
            "value": 15,
            "target_rule": json.dumps({"minDaysSinceLastVisit": 90, "maxRiskScore": 45}),
            "priority": 10,
        },
        {
            "name": "VIP Ayrıcalığı",
            "description": "Altın ve üzeri seviyedeki müşterilere her randevuda 250 bonus puan.",
            "kind": "BONUS_POINTS",
            "value": 250,
            "target_rule": json.dumps({"minTier": "ALTIN", "minTotalSpend": 4000}),
            "priority": 20,
        },
        {
            "name": "Hoş Geldin",
            "description": "İlk iki randevusundaki yeni müşterilere %10 indirim.",
            "kind": "DISCOUNT_PERCENT",
            "value": 10,
            "target_rule": json.dumps({"segments": ["YENI"], "maxVisits": 2}),
            "priority": 5,
        },
    ]
    for definition in campaign_defs:
        db.add(
            Campaign(
                branch_id=branch.id,
                is_active=True,
                starts_at=now - timedelta(days=30),
                ends_at=now + timedelta(days=120),
                **definition,
            )
        )

    # -----------------------------------------------------------------
    # 8. Hatirlatma kurallari (hard-code yok, tablo yonetiyor)
    # -----------------------------------------------------------------
    reminder_defs = [
        {
            "name": "Dip boya büyüme kuralı",
            "service_id": services["sac-boyasi"]["id"],
            "category_id": None,
            "formula": "GROWTH",
            "base_days": 35,
            # Sac ~12 mm/ay uzar; 14 mm dip gorunur hale gelir -> ~35 gun.
            "params": json.dumps({"mmPerMonth": 12, "toleranceMm": 14}),
            "channel": "WHATSAPP",
            "template": "{ad}, {hizmet} işleminizin üzerinden {gun} gün geçti. Dipler belirmeden yenileyelim mi? {link}",
            "priority": 30,
        },
        {
            "name": "Kalıcı oje ürün ömrü",
            "service_id": services["kalici-oje"]["id"],
            "category_id": None,
            "formula": "PRODUCT_LIFETIME",
            "base_days": 21,
            "params": json.dumps({"productDays": {"kalici_oje": 21, "jel": 28, "klasik_oje": 7}}),
            "channel": "SMS",
            "template": "{ad}, ojenizin ömrü doluyor ({gun} gün). {salon} sizi bekliyor 💅 {link}",
            "priority": 30,
        },
        {
            "name": "Kaş & kirpik sabit döngü",
            "service_id": None,
            "category_id": categories["kas-kirpik"],
            "formula": "FIXED",
            "base_days": 21,
            "params": "{}",
            "channel": "SMS",
            "template": "{ad}, {hizmet} için {gun} gün oldu. Randevu alalım mı? {link}",
            "priority": 20,
        },
        {
            "name": "Cilt bakımı mevsimsel",
            "service_id": None,
            "category_id": categories["cilt"],
            "formula": "SEASONAL",
            "base_days": 30,
            # Kis aylarinda cilt daha sik bakim ister -> carpan < 1.
            "params": json.dumps(
                {"monthFactors": {"1": 0.8, "2": 0.85, "6": 1.2, "7": 1.3, "8": 1.2, "12": 0.85}}
            ),
            "channel": "SMS",
            "template": "{ad}, cildinizin bakım zamanı geldi ({gun} gün). {link}",
            "priority": 20,
        },
        {
            "name": "Genel yenileme hatırlatması",
            "service_id": None,
            "category_id": None,
            "formula": "FIXED",
            "base_days": 45,
            "params": "{}",
            "channel": "SMS",
            "template": "{ad}, {hizmet} işleminizin üzerinden {gun} gün geçti. {salon} 🙂 {link}",
            "priority": 0,
        },
    ]

    reminder_rules: list[ReminderRuleSpec] = []
    for definition in reminder_defs:
        row = ReminderRule(branch_id=branch.id, pre_reminder_hours=24, **definition)
        db.add(row)
        db.flush()
        reminder_rules.append(
            ReminderRuleSpec(
                id=row.id,
                name=row.name,
                service_id=row.service_id,
                category_id=row.category_id,
                formula=row.formula,
                base_days=row.base_days,
                params=row.params,
                channel=row.channel,
                template=row.template,
                priority=row.priority,
                is_active=True,
            )
        )

    # -----------------------------------------------------------------
    # 9. Portfolyo
    # -----------------------------------------------------------------
    #
    # `photo` alani `frontend/public/photos/` altindaki gercek fotografa isaret
    # eder. Fotograf yoksa cizilmis yer tutucuya dusulur - galeri hicbir
    # kosulda bos kalmaz.
    portfolio_defs = [
        ("Balyaj — Küllü Kumral", "sac", 0, "is-balyaj.jpg",
         "Tek seansta 3 ton açma, küllü toner ile nötrleme. Bitişte ısı korumalı bakım maskesi."),
        ("Işıltı Fönü", "sac", 1, "is-fon.jpg",
         "Yıkama + hacim odaklı şekillendirme. Fırça ısısı saç tipine göre ayarlandı."),
        ("Uzun Saç Bakım Ritüeli", "sac", 0, "is-uzun-sac.jpg",
         "Uç bakımı, keratin destekli maske ve dalga şekillendirme."),
        ("Derin Nem Yıkama", "sac", 1, "is-yikama.jpg",
         "Sülfatsız şampuan + saç derisi masajı. Boyalı saçlarda renk ömrünü uzatır."),
        ("Fantezi Renk — Gül Kurusu", "sac", 0, "is-fantezi-renk.jpg",
         "Açma sonrası pigment uygulaması. Renk koruma şampuanı ile teslim edildi."),
        ("Nude Kalıcı Oje", "tirnak", 3, "is-nude-oje.jpg",
         "Kütikül bakımı sonrası tek renk kalıcı oje; simli aksan tırnak."),
        ("Kırmızı Nail Art", "tirnak", 2, "is-nail-art-kirmizi.jpg",
         "Elle çizim yazı detayı. Badem form, 25 gün dayanım."),
        ("Kahve Tonlarında Nail Art", "tirnak", 2, "is-nail-art-kahve.jpg",
         "Bal rengi geçişler ve altın folyo. Uygulama süresi 70 dk."),
        ("Fuşya Kalıcı Oje", "tirnak", 3, "is-fusya-oje.jpg",
         "Kısa oval form, yüksek pigmentli tek kat kapatma."),
        ("Kaş Tasarımı & Göz Makyajı", "kas-kirpik", 2, "is-makyaj.jpg",
         "Yüz oranına göre kaş formu, ardından günlük göz makyajı."),
        ("Hydrafacial Sonrası", "cilt", 1, "is-hydrafacial.jpg",
         "Derin temizlik + serum infüzyonu. Aynı gün makyaj yapılabilir."),
        ("Derin Temizlik Bakımı", "cilt", 0, "is-derin-temizlik.jpg",
         "Buhar, komedon temizliği ve yatıştırıcı kil maskesi."),
    ]
    for order, (title, category, staff_index, photo, description) in enumerate(portfolio_defs):
        # Yer tutucuya dusulurse gorselde yazi YOK: baslik zaten kartin
        # altinda yaziyor, gorselin kendisi sanat eseri gibi dursun.
        image_url = site_photo(photo) or write_placeholder_image(
            f"portfolio/{order + 1}.svg",
            title,
            order * 13 + 5,
        )
        db.add(
            PortfolioItem(
                branch_id=branch.id,
                category_id=categories[category],
                staff_id=staff_list[staff_index]["id"],
                title=title,
                image_url=image_url,
                description=description,
                sort_order=order,
            )
        )

    db.commit()

    # -----------------------------------------------------------------
    # 10. Musteriler
    # -----------------------------------------------------------------
    customers: list[Customer] = []
    for i in range(25):
        customer = Customer(
            phone=f"53210100{i:02d}",
            first_name=FIRST_NAMES[i % len(FIRST_NAMES)],
            last_name=LAST_NAMES[(i * 7) % len(LAST_NAMES)],
            email=None,
            birth_date=f"19{rng.int(80, 99)}-{rng.int(1, 12):02d}-{rng.int(1, 28):02d}",
            engagement_opt_in=rng.chance(0.85),
        )
        db.add(customer)
        customers.append(customer)
    db.flush()

    # Alerji / gizli not / albüm ornekleri
    db.add(
        Allergy(
            customer_id=customers[3].id,
            label="Amonyaklı boya",
            severity="HIGH",
            note="Saç derisinde yanma yapıyor; amonyaksız seri kullanılacak.",
        )
    )
    db.add(
        Allergy(
            customer_id=customers[11].id,
            label="Lateks",
            severity="MEDIUM",
            note="Nitril eldiven kullanılmalı.",
        )
    )
    db.add(
        CustomerNote(
            customer_id=customers[3].id,
            staff_id=staff_list[0]["id"],
            body="Dip boyada 30 volüm kullanma, 20 yeterli. Sohbeti sever, aceleye getirme.",
            visibility="STAFF_ONLY",
        )
    )

    color_tags = ["nude", "kirmizi", "fusya", "nude", "bordo", "pembe", "nude", "siyah"]
    for i, tag in enumerate(color_tags):
        image_url = write_placeholder_image(f"album/{i + 1}.svg", tag, (i + 1) * 3 + 11)
        db.add(
            CustomerPhoto(
                customer_id=customers[i % 5].id,
                staff_id=staff_list[2]["id"],
                image_url=image_url,
                note="Uygulama sonrası",
                color_tag=tag,
                created_at=now - timedelta(days=rng.int(5, 200)),
            )
        )

    db.commit()

    # -----------------------------------------------------------------
    # 11. Gecmis randevular (cakismasiz uretim)
    # -----------------------------------------------------------------
    print("▸ Geçmiş randevular üretiliyor...")

    #: Uretilen hucrelerin global kumesi - unique kisiti ihlal edilmesin.
    used_cells: set[tuple[str, int, str, int]] = set()
    created = 0
    completed_count = 0
    #: Firsat saati onbellegi icin gecmis randevular: (weekday, start, end)
    history_plans: list[tuple[int, int, int]] = []
    review_candidates: list[tuple[Appointment, list[str]]] = []

    package_pool: list[list[str]] = []
    for keys, weight in PACKAGE_DEFS:
        package_pool.extend([keys] * weight)

    day_offsets = list(range(-HISTORY_DAYS, 15))

    while created < HISTORY_APPOINTMENT_TARGET:
        offset = rng.pick(day_offsets)
        date = add_days_to_key(today_key, offset)
        weekday = weekday_of(date)

        package_keys = rng.pick(package_pool)
        candidates = [
            s for s in staff_list
            if all(k in s["skills"] for k in package_keys) and weekday not in s["off_weekdays"]
        ]
        if not candidates:
            continue
        staff = rng.pick(candidates)

        specs = [services[k]["spec"] for k in package_keys]
        layout = layout_package(specs, LayoutOptions(speed_factor=staff["speed_factor"]))

        hour = rng.weighted(START_HOUR_WEIGHTS)
        start_min = hour * 60 + rng.pick([0, 15, 30, 45])
        close_min = 1080 if weekday == 6 else CLOSE_MIN
        if start_min < OPEN_MIN or start_min + layout.total_min > close_min:
            continue

        customer = rng.pick(customers)

        cells = build_occupancy_cells(
            layout=layout,
            date=date,
            start_min=start_min,
            staff_id=staff["id"],
            customer_id=customer.id,
            exclusive_resource_ids=exclusive_resource_ids,
        )
        keys = [(c.owner_type, c.owner_id, c.date, c.cell_index) for c in cells]
        if any(k in used_cells for k in keys):
            continue

        # --- Durum: gecmis randevular tamamlanmis/gelinmemis sayilir ----
        if offset < 0:
            status = rng.weighted([("COMPLETED", 86), ("NO_SHOW", 6), ("CANCELLED", 8)])
        else:
            status = "CONFIRMED"

        is_opportunity = start_min < OPPORTUNITY_BEFORE_MIN
        discount_rate = OPPORTUNITY_DISCOUNT if is_opportunity else 0.0
        total_price = round(layout.total_price * (1 - discount_rate), 2)

        appointment = Appointment(
            branch_id=branch.id,
            customer_id=customer.id,
            staff_id=staff["id"],
            date=date,
            start_min=start_min,
            end_min=start_min + layout.total_min,
            status=status,
            total_price=total_price,
            discount_rate=discount_rate,
            is_opportunity=is_opportunity,
            version=0,
            created_at=to_datetime(date, start_min) - timedelta(days=rng.int(1, 12)),
        )
        db.add(appointment)
        db.flush()

        for item in layout.items:
            db.add(
                AppointmentItem(
                    appointment_id=appointment.id,
                    service_id=item.service.id,
                    sort_order=item.sort_order,
                    offset_min=item.offset_min,
                    active_before_min=item.active_before_min,
                    passive_min=item.passive_min,
                    active_after_min=item.active_after_min,
                    buffer_min=item.buffer_min,
                    price=item.price,
                )
            )
        for usage in layout.resource_usage:
            db.add(
                AppointmentResource(
                    appointment_id=appointment.id,
                    resource_id=usage.resource_id,
                    quantity=usage.quantity,
                    start_min=int(usage.interval.start + start_min),
                    end_min=int(usage.interval.end + start_min),
                )
            )

        # Iptal/gelmedi olanlar slotu isgal etmez (uygulamadaki davranisin aynisi).
        if status not in ("CANCELLED", "NO_SHOW"):
            used_cells.update(keys)
            for c in cells:
                db.add(
                    OccupancyCell(
                        owner_type=c.owner_type,
                        owner_id=c.owner_id,
                        date=c.date,
                        cell_index=c.cell_index,
                        kind="APPOINTMENT",
                        appointment_id=appointment.id,
                    )
                )

        # --- Yan etkiler (gecmis icin) ----------------------------------
        starts_at = to_datetime(date, start_min)
        if offset < 0:
            outcome = {
                "COMPLETED": "COMPLETED",
                "NO_SHOW": "NO_SHOW",
                "CANCELLED": "LATE_CANCEL" if rng.chance(0.4) else None,
            }[status]
            if outcome:
                db.add(
                    PhoneRiskEvent(
                        phone_hash=hash_phone(customer.phone),
                        outcome=outcome,
                        occurred_at=starts_at,
                        salon_id=salon.id,
                    )
                )

        if status == "COMPLETED":
            completed_count += 1
            earned = calculate_earned_points(
                amount=total_price,
                days_since_last_visit=rng.int(10, 150),
                current_tier=tier_for(customer.loyalty_points),
                opportunity_discount_rate=discount_rate,
            )
            db.add(
                LoyaltyEntry(
                    customer_id=customer.id,
                    appointment_id=appointment.id,
                    delta=earned.points,
                    reason="OPPORTUNITY_BONUS" if is_opportunity else "SPEND",
                    breakdown=json.dumps(earned.breakdown),
                    created_at=starts_at,
                )
            )
            customer.loyalty_points = round(customer.loyalty_points + earned.points, 2)
            customer.tier = tier_for(customer.loyalty_points)

            if rng.chance(0.18):
                review_candidates.append(
                    (appointment, [services[k]["def"]["name"] for k in package_keys])
                )

        # --- Doluluk istatistigi (firsat saatleri icin) ------------------
        if offset < 0 and status != "CANCELLED":
            history_plans.append((weekday, start_min, start_min + layout.total_min))

        created += 1
        if created % 100 == 0:
            db.commit()

    db.commit()

    # --- Firsat saati onbellegi (occupancy_stat) -----------------------
    #
    # Doluluk **personel-saat dilimi** olarak sayilir:
    #   payda (total) = her acik gun x o gun calisan personel sayisi
    #   pay   (busy)  = randevunun kapladigi her saat dilimi icin 1
    # ``sample_size`` paydadir; Bayes shrinkage'in "bu kova ne kadar iyi
    # gozlemlenmis" girdisi budur (sabit bir sayi verilirse daraltma
    # anlamsizlasir).
    buckets: dict[tuple[int, int], list[int]] = {}

    for day_offset in range(HISTORY_DAYS, 0, -1):
        date = add_days_to_key(today_key, -day_offset)
        weekday = weekday_of(date)
        if weekday == 0:  # Pazar kapali
            continue
        close_min = 1080 if weekday == 6 else CLOSE_MIN
        working_staff = sum(1 for s in staff_list if weekday not in s["off_weekdays"])
        for slot in range(OPEN_MIN, close_min, 60):
            buckets.setdefault((weekday, slot), [0, 0])[1] += working_staff

    for weekday, start_min, end_min in history_plans:
        first = (start_min // 60) * 60
        for slot in range(first, end_min, 60):
            if slot < OPEN_MIN or slot >= CLOSE_MIN:
                continue
            buckets.setdefault((weekday, slot), [0, 0])[0] += 1

    for (weekday, slot_min), (busy, total) in buckets.items():
        db.add(
            OccupancyStat(
                branch_id=branch.id,
                weekday=weekday,
                slot_min=slot_min,
                occupancy=round(min(1.0, busy / total), 4) if total else 0.0,
                sample_size=total,
            )
        )

    # -----------------------------------------------------------------
    # 12. Yorumlar (yalnizca TAMAMLANMIS randevulardan)
    # -----------------------------------------------------------------
    texts = list(REVIEW_TEXTS)
    rng.shuffle(texts)
    for index, (appointment, service_names) in enumerate(review_candidates[: len(texts) * 2]):
        customer = db.get(Customer, appointment.customer_id)
        rating = rng.weighted([(5, 62), (4, 26), (3, 8), (2, 3), (1, 1)])
        db.add(
            Review(
                branch_id=branch.id,
                customer_id=customer.id,
                staff_id=appointment.staff_id,
                appointment_id=appointment.id,
                author_name=f"{customer.first_name} {(customer.last_name or ' ')[0].upper()}.",
                rating=rating,
                comment=texts[index % len(texts)],
                service_names=", ".join(service_names),
                is_verified=True,
                is_published=True,
                is_featured=index < 3 and rating == 5,
                created_at=to_datetime(appointment.date, appointment.end_min)
                + timedelta(days=rng.int(1, 5)),
            )
        )

    # -----------------------------------------------------------------
    # 13. Bekleyen hatirlatma ornekleri
    # -----------------------------------------------------------------
    last_completed = (
        db.query(Appointment)
        .filter(Appointment.status == "COMPLETED")
        .order_by(Appointment.date.desc())
        .limit(5)
        .all()
    )
    for appointment in last_completed:
        item = db.query(AppointmentItem).filter(
            AppointmentItem.appointment_id == appointment.id
        ).first()
        if item is None:
            continue
        service = db.get(Service, item.service_id)
        customer = db.get(Customer, appointment.customer_id)
        reminder = resolve_reminder(
            reminder_rules,
            ReminderContext(
                service_id=service.id,
                category_id=service.category_id,
                service_name=service.name,
                customer_name=customer.first_name,
                performed_at=to_datetime(appointment.date, appointment.end_min),
                recommended_repeat_days=service.recommended_repeat_days,
                salon_name=salon.name,
                booking_url="/randevu",
            ),
            appointment.id,
        )
        if reminder:
            db.add(
                ScheduledNotification(
                    customer_id=customer.id,
                    rule_id=reminder.rule_id,
                    channel=reminder.channel,
                    body=reminder.body,
                    due_at=reminder.due_at,
                    dedupe_key=reminder.dedupe_key,
                )
            )

    db.commit()

    review_count = db.query(Review).count()
    cell_count = db.query(OccupancyCell).count()

    print("✔ Seed tamamlandı.")
    print(f"  {created} randevu ({completed_count} tamamlanmış), {cell_count} doluluk hücresi")
    print(f"  {len(customers)} müşteri, {review_count} yorum, {len(services)} hizmet")
    print()
    print("  Demo giriş bilgileri")
    print("  ---------------------------------------------")
    for definition in STAFF_DEFS:
        print(f"  {definition['role']:<8} {definition['phone']}  {definition['password']}")
    otp_note = (
        f"sabit kod: {config.dev_otp_code}"
        if config.dev_otp_code
        else "kod sunucu konsoluna yazılır ve yanıtta devCode olarak döner"
    )
    print(f"  Müşteri girişi şifresizdir: 05321010000 … 05321010024 ({otp_note})")

    db.close()


if __name__ == "__main__":
    main()
