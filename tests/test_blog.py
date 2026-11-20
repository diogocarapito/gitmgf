from app.services import blog

SLUG = "como-criei-o-gitmgf"


def test_every_article_exists_in_both_languages_with_front_matter():
    pt = {p.slug for p in blog.all_posts("pt")}
    assert SLUG in pt
    for slug in pt:
        for lang in ("pt", "en"):
            post = blog.get(slug, lang)
            assert post and not post.is_fallback and post.title and post.summary and post.published


def test_blog_index_and_article_render_in_both_languages(client):
    index = client.get("/blog")
    assert index.status_code == 200 and f'href="/blog/{SLUG}"' in index.text
    page = client.get(f"/blog/{SLUG}")
    assert page.status_code == 200 and "Claude Code" in page.text and "<pre>" in page.text
    en = client.get(f"/en/blog/{SLUG}")
    assert en.status_code == 200 and "How I built gitmgf in a day" in en.text
    assert f'href="/en/blog/{SLUG}"' in client.get("/en/blog").text


def test_unknown_or_unsafe_slugs_are_404(client):
    for slug in ("nao-existe", "..%2F..%2Fapp%2Fconfig", "Como-Criei-O-Gitmgf"):
        assert client.get(f"/blog/{slug}").status_code == 404
    assert blog.get("../legal/terms", "pt") is None


def test_english_falls_back_to_portuguese(tmp_path, monkeypatch):
    (tmp_path / "so-pt.md").write_text("---\ntitle: Só PT\ndate: 2026-11-01\n---\nTexto.\n")
    monkeypatch.setattr(blog, "CONTENT_DIR", tmp_path)
    post = blog.get("so-pt", "en")
    assert post and post.is_fallback and post.lang == "pt" and post.title == "Só PT"
    assert [p.slug for p in blog.all_posts("en")] == ["so-pt"]


def test_blog_is_linked_and_in_the_sitemap(client):
    assert 'href="/blog"' in client.get("/").text
    sitemap = client.get("/sitemap.xml").text
    assert f"/blog/{SLUG}</loc>" in sitemap and f"/en/blog/{SLUG}</loc>" in sitemap


def test_file_names_are_not_auto_linked_as_domains():
    import re

    for post in blog.all_posts("pt") + blog.all_posts("en"):
        assert not re.search(r'href="https?://[\w.-]+\.md"', post.html), post.slug


def test_tabs_blocks_render_as_labelled_panels():
    html = blog.render_body(
        "Antes\n\n:::tabs\n::tab macOS / Linux\n```bash\ncurl x\n```\n::tab <Windows>\nTexto **forte**.\n:::\n\nDepois\n"
    )
    assert html.count('class="ctabs__panel"') == 2 and "data-tabs" in html
    assert 'data-tab-label="macOS / Linux"' in html and "&lt;Windows&gt;" in html and "<Windows>" not in html
    assert "<pre><code" in html and "<strong>forte</strong>" in html
    assert html.index("Antes") < html.index("data-tabs") < html.index("Depois")
    assert "TABSBLOCK" not in html and ":::" not in html


def test_install_step_has_macos_windows_and_vscode_tabs(client):
    for path in (f"/blog/{SLUG}", f"/en/blog/{SLUG}"):
        page = client.get(path).text
        assert page.count('class="ctabs__panel"') == 3
        assert "install.ps1" in page and "VS Code" in page
