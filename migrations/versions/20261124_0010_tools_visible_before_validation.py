"""tools visible before validation (D43): changes_requested_at, rejected_at

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-24 00:19:57.611505
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('tools', schema=None) as batch_op:
        batch_op.add_column(sa.Column('changes_requested_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('rejected_at', sa.DateTime(), nullable=True))
    # Tools rejected before this change must not become visible on resubmission.
    op.execute("UPDATE tools SET rejected_at = updated_at WHERE status = 'rejected'")



def downgrade() -> None:
    with op.batch_alter_table('tools', schema=None) as batch_op:
        batch_op.drop_column('rejected_at')
        batch_op.drop_column('changes_requested_at')

