"""whatsapp karsilama mesaji

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-30 14:14:19.272368
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('whatsapp_contact',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('contact_key', sa.String(length=64), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(), nullable=False),
    sa.Column('welcomed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('contact_key')
    )
    op.add_column('salon', sa.Column('whatsapp_welcome_enabled', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('salon', sa.Column('whatsapp_welcome_message', sa.Text(), nullable=True))



def downgrade() -> None:
    op.drop_column('salon', 'whatsapp_welcome_message')
    op.drop_column('salon', 'whatsapp_welcome_enabled')

    op.drop_table('whatsapp_contact')
