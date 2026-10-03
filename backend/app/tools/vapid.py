"""VAPID anahtar cifti uretici (Web Push).

Kullanim:
    python -m app.tools.vapid

Cikti .env'e yapistirilir (VAPID_PRIVATE_KEY gizlidir, depoya girmez).
Anahtarlar degisirse mevcut tum cihaz abonelikleri gecersiz olur.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_keypair() -> dict[str, str]:
    """{"public": ..., "private": ...} - ikisi de base64url (ham bicim)."""
    vapid = Vapid01()
    vapid.generate_keys()
    raw_private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return {"public": _b64(raw_public), "private": _b64(raw_private)}


def main() -> None:
    pair = generate_keypair()
    print("# .env dosyasina ekleyin:")
    print(f"VAPID_PUBLIC_KEY={pair['public']}")
    print(f"VAPID_PRIVATE_KEY={pair['private']}")
    print("VAPID_SUBJECT=mailto:admin@salonunuz.com")


if __name__ == "__main__":
    main()
