"""kvkk riza ve anonimlestirme alanlari

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('customer', sa.Column('marketing_consent_at', sa.DateTime(), nullable=True))
    op.add_column('customer', sa.Column('health_consent_at', sa.DateTime(), nullable=True))
    op.add_column('customer', sa.Column('anonymized_at', sa.DateTime(), nullable=True))

    # Mevcut alerji kayitlari personelin sozlu teyidiyle girilmisti; kayit
    # tarihi riza tarihi olarak tasinir. Gercek bir salonda bu musterilerden
    # yazili riza ayrica alinmalidir (DEGISIKLIKLER_V3.md).
    op.execute(
        """
        UPDATE customer SET health_consent_at = sub.first_at
        FROM (SELECT customer_id, MIN(created_at) AS first_at FROM allergy GROUP BY customer_id) sub
        WHERE customer.id = sub.customer_id
        """
    )


def downgrade() -> None:
    op.drop_column('customer', 'anonymized_at')
    op.drop_column('customer', 'health_consent_at')
    op.drop_column('customer', 'marketing_consent_at')
