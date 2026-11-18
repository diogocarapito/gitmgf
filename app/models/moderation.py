from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import ReportReason, ReportStatus, str_enum
from app.models.tool import Tool


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id", ondelete="CASCADE"), index=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reporter_email: Mapped[str | None] = mapped_column(String(254))
    reason: Mapped[ReportReason] = mapped_column(str_enum(ReportReason, "report_reason"))
    details: Mapped[str] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        str_enum(ReportStatus, "report_status"), default=ReportStatus.open
    )
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(String(2), default="pt")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None]
    visitor_hash: Mapped[str | None] = mapped_column(String(32))

    tool: Mapped[Tool] = relationship(lazy="joined")


class AuditLog(Base):
    """Append-only: code never updates or deletes rows except the retention job."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(30))
    target_id: Mapped[int | None]
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
