"""V2 guvenlik sertlestirmeleri: OTP kaba kuvvet korumasi, deneme sinirlari,
bakim ucu yetkisi, uretim yapilandirma dogrulamasi ve saat dilimi."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.auth import otp
from app.config import ConfigError, config, validate_config
from app.main import app
from app.time_utils import now_local

PHONE = "5321010000"
STRONG = "s" * 40


@pytest.fixture()
def client(salon):
    with TestClient(app) as test_client:
        yield test_client


def ok(response) -> dict:
    body = response.json()
    assert body["ok"] is True, body
    return body["data"]


def err(response) -> tuple[int, dict]:
    body = response.json()
    assert body["ok"] is False, body
    return response.status_code, body["error"]


def _verify(client, code: str, phone: str = PHONE):
    return client.post("/api/auth/otp/verify", json={"phone": phone, "code": code})


# ---------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------


def test_otp_code_is_burned_after_max_attempts(client):
    """v1'de yanlis deneme sayaci numaraya uretilen KOD sayisini sayiyordu;
    tek kod isteyen saldirgan sinirsiz tahmin yapabiliyordu."""
    ok(client.post("/api/auth/otp/send", json={"phone": PHONE}))

    for _ in range(otp.MAX_ATTEMPTS):
        status, error = err(_verify(client, "000000"))
        assert status == 401

    # Dogru kod bile artik kabul edilmez: kod yakildi.
    status, error = err(_verify(client, "123456"))
    assert status == 401
    assert "yeni kod" in error["message"]


def test_otp_verify_failures_are_limited_per_phone(client):
    """Yeni kod isteyerek deneme hakkini yenilemek de sinirlidir."""
    for _ in range(2):
        ok(client.post("/api/auth/otp/send", json={"phone": PHONE}))
        for _ in range(otp.MAX_ATTEMPTS):
            err(_verify(client, "000000"))

    ok(client.post("/api/auth/otp/send", json={"phone": PHONE}))
    status, error = err(_verify(client, "123456"))
    assert status == 429
    assert error["code"] == "RATE_LIMITED"


def test_otp_send_is_rate_limited_per_phone(client):
    """v1'de her istek onceki kodlari sildigi icin sayac hic dolmuyordu."""
    for _ in range(5):
        ok(client.post("/api/auth/otp/send", json={"phone": PHONE}))
    status, error = err(client.post("/api/auth/otp/send", json={"phone": PHONE}))
    assert status == 429
    # Baska numara etkilenmez.
    ok(client.post("/api/auth/otp/send", json={"phone": "5321010001"}))


def test_otp_code_cannot_be_used_twice(client, db):
    ok(client.post("/api/auth/otp/send", json={"phone": PHONE}))
    ok(_verify(client, "123456"))
    status, _ = err(_verify(client, "123456"))
    assert status == 401


def test_dev_code_never_returned_in_production(salon, db, monkeypatch):
    monkeypatch.setattr(otp, "config", dataclasses.replace(config, is_production=True))
    issued = otp.issue_otp(db, PHONE)
    assert issued.dev_code is None
    # DEV_OTP_CODE tanimli olsa bile uretimde sabit kod kullanilmaz.
    stored = db.scalar(
        otp.select(otp.VerificationCode).where(otp.VerificationCode.phone == PHONE)
    )
    assert stored.code != config.dev_otp_code or config.dev_otp_code == ""


# ---------------------------------------------------------------------
# Personel girisi
# ---------------------------------------------------------------------


def test_staff_login_locks_after_failures(client):
    for _ in range(5):
        status, _ = err(
            client.post("/api/auth/staff/login", json={"phone": "5551110001", "password": "x" * 6})
        )
        assert status == 401

    # Sinir dolunca dogru sifre de reddedilir.
    status, error = err(
        client.post("/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"})
    )
    assert status == 429

    # Baska personel etkilenmez.
    ok(client.post("/api/auth/staff/login", json={"phone": "5551110002", "password": "merve123"}))


def _staff_login(client, password: str, phone: str = "5551110001"):
    return client.post("/api/auth/staff/login", json={"phone": phone, "password": password})


def test_successful_staff_login_resets_counter(client):
    for _ in range(2):
        for _ in range(4):
            err(_staff_login(client, "yanlis"))
        ok(_staff_login(client, "admin123"))


# ---------------------------------------------------------------------
# Bakim ucu
# ---------------------------------------------------------------------


def test_cron_sweep_requires_secret_or_manager(client):
    status, _ = err(client.post("/api/cron/sweep"))
    assert status == 401
    status, _ = err(client.post("/api/cron/sweep", headers={"X-Cron-Secret": "yanlis"}))
    assert status == 401
    # GET ile tetikleme kaldirildi.
    assert client.get("/api/cron/sweep").status_code == 405

    ok(client.post("/api/cron/sweep", headers={"X-Cron-Secret": config.cron_secret}))


def test_cron_sweep_staff_role_gate(client):
    ok(client.post("/api/auth/staff/login", json={"phone": "5551110002", "password": "merve123"}))
    status, _ = err(client.post("/api/cron/sweep"))  # STAFF rolu yetmez
    assert status == 403

    client.post("/api/auth/logout", json={"scope": "staff"})
    ok(client.post("/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123"}))
    ok(client.post("/api/cron/sweep"))  # OWNER


# ---------------------------------------------------------------------
# Yapilandirma
# ---------------------------------------------------------------------


def _prod(**overrides):
    base = dict(
        app_env="production",
        is_production=True,
        session_secret=STRONG,
        phone_hash_secret=STRONG,
        cron_secret=STRONG,
        dev_otp_code="",
    )
    base.update(overrides)
    return dataclasses.replace(config, **base)


def test_production_config_accepts_strong_secrets():
    validate_config(_prod())


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_secret": "lokal-gelistirme-anahtari"},
        {"phone_hash_secret": "kisa"},
        {"cron_secret": ""},
        {"dev_otp_code": "123456"},
        {"database_url": "postgresql+psycopg://aurora:aurora@localhost:5432/aurora"},
    ],
)
def test_production_config_rejects_unsafe_values(overrides):
    with pytest.raises(ConfigError):
        validate_config(_prod(**overrides))


@pytest.mark.parametrize("url", ["sqlite:///./beauty.db", "mysql://u:p@localhost/aurora"])
def test_only_postgresql_is_accepted(url):
    """Proje yalnizca PostgreSQL'i destekler; baska bir veritabaniyla
    gelistirme modunda da acilmaz."""
    with pytest.raises(ConfigError, match="PostgreSQL"):
        validate_config(dataclasses.replace(config, database_url=url))


def test_unknown_app_env_is_treated_as_production(monkeypatch):
    import importlib

    import app.config as config_module

    monkeypatch.setenv("APP_ENV", "prod")
    try:
        reloaded = importlib.reload(config_module)
        assert reloaded.config.is_production is True
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        importlib.reload(config_module)


# ---------------------------------------------------------------------
# Saat dilimi
# ---------------------------------------------------------------------


def test_now_local_follows_salon_timezone():
    expected = datetime.now(ZoneInfo(config.timezone)).replace(tzinfo=None)
    assert abs(now_local() - expected) < timedelta(seconds=5)
    assert now_local().tzinfo is None
