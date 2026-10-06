"""Personel yonetimi (admin paneli): liste, ekleme, duzenleme, silme, kazanc.

Kurallar:
  * Yonetici yalnizca ``STAFF`` rolundeki personeli yonetir; ``OWNER`` /
    ``MANAGER`` satirlarini ve rol degisikligini yalnizca salon sahibi yapar.
  * Salon sahibi silinemez / pasife alinamaz.
  * Randevu gecmisi olan personel SILINMEZ (randevular ``CASCADE`` ile gider);
    bunun yerine pasife alinir. Pasif personel girisi ve rezervasyonu kapanir.
  * Telefon, sifre, rol ya da pasife alma degistiginde acik oturumlari kapanir.
  * Kazanc = TAMAMLANAN randevularin ``total_price`` toplami x kazanc yuzdesi.
    Yuzde anlik degeri kullanilir (gecmis yuzde kaydi tutulmaz).
"""

from __future__ import annotations

import re

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..auth.password import hash_password
from ..core.risk_score import is_valid_mobile, normalize_phone
from ..errors import AppError
from ..models import (
    Appointment,
    AppointmentItem,
    Service,
    Staff,
    StaffService,
    StaffSession,
    WorkingHour,
)

MIN_PASSWORD_LENGTH = 8
ROLES = ("STAFF", "MANAGER")
_INSTAGRAM = re.compile(r"[A-Za-z0-9._]{1,30}")


def normalize_instagram(raw: str | None) -> str | None:
    """"@ad", profil bagi ya da duz kullanici adi -> "ad" (bos ise None)."""
    value = (raw or "").strip()
    if not value:
        return None
    value = re.sub(r"^https?://(www\.)?instagram\.com/", "", value, flags=re.I)
    value = value.split("?")[0].strip("/").lstrip("@")
    if not _INSTAGRAM.fullmatch(value):
        raise AppError("VALIDATION", "Instagram kullanıcı adı geçersiz.", 400, {"field": "instagram"})
    return value


def validate_phone(db: Session, raw: str, *, exclude_id: int | None = None) -> str:
    phone = normalize_phone(raw)
    if not is_valid_mobile(phone):
        raise AppError("VALIDATION", "Geçerli bir cep telefonu girin.", 400, {"field": "phone"})
    query = select(Staff.id).where(Staff.phone == phone)
    if exclude_id is not None:
        query = query.where(Staff.id != exclude_id)
    if db.scalar(query) is not None:
        raise AppError("VALIDATION", "Bu telefon numarası başka bir personelde kayıtlı.", 409, {"field": "phone"})
    return phone


def validate_password(raw: str) -> str:
    if len(raw) < MIN_PASSWORD_LENGTH:
        raise AppError(
            "VALIDATION", f"Şifre en az {MIN_PASSWORD_LENGTH} karakter olmalı.", 400, {"field": "password"}
        )
    return raw


def validate_name(raw: str) -> str:
    name = " ".join((raw or "").split())
    if len(name) < 2:
        raise AppError("VALIDATION", "Ad soyad girin.", 400, {"field": "name"})
    return name


def get_staff_or_404(db: Session, branch_id: int, staff_id: int) -> Staff:
    row = db.scalar(select(Staff).where(Staff.id == staff_id, Staff.branch_id == branch_id))
    if row is None:
        raise AppError("NOT_FOUND", "Personel bulunamadı.", 404)
    return row


def ensure_can_manage(actor_id: int, actor_role: str, target: Staff) -> None:
    """Yonetici yalnizca STAFF rolunu yonetir (kendisi dahil degil)."""
    if actor_role == "OWNER":
        return
    if target.role != "STAFF":
        raise AppError("FORBIDDEN", "Bu kullanıcıyı yalnızca salon sahibi düzenleyebilir.", 403)


def revoke_sessions(db: Session, staff_id: int) -> None:
    db.execute(delete(StaffSession).where(StaffSession.staff_id == staff_id))


def set_services(db: Session, staff_id: int, service_ids: list[int], branch_id: int) -> None:
    valid = set(
        db.scalars(
            select(Service.id).where(Service.id.in_(set(service_ids)), Service.branch_id == branch_id)
        )
    )
    if len(valid) != len(set(service_ids)):
        raise AppError("VALIDATION", "Geçersiz hizmet seçildi.", 400, {"field": "serviceIds"})
    existing = {
        link.service_id: link
        for link in db.scalars(select(StaffService).where(StaffService.staff_id == staff_id))
    }
    for sid, link in existing.items():
        if sid not in valid:
            db.delete(link)
    for sid in valid - set(existing):
        db.add(StaffService(staff_id=staff_id, service_id=sid))


def create_default_hours(db: Session, staff_id: int, open_min: int, close_min: int) -> None:
    """Pazar kapali, diger gunler sube saatlerinde (sonradan duzenlenebilir)."""
    for weekday in range(7):
        db.add(
            WorkingHour(
                staff_id=staff_id,
                weekday=weekday,
                start_min=open_min,
                end_min=close_min,
                is_working=weekday != 0,
            )
        )


def hash_new_password(raw: str) -> str:
    return hash_password(validate_password(raw))


def serialize(row: Staff, service_ids: list[int]) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "phone": row.phone,
        "role": row.role,
        "photoUrl": row.photo_url,
        "instagram": row.instagram,
        "commissionPercent": row.commission_percent,
        "isActive": row.is_active,
        "serviceIds": service_ids,
    }


def service_ids_by_staff(db: Session, staff_ids: list[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {i: [] for i in staff_ids}
    for sid, svc in db.execute(
        select(StaffService.staff_id, StaffService.service_id).where(StaffService.staff_id.in_(staff_ids))
    ):
        out[sid].append(svc)
    return out


def earnings_summary(db: Session, staff_ids: list[int], date_from: str, date_to: str) -> dict[int, dict]:
    """Aralikta TAMAMLANAN randevulardan personel basina adet + ciro."""
    rows = db.execute(
        select(
            Appointment.staff_id,
            func.count(Appointment.id),
            func.coalesce(func.sum(Appointment.total_price), 0),
        )
        .where(
            Appointment.staff_id.in_(staff_ids),
            Appointment.status == "COMPLETED",
            Appointment.date >= date_from,
            Appointment.date <= date_to,
        )
        .group_by(Appointment.staff_id)
    ).all()
    return {sid: {"count": int(n), "revenue": float(total)} for sid, n, total in rows}


def earnings_detail(db: Session, staff: Staff, date_from: str, date_to: str) -> dict:
    appointments = db.scalars(
        select(Appointment)
        .where(
            Appointment.staff_id == staff.id,
            Appointment.status == "COMPLETED",
            Appointment.date >= date_from,
            Appointment.date <= date_to,
        )
        .order_by(Appointment.date.desc(), Appointment.start_min.desc())
    ).all()
    names: dict[int, list[str]] = {}
    if appointments:
        for appt_id, name in db.execute(
            select(AppointmentItem.appointment_id, Service.name)
            .join(Service, Service.id == AppointmentItem.service_id)
            .where(AppointmentItem.appointment_id.in_([a.id for a in appointments]))
        ):
            names.setdefault(appt_id, []).append(name)
    pct = staff.commission_percent or 0
    rows = [
        {
            "id": a.id,
            "date": a.date,
            "startMin": a.start_min,
            "services": names.get(a.id, []),
            "price": float(a.total_price),
            "commission": round(float(a.total_price) * pct / 100, 2),
        }
        for a in appointments
    ]
    revenue = sum(r["price"] for r in rows)
    return {
        "from": date_from,
        "to": date_to,
        "commissionPercent": pct,
        "count": len(rows),
        "revenue": revenue,
        "commission": round(revenue * pct / 100, 2),
        "appointments": rows,
    }
