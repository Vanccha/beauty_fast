"""personel yonetimi: instagram + kazanc yuzdesi

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-04 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('staff', sa.Column('instagram', sa.String(length=60), nullable=True))
    op.add_column('staff', sa.Column('commission_percent', sa.Float(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('staff', 'commission_percent')
    op.drop_column('staff', 'instagram')
