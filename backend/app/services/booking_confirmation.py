"""
====================================================================
RANDEVU ONAYI - randevuyu alana "randevunuz olusturuldu" mesaji
====================================================================

Onay mesaji dogrudan gonderilmez; bildirim kuyruguna ``due_at = simdi``
olarak yazilir ve arka plan isci (``notification_worker``) hemen
uyandirilir. Boylece:

  * mesaj randevuyla ayni veritabanina yazilir - sunucu yeniden baslasa
    da kaybolmaz,
  * WhatsApp baglantisi o an kopuksa mesaj kuyrukta bekler, baglanti
    gelince gider (geri cekilmeli yeniden deneme kuyrugun kendisinde),
  * randevu istegi WhatsApp yanitini beklemez.

Grup randevusunda alana TEK bir ozet mesaj gider; baskasi adina alinan
randevularda alicinin bilgilendirmesi ``booking_for_other`` modulundedir.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import config
from ..models import ScheduledNotification
from ..time_utils import format_date_tr, minutes_to_label, now_local

#: ``dedupe_key`` onekleri; iptalde bekleyen onay da geri cekilir.
CONFIRM_PREFIX = "confirm:"
CONFIRM_GROUP_PREFIX = "confirm-group:"


@dataclass(frozen=True)
class ConfirmationLine:
    """Onay mesajindaki bir randevu."""

    date: str
    start_min: int
    service_names: list[str]
    staff_name: str
    #: Baskasi icin alinan randevuda alicinin (alanin yazdigi) adi; kendisi icin None.
    for_name: str | None = None


def _line_text(line: ConfirmationLine) -> str:
    who = f"{line.for_name} için " if line.for_name else ""
    staff = f" · {line.staff_name}" if line.staff_name else ""
    return (
        f"{who}{format_date_tr(line.date)} saat {minutes_to_label(line.start_min)}"
        f" - {', '.join(line.service_names)}{staff}"
    )


def build_confirmation_message(booker_name: str, lines: list[ConfirmationLine]) -> str:
    """Randevuyu alana giden onay metni (islemsel, ticari icerik yok)."""
    if len(lines) == 1:
        head = f"Merhaba {booker_name}, randevunuz oluşturuldu ✅"
        body = _line_text(lines[0])
    else:
        head = f"Merhaba {booker_name}, {len(lines)} kişilik grup randevunuz oluşturuldu ✅"
        body = "\n".join(f"• {_line_text(line)}" for line in lines)
    return (
        f"{head}\n\n{body}\n\n"
        f"Randevunuzu görmek veya iptal etmek için: {config.public_site_url}/randevularim"
    )


def queue_confirmation(
    db: Session, customer_id: int, dedupe_key: str, text: str
) -> None:
    """Onay mesajini kuyruga yazar (vadesi simdi). Commit cagiranindir."""
    if db.scalar(
        select(ScheduledNotification.id).where(ScheduledNotification.dedupe_key == dedupe_key)
    ):
        return
    db.add(
        ScheduledNotification(
            customer_id=customer_id,
            channel="WHATSAPP",
            body=text,
            due_at=now_local(),
            dedupe_key=dedupe_key,
        )
    )
