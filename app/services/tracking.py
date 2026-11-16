"""Cookie-less usage signals (TECH_SPEC §9.1–9.2).

visitor_hash = sha256(daily_salt + ip + user_agent)[:32]. The salt is replaced every day and the old one
discarded, so hashes cannot be linked across days or reversed. Raw IPs are never stored.
"""

import hashlib
import re
import secrets

from fastapi import Request
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.db import today, utcnow
from app.models import InteractionEvent, Tool, User
from app.models.enums import EventKind, LinkKind
from app.services import settings_store

BOT_RE = re.compile(
    r"(bot|crawl|spider|slurp|preview|facebookexternalhit|curl|wget|python-requests|httpx|headless|monitor)",
    re.I,
)
SALT_KEY = "tracking.daily_salt"
SALT_DAY_KEY = "tracking.salt_day"


def is_bot(user_agent: str | None) -> bool:
    return not user_agent or bool(BOT_RE.search(user_agent))


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers sets request.client from Caddy's X-Forwarded-For.
    return request.client.host if request.client else "0.0.0.0"  # noqa: S104


def rotate_salt(db: Session) -> None:
    settings_store.set_value(db, SALT_KEY, secrets.token_hex(32), None)
    settings_store.set_value(db, SALT_DAY_KEY, today().isoformat(), None)


def daily_salt(db: Session) -> str:
    if settings_store.get(db, SALT_DAY_KEY) != today().isoformat() or not settings_store.get(db, SALT_KEY):
        settings_store.invalidate()  # another worker may already have rotated
        if settings_store.get(db, SALT_DAY_KEY) != today().isoformat() or not settings_store.get(
            db, SALT_KEY
        ):
            rotate_salt(db)
            db.commit()
    return str(settings_store.get(db, SALT_KEY))


def visitor_hash(db: Session, request: Request) -> str:
    ua = request.headers.get("user-agent", "")[:300]
    raw = f"{daily_salt(db)}|{client_ip(request)}|{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def record(
    db: Session,
    request: Request,
    tool: Tool,
    kind: EventKind,
    user: User | None,
    link_kind: LinkKind | None = None,
    search_id: str | None = None,
    position: int | None = None,
) -> bool:
    """One event per visitor, tool, signal and day. Owners and bots never count."""
    if is_bot(request.headers.get("user-agent")):
        return False
    if user is not None and user.id == tool.owner_id:
        return False
    result = db.execute(
        insert(InteractionEvent)
        .prefix_with("OR IGNORE")
        .values(
            tool_id=tool.id,
            kind=kind.value,
            link_kind=link_kind.value if link_kind else None,
            search_id=search_id,
            position=position,
            visitor_hash=visitor_hash(db, request),
            user_id=user.id if user else None,
            day=today(),
            created_at=utcnow(),
        )
    )
    return bool(getattr(result, "rowcount", 0))
