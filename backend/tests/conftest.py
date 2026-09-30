"""Test altyapisi.

Testler AYRI bir PostgreSQL veritabani kullanir (varsayilan: Docker'daki
``aurora_test``, bkz. ``docker-compose.yml``); gelistirme veritabani
(``aurora``) etkilenmez. Baska bir adres icin ``TEST_DATABASE_URL`` verin.

Bu veritabanindaki TUM tablolar test basinda silinir. Yanlislikla gercek
bir veritabani verilmesine karsi, adi ``_test`` ile bitmeyen veritabaninda
testler calismayi reddeder.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://aurora:aurora@localhost:5432/aurora_test"
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise SystemExit(
        f"TEST_DATABASE_URL bir test veritabani olmali (adi _test ile bitmeli): {TEST_DATABASE_URL}"
    )

# Uygulama modulleri import edilmeden ONCE ayarlanmali (config import aninda okunur).
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["APP_ENV"] = "test"
os.environ["DEV_OTP_CODE"] = "123456"
os.environ["CRON_SECRET"] = "test-cron-secret-" + "x" * 32
# Testler asla gercek mesaj gondermez; WhatsApp testleri sahte sunucu kullanir.
os.environ["NOTIFICATION_DRIVER"] = "console"
os.environ["WHATSAPP_SEND_INTERVAL_MS"] = "0"
# Gelistiricinin lokal .env'indeki Evolution ayarlari testlere sizmasin.
for _key in (
    "EVOLUTION_API_URL", "EVOLUTION_API_KEY", "EVOLUTION_INSTANCE", "EVOLUTION_WEBHOOK_URL",
):
    os.environ[_key] = ""
os.environ["UPLOAD_DIR"] = str(Path(__file__).resolve().parent / "uploads")

import pytest  # noqa: E402
from sqlalchemy import MetaData, delete  # noqa: E402

from app.auth.password import hash_password  # noqa: E402
from app.core.types import ResourceNeed, ServiceSpec  # noqa: E402
from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.models import (  # noqa: E402
    Appointment,
    AppointmentItem,
    AppointmentResource,
    Branch,
    Customer,
    InventoryItem,
    LoyaltyEntry,
    OccupancyCell,
    PhoneRiskEvent,
    RateLimitHit,
    Resource,
    ScheduledNotification,
    Salon,
    Service,
    ServiceCategory,
    ServiceConsumable,
    ServiceResource,
    SlotLock,
    Staff,
    StaffService,
    StockMovement,
    VerificationCode,
    WhatsappContact,
    WorkingHour,
)


@pytest.fixture(scope="session", autouse=True)
def _database():
    # Onceki kosudan kalan semayi (alembic_version dahil) temizle.
    stale = MetaData()
    stale.reflect(bind=engine)
    stale.drop_all(bind=engine)
    init_db()
    yield
    engine.dispose()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def clean_db(db):
    """Her test temiz bir veritabaniyla baslar."""
    for model in (
        RateLimitHit, VerificationCode, ScheduledNotification, WhatsappContact,
        OccupancyCell, SlotLock, StockMovement, LoyaltyEntry, PhoneRiskEvent,
        AppointmentResource, AppointmentItem, Appointment, ServiceConsumable,
        InventoryItem, ServiceResource, StaffService, WorkingHour, Resource,
        Service, ServiceCategory, Staff, Customer, Branch, Salon,
    ):
        db.execute(delete(model))
    db.commit()
    return db


@pytest.fixture()
def salon(clean_db):
    """Minimal ama gercekci bir salon: 2 usta, 3 hizmet, 1 tekil kaynak.

    Hizmetler ``seed.py`` ile ayni sure profillerini kullanir:
      * boya      : 30 aktif + 40 pasif + 20 aktif + 10 buffer (golge sahibi)
      * kas       : 15 dk, golge misafiri olabilir
      * manikur   : 40 dk
    """
    db = clean_db

    salon_row = Salon(name="Test Salon", slug="test-salon", phone="5550000000")
    db.add(salon_row)
    db.flush()

    branch = Branch(
        salon_id=salon_row.id, name="Merkez", open_minute=540, close_minute=1200
    )
    db.add(branch)
    db.flush()

    category = ServiceCategory(branch_id=branch.id, name="Genel", slug="genel")
    db.add(category)
    db.flush()

    chair = Resource(branch_id=branch.id, name="Koltuk", kind="CHAIR", capacity=1)
    db.add(chair)
    db.flush()

    boya = Service(
        branch_id=branch.id, category_id=category.id, name="Saç Boyası", price=1200,
        active_before_min=30, passive_min=40, active_after_min=20, buffer_min=10,
        shadow_host_allowed=True, shadow_guest_allowed=False, recommended_repeat_days=35,
    )
    kas = Service(
        branch_id=branch.id, category_id=category.id, name="Kaş Alma", price=150,
        active_before_min=15, passive_min=0, active_after_min=0, buffer_min=0,
        shadow_host_allowed=False, shadow_guest_allowed=True, recommended_repeat_days=21,
    )
    manikur = Service(
        branch_id=branch.id, category_id=category.id, name="Manikür", price=350,
        active_before_min=40, passive_min=0, active_after_min=0, buffer_min=0,
        shadow_host_allowed=False, shadow_guest_allowed=False, recommended_repeat_days=21,
    )
    db.add_all([boya, kas, manikur])
    db.flush()

    db.add(ServiceResource(service_id=boya.id, resource_id=chair.id, only_during_active=False))

    staff_a = Staff(
        branch_id=branch.id, name="Elif", phone="5551110001",
        password_hash=hash_password("admin123"), role="OWNER", display_order=0,
    )
    staff_b = Staff(
        branch_id=branch.id, name="Merve", phone="5551110002",
        password_hash=hash_password("merve123"), role="STAFF", display_order=1,
    )
    db.add_all([staff_a, staff_b])
    db.flush()

    for staff in (staff_a, staff_b):
        for weekday in range(7):
            db.add(
                WorkingHour(
                    staff_id=staff.id, weekday=weekday, start_min=540, end_min=1200,
                    is_working=True,
                )
            )
        for service in (boya, kas, manikur):
            db.add(
                StaffService(staff_id=staff.id, service_id=service.id, speed_factor=1.0)
            )

    customer = Customer(phone="5321010000", first_name="Ayşe", last_name="Yılmaz")
    other_customer = Customer(phone="5321010001", first_name="Zeynep", last_name="Kaya")
    db.add_all([customer, other_customer])

    db.commit()

    return {
        "salon": salon_row,
        "branch": branch,
        "category": category,
        "chair": chair,
        "boya": boya,
        "kas": kas,
        "manikur": manikur,
        "staff_a": staff_a,
        "staff_b": staff_b,
        "customer": customer,
        "other_customer": other_customer,
    }


def spec_of(service: Service, resources: tuple[ResourceNeed, ...] = ()) -> ServiceSpec:
    """Test icin ORM satirini saf ``ServiceSpec``e cevirir."""
    return ServiceSpec(
        id=service.id,
        name=service.name,
        active_before_min=service.active_before_min,
        passive_min=service.passive_min,
        active_after_min=service.active_after_min,
        buffer_min=service.buffer_min,
        shadow_host_allowed=service.shadow_host_allowed,
        shadow_guest_allowed=service.shadow_guest_allowed,
        price=service.price,
        resources=resources,
    )
