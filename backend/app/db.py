"""Veritabani baglantisi ve oturum yonetimi.

Veritabani PostgreSQL'dir (lokalde ``docker compose up -d db``). Sema
Alembic migration'lariyla yonetilir (``migrations/``), ``create_all``
KULLANILMAZ.

Yaris kosulu garantileri veritabani kisitlarindan gelir (``occupancy_cell``
uzerindeki unique kisit vb.). PostgreSQL varsayilan olarak READ COMMITTED
calistigi icin oku-degistir-yaz yapan yerler ayrica korunur
(``SELECT ... FOR UPDATE``, kosullu UPDATE); bkz. ``services/stock.py``,
``services/appointment_status.py``.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import BASE_DIR, config


class Base(DeclarativeBase):
    pass


# pool_pre_ping: veritabani yeniden baslatildiginda (docker restart vb.)
# havuzdaki kopmus baglantilar ilk istekte hataya donusmesin.
engine = create_engine(config.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Semayi en guncel migration'a (``alembic upgrade head``) getirir."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))

    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")


@contextmanager
def session_scope() -> Iterator[Session]:
    """Betikler ve testler icin transaction sarmalayici."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI bagimliligi: istek basina bir oturum."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
