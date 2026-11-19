from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import NotificationKind, str_enum
from app.models.tool import Tool


class Notification(Base):
    """A moderation decision on one of the user's tools, shown in their notifications (D36)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tool_id: Mapped[int | None] = mapped_column(ForeignKey("tools.id", ondelete="SET NULL"), index=True)
    tool_title: Mapped[str] = mapped_column(String(200))  # kept if the tool is later purged
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind, "notification_kind"))
    message: Mapped[str | None] = mapped_column(Text)  # the moderator's reason or suggestions
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    read_at: Mapped[datetime | None]

    tool: Mapped[Tool | None] = relationship(lazy="joined")
