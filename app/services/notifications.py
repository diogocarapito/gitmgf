"""Notifications page and header badge (D36): moderation decisions on the user's tools, suggestions
received (D32) and, for moderators, the review queue as live to-dos."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.i18n import lang_path
from app.models import Colab, Comment, Notification, Report, Suggestion, Tool, ToolRevision, User
from app.models.enums import NotificationKind, ReportStatus, RevisionStatus, ToolStatus
from app.services import email, suggestions

SNIPPET = 300

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


def _snippet(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= SNIPPET else text[: SNIPPET - 1].rstrip() + "…"


def _subject(comment: Comment | None, colab: Colab | None) -> tuple[Tool | None, Colab | None, str]:
    tool = comment.tool if comment is not None else None
    colab = colab or (comment.colab if comment is not None else None)
    title = tool.title_pt if tool is not None else (colab.title if colab is not None else "")
    return tool, colab, title[:200]


def notify_comment(
    db: Session, user: User, kind: NotificationKind, comment: Comment, actor: User
) -> Notification:
    """A comment on the user's tool or colab, a reply to them or an @mention (D41): in-app, plus an email
    unless they opted out in Definições."""
    tool, colab, title = _subject(comment, None)
    row = Notification(
        user_id=user.id,
        tool_id=tool.id if tool else None,
        colab_id=colab.id if colab else None,
        comment_id=comment.id,
        actor_id=actor.id,
        tool_title=title,
        kind=kind,
        message=_snippet(comment.body),
    )
    db.add(row)
    if user.email_on_comments:
        from app.services.comments import link

        lang = user.locale.value
        email.enqueue(
            db,
            user.email,
            "comment_notice",
            {
                "name": user.display_name,
                "actor": actor.display_name,
                "title": title,
                "kind": kind.value,
                "excerpt": row.message or "",
                "link": link(comment, lang),
                "settings_link": get_settings().base_url.rstrip("/") + lang_path(lang, "/me/settings"),
            },
            lang,
        )
    return row


def notify_moderation(
    db: Session,
    user: User,
    comment: Comment | None = None,
    colab: Colab | None = None,
    hidden: bool = True,
    reason: str | None = None,
) -> Notification | None:
    """A moderator hid or restored the user's comment or colab post: in-app and by email, with the reason
    (statement of reasons, DSA Art. 17)."""
    if not user.is_active or user.deleted_at is not None:
        return None
    tool, colab, title = _subject(comment, colab)
    if comment is not None:
        kind = NotificationKind.comment_hidden if hidden else NotificationKind.comment_unhidden
    else:
        kind = NotificationKind.colab_hidden if hidden else NotificationKind.colab_unhidden
    row = Notification(
        user_id=user.id,
        tool_id=tool.id if tool else None,
        colab_id=colab.id if colab else None,
        comment_id=comment.id if comment else None,
        tool_title=title,
        kind=kind,
        message=(reason or "").strip() or None,
    )
    db.add(row)
    email.enqueue(
        db,
        user.email,
        "content_moderated",
        {
            "title": title,
            "is_comment": comment is not None,
            "hidden": hidden,
            "reason": row.message or "",
            "excerpt": _snippet(comment.body) if comment is not None else "",
        },
        user.locale.value,
    )
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
                .outerjoin(Tool, Tool.id == Report.tool_id)
                .where(Report.status == ReportStatus.open, (Report.tool_id.is_(None)) | not_own)
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
