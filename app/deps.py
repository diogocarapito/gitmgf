"""FastAPI dependencies shared by routers."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.services import auth as auth_service
from app.services import csrf, permissions, sessions, settings_store

DB = Annotated[Session, Depends(get_db)]


class LoginRequired(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


class OnboardingRequired(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


def load_user(request: Request, db: DB) -> User | None:
    """Global dependency: resolves the session cookie and the site banner once per request."""
    if hasattr(request.state, "user"):
        return request.state.user  # type: ignore[no-any-return]
    token = request.cookies.get(get_settings().session_cookie)
    row = sessions.load(db, token) if token else None
    request.state.user = row.user if row else None
    request.state.session_id = row.id if row else None
    lang = getattr(request.state, "lang", "pt")
    request.state.banner = settings_store.get(db, f"site.banner_{lang}") or ""
    return request.state.user  # type: ignore[no-any-return]


CurrentUser = Annotated[User | None, Depends(load_user)]


def _next(request: Request) -> str:
    return request.url.path + (f"?{request.url.query}" if request.url.query else "")


def require_user(request: Request, db: DB, user: CurrentUser) -> User:
    if user is None:
        if request.method != "GET":
            raise HTTPException(status_code=403)
        raise LoginRequired(_next(request))
    if auth_service.needs_onboarding(db, user) and request.method == "GET":
        raise OnboardingRequired(_next(request))
    return user


def require_moderator(user: Annotated[User, Depends(require_user)]) -> User:
    if not permissions.is_moderator(user):
        raise HTTPException(status_code=404)
    return user


def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if not permissions.can_admin(user):
        raise HTTPException(status_code=404)
    return user


UserDep = Annotated[User, Depends(require_user)]
ModDep = Annotated[User, Depends(require_moderator)]
AdminDep = Annotated[User, Depends(require_admin)]


async def get_form(request: Request) -> FormData:
    """Parsed once and cached by Starlette, so the CSRF check and the handler share it."""
    return await request.form()


Form = Annotated[FormData, Depends(get_form)]


def allowed_origins(request: Request) -> set[str]:
    settings = get_settings()
    origins = {csrf.origin_of(settings.base_url)}
    if not settings.is_prod:
        origins.add(csrf.origin_of(str(request.base_url)))
    return origins


async def csrf_protect(request: Request) -> None:
    """Global dependency: every unsafe request needs a matching token and a same-site origin."""
    if request.method not in csrf.UNSAFE_METHODS:
        return
    cookie_token = request.cookies.get(csrf.COOKIE_NAME)
    submitted = request.headers.get(csrf.HEADER)
    if not submitted:
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            form = await request.form(max_part_size=1024 * 1024)
            value = form.get(csrf.FORM_FIELD)
            submitted = value if isinstance(value, str) else None
    if not csrf.tokens_match(cookie_token, submitted):
        raise HTTPException(status_code=403, detail="csrf")
    if not csrf.origin_allowed(
        request.headers.get("origin"), request.headers.get("referer"), allowed_origins(request)
    ):
        raise HTTPException(status_code=403, detail="origin")
