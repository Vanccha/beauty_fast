"""
====================================================================
STOK TAKIBI
====================================================================

Her hizmetin bir sarf malzemesi recetesi vardir (``service_consumable``).
Randevu "COMPLETED" olarak isaretlendiginde recetedeki miktarlar stoktan
otomatik dusulur.

--------------------------------------------------------------------
Idempotency
--------------------------------------------------------------------
``stock_movement`` uzerindeki ``UNIQUE(appointment_id, item_id)`` kisiti
sayesinde ayni randevu iki kez tamamlanirsa (cift tiklama, yeniden
deneme, iki sekme) stok IKI KEZ DUSMEZ: ikinci yazma unique ihlaliyle
reddedilir ve sessizce atlanir. Bu, uygulama katmanindaki "zaten dusulmus
mu" kontrolune guvenmekten daha saglamdir.

Not: ``appointment_id`` NULL olan manuel hareketler bu kisittan
etkilenmez (PostgreSQL'de NULL degerler unique indekste birbirinden
farkli sayilir).

Ayni hizmet bir randevuda birden fazla kez geciyorsa (bkz. "Hata 2":
ayni hizmeti iki kez secme) malzeme O KADAR KEZ dusulur.

(``services/inventory/stock.ts`` karsiligi.)
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..errors import is_unique_violation
from ..models import AppointmentItem, InventoryItem, ServiceConsumable, StockMovement
from . import push


def consume_for_appointment(db: Session, appointment_id: int) -> dict:
    """Randevunun hizmetlerine bagli sarf malzemelerini stoktan duser.

    Cagiran transaction icinde calistirmalidir (commit etmez).
    """
    service_ids = list(
        db.scalars(
            select(AppointmentItem.service_id).where(
                AppointmentItem.appointment_id == appointment_id
            )
        )
    )

    if not service_ids:
        return {"applied": False, "lines": [], "warnings": []}

    recipes = db.scalars(
        select(ServiceConsumable)
        .options(selectinload(ServiceConsumable.item))
        .where(ServiceConsumable.service_id.in_(set(service_ids)))
    ).all()

    if not recipes:
        return {"applied": False, "lines": [], "warnings": []}

    # Ayni malzeme birden cok hizmette geciyorsa miktarlar toplanir.
    totals: dict[int, dict] = {}
    for recipe in recipes:
        # Bir hizmet randevuda birden fazla kez geciyorsa o kadar kez sayilir.
        occurrences = sum(1 for sid in service_ids if sid == recipe.service_id)
        cur = totals.setdefault(recipe.item_id, {"qty": 0.0, "item": recipe.item})
        cur["qty"] += recipe.qty_per_use * occurrences

    lines: list[dict] = []
    warnings: list[str] = []
    applied = False

    # Satir kilitleri hep ayni sirayla (item_id) alinir; iki randevu ayni
    # malzemeleri farkli sirayla kilitleyip kilitlenme (deadlock) uretmez.
    for item_id, entry in sorted(totals.items()):
        qty = entry["qty"]
        try:
            with db.begin_nested():
                # Idempotency anahtari: (appointment_id, item_id)
                db.add(
                    StockMovement(
                        item_id=item_id,
                        delta=-qty,
                        reason="APPOINTMENT_COMPLETED",
                        appointment_id=appointment_id,
                    )
                )
        except IntegrityError as error:
            if is_unique_violation(error):
                # Bu randevu icin bu malzeme zaten dusulmus - atla.
                continue
            raise

        # Oku-degistir-yaz: eszamanli iki dusum birbirini ezmesin diye satir
        # kilitlenir (SELECT ... FOR UPDATE).
        item: InventoryItem = db.get(
            InventoryItem, item_id, with_for_update=True, populate_existing=True
        )
        item.quantity = round(item.quantity - qty, 4)
        db.flush()

        applied = True
        below_critical = item.quantity <= item.critical_level

        lines.append(
            {
                "itemId": item_id,
                "itemName": item.name,
                "quantity": qty,
                "unit": item.unit,
                "remaining": item.quantity,
                "belowCritical": below_critical,
                #: Bu dusumla kritik seviyenin ALTINA yeni inildi (push icin)
                "crossedCritical": below_critical
                and (item.quantity + qty) > item.critical_level,
            }
        )

        if item.quantity < 0:
            warnings.append(
                f"{item.name} stoğu eksiye düştü ({item.quantity} {item.unit})."
            )
        elif below_critical:
            warnings.append(
                f"{item.name} kritik seviyenin altında: {item.quantity} {item.unit} kaldı."
            )

    return {"applied": applied, "lines": lines, "warnings": warnings}


def critical_items(db: Session, branch_id: int) -> list[dict]:
    """Kritik seviyenin altindaki malzemeler - admin panel uyari listesi."""
    items = db.scalars(
        select(InventoryItem)
        .where(InventoryItem.branch_id == branch_id)
        .order_by(InventoryItem.name)
    ).all()
    return [
        {
            "id": i.id,
            "name": i.name,
            "quantity": i.quantity,
            "unit": i.unit,
            "criticalLevel": i.critical_level,
            "severity": "OUT" if i.quantity <= 0 else "LOW",
        }
        for i in items
        if i.quantity <= i.critical_level
    ]


def adjust_stock(
    db: Session,
    item_id: int,
    delta: float,
    reason: str | None = None,
    note: str | None = None,
) -> InventoryItem:
    """Manuel stok girisi/duzeltmesi.

    Miktar ve hareket kaydi AYNI transaction'da degisir; "stok dustu ama
    kaydi yok" durumu olusmaz.
    """
    db.add(
        StockMovement(
            item_id=item_id,
            delta=delta,
            reason=reason or ("PURCHASE" if delta >= 0 else "MANUAL_ADJUST"),
            note=note,
        )
    )
    item = db.get(InventoryItem, item_id, with_for_update=True, populate_existing=True)
    before = item.quantity
    item.quantity = round(item.quantity + delta, 4)
    db.commit()
    if before > item.critical_level >= item.quantity:
        push.notify_low_stock([(item.name, item.quantity, item.unit)])
    return item


def preview_consumption(db: Session, service_ids: Sequence[int]) -> list[dict]:
    """Bir paketin tuketecegi malzemeleri onceden hesaplar (stok yeterli mi?)."""
    if not service_ids:
        return []

    recipes = db.scalars(
        select(ServiceConsumable)
        .options(selectinload(ServiceConsumable.item))
        .where(ServiceConsumable.service_id.in_(set(service_ids)))
    ).all()

    totals: dict[int, dict] = {}
    for r in recipes:
        occurrences = sum(1 for sid in service_ids if sid == r.service_id)
        cur = totals.setdefault(
            r.item_id, {"needed": 0.0, "name": r.item.name, "available": r.item.quantity}
        )
        cur["needed"] += r.qty_per_use * occurrences

    return [
        {
            "itemId": item_id,
            "name": v["name"],
            "needed": v["needed"],
            "available": v["available"],
            "sufficient": v["available"] >= v["needed"],
        }
        for item_id, v in totals.items()
    ]
