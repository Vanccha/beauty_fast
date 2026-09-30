"""
====================================================================
SIFRE HASH'LEME - hashlib.scrypt
====================================================================

``bcrypt``/``passlib`` BILEREK eklenmedi: bu proje "klonla, pip install,
calistir" sozu veriyor. ``scrypt`` Python'un standart kutuphanesinde
bulunur ve bcrypt ile ayni sinifta (bellek-zor) bir KDF'tir.

Saklama bicimi tek bir metin alanindadir:

    scrypt$<saltHex>$<hashHex>

Salt her sifre icin ayri uretilir; iki ayni sifre farkli hash verir.
Dogrulama ``hmac.compare_digest`` ile yapilir - karsilastirma suresi
girdiye bagli olmadigi icin zamanlama saldirisina kapalidir.

(``src/lib/auth/password.ts`` karsiligi.)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import unicodedata

PREFIX = "scrypt"
SALT_BYTES = 16
KEY_LENGTH = 64

# Node'un varsayilan scrypt parametreleri (N=16384, r=8, p=1).
_N = 16384
_R = 8
_P = 1


def _normalize(plain: str) -> bytes:
    return unicodedata.normalize("NFKC", plain or "").encode("utf-8")


def _derive(plain: str, salt: bytes, length: int) -> bytes:
    return hashlib.scrypt(
        _normalize(plain), salt=salt, n=_N, r=_R, p=_P, dklen=length, maxmem=64 * 1024 * 1024
    )


def hash_password(plain: str) -> str:
    """Sifreyi hash'ler. Donen metin dogrudan ``staff.password_hash``a yazilir."""
    salt = os.urandom(SALT_BYTES)
    derived = _derive(plain, salt, KEY_LENGTH)
    return f"{PREFIX}${salt.hex()}${derived.hex()}"


def verify_password(plain: str, stored: str | None) -> bool:
    """Bozuk/eksik formatta hash gelirse istisna firlatmaz, ``False`` doner.

    Giris uc noktasi bu durumda da "hatali sifre" davranmalidir.
    """
    parts = (stored or "").split("$")
    if len(parts) != 3 or parts[0] != PREFIX:
        return False

    try:
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
    except ValueError:
        return False

    if not salt or not expected:
        return False

    try:
        actual = _derive(plain, salt, len(expected))
    except ValueError:
        return False

    return hmac.compare_digest(actual, expected)
