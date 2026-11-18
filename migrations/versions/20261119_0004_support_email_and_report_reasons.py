"""tool support email; report reason "inappropriate"; drop reports.csam

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_REASONS = ('broken_link', 'dangerous_content', 'security_privacy', 'incorrect_certification', 'spam', 'copyright', 'illegal', 'other')
NEW_REASONS = ('broken_link', 'dangerous_content', 'inappropriate', 'security_privacy', 'incorrect_certification', 'spam', 'copyright', 'illegal', 'other')


def _reason(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name='report_reason', native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    with op.batch_alter_table('tools', schema=None, recreate='never') as batch_op:
        batch_op.add_column(sa.Column('support_email', sa.String(length=254), nullable=True))
    with op.batch_alter_table('reports', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('reason', existing_type=_reason(OLD_REASONS), type_=_reason(NEW_REASONS), existing_nullable=False)
        batch_op.drop_column('csam')


def downgrade() -> None:
    op.execute("UPDATE reports SET reason = 'other' WHERE reason = 'inappropriate'")
    with op.batch_alter_table('reports', schema=None, recreate='always') as batch_op:
        batch_op.add_column(sa.Column('csam', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.alter_column('reason', existing_type=_reason(NEW_REASONS), type_=_reason(OLD_REASONS), existing_nullable=False)
    with op.batch_alter_table('tools', schema=None, recreate='never') as batch_op:
        batch_op.drop_column('support_email')
