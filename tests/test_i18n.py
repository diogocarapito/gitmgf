import subprocess
import sys
from pathlib import Path

import pytest

from app import i18n
from tests.factories import make_tool

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("accept", "expected"),
    [
        ("pt-PT,pt;q=0.9", None),
        ("pt-BR", None),
        ("en-GB,en;q=0.8", "/en/"),
        ("fr-FR", "/en/"),
        ("fr, pt;q=0.5", None),
        (None, None),
    ],
)
def test_first_visit_to_root_follows_accept_language(client, accept, expected):
    """D28: PT lives at the root; only a first visit from an English browser is sent to /en/."""
    headers = {"accept-language": accept} if accept else {}
    r = client.get("/", headers=headers)
    if expected is None:
        assert r.status_code == 200 and '<html lang="pt-PT">' in r.text
    else:
        assert r.status_code == 302 and r.headers["location"] == expected


def test_choosing_pt_sticks_even_for_english_browsers(client):
    client.get("/search")  # a PT page remembers PT
    r = client.get("/", headers={"accept-language": "en-GB"})
    assert r.status_code == 200 and '<html lang="pt-PT">' in r.text


def test_english_choice_is_remembered_but_root_stays_pt(client):
    client.get("/en/")  # remembers EN in the cookie
    r = client.get("/", headers={"accept-language": "en-GB"})
    assert r.status_code == 200  # an explicit visit to the PT home is never bounced


def test_pt_urls_have_no_prefix_and_old_pt_urls_redirect(client):
    assert 'href="/search"' in client.get("/").text
    assert 'href="/en/search"' in client.get("/en/").text
    r = client.get("/pt/p/terms?x=1")
    assert r.status_code == 301 and r.headers["location"] == "/p/terms?x=1"
    assert client.get("/pt").headers["location"] == "/"


def test_html_lang_and_hreflang(client):
    r = client.get("/search")
    assert '<html lang="pt-PT">' in r.text
    assert 'hreflang="en" href="http://testserver/en/search"' in r.text
    assert 'hreflang="x-default"' in r.text
    r = client.get("/en/search")
    assert '<html lang="en">' in r.text and "Explore tools" in r.text


def test_language_switcher_keeps_page(client):
    r = client.get("/p/privacy")
    assert 'href="/en/p/privacy"' in r.text


def test_pt_fallback_pill_when_no_english_text(client, db):
    tool = make_tool(db, title_pt="Só em português", title_en=None, summary_en=None)
    r = client.get(f"/en/t/{tool.slug}")
    assert r.status_code == 200
    assert 'class="lang-pill"' in r.text
    r = client.get(f"/t/{tool.slug}")
    assert "lang-pill" not in r.text.split("<main")[1].split("Detalhes")[0]


def test_unknown_language_prefix_is_404(client):
    assert client.get("/fr/").status_code == 404


def test_dates_are_formatted_in_european_portuguese():
    from datetime import date

    assert i18n.format_date(date(2026, 11, 16), "pt") == "16 de novembro de 2026"
    assert i18n.format_short_date(date(2028, 5, 1), "pt") == "01/05/2028"


def test_english_catalogue_is_complete():
    """Every msgid extracted from code and templates must have an EN translation, none fuzzy."""
    from babel.messages.pofile import read_po

    po = ROOT / "app" / "locales" / "en" / "LC_MESSAGES" / "messages.po"
    pot = ROOT / "app" / "locales" / "messages.pot"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "babel.messages.frontend",
            "extract",
            "-F",
            "babel.cfg",
            "-k",
            "N_",
            "-k",
            "t:2",
            "--no-location",
            "-o",
            str(pot),
            ".",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    with pot.open("rb") as f:
        template = read_po(f)
    with po.open("rb") as f:
        catalog = read_po(f)
    missing = [m.id for m in template if m.id and (catalog.get(m.id) is None or not catalog.get(m.id).string)]
    fuzzy = [m.id for m in catalog if m.id and m.fuzzy]
    assert not missing, f"{len(missing)} untranslated, e.g. {missing[:5]}"
    assert not fuzzy, f"fuzzy entries: {fuzzy[:5]}"
