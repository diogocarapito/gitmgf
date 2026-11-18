"""In-memory rate limits (single app host; each uvicorn worker keeps its own window)."""

from limits import parse, storage, strategies

_storage = storage.MemoryStorage()
_limiter = strategies.MovingWindowRateLimiter(_storage)

LOGIN_EMAIL = "10 per 15 minutes"
LOGIN_IP = "30 per 15 minutes"
REGISTER_IP = "10/hour"
REGISTER_EMAIL = "3/hour"  # codes emailed per address
CODE_IP = "30 per 15 minutes"  # code entries and resends
PASSWORD_CHANGE_USER = "10/hour"  # noqa: S105 - a rate, not a secret
FORGOT_EMAIL = "3/hour"
FORGOT_IP = "10/hour"
REPORTS_VISITOR = "10/day"
SUGGEST_USER = "10/day"
SUGGEST_USER_TOOL = "3/day"
TOOL_CREATE_USER = "10/day"
STAR_USER = "60/minute"
SEARCH_IP = "120/minute"
UPLOAD_USER = "60/hour"


def hit(rate: str, *identifiers: str) -> bool:
    """Counts one hit; returns False when the limit is exceeded."""
    return bool(_limiter.hit(parse(rate), *identifiers))


def reset() -> None:
    _storage.reset()
