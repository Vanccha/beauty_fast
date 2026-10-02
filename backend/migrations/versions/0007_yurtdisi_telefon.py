"""yurtdisi telefon numaralari (E.164) icin telefon kolonlari genisletildi

Turkiye numaralari 10 hane (5XXXXXXXXX) olarak kalir; yurtdisi numaralari
``+`` ile birlikte en fazla 16 karakterdir (``+`` + 15 hane).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-02 22:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('customer', 'phone', type_=sa.String(16), existing_type=sa.String(10), existing_nullable=False)
    op.alter_column('verification_code', 'phone', type_=sa.String(16), existing_type=sa.String(10), existing_nullable=False)


def downgrade() -> None:
    # Yurtdisi numarasi varken geri donus veri kaybettirir; bilerek engellenir.
    bind = op.get_bind()
    foreign = bind.execute(sa.text("SELECT count(*) FROM customer WHERE length(phone) > 10")).scalar()
    if foreign:
        raise RuntimeError(f"{foreign} yurtdisi numarali musteri var; 0006'ya donulemez.")
    op.execute("DELETE FROM verification_code WHERE length(phone) > 10")
    op.alter_column('verification_code', 'phone', type_=sa.String(10), existing_type=sa.String(16), existing_nullable=False)
    op.alter_column('customer', 'phone', type_=sa.String(10), existing_type=sa.String(16), existing_nullable=False)
