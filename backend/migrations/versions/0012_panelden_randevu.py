"""panelden eklenen randevu: kaynak + olusturan personel

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-03 20:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'appointment',
        sa.Column('source', sa.String(length=10), server_default='ONLINE', nullable=False),
    )
    op.add_column('appointment', sa.Column('created_by_staff_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_appointment_created_by_staff',
        'appointment',
        'staff',
        ['created_by_staff_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_appointment_created_by_staff', 'appointment', type_='foreignkey')
    op.drop_column('appointment', 'created_by_staff_id')
    op.drop_column('appointment', 'source')
