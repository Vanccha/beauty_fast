"""Uygulama genelinde kullanılan tipli hatalar (``src/lib/errors.ts`` karşılığı)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError


class AppError(Exception):
    """Koda çevrilebilen, istemciye güvenle gösterilebilen hata."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class SlotConflictError(AppError):
    """Slot çakışması.

    ``held_until``, kullanıcıya "az önce alındı, HH:MM'e kadar rezerve"
    mesajını gösterebilmek için doldurulur.
    """

    def __init__(self, held_until: datetime | None = None) -> None:
        super().__init__(
            "SLOT_TAKEN",
            "Bu saat az önce başka bir müşteri tarafından alındı.",
            409,
            {"heldUntil": held_until.isoformat() if held_until else None},
        )
        self.held_until = held_until


class VersionConflictError(AppError):
    """Optimistic locking ihlali: kayıt biz okuduktan sonra değişmiş."""

    def __init__(self, current_version: int | None = None) -> None:
        super().__init__(
            "VERSION_MISMATCH",
            "Bu randevu başka bir kullanıcı tarafından güncellendi. Lütfen sayfayı yenileyin.",
            409,
            {"currentVersion": current_version},
        )
        self.current_version = current_version


def is_unique_violation(error: BaseException) -> bool:
    """Unique constraint ihlali mi? (Prisma'daki P2002.)

    PostgreSQL SQLSTATE ``23505`` (unique_violation) koduna bakilir; hata
    mesajinin metnine guvenilmez.
    """
    if not isinstance(error, IntegrityError):
        return False
    return getattr(error.orig, "sqlstate", None) == "23505"
