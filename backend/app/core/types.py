"""Zamanlama motorunun giris tipleri.

ORM modellerinden bagimsizdir - motor saf veriyle calisir, boylece
testlerde veritabani gerekmez. (``scheduling/types.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..intervals import Interval


@dataclass(frozen=True)
class ResourceNeed:
    resource_id: int
    quantity: int = 1
    #: True  -> kaynak yalnizca ustanin aktif calistigi dilimlerde tutulur
    #: False -> pasif (bekleme) suresi dahil tum hizmet boyunca tutulur
    #:          (orn. boya beklerken musteri koltukta oturur)
    only_during_active: bool = False


@dataclass(frozen=True)
class ServiceSpec:
    id: int
    name: str
    #: Ustanin mudahale ettigi ilk blok
    active_before_min: int
    #: Ustanin SERBEST oldugu bekleme penceresi
    passive_min: int
    #: Bekleme sonrasi aktif blok
    active_after_min: int
    #: Temizlik/hazirlik tamponu (ucretlendirilmez, usta mesgul sayilir)
    buffer_min: int
    #: Pasif penceresi baska musterinin hizmetine acilabilir mi?
    shadow_host_allowed: bool
    #: Baska bir randevunun pasif penceresine yerlestirilebilir mi?
    shadow_guest_allowed: bool
    price: float
    resources: tuple[ResourceNeed, ...] = ()


@dataclass
class PlacedItem:
    service: ServiceSpec
    sort_order: int
    #: Paket baslangicina gore ofset (dk)
    offset_min: int
    active_before_min: int
    passive_min: int
    active_after_min: int
    buffer_min: int
    price: float
    #: Bu hizmet, ayni paketteki baska bir hizmetin pasif penceresine mi yerlesti?
    placed_in_shadow: bool


@dataclass
class ResourceUsage:
    resource_id: int
    quantity: int
    interval: Interval


@dataclass
class PackageLayout:
    #: Paketin takvimde kapladigi KESINTISIZ blok uzunlugu (dk)
    total_min: int
    #: Ustanin fiilen mesgul oldugu ofset araliklari
    staff_busy: list[Interval]
    #: Paket icinde ustanin serbest kaldigi ve DIS bir misafir hizmete
    #: acilabilecek pencereler (golgeli paralel blok)
    shadow_windows: list[Interval]
    #: Musteri tum blok boyunca salondadir
    customer_busy: list[Interval]
    resource_usage: list[ResourceUsage]
    items: list[PlacedItem]
    total_price: float
    #: Sikistirma (compaction) sayesinde kazanilan dakika
    saved_min: int


@dataclass(frozen=True)
class ExternalShadowWindow:
    """Mevcut bir randevunun, baska musteriye acilabilen pasif penceresi."""

    appointment_id: int
    staff_id: int
    interval: Interval


@dataclass(frozen=True)
class ResourceCalendar:
    resource_id: int
    capacity: int
    #: O gun icin mevcut kullanimlar
    usages: tuple[tuple[Interval, int], ...] = field(default=())


@dataclass(frozen=True)
class SlotCandidate:
    start_min: int
    end_min: int
    #: Bu slot, mevcut bir randevunun pasif penceresine mi yerlesiyor?
    is_shadow_fill: bool = False
    shadow_parent_appointment_id: int | None = None
