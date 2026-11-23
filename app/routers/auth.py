"""Sign-in, registration with an emailed code, password reset, onboarding (PRD F1/F2; D26, D29, D30)."""

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
from app.i18n import N_, lang_prefix
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
        "Não é possível iniciar sessão com esta conta. Contacta-nos se achares que se trata de um erro."
    ),
    "invalid_invite": N_("O convite é inválido, já foi usado ou expirou. Pede um novo convite."),
    "invite_email_mismatch": N_("Este convite foi criado para outro endereço de email."),
    "email_taken": N_("Já existe uma conta com este email. Inicia sessão."),
    "invalid_link": N_("Esta ligação é inválida, já foi usada ou expirou. Pede uma nova a um administrador."),
    "rate_limited": N_("Demasiadas tentativas. Aguarda um pouco e tenta novamente."),
    "bad_code": N_("Código incorreto. Verifica o último email que enviámos e tenta novamente."),
    "code_expired": N_("Este código expirou ou foi tentado demasiadas vezes. Pede um novo."),
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
    target = auth_service.safe_next(next_path) or f"{lang_prefix(lang)}/"
    if auth_service.needs_onboarding(db, user):
        target = f"{lang_prefix(lang)}/onboarding?next={quote(target, safe='/')}"
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
        return RedirectResponse(
            auth_service.safe_next(next) or f"{lang_prefix(request.state.lang)}/", status_code=303
        )
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
            "specialties": specialty_options(db),
            **ctx,
        },
        status_code=status_code,
    )


def _email_key(address: str) -> str:
    return hashlib.sha256(address.encode()).hexdigest()[:16]


@pages.get("/register")
def register_page(request: Request, db: DB, user: CurrentUser, invite: str | None = None) -> Response:
    if user is not None:
        return RedirectResponse(f"{lang_prefix(request.state.lang)}/", status_code=303)
    return _register_page(request, db, {"invite": invite or ""}, {})


@pages.post("/register")
def register_submit(request: Request, db: DB, form: Form, background: BackgroundTasks) -> Response:
    raw = form_to_dict(form)
    raw.pop("csrf_token", None)
    raw["accept_terms"] = form.get("accept_terms") in ("1", "on", "true")
    if not ratelimit.hit(ratelimit.REGISTER_IP, "register", client_key(request)):
        return _register_page(request, db, raw, {}, 429, error=AUTH_ERRORS["rate_limited"])
    try:
        data = RegisterForm.model_validate(raw)
    except ValidationError as exc:
        return _register_page(request, db, raw, errors_from(exc), 422)
    errors = data.password_errors()
    if data.specialty_category_id is not None and data.specialty_category_id not in {
        c.id for c in specialty_options(db)
    }:
        errors["specialty_category_id"] = (N_("Escolhe uma opção válida."), {})
    if errors:
        return _register_page(request, db, raw, errors, 422)
    lang = request.state.lang
    try:
        if not auth_service.email_enabled():
            user = auth_service.register(
                db, str(data.email), data.password, data.invite, lang, data.profile()
            )
            return login_response(db, request, user, None)
        address = auth_service.normalize_email(str(data.email))
        if not ratelimit.hit(ratelimit.REGISTER_EMAIL, "register-email", _email_key(address)):
            return _register_page(request, db, raw, {}, 429, error=AUTH_ERRORS["rate_limited"])
        ticket = auth_service.start_registration(
            db, address, data.password, data.invite, lang, data.profile()
        )
    except AuthError as exc:
        db.rollback()
        field = "email" if exc.code in ("email_taken", "invite_email_mismatch") else "invite"
        return _register_page(request, db, raw, {field: (AUTH_ERRORS[exc.code], {})}, 422)
    db.commit()
    background.add_task(email.deliver_queued)
    return RedirectResponse(f"{lang_prefix(lang)}/register/verify?t={ticket}", status_code=303)


def _code_page(
    request: Request,
    purpose: str,
    ticket: str,
    row: Any,
    status_code: int = 200,
    errors: dict[str, Any] | None = None,
    **ctx: Any,
) -> Response:
    if row is None:
        return render(request, "auth/code_invalid.html", {"purpose": purpose}, status_code=400)
    return render(
        request,
        "auth/code.html",
        {
            "purpose": purpose,
            "reset": purpose == "reset",
            "base": _code_route(purpose),
            "ticket": ticket,
            "masked": auth_service.mask_email(row.email),
            "minutes": int(auth_service.CODE_TTL.total_seconds() // 60),
            "can_resend": row.sends < auth_service.CODE_SENDS,
            "errors": errors or {},
            **ctx,
        },
        status_code=status_code,
    )


def _code_route(purpose: str) -> str:
    return "/register" if purpose == "register" else "/forgot"


def _resend(request: Request, db: DB, purpose: str, form: Any, background: BackgroundTasks) -> Response:
    ticket = str(form.get("t") or "")
    if not ratelimit.hit(ratelimit.CODE_IP, "code", client_key(request)):
        row = auth_service.find_code(db, purpose, ticket)
        return _code_page(request, purpose, ticket, row, 429, error=AUTH_ERRORS["rate_limited"])
    sent = auth_service.resend_code(db, purpose, ticket)
    db.commit()
    if sent:
        background.add_task(email.deliver_queued)
    row = auth_service.find_code(db, purpose, ticket)
    return _code_page(request, purpose, ticket, row, resent=sent)


@pages.get("/register/verify")
def register_verify_page(request: Request, db: DB, t: str = "") -> Response:
    return _code_page(request, "register", t, auth_service.find_code(db, "register", t))


@pages.post("/register/verify")
def register_verify_submit(request: Request, db: DB, form: Form, background: BackgroundTasks) -> Response:
    ticket = str(form.get("t") or "")
    if not ratelimit.hit(ratelimit.CODE_IP, "code", client_key(request)):
        row = auth_service.find_code(db, "register", ticket)
        return _code_page(request, "register", ticket, row, 429, error=AUTH_ERRORS["rate_limited"])
    try:
        user = auth_service.complete_registration(db, ticket, str(form.get("code") or ""))
    except AuthError as exc:
        db.commit()  # keep the attempt count
        row = auth_service.find_code(db, "register", ticket)
        if exc.code in ("email_taken", "invalid_invite"):
            ctx = {"purpose": "register", "error": AUTH_ERRORS[exc.code]}
            return render(request, "auth/code_invalid.html", ctx, status_code=400)
        return _code_page(request, "register", ticket, row, 422, {"code": (AUTH_ERRORS[exc.code], {})})
    response = login_response(db, request, user, None)  # commits (with the welcome email)
    background.add_task(email.deliver_queued)
    return response


@pages.post("/register/resend")
def register_resend(request: Request, db: DB, form: Form, background: BackgroundTasks) -> Response:
    return _resend(request, db, "register", form, background)


@pages.get("/forgot")
def forgot_page(request: Request) -> Response:
    if not auth_service.email_enabled():
        raise HTTPException(status_code=404)
    return render(request, "auth/forgot.html", {"errors": {}, "email": ""})


@pages.post("/forgot")
def forgot_submit(request: Request, db: DB, form: Form, background: BackgroundTasks) -> Response:
    """Self-service reset with an emailed code (D30). Same next screen whether or not the account exists."""
    from pydantic import TypeAdapter
    from pydantic import ValidationError as PydanticValidationError
    from pydantic.networks import EmailStr

    if not auth_service.email_enabled():
        raise HTTPException(status_code=404)
    raw = str(form.get("email") or "").strip()
    try:
        address = auth_service.normalize_email(str(TypeAdapter(EmailStr).validate_python(raw)))
    except PydanticValidationError:
        return render(
            request,
            "auth/forgot.html",
            {"errors": {"email": (N_("Indica um email válido."), {})}, "email": raw},
            422,
        )
    if not (
        ratelimit.hit(ratelimit.FORGOT_IP, "forgot-ip", client_key(request))
        and ratelimit.hit(ratelimit.FORGOT_EMAIL, "forgot-email", _email_key(address))
    ):
        return render(
            request,
            "auth/forgot.html",
            {"errors": {}, "email": address, "error": AUTH_ERRORS["rate_limited"]},
            429,
        )
    ticket = auth_service.start_password_reset(db, address, request.state.lang)
    db.commit()
    background.add_task(email.deliver_queued)
    return RedirectResponse(f"{lang_prefix(request.state.lang)}/forgot/verify?t={ticket}", status_code=303)


@pages.get("/forgot/verify")
def forgot_verify_page(request: Request, db: DB, t: str = "") -> Response:
    return _code_page(request, "reset", t, auth_service.find_code(db, "reset", t))


@pages.post("/forgot/verify")
def forgot_verify_submit(request: Request, db: DB, form: Form) -> Response:
    ticket = str(form.get("t") or "")
    row = auth_service.find_code(db, "reset", ticket)
    if not ratelimit.hit(ratelimit.CODE_IP, "code", client_key(request)):
        return _code_page(request, "reset", ticket, row, 429, error=AUTH_ERRORS["rate_limited"])
    if row is None:
        return _code_page(request, "reset", ticket, None)
    password = str(form.get("password") or "")
    errors = new_password_errors(password, str(form.get("password_confirm") or ""), row.email)
    if errors:
        return _code_page(request, "reset", ticket, row, 422, errors)
    try:
        user = auth_service.complete_password_reset(db, ticket, str(form.get("code") or ""), password)
    except AuthError as exc:
        db.commit()  # keep the attempt count
        row = auth_service.find_code(db, "reset", ticket)
        return _code_page(request, "reset", ticket, row, 422, {"code": (AUTH_ERRORS[exc.code], {})})
    return login_response(db, request, user, None)


@pages.post("/forgot/resend")
def forgot_resend(request: Request, db: DB, form: Form, background: BackgroundTasks) -> Response:
    return _resend(request, db, "reset", form, background)


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
    response = RedirectResponse(f"{lang_prefix(request.state.lang)}/", status_code=303)
    response.delete_cookie(get_settings().session_cookie, path="/")
    return response


@actions.post("/auth/logout-all")
def logout_all(request: Request, db: DB, user: CurrentUser) -> Response:
    if user is not None:
        sessions.destroy_all(db, user.id)
        db.commit()
    response = RedirectResponse(f"{lang_prefix(request.state.lang)}/?flash=signed_out_all", status_code=303)
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
                errors["specialty_category_id"] = (N_("Escolhe uma opção válida."), {})
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
    target = auth_service.safe_next(raw.get("next")) or f"{lang_prefix(user.locale.value)}/"
    return RedirectResponse(target, status_code=303)
