"""colabs, comments and reactions (D41); reports and notifications on them; comment email opt-out

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-23 23:52:00.024143
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = ('tool_approved', 'tool_rejected', 'tool_changes_requested', 'tool_hidden', 'tool_unhidden', 'revision_approved', 'revision_rejected')
NEW_KINDS = OLD_KINDS + ('comment_new', 'comment_reply', 'comment_mention', 'comment_hidden', 'comment_unhidden', 'colab_hidden', 'colab_unhidden')


def _kind(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name='notification_kind', native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    op.create_table('colabs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('idea', 'help', 'feedback', name='colab_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('link_url', sa.String(length=500), nullable=True),
    sa.Column('tool_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('open', 'resolved', 'hidden', 'deleted', name='colab_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('hidden_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_colabs_author_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tool_id'], ['tools.id'], name=op.f('fk_colabs_tool_id_tools'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_colabs'))
    )
    with op.batch_alter_table('colabs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_colabs_author_id'), ['author_id'], unique=False)
        batch_op.create_index('ix_colabs_status_created', ['status', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_colabs_tool_id'), ['tool_id'], unique=False)

    op.create_table('comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tool_id', sa.Integer(), nullable=True),
    sa.Column('colab_id', sa.Integer(), nullable=True),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('edited_at', sa.DateTime(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('hidden_at', sa.DateTime(), nullable=True),
    sa.Column('hidden_by', sa.Integer(), nullable=True),
    sa.Column('hidden_reason', sa.Text(), nullable=True),
    sa.CheckConstraint('(tool_id IS NULL) != (colab_id IS NULL)', name=op.f('ck_comments_one_target')),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_comments_author_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['colab_id'], ['colabs.id'], name=op.f('fk_comments_colab_id_colabs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['hidden_by'], ['users.id'], name=op.f('fk_comments_hidden_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], name=op.f('fk_comments_parent_id_comments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tool_id'], ['tools.id'], name=op.f('fk_comments_tool_id_tools'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comments'))
    )
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_comments_author_id'), ['author_id'], unique=False)
        batch_op.create_index('ix_comments_colab_created', ['colab_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_comments_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index('ix_comments_tool_created', ['tool_id', 'created_at'], unique=False)

    op.create_table('comment_reactions',
    sa.Column('comment_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('emoji', sa.Enum('thumbs_up', 'heart', 'tada', 'pray', 'bulb', 'eyes', name='reaction', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], name=op.f('fk_comment_reactions_comment_id_comments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_comment_reactions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('comment_id', 'user_id', 'emoji', name=op.f('pk_comment_reactions'))
    )
    with op.batch_alter_table('notifications', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('kind', existing_type=_kind(OLD_KINDS), type_=_kind(NEW_KINDS), existing_nullable=False)
        batch_op.add_column(sa.Column('colab_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('comment_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('actor_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_notifications_colab_id'), ['colab_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_notifications_actor_id_users'), 'users', ['actor_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(batch_op.f('fk_notifications_colab_id_colabs'), 'colabs', ['colab_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(batch_op.f('fk_notifications_comment_id_comments'), 'comments', ['comment_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('reports', schema=None, recreate='always') as batch_op:
        batch_op.add_column(sa.Column('comment_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('colab_id', sa.Integer(), nullable=True))
        batch_op.alter_column('tool_id',
               existing_type=sa.INTEGER(),
               nullable=True)
        batch_op.create_index(batch_op.f('ix_reports_colab_id'), ['colab_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reports_comment_id'), ['comment_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_reports_comment_id_comments'), 'comments', ['comment_id'], ['id'], ondelete='CASCADE')
        batch_op.create_foreign_key(batch_op.f('fk_reports_colab_id_colabs'), 'colabs', ['colab_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_on_comments', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('publish_blocked_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('publish_blocked_reason', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('social_blocked_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('social_blocked_reason', sa.String(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('social_blocked_reason')
        batch_op.drop_column('social_blocked_at')
        batch_op.drop_column('publish_blocked_reason')
        batch_op.drop_column('publish_blocked_at')
        batch_op.drop_column('email_on_comments')

    op.execute("DELETE FROM reports WHERE tool_id IS NULL")
    with op.batch_alter_table('reports', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_reports_colab_id_colabs'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_reports_comment_id_comments'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_reports_comment_id'))
        batch_op.drop_index(batch_op.f('ix_reports_colab_id'))
        batch_op.alter_column('tool_id',
               existing_type=sa.INTEGER(),
               nullable=False)
        batch_op.drop_column('colab_id')
        batch_op.drop_column('comment_id')

    op.execute("DELETE FROM notifications WHERE kind NOT IN ('" + "', '".join(OLD_KINDS) + "')")
    with op.batch_alter_table('notifications', schema=None, recreate='always') as batch_op:
        batch_op.alter_column('kind', existing_type=_kind(NEW_KINDS), type_=_kind(OLD_KINDS), existing_nullable=False)
        batch_op.drop_constraint(batch_op.f('fk_notifications_comment_id_comments'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_notifications_colab_id_colabs'), type_='foreignkey')
        batch_op.drop_constraint(batch_op.f('fk_notifications_actor_id_users'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_notifications_colab_id'))
        batch_op.drop_column('actor_id')
        batch_op.drop_column('comment_id')
        batch_op.drop_column('colab_id')

    op.drop_table('comment_reactions')
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index('ix_comments_tool_created')
        batch_op.drop_index(batch_op.f('ix_comments_parent_id'))
        batch_op.drop_index('ix_comments_colab_created')
        batch_op.drop_index(batch_op.f('ix_comments_author_id'))

    op.drop_table('comments')
    with op.batch_alter_table('colabs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_colabs_tool_id'))
        batch_op.drop_index('ix_colabs_status_created')
        batch_op.drop_index(batch_op.f('ix_colabs_author_id'))

    op.drop_table('colabs')
