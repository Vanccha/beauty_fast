"""
====================================================================
YORUM OKUMA KATMANI
====================================================================

TEMEL KURAL: buradaki hicbir sayi uydurulmaz. Ortalama puan, yorum adedi
ve yildiz dagilimi ``review`` tablosundan toplanir; tek bir yorum bile
yoksa bolum gosterilmez (sahte sosyal kanit uretmeyiz).

(``src/lib/server/reviews.ts`` karsiligi.)
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Appointment, Review, Staff

EMPTY_DISTRIBUTION = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}


def get_review_summary(db: Session, branch_id: int) -> dict:
    """Yayinlanmis yorumlarin ozeti: adet, ortalama ve yildiz dagilimi."""
    rows = db.execute(
        select(Review.rating, func.count())
        .where(Review.branch_id == branch_id, Review.is_published.is_(True))
        .group_by(Review.rating)
    ).all()

    distribution = dict(EMPTY_DISTRIBUTION)
    count = 0
    positive = 0
    weighted = 0

    for rating, n in rows:
        if 1 <= rating <= 5:
            distribution[rating] = n
        count += n
        weighted += rating * n
        if rating >= 4:
            positive += n

    return {
        "count": count,
        "average": round(weighted / count, 2) if count else None,
        "distribution": distribution,
        "positiveRate": (positive / count) if count else 0,
    }


def _shape(review: Review, staff_name: str | None) -> dict:
    return {
        "id": review.id,
        "authorName": review.author_name,
        "rating": review.rating,
        "comment": review.comment,
        "serviceNames": review.service_names,
        "staffName": staff_name,
        "isVerified": review.is_verified,
        "createdAt": review.created_at.isoformat(),
        "reply": review.reply,
    }


def get_showcase_reviews(db: Session, branch_id: int, take: int = 6) -> list[dict]:
    """Vitrin yorumlari.

    Siralama kasitli: once salonun one cikardiklari, sonra yuksek
    puanlilar, sonra en yeniler. Yorumlarin kendisi gercek kalir.
    """
    rows = db.execute(
        select(Review, Staff.name)
        .outerjoin(Staff, Staff.id == Review.staff_id)
        .where(Review.branch_id == branch_id, Review.is_published.is_(True))
        .order_by(Review.is_featured.desc(), Review.rating.desc(), Review.created_at.desc())
        .limit(take)
    ).all()
    return [_shape(r, name) for r, name in rows]


def list_reviews(
    db: Session,
    branch_id: int,
    min_rating: int | None = None,
    staff_id: int | None = None,
    take: int = 60,
) -> list[dict]:
    """Tum yorumlar sayfasi icin listeleme (tarih sirasiyla)."""
    query = (
        select(Review, Staff.name)
        .outerjoin(Staff, Staff.id == Review.staff_id)
        .where(Review.branch_id == branch_id, Review.is_published.is_(True))
    )
    if min_rating:
        query = query.where(Review.rating >= min_rating)
    if staff_id:
        query = query.where(Review.staff_id == staff_id)

    rows = db.execute(query.order_by(Review.created_at.desc()).limit(take)).all()
    return [_shape(r, name) for r, name in rows]


def get_staff_ratings(db: Session, branch_id: int) -> dict[int, dict]:
    """Personel bazli puan ortalamasi.

    Yalnizca en az 3 yorumu olan ustalar icin puan doner: iki yorumla
    "5.0 puan" yazmak yaniltcidir.
    """
    rows = db.execute(
        select(Review.staff_id, func.avg(Review.rating), func.count())
        .where(
            Review.branch_id == branch_id,
            Review.is_published.is_(True),
            Review.staff_id.is_not(None),
        )
        .group_by(Review.staff_id)
    ).all()

    return {
        staff_id: {"average": round(float(avg), 1), "count": count}
        for staff_id, avg, count in rows
        if count >= 3
    }


# ---------------------------------------------------------------------
# Moderasyon (yalnizca personel)
# ---------------------------------------------------------------------


def list_admin_reviews(db: Session, branch_id: int, take: int = 100) -> list[dict]:
    """Moderasyon listesi: EN YENIDEN eskiye, yayindan kaldirilanlar DAHIL.

    Moderasyon karari geri alinabilir olmali; bu yuzden yayinda olmayan
    yorumlar da doner (panel onlari soluk gosterir).
    """
    rows = db.execute(
        select(Review, Staff.name, Appointment.date)
        .outerjoin(Staff, Staff.id == Review.staff_id)
        .outerjoin(Appointment, Appointment.id == Review.appointment_id)
        .where(Review.branch_id == branch_id)
        .order_by(Review.created_at.desc())
        .limit(take)
    ).all()

    return [
        {
            "id": r.id,
            "authorName": r.author_name,
            "rating": r.rating,
            "comment": r.comment,
            "serviceNames": r.service_names,
            "staffId": r.staff_id,
            "staffName": staff_name,
            "appointmentDate": appointment_date,
            "isVerified": r.is_verified,
            "isPublished": r.is_published,
            "isFeatured": r.is_featured,
            "reply": r.reply,
            "createdAt": r.created_at.isoformat(),
        }
        for r, staff_name, appointment_date in rows
    ]


def count_unanswered_low_ratings(db: Session, branch_id: int) -> int:
    """Yayindaki, yanitlanmamis dusuk puanli (<= 3) yorum sayisi."""
    return (
        db.scalar(
            select(func.count())
            .select_from(Review)
            .where(
                Review.branch_id == branch_id,
                Review.rating <= 3,
                Review.reply.is_(None),
                Review.is_published.is_(True),
            )
        )
        or 0
    )
