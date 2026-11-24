"""Community: colab posts, comments on tools and colabs, and emoji reactions (D41)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import ColabKind, ColabStatus, Reaction, str_enum
from app.models.tool import Tool
from app.models.user import User

PUBLIC_COLAB_STATUSES = (ColabStatus.open, ColabStatus.resolved)


class Colab(Base):
    """A post on /colabs: an idea, a project that needs help, or a request for feedback."""

    __tablename__ = "colabs"
    __table_args__ = (Index("ix_colabs_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[ColabKind] = mapped_column(str_enum(ColabKind, "colab_kind"))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    link_url: Mapped[str | None] = mapped_column(String(500))  # repository, MVP, prototype
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.id", ondelete="SET NULL"), index=True)
    status: Mapped[ColabStatus] = mapped_column(
        str_enum(ColabStatus, "colab_status"), default=ColabStatus.open
    )
    hidden_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None]

    author: Mapped[User] = relationship(lazy="joined")
    tool: Mapped[Tool | None] = relationship(lazy="joined")

    @property
    def is_public(self) -> bool:
        return self.status in PUBLIC_COLAB_STATUSES


class Comment(Base):
    """A comment on a tool page or a colab post. One level of replies (`parent_id` is always top-level)."""

    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint("(tool_id IS NULL) != (colab_id IS NULL)", name="one_target"),
        Index("ix_comments_tool_created", "tool_id", "created_at"),
        Index("ix_comments_colab_created", "colab_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"))
    colab_id: Mapped[int | None] = mapped_column(ForeignKey("colabs.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    edited_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]  # tombstone: kept only while it has replies
    hidden_at: Mapped[datetime | None]
    hidden_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    hidden_reason: Mapped[str | None] = mapped_column(Text)

    author: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[author_id])
    tool: Mapped[Tool | None] = relationship(lazy="joined")
    colab: Mapped[Colab | None] = relationship(lazy="joined")

    @property
    def is_visible(self) -> bool:
        return self.deleted_at is None and self.hidden_at is None


class CommentReaction(Base):
    __tablename__ = "comment_reactions"

    comment_id: Mapped[int] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    emoji: Mapped[Reaction] = mapped_column(str_enum(Reaction, "reaction"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
