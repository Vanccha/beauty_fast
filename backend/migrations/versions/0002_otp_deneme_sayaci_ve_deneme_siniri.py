"""otp deneme sayaci ve deneme siniri

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30 13:32:19.010820
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('rate_limit_hit',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rate_limit_key_created', 'rate_limit_hit', ['key', 'created_at'], unique=False)

    op.add_column('verification_code', sa.Column('attempts', sa.Integer(), server_default='0', nullable=False))



def downgrade() -> None:
    op.drop_column('verification_code', 'attempts')

    op.drop_index('ix_rate_limit_key_created', table_name='rate_limit_hit')

    op.drop_table('rate_limit_hit')
