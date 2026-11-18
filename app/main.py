import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from app.config import get_settings
from app.db import SessionLocal, get_engine
from app.deps import LoginRequired, OnboardingRequired, csrf_protect, load_user
from app.i18n import lang_prefix
from app.middleware import plumbing
from app.routers import admin, auth, dev, editor, me, mod, public, stats, system, tracking
from app.services import legal, settings_store
from app.templating import render

STATIC_DIR = Path(__file__).resolve().parent / "static"
log = logging.getLogger("gitmgf")


class CachedStatic(StaticFiles):
    """Static files with long-lived caching when fingerprinted with ?v=<git sha>."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if b"v=" in scope.get("query_string", b""):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
        return response


def startup_problems() -> list[str]:
    """Refuse to start in prod with unsafe config or unresolved legal placeholders (TECH_SPEC §13a)."""
    settings = get_settings()
    problems = settings.config_errors()
    if settings.is_prod:
        get_engine()
        with SessionLocal() as db:
            missing = legal.missing_placeholders(db)
            if missing:
                problems.append("Legal placeholders without value: " + ", ".join(sorted(missing)))
            version = legal.terms_version()
            current = settings_store.get(db, "terms.current_version")
            if version != current:
                problems.append(f"terms.md version {version!r} != terms.current_version {current!r}")
    return problems


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    problems = startup_problems()
    if problems:
        for problem in problems:
            log.error("config: %s", problem)
        raise RuntimeError("gitmgf refuses to start: " + "; ".join(problems))
    yield


def page_language(lang: str) -> Any:
    """Router dependency: the page's language comes from where it is mounted, not from cookies."""

    def dependency(request: Request) -> None:
        request.state.lang = lang
        request.state.page_lang = lang

    return dependency


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO if settings.app_env != "test" else logging.WARNING)
    app = FastAPI(
        title="gitmgf",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        dependencies=[Depends(csrf_protect), Depends(load_user)],
    )
    app.middleware("http")(plumbing)
    app.mount("/static", CachedStatic(directory=STATIC_DIR), name="static")
    if not settings.is_prod:
        # In prod Caddy serves /media directly (deploy/Caddyfile).
        settings.media_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

    app.include_router(system.router)
    app.include_router(tracking.router)
    modules = (public, auth, me, editor, mod, stats, admin)
    if not settings.is_prod:
        modules = (*modules, dev)
    # Pages first (D28): PT at the root, EN under /en. Without a prefix, PT pages share the path space
    # with unprefixed action routes, so pages must win (e.g. POST /me/tools/{id}/edit).
    for lang in ("en", "pt"):
        for module in modules:
            app.include_router(
                module.pages, prefix=lang_prefix(lang), dependencies=[Depends(page_language(lang))]
            )
    for module in (public, auth, me, editor, mod, stats, admin):
        app.include_router(module.actions)
    app.include_router(public.root)  # legacy /pt/… redirects
    register_error_handlers(app)
    return app


ERROR_TEMPLATES = {403: "errors/403.html", 404: "errors/404.html", 429: "errors/429.html"}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, exc: LoginRequired) -> Response:
        return RedirectResponse(
            _with_next(f"{lang_prefix(request.state.lang)}/login", exc.next_path), status_code=303
        )

    @app.exception_handler(OnboardingRequired)
    async def _onboarding_required(request: Request, exc: OnboardingRequired) -> Response:
        return RedirectResponse(
            _with_next(f"{lang_prefix(request.state.lang)}/onboarding", exc.next_path), status_code=303
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        template = ERROR_TEMPLATES.get(exc.status_code)
        if template is None:
            if exc.status_code == 405:
                template = "errors/404.html"
            else:
                return Response(status_code=exc.status_code, headers=getattr(exc, "headers", None))
        context: dict[str, Any] = {"detail": exc.detail}
        return render(request, template, context, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> Response:
        return render(request, "errors/404.html", {}, status_code=404)

    @app.exception_handler(Exception)
    async def _server_error(request: Request, exc: Exception) -> Response:
        log.exception("unhandled error rid=%s", getattr(request.state, "request_id", "-"))
        return render(request, "errors/500.html", {}, status_code=500)


def _with_next(path: str, next_path: str) -> str:
    from urllib.parse import quote

    return f"{path}?next={quote(next_path, safe='/')}"


app = create_app()
