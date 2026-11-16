"""Server-side sessions: the cookie holds a random token, the DB stores only its sha256 (TECH_SPEC §6.3)."""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import User, UserSession

SESSION_LIFETIME = timedelta(days=30)
SLIDE_EVERY = timedelta(minutes=5)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(db: Session, user: User, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        UserSession(
            id=hash_token(token),
            user_id=user.id,
            csrf_secret=secrets.token_hex(16),
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_LIFETIME,
            user_agent=(user_agent or "")[:200] or None,
        )
    )
    user.last_login_at = now
    return token


def load(db: Session, token: str) -> UserSession | None:
    row = db.get(UserSession, hash_token(token))
    if row is None:
        return None
    now = utcnow()
    if row.expires_at <= now or not row.user.is_active:
        db.delete(row)
        db.commit()
        return None
    if now - row.last_seen_at >= SLIDE_EVERY:
        row.last_seen_at = now
        row.expires_at = now + SESSION_LIFETIME
        db.commit()
    return row


def destroy(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.id == hash_token(token)))


def destroy_all(db: Session, user_id: int) -> int:
    result = db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    return int(getattr(result, "rowcount", 0) or 0)


def count_for(db: Session, user_id: int) -> int:
    return len(db.scalars(select(UserSession.id).where(UserSession.user_id == user_id)).all())
