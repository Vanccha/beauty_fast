"""Admin girisinde "Beni hatirla": kalici cerez/30 gun vs tarayici-oturumu/12 saat."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import StaffSession
from app.time_utils import now_local


def _login(**extra):
    c = TestClient(app)
    r = c.post(
        "/api/auth/staff/login", json={"phone": "5551110001", "password": "admin123", **extra}
    )
    assert r.status_code == 200, r.text
    return c, r.headers["set-cookie"]


def _session(db, client):
    db.expire_all()
    token = client.cookies.get("staff_session")
    return db.scalar(select(StaffSession).where(StaffSession.token == token))


def test_remember_me_sets_persistent_cookie_and_30_days(salon, db):
    c, cookie = _login(rememberMe=True)
    assert "Max-Age=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    max_age = int(cookie.split("Max-Age=")[1].split(";")[0])
    assert abs(max_age - 30 * 86400) < 120
    left = _session(db, c).expires_at - now_local()
    assert timedelta(days=29, hours=23) < left <= timedelta(days=30)
    assert c.get("/api/me").status_code == 200


def test_default_is_browser_session_cookie_and_12_hours(salon, db):
    c, cookie = _login()
    assert "Max-Age" not in cookie and "expires" not in cookie.lower()
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    left = _session(db, c).expires_at - now_local()
    assert timedelta(hours=11, minutes=55) < left <= timedelta(hours=12)
    assert c.get("/api/me").status_code == 200


def test_remember_me_false_explicit(salon, db):
    c, cookie = _login(rememberMe=False)
    assert "Max-Age" not in cookie
