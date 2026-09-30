"""v1 baslangic semasi

Revision ID: 0001
Revises: 
Create Date: 2026-09-30 13:31:36.463336
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('customer',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=10), nullable=False),
    sa.Column('first_name', sa.String(length=80), nullable=False),
    sa.Column('last_name', sa.String(length=80), nullable=True),
    sa.Column('email', sa.String(length=160), nullable=True),
    sa.Column('birth_date', sa.String(length=10), nullable=True),
    sa.Column('is_member', sa.Boolean(), nullable=False),
    sa.Column('loyalty_points', sa.Float(), nullable=False),
    sa.Column('tier', sa.String(length=10), nullable=False),
    sa.Column('engagement_opt_in', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('phone')
    )
    op.create_table('occupancy_stat',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('weekday', sa.Integer(), nullable=False),
    sa.Column('slot_min', sa.Integer(), nullable=False),
    sa.Column('occupancy', sa.Float(), nullable=False),
    sa.Column('sample_size', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('branch_id', 'weekday', 'slot_min')
    )
    op.create_table('salon',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('slug', sa.String(length=160), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('slot_lock',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('start_min', sa.Integer(), nullable=False),
    sa.Column('end_min', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=64), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('consumed_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_slot_lock_expires', 'slot_lock', ['expires_at'], unique=False)
    op.create_index(op.f('ix_slot_lock_session_id'), 'slot_lock', ['session_id'], unique=False)
    op.create_index('ix_slot_lock_staff_date', 'slot_lock', ['staff_id', 'date'], unique=False)

    op.create_table('slot_view_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('start_min', sa.Integer(), nullable=False),
    sa.Column('viewer_key', sa.String(length=64), nullable=False),
    sa.Column('viewed_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_slot_view_branch_date_start', 'slot_view_event', ['branch_id', 'date', 'start_min'], unique=False)

    op.create_table('allergy',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_allergy_customer_id'), 'allergy', ['customer_id'], unique=False)

    op.create_table('branch',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('salon_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('address', sa.String(length=300), nullable=True),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('open_minute', sa.Integer(), nullable=False),
    sa.Column('close_minute', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['salon_id'], ['salon.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_branch_salon_id'), 'branch', ['salon_id'], unique=False)

    op.create_table('customer_session',
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token')
    )
    op.create_index(op.f('ix_customer_session_customer_id'), 'customer_session', ['customer_id'], unique=False)

    op.create_table('phone_risk_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone_hash', sa.String(length=64), nullable=False),
    sa.Column('outcome', sa.String(length=12), nullable=False),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.Column('salon_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['salon_id'], ['salon.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_phone_risk_hash_occurred', 'phone_risk_event', ['phone_hash', 'occurred_at'], unique=False)

    op.create_table('verification_code',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('phone', sa.String(length=10), nullable=False),
    sa.Column('code', sa.String(length=8), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('consumed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_verification_phone_expires', 'verification_code', ['phone', 'expires_at'], unique=False)

    op.create_table('campaign',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('target_rule', sa.Text(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('starts_at', sa.DateTime(), nullable=True),
    sa.Column('ends_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_campaign_branch_id'), 'campaign', ['branch_id'], unique=False)

    op.create_table('inventory_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('unit', sa.String(length=10), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('critical_level', sa.Float(), nullable=False),
    sa.Column('cost_per_unit', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inventory_item_branch_id'), 'inventory_item', ['branch_id'], unique=False)

    op.create_table('resource',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resource_branch_id'), 'resource', ['branch_id'], unique=False)

    op.create_table('service_category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('icon', sa.String(length=16), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('branch_id', 'slug')
    )
    op.create_table('staff',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('password_hash', sa.String(length=300), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('photo_url', sa.String(length=300), nullable=True),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('phone')
    )
    op.create_index(op.f('ix_staff_branch_id'), 'staff', ['branch_id'], unique=False)

    op.create_table('appointment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('start_min', sa.Integer(), nullable=False),
    sa.Column('end_min', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('total_price', sa.Float(), nullable=False),
    sa.Column('discount_rate', sa.Float(), nullable=False),
    sa.Column('is_opportunity', sa.Boolean(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('shadow_parent_id', sa.Integer(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['shadow_parent_id'], ['appointment.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_appointment_branch_date', 'appointment', ['branch_id', 'date'], unique=False)
    op.create_index('ix_appointment_customer', 'appointment', ['customer_id'], unique=False)
    op.create_index('ix_appointment_staff_date', 'appointment', ['staff_id', 'date'], unique=False)

    op.create_table('campaign_grant',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('granted_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaign.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('campaign_id', 'customer_id')
    )
    op.create_table('customer_note',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('visibility', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_customer_note_customer_id'), 'customer_note', ['customer_id'], unique=False)

    op.create_table('portfolio_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('image_url', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['service_category.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_portfolio_item_branch_id'), 'portfolio_item', ['branch_id'], unique=False)

    op.create_table('service',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price', sa.Float(), nullable=False),
    sa.Column('active_before_min', sa.Integer(), nullable=False),
    sa.Column('passive_min', sa.Integer(), nullable=False),
    sa.Column('active_after_min', sa.Integer(), nullable=False),
    sa.Column('buffer_min', sa.Integer(), nullable=False),
    sa.Column('shadow_host_allowed', sa.Boolean(), nullable=False),
    sa.Column('shadow_guest_allowed', sa.Boolean(), nullable=False),
    sa.Column('recommended_repeat_days', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['service_category.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_branch_id'), 'service', ['branch_id'], unique=False)

    op.create_table('staff_session',
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token')
    )
    op.create_index(op.f('ix_staff_session_staff_id'), 'staff_session', ['staff_id'], unique=False)

    op.create_table('time_off',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('start_min', sa.Integer(), nullable=True),
    sa.Column('end_min', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=200), nullable=True),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_time_off_staff_date', 'time_off', ['staff_id', 'date'], unique=False)

    op.create_table('working_hour',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('weekday', sa.Integer(), nullable=False),
    sa.Column('start_min', sa.Integer(), nullable=False),
    sa.Column('end_min', sa.Integer(), nullable=False),
    sa.Column('is_working', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('staff_id', 'weekday')
    )
    op.create_table('appointment_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('offset_min', sa.Integer(), nullable=False),
    sa.Column('active_before_min', sa.Integer(), nullable=False),
    sa.Column('passive_min', sa.Integer(), nullable=False),
    sa.Column('active_after_min', sa.Integer(), nullable=False),
    sa.Column('buffer_min', sa.Integer(), nullable=False),
    sa.Column('price', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['service_id'], ['service.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_appointment_item_appointment', 'appointment_item', ['appointment_id'], unique=False)

    op.create_table('appointment_resource',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('start_min', sa.Integer(), nullable=False),
    sa.Column('end_min', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resource_id'], ['resource.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_appointment_resource_resource', 'appointment_resource', ['resource_id'], unique=False)

    op.create_table('customer_photo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('image_url', sa.String(length=300), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('color_tag', sa.String(length=60), nullable=True),
    sa.Column('product_info', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_customer_photo_customer_created', 'customer_photo', ['customer_id', 'created_at'], unique=False)

    op.create_table('design_reference',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_design_reference_appointment', 'design_reference', ['appointment_id'], unique=False)

    op.create_table('loyalty_entry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('delta', sa.Float(), nullable=False),
    sa.Column('reason', sa.String(length=24), nullable=False),
    sa.Column('breakdown', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_loyalty_customer_created', 'loyalty_entry', ['customer_id', 'created_at'], unique=False)

    op.create_table('occupancy_cell',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_type', sa.String(length=10), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=10), nullable=False),
    sa.Column('cell_index', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('lock_id', sa.Integer(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lock_id'], ['slot_lock.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('owner_type', 'owner_id', 'date', 'cell_index', name='uq_occupancy_cell')
    )
    op.create_index('ix_occupancy_date_owner', 'occupancy_cell', ['date', 'owner_type'], unique=False)
    op.create_index('ix_occupancy_expires', 'occupancy_cell', ['expires_at'], unique=False)

    op.create_table('reminder_rule',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('formula', sa.String(length=20), nullable=False),
    sa.Column('base_days', sa.Integer(), nullable=False),
    sa.Column('params', sa.Text(), nullable=False),
    sa.Column('pre_reminder_hours', sa.Integer(), nullable=True),
    sa.Column('channel', sa.String(length=10), nullable=False),
    sa.Column('template', sa.Text(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['service_category.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['service_id'], ['service.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reminder_rule_branch_id'), 'reminder_rule', ['branch_id'], unique=False)

    op.create_table('review',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('branch_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=True),
    sa.Column('staff_id', sa.Integer(), nullable=True),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('author_name', sa.String(length=80), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.Column('service_names', sa.String(length=300), nullable=True),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('is_featured', sa.Boolean(), nullable=False),
    sa.Column('reply', sa.Text(), nullable=True),
    sa.Column('replied_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('appointment_id')
    )
    op.create_index('ix_review_branch_published', 'review', ['branch_id', 'is_published'], unique=False)
    op.create_index('ix_review_customer', 'review', ['customer_id'], unique=False)
    op.create_index('ix_review_staff', 'review', ['staff_id'], unique=False)

    op.create_table('service_consumable',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('qty_per_use', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['inventory_item.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['service_id'], ['service.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('service_id', 'item_id')
    )
    op.create_table('service_resource',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('only_during_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['resource_id'], ['resource.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['service_id'], ['service.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('service_id', 'resource_id')
    )
    op.create_table('staff_service',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('staff_id', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=False),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('speed_factor', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['service.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('staff_id', 'service_id')
    )
    op.create_table('stock_movement',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=False),
    sa.Column('delta', sa.Float(), nullable=False),
    sa.Column('reason', sa.String(length=30), nullable=False),
    sa.Column('appointment_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointment.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['item_id'], ['inventory_item.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('appointment_id', 'item_id', name='uq_stock_movement_appointment_item')
    )
    op.create_index('ix_stock_movement_item_created', 'stock_movement', ['item_id', 'created_at'], unique=False)

    op.create_table('scheduled_notification',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('rule_id', sa.Integer(), nullable=True),
    sa.Column('channel', sa.String(length=10), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('due_at', sa.DateTime(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.Column('dedupe_key', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['rule_id'], ['reminder_rule.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe_key')
    )
    op.create_index('ix_scheduled_status_due', 'scheduled_notification', ['status', 'due_at'], unique=False)



def downgrade() -> None:
    op.drop_index('ix_scheduled_status_due', table_name='scheduled_notification')

    op.drop_table('scheduled_notification')
    op.drop_index('ix_stock_movement_item_created', table_name='stock_movement')

    op.drop_table('stock_movement')
    op.drop_table('staff_service')
    op.drop_table('service_resource')
    op.drop_table('service_consumable')
    op.drop_index('ix_review_staff', table_name='review')
    op.drop_index('ix_review_customer', table_name='review')
    op.drop_index('ix_review_branch_published', table_name='review')

    op.drop_table('review')
    op.drop_index(op.f('ix_reminder_rule_branch_id'), table_name='reminder_rule')

    op.drop_table('reminder_rule')
    op.drop_index('ix_occupancy_expires', table_name='occupancy_cell')
    op.drop_index('ix_occupancy_date_owner', table_name='occupancy_cell')

    op.drop_table('occupancy_cell')
    op.drop_index('ix_loyalty_customer_created', table_name='loyalty_entry')

    op.drop_table('loyalty_entry')
    op.drop_index('ix_design_reference_appointment', table_name='design_reference')

    op.drop_table('design_reference')
    op.drop_index('ix_customer_photo_customer_created', table_name='customer_photo')

    op.drop_table('customer_photo')
    op.drop_index('ix_appointment_resource_resource', table_name='appointment_resource')

    op.drop_table('appointment_resource')
    op.drop_index('ix_appointment_item_appointment', table_name='appointment_item')

    op.drop_table('appointment_item')
    op.drop_table('working_hour')
    op.drop_index('ix_time_off_staff_date', table_name='time_off')

    op.drop_table('time_off')
    op.drop_index(op.f('ix_staff_session_staff_id'), table_name='staff_session')

    op.drop_table('staff_session')
    op.drop_index(op.f('ix_service_branch_id'), table_name='service')

    op.drop_table('service')
    op.drop_index(op.f('ix_portfolio_item_branch_id'), table_name='portfolio_item')

    op.drop_table('portfolio_item')
    op.drop_index(op.f('ix_customer_note_customer_id'), table_name='customer_note')

    op.drop_table('customer_note')
    op.drop_table('campaign_grant')
    op.drop_index('ix_appointment_staff_date', table_name='appointment')
    op.drop_index('ix_appointment_customer', table_name='appointment')
    op.drop_index('ix_appointment_branch_date', table_name='appointment')

    op.drop_table('appointment')
    op.drop_index(op.f('ix_staff_branch_id'), table_name='staff')

    op.drop_table('staff')
    op.drop_table('service_category')
    op.drop_index(op.f('ix_resource_branch_id'), table_name='resource')

    op.drop_table('resource')
    op.drop_index(op.f('ix_inventory_item_branch_id'), table_name='inventory_item')

    op.drop_table('inventory_item')
    op.drop_index(op.f('ix_campaign_branch_id'), table_name='campaign')

    op.drop_table('campaign')
    op.drop_index('ix_verification_phone_expires', table_name='verification_code')

    op.drop_table('verification_code')
    op.drop_index('ix_phone_risk_hash_occurred', table_name='phone_risk_event')

    op.drop_table('phone_risk_event')
    op.drop_index(op.f('ix_customer_session_customer_id'), table_name='customer_session')

    op.drop_table('customer_session')
    op.drop_index(op.f('ix_branch_salon_id'), table_name='branch')

    op.drop_table('branch')
    op.drop_index(op.f('ix_allergy_customer_id'), table_name='allergy')

    op.drop_table('allergy')
    op.drop_index('ix_slot_view_branch_date_start', table_name='slot_view_event')

    op.drop_table('slot_view_event')
    op.drop_index('ix_slot_lock_staff_date', table_name='slot_lock')
    op.drop_index(op.f('ix_slot_lock_session_id'), table_name='slot_lock')
    op.drop_index('ix_slot_lock_expires', table_name='slot_lock')

    op.drop_table('slot_lock')
    op.drop_table('salon')
    op.drop_table('occupancy_stat')
    op.drop_table('customer')
