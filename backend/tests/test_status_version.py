"""Durum degisikliginde donen ``version`` alani regresyonu.

``change_appointment_status`` yeni surumu HESAPLAMAZ, veritabanindan okur.
Hesaplama (``appointment.version + 1``) yanlis sonuc veriyordu: SQLAlchemy'nin
``update()`` cagrisi oturumdaki nesnenin alanlarini da tazeliyor
(``synchronize_session``), dolayisiyla elde tutulan deger zaten artmis
oluyor ve bir daha +1 eklenince istemciye BIR FAZLA surum donuyordu.

Sonuc: istemci bir sonraki istegi o surumle gonderdiginde haksiz yere
``VERSION_MISMATCH`` aliyordu - randevuyu tamamlayan personel, ardindan
kartta hicbir islem yapamiyordu.
"""

from __future__ import annotations


import pytest
from sqlalchemy import select

from app.core.package_layout import layout_package
from app.errors import AppError
from app.models import Appointment
from app.services.appointment import confirm_appointment_from_lock
from app.services.appointment_status import change_appointment_status
from app.services.soft_lock import acquire_slot_lock
from app.time_utils import add_days_to_key, now_local, to_date_key

from .conftest import spec_of

TOMORROW = add_days_to_key(to_date_key(now_local()), 1)


def _create(db, salon, start_min: int = 600) -> Appointment:
    layout = layout_package([spec_of(salon["manikur"])])
    lock = acquire_slot_lock(
        db, branch_id=salon["branch"].id, staff_id=salon["staff_a"].id,
        session_id="s", date=TOMORROW, start_min=start_min, layout=layout,
        customer_id=salon["customer"].id,
    )
    return confirm_appointment_from_lock(
        db, lock_id=lock.lock_id, session_id="s", customer_id=salon["customer"].id,
        branch_id=salon["branch"].id, staff_id=salon["staff_a"].id, date=TOMORROW,
        start_min=start_min, layout=layout,
    )


def test_returned_version_matches_database(salon, db):
    appointment = _create(db, salon, 600)
    assert appointment.version == 0

    result = change_appointment_status(
        db, appointment_id=appointment.id, status="COMPLETED", expected_version=0
    )

    stored = db.scalar(select(Appointment.version).where(Appointment.id == appointment.id))
    assert result["version"] == stored == 1


def test_second_call_with_returned_version_reports_terminal_state(salon, db):
    """Istemci, donen surumle tekrar denerse "zaten tamamlanmis" demeli -
    yanlis bir VERSION_MISMATCH degil."""
    appointment = _create(db, salon, 660)
    result = change_appointment_status(
        db, appointment_id=appointment.id, status="COMPLETED", expected_version=0
    )

    with pytest.raises(AppError) as excinfo:
        change_appointment_status(
            db,
            appointment_id=appointment.id,
            status="CANCELLED",
            expected_version=result["version"],
        )
    assert excinfo.value.code == "VALIDATION"
    assert "COMPLETED" in excinfo.value.message


def test_cancel_then_version_is_usable(salon, db):
    appointment = _create(db, salon, 720)
    result = change_appointment_status(
        db, appointment_id=appointment.id, status="CANCELLED", expected_version=0
    )
    stored = db.scalar(select(Appointment.version).where(Appointment.id == appointment.id))
    assert result["version"] == stored == 1
    assert result["freedSlot"] is True
