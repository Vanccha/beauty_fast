"""
====================================================================
KATALOG OKUMA
====================================================================

Veritabani satirlarini, zamanlama motorunun bekledigi saf ``ServiceSpec``
yapisina cevirir. Motor ORM'i bilmez; bu dosya iki dunya arasindaki TEK
koprudur.

--------------------------------------------------------------------
HATA DUZELTMESI 2 - "ayni hizmeti iki kez secmek"
--------------------------------------------------------------------
Next.js surumunde personel yetkinligi su sekilde dogrulaniyordu:

    staff.services.length === serviceIds.length        (catalog.ts:118)
    links.length !== body.serviceIds.length            (slots/lock, appointments)

Bu sayim karsilastirmasi, ``serviceIds`` icinde ayni hizmet iki kez
gecerse (orn. iki kisi icin kas alma, ya da paketin ikinci bir seans
icermesi) DAIMA basarisiz olur: 2 istenen kaleme karsilik 1 yetkinlik
satiri bulunur ve istek "Secilen personel bu hizmetlerin tamamini
yapmiyor" hatasiyla reddedilir - musaitlik ucunda ise hic personel
bulunamaz. Oysa ayni sistemin stok katmani tekrari acikca destekliyor
(``stock.ts``: "Bir hizmet randevuda birden fazla kez geciyorsa o kadar
kez sayilir").

Burada karsilastirma **kume kapsamasina** cevrildi: personelin yetkinlik
kumesi, istenen benzersiz hizmet kumesini kapsiyorsa yeterlidir. Tekrar
eden kalemler paket yerlesiminde ayri ayri yer alir.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.opportunity import FixedWindowSettings, fixed_window_settings_from_salon
from ..core.types import ResourceNeed, ServiceSpec
from ..errors import AppError
from ..models import Branch, Resource, Salon, Service, Staff, StaffService

#: Bir pakette kabul edilen azami hizmet kalemi (tekrarlar dahil).
MAX_PACKAGE_ITEMS = 10


def get_default_branch(db: Session) -> Branch:
    """Bu proje tek salon / tek sube icin calisir.

    Cok subeye gecildiginde yalnizca bu fonksiyon (ve cagiranlarin
    ``branch_id`` parametresi) degisir; alt katmanlar zaten ``branch_id``
    aliyor.
    """
    branch = db.scalar(select(Branch).order_by(Branch.id).limit(1))
    if branch is None:
        raise AppError(
            "NOT_FOUND", "Şube bulunamadı. Önce `python -m app.seed` çalıştırın.", 404
        )
    return branch


def get_discount_settings(db: Session) -> FixedWindowSettings:
    """Firsat saati indirim ayarlari (tek salon). Fiyat icin TEK kaynak."""
    salon = db.scalar(select(Salon).order_by(Salon.id).limit(1))
    return fixed_window_settings_from_salon(salon)


def get_exclusive_resource_ids(db: Session, branch_id: int) -> list[int]:
    """Kapasitesi 1 olan (dolayisiyla hucre yazan) kaynaklarin id kumesi."""
    return list(
        db.scalars(
            select(Resource.id).where(
                Resource.branch_id == branch_id,
                Resource.capacity == 1,
                Resource.is_active.is_(True),
            )
        )
    )


def to_spec(row: Service) -> ServiceSpec:
    return ServiceSpec(
        id=row.id,
        name=row.name,
        active_before_min=row.active_before_min,
        passive_min=row.passive_min,
        active_after_min=row.active_after_min,
        buffer_min=row.buffer_min,
        shadow_host_allowed=row.shadow_host_allowed,
        shadow_guest_allowed=row.shadow_guest_allowed,
        price=row.price,
        resources=tuple(
            ResourceNeed(r.resource_id, r.quantity, r.only_during_active)
            for r in row.requirements
        ),
    )


def validate_service_ids(service_ids: Sequence[int]) -> list[int]:
    """Istemciden gelen hizmet listesini dogrular.

    Tekrarlara IZIN VERILIR (bkz. modul basligi); yalnizca sayi ve deger
    sinirlari uygulanir.
    """
    if not service_ids:
        raise AppError("VALIDATION", "En az bir hizmet seçmelisiniz.", 400)
    if len(service_ids) > MAX_PACKAGE_ITEMS:
        raise AppError(
            "VALIDATION",
            f"Bir randevuda en fazla {MAX_PACKAGE_ITEMS} hizmet seçebilirsiniz.",
            400,
        )
    if any(not isinstance(i, int) or i <= 0 for i in service_ids):
        raise AppError("VALIDATION", "Geçersiz hizmet kimliği.", 400)
    return list(service_ids)


def load_service_specs(db: Session, service_ids: Sequence[int]) -> list[ServiceSpec]:
    """Secilen hizmetleri MUSTERININ SECTIGI SIRAYLA doner.

    Sira onemlidir: paket yerlesimi (ve sikistirma) bu sirayi korur.
    Ayni id birden fazla kez gecebilir - her gecis ayri bir kalemdir.
    """
    ids = validate_service_ids(service_ids)
    unique_ids = list(dict.fromkeys(ids))

    rows = db.scalars(
        select(Service)
        .options(selectinload(Service.requirements))
        .where(Service.id.in_(unique_ids), Service.is_active.is_(True))
    ).all()
    by_id = {r.id: r for r in rows}

    missing = [i for i in unique_ids if i not in by_id]
    if missing:
        raise AppError(
            "NOT_FOUND", "Seçilen hizmetlerden bazıları bulunamadı.", 404, {"missing": missing}
        )

    return [to_spec(by_id[i]) for i in ids]


def find_capable_staff(db: Session, branch_id: int, service_ids: Sequence[int]) -> list[Staff]:
    """Paketin TUM hizmetlerini yapabilen aktif personel.

    Kume kapsamasi kullanilir; ``service_ids`` icindeki tekrarlar sonucu
    etkilemez (bkz. modul basligi, "Hata duzeltmesi 2").
    """
    needed = set(service_ids)
    if not needed:
        return []

    staff_rows = db.scalars(
        select(Staff)
        .options(selectinload(Staff.services), selectinload(Staff.working_hours))
        .where(Staff.branch_id == branch_id, Staff.is_active.is_(True))
        .order_by(Staff.display_order, Staff.id)
    ).all()

    return [s for s in staff_rows if needed.issubset({link.service_id for link in s.services})]


def speed_factor_for(links: Iterable[StaffService] | Iterable[float]) -> float:
    """Personelin bu paket icin gecerli hiz carpani.

    Paketteki hizmetler farkli carpanlara sahipse EN YAVASI (en buyuk)
    alinir - sureyi oldugundan kisa gostermek, takvimi bozmaktan kotudur.
    """
    values = [
        (link if isinstance(link, (int, float)) else link.speed_factor) for link in links
    ]
    return max(values) if values else 1.0


def assert_staff_can_do(db: Session, staff_id: int, service_ids: Sequence[int]) -> float:
    """Personel bu hizmetlerin tamamini yapabiliyor mu? Hiz carpanini doner.

    Kume kapsamasi (tekrarlara toleransli) - bkz. modul basligi.
    """
    needed = set(service_ids)
    links = db.scalars(
        select(StaffService).where(
            StaffService.staff_id == staff_id, StaffService.service_id.in_(needed)
        )
    ).all()

    if needed - {link.service_id for link in links}:
        raise AppError("VALIDATION", "Seçilen personel bu hizmetlerin tamamını yapmıyor.", 400)

    return speed_factor_for(links)


def staff_speed_factor_for(staff: Staff, service_ids: Sequence[int]) -> float:
    """Yuklenmis bir ``Staff`` nesnesi icin hiz carpani (ek sorgu yapmaz)."""
    needed = set(service_ids)
    return speed_factor_for(
        [link.speed_factor for link in staff.services if link.service_id in needed]
    )
