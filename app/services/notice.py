"""First-visit notice (D38): before browsing, visitors acknowledge that listed tools are their authors' sole
responsibility and that gitmgf only shows what each author published. Text in content/notice/notice.md."""

from app.services import legal

COOKIE = "gitmgf_notice"
MAX_AGE = 365 * 24 * 3600
# Pages the notice links to stay readable before accepting.
EXEMPT_PAGES = ("/p/terms", "/p/privacy", "/p/disclaimer")


def version() -> str:
    """Accepting is tied to the Terms version, so a new version asks again."""
    return legal.terms_version() or "1"


def is_needed(cookie: str | None, signed_in: bool, path: str) -> bool:
    """Signed-in users accepted the Terms when they registered."""
    if signed_in or cookie == version():
        return False
    return not path.removeprefix("/en").startswith(EXEMPT_PAGES)
