"""
====================================================================
PORTFOLYO YONETIMI - okuma katmani
====================================================================

Panel galerisi: isler + yukleme formu icin kategori ve usta secenekleri.
Gorseller ``uploads/portfolyo/<yyyy-mm>/`` altina yazilir; uzak depolama
yoktur.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import PortfolioItem, ServiceCategory, Staff


def list_admin_portfolio(db: Session, branch_id: int) -> dict:
    items = db.scalars(
        select(PortfolioItem)
        .options(selectinload(PortfolioItem.category), selectinload(PortfolioItem.staff))
        .where(PortfolioItem.branch_id == branch_id)
        .order_by(PortfolioItem.sort_order, PortfolioItem.id.desc())
    ).all()

    categories = db.scalars(
        select(ServiceCategory)
        .where(ServiceCategory.branch_id == branch_id)
        .order_by(ServiceCategory.sort_order, ServiceCategory.id)
    ).all()

    staff = db.scalars(
        select(Staff)
        .where(Staff.branch_id == branch_id, Staff.is_active.is_(True))
        .order_by(Staff.display_order, Staff.id)
    ).all()

    return {
        "items": [
            {
                "id": i.id,
                "title": i.title,
                "imageUrl": i.image_url,
                "description": i.description,
                "isPublished": i.is_published,
                "categoryName": i.category.name if i.category else None,
                "staffName": i.staff.name if i.staff else None,
            }
            for i in items
        ],
        "categories": [{"id": c.id, "name": c.name} for c in categories],
        "staff": [{"id": s.id, "name": s.name} for s in staff],
    }
