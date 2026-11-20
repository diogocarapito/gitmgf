"""Site texts edited as Markdown under `content/` (D37).

Every text lives in `content/<page>/<name>.md` (Portuguese, prevails) with its English translation next to it in
`<name>_en.md`. A missing translation falls back to Portuguese at runtime; `tests/test_content.py` fails CI first.
An optional front matter between `---` lines holds short fields, one `field: value` per line (everything after
the first colon is the value, no quoting needed); the body is Markdown.
"""

import html
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from markupsafe import Markup

from app.services import markdown

ROOT = Path(__file__).resolve().parents[2] / "content"
EN_SUFFIX = "_en"
DOC_FILES = {"README.md", "NOTES.md"}  # notes for editors, never published
NAME_RE = re.compile(r"[a-z0-9_-]+(?:/[a-z0-9_-]+)*")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
VALUE_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def path_for(name: str, lang: str) -> Path:
    """`home/hero` -> content/home/hero.md (pt) or content/home/hero_en.md (en)."""
    return ROOT / f"{name}{EN_SUFFIX if lang == 'en' else ''}.md"


def resolve(name: str, lang: str) -> tuple[Path, str] | None:
    """The file to show and its language: the translation when it exists, otherwise the Portuguese original."""
    if not NAME_RE.fullmatch(name):
        return None
    for candidate in dict.fromkeys((lang, "pt")):
        path = path_for(name, candidate)
        if path.is_file():
            return path, candidate
    return None


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if not sep or not key.strip() or key.lstrip().startswith("#"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]  # quotes are optional, as in the older YAML front matter
        meta[key.strip()] = value
    return meta, text[match.end() :]


@lru_cache(maxsize=256)
def _read(path: Path, mtime: float) -> tuple[dict[str, Any], str]:
    return split_front_matter(path.read_text(encoding="utf-8"))


def read(path: Path) -> tuple[dict[str, Any], str]:
    """Front matter and body, re-read when the file changes."""
    return _read(path, path.stat().st_mtime)


@lru_cache(maxsize=256)
def _html(path: Path, mtime: float) -> str:
    return markdown.render_trusted(_read(path, mtime)[1])


@dataclass(frozen=True)
class Block:
    """One text block for a template: `{{ b.title }}` reads the front matter, `{{ b.html }}` the body."""

    name: str
    lang: str
    meta: dict[str, Any]
    html: Markup

    def __getitem__(self, key: str) -> Any:  # Jinja falls back to item access for b.title, b.icon...
        return self.meta.get(key, "")

    @property
    def inline(self) -> Markup:
        """The body without its paragraph wrapper, for text that sits inside an existing <p> or <h1>."""
        match = re.fullmatch(r"\s*<p>(.*?)</p>\s*", str(self.html), re.S)
        return Markup(match.group(1)) if match else self.html  # noqa: S704 - sanitised Markdown


def block(name: str, lang: str, /, **values: Any) -> Block:
    """Loads a text block; `{{ key }}` in the body is replaced by the escaped value passed here."""
    found = resolve(name, lang)
    if found is None:
        raise FileNotFoundError(f"content/{name}.md")
    path, actual = found
    mtime = path.stat().st_mtime
    rendered = _html(path, mtime)
    if values:
        rendered = VALUE_RE.sub(
            lambda m: html.escape(str(values[m.group(1)])) if m.group(1) in values else m.group(0), rendered
        )
    return Block(name=name, lang=actual, meta=_read(path, mtime)[0], html=Markup(rendered))  # noqa: S704


def originals() -> list[Path]:
    """Every Portuguese source file (the ones that need an `_en.md` next to them)."""
    return sorted(p for p in ROOT.rglob("*.md") if p.name not in DOC_FILES and not p.stem.endswith(EN_SUFFIX))


def missing_translations() -> list[Path]:
    return [p for p in originals() if not p.with_name(f"{p.stem}{EN_SUFFIX}.md").is_file()]
