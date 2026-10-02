"""Herkese acik uclar (oturum gerektirmez) + oturum bilgisi.

  GET  /api/me         - oturum sahibi + kisisellestirilmis karsilama
  GET  /api/showcase   - acilis sayfasinin tum verisi (vitrin)
  GET  /api/portfolio  - galeri
  GET  /api/reviews    - yayinlanmis yorumlar
  POST /api/reviews    - tamamlanmis randevuya yorum yaz
  POST /api/cron/sweep - bakim isi (kilit/oturum temizligi + bildirim kuyrugu);
                         ``X-Cron-Secret`` basligi veya MANAGER oturumu ister
"""

from __future__ import annotations


from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..auth.rate_limit import sweep_rate_limits
from ..auth.sessions import get_customer_principal, get_staff_principal, sweep_expired_sessions
from ..deps import CustomerDep, DbSession, require_cron_or_manager
from ..errors import AppError
from ..http import EnvelopeRoute
from ..models import (
    Appointment,
    AppointmentItem,
    Customer,
    CustomerPhoto,
    PortfolioItem,
    Review,
    Salon,
    Service,
    ServiceCategory,
    Staff,
    StaffService,
)
from ..services.booking_for_other import clean_person_name
from ..services.catalog import get_default_branch
from ..services.reviews import (
    get_review_summary,
    get_showcase_reviews,
    get_staff_ratings,
    list_reviews,
)
from ..services.notifications import deliver_due_notifications
from ..services.privacy import sweep_retention
from ..services.soft_lock import sweep_expired_locks
from ..services.welcome import build_welcome, get_opening_hours, get_salon_stats
from ..time_utils import now_local

router = APIRouter(tags=["public"], route_class=EnvelopeRoute)


@router.get("/api/me")
def me(request: Request, db: DbSession) -> dict:
    """Oturum yoksa 200 + ``null`` doner - misafir gezinme desteklendigi
    icin bu bir hata degildir."""
    staff = get_staff_principal(db, request)
    customer = get_customer_principal(db, request)
    welcome = build_welcome(db, customer.id) if customer else None

    return {
        "staff": staff.to_dict() if staff else None,
        "customer": customer.to_dict() if customer else None,
        "welcome": welcome,
    }


class UpdateMeBody(BaseModel):
    firstName: str = Field(min_length=1, max_length=60)
    lastName: str | None = Field(default=None, max_length=60)

    @field_validator("firstName")
    @classmethod
    def _first(cls, v: str) -> str:
        return clean_person_name(v, required=True)  # type: ignore[return-value]

    @field_validator("lastName")
    @classmethod
    def _last(cls, v: str | None) -> str | None:
        return clean_person_name(v, required=False)


@router.patch("/api/me")
def update_me(body: UpdateMeBody, customer: CustomerDep, db: DbSession) -> dict:
    """Musteri adini gunceller ("Ismimi degistir"). Telefon degismez
    (kimlik telefondur). ``lastName`` bos birakilirsa soyad temizlenir."""
    row = db.get(Customer, customer.id)
    row.first_name = body.firstName
    row.last_name = body.lastName
    db.commit()
    db.refresh(row)
    return {
        "customer": {
            "id": row.id,
            "firstName": row.first_name,
            "lastName": row.last_name,
            "phone": row.phone,
            "tier": row.tier,
            "loyaltyPoints": row.loyalty_points,
            "engagementOptIn": row.engagement_opt_in,
        }
    }


@router.get("/api/me/album")
def my_album(customer: CustomerDep, db: DbSession, take: int = Query(default=12, ge=1, le=60)):
    """Musterinin kendi islem gecmisi albumu.

    Gizlilik: yalnizca oturum sahibinin fotograflari doner. Gizli usta
    notlari (``customer_note``) bu ucta HIC sorgulanmaz.
    """
    photos = db.scalars(
        select(CustomerPhoto)
        .where(CustomerPhoto.customer_id == customer.id)
        .order_by(CustomerPhoto.created_at.desc())
        .limit(take)
    ).all()

    return {
        "photos": [
            {
                "id": p.id,
                "imageUrl": p.image_url,
                "note": p.note,
                "colorTag": p.color_tag,
                "createdAt": p.created_at.isoformat(),
            }
            for p in photos
        ]
    }


@router.get("/api/showcase")
def showcase(db: DbSession) -> dict:
    """Acilis sayfasinin (vitrin) tum verisi tek istekte.

    DURUSTLUK KURALI: her rakam veritabanindan sayilir. Yorum yoksa
    ``reviews`` bos doner ve arayuz o bolumu hic gostermemelidir - bos
    vitrin, sahte vitrinden iyidir.
    """
    branch = get_default_branch(db)

    categories = db.scalars(
        select(ServiceCategory)
        .where(ServiceCategory.branch_id == branch.id)
        .order_by(ServiceCategory.sort_order, ServiceCategory.id)
    ).all()

    services = db.scalars(
        select(Service)
        .where(Service.branch_id == branch.id, Service.is_active.is_(True))
        .order_by(Service.price.desc())
    ).all()

    staff = db.scalars(
        select(Staff)
        .options(selectinload(Staff.services).selectinload(StaffService.service))
        .where(Staff.branch_id == branch.id, Staff.is_active.is_(True))
        .order_by(Staff.display_order, Staff.id)
    ).all()
    ratings = get_staff_ratings(db, branch.id)

    portfolio = db.scalars(
        select(PortfolioItem)
        .options(selectinload(PortfolioItem.category))
        .where(PortfolioItem.branch_id == branch.id, PortfolioItem.is_published.is_(True))
        .order_by(PortfolioItem.sort_order, PortfolioItem.id.desc())
    ).all()

    # "...'den" fiyati ve kategori basina hizmet sayisi
    from_price: dict[int, float] = {}
    service_count: dict[int, int] = {}
    for s in services:
        if s.category_id is None:
            continue
        service_count[s.category_id] = service_count.get(s.category_id, 0) + 1
        current = from_price.get(s.category_id)
        if current is None or s.price < current:
            from_price[s.category_id] = s.price

    # Kategori kapagi: o kategorinin ilk isi, yoksa galerinin ilki.
    cover: dict[int, str] = {}
    for item in portfolio:
        if item.category_id is not None and item.category_id not in cover:
            cover[item.category_id] = item.image_url
    first_image = portfolio[0].image_url if portfolio else None

    category_name = {c.id: c.name for c in categories}
    salon = db.get(Salon, branch.salon_id)

    return {
        "salon": {
            "branchId": branch.id,
            "salonName": salon.name if salon else branch.name,
            "branchName": branch.name,
            "phone": salon.phone if salon else None,
            # Geriye donuk uyum: eski istemciler "name" bekliyordu.
            "name": branch.name,
            "address": branch.address,
            "openMinute": branch.open_minute,
            "closeMinute": branch.close_minute,
        },
        "stats": get_salon_stats(db, branch.id),
        "openingHours": get_opening_hours(db, branch.id),
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "icon": c.icon,
                "fromPrice": from_price.get(c.id),
                "serviceCount": service_count.get(c.id, 0),
                "cover": cover.get(c.id) or first_image,
            }
            for c in categories
        ],
        #: Tum hizmetler, pahalidan ucuza (vitrin "imza hizmetler" ilk 6'sini alir)
        "services": [
            {
                "id": s.id,
                "categoryId": s.category_id,
                "categoryName": category_name.get(s.category_id or -1, ""),
                "name": s.name,
                "description": s.description,
                "price": s.price,
                "activeBeforeMin": s.active_before_min,
                "passiveMin": s.passive_min,
                "activeAfterMin": s.active_after_min,
                "totalMin": s.active_before_min + s.passive_min + s.active_after_min,
            }
            for s in services
        ],
        "reviews": {
            "summary": get_review_summary(db, branch.id),
            "items": get_showcase_reviews(db, branch.id, 6),
        },
        "team": [
            {
                "id": s.id,
                "name": s.name,
                "photoUrl": s.photo_url,
                "role": s.role,
                "rating": ratings.get(s.id),
                #: Uzmanlik: verdigi hizmetlerden ilk ucu
                "specialties": list(
                    dict.fromkeys(link.service.name for link in s.services)
                )[:3],
            }
            for s in staff
        ],
        "portfolio": [
            {
                "id": p.id,
                "title": p.title,
                "imageUrl": p.image_url,
                "description": p.description,
                "categoryId": p.category_id,
                "category": (
                    {"id": p.category.id, "name": p.category.name, "slug": p.category.slug}
                    if p.category
                    else None
                ),
            }
            for p in portfolio
        ],
    }


@router.get("/api/portfolio")
def portfolio(db: DbSession, category: str | None = None) -> dict:
    """Herkese acik galeri. Oturum GEREKTIRMEZ."""
    branch = get_default_branch(db)

    category_row = (
        db.scalar(
            select(ServiceCategory).where(
                ServiceCategory.branch_id == branch.id, ServiceCategory.slug == category
            )
        )
        if category and category != "hepsi"
        else None
    )

    query = (
        select(PortfolioItem)
        .options(selectinload(PortfolioItem.category), selectinload(PortfolioItem.staff))
        .where(PortfolioItem.branch_id == branch.id, PortfolioItem.is_published.is_(True))
    )
    if category_row:
        query = query.where(PortfolioItem.category_id == category_row.id)

    items = db.scalars(query.order_by(PortfolioItem.sort_order, PortfolioItem.id.desc())).all()

    categories = db.scalars(
        select(ServiceCategory)
        .where(ServiceCategory.branch_id == branch.id)
        .order_by(ServiceCategory.sort_order, ServiceCategory.id)
    ).all()

    return {
        "categories": [
            {"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon} for c in categories
        ],
        "items": [
            {
                "id": i.id,
                "title": i.title,
                "imageUrl": i.image_url,
                "description": i.description,
                "category": (
                    {"id": i.category.id, "name": i.category.name, "slug": i.category.slug}
                    if i.category
                    else None
                ),
                "staffName": i.staff.name if i.staff else None,
            }
            for i in items
        ],
    }


@router.get("/api/reviews")
def get_reviews(
    db: DbSession,
    minRating: int | None = Query(default=None, ge=1, le=5),
    staffId: int | None = None,
    take: int = Query(default=60, ge=1, le=200),
) -> dict:
    """Tum yorumlar - tarih sirasiyla.

    Vitrin en iyisini gosterir (``/api/showcase``), bu uc olani gosterir.
    """
    branch = get_default_branch(db)
    return {
        "summary": get_review_summary(db, branch.id),
        "items": list_reviews(db, branch.id, min_rating=minRating, staff_id=staffId, take=take),
    }


class CreateReviewBody(BaseModel):
    appointmentId: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=10, max_length=1000)


@router.post("/api/reviews")
def create_review(body: CreateReviewBody, customer: CustomerDep, db: DbSession) -> dict:
    """Musteri, TAMAMLANMIS kendi randevusuna yorum yazar.

    Vitrindeki sosyal kanitin degeri arkasindaki dogrulamadan gelir; dort
    kapi vardir:
      1. Uyelik         - anonim yorum kabul edilmez
      2. Sahiplik       - randevu yorumu yazanin olmali
      3. Tamamlanmislik - hizmet gercekten alinmis olmali
      4. Tekillik       - randevu basina tek yorum (appointment_id unique)

    Yazar adi istemciden ALINMAZ; musteri kaydindan "Ayşe K." biciminde
    uretilir.
    """
    branch = get_default_branch(db)

    appointment = db.scalar(
        select(Appointment)
        .options(selectinload(Appointment.items).selectinload(AppointmentItem.service))
        .where(Appointment.id == body.appointmentId)
    )
    if appointment is None:
        raise AppError("NOT_FOUND", "Randevu bulunamadı.", 404)
    if appointment.customer_id != customer.id:
        raise AppError("FORBIDDEN", "Bu randevuya erişiminiz yok.", 403)
    if appointment.status != "COMPLETED":
        raise AppError(
            "NOT_COMPLETED", "Yalnızca tamamlanmış randevular değerlendirilebilir.", 409
        )

    existing = db.scalar(select(Review.id).where(Review.appointment_id == appointment.id))
    if existing:
        raise AppError("ALREADY_REVIEWED", "Bu randevu için zaten yorum yazdınız.", 409)

    profile = db.get(Customer, customer.id)
    author_name = (
        f"{profile.first_name} {profile.last_name[0].upper()}."
        if profile and profile.last_name
        else (profile.first_name if profile else "Müşteri")
    )

    review = Review(
        branch_id=branch.id,
        customer_id=customer.id,
        staff_id=appointment.staff_id,
        appointment_id=appointment.id,
        author_name=author_name,
        rating=body.rating,
        comment=body.comment,
        service_names=", ".join(i.service.name for i in appointment.items),
        # Tamamlanmis randevuya baglandigi icin dogrulanmistir.
        is_verified=True,
        # Moderasyon kapisi yok: yorum dogrulanmis bir randevudan geliyor.
        is_published=True,
    )
    db.add(review)
    db.commit()

    return {"id": review.id, "rating": review.rating, "createdAt": review.created_at.isoformat()}


@router.post("/api/cron/sweep", dependencies=[Depends(require_cron_or_manager)])
def cron_sweep(db: DbSession) -> dict:
    """Bakim isi.

      1) Suresi dolmus soft-lock'lari ve hucrelerini siler
      2) Suresi dolmus oturum/OTP/deneme siniri kayitlarini siler
      3) KVKK saklama suresi dolan kayitlari siler (``services/privacy.py``)
      4) Zamani gelmis bildirimleri gonderir (``NOTIFICATION_DRIVER``:
         console -> log, evolution -> WhatsApp). Ayrinti:
         ``services/notifications.py::deliver_due_notifications``.

    NOT: ``acquire_slot_lock`` zaten her kilit aliminda suresi gecmisleri
    transaction icinde temizler. Bu uc yalnizca hic trafik olmayan
    donemlerde tablolarin sismesini engeller - dogruluk buna bagli DEGILDIR.
    """
    now = now_local()

    locks = sweep_expired_locks(db, now)
    db.commit()
    sessions = sweep_expired_sessions(db, now)
    rate_limits = sweep_rate_limits(db, now)
    db.commit()
    retention = sweep_retention(db, now)

    delivery = deliver_due_notifications(db, now)

    return {
        "sweptAt": now.isoformat(),
        **locks,
        **sessions,
        "removedRateLimitHits": rate_limits,
        **retention,
        "notificationsSent": delivery["sent"],
        "notificationsFailed": delivery["failed"],
        #: True ise gonderim yapilmadi (orn. WhatsApp baglantisi kopuk).
        "notificationsSkipped": delivery["skipped"],
        "driverState": delivery["driverState"],
    }
