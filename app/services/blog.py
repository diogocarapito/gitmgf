"""Blog articles from `content/blog/{pt,en}/<slug>.md` (site-owned Markdown, like the legal pages)."""

import html as html_lib
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.services import markdown

CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "blog"
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
# Tabbed blocks:  :::tabs / ::tab Label / (markdown) / ::tab Other / ... / :::
TABS_RE = re.compile(r"^:::tabs[ \t]*\n(.*?)\n:::[ \t]*$", re.S | re.M)
TAB_RE = re.compile(r"^::tab[ \t]+(.+)$", re.M)


@dataclass(frozen=True)
class Post:
    slug: str
    lang: str  # language of the text shown (PT when there is no translation)
    title: str
    summary: str
    published: date
    author: str
    html: str
    is_fallback: bool  # an EN visitor reading the PT original


@lru_cache(maxsize=64)
def _load(path: Path, mtime: float) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    return dict(yaml.safe_load(match.group(1)) or {}), text[match.end() :]


def _post(slug: str, lang: str, requested: str) -> Post | None:
    path = CONTENT_DIR / lang / f"{slug}.md"
    if not path.is_file():
        return None
    meta, body = _load(path, path.stat().st_mtime)
    if meta.get("draft"):
        return None
    html = render_body(body)
    html = re.sub(r"\A\s*<h1>.*?</h1>\s*", "", html, flags=re.S)  # the template renders the title
    published = meta.get("date")
    return Post(
        slug=slug,
        lang=lang,
        title=str(meta.get("title") or slug),
        summary=str(meta.get("summary") or ""),
        published=published if isinstance(published, date) else date.fromisoformat(str(published)),
        author=str(meta.get("author") or "gitmgf"),
        html=html,
        is_fallback=lang != requested,
    )


def _tabs_html(block: str, index: int) -> str:
    """Each panel keeps a visible label, so without JS the tabs read as consecutive sections."""
    parts = TAB_RE.split(block)
    panels = []
    for n, (label, content) in enumerate(zip(parts[1::2], parts[2::2], strict=True)):
        label = html_lib.escape(label.strip())
        panels.append(
            f'<section class="ctabs__panel" id="tabs{index}-{n}" data-tab-label="{label}">'
            f'<p class="ctabs__label"><strong>{label}</strong></p>{markdown.render_trusted(content)}</section>'
        )
    return f'<div class="ctabs" data-tabs>{"".join(panels)}</div>'


def render_body(body: str) -> str:
    """Site-owned Markdown, plus `:::tabs` blocks rendered as progressively enhanced tabs (app.js)."""
    blocks: list[str] = []

    def stash(match: re.Match[str]) -> str:
        blocks.append(_tabs_html(match.group(1), len(blocks)))
        return f"\n\nTABSBLOCK{len(blocks) - 1}\n\n"

    rendered = markdown.render_trusted(TABS_RE.sub(stash, body))
    for i, block in enumerate(blocks):
        rendered = rendered.replace(f"<p>TABSBLOCK{i}</p>", block)
    return rendered


def get(slug: str, lang: str) -> Post | None:
    if not SLUG_RE.fullmatch(slug):
        return None
    return _post(slug, lang, lang) or (_post(slug, "pt", lang) if lang != "pt" else None)


def all_posts(lang: str) -> list[Post]:
    """Newest first. Every article exists in Portuguese; English falls back to it."""
    slugs = {p.stem for p in (CONTENT_DIR / "pt").glob("*.md")} if (CONTENT_DIR / "pt").is_dir() else set()
    posts = [post for slug in slugs if (post := get(slug, lang)) is not None]
    return sorted(posts, key=lambda p: (p.published, p.slug), reverse=True)
