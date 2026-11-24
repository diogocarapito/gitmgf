from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import NotificationKind, str_enum
from app.models.tool import Tool

if TYPE_CHECKING:
    from app.models.community import Colab, Comment
    from app.models.user import User


class Notification(Base):
    """A moderation decision on one of the user's tools (D36), or community activity (D41): a comment on
    their tool or colab, a reply, a mention, or a moderation decision on their comment or colab."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.id", ondelete="SET NULL"), index=True)
    tool_title: Mapped[str] = mapped_column(String(200))  # subject title (tool or colab), kept if purged
    colab_id: Mapped[int | None] = mapped_column(ForeignKey("colabs.id", ondelete="SET NULL"), index=True)
    comment_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id", ondelete="SET NULL"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind, "notification_kind"))
    message: Mapped[str | None] = mapped_column(Text)  # the moderator's reason or suggestions
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    read_at: Mapped[datetime | None]

    tool: Mapped[Tool | None] = relationship(lazy="joined")
    colab: Mapped["Colab | None"] = relationship(lazy="joined")
    comment: Mapped["Comment | None"] = relationship(lazy="joined")
    actor: Mapped["User | None"] = relationship(lazy="joined", foreign_keys=[actor_id])
