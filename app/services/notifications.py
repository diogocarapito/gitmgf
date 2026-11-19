"""Notifications page and header badge (D36): moderation decisions on the user's tools, suggestions
received (D32) and, for moderators, the review queue as live to-dos."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Notification, Report, Suggestion, Tool, ToolRevision, User
from app.models.enums import NotificationKind, ReportStatus, RevisionStatus, ToolStatus
from app.services import suggestions

PAGE = 30


@dataclass
class FeedItem:
    notification: Notification | None = None
    suggestion: Suggestion | None = None
    unread: bool = False  # captured before the page marks everything read

    @property
    def created_at(self) -> datetime:
        row = self.notification or self.suggestion
        assert row is not None
        return row.created_at


def notify(
    db: Session, user: User, kind: NotificationKind, tool: Tool, message: str | None = None
) -> Notification | None:
    """Records a moderation decision for the tool's owner (the email is sent separately)."""
    if not user.is_active or user.deleted_at is not None:
        return None
    row = Notification(
        user_id=user.id,
        tool_id=tool.id,
        tool_title=tool.title_pt[:200],
        kind=kind,
        message=(message or "").strip() or None,
    )
    db.add(row)
    return row


def todos(db: Session, user: User) -> dict[str, int]:
    """Open review work a moderator can act on: their own tools are left out (someone else moderates them)."""
    if not user.is_moderator:
        return {}
    not_own = Tool.owner_id != user.id
    return {
        "new": int(
            db.scalar(
                select(func.count()).select_from(Tool).where(Tool.status == ToolStatus.pending, not_own)
            )
            or 0
        ),
        "edits": int(
            db.scalar(
                select(func.count())
                .select_from(ToolRevision)
                .join(Tool, Tool.id == ToolRevision.tool_id)
                .where(ToolRevision.status == RevisionStatus.pending, not_own)
            )
            or 0
        ),
        "reports": int(
            db.scalar(
                select(func.count())
                .select_from(Report)
                .join(Tool, Tool.id == Report.tool_id)
                .where(Report.status == ReportStatus.open, not_own)
            )
            or 0
        ),
    }


def unread_count(db: Session, user: User) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )


def badge_count(db: Session, user: User) -> int:
    """Header badge: unread decisions and suggestions plus, for moderators, the open to-dos."""
    return unread_count(db, user) + suggestions.unread_count(db, user) + sum(todos(db, user).values())


def feed(db: Session, user: User, page: int = 1) -> tuple[list[FeedItem], bool]:
    """Decisions and suggestions merged newest first; returns (items on this page, has_next)."""
    page = max(page, 1)
    upto = page * PAGE + 1
    rows = [
        FeedItem(notification=n, unread=n.read_at is None)
        for n in db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(upto)
        )
        .unique()
        .all()
    ] + [
        FeedItem(suggestion=s, unread=s.read_at is None)
        for s in db.scalars(
            select(Suggestion)
            .where(Suggestion.recipient_id == user.id)
            .order_by(Suggestion.created_at.desc(), Suggestion.id.desc())
            .limit(upto)
        )
        .unique()
        .all()
    ]
    rows.sort(key=lambda item: item.created_at, reverse=True)
    start = (page - 1) * PAGE
    return rows[start : start + PAGE], len(rows) > start + PAGE


def mark_all_read(db: Session, user: User) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    suggestions.mark_all_read(db, user)


def remove(db: Session, user: User, notification_id: int) -> bool:
    """Only the recipient can delete one of their notifications."""
    result = db.execute(
        delete(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    return bool(getattr(result, "rowcount", 0))
