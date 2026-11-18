"""GDPR self-service and retention (PRD F17, TECH_SPEC §9.5, Privacy §9)."""

import hashlib
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import (
    AuditLog,
    EmailCode,
    EmailOutbox,
    InteractionEvent,
    PasswordResetToken,
    Report,
    SearchQuery,
    Star,
    Suggestion,
    Tool,
    ToolRevision,
    User,
    UserSession,
)
from app.models.enums import ReportStatus, ToolStatus, UserStatus
from app.services import audit, certifications, email, media, sessions
from app.services import tools as tool_service

PURGE_AFTER = timedelta(days=30)
EVENTS_RETENTION = timedelta(days=180)
MAGIC_LINK_RETENTION = timedelta(days=3)  # reset links: 48 h validity, deleted after 3 days
OUTBOX_RETENTION = timedelta(days=30)
SUGGESTION_RETENTION = timedelta(days=365)
EMAIL_CODE_RETENTION = timedelta(days=1)  # codes: 15 min validity; pending registrations deleted after 24 h
REPORT_RETENTION = timedelta(days=730)
AUDIT_RETENTION = timedelta(days=3 * 365)


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def export(db: Session, user: User) -> dict[str, Any]:
    """Everything we hold about the user, as JSON (Art. 15/20)."""
    tools = db.scalars(select(Tool).where(Tool.owner_id == user.id)).unique().all()
    revisions = db.scalars(select(ToolRevision).where(ToolRevision.submitted_by == user.id)).unique().all()
    stars = db.execute(select(Star.tool_id, Star.created_at).where(Star.user_id == user.id)).all()
    reports = db.scalars(select(Report).where(Report.reporter_id == user.id)).unique().all()
    sent = db.scalars(select(Suggestion).where(Suggestion.sender_id == user.id)).unique().all()
    received = db.scalars(select(Suggestion).where(Suggestion.recipient_id == user.id)).unique().all()
    return {
        "exported_at": utcnow().isoformat(),
        "profile": {
            "email": user.email,
            "display_name": user.display_name,
            "handle": user.handle,
            "profession": user.profession.value if user.profession else None,
            "specialty": user.specialty.slug if user.specialty else None,
            "workplace": user.workplace,
            "github_username": user.github_username,
            "locale": user.locale.value,
            "role": user.role.value,
            "status": user.status.value,
            "terms_version": user.terms_version,
            "terms_accepted_at": _iso(user.terms_accepted_at),
            "created_at": _iso(user.created_at),
            "last_login_at": _iso(user.last_login_at),
        },
        "tools": [
            {
                **{k: _iso(v) for k, v in tool_service.snapshot(t).items()},
                "slug": t.slug,
                "status": t.status.value,
                "created_at": _iso(t.created_at),
                "published_at": _iso(t.published_at),
                "certification_claims": [
                    {
                        "code": c.certification.code,
                        "state": c.state.value,
                        "details": c.details,
                        "review_reason": c.review_reason,
                    }
                    for c in t.claims
                ],
                "screenshots": [
                    {"file": m.file_name, "alt_pt": m.alt_text_pt, "alt_en": m.alt_text_en} for m in t.media
                ],
            }
            for t in tools
        ],
        "revisions": [
            {
                "tool_id": r.tool_id,
                "status": r.status.value,
                "data": r.data,
                "created_at": _iso(r.created_at),
                "review_reason": r.review_reason,
            }
            for r in revisions
        ],
        "stars": [{"tool_id": tid, "created_at": _iso(at)} for tid, at in stars],
        "reports_filed": [
            {
                "tool_id": r.tool_id,
                "reason": r.reason.value,
                "details": r.details,
                "status": r.status.value,
                "created_at": _iso(r.created_at),
            }
            for r in reports
        ],
        "suggestions_sent": [
            {
                "tool_id": s.tool_id,
                "kind": s.kind.value,
                "message": s.message,
                "email_shared": s.allow_reply,
                "created_at": _iso(s.created_at),
            }
            for s in sent
        ],
        "suggestions_received": [
            {
                "tool_id": s.tool_id,
                "kind": s.kind.value,
                "message": s.message,
                "created_at": _iso(s.created_at),
            }
            for s in received
        ],
    }


def pseudonym(user_id: int) -> str:
    return "deleted-user-" + hashlib.sha256(f"gitmgf:{user_id}".encode()).hexdigest()[:12]


def delete_account(db: Session, user: User, actor: User) -> None:
    """Tools unpublished now and purged after 30 days with the account; stars removed; reports anonymised."""
    lang = user.locale.value
    address = user.email
    for tool in (
        db.scalars(select(Tool).where(Tool.owner_id == user.id, Tool.status != ToolStatus.deleted))
        .unique()
        .all()
    ):
        tool_service.transition(db, tool, "delete", actor if actor.id != user.id else user)
    starred = db.scalars(select(Star.tool_id).where(Star.user_id == user.id)).all()
    db.execute(delete(Star).where(Star.user_id == user.id))
    for tool_id in starred:
        starred_tool = db.get(Tool, tool_id)
        if starred_tool is not None:
            starred_tool.stars_count = max(
                0, len(db.scalars(select(Star.user_id).where(Star.tool_id == tool_id)).all())
            )
    db.execute(
        update(Report).where(Report.reporter_id == user.id).values(reporter_id=None, reporter_email=None)
    )
    sessions.destroy_all(db, user.id)
    user.password_hash = None
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.execute(delete(EmailCode).where(EmailCode.email == user.email))
    db.execute(
        delete(Suggestion).where((Suggestion.sender_id == user.id) | (Suggestion.recipient_id == user.id))
    )
    marker = pseudonym(user.id)
    for entry in db.scalars(
        select(AuditLog).where(
            (AuditLog.actor_id == user.id)
            | ((AuditLog.target_type == "user") & (AuditLog.target_id == user.id))
        )
    ):
        details = dict(entry.details or {})
        if entry.actor_id == user.id:
            details["actor"] = marker
            entry.actor_id = None
        if entry.target_type == "user" and entry.target_id == user.id:
            details["target"] = marker
            entry.target_id = None
        entry.details = details
    email.enqueue(db, address, "account_deleted", {}, lang)
    user.status = UserStatus.deleted
    user.deleted_at = utcnow()
    user.email = f"{marker}@deleted.invalid"
    user.display_name = ""
    user.handle = None
    user.workplace = None
    user.github_username = None
    audit.log(
        db,
        actor.id if actor.id != user.id else None,
        "user.delete",
        "user",
        None,
        target=marker,
        by_self=actor.id == user.id,
    )


def purge(db: Session) -> dict[str, int]:
    """Daily retention job (TECH_SPEC §9.5). Keep in sync with Privacy §9."""
    now = utcnow()
    counts: dict[str, int] = {}

    def run(name: str, stmt: Any) -> None:
        result = db.execute(stmt)
        counts[name] = int(getattr(result, "rowcount", 0) or 0)

    run(
        "interaction_events",
        delete(InteractionEvent).where(InteractionEvent.created_at < now - EVENTS_RETENTION),
    )
    run("search_queries", delete(SearchQuery).where(SearchQuery.created_at < now - EVENTS_RETENTION))
    run(
        "password_reset_tokens",
        delete(PasswordResetToken).where(PasswordResetToken.created_at < now - MAGIC_LINK_RETENTION),
    )
    run("suggestions", delete(Suggestion).where(Suggestion.created_at < now - SUGGESTION_RETENTION))
    run("email_codes", delete(EmailCode).where(EmailCode.created_at < now - EMAIL_CODE_RETENTION))
    run("sessions", delete(UserSession).where(UserSession.expires_at < now))
    run(
        "email_outbox",
        delete(EmailOutbox).where(
            EmailOutbox.created_at < now - OUTBOX_RETENTION,
        ),
    )
    run(
        "reports",
        delete(Report).where(Report.status != ReportStatus.open, Report.resolved_at < now - REPORT_RETENTION),
    )
    run("audit_log", delete(AuditLog).where(AuditLog.created_at < now - AUDIT_RETENTION))
    counts["tools"] = tool_service.purge_deleted(db)
    users = (
        db.scalars(select(User).where(User.status == UserStatus.deleted, User.deleted_at < now - PURGE_AFTER))
        .unique()
        .all()
    )
    for user in users:
        for tool in db.scalars(select(Tool).where(Tool.owner_id == user.id)).unique().all():
            media.delete_tool_dir(tool.id)
            from app.services import search

            search.remove_tool(db, tool.id)
        db.delete(user)
    counts["users"] = len(users)
    return counts


def cert_names(db: Session, lang: str) -> dict[str, str]:
    return {c.code: c.name(lang) for c in certifications.catalogue(db, active_only=False)}
