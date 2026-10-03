"""
====================================================================
ZIYARET SONRASI MESAJ - tesekkur + puanlama + Google/Instagram baglantilari
====================================================================

Randevu COMPLETED olunca, musteriye ``post_visit_delay_hours`` saat sonra
(varsayilan 2) WhatsApp'tan tesekkur / geri bildirim mesaji gider.
``booking_cancellation`` ile ayni kuyruk deseni: mesaj ``ScheduledNotification``
olarak yazilir, ``dedupe_key`` randevu basina tekildir.

Kurallar:
  * ISLEMSEL / geri bildirim mesajidir: indirim, kampanya, hizmet tanitimi
    YOKTUR. Bu yuzden pazarlama onayina (``repeat:`` oneki) tabi degildir.
  * anonimlestirilmis musteriye ve telefonsuz kayda gitmez.
  * ``dedupe_key = postvisit:<randevu_id>`` -> iki kez tamamlama tek mesaj.
  * Randevu COMPLETED'dan baska bir duruma alinirsa bekleyen mesaj iptal edilir.
  * Bos baglanti -> o baglantinin gectigi SATIR mesajdan cikarilir.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import config
from ..models import Appointment, Customer, Salon, ScheduledNotification

POST_VISIT_PREFIX = "postvisit:"

DEFAULT_POST_VISIT = (
    "Merhaba {ad}, bugün bizi tercih ettiğiniz için teşekkürler! "
    "Deneyiminizi 1 dakikada puanlayabilirsiniz: {yorum_linki}\n"
    "Google'da yorum bırakmak isterseniz: {google_linki}\n"
    "Instagram'da bizi takip edin: {instagram_linki}"
)
PLACEHOLDERS = {
    "{ad}": "Müşterinin adı",
    "{hizmetler}": "Yapılan hizmetler",
    "{yorum_linki}": "Randevularım sayfası (puanlama)",
    "{google_linki}": "Google yorum bağlantısı",
    "{instagram_linki}": "Instagram bağlantısı",
}
MAX_MESSAGE_LENGTH = 1000
MAX_DELAY_HOURS = 168


def _link_values(salon: Salon) -> dict[str, str]:
    return {
        "{yorum_linki}": f"{config.public_site_url}/randevularim",
        "{google_linki}": (salon.google_review_url or "").strip(),
        "{instagram_linki}": (salon.instagram_url or "").strip(),
    }


def render_post_visit(
    salon: Salon, first_name: str = "Ayşe", services: str = "Manikür"
) -> str:
    """Yer tutucular doldurulur; bos baglanti iceren satirlar atilir."""
    template = (salon.post_visit_message or "").strip() or DEFAULT_POST_VISIT
    links = _link_values(salon)
    lines: list[str] = []
    for line in template.split("\n"):
        if any(key in line and not value for key, value in links.items()):
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    for key, value in links.items():
        text = text.replace(key, value)
    return text.replace("{ad}", first_name).replace("{hizmetler}", services)


def queue_post_visit(
    db: Session,
    appointment: Appointment,
    customer: Customer | None,
    salon: Salon | None,
    now: datetime,
) -> bool:
    """Mesaji kuyruga yazar. Yazildiysa True. Commit cagiranindir."""
    if salon is None or not salon.post_visit_enabled:
        return False
    if customer is None or customer.anonymized_at is not None or not customer.phone:
        return False
    key = f"{POST_VISIT_PREFIX}{appointment.id}"
    if db.scalar(select(ScheduledNotification.id).where(ScheduledNotification.dedupe_key == key)):
        return False
    services = ", ".join(i.service.name for i in appointment.items if i.service is not None)
    db.add(
        ScheduledNotification(
            customer_id=customer.id,
            channel="WHATSAPP",
            body=render_post_visit(salon, customer.first_name, services),
            due_at=now + timedelta(hours=max(0, salon.post_visit_delay_hours)),
            dedupe_key=key,
        )
    )
    return True


def cancel_post_visit(db: Session, appointment_id: int) -> None:
    """Randevu COMPLETED'dan baska duruma alindi: bekleyen mesaj geri cekilir."""
    db.execute(
        update(ScheduledNotification)
        .where(
            ScheduledNotification.dedupe_key == f"{POST_VISIT_PREFIX}{appointment_id}",
            ScheduledNotification.status == "PENDING",
        )
        .values(status="CANCELLED")
    )
