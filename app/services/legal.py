"""Legal and static pages from `content/` (TECH_SPEC §13a, D37): `about/about.md`, `legal/terms.md`... plus `_en.md`."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services import content, markdown, settings_store

# /p/<page> -> content file (without `.md` / `_en.md`)
PAGES = {
    "about": "about/about",
    "contact": "contact/contact",
    "terms": "legal/terms",
    "privacy": "legal/privacy",
    "disclaimer": "legal/disclaimer",
    "guidelines": "legal/guidelines",
}
PLACEHOLDER_RE = re.compile(r"\[\[([A-Z0-9_]+)\]\]")


@dataclass(frozen=True)
class LegalPage:
    slug: str
    lang: str
    title: str
    version: str | None
    last_updated: str | None
    html: str
    is_translation: bool


def page_path(page: str, lang: str) -> Path:
    return content.path_for(PAGES[page], lang)


def read(page: str, lang: str) -> tuple[dict[str, Any], str, str] | None:
    """(front matter, body, language shown): English falls back to the Portuguese original."""
    found = content.resolve(PAGES[page], lang) if page in PAGES else None
    if found is None:
        return None
    path, actual = found
    meta, body = content.read(path)
    return meta, body, actual


def fill(body: str, values: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), body)


_render_cache: dict[tuple[str, str, str], LegalPage] = {}


def render_page(db: Session, page: str, lang: str) -> LegalPage | None:
    loaded = read(page, lang)
    if loaded is None:
        return None
    meta, body, actual = loaded
    values = settings_store.legal_values(db)
    key = (page, actual, hashlib.sha256((repr(sorted(values.items())) + body).encode()).hexdigest())
    if key not in _render_cache:
        title = str(meta.get("title") or page)
        html = markdown.render_trusted(fill(body, values))
        # The page title is rendered by the template; drop a leading H1 duplicate.
        html = re.sub(r"\A\s*<h1>.*?</h1>\s*", "", html, flags=re.S)
        _render_cache[key] = LegalPage(
            slug=page,
            lang=actual,
            title=title,
            version=str(meta["version"]) if meta.get("version") else None,
            last_updated=str(meta["last_updated"]) if meta.get("last_updated") else None,
            html=html,
            is_translation=actual != "pt",
        )
    return _render_cache[key]


def placeholders_in_content() -> set[str]:
    found: set[str] = set()
    for name in PAGES.values():
        for path in (content.path_for(name, "pt"), content.path_for(name, "en")):
            if path.is_file():
                found.update(PLACEHOLDER_RE.findall(path.read_text(encoding="utf-8")))
    return found


def missing_placeholders(db: Session) -> set[str]:
    values = settings_store.legal_values(db)
    missing = set()
    for key in placeholders_in_content():
        value = values.get(key)
        if value is None or (value == "" and key not in settings_store.LEGAL_OPTIONAL):
            missing.add(key)
    return missing


def terms_version() -> str | None:
    loaded = read("terms", "pt")
    if loaded is None:
        return None
    version = loaded[0].get("version")
    return str(version) if version else None
