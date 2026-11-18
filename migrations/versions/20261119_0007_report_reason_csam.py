"""report reason "csam" (anonymous reports allowed)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19 18:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_REASONS = ('broken_link', 'dangerous_content', 'inappropriate', 'security_privacy', 'incorrect_certification', 'spam', 'copyright', 'illegal', 'other')
NEW_REASONS = ('broken_link', 'dangerous_content', 'inappropriate', 'csam', 'security_privacy', 'incorrect_certification', 'spam', 'copyright', 'illegal', 'other')


def _reason(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name='report_reason', native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    with op.batch_alter_table('reports', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('reason', existing_type=_reason(OLD_REASONS), type_=_reason(NEW_REASONS), existing_nullable=False)


def downgrade() -> None:
    op.execute("UPDATE reports SET reason = 'illegal' WHERE reason = 'csam'")
    with op.batch_alter_table('reports', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('reason', existing_type=_reason(NEW_REASONS), type_=_reason(OLD_REASONS), existing_nullable=False)
