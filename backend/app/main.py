"""
=====================================================================
Aurora - Akilli Salon Randevu Sistemi (FastAPI backend)
=====================================================================

Next.js + Prisma surumunun (``beauty_center_system``) backend'inin
FastAPI + SQLAlchemy karsiligi. API sozlesmesi (yol adlari, govde
alanlari, ``{ok, data}`` zarfi ve hata kodlari) birebir korunmustur;
mevcut istemci kodu degismeden bu sunucuya baglanabilir.

Calistirma:
    python -m app.seed          # demo verisi
    uvicorn app.main:app --reload

Dokumantasyon: http://localhost:8000/docs (yalnizca gelistirme modunda)

Uretimde (``APP_ENV=production``):
  * yapilandirma acilista dogrulanir; eksik sir varsa uygulama baslamaz,
  * ``/docs``, ``/redoc``, ``/openapi.json`` ve demo dizin sayfasi kapalidir,
  * migration'lar otomatik CALISMAZ - dagitim adiminda
    ``alembic upgrade head`` calistirilir (birden fazla worker ayni anda
    sema degistirmeye calismasin).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, appointments, auth, catalog, public, slots, webhooks
from .config import config, validate_config
from .db import init_db
from .errors import AppError
from .http import app_error_handler, unexpected_error_handler, validation_error_handler
from .services import messaging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aurora")


def _register_whatsapp_webhook() -> None:
    """WhatsApp webhook'unu (gelen mesajlar -> karsilama) kurar/tazeler.

    Idempotenttir; adres veya sir degistiyse Evolution'daki kaydi gunceller.
    Evolution'a ulasilamazsa uygulama yine acilir - yalnizca uyari yazilir.
    """
    admin = messaging.get_evolution_admin()
    if admin is None or not config.evolution_webhook_url:
        return
    try:
        if admin.set_webhook():
            logger.info("WhatsApp webhook'u kuruldu: %s", config.evolution_webhook_url)
    except messaging.DeliveryError as error:
        logger.warning("WhatsApp webhook'u kurulamadi: %s", error)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Acilista yapilandirmayi dogrula, semayi guncelle, yuklemeleri servis et."""
    for warning in validate_config():
        logger.warning(warning)
    if not config.is_production:
        init_db()
    _register_whatsapp_webhook()
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    # Yuklenen gorseller dogrudan servis edilir (tamamen lokal, S3 yok).
    application.mount("/uploads", StaticFiles(directory=config.upload_dir), name="uploads")
    yield


app = FastAPI(
    title="Aurora Salon API",
    description=__doc__,
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if config.is_production else "/docs",
    redoc_url=None if config.is_production else "/redoc",
    openapi_url=None if config.is_production else "/openapi.json",
)

# Arayuz istekleri Next.js rewrite'i uzerinden ayni origin'den gelir; CORS
# yalnizca tarayicinin API'ye DOGRUDAN baglandigi durumlar icindir.
# Gelistirmede localhost:3000 varsayilandir, uretimde CORS_ORIGINS ile
# (virgulle ayrilmis) acikca verilmelidir.
_cors_env = os.getenv("CORS_ORIGINS")
_cors_origins = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env is not None
    else ([] if config.is_production else ["http://localhost:3000", "http://127.0.0.1:3000"])
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)

app.include_router(auth.router)
app.include_router(public.router)
app.include_router(catalog.router)
app.include_router(slots.router)
app.include_router(appointments.router)
app.include_router(admin.router)
app.include_router(webhooks.router)


@app.get("/api/health", tags=["public"])
def health() -> dict:
    """Ayakta mi? (Zarf uygulanmaz - bilerek duz yanit.)"""
    return {"ok": True, "service": "aurora-salon-api"}


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    """Kok adres. Demo giris bilgilerini listeledigi icin YALNIZCA
    gelistirme modunda doner; uretimde bos bir 404'tur.

    Bu sunucu yalnizca API'dir; arayuz ayri bir surecte (``frontend/``,
    Next.js) calisir ve buraya bagli degildir. Tarayicidan dogrudan bu
    porta (8000) gelen kullanici bos bir 404 yerine nereye bakacagini
    gorsun diye kucuk bir dizin dondurulur.
    """
    if config.is_production:
        return HTMLResponse("Not Found", status_code=404)
    return HTMLResponse(
        """<!doctype html><html lang="tr"><meta charset="utf-8">
<title>Aurora Salon API</title>
<style>
  body{font:16px/1.6 system-ui,sans-serif;max-width:46rem;margin:3rem auto;padding:0 1.5rem;
       color:#2b2430;background:#faf7f5}
  h1{font-size:1.5rem;margin:0 0 .25rem} p.sub{color:#7a6e78;margin:0 0 2rem}
  ul{list-style:none;padding:0} li{margin:.4rem 0}
  a{color:#7c3a63;text-decoration:none;border-bottom:1px solid #e3d3dd}
  a:hover{border-color:#7c3a63}
  code{background:#f1e9ee;padding:.1rem .35rem;border-radius:.25rem;font-size:.9em}
  table{border-collapse:collapse;margin:.5rem 0 2rem} td{padding:.15rem .9rem .15rem 0}
  .note{color:#7a6e78;font-size:.9rem}
</style>
<h1>Aurora Salon API</h1>
<p class="sub">Akıllı salon randevu sistemi — FastAPI backend. Arayüz <code>frontend/</code> altında ayrı çalışır (<a href="http://localhost:3000">localhost:3000</a>).</p>

<ul>
  <li><a href="/docs">/docs</a> — etkileşimli API dokümanı (Swagger UI)</li>
  <li><a href="/redoc">/redoc</a> — okunabilir referans</li>
  <li><a href="/api/health">/api/health</a> — servis ayakta mı</li>
  <li><a href="/api/showcase">/api/showcase</a> — vitrin verisi (istatistik, ekip, yorumlar)</li>
  <li><a href="/api/catalog/services">/api/catalog/services</a> — hizmetler, öneri sırasıyla</li>
  <li><a href="/api/portfolio">/api/portfolio</a> — galeri</li>
</ul>

<p><strong>Demo personel girişi</strong> — <code>POST /api/auth/staff/login</code></p>
<table>
  <tr><td>Salon sahibi</td><td><code>05551110001</code></td><td><code>admin123</code></td></tr>
  <tr><td>Yönetici</td><td><code>05551110002</code></td><td><code>merve123</code></td></tr>
  <tr><td>Personel</td><td><code>05551110003</code></td><td><code>zeynep123</code></td></tr>
  <tr><td>Personel</td><td><code>05551110004</code></td><td><code>selin123</code></td></tr>
</table>

<p class="note">Müşteri girişi şifresizdir: <code>POST /api/auth/otp/send</code> ile
<code>05321010000</code> … <code>05321010024</code> numaralarından birine kod isteyin;
geliştirmede kod yanıtın <code>devCode</code> alanında döner.</p>
</html>"""
    )
