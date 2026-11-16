"""Legal and static pages from `content/legal/{pt,en}/*.md` (TECH_SPEC §13a)."""

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.services import markdown, settings_store

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "legal"
PAGES = ("about", "terms", "privacy", "disclaimer", "guidelines", "contact")
PLACEHOLDER_RE = re.compile(r"\[\[([A-Z0-9_]+)\]\]")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


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
    return CONTENT_DIR / lang / f"{page}.md"


@lru_cache(maxsize=64)
def _read(path: Path, mtime: float) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    return dict(meta), text[match.end() :]


def read(page: str, lang: str) -> tuple[dict[str, Any], str] | None:
    path = page_path(page, lang)
    if page not in PAGES or not path.is_file():
        return None
    return _read(path, path.stat().st_mtime)


def fill(body: str, values: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), body)


_render_cache: dict[tuple[str, str, str], LegalPage] = {}


def render_page(db: Session, page: str, lang: str) -> LegalPage | None:
    loaded = read(page, lang)
    if loaded is None:
        return None
    meta, body = loaded
    values = settings_store.legal_values(db)
    key = (page, lang, hashlib.sha256((repr(sorted(values.items())) + body).encode()).hexdigest())
    if key not in _render_cache:
        title = str(meta.get("title") or page)
        html = markdown.render_trusted(fill(body, values))
        # The page title is rendered by the template; drop a leading H1 duplicate.
        html = re.sub(r"\A\s*<h1>.*?</h1>\s*", "", html, flags=re.S)
        _render_cache[key] = LegalPage(
            slug=page,
            lang=lang,
            title=title,
            version=str(meta["version"]) if meta.get("version") else None,
            last_updated=str(meta["last_updated"]) if meta.get("last_updated") else None,
            html=html,
            is_translation=lang != "pt",
        )
    return _render_cache[key]


def placeholders_in_content() -> set[str]:
    found: set[str] = set()
    for path in CONTENT_DIR.glob("*/*.md"):
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
