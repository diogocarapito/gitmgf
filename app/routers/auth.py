"""Sign-in, invite-only registration, reset links, onboarding (PRD F1/F2 as amended by D26)."""

import hashlib
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import select

from app.config import get_settings
from app.db import utcnow
from app.deps import DB, CurrentUser, Form, LoginRequired
from app.forms.account import LoginForm, OnboardingForm, RegisterForm, new_password_errors
from app.forms.common import errors_from, form_to_dict
from app.i18n import N_
from app.models import Category, User
from app.services import auth as auth_service
from app.services import email, ratelimit, sessions, settings_store
from app.services.auth import AuthError
from app.templating import render

pages = APIRouter()
actions = APIRouter()

AUTH_ERRORS = {
    "bad_credentials": N_("Email ou palavra-passe incorretos."),
    "suspended": N_(
        "Não é possível iniciar sessão com esta conta. Contacte-nos se achar que se trata de um erro."
    ),
    "invalid_invite": N_("O convite é inválido, já foi usado ou expirou. Peça um novo convite."),
    "invite_email_mismatch": N_("Este convite foi criado para outro endereço de email."),
    "email_taken": N_("Já existe uma conta com este email. Inicie sessão."),
    "invalid_link": N_("Esta ligação é inválida, já foi usada ou expirou. Peça uma nova a um administrador."),
    "rate_limited": N_("Demasiadas tentativas. Aguarde um pouco e tente novamente."),
}


def client_key(request: Request) -> str:
    """Rate-limit key derived from the client IP; the raw IP is never stored or logged."""
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie,
        token,
        max_age=int(sessions.SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def login_response(db: DB, request: Request, user: User, next_path: str | None) -> RedirectResponse:
    auth_service.check_can_login(user)
    auth_service.apply_admin_emails(db, user)
    old = request.cookies.get(get_settings().session_cookie)
    if old:
        sessions.destroy(db, old)  # a fresh session on every login (fixation protection)
    token = sessions.create(db, user, request.headers.get("user-agent"))
    db.commit()
    lang = user.locale.value
    target = auth_service.safe_next(next_path) or f"/{lang}/"
    if auth_service.needs_onboarding(db, user):
        target = f"/{lang}/onboarding?next={quote(target, safe='/')}"
    response = RedirectResponse(target, status_code=303)
    _set_session_cookie(response, token)
    return response


def _login_page(request: Request, next_path: str | None, status_code: int = 200, **ctx: Any) -> Response:
    return render(
        request,
        "auth/login.html",
        {"next": auth_service.safe_next(next_path) or "", "errors": {}, "email": "", **ctx},
        status_code=status_code,
    )


@pages.get("/login")
def login_page(request: Request, user: CurrentUser, next: str | None = None) -> Response:
    if user is not None:
        return RedirectResponse(auth_service.safe_next(next) or f"/{request.state.lang}/", status_code=303)
    return _login_page(request, next)


@pages.post("/login")
def login_submit(request: Request, db: DB, form: Form) -> Response:
    raw = form_to_dict(form)
    next_path = raw.get("next")
    try:
        data = LoginForm.model_validate(raw)
    except ValidationError as exc:
        return _login_page(request, next_path, 422, errors=errors_from(exc), email=raw.get("email", ""))
    address = auth_service.normalize_email(str(data.email))
    email_key = hashlib.sha256(address.encode()).hexdigest()[:16]
    if not (
        ratelimit.hit(ratelimit.LOGIN_IP, "login-ip", client_key(request))
        and ratelimit.hit(ratelimit.LOGIN_EMAIL, "login-email", email_key)
    ):
        return _login_page(request, next_path, 429, error=AUTH_ERRORS["rate_limited"], email=address)
    try:
        user = auth_service.authenticate(db, address, data.password)
    except AuthError as exc:
        return _login_page(
            request,
            next_path,
            401 if exc.code == "bad_credentials" else 403,
            error=AUTH_ERRORS[exc.code],
            email=address,
        )
    return login_response(db, request, user, data.next)


def _register_page(
    request: Request,
    db: DB,
    values: dict[str, Any],
    errors: dict[str, Any],
    status_code: int = 200,
    **ctx: Any,
) -> Response:
    invite_code = values.get("invite") or ""
    return render(
        request,
        "auth/register.html",
        {
            "values": values,
            "errors": errors,
            "invite_required": auth_service.registration_needs_invite(db, values.get("email")),
            "invite_valid": auth_service.find_invite(db, invite_code) is not None if invite_code else False,
            **ctx,
        },
        status_code=status_code,
    )


@pages.get("/register")
def register_page(request: Request, db: DB, user: CurrentUser, invite: str | None = None) -> Response:
    if user is not None:
        return RedirectResponse(f"/{request.state.lang}/", status_code=303)
    return _register_page(request, db, {"invite": invite or ""}, {})


@pages.post("/register")
def register_submit(request: Request, db: DB, form: Form) -> Response:
    raw = form_to_dict(form)
    raw.pop("csrf_token", None)
    if not ratelimit.hit(ratelimit.REGISTER_IP, "register", client_key(request)):
        return _register_page(request, db, raw, {}, 429, error=AUTH_ERRORS["rate_limited"])
    try:
        data = RegisterForm.model_validate(raw)
    except ValidationError as exc:
        return _register_page(request, db, raw, errors_from(exc), 422)
    errors = data.password_errors()
    if errors:
        return _register_page(request, db, raw, errors, 422)
    try:
        user = auth_service.register(db, str(data.email), data.password, data.invite, request.state.lang)
    except AuthError as exc:
        db.rollback()
        field = "email" if exc.code in ("email_taken", "invite_email_mismatch") else "invite"
        return _register_page(request, db, raw, {field: (AUTH_ERRORS[exc.code], {})}, 422)
    return login_response(db, request, user, None)


@pages.get("/reset/{token}")
def reset_page(request: Request, db: DB, token: str) -> Response:
    row = auth_service.find_reset_token(db, token)
    if row is None:
        return render(request, "auth/reset_invalid.html", {}, status_code=400)
    return render(request, "auth/reset.html", {"token": token, "errors": {}, "account": row.user.email})


@pages.post("/reset/{token}")
def reset_submit(request: Request, db: DB, token: str, form: Form) -> Response:
    row = auth_service.find_reset_token(db, token)
    if row is None:
        return render(request, "auth/reset_invalid.html", {}, status_code=400)
    password = str(form.get("password") or "")
    errors = new_password_errors(password, str(form.get("password_confirm") or ""), row.user.email)
    if errors:
        return render(
            request, "auth/reset.html", {"token": token, "errors": errors, "account": row.user.email}, 422
        )
    user = auth_service.reset_password(db, token, password)
    return login_response(db, request, user, None)


@actions.post("/auth/logout")
def logout(request: Request, db: DB) -> Response:
    token = request.cookies.get(get_settings().session_cookie)
    if token:
        sessions.destroy(db, token)
        db.commit()
    response = RedirectResponse(f"/{request.state.lang}/", status_code=303)
    response.delete_cookie(get_settings().session_cookie, path="/")
    return response


@actions.post("/auth/logout-all")
def logout_all(request: Request, db: DB, user: CurrentUser) -> Response:
    if user is not None:
        sessions.destroy_all(db, user.id)
        db.commit()
    response = RedirectResponse(f"/{request.state.lang}/?flash=signed_out_all", status_code=303)
    response.delete_cookie(get_settings().session_cookie, path="/")
    return response


def specialty_options(db: DB) -> list[Category]:
    return list(
        db.scalars(
            select(Category)
            .where(Category.is_specialty.is_(True), Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name_pt)
        ).all()
    )


def _onboarding_values(db: DB, user: User) -> dict[str, Any]:
    return {
        "display_name": user.display_name,
        "handle": user.handle
        or auth_service.suggest_handle(db, user.display_name or user.email.split("@")[0]),
        "profession": user.profession.value if user.profession else "",
        "specialty_category_id": user.specialty_category_id or "",
        "workplace": user.workplace or "",
        "github_username": user.github_username or "",
        "locale": user.locale.value,
    }


@pages.get("/onboarding")
def onboarding_page(request: Request, db: DB, user: CurrentUser, next: str | None = None) -> Response:
    if user is None:
        raise LoginRequired(request.url.path)
    return render(
        request,
        "auth/onboarding.html",
        {
            "values": _onboarding_values(db, user),
            "errors": {},
            "next": auth_service.safe_next(next) or "",
            "specialties": specialty_options(db),
            "reaccept": user.onboarded_at is not None,
        },
    )


@pages.post("/onboarding")
def onboarding_submit(
    request: Request, db: DB, user: CurrentUser, form: Form, background: BackgroundTasks
) -> Response:
    if user is None:
        raise HTTPException(status_code=403)
    raw = form_to_dict(form)
    raw["accept_terms"] = form.get("accept_terms") in ("1", "on", "true")
    errors: dict[str, Any] = {}
    data: OnboardingForm | None = None
    try:
        data = OnboardingForm.model_validate(raw)
    except ValidationError as exc:
        errors = errors_from(exc)
    if data is not None:
        if not auth_service.handle_available(db, data.handle, user.id):
            errors["handle"] = (N_("Este identificador já está a ser usado."), {})
        if data.specialty_category_id is not None:
            valid = {c.id for c in specialty_options(db)}
            if data.specialty_category_id not in valid:
                errors["specialty_category_id"] = (N_("Escolha uma opção válida."), {})
    if errors or data is None:
        return render(
            request,
            "auth/onboarding.html",
            {
                "values": raw,
                "errors": errors,
                "next": auth_service.safe_next(raw.get("next")) or "",
                "specialties": specialty_options(db),
                "reaccept": user.onboarded_at is not None,
            },
            status_code=422,
        )
    first_time = user.onboarded_at is None
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
    now = utcnow()
    user.onboarded_at = user.onboarded_at or now
    user.terms_version = settings_store.get(db, "terms.current_version")
    user.terms_accepted_at = now
    if first_time:
        email.enqueue(db, user.email, "welcome", {"name": user.display_name}, user.locale.value)
    db.commit()
    background.add_task(email.deliver_queued)
    target = auth_service.safe_next(raw.get("next")) or f"/{user.locale.value}/"
    return RedirectResponse(target, status_code=303)
