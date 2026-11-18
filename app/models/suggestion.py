from datetime import datetime

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import SuggestionKind, str_enum
from app.models.tool import Tool
from app.models.user import User


class Suggestion(Base):
    """A feature request or suggestion sent to a tool's author: emailed and shown in their notifications."""

    __tablename__ = "suggestions"
    __table_args__ = (Index("ix_suggestions_recipient_read", "recipient_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    kind: Mapped[SuggestionKind] = mapped_column(str_enum(SuggestionKind, "suggestion_kind"))
    message: Mapped[str] = mapped_column(Text)
    allow_reply: Mapped[bool] = mapped_column(default=False)  # sender agreed to share their email
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    read_at: Mapped[datetime | None]

    tool: Mapped[Tool] = relationship(lazy="joined")
    sender: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[sender_id])
