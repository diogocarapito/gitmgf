"""Scheduled jobs (TECH_SPEC §18). Each one opens its own session and is also exposed as a CLI command."""

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_engine, today, utcnow
from app.i18n import format_short_date
from app.models import AuditLog, Report, Tool, ToolCertification, ToolRevision
from app.models.enums import ClaimState, ReportStatus, RevisionStatus, ToolStatus
from app.services import audit, email, gdpr, github, scoring, tracking
from app.services import reports as report_service

log = logging.getLogger("gitmgf.jobs")


def _with_session(fn: Callable[[Session], Any]) -> Any:
    get_engine()
    with SessionLocal() as db:
        result = fn(db)
        db.commit()
        return result


def send_outbox() -> int:
    return email.deliver_queued()


def recompute_scores() -> int:
    return int(_with_session(scoring.recompute))


def rotate_salt() -> None:
    _with_session(tracking.rotate_salt)


def sync_github(tool_id: int | None = None) -> dict[str, int]:
    get_engine()
    with SessionLocal() as db:
        return github.sync_all(db, tool_id=tool_id)


def prune() -> dict[str, int]:
    return dict(_with_session(gdpr.purge))


def cert_expiry() -> dict[str, int]:
    """T-30 warning and expiry notice to authors; expiries are audit-logged (PRD F20)."""

    def run(db: Session) -> dict[str, int]:
        now_day = today()
        sent = {"expiring": 0, "expired": 0}
        claims = db.scalars(
            select(ToolCertification)
            .join(Tool, Tool.id == ToolCertification.tool_id)
            .where(
                ToolCertification.state == ClaimState.approved,
                ToolCertification.valid_until.is_not(None),
                Tool.status.in_([ToolStatus.published, ToolStatus.archived, ToolStatus.hidden]),
            )
        ).all()
        for claim in claims:
            assert claim.valid_until is not None
            tool, owner = claim.tool, claim.tool.owner
            lang = owner.locale.value
            ctx = {
                "title": tool.title_pt,
                "cert": claim.certification.name(lang),
                "date": format_short_date(claim.valid_until, lang),
                "tool_id": tool.id,
            }
            if (
                now_day <= claim.valid_until <= now_day + timedelta(days=30)
                and claim.expiry_notified_at is None
            ):
                email.enqueue(db, owner.email, "cert_expiring", ctx, lang)
                claim.expiry_notified_at = utcnow()
                sent["expiring"] += 1
            elif claim.valid_until < now_day:
                already = db.scalar(
                    select(AuditLog.id).where(
                        AuditLog.action == "cert.expired",
                        AuditLog.target_type == "claim",
                        AuditLog.target_id == claim.id,
                    )
                )
                if already is None:
                    email.enqueue(db, owner.email, "cert_expired", ctx, lang)
                    audit.log(
                        db,
                        None,
                        "cert.expired",
                        "claim",
                        claim.id,
                        tool_id=tool.id,
                        code=claim.certification.code,
                        valid_until=claim.valid_until.isoformat(),
                    )
                    sent["expired"] += 1
        return sent

    result = _with_session(run)
    email.deliver_queued()
    return dict(result)


def mod_digest() -> int:
    """Daily 08:00 digest to moderators when the queue is not empty."""

    def run(db: Session) -> int:
        new = db.scalar(select(func.count()).select_from(Tool).where(Tool.status == ToolStatus.pending)) or 0
        edits = (
            db.scalar(
                select(func.count())
                .select_from(ToolRevision)
                .where(ToolRevision.status == RevisionStatus.pending)
            )
            or 0
        )
        reports = (
            db.scalar(select(func.count()).select_from(Report).where(Report.status == ReportStatus.open)) or 0
        )
        total = int(new) + int(edits) + int(reports)
        if not total:
            return 0
        oldest = db.scalar(select(func.min(Tool.submitted_at)).where(Tool.status == ToolStatus.pending))
        mods = report_service.moderators(db)
        for mod in mods:
            from app.i18n import format_relative

            email.enqueue(
                db,
                mod.email,
                "mod_digest",
                {
                    "total": total,
                    "new": new,
                    "edits": edits,
                    "reports": reports,
                    "oldest": format_relative(oldest, mod.locale.value) if oldest else "",
                },
                mod.locale.value,
            )
        return len(mods)

    count = int(_with_session(run))
    email.deliver_queued()
    return count


def heartbeat() -> None:
    url = get_settings().healthcheck_ping_url
    if not url:
        return
    try:
        httpx.get(url, timeout=10)
    except httpx.HTTPError as exc:
        log.warning("heartbeat failed: %s", type(exc).__name__)
