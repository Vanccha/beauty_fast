"""
====================================================================
MESAJ GONDERIMI - surucu katmani
====================================================================

OTP kodlari ve bildirim kuyrugu (hatirlatmalar) tek bir arayuzden
gonderilir; hangi kanalin kullanilacagini ``NOTIFICATION_DRIVER`` secer:

  * ``console``   - mesaj log'a yazilir (gelistirme).
  * ``evolution`` - WhatsApp, Evolution API uzerinden (Baileys / QR ile
    bagli numara). Resmi Cloud API KULLANILMAZ; ucret yoktur ama numara
    WhatsApp tarafindan kisitlanabilir. Bu yuzden:
      - yalnizca bilgilendirme mesajlari (OTP, randevu hatirlatmasi)
        gonderilir, toplu kampanya gonderimi YOKTUR,
      - kuyruk mesajlari arasina bekleme konur (``WHATSAPP_SEND_INTERVAL_MS``),
      - salonun kisisel/ana numarasi degil, ayri bir numara kullanilmalidir.

Evolution API uclari (v2.3):
  POST   /message/sendText/{instance}         {"number": "905321234567", "text": "..."}
  GET    /instance/connectionState/{instance} -> {"instance": {"state": "open"}}
         (instance yoksa 404; state: open | connecting | close)
  POST   /instance/create                     {"instanceName", "integration", "qrcode"}
  GET    /instance/connect/{instance}         -> {"base64": "data:image/png;...", "pairingCode"}
  DELETE /instance/logout/{instance}          numaranin baglantisini keser
  POST   /webhook/set/{instance}              {"webhook": {"enabled", "url", "events", ...}}
Kimlik dogrulama ``apikey`` basligiyla yapilir.

DIKKAT: numara bagli degilken (state != "open") ``sendText`` hata donmez,
uzun sure asili kalir. Bu yuzden gondermeden once ``is_ready()`` ile
durum kontrol edilir (OTP'de her istekte, kuyrukta calistirma basina bir kez).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import config

logger = logging.getLogger("aurora.messaging")


class DeliveryError(Exception):
    """Mesaj karsi tarafa teslim edilemedi (ag hatasi, baglanti kopuk, gecersiz numara)."""


@dataclass(frozen=True)
class SendResult:
    #: Saglayicinin mesaj kimligi (Evolution: ``key.id``); console'da None.
    provider_id: str | None = None


class Sender(Protocol):
    name: str

    def send(self, phone: str, text: str) -> SendResult: ...

    def is_ready(self) -> tuple[bool, str]:
        """(gonderime hazir mi, durum aciklamasi)."""
        ...


def to_whatsapp_number(phone: str) -> str:
    """Sistemdeki ``5XXXXXXXXX`` bicimini WhatsApp'in bekledigi ulke kodlu
    bicime (``905XXXXXXXXX``) cevirir. Tam bir WhatsApp adresi
    (``...@lid``, ``...@s.whatsapp.net``) oldugu gibi birakilir."""
    if "@" in phone:
        return phone
    digits = "".join(ch for ch in phone if ch.isdigit())
    code = config.whatsapp_country_code
    if digits.startswith(code) and len(digits) > 10:
        return digits
    return code + digits.lstrip("0")


class ConsoleSender:
    name = "console"

    def send(self, phone: str, text: str) -> SendResult:
        logger.info("[mesaj] %s -> %s", phone, text)
        return SendResult()

    def is_ready(self) -> tuple[bool, str]:
        return True, "console"


class EvolutionSender:
    name = "evolution"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        instance: str,
        timeout: httpx.Timeout | float = httpx.Timeout(15.0, connect=5.0),
        client: httpx.Client | None = None,
    ) -> None:
        self.instance = instance
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"apikey": api_key},
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise DeliveryError(f"Evolution API'ye ulaşılamadı: {error}") from error

    def send(self, phone: str, text: str) -> SendResult:
        response = self._request(
            "POST",
            f"/message/sendText/{self.instance}",
            json={"number": to_whatsapp_number(phone), "text": text},
        )
        if response.status_code >= 400:
            # Govde, numaranin WhatsApp'ta olmadigi gibi durumlari aciklar;
            # log'a yazilir ama istemciye tasinmaz.
            raise DeliveryError(
                f"Evolution API {response.status_code}: {response.text[:300]}"
            )
        try:
            provider_id = (response.json().get("key") or {}).get("id")
        except (ValueError, AttributeError):
            provider_id = None
        return SendResult(provider_id=provider_id)

    def connection_state(self) -> str:
        response = self._request("GET", f"/instance/connectionState/{self.instance}")
        if response.status_code >= 400:
            raise DeliveryError(
                f"Evolution API {response.status_code}: {response.text[:300]}"
            )
        try:
            return str(response.json()["instance"]["state"])
        except (ValueError, KeyError, TypeError) as error:
            raise DeliveryError(f"Beklenmeyen yanıt: {response.text[:300]}") from error

    def is_ready(self) -> tuple[bool, str]:
        try:
            state = self.connection_state()
        except DeliveryError as error:
            return False, str(error)
        # "open" disindaki her durum (close, connecting) gonderimi basarisiz kilar.
        return state == "open", state


@dataclass(frozen=True)
class QrCode:
    #: "data:image/png;base64,..." - dogrudan <img src> olarak kullanilir.
    image: str
    #: QR yerine telefona girilebilecek eslestirme kodu (varsa).
    pairing_code: str | None


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise DeliveryError(f"Evolution API {response.status_code}: {response.text[:300]}")


class EvolutionAdmin:
    """Numara baglama islemleri (panel ve ``python -m app.whatsapp``)."""

    def __init__(self, sender: EvolutionSender) -> None:
        self.sender = sender

    def state(self) -> str:
        """Instance hic olusturulmamissa "missing" doner."""
        response = self.sender._request(
            "GET", f"/instance/connectionState/{self.sender.instance}"
        )
        if response.status_code == 404:
            return "missing"
        _raise_for_status(response)
        return str(response.json().get("instance", {}).get("state", "unknown"))

    def set_webhook(self) -> bool:
        """Gelen mesaj bildirimlerini backend'e yonlendirir (idempotent).

        ``EVOLUTION_WEBHOOK_URL`` tanimli degilse kurulmaz ve False doner.
        Instance henuz yoksa (QR hic istenmediyse) de False doner.
        """
        if not config.evolution_webhook_url:
            return False
        from .whatsapp_inbound import WEBHOOK_EVENTS

        url = (
            f"{config.evolution_webhook_url}/api/webhooks/evolution"
            f"?token={config.evolution_webhook_secret}"
        )
        response = self.sender._request(
            "POST",
            f"/webhook/set/{self.sender.instance}",
            json={
                "webhook": {
                    "enabled": True,
                    "url": url,
                    "byEvents": False,
                    "base64": False,
                    "events": WEBHOOK_EVENTS,
                }
            },
        )
        if response.status_code == 404:
            return False
        _raise_for_status(response)
        return True

    def request_qr(self) -> QrCode | None:
        """Baglanti icin QR uretir; instance yoksa once olusturur.

        Numara zaten bagliysa (state == "open") None doner. QR yaklasik 40
        saniye gecerlidir; suresi dolunca bu cagri yenisini uretir.
        """
        instance = self.sender.instance
        state = self.state()
        if state == "open":
            return None
        if state == "missing":
            _raise_for_status(
                self.sender._request(
                    "POST",
                    "/instance/create",
                    json={
                        "instanceName": instance,
                        "integration": "WHATSAPP-BAILEYS",
                        "qrcode": True,
                    },
                )
            )

        # Webhook, telefon baglanmadan ONCE kurulur: baglanti aninda gelen
        # sohbet gecmisi (tanidik kisiler) kacirilmasin.
        self.set_webhook()

        response = self.sender._request("GET", f"/instance/connect/{instance}")
        _raise_for_status(response)
        payload = response.json()
        image = payload.get("base64") or (payload.get("qrcode") or {}).get("base64")
        if not image:
            raise DeliveryError(f"Yanıtta QR kodu yok: {str(payload)[:300]}")
        if not image.startswith("data:"):
            image = "data:image/png;base64," + image
        return QrCode(image=image, pairing_code=payload.get("pairingCode") or None)

    def logout(self) -> None:
        """Numaranin baglantisini keser (telefondaki "bagli cihaz" da silinir)."""
        response = self.sender._request("DELETE", f"/instance/logout/{self.sender.instance}")
        _raise_for_status(response)


def get_evolution_admin() -> EvolutionAdmin | None:
    """Surucu evolution degilse None."""
    sender = get_sender()
    return EvolutionAdmin(sender) if isinstance(sender, EvolutionSender) else None


_sender: Sender | None = None


def get_sender() -> Sender:
    """Yapilandirilmis surucuyu doner (surec basina tek ornek).

    Testler ``messaging._sender``i degistirerek sahte bir surucu kullanir.
    """
    global _sender
    if _sender is None:
        if config.notification_driver == "evolution":
            _sender = EvolutionSender(
                base_url=config.evolution_api_url,
                api_key=config.evolution_api_key,
                instance=config.evolution_instance,
            )
        else:
            _sender = ConsoleSender()
    return _sender
