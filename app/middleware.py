"""Per-request plumbing: request id, language, CSRF cookie, security headers, access log."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app import i18n
from app.config import get_settings
from app.services import csrf

log = logging.getLogger("gitmgf.access")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "frame-src 'none'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "object-src 'none'"
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
LANG_COOKIE_MAX_AGE = 365 * 24 * 3600


def request_lang(request: Request) -> str:
    """Default language for non-page routes (actions, redirects, errors). Page routes override it (D28)."""
    if i18n.is_en_path(request.url.path):
        return "en"
    referer = request.headers.get("referer")
    if referer:
        from urllib.parse import urlsplit

        parts = urlsplit(referer)
        if parts.netloc == request.url.netloc:
            return "en" if i18n.is_en_path(parts.path) else "pt"
    cookie = request.cookies.get(i18n.LANG_COOKIE)
    if cookie in i18n.LANGS:
        return cookie
    return i18n.negotiate(request.headers.get("accept-language"))


async def plumbing(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    settings = get_settings()
    started = time.perf_counter()
    request.state.request_id = uuid.uuid4().hex[:12]
    request.state.lang = request_lang(request)

    token = request.cookies.get(csrf.COOKIE_NAME)
    new_token = not token or len(token) < 20
    if new_token:
        token = csrf.new_token()
    request.state.csrf_token = token

    response = await call_next(request)

    if new_token:
        response.set_cookie(
            csrf.COOKIE_NAME,
            token or "",
            httponly=True,
            samesite="lax",
            secure=settings.secure_cookies,
            path="/",
        )
    path_lang = getattr(request.state, "page_lang", None)  # set only by page routes
    if path_lang and request.cookies.get(i18n.LANG_COOKIE) != path_lang and response.status_code < 400:
        response.set_cookie(
            i18n.LANG_COOKIE,
            path_lang,
            max_age=LANG_COOKIE_MAX_AGE,
            samesite="lax",
            secure=settings.secure_cookies,
            path="/",
        )

    headers = response.headers
    headers.setdefault("Content-Security-Policy", CSP)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    headers.setdefault("X-Frame-Options", "DENY")
    headers["X-Request-ID"] = request.state.request_id
    if headers.get("content-type", "").startswith("text/html"):
        headers.setdefault("Cache-Control", "private, no-cache")
        headers.setdefault("Vary", "Cookie, HX-Request")

    log.info(
        "%s %s %s %.1fms rid=%s",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
        request.state.request_id,
    )
    return response
