"""Locale resolution, gettext and formatting helpers.

Message ids are written in European Portuguese (the primary language), so PT needs no
catalogue; `locales/en` holds the English translations (see docs/DECISIONS.md D11).
"""

import gettext as _gettext
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from babel import dates as babel_dates
from babel import numbers as babel_numbers
from babel.support import Translations

LANGS = ("pt", "en")
DEFAULT_LANG = "pt"
BABEL_LOCALES = {"pt": "pt_PT", "en": "en"}
HTML_LANG = {"pt": "pt-PT", "en": "en"}
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
TZ = ZoneInfo("Europe/Lisbon")
LANG_COOKIE = "gitmgf_lang"

_current: ContextVar[str] = ContextVar("gitmgf_lang", default=DEFAULT_LANG)


@lru_cache
def translations(lang: str) -> _gettext.NullTranslations:
    if lang != "en":
        return _gettext.NullTranslations()
    return Translations.load(str(LOCALES_DIR), [BABEL_LOCALES[lang]], domain="messages")


def clear_cache() -> None:
    translations.cache_clear()


def get_lang() -> str:
    return _current.get()


@contextmanager
def use_lang(lang: str) -> Iterator[None]:
    token = _current.set(lang if lang in LANGS else DEFAULT_LANG)
    try:
        yield
    finally:
        _current.reset(token)


def gettext(message: str) -> str:
    return translations(get_lang()).gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return translations(get_lang()).ngettext(singular, plural, n)


def N_(message: str) -> str:
    """Marks a string for extraction without translating it (translated at render time)."""
    return message


def t(lang: str, message: str, **variables: Any) -> str:
    text = translations(lang).gettext(message)
    return text % variables if variables else text


def negotiate(accept_language: str | None) -> str:
    """Any pt* preference -> pt, otherwise en (PRD F13)."""
    if not accept_language:
        return DEFAULT_LANG
    prefs = []
    for part in accept_language.split(","):
        bits = part.strip().split(";q=")
        tag = bits[0].strip().lower()
        try:
            q = float(bits[1]) if len(bits) > 1 else 1.0
        except ValueError:
            q = 0.0
        if tag:
            prefs.append((q, tag))
    for _q, tag in sorted(prefs, key=lambda p: -p[0]):
        if tag.startswith("pt"):
            return "pt"
        if tag.startswith("en") or tag == "*":
            return "en" if tag.startswith("en") else DEFAULT_LANG
    return "en"


def lang_from_path(path: str) -> str | None:
    for lang in LANGS:
        if path == f"/{lang}" or path.startswith(f"/{lang}/"):
            return lang
    return None


def swap_lang(path: str, lang: str) -> str:
    """Same page in another language (language switcher, hreflang)."""
    current = lang_from_path(path)
    if current is None:
        return f"/{lang}/"
    rest = path[len(current) + 1 :]
    return f"/{lang}{rest or '/'}"


def localized(obj: Any, field: str, lang: str) -> tuple[str, bool]:
    """Returns (text, is_fallback). EN falls back to PT with a flag for the "PT" pill."""
    if lang == "en":
        value = getattr(obj, f"{field}_en", None) if not isinstance(obj, dict) else obj.get(f"{field}_en")
        if value:
            return value, False
    value = getattr(obj, f"{field}_pt", None) if not isinstance(obj, dict) else obj.get(f"{field}_pt")
    return value or "", lang == "en"


def to_local(value: datetime) -> datetime:
    return value.astimezone(TZ)


def format_date(value: date | datetime | None, lang: str, fmt: str = "long") -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = to_local(value).date()
    return babel_dates.format_date(value, format=fmt, locale=BABEL_LOCALES[lang])


def format_datetime(value: datetime | None, lang: str, fmt: str = "medium") -> str:
    if value is None:
        return ""
    return babel_dates.format_datetime(to_local(value), format=fmt, locale=BABEL_LOCALES[lang], tzinfo=TZ)


def format_short_date(value: date | datetime | None, lang: str) -> str:
    """dd/mm/yyyy in PT, as used in certification tooltips."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = to_local(value).date()
    return babel_dates.format_date(
        value, format="short" if lang == "en" else "dd/MM/yyyy", locale=BABEL_LOCALES[lang]
    )


def format_number(value: float | int, lang: str) -> str:
    return babel_numbers.format_decimal(value, locale=BABEL_LOCALES[lang])


def format_relative(value: datetime | None, lang: str, now: datetime | None = None) -> str:
    if value is None:
        return ""
    now = now or datetime.now(value.tzinfo)
    return babel_dates.format_timedelta(value - now, add_direction=True, locale=BABEL_LOCALES[lang])
