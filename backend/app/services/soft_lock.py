"""
====================================================================
SOFT-LOCK (Gecici Slot Rezervasyonu)
====================================================================

Kullanici bir saat secip "Bu saati tut" dediginde slot 5 dakikaligina
kilitlenir. Bu surede baska kullanicilar o slotu goremez/alamaz; sure
dolarsa veya kullanici vazgecerse slot otomatik serbest kalir.

--------------------------------------------------------------------
Yaris kosulu garantisi
--------------------------------------------------------------------
Kilit, ``occupancy_cell`` tablosuna hucre satirlari yazarak alinir. Bu
tablodaki ``UNIQUE(owner_type, owner_id, date, cell_index)`` kisiti
nedeniyle, ayni slota eszamanli ilerleyen ikinci istek **veritabani
seviyesinde** reddedilir. Kontrol uygulama katmaninda degil, motorda
yapilir - "once kontrol et, sonra yaz" (TOCTOU) acigi yoktur.

Transaction icinde once suresi gecmis LOCK hucreleri silinir; boylece
TTL'i dolmus kilitler yeni istegi yanlislikla engellemez. Silme ve yazma
ayni transaction'da oldugu icin araya baska bir yazici giremez.

(``services/booking/soft-lock.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import config
from ..core.occupancy import CellSpec, build_occupancy_cells
from ..core.types import PackageLayout
from ..errors import AppError, SlotConflictError, is_unique_violation
from ..models import OccupancyCell, SlotLock
from ..time_utils import now_local


@dataclass(frozen=True)
class AcquiredLock:
    lock_id: int
    staff_id: int
    date: str
    start_min: int
    end_min: int
    expires_at: datetime
    #: Geri sayim icin kalan saniye
    ttl_seconds: int


def sweep_expired_locks(db: Session, now: datetime | None = None) -> dict:
    """Suresi gecmis kilitleri ve hucrelerini siler.

    Hem transaction icinden hem de zamanlanmis temizlikten cagrilabilir.
    """
    now = now or now_local()
    cells = db.execute(
        delete(OccupancyCell).where(
            OccupancyCell.kind == "LOCK", OccupancyCell.expires_at < now
        )
    ).rowcount
    locks = db.execute(
        delete(SlotLock).where(SlotLock.expires_at < now, SlotLock.consumed_at.is_(None))
    ).rowcount
    return {"removedCells": cells or 0, "removedLocks": locks or 0}


def _conflicting_cells(
    db: Session,
    cells: Sequence[CellSpec],
    date: str,
    exclude_lock_ids: Sequence[int] = (),
    now: datetime | None = None,
) -> list[OccupancyCell]:
    """Yazilmak istenen hucrelerle cakisan mevcut hucreler.

    ``exclude_lock_ids``: ayni oturumun kendi kilit hucreleri (randevuya
    donusturulen kilit ya da yenisiyle degistirilen eski kilit) cakisma
    sayilmaz - transaction'da silinmislerdi, rollback sonrasi yeniden
    gorunur olurlar. Ayni nedenle suresi dolmus LOCK hucreleri de sayilmaz.
    """
    now = now or now_local()
    if not cells:
        return []
    query = select(OccupancyCell).where(
        OccupancyCell.date == date,
        or_(
            *[
                and_(
                    OccupancyCell.owner_type == c.owner_type,
                    OccupancyCell.owner_id == c.owner_id,
                    OccupancyCell.cell_index == c.cell_index,
                )
                for c in cells
            ]
        ),
    )
    query = query.where(or_(OccupancyCell.kind != "LOCK", OccupancyCell.expires_at > now))
    if exclude_lock_ids:
        query = query.where(
            or_(
                OccupancyCell.lock_id.is_(None),
                OccupancyCell.lock_id.notin_(list(exclude_lock_ids)),
            )
        )
    return list(db.scalars(query.limit(50)))


def conflict_error(
    db: Session,
    cells: Sequence[CellSpec],
    date: str,
    exclude_lock_ids: Sequence[int] = (),
    now: datetime | None = None,
    for_other: bool = False,
) -> AppError:
    """Unique ihlalini kullaniciya dogru anlatan hatayi uretir.

    Hata duzeltmesi: cakisma YALNIZCA musterinin kendi takvimindeyse
    (ayni saatte baska bir randevusu var) "baska bir musteri aldi" demek
    yanlistir - kullanici saat ayni kalsa da tekrar tekrar ayni hatayi
    alir. Bu durum ``CUSTOMER_OVERLAP`` ile ayrica bildirilir.
    """
    conflicts = _conflicting_cells(db, cells, date, exclude_lock_ids, now)
    if conflicts and all(c.owner_type == "CUSTOMER" for c in conflicts):
        if for_other:
            return AppError(
                "CUSTOMER_OVERLAP",
                "Bu kişinin bu saatte zaten başka bir randevusu var. Lütfen farklı bir saat seç.",
                409,
            )
        return AppError(
            "CUSTOMER_OVERLAP",
            "Bu saatte zaten başka bir randevun var. Lütfen farklı bir saat seç.",
            409,
        )
    lock_cell = next((c for c in conflicts if c.kind == "LOCK"), None)
    return SlotConflictError(lock_cell.expires_at if lock_cell else None)


def acquire_slot_lock(
    db: Session,
    branch_id: int,
    staff_id: int,
    session_id: str,
    date: str,
    start_min: int,
    layout: PackageLayout,
    customer_id: int | None = None,
    exclusive_resource_ids: Sequence[int] = (),
    ttl_seconds: int | None = None,
    now: datetime | None = None,
    for_other: bool = False,
    beneficiary_customer_id: int | None = None,
    group_id: str | None = None,
    service_ids: Sequence[int] | None = None,
    commit: bool = True,
) -> AcquiredLock:
    """Slot kilidi alir. Basarisizlikta ``SlotConflictError`` firlatir.

    ``for_other``: baskasi adina kilit. ``customer_id`` kilidi tutan (alan)
    musteridir; musteri doluluk hucresi ALICI icin yazilir
    (``beneficiary_customer_id``; alici henuz kayitli degilse hucre
    yazilmaz, cakisma onayda yakalanir). ``group_id`` verilirse ayni
    gruba ait kilitler birbirini silmez. ``commit=False``: cagiran
    transaction'i kendisi bitirir (grup kilidi: hepsi ya da hicbiri);
    hata durumunda yine de TUM transaction geri alinir.
    """
    now = now or now_local()
    ttl_seconds = ttl_seconds or config.slot_lock_ttl_seconds
    expires_at = now + timedelta(seconds=ttl_seconds)

    end_min = start_min + layout.total_min

    cells = build_occupancy_cells(
        layout=layout,
        date=date,
        start_min=start_min,
        staff_id=staff_id,
        customer_id=beneficiary_customer_id if for_other else customer_id,
        exclusive_resource_ids=exclusive_resource_ids,
    )

    if not cells:
        raise AppError("VALIDATION", "Kilitlenecek zaman dilimi hesaplanamadı.", 400)

    stale_ids: list[int] = []
    try:
        # 1) Suresi dolmus kilitleri ayni transaction icinde temizle.
        sweep_expired_locks(db, now)

        # 2) Ayni oturumun daha once tuttugu, henuz randevuya donusmemis
        #    kilitleri birak (kullanici geri gidip baska saat secmis olabilir).
        stale_ids = list(
            db.scalars(
                select(SlotLock.id).where(
                    SlotLock.session_id == session_id,
                    SlotLock.consumed_at.is_(None),
                    *([or_(SlotLock.group_id.is_(None), SlotLock.group_id != group_id)]
                      if group_id else []),
                )
            )
        )
        if stale_ids:
            db.execute(delete(OccupancyCell).where(OccupancyCell.lock_id.in_(stale_ids)))
            db.execute(delete(SlotLock).where(SlotLock.id.in_(stale_ids)))

        # 3) Kilit kaydi
        lock = SlotLock(
            branch_id=branch_id,
            staff_id=staff_id,
            customer_id=customer_id,
            beneficiary_customer_id=beneficiary_customer_id if for_other else None,
            group_id=group_id,
            service_ids=",".join(str(i) for i in service_ids) if service_ids else None,
            session_id=session_id,
            date=date,
            start_min=start_min,
            end_min=end_min,
            expires_at=expires_at,
            created_at=now,
        )
        db.add(lock)
        db.flush()

        # 4) Hucreleri yaz - CAKISMA BURADA, VERITABANI TARAFINDAN yakalanir.
        db.add_all(
            [
                OccupancyCell(
                    owner_type=c.owner_type,
                    owner_id=c.owner_id,
                    date=c.date,
                    cell_index=c.cell_index,
                    kind="LOCK",
                    lock_id=lock.id,
                    expires_at=expires_at,
                )
                for c in cells
            ]
        )
        if commit:
            db.commit()
        else:
            db.flush()

    except IntegrityError as error:
        db.rollback()
        if is_unique_violation(error):
            raise conflict_error(db, cells, date, stale_ids, now, for_other) from error
        raise
    except Exception:
        db.rollback()
        raise

    return AcquiredLock(
        lock_id=lock.id,
        staff_id=staff_id,
        date=date,
        start_min=start_min,
        end_min=end_min,
        expires_at=expires_at,
        ttl_seconds=ttl_seconds,
    )


def release_slot_lock(db: Session, lock_id: int, session_id: str) -> bool:
    """Kilidi serbest birakir. Sahibi olmayan oturum birakamaz."""
    # Hucreler ON DELETE CASCADE ile birlikte silinir (yabanci anahtar kurali).
    count = db.execute(
        delete(SlotLock).where(
            SlotLock.id == lock_id,
            SlotLock.session_id == session_id,
            SlotLock.consumed_at.is_(None),
        )
    ).rowcount
    db.commit()
    return bool(count)


def find_active_lock(db: Session, session_id: str, now: datetime | None = None) -> SlotLock | None:
    """Bu oturumun halen gecerli kilidi (arayuz geri dondugunde gosterilir)."""
    now = now or now_local()
    return db.scalar(
        select(SlotLock)
        .where(
            SlotLock.session_id == session_id,
            SlotLock.consumed_at.is_(None),
            SlotLock.expires_at > now,
        )
        .order_by(SlotLock.id.desc())
        .limit(1)
    )


def assert_lock_valid(
    db: Session,
    lock_id: int,
    session_id: str,
    now: datetime | None = None,
    customer_id: int | None = None,
) -> SlotLock:
    """Kilidin hala gecerli olup olmadigini kontrol eder.

    Sahiplik iki katmanlidir: kilit bu tarayicinin (``visitor_key``)
    olmali; kilit alinirken bir musteri oturumu varsa ONAYLAYAN da ayni
    musteri olmalidir. Misafirken alinan kilit (``customer_id`` bos),
    giris yaptiktan sonra ayni tarayicidan onaylanabilir - "giris yap,
    sonra onayla" akisi bunu gerektirir.
    """
    now = now or now_local()
    lock = db.get(SlotLock, lock_id)
    if lock is None:
        raise AppError("LOCK_NOT_FOUND", "Rezervasyon bulunamadı.", 404)
    if lock.session_id != session_id:
        raise AppError("FORBIDDEN", "Bu rezervasyon bu oturuma ait değil.", 403)
    if customer_id is not None and lock.customer_id is not None and lock.customer_id != customer_id:
        raise AppError("FORBIDDEN", "Bu rezervasyon başka bir üyeye ait.", 403)
    if lock.consumed_at is not None:
        raise AppError("LOCK_EXPIRED", "Bu rezervasyon zaten kullanılmış.", 409)
    if lock.expires_at <= now:
        raise AppError(
            "LOCK_EXPIRED", "Rezervasyon süreniz doldu. Lütfen saati yeniden seçin.", 409
        )
    return lock
