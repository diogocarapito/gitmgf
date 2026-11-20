from app.services import notice
from tests.conftest import get_cookie, login, make_user, post

MARKER = "data-first-notice"


def test_first_visit_shows_the_notice_with_terms_and_privacy_links(client):
    page = client.get("/t/nao-existe").text + client.get("/").text
    assert MARKER in page and "Antes de continuar" in page and "exclusiva responsabilidade" in page
    assert 'href="/p/terms"' in page and 'href="/p/privacy"' in page and 'action="/notice/accept"' in page
    en = client.get("/en/").text
    assert MARKER in en and "sole responsibility" in en and 'href="/en/p/terms"' in en


def test_accepting_sets_the_cookie_returns_to_the_page_and_hides_the_notice(client):
    r = post(client, "/notice/accept", {"next": "/search?q=risco"})
    assert r.status_code == 303 and r.headers["location"] == "/search?q=risco"
    assert get_cookie(client, notice.COOKIE) == notice.version()
    assert (
        "max-age=31536000" in r.headers["set-cookie"].lower()
        and "httponly" in r.headers["set-cookie"].lower()
    )
    assert MARKER not in client.get("/").text and MARKER not in client.get("/en/search").text


def test_accept_needs_csrf_and_only_redirects_to_local_paths(client):
    assert client.post("/notice/accept", data={"next": "/"}).status_code == 403
    for unsafe in ("https://evil.example", "//evil.example", ""):
        assert post(client, "/notice/accept", {"next": unsafe}).headers["location"] == "/"


def test_js_accept_gets_no_redirect(client):
    r = post(client, "/notice/accept", {"next": "/"}, headers={"HX-Request": "true"})
    assert r.status_code == 204 and get_cookie(client, notice.COOKIE) == notice.version()


def test_signed_in_users_and_the_linked_pages_skip_the_notice(client, db):
    for path in ("/p/terms", "/p/privacy", "/en/p/terms", "/p/disclaimer"):
        assert MARKER not in client.get(path).text, path
    assert MARKER in client.get("/p/about").text
    login(client, db, make_user(db))
    assert MARKER not in client.get("/").text


def test_a_new_terms_version_asks_again(client, monkeypatch):
    post(client, "/notice/accept", {"next": "/"})
    assert MARKER not in client.get("/").text
    monkeypatch.setattr(notice, "version", lambda: "2099-01")
    assert MARKER in client.get("/").text
