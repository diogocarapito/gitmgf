import re
from pathlib import Path

import pytest

from app.services import content
from app.templating import TEMPLATES_DIR, render_email

LITERAL_NAME_RE = re.compile(r'site_text\(\s*"([^"]+)"\s*(?:[,)]|if\b)')
INDIRECT_NAMES = [
    "onboarding/welcome",
    "home/create",
    "home/share",
    "home/collaborate",
    "home/step-1",
    "home/step-2",
    "home/step-3",
]


def test_every_text_has_an_english_translation():
    missing = [str(p.relative_to(content.ROOT)) for p in content.missing_translations()]
    assert not missing, f"Add the _en.md translation for: {missing}"


def test_every_text_used_by_a_template_exists():
    names = set(INDIRECT_NAMES)  # built with ~ or a conditional in the template
    for template in TEMPLATES_DIR.rglob("*.html"):
        names.update(LITERAL_NAME_RE.findall(template.read_text(encoding="utf-8")))
    assert {"home/hero", "suggest/intro", "onboarding/welcome"} <= names
    for name in sorted(names):
        for lang in ("pt", "en"):
            assert content.block(name, lang).lang == lang, f"content/{name} ({lang})"


@pytest.mark.parametrize("lang", ["pt", "en"])
def test_every_email_renders(lang):
    context = {"title": "Calc", "reason": "R", "name": "Ana", "code": "123456", "link": "https://x/l"}
    emails = [p.stem for p in (content.ROOT / "emails").glob("*.md") if not p.stem.endswith("_en")]
    assert "tool_approved" in emails and len(emails) > 20
    for name in emails:
        if name.startswith("_"):
            continue
        subject, text, _html = render_email(name, context, lang)
        assert subject and text.strip() and "{{" not in text + subject and "{%" not in text + subject, name


def test_home_reads_its_texts_from_content(client):
    for prefix, lang in (("", "pt"), ("/en", "en")):
        page = client.get(f"{prefix}/").text
        hero = content.block("home/hero", lang)
        assert hero.meta["title"] in page and str(hero.inline) in page
        assert content.block("home/create", lang).meta["title"] in page


def _write(root: Path, name: str, text: str) -> None:
    path = root / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_front_matter_needs_no_quotes_and_values_are_escaped(tmp_path, monkeypatch):
    monkeypatch.setattr(content, "ROOT", tmp_path)
    _write(
        tmp_path,
        "page/block",
        '---\ntitle: Criar: partilhar\nicon: "send"\n---\nOlá {{ name }}, **bem-vindo/a**.\n',
    )
    b = content.block("page/block", "pt", name="<b>Ana</b>")
    assert b["title"] == "Criar: partilhar" and b["icon"] == "send" and b["missing"] == ""
    assert str(b.inline) == "Olá &lt;b&gt;Ana&lt;/b&gt;, <strong>bem-vindo/a</strong>."


def test_english_falls_back_to_portuguese_and_edits_are_picked_up(tmp_path, monkeypatch):
    monkeypatch.setattr(content, "ROOT", tmp_path)
    _write(tmp_path, "page/only-pt", "Primeira versão.\n")
    b = content.block("page/only-pt", "en")
    assert b.lang == "pt" and "Primeira versão." in b.html
    assert [p.name for p in content.missing_translations()] == ["only-pt.md"]
    _write(tmp_path, "page/only-pt_en", "First version.\n")
    assert content.block("page/only-pt", "en").lang == "en" and content.missing_translations() == []


def test_unsafe_or_unknown_names_are_rejected():
    for name in ("../app/config", "home/Hero", "home/nao-existe"):
        with pytest.raises(FileNotFoundError):
            content.block(name, "pt")
