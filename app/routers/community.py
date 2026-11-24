"""Colaborações and comments (D41): /colabs pages, comments on tools and colabs, reactions, reports and
their moderation. Thin handlers: the rules live in services/colabs.py, services/comments.py and
services/permissions.py."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select

from app.deps import DB, CurrentUser, Form, ModDep, UserDep
from app.forms.common import errors_from, form_to_dict
from app.forms.community import ColabForm, CommentForm, ReasonForm
from app.i18n import N_, lang_path
from app.models import Colab, Comment, Report, Tool
from app.models.enums import ColabKind, Reaction, ReportStatus
from app.routers.public import handle_report, report_page, report_subject
from app.services import colabs, comments, email, permissions, ratelimit
from app.services.colabs import ColabError
from app.services.comments import CommentError
from app.templating import is_htmx, render

pages = APIRouter()
actions = APIRouter()


def _go(request: Request, path: str, flash: str | None = None, anchor: str | None = None) -> RedirectResponse:
    url = (
        lang_path(request.state.lang, path)
        + (f"?flash={flash}" if flash else "")
        + (f"#{anchor}" if anchor else "")
    )
    return RedirectResponse(url, status_code=303)


def _colab(db: DB, user: Any, colab_id: int) -> Colab:
    colab = db.get(Colab, colab_id)
    if colab is None or not permissions.can_view_colab(user, colab):
        raise HTTPException(status_code=404)
    return colab


def _comment(db: DB, user: Any, comment_id: int) -> Comment:
    """A comment whose page the user can see (hidden ones only for their author and moderators)."""
    comment = db.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise HTTPException(status_code=404)
    if comment.tool is not None and not permissions.can_view_tool(user, comment.tool):
        raise HTTPException(status_code=404)
    if comment.colab is not None and not permissions.can_view_colab(user, comment.colab):
        raise HTTPException(status_code=404)
    if comment.hidden_at is not None and not (
        permissions.is_moderator(user) or (user is not None and user.id == comment.author_id)
    ):
        raise HTTPException(status_code=404)
    return comment


def _comment_path(comment: Comment) -> str:
    return f"/t/{comment.tool.slug}" if comment.tool is not None else f"/colabs/{comment.colab_id}"


# ---------- colab pages ----------


@pages.get("/colabs")
def colab_index(
    request: Request, db: DB, user: CurrentUser, kind: str = "", status: str = "open", page: int = 1
) -> Response:
    chosen = ColabKind(kind) if kind in ColabKind.__members__ else None
    status = status if status in ("open", "resolved", "all") else "open"
    items, has_next, counts = colabs.listing(db, chosen, status, page)
    return render(
        request,
        "community/index.html",
        {
            "items": items,
            "has_next": has_next,
            "page": max(page, 1),
            "kind": chosen.value if chosen else "",
            "status": status,
            "kind_counts": counts,
            "comment_counts": comments.count_for_colabs(db, [c.id for c in items]),
            "can_post": permissions.can_post_colab(user),
        },
    )


def _colab_form(
    request: Request,
    db: DB,
    user: Any,
    values: dict[str, Any],
    errors: dict[str, Any],
    colab: Colab | None = None,
    status_code: int = 200,
) -> Response:
    return render(
        request,
        "community/form.html",
        {"values": values, "errors": errors, "colab": colab, "own_tools": colabs.own_tools(db, user)},
        status_code=status_code,
    )


@pages.get("/colabs/new")
def colab_new(request: Request, db: DB, user: UserDep, kind: str = "") -> Response:
    if not permissions.can_post_colab(user):
        return render(request, "community/blocked.html", {"what": "publish"}, status_code=403)
    return _colab_form(request, db, user, {"kind": kind if kind in ColabKind.__members__ else ""}, {})


@pages.post("/colabs/new")
def colab_create(request: Request, db: DB, user: UserDep, form: Form) -> Response:
    if not permissions.can_post_colab(user):
        raise HTTPException(status_code=403)
    raw = form_to_dict(form)
    try:
        data = ColabForm.model_validate(raw)
    except ValidationError as exc:
        return _colab_form(request, db, user, raw, errors_from(exc), status_code=422)
    if not ratelimit.hit(ratelimit.COLAB_USER, "colab", str(user.id)):
        errors = {"__all__": (N_("Publicaste demasiadas colaborações hoje. Tenta novamente amanhã."), {})}
        return _colab_form(request, db, user, raw, errors, status_code=429)
    try:
        colab = colabs.create(db, user, data.data())
    except ColabError:
        return _colab_form(
            request, db, user, raw, {"tool_id": (N_("Escolhe uma opção válida."), {})}, status_code=422
        )
    db.commit()
    return _go(request, f"/colabs/{colab.id}", "colab_posted")


@pages.get("/colabs/{colab_id}")
def colab_page(request: Request, db: DB, user: CurrentUser, colab_id: int) -> Response:
    colab = _colab(db, user, colab_id)
    lang = request.state.lang
    return render(
        request,
        "community/colab.html",
        {
            "colab": colab,
            "body_html": comments.render_bodies_text(db, colab.body, lang),
            "thread": comments.thread(db, user, colab=colab, lang=lang),
            "can_comment": permissions.can_comment_on_colab(user, colab),
            "can_edit": permissions.can_edit_colab(user, colab),
            "can_moderate": permissions.can_moderate_colab(user, colab),
            "is_author": user is not None and user.id == colab.author_id,
        },
    )


@pages.get("/colabs/{colab_id}/edit")
def colab_edit(request: Request, db: DB, user: UserDep, colab_id: int) -> Response:
    colab = _colab(db, user, colab_id)
    if not permissions.can_edit_colab(user, colab):
        raise HTTPException(status_code=404)
    values = {
        "kind": colab.kind.value,
        "title": colab.title,
        "body": colab.body,
        "link_url": colab.link_url or "",
        "tool_id": colab.tool_id or "",
    }
    return _colab_form(request, db, user, values, {}, colab)


@pages.post("/colabs/{colab_id}/edit")
def colab_update(request: Request, db: DB, user: UserDep, colab_id: int, form: Form) -> Response:
    colab = _colab(db, user, colab_id)
    if not permissions.can_edit_colab(user, colab):
        raise HTTPException(status_code=404)
    raw = form_to_dict(form)
    try:
        data = ColabForm.model_validate(raw)
        colabs.update(db, user, colab, data.data())
    except ValidationError as exc:
        return _colab_form(request, db, user, raw, errors_from(exc), colab, 422)
    except ColabError:
        return _colab_form(
            request, db, user, raw, {"tool_id": (N_("Escolhe uma opção válida."), {})}, colab, 422
        )
    db.commit()
    return _go(request, f"/colabs/{colab.id}", "colab_saved")


@actions.post("/colabs/{colab_id}/{action}")
def colab_action(request: Request, db: DB, user: UserDep, colab_id: int, action: str) -> Response:
    colab = _colab(db, user, colab_id)
    try:
        if action == "resolve":
            colabs.set_resolved(db, user, colab, True)
            flash = "colab_resolved"
        elif action == "reopen":
            colabs.set_resolved(db, user, colab, False)
            flash = "colab_reopened"
        elif action == "delete":
            colabs.delete_own(db, user, colab)
            db.commit()
            return _go(request, "/colabs", "colab_deleted")
        else:
            raise HTTPException(status_code=404)
    except ColabError as exc:
        raise HTTPException(status_code=404) from exc
    db.commit()
    return _go(request, f"/colabs/{colab.id}", flash)


# ---------- comments ----------


def _comment_form_page(
    request: Request, target: dict[str, Any], values: dict[str, Any], errors: dict[str, Any], status_code: int
) -> Response:
    """Shown only when a comment can't be saved (too long, rate limit…), so the text isn't lost."""
    return render(
        request,
        "community/comment_form.html",
        {"target": target, "values": values, "errors": errors},
        status_code=status_code,
    )


def _post_comment(
    request: Request,
    db: DB,
    user: Any,
    form: Any,
    background: BackgroundTasks,
    target: dict[str, Any],
    tool: Tool | None = None,
    colab: Colab | None = None,
) -> Response:
    raw = form_to_dict(form)
    try:
        data = CommentForm.model_validate(raw)
    except ValidationError as exc:
        return _comment_form_page(request, target, raw, errors_from(exc), 422)
    if not (
        ratelimit.hit(ratelimit.COMMENT_USER, "comment", str(user.id))
        and ratelimit.hit(ratelimit.COMMENT_USER_DAY, "comment-day", str(user.id))
    ):
        errors = {
            "__all__": (
                N_("Comentaste demasiadas vezes num curto espaço de tempo. Tenta novamente mais tarde."),
                {},
            )
        }
        return _comment_form_page(request, target, raw, errors, 429)
    parent = db.get(Comment, data.parent_id) if data.parent_id else None
    try:
        comment = comments.post(db, user, data.body, tool=tool, colab=colab, parent=parent)
    except CommentError as exc:
        raise HTTPException(status_code=403) from exc
    db.commit()
    background.add_task(email.deliver_queued)
    return _go(request, target["path"], "commented", f"comment-{comment.id}")


@pages.post("/t/{slug}/comments")
def tool_comment(
    request: Request, db: DB, user: UserDep, slug: str, form: Form, background: BackgroundTasks
) -> Response:
    tool = db.scalar(select(Tool).where(Tool.slug == slug))
    if tool is None or not permissions.can_view_tool(user, tool):
        raise HTTPException(status_code=404)
    if not permissions.can_comment_on_tool(user, tool):
        raise HTTPException(status_code=403)
    target = {"title": tool.title_pt, "path": f"/t/{tool.slug}", "action": f"/t/{tool.slug}/comments"}
    return _post_comment(request, db, user, form, background, target, tool=tool)


@pages.post("/colabs/{colab_id}/comments")
def colab_comment(
    request: Request, db: DB, user: UserDep, colab_id: int, form: Form, background: BackgroundTasks
) -> Response:
    colab = _colab(db, user, colab_id)
    if not permissions.can_comment_on_colab(user, colab):
        raise HTTPException(status_code=403)
    target = {"title": colab.title, "path": f"/colabs/{colab.id}", "action": f"/colabs/{colab.id}/comments"}
    return _post_comment(request, db, user, form, background, target, colab=colab)


@pages.get("/comments/{comment_id}/edit")
def comment_edit_form(request: Request, db: DB, user: UserDep, comment_id: int) -> Response:
    comment = _comment(db, user, comment_id)
    if not permissions.can_edit_comment(user, comment):
        raise HTTPException(status_code=404)
    target = {
        "title": "",
        "path": _comment_path(comment),
        "action": f"/comments/{comment.id}/edit",
        "edit": True,
    }
    return _comment_form_page(request, target, {"body": comment.body}, {}, 200)


@pages.post("/comments/{comment_id}/edit")
def comment_edit(request: Request, db: DB, user: UserDep, comment_id: int, form: Form) -> Response:
    comment = _comment(db, user, comment_id)
    target = {
        "title": "",
        "path": _comment_path(comment),
        "action": f"/comments/{comment.id}/edit",
        "edit": True,
    }
    raw = form_to_dict(form)
    try:
        data = CommentForm.model_validate(raw)
        comments.edit(db, user, comment, data.body)
    except ValidationError as exc:
        return _comment_form_page(request, target, raw, errors_from(exc), 422)
    except CommentError as exc:
        raise HTTPException(status_code=404) from exc
    db.commit()
    return _go(request, target["path"], "comment_saved", f"comment-{comment.id}")


@actions.post("/comments/{comment_id}/delete")
def comment_delete(request: Request, db: DB, user: UserDep, comment_id: int) -> Response:
    comment = _comment(db, user, comment_id)
    path = _comment_path(comment)
    try:
        comments.delete_own(db, user, comment)
    except CommentError as exc:
        raise HTTPException(status_code=404) from exc
    db.commit()
    return _go(request, path, "comment_deleted", "comentarios")


@actions.post("/comments/{comment_id}/react")
def comment_react(request: Request, db: DB, user: CurrentUser, comment_id: int, form: Form) -> Response:
    comment = _comment(db, user, comment_id)
    if user is None:
        login = (
            lang_path(request.state.lang, "/login")
            + "?next="
            + lang_path(request.state.lang, _comment_path(comment))
        )
        if is_htmx(request):
            return Response(status_code=204, headers={"HX-Redirect": login})
        return RedirectResponse(login, status_code=303)
    value = form.get("emoji")
    if not isinstance(value, str) or value not in Reaction.__members__:
        raise HTTPException(status_code=422)
    if not ratelimit.hit(ratelimit.REACT_USER, "react", str(user.id)):
        raise HTTPException(status_code=429)
    try:
        comments.toggle_reaction(db, user, comment, Reaction(value))
    except CommentError as exc:
        raise HTTPException(status_code=403) from exc
    db.commit()
    if is_htmx(request):
        return render(
            request,
            "community/_reactions.html",
            {
                "c": comment,
                "reactions": comments.reactions_for(db, [comment.id], user)[comment.id],
                "can_react": True,
            },
        )
    return _go(request, _comment_path(comment), anchor=f"comment-{comment.id}")


# ---------- reports ----------


@pages.get("/comments/{comment_id}/report")
def comment_report_form(request: Request, db: DB, user: CurrentUser, comment_id: int) -> Response:
    comment = _comment(db, user, comment_id)
    return report_page(request, report_subject(request, comment=comment), {}, {})


@pages.post("/comments/{comment_id}/report")
def comment_report(
    request: Request, db: DB, user: CurrentUser, comment_id: int, form: Form, background: BackgroundTasks
) -> Response:
    comment = _comment(db, user, comment_id)
    done = lang_path(request.state.lang, _comment_path(comment)) + "?flash=reported"
    return handle_report(request, db, user, form, background, report_subject(request, comment=comment), done)


@pages.get("/colabs/{colab_id}/report")
def colab_report_form(request: Request, db: DB, user: CurrentUser, colab_id: int) -> Response:
    colab = _colab(db, user, colab_id)
    return report_page(request, report_subject(request, colab=colab), {}, {})


@pages.post("/colabs/{colab_id}/report")
def colab_report(
    request: Request, db: DB, user: CurrentUser, colab_id: int, form: Form, background: BackgroundTasks
) -> Response:
    colab = _colab(db, user, colab_id)
    done = lang_path(request.state.lang, f"/colabs/{colab.id}") + "?flash=reported"
    return handle_report(request, db, user, form, background, report_subject(request, colab=colab), done)


# ---------- moderation ----------


def _open_reports(db: DB, **subject: int) -> list[Report]:
    query = select(Report).where(Report.status == ReportStatus.open)
    for column, value in subject.items():
        query = query.where(getattr(Report, column) == value)
    return list(db.scalars(query.order_by(Report.created_at)).unique().all())


@pages.get("/mod/comments/{comment_id}")
def mod_comment(request: Request, db: DB, user: ModDep, comment_id: int) -> Response:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404)
    return render(
        request,
        "community/mod_item.html",
        {
            "comment": comment,
            "colab": None,
            "body_html": comments.render_bodies(db, [comment], request.state.lang)[comment.id],
            "can_act": permissions.can_moderate_comment(user, comment) and comment.deleted_at is None,
            "reports": _open_reports(db, comment_id=comment.id),
            "author": comment.author,
            "public_path": _comment_path(comment),
            "values": {},
            "errors": {},
        },
    )


@pages.get("/mod/colabs/{colab_id}")
def mod_colab(request: Request, db: DB, user: ModDep, colab_id: int) -> Response:
    colab = db.get(Colab, colab_id)
    if colab is None:
        raise HTTPException(status_code=404)
    return render(
        request,
        "community/mod_item.html",
        {
            "comment": None,
            "colab": colab,
            "body_html": comments.render_bodies_text(db, colab.body, request.state.lang),
            "can_act": permissions.can_moderate_colab(user, colab),
            "reports": _open_reports(db, colab_id=colab.id),
            "author": colab.author,
            "public_path": f"/colabs/{colab.id}",
            "values": {},
            "errors": {},
        },
    )


@actions.post("/mod/comments/{comment_id}/{action}")
def mod_comment_action(
    request: Request,
    db: DB,
    user: ModDep,
    comment_id: int,
    action: str,
    form: Form,
    background: BackgroundTasks,
) -> Response:
    comment = db.get(Comment, comment_id)
    if comment is None or action not in ("hide", "unhide"):
        raise HTTPException(status_code=404)
    try:
        if action == "hide":
            data = ReasonForm.model_validate(form_to_dict(form))
            comments.hide(db, user, comment, data.reason)
        else:
            comments.unhide(db, user, comment)
    except ValidationError:
        return _go(request, f"/mod/comments/{comment.id}", "reason_required")
    except CommentError as exc:
        raise HTTPException(status_code=403) from exc
    db.commit()
    background.add_task(email.deliver_queued)
    return _go(
        request, f"/mod/comments/{comment.id}", "comment_hidden" if action == "hide" else "comment_unhidden"
    )


@actions.post("/mod/colabs/{colab_id}/{action}")
def mod_colab_action(
    request: Request,
    db: DB,
    user: ModDep,
    colab_id: int,
    action: str,
    form: Form,
    background: BackgroundTasks,
) -> Response:
    colab = db.get(Colab, colab_id)
    if colab is None or action not in ("hide", "unhide"):
        raise HTTPException(status_code=404)
    try:
        if action == "hide":
            data = ReasonForm.model_validate(form_to_dict(form))
            colabs.hide(db, user, colab, data.reason)
        else:
            colabs.unhide(db, user, colab)
    except ValidationError:
        return _go(request, f"/mod/colabs/{colab.id}", "reason_required")
    except ColabError as exc:
        raise HTTPException(status_code=403) from exc
    db.commit()
    background.add_task(email.deliver_queued)
    return _go(request, f"/mod/colabs/{colab.id}", "colab_hidden" if action == "hide" else "colab_unhidden")


# ---------- account restrictions (moderator+) ----------


@pages.get("/mod/users/{user_id}")
def mod_user(request: Request, db: DB, user: ModDep, user_id: int) -> Response:
    from sqlalchemy import func

    from app.models import User

    target = db.get(User, user_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(status_code=404)
    recent = list(
        db.scalars(
            select(Comment)
            .where(Comment.author_id == target.id, Comment.deleted_at.is_(None))
            .order_by(Comment.created_at.desc())
            .limit(10)
        )
        .unique()
        .all()
    )
    counts = {
        "tools": db.scalar(select(func.count()).select_from(Tool).where(Tool.owner_id == target.id)) or 0,
        "colabs": db.scalar(select(func.count()).select_from(Colab).where(Colab.author_id == target.id)) or 0,
        "comments": db.scalar(select(func.count()).select_from(Comment).where(Comment.author_id == target.id))
        or 0,
    }
    return render(
        request,
        "community/mod_user.html",
        {
            "target": target,
            "recent": recent,
            "counts": counts,
            "can_act": permissions.can_restrict(user, target),
            "values": {},
            "errors": {},
        },
    )


@actions.post("/mod/users/{user_id}/{action}/{kind}")
def mod_user_action(
    request: Request,
    db: DB,
    user: ModDep,
    user_id: int,
    action: str,
    kind: str,
    form: Form,
    background: BackgroundTasks,
) -> Response:
    from app.models import User
    from app.services import restrictions

    target = db.get(User, user_id)
    if target is None or action not in ("restrict", "lift") or kind not in restrictions.KINDS:
        raise HTTPException(status_code=404)
    try:
        if action == "restrict":
            data = ReasonForm.model_validate(form_to_dict(form))
            restrictions.restrict(db, user, target, kind, data.reason)  # type: ignore[arg-type]
        else:
            restrictions.lift(db, user, target, kind)  # type: ignore[arg-type]
    except ValidationError:
        return _go(request, f"/mod/users/{target.id}", "reason_required")
    except restrictions.RestrictionError as exc:
        raise HTTPException(status_code=403) from exc
    db.commit()
    background.add_task(email.deliver_queued)
    return _go(request, f"/mod/users/{target.id}", "restricted" if action == "restrict" else "unrestricted")
