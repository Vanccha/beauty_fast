"""bildirim gonderim denemeleri

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 13:47:42.712815
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scheduled_notification', sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('scheduled_notification', sa.Column('last_error', sa.String(length=300), nullable=True))
    op.add_column('scheduled_notification', sa.Column('next_attempt_at', sa.DateTime(), nullable=True))



def downgrade() -> None:
    op.drop_column('scheduled_notification', 'next_attempt_at')
    op.drop_column('scheduled_notification', 'last_error')
    op.drop_column('scheduled_notification', 'attempts')

