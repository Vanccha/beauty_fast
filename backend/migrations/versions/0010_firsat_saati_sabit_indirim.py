"""firsat saati sabit indirim ayarlari

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-03 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('salon', sa.Column('discount_enabled', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('salon', sa.Column('discount_rate', sa.Float(), server_default='0.10', nullable=False))
    op.add_column('salon', sa.Column('discount_cutoff_min', sa.Integer(), server_default='720', nullable=False))
    op.add_column('salon', sa.Column('discount_days', sa.String(length=20), server_default='1,2,3,4,5', nullable=False))


def downgrade() -> None:
    op.drop_column('salon', 'discount_days')
    op.drop_column('salon', 'discount_cutoff_min')
    op.drop_column('salon', 'discount_rate')
    op.drop_column('salon', 'discount_enabled')
