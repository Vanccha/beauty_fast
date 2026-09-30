"""Alembic ortami.

Baglanti uygulamanin kendi motorundan (``app.db.engine``) alinir; boylece
``DATABASE_URL`` tek yerden yonetilir.
"""

from __future__ import annotations

from alembic import context

from app import models  # noqa: F401  (tablolarin metadata'ya kaydolmasi icin)
from app.db import Base, engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is not None:
        _run(connectable)
        return
    with engine.connect() as connection:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():  # pragma: no cover
    raise SystemExit("Offline (SQL uretme) modu desteklenmiyor.")
run_migrations_online()
