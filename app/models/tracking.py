from datetime import date, datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow
from app.models.enums import EventKind, LinkKind, str_enum


class InteractionEvent(Base):
    __tablename__ = "interaction_events"
    __table_args__ = (
        # One event per visitor, tool, signal and day: INSERT OR IGNORE gives the dedupe.
        UniqueConstraint("tool_id", "kind", "visitor_hash", "day"),
        Index("ix_interaction_events_tool_day", "tool_id", "day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"))
    kind: Mapped[EventKind] = mapped_column(str_enum(EventKind, "event_kind"))
    link_kind: Mapped[LinkKind | None] = mapped_column(str_enum(LinkKind, "link_kind"))
    search_id: Mapped[str | None] = mapped_column(String(26))
    position: Mapped[int | None]
    visitor_hash: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    day: Mapped[date] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ToolDailyStat(Base):
    __tablename__ = "tool_daily_stats"

    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    search_clicks: Mapped[int] = mapped_column(default=0)
    outbound_clicks: Mapped[int] = mapped_column(default=0)
    views: Mapped[int] = mapped_column(default=0)


class SearchQuery(Base):
    __tablename__ = "search_queries"
    __table_args__ = (
        Index("ix_search_queries_created", "created_at"),
        Index("ix_search_queries_results_created", "results_count", "created_at"),
        Index("ix_search_queries_visitor", "visitor_hash", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)  # ULID
    q: Mapped[str] = mapped_column(String(200), default="")
    locale: Mapped[str] = mapped_column(String(2))
    filters: Mapped[dict[str, Any]] = mapped_column(default=dict)
    sort: Mapped[str] = mapped_column(String(20))
    results_count: Mapped[int] = mapped_column(default=0)
    visitor_hash: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
