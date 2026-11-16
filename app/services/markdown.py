"""Markdown rendering: CommonMark without raw HTML, then sanitised with nh3 (TECH_SPEC §16 XSS)."""

import html
import re

import nh3
from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(["table", "strikethrough", "linkify"])

ALLOWED_TAGS = {
    "p", "br", "hr", "strong", "em", "del", "s", "code", "pre", "blockquote",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "a",
    "table", "thead", "tbody", "tr", "th", "td",
}  # fmt: skip
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}, "th": {"align"}, "td": {"align"}, "ol": {"start"}}
URL_SCHEMES = {"http", "https", "mailto"}
USER_LINK_REL = "nofollow ugc noopener noreferrer"


def render(source: str) -> str:
    """User content (tool descriptions)."""
    if not source:
        return ""
    return nh3.clean(
        _md.render(source),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=URL_SCHEMES,
        link_rel=USER_LINK_REL,
    )


def render_trusted(source: str) -> str:
    """Site-owned content (legal pages): same sanitiser, headings get anchors, links stay followable."""
    rendered = nh3.clean(
        _md.render(source),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=URL_SCHEMES,
        link_rel=None,
    )
    return re.sub(r"<h([23])>(.*?)</h\1>", _heading_with_id, rendered)


def _heading_with_id(match: re.Match[str]) -> str:
    level, inner = match.group(1), match.group(2)
    text = html.unescape(re.sub(r"<[^>]+>", "", inner))
    slug = re.sub(r"[^\w]+", "-", text.lower()).strip("-")
    return f'<h{level} id="{html.escape(slug)}">{inner}</h{level}>'


def to_text(source: str) -> str:
    """Plain text for the search index and summaries."""
    if not source:
        return ""
    stripped = nh3.clean(_md.render(source), tags=set())
    return re.sub(r"\s+", " ", html.unescape(stripped)).strip()
