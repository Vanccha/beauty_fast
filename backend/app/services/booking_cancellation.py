"""
====================================================================
RANDEVU IPTALI - "randevunuz iptal edildi" mesaji
====================================================================

``booking_confirmation`` ile ayni desen: mesaj dogrudan gonderilmez,
iptalle AYNI transaction'da bildirim kuyruguna (``due_at = simdi``)
yazilir; arka plan isci iptalden sonra (commit SONRASI) uyandirilir.

Kurallar:
  * mesaj randevunun SAHIBINE gider; baskasi adina alinmissa randevuyu
    alana da (ayri mesaj) gider. Ayni kisiyse tek mesaj.
  * grup iptalinde alana TEK ozet mesaj, her alici icin ayri mesaj.
  * anonimlestirilmis musteriye ve telefonsuz kayda mesaj gitmez.
  * NO_SHOW icin mesaj YOKTUR (cagiran yalnizca CANCELLED'da cagirir).
  * ``dedupe_key`` benzersiz oldugu icin iki kez iptal tek mesaj uretir.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import config
from ..models import Appointment, Customer
from ..time_utils import format_date_tr, minutes_to_label
from .booking_confirmation import queue_confirmation
from .deposit import REFUND_LINE, unpaid_cancel_message

#: ``dedupe_key`` onekleri.
CANCEL_PREFIX = "cancel:"
CANCEL_GROUP_PREFIX = "cancel-group:"


def _reachable(customer: Customer | None) -> bool:
    return bool(customer and customer.anonymized_at is None and customer.phone)


def _services(appointment: Appointment) -> str:
    names = [i.service.name for i in appointment.items if i.service is not None]
    return ", ".join(names)


def _line(appointment: Appointment, for_name: str | None = None) -> str:
    who = f"{for_name} için " if for_name else ""
    return (
        f"{who}{format_date_tr(appointment.date)} saat {minutes_to_label(appointment.start_min)}"
        f" - {_services(appointment)}"
    )


def _rebook_hint() -> str:
    return f"Yeni randevu almak için: {config.public_site_url}/randevu"


def build_cancellation_message(
    name: str, appointment: Appointment, for_name: str | None = None, refund_note: bool = False
) -> str:
    text = f"Merhaba {name}, {_line(appointment, for_name)} randevunuz iptal edildi. {_rebook_hint()}"
    # Kapora iadesi: odeme yapan kisiye gider.
    return f"{text}\n{REFUND_LINE}" if refund_note else text


def build_group_cancellation_message(
    name: str,
    appointments: list[Appointment],
    labels: dict[int, str | None],
    refund_note: bool = False,
) -> str:
    body = "\n".join(f"• {_line(a, labels.get(a.id))}" for a in appointments)
    text = (
        f"Merhaba {name}, {len(appointments)} kişilik grup randevunuz iptal edildi.\n\n"
        f"{body}\n\n{_rebook_hint()}"
    )
    return f"{text}\n{REFUND_LINE}" if refund_note else text


def _booker_of(db: Session, appointment: Appointment) -> Customer | None:
    """Randevuyu alan, sahibinden FARKLIYSA o; degilse None."""
    bid = appointment.booked_by_customer_id
    if bid is None or bid == appointment.customer_id:
        return None
    return db.get(Customer, bid)


def queue_cancellation_notices(
    db: Session, appointment: Appointment, deposit_mode: str | None = None
) -> None:
    """Tek randevu iptali: sahibe + (baskasi adinaysa) alana. Commit cagiranindir.

    ``deposit_mode`` (kapora): "UNPAID" -> kapora yatirilmadigi icin iptal;
    odeme yapana (alan, yoksa sahibi) ozel metin, genel iptal mesajinin
    YERINE gider. "REFUND" -> odeme yapana iade satiri eklenir."""
    owner = appointment.customer or db.get(Customer, appointment.customer_id)
    booker = _booker_of(db, appointment)
    # Kaporayi yatiran: alan kisi (baskasi adinaysa), degilse sahibi.
    payer_is_booker = booker is not None

    if _reachable(owner):
        pays = not payer_is_booker
        if pays and deposit_mode == "UNPAID":
            text = unpaid_cancel_message(owner.first_name, appointment)
        else:
            text = build_cancellation_message(
                owner.first_name, appointment, refund_note=pays and deposit_mode == "REFUND"
            )
        queue_confirmation(db, owner.id, f"{CANCEL_PREFIX}{appointment.id}:{owner.id}", text)
    if _reachable(booker):
        label = appointment.beneficiary_label or (owner.first_name if owner else None)
        if deposit_mode == "UNPAID":
            text = unpaid_cancel_message(booker.first_name, appointment)
        else:
            text = build_cancellation_message(
                booker.first_name, appointment, label, refund_note=deposit_mode == "REFUND"
            )
        queue_confirmation(db, booker.id, f"{CANCEL_PREFIX}{appointment.id}:{booker.id}", text)


def queue_group_cancellation_notices(
    db: Session,
    booker: Customer,
    group_id: str,
    appointments: list[Appointment],
    refund_note: bool = False,
) -> None:
    """Grup iptali: alana TEK ozet + baskasi icin olan her randevunun sahibine ayri
    mesaj. Alanin kendi randevulari yalniz ozette yer alir. Commit cagiranindir."""
    if not appointments:
        return
    labels: dict[int, str | None] = {}
    for a in appointments:
        if a.customer_id != booker.id:
            owner = a.customer or db.get(Customer, a.customer_id)
            labels[a.id] = a.beneficiary_label or (owner.first_name if owner else None)
        else:
            labels[a.id] = None

    if _reachable(booker):
        queue_confirmation(
            db,
            booker.id,
            f"{CANCEL_GROUP_PREFIX}{group_id}",
            build_group_cancellation_message(booker.first_name, appointments, labels, refund_note),
        )
    for a in appointments:
        if a.customer_id == booker.id:
            continue
        owner = a.customer or db.get(Customer, a.customer_id)
        if _reachable(owner):
            queue_confirmation(
                db,
                owner.id,
                f"{CANCEL_PREFIX}{a.id}:{owner.id}",
                build_cancellation_message(owner.first_name, a),
            )
