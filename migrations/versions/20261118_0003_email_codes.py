"""email verification and reset codes

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('email_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=10), nullable=False),
    sa.Column('ticket_hash', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('sends', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_codes')),
    sa.UniqueConstraint('ticket_hash', name=op.f('uq_email_codes_ticket_hash'))
    )
    with op.batch_alter_table('email_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_codes_email'), ['email'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('email_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_codes_email'))
    op.drop_table('email_codes')
