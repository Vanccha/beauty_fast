"""baskasi adina randevu ve grup randevusu alanlari

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-02 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('appointment', sa.Column('booked_by_customer_id', sa.Integer(), nullable=True))
    op.add_column('appointment', sa.Column('booking_group_id', sa.String(length=36), nullable=True))
    # Randevuyu alanin yazdigi ad: alan kisiye alicinin KAYITLI adi gosterilmez.
    op.add_column('appointment', sa.Column('beneficiary_label', sa.String(length=80), nullable=True))
    op.create_foreign_key(
        'fk_appointment_booked_by_customer', 'appointment', 'customer',
        ['booked_by_customer_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_appointment_booked_by', 'appointment', ['booked_by_customer_id'])
    op.create_index('ix_appointment_booking_group', 'appointment', ['booking_group_id'])

    op.add_column('slot_lock', sa.Column('beneficiary_customer_id', sa.Integer(), nullable=True))
    op.add_column('slot_lock', sa.Column('group_id', sa.String(length=36), nullable=True))
    op.create_index('ix_slot_lock_group_id', 'slot_lock', ['group_id'])
    # Grup kilidinde hizmet kimlikleri (virgullu, SIRALI); onayda yeniden hesaplanir.
    op.add_column('slot_lock', sa.Column('service_ids', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('slot_lock', 'service_ids')
    op.drop_index('ix_slot_lock_group_id', table_name='slot_lock')
    op.drop_column('slot_lock', 'group_id')
    op.drop_column('slot_lock', 'beneficiary_customer_id')

    op.drop_index('ix_appointment_booking_group', table_name='appointment')
    op.drop_index('ix_appointment_booked_by', table_name='appointment')
    op.drop_constraint('fk_appointment_booked_by_customer', 'appointment', type_='foreignkey')
    op.drop_column('appointment', 'beneficiary_label')
    op.drop_column('appointment', 'booking_group_id')
    op.drop_column('appointment', 'booked_by_customer_id')
