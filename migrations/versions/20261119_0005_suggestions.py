"""suggestions to tool authors; per-message Reply-To

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19 12:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('suggestions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tool_id', sa.Integer(), nullable=False),
    sa.Column('recipient_id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=True),
    sa.Column('kind', sa.Enum('feature', 'improvement', 'other', name='suggestion_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('allow_reply', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], name=op.f('fk_suggestions_recipient_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], name=op.f('fk_suggestions_sender_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tool_id'], ['tools.id'], name=op.f('fk_suggestions_tool_id_tools'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suggestions'))
    )
    with op.batch_alter_table('suggestions', schema=None) as batch_op:
        batch_op.create_index('ix_suggestions_recipient_read', ['recipient_id', 'read_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_suggestions_sender_id'), ['sender_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_suggestions_tool_id'), ['tool_id'], unique=False)
    with op.batch_alter_table('email_outbox', schema=None, recreate='never') as batch_op:
        batch_op.add_column(sa.Column('reply_to', sa.String(length=254), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('email_outbox', schema=None, recreate='never') as batch_op:
        batch_op.drop_column('reply_to')
    with op.batch_alter_table('suggestions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_suggestions_tool_id'))
        batch_op.drop_index(batch_op.f('ix_suggestions_sender_id'))
        batch_op.drop_index('ix_suggestions_recipient_read')
    op.drop_table('suggestions')
