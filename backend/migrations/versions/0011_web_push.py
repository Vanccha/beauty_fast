"""web push abonelikleri ve uygulama durumu

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-03 18:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'push_subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('staff_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh', sa.String(length=200), nullable=False),
        sa.Column('auth', sa.String(length=100), nullable=False),
        sa.Column('user_agent', sa.String(length=300), nullable=True),
        sa.Column('pref_new', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('pref_cancel', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('pref_alerts', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('pref_whatsapp', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_success_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint'),
    )
    op.create_index('ix_push_subscription_staff', 'push_subscription', ['staff_id'])
    op.create_table(
        'app_state',
        sa.Column('key', sa.String(length=80), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('app_state')
    op.drop_index('ix_push_subscription_staff', table_name='push_subscription')
    op.drop_table('push_subscription')
