"""Double-submit CSRF token plus Origin/Referer check (TECH_SPEC §6.4)."""

import hmac
import secrets
from urllib.parse import urlsplit

COOKIE_NAME = "gitmgf_csrf"
FORM_FIELD = "csrf_token"
HEADER = "x-csrf-token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def new_token() -> str:
    return secrets.token_urlsafe(32)


def tokens_match(cookie_token: str | None, submitted: str | None) -> bool:
    if not cookie_token or not submitted:
        return False
    return hmac.compare_digest(cookie_token.encode(), submitted.encode())


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def origin_allowed(origin: str | None, referer: str | None, allowed: set[str]) -> bool:
    """When the browser sends Origin (or Referer), it must be one of ours."""
    if origin and origin != "null":
        return origin_of(origin) in allowed
    if referer:
        return origin_of(referer) in allowed
    return True
