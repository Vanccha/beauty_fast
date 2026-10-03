"""kapora (deposit): salon ayarlari, randevu kapora alanlari, push tercihi

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-04 10:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Salon ayarlari (varsayilan KAPALI: mevcut davranis degismez) ------
    op.add_column('salon', sa.Column('deposit_enabled', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('salon', sa.Column('deposit_percent', sa.Integer(), server_default='20', nullable=False))
    op.add_column('salon', sa.Column('deposit_min_amount', sa.Integer(), server_default='100', nullable=False))
    op.add_column('salon', sa.Column('deposit_iban', sa.String(length=34), server_default='', nullable=False))
    op.add_column('salon', sa.Column('deposit_account_name', sa.String(length=120), server_default='', nullable=False))
    op.add_column('salon', sa.Column('deposit_bank_name', sa.String(length=80), server_default='', nullable=False))
    op.add_column('salon', sa.Column('deposit_deadline_minutes', sa.Integer(), server_default='60', nullable=False))
    op.add_column('salon', sa.Column('deposit_message', sa.Text(), nullable=True))

    # --- Randevu ---------------------------------------------------------
    op.add_column('appointment', sa.Column('deposit_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('appointment', sa.Column('deposit_status', sa.String(length=12), server_default='NONE', nullable=False))
    op.add_column('appointment', sa.Column('deposit_requested_at', sa.DateTime(), nullable=True))
    op.add_column('appointment', sa.Column('deposit_paid_at', sa.DateTime(), nullable=True))
    op.add_column('appointment', sa.Column('deposit_paid_by_staff_id', sa.Integer(), nullable=True))
    op.add_column('appointment', sa.Column('deposit_refund_due_at', sa.DateTime(), nullable=True))
    op.add_column('appointment', sa.Column('deposit_refunded_at', sa.DateTime(), nullable=True))
    op.add_column('appointment', sa.Column('deposit_refunded_by_staff_id', sa.Integer(), nullable=True))
    op.add_column('appointment', sa.Column('deposit_overdue_alerted_at', sa.DateTime(), nullable=True))
    op.add_column('appointment', sa.Column('deposit_refund_alerted_at', sa.DateTime(), nullable=True))
    op.create_foreign_key(
        'fk_appointment_deposit_paid_by', 'appointment', 'staff',
        ['deposit_paid_by_staff_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_appointment_deposit_refunded_by', 'appointment', 'staff',
        ['deposit_refunded_by_staff_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_appointment_deposit_status', 'appointment', ['deposit_status'])

    # --- Push tercihi ------------------------------------------------------
    op.add_column('push_subscription', sa.Column('pref_deposit', sa.Boolean(), server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column('push_subscription', 'pref_deposit')
    op.drop_index('ix_appointment_deposit_status', table_name='appointment')
    op.drop_constraint('fk_appointment_deposit_refunded_by', 'appointment', type_='foreignkey')
    op.drop_constraint('fk_appointment_deposit_paid_by', 'appointment', type_='foreignkey')
    for col in (
        'deposit_refund_alerted_at', 'deposit_overdue_alerted_at', 'deposit_refunded_by_staff_id',
        'deposit_refunded_at', 'deposit_refund_due_at', 'deposit_paid_by_staff_id',
        'deposit_paid_at', 'deposit_requested_at', 'deposit_status', 'deposit_amount',
    ):
        op.drop_column('appointment', col)
    for col in (
        'deposit_message', 'deposit_deadline_minutes', 'deposit_bank_name',
        'deposit_account_name', 'deposit_iban', 'deposit_min_amount', 'deposit_percent',
        'deposit_enabled',
    ):
        op.drop_column('salon', col)
