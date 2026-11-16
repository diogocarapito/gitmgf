"""Signed-in user's own area: settings, linked accounts, stars, GDPR self-service."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError

from app.config import get_settings
from app.deps import DB, Form, UserDep
from app.forms.account import ProfileForm
from app.forms.common import errors_from, form_to_dict
from app.i18n import N_
from app.models import User
from app.models.enums import OAuthProvider
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
    settings = get_settings()
    linked = {a.provider.value for a in user.oauth_accounts}
    return render(
        request,
        "me/settings.html",
        {
            "values": values,
            "errors": errors,
            "specialties": specialty_options(db),
            "linked": linked,
            "providers": [
                ("github", "GitHub", settings.github_enabled),
                ("google", "Google", settings.google_enabled),
            ],
            "session_count": sessions.count_for(db, user.id),
        },
        status_code=status,
    )


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
    return RedirectResponse(f"/{user.locale.value}/me/settings?flash=saved", status_code=303)


@actions.post("/me/providers/{provider}/unlink")
def unlink(request: Request, db: DB, user: UserDep, provider: str) -> Response:
    try:
        prov = OAuthProvider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    auth_service.unlink_provider(db, user, prov)
    db.commit()
    return RedirectResponse(f"/{request.state.lang}/me/settings?flash=unlinked", status_code=303)


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
    response = RedirectResponse(f"/{lang}/?flash=account_deleted", status_code=303)
    response.delete_cookie(get_settings().session_cookie, path="/")
    return response
