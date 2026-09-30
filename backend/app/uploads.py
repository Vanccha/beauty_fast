"""
====================================================================
DOSYA YUKLEME (tamamen lokal)
====================================================================

Uzak depolama (S3 vb.) YOKTUR. Dosyalar ``UPLOAD_DIR/<alt-klasor>/<yyyy-mm>/``
altina rastgele bir isimle yazilir; ad kullanicidan gelmez.

Guvenlik notlari:
  * Dosya adi ``uuid4`` - kullanici girdisi yol olarak KULLANILMAZ,
    dolayisiyla ``../`` ile dizin disina cikma (path traversal) imkansiz.
  * Uzanti, izin verilen MIME tipinden TURETILIR; istemcinin gonderdigi
    dosya adina guvenilmez.
  * Icerik ayrica "sihirli bayt" (magic number) ile dogrulanir; sadece
    ``Content-Type`` basligina guvenmek yeterli degildir.

(``src/lib/upload.ts`` karsiligi.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import UploadFile

from .config import config
from .errors import AppError
from .time_utils import now_local

MAX_BYTES = 8 * 1024 * 1024  # 8 MB

ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _sniff(data: bytes) -> str | None:
    """Dosyanin gercekten iddia ettigi tur olup olmadigini bastan dogrular."""
    if len(data) >= 3 and data[0] == 0xFF and data[1] == 0xD8 and data[2] == 0xFF:
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class StoredFile:
    #: "/uploads/album/2026-09/<uuid>.jpg" - dogrudan <img src> olarak kullanilir
    url: str
    bytes: int
    mime_type: str

    def to_dict(self) -> dict:
        return {"url": self.url, "bytes": self.bytes, "mimeType": self.mime_type}


async def store_upload(file: UploadFile | None, subdirectory: str = "genel") -> StoredFile:
    if file is None or not getattr(file, "filename", None):
        raise AppError("VALIDATION", "Dosya bulunamadı.", 400)

    data = await file.read()
    if not data:
        raise AppError("VALIDATION", "Dosya bulunamadı.", 400)
    if len(data) > MAX_BYTES:
        raise AppError("VALIDATION", "Dosya çok büyük (en fazla 8 MB).", 413)

    detected = _sniff(data)
    if detected is None or detected not in ALLOWED:
        raise AppError("VALIDATION", "Yalnızca JPG, PNG veya WEBP yükleyebilirsiniz.", 415)

    now = now_local()
    bucket = f"{now.year}-{now.month:02d}"
    safe_subdir = "".join(ch for ch in subdirectory if ch.isalnum() or ch == "-") or "genel"

    relative_dir = Path(safe_subdir) / bucket
    file_name = f"{uuid4().hex}.{ALLOWED[detected]}"

    absolute_dir = config.upload_dir / relative_dir
    absolute_dir.mkdir(parents=True, exist_ok=True)
    (absolute_dir / file_name).write_bytes(data)

    return StoredFile(
        url=f"/uploads/{relative_dir.as_posix()}/{file_name}",
        bytes=len(data),
        mime_type=detected,
    )


def sanitize_external_link(raw: str) -> str:
    """Tasarim referansi olarak yapistirilan baglantiyi dogrular.

    Yalnizca http(s) kabul edilir - ``javascript:`` / ``data:`` semalari
    sayfaya gomuldugunde XSS'e donusebilecegi icin reddedilir.
    """
    parsed = urlparse((raw or "").strip())
    if not parsed.scheme or not parsed.netloc:
        raise AppError("VALIDATION", "Geçerli bir bağlantı girin.", 400)
    if parsed.scheme not in ("http", "https"):
        raise AppError("VALIDATION", "Yalnızca http/https bağlantıları kabul edilir.", 400)
    return parsed.geturl()
