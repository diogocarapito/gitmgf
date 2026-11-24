"""Public profile pages and profile photos (D33)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PUBLIC_STATUSES, Tool, User
from app.services import audit, media, permissions


def by_handle(db: Session, handle: str) -> User | None:
    return db.scalar(select(User).where(User.handle == handle.lower()))


def public_tools(db: Session, user: User) -> list[Tool]:
    return list(
        db.scalars(
            select(Tool)
            .where(Tool.owner_id == user.id, Tool.status.in_(PUBLIC_STATUSES) | Tool.unvalidated_clause())
            .order_by(Tool.published_at.desc().nulls_first(), Tool.submitted_at.desc())
        )
        .unique()
        .all()
    )


def set_avatar(db: Session, user: User, data: bytes) -> None:
    """Raises media.MediaError for unusable files. The previous photo is deleted."""
    new_name = media.process_avatar(data, user.id)
    old_name = user.avatar_name
    user.avatar_name = new_name
    media.delete_avatar(user.id, old_name)


def remove_avatar(db: Session, user: User, actor: User, reason: str | None = None) -> None:
    old_name = user.avatar_name
    user.avatar_name = None
    media.delete_avatar(user.id, old_name)
    if actor.id != user.id and permissions.can_admin(actor):
        audit.log(db, actor.id, "user.avatar_remove", "user", user.id, reason=reason)
