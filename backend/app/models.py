"""
=====================================================================
VERI MODELI - Aurora Salon Randevu Sistemi (FastAPI surumu)
=====================================================================

``prisma/schema.prisma`` dosyasinin SQLAlchemy karsiligi. Tablo ve alan
adlari snake_case'e cevrildi; anlam ve kisitlar birebir korundu.

Prisma semasiyla ayni tercih:
  * ``enum`` yerine dokumante edilmis ``String`` alanlar kullanilir
    (yeni bir durum eklemek migration gerektirmez).
  * JSON alanlar JSON metni tutan ``String`` alanlardir.

One cikan uc tablo:
  * ``occupancy_cell``   - yaris kosulu savunmasinin veritabani tarafi
  * ``phone_risk_event`` - salonlar arasi no-show havuzu (ham numara YOK)
  * ``review``           - vitrindeki sosyal kanitin kaynagi
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .time_utils import now_local


def _now() -> datetime:
    return now_local()


# ---------------------------------------------------------------------
# 1. ORGANIZASYON
# ---------------------------------------------------------------------


class Salon(Base):
    __tablename__ = "salon"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    #: WhatsApp'tan ilk kez yazan kisiye otomatik karsilama mesaji gitsin mi?
    whatsapp_welcome_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa_true()
    )
    #: Karsilama metni; bossa varsayilan metin kullanilir.
    #: Yer tutucular: {salon}, {link}. Bkz. ``services/whatsapp_inbound.py``.
    whatsapp_welcome_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    branches: Mapped[list["Branch"]] = relationship(back_populates="salon")


class Branch(Base):
    __tablename__ = "branch"

    id: Mapped[int] = mapped_column(primary_key=True)
    salon_id: Mapped[int] = mapped_column(ForeignKey("salon.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(300), default=None)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul")

    #: Varsayilan acilis/kapanis (gun ici dakika: 09:00 -> 540)
    open_minute: Mapped[int] = mapped_column(Integer, default=540)
    close_minute: Mapped[int] = mapped_column(Integer, default=1200)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    salon: Mapped[Salon] = relationship(back_populates="branches")


# ---------------------------------------------------------------------
# 2. HIZMET & KAYNAK
# ---------------------------------------------------------------------


class ServiceCategory(Base):
    __tablename__ = "service_category"
    __table_args__ = (UniqueConstraint("branch_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120))
    #: Portfolyo filtrelemesinde de kullanilir
    icon: Mapped[str | None] = mapped_column(String(16), default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    services: Mapped[list["Service"]] = relationship(back_populates="category")


class Service(Base):
    """Hizmet. Sure uc parcaya bolunmustur - SHADOW BLOCKING'in temeli:

        |<-- active_before_min -->|<-- passive_min -->|<-- active_after_min -->|
        ^ usta mesgul              ^ usta SERBEST      ^ usta mesgul

    Orn. sac boyasi: 30 + 40 + 20 = 90 dk. Ortadaki 40 dakikada usta
    baska bir kisa hizmet (kas alma vb.) yapabilir.
    """

    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_category.id", ondelete="SET NULL"), default=None
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    price: Mapped[float] = mapped_column(Float)

    #: Ustanin fiziksel mudahalesinin gerektigi ilk blok (dk)
    active_before_min: Mapped[int] = mapped_column(Integer, default=30)
    #: Ustanin serbest oldugu bekleme penceresi (dk) - 0 ise golge yok
    passive_min: Mapped[int] = mapped_column(Integer, default=0)
    #: Bekleme sonrasi aktif blok (dk)
    active_after_min: Mapped[int] = mapped_column(Integer, default=0)
    #: Randevu sonrasi temizlik/hazirlik tamponu (dk)
    buffer_min: Mapped[int] = mapped_column(Integer, default=0)

    #: Pasif pencere baska bir hizmete acilabilir mi?
    shadow_host_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Bu hizmet baska bir hizmetin pasif penceresine yerlestirilebilir mi?
    shadow_guest_allowed: Mapped[bool] = mapped_column(Boolean, default=False)

    #: Hatirlatma kural motoru icin taban tekrar araligi (gun)
    recommended_repeat_days: Mapped[int | None] = mapped_column(Integer, default=None)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    category: Mapped[ServiceCategory | None] = relationship(back_populates="services")
    requirements: Mapped[list["ServiceResource"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )
    consumables: Mapped[list["ServiceConsumable"]] = relationship(back_populates="service")
    staff_links: Mapped[list["StaffService"]] = relationship(back_populates="service")


class Resource(Base):
    """Cihaz / koltuk / oda gibi paylasilan kaynak."""

    __tablename__ = "resource"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    #: "DEVICE" | "CHAIR" | "ROOM" | "SINK"
    kind: Mapped[str] = mapped_column(String(20), default="DEVICE")
    #: Ayni anda kac randevuya hizmet verebilir (paralel kapasite)
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ServiceResource(Base):
    """Hizmet -> Kaynak gereksinimi.

    ``only_during_active=False`` ise pasif pencerede de kaynak dolu
    sayilir (orn. boya bekleyen musteri koltukta oturur).
    """

    __tablename__ = "service_resource"
    __table_args__ = (UniqueConstraint("service_id", "resource_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id", ondelete="CASCADE"))
    resource_id: Mapped[int] = mapped_column(ForeignKey("resource.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    only_during_active: Mapped[bool] = mapped_column(Boolean, default=False)

    service: Mapped[Service] = relationship(back_populates="requirements")
    resource: Mapped[Resource] = relationship()


# ---------------------------------------------------------------------
# 3. PERSONEL
# ---------------------------------------------------------------------


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    #: "OWNER" | "MANAGER" | "STAFF"
    role: Mapped[str] = mapped_column(String(20), default="STAFF")
    photo_url: Mapped[str | None] = mapped_column(String(300), default=None)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    working_hours: Mapped[list["WorkingHour"]] = relationship(back_populates="staff")
    services: Mapped[list["StaffService"]] = relationship(back_populates="staff")


class WorkingHour(Base):
    __tablename__ = "working_hour"
    __table_args__ = (UniqueConstraint("staff_id", "weekday"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))
    #: 0 = Pazar ... 6 = Cumartesi
    weekday: Mapped[int] = mapped_column(Integer)
    start_min: Mapped[int] = mapped_column(Integer)
    end_min: Mapped[int] = mapped_column(Integer)
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)

    staff: Mapped[Staff] = relationship(back_populates="working_hours")


class TimeOff(Base):
    __tablename__ = "time_off"
    __table_args__ = (Index("ix_time_off_staff_date", "staff_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))
    #: "YYYY-MM-DD"
    date: Mapped[str] = mapped_column(String(10))
    #: None ise tum gun izinli
    start_min: Mapped[int | None] = mapped_column(Integer, default=None)
    end_min: Mapped[int | None] = mapped_column(Integer, default=None)
    reason: Mapped[str | None] = mapped_column(String(200), default=None)


class StaffService(Base):
    __tablename__ = "staff_service"
    __table_args__ = (UniqueConstraint("staff_id", "service_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id", ondelete="CASCADE"))
    #: Personel bazli fiyat override'i (None ise hizmetin fiyati)
    price: Mapped[float | None] = mapped_column(Float, default=None)
    #: Personel bazli sure carpani (deneyimli usta daha hizli) - 1.0 = standart
    speed_factor: Mapped[float] = mapped_column(Float, default=1.0)

    staff: Mapped[Staff] = relationship(back_populates="services")
    service: Mapped[Service] = relationship(back_populates="staff_links")


class StaffSession(Base):
    __tablename__ = "staff_session"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------
# 4. MUSTERI & CRM
# ---------------------------------------------------------------------


class Customer(Base):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Normalize edilmis 10 haneli numara (5XXXXXXXXX)
    phone: Mapped[str] = mapped_column(String(10), unique=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str | None] = mapped_column(String(80), default=None)
    email: Mapped[str | None] = mapped_column(String(160), default=None)
    birth_date: Mapped[str | None] = mapped_column(String(10), default=None)

    #: Uyelik: misafir gezinme mumkundur, randevu icin uyelik gerekir
    is_member: Mapped[bool] = mapped_column(Boolean, default=True)

    #: Sadakat - defterden turetilir, hizli okuma icin denormalize edilir
    loyalty_points: Mapped[float] = mapped_column(Float, default=0)
    #: "BRONZ" | "GUMUS" | "ALTIN" | "VIP"
    tier: Mapped[str] = mapped_column(String(10), default="BRONZ")

    #: Engagement modulu tercihi (kullanici kapatabilir)
    engagement_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CustomerSession(Base):
    __tablename__ = "customer_session"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class VerificationCode(Base):
    __tablename__ = "verification_code"
    __table_args__ = (Index("ix_verification_phone_expires", "phone", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(8))
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), default=None
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    #: Bu koda yapilan yanlis deneme sayisi. Sinira ulasinca kod yakilir.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Allergy(Base):
    """ALERJI IKAZ KUTUSU - randevu olusturulurken kirmizi uyari."""

    __tablename__ = "allergy"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(120))
    #: "LOW" | "MEDIUM" | "HIGH"
    severity: Mapped[str] = mapped_column(String(10), default="HIGH")
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CustomerNote(Base):
    """GIZLI USTA NOTLARI - ``visibility`` alani ile korunur.

    "STAFF_ONLY" notlar musteri API'lerinden ASLA donmez.
    """

    __tablename__ = "customer_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customer.id", ondelete="CASCADE"), index=True
    )
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), default=None
    )
    body: Mapped[str] = mapped_column(Text)
    #: "STAFF_ONLY" | "SHARED"
    visibility: Mapped[str] = mapped_column(String(12), default="STAFF_ONLY")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    staff: Mapped[Staff | None] = relationship()


class CustomerPhoto(Base):
    """ISLEM GECMISI ALBUMU - usta randevu sonunda fotograf + not yukler."""

    __tablename__ = "customer_photo"
    __table_args__ = (Index("ix_customer_photo_customer_created", "customer_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id", ondelete="CASCADE"))
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="SET NULL"), default=None
    )
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), default=None
    )
    #: uploads altindaki lokal dosya yolu
    image_url: Mapped[str] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text, default=None)
    #: Renk psikolojisi analizi bu alandan beslenir (orn. "kirmizi", "nude")
    color_tag: Mapped[str | None] = mapped_column(String(60), default=None)
    #: Urun/teknik bilgisi
    product_info: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    staff: Mapped[Staff | None] = relationship()


# ---------------------------------------------------------------------
# 5. RANDEVU
# ---------------------------------------------------------------------


class Appointment(Base):
    """Randevu. Birden fazla hizmet (paket) icerebilir ve takvimde
    KESINTISIZ tek blok kaplar."""

    __tablename__ = "appointment"
    __table_args__ = (
        Index("ix_appointment_branch_date", "branch_id", "date"),
        Index("ix_appointment_staff_date", "staff_id", "date"),
        Index("ix_appointment_customer", "customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id", ondelete="CASCADE"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))

    #: "YYYY-MM-DD" - izgara hesaplari gun-yerel dakika uzerinden yapilir
    date: Mapped[str] = mapped_column(String(10))
    #: Gun ici baslangic dakikasi (09:30 -> 570)
    start_min: Mapped[int] = mapped_column(Integer)
    #: Gun ici bitis dakikasi (buffer dahil)
    end_min: Mapped[int] = mapped_column(Integer)

    #: "PENDING" | "CONFIRMED" | "COMPLETED" | "CANCELLED" | "NO_SHOW"
    status: Mapped[str] = mapped_column(String(12), default="CONFIRMED")

    total_price: Mapped[float] = mapped_column(Float, default=0)
    discount_rate: Mapped[float] = mapped_column(Float, default=0)
    #: Firsat saati indirimi uygulandiysa True
    is_opportunity: Mapped[bool] = mapped_column(Boolean, default=False)

    #: OPTIMISTIC LOCKING - her guncellemede +1 artirilir. Guncelleme
    #: ``WHERE id = ? AND version = ?`` ile yapilir; eslesmezse baska biri
    #: kaydi degistirmis demektir ve islem reddedilir.
    version: Mapped[int] = mapped_column(Integer, default=0)

    #: Bu randevu baska bir randevunun pasif (golge) penceresine
    #: yerlestirildiyse ana randevunun id'si.
    shadow_parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="SET NULL"), default=None
    )

    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    customer: Mapped[Customer] = relationship()
    staff: Mapped[Staff] = relationship()
    branch: Mapped[Branch] = relationship()
    items: Mapped[list["AppointmentItem"]] = relationship(
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentItem.sort_order",
    )
    resources: Mapped[list["AppointmentResource"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )
    design_refs: Mapped[list["DesignReference"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )


class AppointmentItem(Base):
    """Randevudaki tek bir hizmet.

    Sure parcalari randevu aninda kopyalanir (hizmet tanimi sonradan
    degisse bile gecmis bozulmaz).
    """

    __tablename__ = "appointment_item"
    __table_args__ = (Index("ix_appointment_item_appointment", "appointment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointment.id", ondelete="CASCADE"))
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    #: Randevu baslangicina gore bu hizmetin ofseti (dk)
    offset_min: Mapped[int] = mapped_column(Integer)
    active_before_min: Mapped[int] = mapped_column(Integer)
    passive_min: Mapped[int] = mapped_column(Integer)
    active_after_min: Mapped[int] = mapped_column(Integer)
    buffer_min: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float)

    appointment: Mapped[Appointment] = relationship(back_populates="items")
    service: Mapped[Service] = relationship()


class AppointmentResource(Base):
    __tablename__ = "appointment_resource"
    __table_args__ = (Index("ix_appointment_resource_resource", "resource_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointment.id", ondelete="CASCADE"))
    resource_id: Mapped[int] = mapped_column(ForeignKey("resource.id", ondelete="CASCADE"))
    start_min: Mapped[int] = mapped_column(Integer)
    end_min: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    appointment: Mapped[Appointment] = relationship(back_populates="resources")


class DesignReference(Base):
    """TASARIM YUKLEME - musterinin referans gorseli (dosya veya link)."""

    __tablename__ = "design_reference"
    __table_args__ = (Index("ix_design_reference_appointment", "appointment_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointment.id", ondelete="CASCADE"))
    #: "UPLOAD" | "LINK"
    source: Mapped[str] = mapped_column(String(10))
    #: UPLOAD ise lokal dosya yolu, LINK ise URL
    url: Mapped[str] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    appointment: Mapped[Appointment] = relationship(back_populates="design_refs")


# ---------------------------------------------------------------------
# 6. ESZAMANLILIK KALKANI
# ---------------------------------------------------------------------


class SlotLock(Base):
    """Soft-lock kaydi.

    Kullanici "Bu saati tut" dediginde olusturulur ve ``expires_at``
    (varsayilan +5 dk) gecince gecersiz sayilir.
    """

    __tablename__ = "slot_lock"
    __table_args__ = (
        Index("ix_slot_lock_staff_date", "staff_id", "date"),
        Index("ix_slot_lock_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer)
    staff_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String(10))
    start_min: Mapped[int] = mapped_column(Integer)
    end_min: Mapped[int] = mapped_column(Integer)
    #: Kilidi tutan tarayici oturumu / musteri
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, default=None)
    #: Kilit randevuya donustuyse
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class OccupancyCell(Base):
    """DOLULUK HUCRESI - yaris kosulu savunmasinin VERITABANI seviyesindeki
    garantisi burada.

    Zaman 5 dakikalik hucrelere bolunur (``cell_index = dakika // 5``).
    Bir randevu veya soft-lock, kapladigi her hucre icin bir satir yazar.
    ``UNIQUE(owner_type, owner_id, date, cell_index)`` sayesinde ayni
    ustanin ayni 5 dakikasina ikinci bir kayit yazmak VERITABANI
    TARAFINDAN reddedilir.

    SHADOW BLOCKING burada dogal olarak calisir: bir hizmetin pasif
    penceresi icin STAFF hucresi YAZILMAZ (usta serbesttir), ama CUSTOMER
    ve gerekiyorsa RESOURCE hucreleri yazilir.
    """

    __tablename__ = "occupancy_cell"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", "date", "cell_index", name="uq_occupancy_cell"),
        Index("ix_occupancy_date_owner", "date", "owner_type"),
        Index("ix_occupancy_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    #: "STAFF" | "RESOURCE" | "CUSTOMER"
    owner_type: Mapped[str] = mapped_column(String(10))
    owner_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String(10))
    #: gun ici dakika / 5
    cell_index: Mapped[int] = mapped_column(Integer)

    #: "APPOINTMENT" | "LOCK"
    kind: Mapped[str] = mapped_column(String(12))

    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="CASCADE"), default=None
    )
    lock_id: Mapped[int | None] = mapped_column(
        ForeignKey("slot_lock.id", ondelete="CASCADE"), default=None
    )
    #: LOCK turu icin TTL; suresi gecmis hucreler yazma aninda temizlenir
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------
# 7. GOLGE RISK SKORU (KVKK uyumlu, salonlar arasi)
# ---------------------------------------------------------------------


class PhoneRiskEvent(Base):
    """Salonlar arasi no-show gecmisi.

    KVKK: telefon numarasi burada ACIK tutulmaz - ``phone_hash`` =
    HMAC-SHA256(normalize(phone), PHONE_HASH_SECRET). ``salon_id``
    yalnizca veri sahipligi icindir ve HICBIR API yanitinda donmez.
    """

    __tablename__ = "phone_risk_event"
    __table_args__ = (Index("ix_phone_risk_hash_occurred", "phone_hash", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_hash: Mapped[str] = mapped_column(String(64))
    #: "COMPLETED" | "NO_SHOW" | "LATE_CANCEL"
    outcome: Mapped[str] = mapped_column(String(12))
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    #: Veri sahipligi icin; DISARIYA ASLA SIZDIRILMAZ
    salon_id: Mapped[int | None] = mapped_column(
        ForeignKey("salon.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------
# 8. STOK
# ---------------------------------------------------------------------


class InventoryItem(Base):
    __tablename__ = "inventory_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    #: "ml" | "adet" | "gram"
    unit: Mapped[str] = mapped_column(String(10), default="adet")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    #: Bu seviyenin altina ininca admin panelde uyari
    critical_level: Mapped[float] = mapped_column(Float, default=0)
    cost_per_unit: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    used_by: Mapped[list["ServiceConsumable"]] = relationship(back_populates="item")


class ServiceConsumable(Base):
    """Hizmet -> sarf malzemesi recetesi."""

    __tablename__ = "service_consumable"
    __table_args__ = (UniqueConstraint("service_id", "item_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id", ondelete="CASCADE"))
    qty_per_use: Mapped[float] = mapped_column(Float)

    service: Mapped[Service] = relationship(back_populates="consumables")
    item: Mapped[InventoryItem] = relationship(back_populates="used_by")


class StockMovement(Base):
    __tablename__ = "stock_movement"
    __table_args__ = (
        #: Ayni randevunun stogu iki kez dusmesini engelleyen idempotency anahtari
        UniqueConstraint("appointment_id", "item_id", name="uq_stock_movement_appointment_item"),
        Index("ix_stock_movement_item_created", "item_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id", ondelete="CASCADE"))
    #: Negatif = dusum (tuketim), pozitif = giris (satin alma)
    delta: Mapped[float] = mapped_column(Float)
    #: "APPOINTMENT_COMPLETED" | "PURCHASE" | "MANUAL_ADJUST" | "WASTE"
    reason: Mapped[str] = mapped_column(String(30))
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="SET NULL"), default=None
    )
    note: Mapped[str | None] = mapped_column(String(300), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ---------------------------------------------------------------------
# 9. SADAKAT & KAMPANYA
# ---------------------------------------------------------------------


class LoyaltyEntry(Base):
    """Puan hareketi defteri. ``customer.loyalty_points`` bundan turetilir."""

    __tablename__ = "loyalty_entry"
    __table_args__ = (Index("ix_loyalty_customer_created", "customer_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id", ondelete="CASCADE"))
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="SET NULL"), default=None
    )
    #: Kazanilan (+) veya harcanan/eriyen (-) puan
    delta: Mapped[float] = mapped_column(Float)
    #: "SPEND" | "FREQUENCY" | "OPPORTUNITY_BONUS" | "DECAY" | "REDEEM" | "MANUAL"
    reason: Mapped[str] = mapped_column(String(24))
    #: Formul girdilerinin JSON metni (denetlenebilirlik icin)
    breakdown: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Campaign(Base):
    """Algoritmik hedefleme: manuel kupon yerine segment + puan kosullari."""

    __tablename__ = "campaign"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    #: "DISCOUNT_PERCENT" | "FREE_SERVICE" | "BONUS_POINTS"
    kind: Mapped[str] = mapped_column(String(20))
    #: Odul degeri (yuzde / puan / hizmet id)
    value: Mapped[float] = mapped_column(Float, default=0)

    #: Hedefleme kurali - JSON metni
    target_rule: Mapped[str] = mapped_column(Text)

    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class CampaignGrant(Base):
    __tablename__ = "campaign_grant"
    __table_args__ = (UniqueConstraint("campaign_id", "customer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaign.id", ondelete="CASCADE"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id", ondelete="CASCADE"))
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


# ---------------------------------------------------------------------
# 10. BILDIRIM KURAL MOTORU
# ---------------------------------------------------------------------


class ReminderRule(Base):
    """Hatirlatma kurallari - hard-code YOK, yapilandirilabilir tablo."""

    __tablename__ = "reminder_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    #: Kural bu hizmete ozel (oncelikli)
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("service.id", ondelete="CASCADE"), default=None
    )
    #: veya bu kategoriye ait tum hizmetlere
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_category.id", ondelete="CASCADE"), default=None
    )

    #: "FIXED" | "GROWTH" | "PRODUCT_LIFETIME" | "SEASONAL"
    formula: Mapped[str] = mapped_column(String(20), default="FIXED")
    base_days: Mapped[int] = mapped_column(Integer)
    #: Formul parametreleri, JSON metni
    params: Mapped[str] = mapped_column(Text, default="{}")

    #: Randevu saatinden kac saat once on-hatirlatma
    pre_reminder_hours: Mapped[int | None] = mapped_column(Integer, default=24)

    #: "SMS" | "WHATSAPP" | "PUSH" | "EMAIL"
    channel: Mapped[str] = mapped_column(String(10), default="SMS")
    template: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    service: Mapped[Service | None] = relationship()
    category: Mapped[ServiceCategory | None] = relationship()


class ScheduledNotification(Base):
    __tablename__ = "scheduled_notification"
    __table_args__ = (Index("ix_scheduled_status_due", "status", "due_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id", ondelete="CASCADE"))
    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("reminder_rule.id", ondelete="SET NULL"), default=None
    )
    channel: Mapped[str] = mapped_column(String(10))
    body: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    #: "PENDING" | "SENDING" | "SENT" | "CANCELLED" | "FAILED"
    #: SENDING: bir bakim calistirmasi kaydi sahiplendi, gonderim suruyor.
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    #: Basarisiz gonderim denemesi sayisi; sinira ulasinca FAILED.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Son hatanin kisa aciklamasi (panelde gosterilir).
    last_error: Mapped[str | None] = mapped_column(String(300), default=None)
    #: PENDING iken: bir sonraki yeniden deneme zamani (geri cekilme).
    #: SENDING iken: sahiplenmenin gecerlilik suresi; dolarsa (surec coktu)
    #: kayit tekrar sahiplenilebilir.
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    #: Ayni kural + randevu icin tekrar uretimi engeller
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    customer: Mapped[Customer] = relationship()


# ---------------------------------------------------------------------
# 11. PORTFOLYO & ENGAGEMENT
# ---------------------------------------------------------------------


class PortfolioItem(Base):
    __tablename__ = "portfolio_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("service_category.id", ondelete="SET NULL"), default=None
    )
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), default=None
    )
    title: Mapped[str] = mapped_column(String(160))
    image_url: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    category: Mapped[ServiceCategory | None] = relationship()
    staff: Mapped[Staff | None] = relationship()


class SlotViewEvent(Base):
    """"Bugun 3 kisi bu saate bakti" gostergesinin GERCEK veri kaynagi.

    Uydurma sayi uretilmez; slot goruntuleme olaylari burada sayilir.
    """

    __tablename__ = "slot_view_event"
    __table_args__ = (Index("ix_slot_view_branch_date_start", "branch_id", "date", "start_min"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer)
    staff_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String(10))
    start_min: Mapped[int] = mapped_column(Integer)
    #: Tekil ziyaretci ayrimi icin anonim oturum anahtari
    viewer_key: Mapped[str] = mapped_column(String(64))
    viewed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class OccupancyStat(Base):
    """Firsat saati skorlarinin onbellegi (gecmis dolulugundan hesaplanir)."""

    __tablename__ = "occupancy_stat"
    __table_args__ = (UniqueConstraint("branch_id", "weekday", "slot_min"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer)
    weekday: Mapped[int] = mapped_column(Integer)
    #: Gun ici saat dilimi baslangici (dk)
    slot_min: Mapped[int] = mapped_column(Integer)
    #: 0..1 arasi tarihsel doluluk orani
    occupancy: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ---------------------------------------------------------------------
# 12. MUSTERI YORUMLARI (vitrin)
# ---------------------------------------------------------------------


class Review(Base):
    """Vitrindeki sosyal kanitin GERCEK kaynagi.

    Yorum uydurulmaz: ``appointment_id`` dolu olan bir yorum, o randevunun
    TAMAMLANMIS oldugu dogrulanarak yazilir ve ``is_verified`` isaretlenir.
    Her randevuya en fazla bir yorum yazilabilir (``appointment_id`` tekil).
    """

    __tablename__ = "review"
    __table_args__ = (
        Index("ix_review_branch_published", "branch_id", "is_published"),
        Index("ix_review_staff", "staff_id"),
        Index("ix_review_customer", "customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id", ondelete="CASCADE"))
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer.id", ondelete="SET NULL"), default=None
    )
    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), default=None
    )
    #: Yorumun dayandigi randevu - dogrulanmis yorumlarda zorunlu
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointment.id", ondelete="SET NULL"), unique=True, default=None
    )

    #: Vitrinde gorunen ad: "Ayşe K." - soyadi kisaltilir (gizlilik)
    author_name: Mapped[str] = mapped_column(String(80))
    #: 1..5
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text)
    #: Randevudaki hizmet adlari, virgulle
    service_names: Mapped[str | None] = mapped_column(String(300), default=None)

    #: Tamamlanmis bir randevuya bagli mi?
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Vitrinde yayinlansin mi? (moderasyon)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    #: One cikan yorum
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)

    #: Salonun yoruma verdigi cevap
    reply: Mapped[str | None] = mapped_column(Text, default=None)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    staff: Mapped[Staff | None] = relationship()


class RateLimitHit(Base):
    """DENEME SINIRI KAYDI - kayan pencereli hiz sinirlama.

    Her sayilan olay (hatali personel girisi, OTP istegi...) bir satirdir;
    ``key`` olayin turunu ve kaynagini tasir (``staff-login:ip:1.2.3.4``).
    Sayac veritabaninda tutuldugu icin birden fazla worker/sunucu ayni
    sinirlari paylasir. Eski satirlar ``/api/cron/sweep`` ile silinir.
    """

    __tablename__ = "rate_limit_hit"
    __table_args__ = (Index("ix_rate_limit_key_created", "key", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WhatsappContact(Base):
    """WHATSAPP KISI DEFTERI - "ilk mesaj" tespiti.

    Salon numarasiyla yazismis her kisi burada bir satirdir. Bir kisi
    buraya hic girmeden mesaj atarsa "ilk mesaj" sayilir ve karsilama
    gonderilir. Sistem veya personel o kisiye yazdiysa (OTP, hatirlatma,
    telefondan elle mesaj) ya da numara baglanirken sohbet gecmisi varsa
    kisi zaten "tanidik"tir - karsilama gitmez.

    ``contact_key`` ulke kodlu numaradir (``905321234567``). WhatsApp
    numarayi gizlediginde (``@lid`` kimligi) ve gercek numara bilinmiyorsa
    lid kimligi kullanilir. Unique kisit, ayni webhook'un tekrar gelmesi
    veya es zamanli iki mesajda karsilamanin iki kez gitmesini engeller.
    """

    __tablename__ = "whatsapp_contact"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_key: Mapped[str] = mapped_column(String(64), unique=True)
    #: "INBOUND" (ilk mesaji kendisi atti) | "OUTBOUND" (biz yazdik) | "HISTORY"
    source: Mapped[str] = mapped_column(String(10))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    #: Karsilama mesaji gonderildiyse zamani.
    welcomed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
