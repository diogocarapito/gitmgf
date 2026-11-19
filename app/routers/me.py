"""Signed-in user's own area: settings, notifications, stars, GDPR self-service."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.config import get_settings
from app.deps import DB, Form, UserDep
from app.forms.account import ProfileForm
from app.forms.common import errors_from, form_to_dict
from app.i18n import N_, lang_prefix
from app.models import User, UserSession
from app.routers.auth import specialty_options
from app.services import auth as auth_service
from app.services import sessions
from app.templating import render

pages = APIRouter()
actions = APIRouter()


def _profile_values(user: User) -> dict[str, Any]:
    return {
        "display_name": user.display_name,
        "handle": user.handle or "",
        "profession": user.profession.value if user.profession else "",
        "specialty_category_id": user.specialty_category_id or "",
        "workplace": user.workplace or "",
        "github_username": user.github_username or "",
        "locale": user.locale.value,
    }


def _settings_page(
    request: Request, db: DB, user: User, values: dict[str, Any], errors: dict[str, Any], status: int = 200
) -> Response:
    return render(
        request,
        "me/settings.html",
        {
            "values": values,
            "errors": errors,
            "specialties": specialty_options(db),
            "session_count": sessions.count_for(db, user.id),
        },
        status_code=status,
    )


@actions.post("/me/avatar")
def upload_avatar(request: Request, db: DB, user: UserDep, form: Form) -> Response:
    """Profile photo (D33): re-encoded square WebP; the original bytes are never kept."""
    from app.services import media, profiles, ratelimit

    if not ratelimit.hit(ratelimit.UPLOAD_USER, "upload", str(user.id)):
        raise HTTPException(status_code=429)
    upload = form.get("avatar")
    error: str | None = None
    if not isinstance(upload, UploadFile):
        error = N_("Escolha um ficheiro de imagem.")
    else:
        try:
            profiles.set_avatar(db, user, upload.file.read(media.MAX_BYTES + 1))
            db.commit()
        except media.MediaError as exc:
            db.rollback()
            error = exc.message
    if error:
        return _settings_page(request, db, user, _profile_values(user), {"avatar": (error, {})}, status=422)
    return RedirectResponse(f"{lang_prefix(request.state.lang)}/me/settings?flash=avatar_saved", 303)


@actions.post("/me/avatar/delete")
def delete_avatar(request: Request, db: DB, user: UserDep) -> Response:
    from app.services import profiles

    profiles.remove_avatar(db, user, user)
    db.commit()
    return RedirectResponse(f"{lang_prefix(request.state.lang)}/me/settings?flash=avatar_removed", 303)


@pages.get("/me/settings")
def settings_page(request: Request, db: DB, user: UserDep) -> Response:
    return _settings_page(request, db, user, _profile_values(user), {})


@pages.post("/me/settings")
def settings_submit(request: Request, db: DB, user: UserDep, form: Form) -> Response:
    raw = form_to_dict(form)
    errors: dict[str, Any] = {}
    data: ProfileForm | None = None
    try:
        data = ProfileForm.model_validate(raw)
    except ValidationError as exc:
        errors = errors_from(exc)
    if data is not None and not auth_service.handle_available(db, data.handle, user.id):
        errors["handle"] = (N_("Este identificador já está a ser usado."), {})
    valid_specialties = {c.id for c in specialty_options(db)}
    if (
        data is not None
        and data.specialty_category_id is not None
        and data.specialty_category_id not in valid_specialties
    ):
        errors["specialty_category_id"] = (N_("Escolha uma opção válida."), {})
    if errors or data is None:
        return _settings_page(request, db, user, raw, errors, status=422)
    for field in (
        "display_name",
        "handle",
        "profession",
        "specialty_category_id",
        "workplace",
        "github_username",
    ):
        setattr(user, field, getattr(data, field))
    user.locale = data.locale
    db.commit()
    return RedirectResponse(f"{lang_prefix(user.locale.value)}/me/settings?flash=saved", status_code=303)


@pages.post("/me/password")
def change_password(request: Request, db: DB, user: UserDep, form: Form) -> Response:
    from app.forms.account import new_password_errors
    from app.services import passwords, ratelimit

    current = str(form.get("current_password") or "")
    new = str(form.get("password") or "")
    errors: dict[str, Any] = {}
    if not ratelimit.hit(ratelimit.PASSWORD_CHANGE_USER, "pw-change", str(user.id)):
        raise HTTPException(status_code=429)
    if not passwords.verify_password(current, user.password_hash):
        errors["current_password"] = (N_("A palavra-passe atual está incorreta."), {})
    else:
        errors = new_password_errors(new, str(form.get("password_confirm") or ""), user.email)
    if errors:
        return _settings_page(request, db, user, _profile_values(user), errors, status=422)
    auth_service.set_password(db, user, new)
    keep = request.cookies.get(get_settings().session_cookie)
    for row in db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all():
        if keep is None or row.id != sessions.hash_token(keep):
            db.delete(row)  # sign out every other device
    db.commit()
    return RedirectResponse(
        f"{lang_prefix(request.state.lang)}/me/settings?flash=password_changed", status_code=303
    )


@pages.get("/me/stars")
def my_stars(request: Request, db: DB, user: UserDep) -> Response:
    from sqlalchemy import select

    from app.models import PUBLIC_STATUSES, Star, Tool
    from app.services import certifications

    tools = list(
        db.scalars(
            select(Tool)
            .join(Star, Star.tool_id == Tool.id)
            .where(Star.user_id == user.id, Tool.status.in_(PUBLIC_STATUSES))
            .order_by(Star.created_at.desc())
        )
        .unique()
        .all()
    )
    badges = certifications.badges_for(db, [t.id for t in tools], request.state.lang)
    return render(request, "me/stars.html", {"tools": tools, "badges": badges})


@pages.get("/me/notifications")
def notifications(request: Request, db: DB, user: UserDep, page: int = 1) -> Response:
    """Moderation decisions and suggestions for the user's tools, plus moderators' to-dos (D32, D36).

    Opening the page marks everything as read; to-dos stay in the badge until the queue is handled."""
    from app.services import notifications as notes

    page = max(1, page)
    items, has_next = notes.feed(db, user, page)
    todos = notes.todos(db, user)
    notes.mark_all_read(db, user)
    db.commit()
    request.state.unread_count = sum(todos.values())
    return render(
        request,
        "me/notifications.html",
        {"items": items, "todos": todos, "page": page, "has_next": has_next},
    )


@actions.post("/me/notifications/{suggestion_id}/delete")
def delete_notification(request: Request, db: DB, user: UserDep, suggestion_id: int) -> Response:
    from app.services import suggestions

    if not suggestions.remove(db, user, suggestion_id):
        raise HTTPException(status_code=404)
    db.commit()
    return RedirectResponse(
        f"{lang_prefix(request.state.lang)}/me/notifications?flash=suggestion_deleted", status_code=303
    )


@actions.post("/me/notifications/decisions/{notification_id}/delete")
def delete_decision(request: Request, db: DB, user: UserDep, notification_id: int) -> Response:
    from app.services import notifications as notes

    if not notes.remove(db, user, notification_id):
        raise HTTPException(status_code=404)
    db.commit()
    return RedirectResponse(
        f"{lang_prefix(request.state.lang)}/me/notifications?flash=notification_deleted", status_code=303
    )


@actions.get("/me/export.json")
def export_data(db: DB, user: UserDep) -> Response:
    """GDPR Art. 15/20: everything we hold about the account, as JSON."""
    import json

    from app.services import gdpr

    body = json.dumps(gdpr.export(db, user), ensure_ascii=False, indent=2, default=str)
    return Response(
        body,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="gitmgf-dados.json"',
            "Cache-Control": "no-store",
        },
    )


@pages.get("/me/delete-account")
def delete_account_page(request: Request, db: DB, user: UserDep) -> Response:
    from app.services import tools as tool_service

    return render(
        request, "me/delete_account.html", {"tools": tool_service.owned_tools(db, user), "errors": {}}
    )


@pages.post("/me/delete-account")
def delete_account(
    request: Request, db: DB, user: UserDep, form: Form, background: BackgroundTasks
) -> Response:
    from app.services import email, gdpr
    from app.services import tools as tool_service

    if form.get("confirm") != "1":
        return render(
            request,
            "me/delete_account.html",
            {
                "tools": tool_service.owned_tools(db, user),
                "errors": {"confirm": (N_("Confirme que quer eliminar a conta."), {})},
            },
            status_code=422,
        )
    lang = user.locale.value
    gdpr.delete_account(db, user, user)
    db.commit()
    background.add_task(email.deliver_queued)
    response = RedirectResponse(f"{lang_prefix(lang)}/?flash=account_deleted", status_code=303)
    response.delete_cookie(get_settings().session_cookie, path="/")
    return response
