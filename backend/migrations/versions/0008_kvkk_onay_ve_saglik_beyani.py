"""randevuya KVKK aydinlatma onayi ve saglik beyani zaman damgalari

Iki kolon da NULL'a izin verir; eski randevular NULL kalir. Saglik verisi
tutulmaz, yalnizca beyanin yapildigi an saklanir.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-03 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('appointment', sa.Column('privacy_notice_ack_at', sa.DateTime(), nullable=True))
    op.add_column('appointment', sa.Column('health_declaration_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('appointment', 'health_declaration_at')
    op.drop_column('appointment', 'privacy_notice_ack_at')
