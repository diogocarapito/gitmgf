"""notifications for moderation decisions

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19 22:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = ('tool_approved', 'tool_rejected', 'tool_changes_requested', 'tool_hidden', 'tool_unhidden', 'revision_approved', 'revision_rejected')


def upgrade() -> None:
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('tool_id', sa.Integer(), nullable=True),
    sa.Column('tool_title', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.Enum(*KINDS, name='notification_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['tool_id'], ['tools.id'], name=op.f('fk_notifications_tool_id_tools'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications'))
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index('ix_notifications_user_read', ['user_id', 'read_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_tool_id'), ['tool_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_tool_id'))
        batch_op.drop_index('ix_notifications_user_read')
    op.drop_table('notifications')
