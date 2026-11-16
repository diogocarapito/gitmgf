"""In-memory rate limits (single app host; each uvicorn worker keeps its own window)."""

from limits import parse, storage, strategies

_storage = storage.MemoryStorage()
_limiter = strategies.MovingWindowRateLimiter(_storage)

MAGIC_LINK_EMAIL = "5/hour"
MAGIC_LINK_IP = "20/hour"
REPORTS_VISITOR = "10/day"
TOOL_CREATE_USER = "10/day"
STAR_USER = "60/minute"
SEARCH_IP = "120/minute"
LOGIN_CALLBACK_IP = "30/minute"
UPLOAD_USER = "60/hour"


def hit(rate: str, *identifiers: str) -> bool:
    """Counts one hit; returns False when the limit is exceeded."""
    return bool(_limiter.hit(parse(rate), *identifiers))


def reset() -> None:
    _storage.reset()
