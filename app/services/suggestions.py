"""Suggestions and feature requests to tool authors: emailed and listed in their notifications (D32)."""

from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.i18n import N_, labels, lang_path, t
from app.models import Suggestion, Tool, User
from app.models.enums import SuggestionKind
from app.services import email, permissions

RETENTION = timedelta(days=365)
NO_NAME = N_("Um utilizador")
PAGE = 30


class SuggestionError(Exception):
    pass


def send(
    db: Session, tool: Tool, sender: User, kind: SuggestionKind, message: str, allow_reply: bool
) -> Suggestion:
    if not permissions.can_suggest(sender, tool):
        raise SuggestionError("not allowed")
    recipient = tool.owner
    suggestion = Suggestion(
        tool_id=tool.id,
        recipient_id=recipient.id,
        sender_id=sender.id,
        kind=kind,
        message=message.strip(),
        allow_reply=allow_reply,
    )
    db.add(suggestion)
    db.flush()
    if recipient.is_active and recipient.deleted_at is None:
        lang = recipient.locale.value
        email.enqueue(
            db,
            recipient.email,
            "suggestion_received",
            {
                "name": recipient.display_name,
                "title": tool.title_en if lang == "en" and tool.title_en else tool.title_pt,
                "kind": t(lang, labels.SUGGESTION_KIND[kind.value]),
                "message": suggestion.message,
                "sender": sender.display_name or t(lang, NO_NAME),
                "allow_reply": allow_reply,
                "link": get_settings().base_url.rstrip("/") + lang_path(lang, "/me/notifications"),
            },
            lang,
            reply_to=sender.email if allow_reply else None,
        )
    return suggestion


def unread_count(db: Session, user: User) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Suggestion)
            .where(Suggestion.recipient_id == user.id, Suggestion.read_at.is_(None))
        )
        or 0
    )


def inbox(db: Session, user: User, page: int = 1) -> list[Suggestion]:
    return list(
        db.scalars(
            select(Suggestion)
            .where(Suggestion.recipient_id == user.id)
            .order_by(Suggestion.created_at.desc(), Suggestion.id.desc())
            .offset((max(page, 1) - 1) * PAGE)
            .limit(PAGE + 1)
        )
        .unique()
        .all()
    )


def mark_all_read(db: Session, user: User) -> None:
    db.execute(
        update(Suggestion)
        .where(Suggestion.recipient_id == user.id, Suggestion.read_at.is_(None))
        .values(read_at=utcnow())
    )


def remove(db: Session, user: User, suggestion_id: int) -> bool:
    """Only the recipient can delete a suggestion from their notifications."""
    result = db.execute(
        delete(Suggestion).where(Suggestion.id == suggestion_id, Suggestion.recipient_id == user.id)
    )
    return bool(getattr(result, "rowcount", 0))
