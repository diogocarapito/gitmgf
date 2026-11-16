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
from app.forms.account import MagicLinkForm, OnboardingForm
from app.forms.common import errors_from, form_to_dict
from app.i18n import N_
from app.models import Category, User
from app.models.enums import OAuthProvider
from app.services import auth as auth_service
from app.services import email, oauth, ratelimit, sessions, settings_store
from app.services.auth import AuthError
from app.templating import render

pages = APIRouter()
actions = APIRouter()

AUTH_ERRORS = {
    "invalid_link": N_("Esta ligação de acesso é inválida, já foi usada ou expirou. Peça uma nova."),
    "suspended": N_(
        "Não é possível iniciar sessão com esta conta. Contacte-nos se achar que se trata de um erro."
    ),
    "registration_closed": N_("Os novos registos estão temporariamente fechados."),
    "unverified_email": N_(
        "O email desta conta não está verificado no fornecedor. Use a ligação por email para entrar."
    ),
    "provider_taken": N_("Essa conta já está associada a outro utilizador da gitmgf."),
    "oauth_state": N_("A autenticação expirou ou é inválida. Tente novamente."),
    "oauth_failed": N_("Não foi possível concluir a autenticação. Tente novamente."),
    "rate_limited": N_("Demasiados pedidos. Aguarde um pouco e tente novamente."),
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
    settings = get_settings()
    return render(
        request,
        "auth/login.html",
        {
            "next": auth_service.safe_next(next_path) or "",
            "github_enabled": settings.github_enabled,
            "google_enabled": settings.google_enabled,
            **ctx,
        },
        status_code=status_code,
    )


@pages.get("/login")
def login_page(
    request: Request, user: CurrentUser, next: str | None = None, error: str | None = None
) -> Response:
    if user is not None:
        return RedirectResponse(auth_service.safe_next(next) or f"/{request.state.lang}/", status_code=303)
    message = AUTH_ERRORS.get(error or "")
    return _login_page(request, next, error=message)


@actions.post("/auth/magic-link")
def magic_link(request: Request, db: DB, form: Form, background: BackgroundTasks) -> Response:
    lang = request.state.lang
    try:
        data = MagicLinkForm.model_validate(form_to_dict(form))
    except ValidationError as exc:
        errors = errors_from(exc)
        raw_next = form.get("next")
        return render(
            request,
            "auth/login.html",
            {
                "next": auth_service.safe_next(raw_next if isinstance(raw_next, str) else None) or "",
                "errors": errors,
                "email": form.get("email", ""),
                "github_enabled": get_settings().github_enabled,
                "google_enabled": get_settings().google_enabled,
            },
            status_code=422,
        )
    address = auth_service.normalize_email(str(data.email))
    email_key = hashlib.sha256(address.encode()).hexdigest()[:16]
    allowed = ratelimit.hit(ratelimit.MAGIC_LINK_IP, "magic-ip", client_key(request)) and ratelimit.hit(
        ratelimit.MAGIC_LINK_EMAIL, "magic-email", email_key
    )
    if allowed:
        auth_service.request_magic_link(db, address, data.next, lang)
        db.commit()
        background.add_task(email.deliver_queued)
    # Identical response whether or not the account exists or the limit was hit (no enumeration).
    return render(request, "auth/check_email.html", {"email": address})


@actions.get("/auth/magic/{token}")
def magic_confirm(request: Request, db: DB, token: str) -> Response:
    """Shows a POST button: link-prefetching scanners must not consume the token (D7)."""
    row = auth_service.find_magic_token(db, token)
    if row is None:
        return render(request, "auth/magic_invalid.html", {}, status_code=400)
    return render(request, "auth/magic_confirm.html", {"token": token})


@actions.post("/auth/magic/{token}")
def magic_consume(request: Request, db: DB, token: str) -> Response:
    try:
        user, next_path, _created = auth_service.consume_magic_token(db, token, request.state.lang)
        return login_response(db, request, user, next_path)
    except AuthError as exc:
        db.rollback()
        if exc.code == "invalid_link":
            return render(request, "auth/magic_invalid.html", {}, status_code=400)
        return _login_page(request, None, error=AUTH_ERRORS.get(exc.code), status_code=403)


def _provider(name: str) -> OAuthProvider:
    try:
        provider = OAuthProvider(name)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    if not oauth.enabled(provider):
        raise HTTPException(status_code=404)
    return provider


@actions.get("/auth/{provider_name}/start")
def oauth_start(
    request: Request, user: CurrentUser, provider_name: str, next: str | None = None, link: int = 0
) -> Response:
    provider = _provider(provider_name)
    if link and user is None:
        raise LoginRequired(request.url.path)
    url, cookie = oauth.start(provider, auth_service.safe_next(next), request.state.lang, bool(link and user))
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        oauth.COOKIE_NAME,
        cookie,
        max_age=oauth.COOKIE_MAX_AGE,
        httponly=True,
        secure=get_settings().secure_cookies,
        samesite="lax",
        path="/auth/",
    )
    return response


@actions.get("/auth/{provider_name}/callback")
def oauth_callback(
    request: Request,
    db: DB,
    user: CurrentUser,
    provider_name: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    provider = _provider(provider_name)
    lang = request.state.lang

    def fail(code_: str) -> Response:
        response = RedirectResponse(f"/{lang}/login?error={code_}", status_code=303)
        response.delete_cookie(oauth.COOKIE_NAME, path="/auth/")
        return response

    if not ratelimit.hit(ratelimit.LOGIN_CALLBACK_IP, "oauth-cb", client_key(request)):
        return fail("rate_limited")
    try:
        data = oauth.read_state(request.cookies.get(oauth.COOKIE_NAME), provider, state)
        if error or not code:
            raise AuthError("oauth_failed")
        with oauth.http_client() as client:
            access_token = oauth.exchange_code(provider, code, data["v"], client)
            profile = oauth.fetch_profile(provider, access_token, client)
        lang = data.get("l") or lang
        link_to = user if data.get("k") and user is not None else None
        account_user, _created = auth_service.oauth_login(db, profile, lang, link_to=link_to)
        if link_to is not None:
            db.commit()
            response: Response = RedirectResponse(
                f"/{link_to.locale.value}/me/settings?flash=linked", status_code=303
            )
        else:
            response = login_response(db, request, account_user, data.get("n"))
    except AuthError as exc:
        db.rollback()
        if exc.code == "provider_taken" and user is not None:
            return RedirectResponse(f"/{user.locale.value}/me/settings?flash=provider_taken", status_code=303)
        return fail(exc.code)
    response.delete_cookie(oauth.COOKIE_NAME, path="/auth/")
    return response


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
