"""Reports: DSA notice-and-action (PRD F11, Terms §9)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.i18n import labels, t
from app.models import Colab, Comment, Report, Tool, User
from app.models.enums import ReportReason, ReportStatus, Role, ToolStatus, UserStatus
from app.services import audit, email, settings_store
from app.services import tools as tool_service

AUTO_HIDE_REASONS = (
    ReportReason.dangerous_content,
    ReportReason.inappropriate,
    ReportReason.security_privacy,
)


def moderators(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User).where(User.role.in_([Role.moderator, Role.admin]), User.status == UserStatus.active)
        ).all()
    )


# Reasons offered when the subject is a comment or a colab post (no links or certifications to check).
COMMUNITY_REASONS = (
    ReportReason.inappropriate,
    ReportReason.dangerous_content,
    ReportReason.security_privacy,
    ReportReason.csam,
    ReportReason.copyright,
    ReportReason.illegal,
    ReportReason.spam,
    ReportReason.other,
)


def create(
    db: Session,
    reason: ReportReason,
    details: str,
    reporter: User | None,
    reporter_email: str | None,
    lang: str,
    visitor_hash: str | None,
    tool: Tool | None = None,
    comment: Comment | None = None,
    colab: Colab | None = None,
) -> Report:
    """A report on exactly one subject: a tool, a comment (D41) or a colab post (D41)."""
    if sum(x is not None for x in (tool, comment, colab)) != 1:
        raise ValueError("one subject")
    report = Report(
        tool_id=tool.id if tool else None,
        comment_id=comment.id if comment else None,
        colab_id=colab.id if colab else None,
        reporter_id=reporter.id if reporter else None,
        reporter_email=None if reporter else (reporter_email or None),
        reason=reason,
        details=details.strip(),
        locale=lang,
        visitor_hash=visitor_hash,
    )
    db.add(report)
    db.flush()
    db.refresh(report)
    audit.log(
        db,
        reporter.id if reporter else None,
        "report.create",
        "report",
        report.id,
        tool_id=report.tool_id,
        comment_id=report.comment_id,
        colab_id=report.colab_id,
        reason=reason.value,
    )
    to = reporter.email if reporter else reporter_email
    if to:
        email.enqueue(
            db,
            to,
            "report_ack",
            {
                "title": report.subject_title,
                "reason": t(lang, labels.REPORT_REASON[reason.value]),
                "report_id": report.id,
            },
            lang,
        )
    if tool is not None and reason in AUTO_HIDE_REASONS:
        maybe_auto_hide(db, tool)
    return report


def open_safety_reports(db: Session, tool_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Report)
            .where(
                Report.tool_id == tool_id,
                Report.status == ReportStatus.open,
                Report.reason.in_(AUTO_HIDE_REASONS),
            )
        )
        or 0
    )


def maybe_auto_hide(db: Session, tool: Tool) -> bool:
    """≥ threshold open dangerous/security reports hide the tool pending review, and moderators are emailed."""
    threshold = settings_store.get_int(db, "reports.auto_hide_threshold")
    count = open_safety_reports(db, tool.id)
    if count < threshold or tool.status not in (ToolStatus.published, ToolStatus.archived):
        return False
    owner_lang = tool.owner.locale.value
    reason = t(
        owner_lang,
        "Ocultada automaticamente após %(n)s denúncias abertas de conteúdo clínico perigoso ou de problemas de segurança, enquanto um moderador analisa o caso.",
        n=count,
    )
    tool_service.transition(db, tool, "auto_hide", None, reason=reason)
    for mod in moderators(db):
        email.enqueue(
            db, mod.email, "mod_auto_hide", {"title": tool.title_pt, "count": count}, mod.locale.value
        )
    return True


def close(db: Session, report: Report, actor: User, resolved: bool, note: str | None) -> None:
    if report.status != ReportStatus.open:
        return
    report.status = ReportStatus.resolved if resolved else ReportStatus.dismissed
    report.handled_by = actor.id
    report.resolution_note = (note or "").strip() or None
    report.resolved_at = utcnow()
    audit.log(
        db,
        actor.id,
        f"report.{report.status.value}",
        "report",
        report.id,
        tool_id=report.tool_id,
        note=report.resolution_note,
    )
    to = report.reporter_email
    if report.reporter_id is not None:
        reporter = db.get(User, report.reporter_id)
        to = reporter.email if reporter else None
    if to:
        email.enqueue(
            db,
            to,
            "report_outcome",
            {
                "title": report.subject_title,
                "report_id": report.id,
                "resolved": resolved,
                "note": report.resolution_note or "",
            },
            report.locale,
        )
