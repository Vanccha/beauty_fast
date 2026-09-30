"""
=====================================================================
WHATSAPP (Evolution API) - kurulum ve bakim komutlari
=====================================================================

    python -m app.whatsapp status              # baglanti durumu
    python -m app.whatsapp connect             # instance olustur + QR kodu
    python -m app.whatsapp test 5321234567     # deneme mesaji gonder

``connect`` QR kodunu ``whatsapp-qr.png`` dosyasina yazar. Telefonda
WhatsApp > Bagli cihazlar > Cihaz bagla ile okutun. QR yaklasik 40 saniye
gecerlidir; suresi dolarsa komutu tekrar calistirin.

Ayarlar ``.env``den okunur: EVOLUTION_API_URL, EVOLUTION_API_KEY,
EVOLUTION_INSTANCE.
"""

from __future__ import annotations

import base64
import sys

from .config import BASE_DIR, config
from .services.messaging import DeliveryError, EvolutionAdmin, EvolutionSender

QR_FILE = BASE_DIR / "whatsapp-qr.png"


def _admin() -> EvolutionAdmin:
    if not (config.evolution_api_url and config.evolution_api_key and config.evolution_instance):
        sys.exit(
            "EVOLUTION_API_URL, EVOLUTION_API_KEY ve EVOLUTION_INSTANCE "
            ".env içinde tanımlı olmalı."
        )
    return EvolutionAdmin(
        EvolutionSender(
            config.evolution_api_url, config.evolution_api_key, config.evolution_instance
        )
    )


def status() -> None:
    try:
        state = _admin().state()
    except DeliveryError as error:
        sys.exit(f"Durum alınamadı: {error}")
    print(f"Instance '{config.evolution_instance}': {state}")
    if state != "open":
        print("Numara bağlı değil. `python -m app.whatsapp connect` ile QR kodunu okutun.")


def connect() -> None:
    try:
        qr = _admin().request_qr()
    except DeliveryError as error:
        sys.exit(f"QR alınamadı: {error}")
    if qr is None:
        print(f"Instance '{config.evolution_instance}' zaten bağlı. Yapılacak bir şey yok.")
        return

    QR_FILE.write_bytes(base64.b64decode(qr.image.split(",", 1)[-1]))
    print(f"QR kodu kaydedildi: {QR_FILE}")
    if qr.pairing_code:
        print(f"Eşleştirme kodu (QR yerine): {qr.pairing_code}")
    print(
        "Telefonda: WhatsApp > Bağlı cihazlar > Cihaz bağla. Okuttuktan sonra\n"
        "`python -m app.whatsapp status` ile 'open' durumunu doğrulayın.\n"
        "(Aynı işlem admin panelinde WhatsApp sayfasından da yapılabilir.)"
    )


def test(phone: str) -> None:
    try:
        result = _admin().sender.send(phone, "Aurora: WhatsApp bağlantısı çalışıyor ✅")
    except DeliveryError as error:
        sys.exit(f"Gönderilemedi: {error}")
    print(f"Gönderildi (mesaj kimliği: {result.provider_id})")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - platforma bagli
        pass

    args = sys.argv[1:]
    if args[:1] == ["status"]:
        status()
    elif args[:1] == ["connect"]:
        connect()
    elif args[:1] == ["test"] and len(args) == 2:
        test(args[1])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
