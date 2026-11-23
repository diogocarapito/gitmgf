"""'My tools' and the tool editor (PRD F3, F15)."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.deps import DB, Form, UserDep
from app.forms.tool import DECLARATIONS, parse_tool_form
from app.i18n import lang_prefix
from app.models import Category, Tool, ToolMedia, User
from app.models.enums import ToolStatus
from app.services import certifications, email, media, permissions, ratelimit, stats
from app.services import tools as tool_service
from app.services.media import MediaError
from app.services.tools import InvalidTransition, ToolError
from app.templating import render

pages = APIRouter()
actions = APIRouter()


def owned_tool(db: DB, user: User, tool_id: int) -> Tool:
    tool = db.get(Tool, tool_id)
    if tool is None or not permissions.can_edit_tool(user, tool):
        raise HTTPException(status_code=404)
    return tool


def category_groups(db: DB) -> tuple[list[Category], list[Category]]:
    cats = db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name_pt)
    ).all()
    return [c for c in cats if not c.is_specialty], [c for c in cats if c.is_specialty]


def values_from_data(data: dict[str, Any], declarations: bool) -> dict[str, Any]:
    values: dict[str, Any] = {
        k: ("" if v is None else v) for k, v in data.items() if k not in ("certifications", "media_order")
    }
    values["tags"] = ", ".join(data.get("tags") or [])
    values["category_ids"] = [str(i) for i in data.get("category_ids") or []]
    for item in data.get("certifications") or []:
        values[f"cert_{item['code']}"] = "1"
        for key, value in (item.get("details") or {}).items():
            values[f"cert_{item['code']}__{key}"] = (
                "1" if value is True else ("" if value is False else value)
            )
    for name in DECLARATIONS:
        values[name] = declarations
    return values


def editor_page(
    request: Request,
    db: DB,
    tool: Tool | None,
    values: dict[str, Any],
    errors: dict[str, Any],
    warnings: list[str] | None = None,
    status_code: int = 200,
    notice: str | None = None,
) -> Response:
    purposes, specialties = category_groups(db)
    revision = tool_service.pending_revision(db, tool) if tool is not None else None
    claim_states = {c.certification.code: c for c in tool.claims} if tool is not None else {}
    return render(
        request,
        "me/tool_form.html",
        {
            "tool": tool,
            "values": values,
            "errors": errors,
            "warnings": warnings or [],
            "purposes": purposes,
            "specialties": specialties,
            "certs": certifications.catalogue(db),
            "claim_states": claim_states,
            "revision": revision,
            "media_items": tool_service.effective_media(db, tool) if tool is not None else [],
            "notice": notice,
        },
        status_code=status_code,
    )


@pages.get("/me/tools")
def my_tools(request: Request, db: DB, user: UserDep) -> Response:
    tools = tool_service.owned_tools(db, user)
    revisions = {t.id: tool_service.pending_revision(db, t) for t in tools}
    usage = stats.usage_for(db, [t.id for t in tools])
    github_errors = {t.id: t.github.last_error for t in tools if t.github is not None and t.github.last_error}
    return render(
        request,
        "me/tools.html",
        {"tools": tools, "revisions": revisions, "usage": usage, "github_errors": github_errors},
    )


@pages.get("/me/tools/new")
def new_tool_page(request: Request, db: DB, user: UserDep) -> Response:
    return editor_page(request, db, None, {"tool_languages": ["pt"], "platforms": []}, {})


@pages.get("/me/tools/{tool_id}/edit")
def edit_tool_page(request: Request, db: DB, user: UserDep, tool_id: int) -> Response:
    tool = owned_tool(db, user, tool_id)
    revision = tool_service.pending_revision(db, tool)
    data = revision.data if revision is not None else tool_service.snapshot(tool)
    return editor_page(
        request, db, tool, values_from_data(data, tool.declarations_accepted_at is not None), {}
    )


def _handle_save(
    request: Request, db: DB, user: User, tool: Tool | None, form: Any, background: BackgroundTasks
) -> Response:
    lang = request.state.lang
    parsed, errors, raw = parse_tool_form(form)
    submit = form.get("intent") == "submit"
    declarations = all(raw.get(name) for name in DECLARATIONS)
    certs = certifications.by_code(db)
    active = certifications.catalogue(db)
    raw_claims = certifications.parse_form(form, active)
    cat_slugs = (
        [c.slug for c in db.scalars(select(Category).where(Category.id.in_(parsed.category_ids))).all()]
        if parsed.category_ids
        else []
    )
    revision_mode = tool is not None and not tool_service.editable_in_place(tool)
    full = submit or revision_mode
    check = certifications.check_claims(
        certs,
        raw_claims,
        parsed.tool_data()["tool_type"],
        cat_slugs,
        parsed.tool_data()["patient_data"],
        full,
    )
    errors.update({k: (v, {}) for k, v in check.errors.items()})
    for code in check.claims:  # reflect auto-enabled CE in the form
        raw[f"cert_{code}"] = "1"
        for key, value in check.claims[code].items():
            raw.setdefault(f"cert_{code}__{key}", value)
    if full:
        for name, err in parsed.submission_errors().items():
            errors.setdefault(name, err)
    blocking = {
        k: v
        for k, v in errors.items()
        if not (submit and not revision_mode and k in parsed.submission_errors())
    }
    if tool is not None and tool.status == ToolStatus.pending:
        return editor_page(request, db, tool, raw, {}, status_code=409, notice="pending")
    if blocking:
        return editor_page(request, db, tool, raw, errors, check.warnings, status_code=422)

    if tool is None:
        if not ratelimit.hit(ratelimit.TOOL_CREATE_USER, "tool-create", str(user.id)):
            raise HTTPException(status_code=429)
        tool = tool_service.create_tool(db, user, parsed.tool_data(), check.claims)
        if declarations:
            from app.db import utcnow

            tool.declarations_accepted_at = utcnow()
        outcome = "in_place"
    else:
        try:
            outcome = tool_service.save_edit(db, tool, user, parsed.tool_data(), check.claims, declarations)
        except ToolError as exc:
            db.rollback()
            return editor_page(
                request, db, tool, raw, errors, check.warnings, status_code=409, notice=exc.message
            )
    db.commit()

    if outcome == "in_place" and submit:
        if errors:
            db.refresh(tool)
            return editor_page(
                request,
                db,
                tool,
                raw,
                errors,
                check.warnings,
                status_code=422,
                notice="draft_saved_incomplete",
            )
        try:
            tool_service.transition(db, tool, "submit", user)
            db.commit()
        except ToolError as exc:
            db.rollback()
            db.refresh(tool)
            return editor_page(
                request, db, tool, raw, errors, check.warnings, status_code=409, notice=exc.message
            )
        background.add_task(email.deliver_queued)
        return RedirectResponse(f"{lang_prefix(lang)}/me/tools?flash=submitted", status_code=303)
    flash = {"in_place": "draft_saved", "revision": "revision_submitted", "unchanged": "saved"}[outcome]
    if check.warnings and outcome != "unchanged":
        db.refresh(tool)
        return editor_page(
            request,
            db,
            tool,
            values_from_data(_current_data(db, tool), declarations),
            {},
            check.warnings,
            notice=flash,
        )
    return RedirectResponse(f"{lang_prefix(lang)}/me/tools/{tool.id}/edit?flash={flash}", status_code=303)


def _current_data(db: DB, tool: Tool) -> dict[str, Any]:
    revision = tool_service.pending_revision(db, tool)
    return revision.data if revision is not None else tool_service.snapshot(tool)


@pages.post("/me/tools/new")
def new_tool_submit(
    request: Request, db: DB, user: UserDep, form: Form, background: BackgroundTasks
) -> Response:
    return _handle_save(request, db, user, None, form, background)


@pages.post("/me/tools/{tool_id}/edit")
def edit_tool_submit(
    request: Request, db: DB, user: UserDep, tool_id: int, form: Form, background: BackgroundTasks
) -> Response:
    tool = owned_tool(db, user, tool_id)
    return _handle_save(request, db, user, tool, form, background)


@actions.post("/me/tools/{tool_id}/revision/withdraw")
def withdraw_revision(request: Request, db: DB, user: UserDep, tool_id: int) -> Response:
    tool = owned_tool(db, user, tool_id)
    revision = tool_service.pending_revision(db, tool)
    if revision is None:
        raise HTTPException(status_code=404)
    try:
        tool_service.withdraw_revision(db, revision, user)
    except InvalidTransition as exc:
        raise HTTPException(status_code=404) from exc
    db.commit()
    return RedirectResponse(
        f"{lang_prefix(request.state.lang)}/me/tools/{tool.id}/edit?flash=revision_withdrawn", status_code=303
    )


@actions.post("/me/tools/{tool_id}/media")
def upload_media(request: Request, db: DB, user: UserDep, tool_id: int, form: Form) -> Response:
    tool = owned_tool(db, user, tool_id)
    lang = request.state.lang
    upload = form.get("file")
    alt_pt = form.get("alt_text_pt")
    alt_en = form.get("alt_text_en")
    error: str | None = None
    if not ratelimit.hit(ratelimit.UPLOAD_USER, "upload", str(user.id)):
        raise HTTPException(status_code=429)
    if not isinstance(upload, UploadFile):
        error = "Escolhe um ficheiro de imagem."
    else:
        data = upload.file.read(media.MAX_BYTES + 1)
        try:
            tool_service.add_media(
                db,
                tool,
                user,
                data,
                alt_pt if isinstance(alt_pt, str) else "",
                alt_en if isinstance(alt_en, str) else None,
            )
            db.commit()
        except (MediaError, ToolError) as exc:
            db.rollback()
            error = exc.message
        except InvalidTransition as exc:
            db.rollback()
            raise HTTPException(status_code=409) from exc
    if error:
        db.refresh(tool)
        revision = tool_service.pending_revision(db, tool)
        data_ = revision.data if revision is not None else tool_service.snapshot(tool)
        return editor_page(
            request,
            db,
            tool,
            values_from_data(data_, tool.declarations_accepted_at is not None),
            {"file": (error, {})},
            status_code=422,
        )
    return RedirectResponse(
        f"{lang_prefix(lang)}/me/tools/{tool.id}/edit?flash=media_added#screenshots", status_code=303
    )


def _owned_media(db: DB, user: User, media_id: int) -> ToolMedia:
    item = db.get(ToolMedia, media_id)
    if item is None or not permissions.can_edit_tool(user, item.tool):
        raise HTTPException(status_code=404)
    return item


@actions.post("/me/media/{media_id}/delete")
def delete_media(request: Request, db: DB, user: UserDep, media_id: int) -> Response:
    item = _owned_media(db, user, media_id)
    tool_id = item.tool_id
    try:
        tool_service.remove_media(db, item, user)
        db.commit()
    except (InvalidTransition, ToolError) as exc:
        db.rollback()
        raise HTTPException(status_code=409) from exc
    return RedirectResponse(
        f"{lang_prefix(request.state.lang)}/me/tools/{tool_id}/edit?flash=media_removed#screenshots",
        status_code=303,
    )


@actions.post("/me/media/{media_id}/move")
def move_media(request: Request, db: DB, user: UserDep, media_id: int, form: Form) -> Response:
    item = _owned_media(db, user, media_id)
    direction = -1 if form.get("direction") == "up" else 1
    try:
        tool_service.move_media(db, item, user, direction)
        db.commit()
    except (InvalidTransition, ToolError) as exc:
        db.rollback()
        raise HTTPException(status_code=409) from exc
    return RedirectResponse(
        f"{lang_prefix(request.state.lang)}/me/tools/{item.tool_id}/edit#screenshots", status_code=303
    )


@pages.get("/me/tools/{tool_id}/stats")
def tool_stats(request: Request, db: DB, user: UserDep, tool_id: int) -> Response:
    tool = owned_tool(db, user, tool_id)
    daily = [d for d in stats.daily_series(db, tool.id, 90) if d["search"] or d["outbound"] or d["views"]]
    return render(
        request,
        "me/tool_stats.html",
        {"tool": tool, "daily": daily, "usage": stats.usage_for(db, [tool.id])[tool.id]},
    )


# Registered last: the generic `/{action}` segment must not shadow /media or /revision routes.
LIFECYCLE_FLASH = {
    "submit": "submitted",
    "withdraw": "withdrawn",
    "archive": "archived",
    "unarchive": "unarchived",
    "delete": "deleted",
}


@actions.post("/me/tools/{tool_id}/{action}")
def lifecycle(
    request: Request, db: DB, user: UserDep, tool_id: int, action: str, background: BackgroundTasks
) -> Response:
    if action not in LIFECYCLE_FLASH:
        raise HTTPException(status_code=404)
    tool = owned_tool(db, user, tool_id)
    lang = request.state.lang
    try:
        tool_service.transition(db, tool, action, user)
        db.commit()
    except ToolError as exc:
        db.rollback()
        key = "pending_limit" if "limite" in exc.message else None
        target = (
            f"{lang_prefix(lang)}/me/tools/{tool.id}/edit?intent=submit"
            if key is None
            else f"{lang_prefix(lang)}/me/tools?flash={key}"
        )
        return RedirectResponse(target, status_code=303)
    except InvalidTransition as exc:
        db.rollback()
        raise HTTPException(status_code=409) from exc
    background.add_task(email.deliver_queued)
    target = f"{lang_prefix(lang)}/me/tools?flash={LIFECYCLE_FLASH[action]}"
    return RedirectResponse(target, status_code=303)
