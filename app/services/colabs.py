"""Colaborações (D41): ideas, projects that need help, and requests for feedback, with a public thread.

Published immediately and reportable. The author edits, marks as resolved, reopens or deletes their post;
moderators hide or restore it with a reason (audited, the author is notified).
"""

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import PUBLIC_COLAB_STATUSES, PUBLIC_STATUSES, Colab, Tool, User
from app.models.enums import ColabKind, ColabStatus
from app.services import audit, notifications, permissions

PAGE = 20
PURGE_AFTER = timedelta(days=30)


class ColabError(Exception):
    pass


@dataclass
class ColabData:
    kind: ColabKind
    title: str
    body: str
    link_url: str | None = None
    tool_id: int | None = None


def own_tools(db: Session, user: User) -> list[Tool]:
    """Tools the author may attach to a post: their own public ones."""
    return list(
        db.scalars(
            select(Tool)
            .where(Tool.owner_id == user.id, Tool.status.in_(PUBLIC_STATUSES))
            .order_by(Tool.title_pt)
        )
        .unique()
        .all()
    )


def _apply(db: Session, colab: Colab, author: User, data: ColabData) -> None:
    if data.tool_id is not None and data.tool_id not in {t.id for t in own_tools(db, author)}:
        raise ColabError("tool")
    colab.kind = data.kind
    colab.title = data.title.strip()
    colab.body = data.body.replace("\r\n", "\n").strip()
    colab.link_url = data.link_url or None
    colab.tool_id = data.tool_id


def create(db: Session, author: User, data: ColabData) -> Colab:
    if not permissions.can_post_colab(author):
        raise ColabError("not allowed")
    colab = Colab(author_id=author.id, status=ColabStatus.open)
    _apply(db, colab, author, data)
    db.add(colab)
    db.flush()
    return colab


def update(db: Session, user: User, colab: Colab, data: ColabData) -> None:
    if not permissions.can_edit_colab(user, colab):
        raise ColabError("not allowed")
    _apply(db, colab, user, data)
    colab.updated_at = utcnow()


def set_resolved(db: Session, user: User, colab: Colab, resolved: bool) -> None:
    if not permissions.can_edit_colab(user, colab):
        raise ColabError("not allowed")
    colab.status = ColabStatus.resolved if resolved else ColabStatus.open
    colab.resolved_at = utcnow() if resolved else None


def delete_own(db: Session, user: User, colab: Colab) -> None:
    """Soft delete: gone from the site at once, purged with its thread after 30 days."""
    if user.id != colab.author_id or colab.status == ColabStatus.deleted:
        raise ColabError("not allowed")
    colab.status = ColabStatus.deleted
    colab.updated_at = utcnow()


def hide(db: Session, moderator: User, colab: Colab, reason: str) -> None:
    if not permissions.can_moderate_colab(moderator, colab) or colab.status not in PUBLIC_COLAB_STATUSES:
        raise ColabError("not allowed")
    colab.status = ColabStatus.hidden
    colab.hidden_reason = reason.strip()
    colab.updated_at = utcnow()
    audit.log(db, moderator.id, "colab.hide", "colab", colab.id, reason=colab.hidden_reason)
    notifications.notify_moderation(db, colab.author, colab=colab, hidden=True, reason=reason)


def unhide(db: Session, moderator: User, colab: Colab) -> None:
    if not permissions.can_moderate_colab(moderator, colab) or colab.status != ColabStatus.hidden:
        raise ColabError("not allowed")
    colab.status = ColabStatus.resolved if colab.resolved_at else ColabStatus.open
    colab.hidden_reason = None
    colab.updated_at = utcnow()
    audit.log(db, moderator.id, "colab.unhide", "colab", colab.id)
    notifications.notify_moderation(db, colab.author, colab=colab, hidden=False)


def listing(
    db: Session, kind: ColabKind | None, status: str, page: int = 1
) -> tuple[list[Colab], bool, dict[str, int]]:
    """Public posts, newest first. `status` is open, resolved or all. Returns (page items, has_next,
    open posts per kind for the filter chips)."""
    statuses = {
        "open": [ColabStatus.open],
        "resolved": [ColabStatus.resolved],
    }.get(status, list(PUBLIC_COLAB_STATUSES))
    query = select(Colab).where(Colab.status.in_(statuses))
    if kind is not None:
        query = query.where(Colab.kind == kind)
    page = max(page, 1)
    rows = list(
        db.scalars(
            query.order_by(Colab.created_at.desc(), Colab.id.desc()).offset((page - 1) * PAGE).limit(PAGE + 1)
        )
        .unique()
        .all()
    )
    counts = {
        str(k): int(n)
        for k, n in db.execute(
            select(Colab.kind, func.count()).where(Colab.status.in_(statuses)).group_by(Colab.kind)
        ).all()
    }
    return rows[:PAGE], len(rows) > PAGE, counts


def by_author(db: Session, user: User) -> list[Colab]:
    return list(
        db.scalars(
            select(Colab)
            .where(Colab.author_id == user.id, Colab.status.in_(PUBLIC_COLAB_STATUSES))
            .order_by(Colab.created_at.desc())
        )
        .unique()
        .all()
    )


def purge_deleted(db: Session) -> int:
    result = db.execute(
        delete(Colab).where(Colab.status == ColabStatus.deleted, Colab.updated_at < utcnow() - PURGE_AFTER)
    )
    return int(getattr(result, "rowcount", 0) or 0)
