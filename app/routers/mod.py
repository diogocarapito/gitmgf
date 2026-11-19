"""Moderation queue and actions (PRD F10, TECH_SPEC §7.3). Moderators+ only; never on their own tools."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select

from app.db import utcnow
from app.deps import DB, Form, ModDep
from app.i18n import labels, lang_prefix, t
from app.models import Report, Tool, ToolRevision, User
from app.models.enums import ClaimState, ReportReason, ReportStatus, RevisionStatus, ToolStatus
from app.services import audit, certifications, email, permissions
from app.services import reports as report_service
from app.services import tools as tool_service
from app.services.tools import InvalidTransition, ToolError
from app.templating import render

pages = APIRouter()
actions = APIRouter()

TABS = ("new", "edits", "reports")


def queue_counts(db: DB) -> dict[str, int]:
    return {
        "new": int(
            db.scalar(select(func.count()).select_from(Tool).where(Tool.status == ToolStatus.pending)) or 0
        ),
        "edits": int(
            db.scalar(
                select(func.count())
                .select_from(ToolRevision)
                .where(ToolRevision.status == RevisionStatus.pending)
            )
            or 0
        ),
        "reports": int(
            db.scalar(select(func.count()).select_from(Report).where(Report.status == ReportStatus.open)) or 0
        ),
    }


@pages.get("/mod")
def queue(request: Request, db: DB, user: ModDep, tab: str = "new") -> Response:
    tab = tab if tab in TABS else "new"
    items: list[Any]
    if tab == "new":
        items = list(
            db.scalars(select(Tool).where(Tool.status == ToolStatus.pending).order_by(Tool.submitted_at))
            .unique()
            .all()
        )
    elif tab == "edits":
        items = list(
            db.scalars(
                select(ToolRevision)
                .where(ToolRevision.status == RevisionStatus.pending)
                .order_by(ToolRevision.created_at)
            )
            .unique()
            .all()
        )
    else:
        items = list(
            db.scalars(
                select(Report)
                .where(Report.status == ReportStatus.open)
                .order_by((Report.reason == ReportReason.csam).desc(), Report.created_at)  # CSAM first
            )
            .unique()
            .all()
        )
    return render(
        request, "mod/queue.html", {"tab": tab, "items": items, "counts": queue_counts(db), "now": utcnow()}
    )


def _tool(db: DB, tool_id: int) -> Tool:
    tool = db.get(Tool, tool_id)
    if tool is None or tool.status == ToolStatus.deleted:
        raise HTTPException(status_code=404)
    return tool


def _claims_view(
    db: DB, tool: Tool, lang: str, only: list[str] | None = None, proposed: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    catalogue = certifications.by_code(db)
    source = (
        proposed
        if proposed is not None
        else [{"code": c.certification.code, "details": c.details} for c in tool.claims]
    )
    states = {c.certification.code: c for c in tool.claims}
    out = []
    for item in source:
        cert = catalogue.get(item["code"])
        if cert is None or (only is not None and item["code"] not in only):
            continue
        row = states.get(item["code"])
        out.append(
            {
                "code": cert.code,
                "cert": cert,
                "rows": certifications.detail_rows(cert, item["details"], lang),
                "state": row.state.value if row is not None and proposed is None else None,
                "label": certifications.badge_label(cert, item["details"]),
            }
        )
    return out


@pages.get("/mod/tools/{tool_id}")
def review_tool(request: Request, db: DB, user: ModDep, tool_id: int) -> Response:
    tool = _tool(db, tool_id)
    lang = request.state.lang
    data = tool_service.snapshot(tool)
    check = certifications.check_claims(
        certifications.by_code(db),
        {c["code"]: {k: str(v) for k, v in c["details"].items()} for c in data["certifications"]},
        data["tool_type"],
        [c.slug for c in tool.categories],
        data["patient_data"],
        full=False,
    )
    pending_claims = [c.certification.code for c in tool.claims if c.state == ClaimState.pending]
    return render(
        request,
        "mod/tool.html",
        {
            "tool": tool,
            "can_act": permissions.can_moderate(user, tool),
            "claims": _claims_view(db, tool, lang),
            "pending_claims": pending_claims,
            "warnings": check.warnings,
            "open_reports": db.scalars(
                select(Report).where(Report.tool_id == tool.id, Report.status == ReportStatus.open)
            )
            .unique()
            .all(),
            "revision": tool_service.pending_revision(db, tool),
        },
    )


@pages.get("/mod/revisions/{revision_id}")
def review_revision(request: Request, db: DB, user: ModDep, revision_id: int) -> Response:
    revision = db.get(ToolRevision, revision_id)
    if revision is None:
        raise HTTPException(status_code=404)
    tool = revision.tool
    lang = request.state.lang
    live = tool_service.snapshot(tool)
    changed = certifications.changed_claims(tool, revision.data.get("certifications", []))
    media_by_id = {m.id: m for m in tool.media}
    return render(
        request,
        "mod/revision.html",
        {
            "revision": revision,
            "tool": tool,
            "diffs": tool_service.diff(db, live, revision.data, lang),
            "can_act": permissions.can_moderate(user, tool) and revision.status == RevisionStatus.pending,
            "claims": _claims_view(
                db, tool, lang, only=changed, proposed=revision.data.get("certifications", [])
            ),
            "media_by_id": media_by_id,
        },
    )


@pages.get("/mod/reports/{report_id}")
def review_report(request: Request, db: DB, user: ModDep, report_id: int) -> Response:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404)
    reporter = db.get(User, report.reporter_id) if report.reporter_id else None
    return render(
        request,
        "mod/report.html",
        {
            "report": report,
            "tool": report.tool,
            "reporter": reporter,
            "can_act": permissions.can_moderate(user, report.tool),
        },
    )


def build_reason(form: Any, lang: str, required: bool = True) -> str | None:
    """Template text in the owner's language + the moderator's free text (TECH_SPEC §7.3)."""
    key = form.get("reason_template") or ""
    text = (form.get("reason_text") or "").strip()
    parts = []
    if key in labels.REJECTION_REASONS and key != "other":
        parts.append(t(lang, labels.REJECTION_REASONS[key]))
    if text:
        parts.append(text)
    reason = "\n\n".join(parts)
    if required and not reason:
        return None
    return reason or None


def approval_suggestions(form: Any) -> str | None:
    """Optional advice emailed to the author with an approval; it never blocks publication."""
    return (form.get("suggestions") or "").strip()[:2000] or None


def claim_rejections(form: Any, codes: list[str], lang: str) -> dict[str, str]:
    out = {}
    for code in codes:
        if form.get(f"claim_{code}") == "reject":
            reason = (form.get(f"claim_{code}_reason") or "").strip()
            out[code] = reason or t(lang, labels.REJECTION_REASONS["certification"])
    return out


def _back(request: Request, path: str, flash: str) -> RedirectResponse:
    return RedirectResponse(f"{lang_prefix(request.state.lang)}{path}?flash={flash}", status_code=303)


TOOL_ACTIONS = {
    "approve": "approved",
    "reject": "rejected",
    "request-changes": "rejected",
    "hide": "hidden",
    "unhide": "unhidden",
}


@actions.post("/mod/tools/{tool_id}/reset-score")
def reset_score(request: Request, db: DB, user: ModDep, tool_id: int) -> Response:
    tool = _tool(db, tool_id)
    if not permissions.can_moderate(user, tool):
        raise HTTPException(status_code=403)
    tool.score_reset_at = utcnow()
    tool.score = 0.0
    tool.score_log = 0.0
    audit.log(db, user.id, "tool.reset_score", "tool", tool.id)
    db.commit()
    return _back(request, f"/mod/tools/{tool.id}", "score_reset")


@actions.post("/mod/tools/{tool_id}/{action}")
def tool_action(
    request: Request, db: DB, user: ModDep, tool_id: int, action: str, form: Form, background: BackgroundTasks
) -> Response:
    if action not in TOOL_ACTIONS:
        raise HTTPException(status_code=404)
    tool = _tool(db, tool_id)
    if not permissions.can_moderate(user, tool):
        raise HTTPException(status_code=403)
    owner_lang = tool.owner.locale.value
    reason = build_reason(form, owner_lang, required=action in ("reject", "request-changes", "hide"))
    if action in ("reject", "request-changes", "hide") and not reason:
        return _back(request, f"/mod/tools/{tool.id}", "reason_required")
    rejections = {}
    if action == "approve":
        reason = approval_suggestions(form)
        rejections = claim_rejections(
            form, [c.certification.code for c in tool.claims if c.state == ClaimState.pending], owner_lang
        )
    try:
        tool_service.transition(
            db, tool, action.replace("-", "_"), user, reason=reason, claim_rejections=rejections
        )
        db.commit()
    except (InvalidTransition, ToolError) as exc:
        db.rollback()
        raise HTTPException(status_code=409) from exc
    if action == "approve" and tool.github is not None:
        background.add_task(_sync_github_later, tool.id)  # TECH_SPEC §10: sync right after approval
    background.add_task(email.deliver_queued)
    target = "/mod" if action in ("approve", "reject", "request-changes") else f"/mod/tools/{tool.id}"
    return _back(request, target, TOOL_ACTIONS[action])


def _sync_github_later(tool_id: int) -> None:
    from app.db import SessionLocal, get_engine
    from app.services import github

    get_engine()
    with SessionLocal() as db:
        github.sync_all(db, tool_id=tool_id, delay=0)


@actions.post("/mod/revisions/{revision_id}/{action}")
def revision_action(
    request: Request,
    db: DB,
    user: ModDep,
    revision_id: int,
    action: str,
    form: Form,
    background: BackgroundTasks,
) -> Response:
    revision = db.get(ToolRevision, revision_id)
    if revision is None or action not in ("approve", "reject"):
        raise HTTPException(status_code=404)
    tool = revision.tool
    if not permissions.can_moderate(user, tool):
        raise HTTPException(status_code=403)
    owner_lang = tool.owner.locale.value
    try:
        if action == "approve":
            changed = certifications.changed_claims(tool, revision.data.get("certifications", []))
            tool_service.approve_revision(
                db, revision, user, claim_rejections(form, changed, owner_lang), approval_suggestions(form)
            )
        else:
            reason = build_reason(form, owner_lang)
            if not reason:
                return _back(request, f"/mod/revisions/{revision.id}", "reason_required")
            tool_service.reject_revision(db, revision, user, reason)
        db.commit()
    except InvalidTransition as exc:
        db.rollback()
        raise HTTPException(status_code=409) from exc
    background.add_task(email.deliver_queued)
    return _back(request, "/mod?tab=edits", "approved" if action == "approve" else "rejected")


@actions.post("/mod/reports/{report_id}/{action}")
def report_action(
    request: Request,
    db: DB,
    user: ModDep,
    report_id: int,
    action: str,
    form: Form,
    background: BackgroundTasks,
) -> Response:
    report = db.get(Report, report_id)
    if report is None or action not in ("resolve", "dismiss"):
        raise HTTPException(status_code=404)
    if not permissions.can_moderate(user, report.tool):
        raise HTTPException(status_code=403)
    note = form.get("note")
    report_service.close(db, report, user, action == "resolve", note if isinstance(note, str) else None)
    db.commit()
    background.add_task(email.deliver_queued)
    return _back(request, "/mod?tab=reports", "report_closed")
