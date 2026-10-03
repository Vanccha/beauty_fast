"""ziyaret sonrasi mesaj ayarlari

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-03 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

GOOGLE_ORNEK = "https://g.page/r/ORNEK-GOOGLE-YORUM-LINKI/review"
INSTAGRAM_ORNEK = "https://instagram.com/ornek_salon"


def upgrade() -> None:
    op.add_column('salon', sa.Column('post_visit_enabled', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('salon', sa.Column('post_visit_delay_hours', sa.Integer(), server_default='2', nullable=False))
    op.add_column('salon', sa.Column('post_visit_message', sa.Text(), nullable=True))
    op.add_column('salon', sa.Column('google_review_url', sa.String(length=300), server_default=GOOGLE_ORNEK, nullable=False))
    op.add_column('salon', sa.Column('instagram_url', sa.String(length=300), server_default=INSTAGRAM_ORNEK, nullable=False))


def downgrade() -> None:
    op.drop_column('salon', 'instagram_url')
    op.drop_column('salon', 'google_review_url')
    op.drop_column('salon', 'post_visit_message')
    op.drop_column('salon', 'post_visit_delay_hours')
    op.drop_column('salon', 'post_visit_enabled')
