"""Blog articles from `content/blog/<slug>.md` and `<slug>_en.md` (site-owned Markdown, like the legal pages, D37)."""

import html as html_lib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.services import content, markdown

CONTENT_DIR = content.ROOT / "blog"
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
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


def _path(slug: str, lang: str) -> Path:
    return CONTENT_DIR / f"{slug}{content.EN_SUFFIX if lang == 'en' else ''}.md"


def _post(slug: str, lang: str, requested: str) -> Post | None:
    path = _path(slug, lang)
    if not path.is_file():
        return None
    meta, body = content.read(path)
    if str(meta.get("draft", "")).lower() in ("true", "yes", "sim"):
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
    for n, (label, panel) in enumerate(zip(parts[1::2], parts[2::2], strict=True)):
        label = html_lib.escape(label.strip())
        panels.append(
            f'<section class="ctabs__panel" id="tabs{index}-{n}" data-tab-label="{label}">'
            f'<p class="ctabs__label"><strong>{label}</strong></p>{markdown.render_trusted(panel)}</section>'
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
    slugs = {p.stem for p in CONTENT_DIR.glob("*.md") if SLUG_RE.fullmatch(p.stem)}  # skips `_en` files
    posts = [post for slug in slugs if (post := get(slug, lang)) is not None]
    return sorted(posts, key=lambda p: (p.published, p.slug), reverse=True)
