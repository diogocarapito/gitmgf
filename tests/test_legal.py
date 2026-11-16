import re

import pytest

from app.services import gdpr, legal, settings_store

ALL_LEGAL = {key: f"valor-{key.lower()}" for key in settings_store.LEGAL_KEYS}


def test_every_placeholder_has_a_setting_key():
    known = set(settings_store.LEGAL_KEYS) | {"AUTO_HIDE_THRESHOLD"}
    assert legal.placeholders_in_content() <= known


def test_terms_version_matches_current_setting():
    assert legal.terms_version() == settings_store.DEFAULTS["terms.current_version"]


@pytest.mark.parametrize("page", legal.PAGES)
@pytest.mark.parametrize("lang", ["pt", "en"])
def test_pages_render(client, page, lang):
    r = client.get(f"{'/en' if lang == 'en' else ''}/p/{page}")
    assert r.status_code == 200
    if lang == "en":
        assert "prevalece a versão em português" in r.text or "Portuguese version prevails" in r.text


def test_placeholders_are_filled_and_threshold_comes_from_settings(client, db, monkeypatch):
    for key, value in ALL_LEGAL.items():
        monkeypatch.setenv(f"LEGAL_{key}", value)
    settings_store.set_value(db, "reports.auto_hide_threshold", 4, None)
    db.commit()
    html = client.get("/p/terms").text
    assert "[[" not in html
    assert "valor-controller_name" in html
    assert legal.missing_placeholders(db) == set()


def test_missing_placeholders_block_prod_start(db, monkeypatch):
    from app import main
    from app.config import get_settings

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("BASE_URL", "https://gitmgf.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    get_settings.cache_clear()
    try:
        problems = main.startup_problems()
        assert any("Legal placeholders" in p for p in problems)
        for key, value in ALL_LEGAL.items():
            monkeypatch.setenv(f"LEGAL_{key}", value)
        settings_store.invalidate()
        assert main.startup_problems() == []
    finally:
        monkeypatch.setenv("APP_ENV", "test")
        get_settings.cache_clear()


def test_retention_matches_privacy_policy():
    text = (legal.CONTENT_DIR / "pt" / "privacy.md").read_text(encoding="utf-8")
    section = text[text.index("## 9.") : text.index("## 10.")]
    assert "180 dias" in section and gdpr.EVENTS_RETENTION.days == 180
    assert "30 dias" in section and gdpr.PURGE_AFTER.days == 30 and gdpr.OUTBOX_RETENTION.days == 30
    assert "48 horas" in section and "3 dias" in section and gdpr.MAGIC_LINK_RETENTION.days == 3
    assert "2 anos" in section and gdpr.REPORT_RETENTION.days == 730
    assert "3 anos" in section and gdpr.AUDIT_RETENTION.days == 3 * 365
    assert re.search(r"Até 30 dias sem atividade", section)


def test_security_txt(client, monkeypatch):
    assert client.get("/.well-known/security.txt").status_code == 404
    monkeypatch.setenv("LEGAL_SECURITY_EMAIL", "seguranca@gitmgf.com")
    r = client.get("/.well-known/security.txt")
    assert "Contact: mailto:seguranca@gitmgf.com" in r.text and "Expires:" in r.text


def test_robots_and_sitemap(client, db):
    from tests.factories import make_tool

    tool = make_tool(db)
    assert "Disallow: /go/" in client.get("/robots.txt").text
    xml = client.get("/sitemap.xml").text
    assert f"/t/{tool.slug}" in xml and 'hreflang="en"' in xml
    feed = client.get("/feed.xml")
    assert feed.headers["content-type"].startswith("application/atom+xml") and tool.title_pt in feed.text


def test_security_headers(client):
    r = client.get("/")
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_no_inline_scripts_or_styles_in_templates():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app" / "templates"
    for path in root.rglob("*.html"):
        if path.parts[-2] == "emails":
            continue  # email clients need inline styles; never served under the site CSP
        content = path.read_text(encoding="utf-8")
        assert "<script>" not in content and not re.search(r"<script(?![^>]*\ssrc=)", content), path
        assert " style=" not in content, path
        assert "hx-on" not in content, path


def test_password_inputs_share_the_text_input_style():
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "app.css").read_text()
    rule = next(line for line in css.splitlines() if 'input[type="text"]' in line and "{" in line)
    assert 'input[type="password"]' in rule


def test_theme_toggle_is_rendered_and_safe_without_js(client):
    html = client.get("/").text
    assert "data-theme-toggle hidden" in html  # app.js reveals it; no JS → no dead button
    assert "/static/js/theme.js" in html.split("</head>")[0]  # applied before first paint
    assert 'class="logo--light"' in html and 'class="logo--dark"' in html
    css = client.get("/static/css/app.css").text
    assert ':root[data-theme="dark"] {' in css and ':root:not([data-theme="light"])' in css
