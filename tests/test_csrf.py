from tests.conftest import csrf_token, login, make_user


def test_post_without_token_is_rejected(client, db):
    csrf_token(client)
    r = client.post("/login", data={"email": "a@example.org", "password": "x"})
    assert r.status_code == 403


def test_post_with_wrong_token_is_rejected(client):
    csrf_token(client)
    r = client.post("/login", data={"email": "a@example.org", "password": "x", "csrf_token": "x" * 40})
    assert r.status_code == 403


def test_post_with_form_token_is_accepted(client):
    r = client.post(
        "/login", data={"email": "a@example.org", "password": "x", "csrf_token": csrf_token(client)}
    )
    assert r.status_code == 401  # past CSRF; wrong credentials


def test_htmx_header_token_is_accepted(client, db):
    from tests.factories import make_tool

    tool = make_tool(db)
    user = make_user(db, "fan@example.org")
    login(client, db, user)
    r = client.post(f"/t/{tool.id}/star", headers={"X-CSRF-Token": csrf_token(client), "HX-Request": "true"})
    assert r.status_code == 200
    assert 'aria-pressed="true"' in r.text


def test_cross_origin_post_is_rejected(client):
    token = csrf_token(client)
    r = client.post(
        "/login",
        data={"email": "a@example.org", "password": "x", "csrf_token": token},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_csrf_cookie_flags(client):
    r = client.get("/")
    cookie = r.headers.get("set-cookie", "")
    assert (
        "gitmgf_csrf=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie.replace("Lax", "lax")
    )


def _form_tokens(html: str) -> list[str]:
    import re

    return re.findall(r'name="csrf_token" value="([^"]*)"', html)


def test_every_rendered_form_carries_the_cookie_token(client, db):
    """Regression: imported macros must see the page context, or forms ship an empty token (403 in browsers)."""
    from app.models.enums import Role
    from tests.conftest import get_cookie
    from tests.factories import make_tool

    admin = make_user(db, "admin@example.org", Role.admin)
    other = make_user(db, "author@example.org")
    pending = make_tool(db, other, status="pending", title_pt="Pendente")
    published = make_tool(db, other, status="published", title_pt="Publicada", moderator=admin)
    pages_anon = ["/login", "/register", f"/t/{published.slug}/report"]
    pages_user = [
        "/me/settings",
        "/me/tools/new",
        f"/mod/tools/{pending.id}",
        "/admin/invites",
        "/admin/settings",
        f"/admin/users/{other.id}",
    ]
    for path in pages_anon:
        html = client.get(path).text
        cookie = get_cookie(client, "gitmgf_csrf")
        tokens = _form_tokens(html)
        assert tokens and all(t == cookie for t in tokens), path
    login(client, db, admin)
    for path in pages_user:
        html = client.get(path).text
        cookie = get_cookie(client, "gitmgf_csrf")
        tokens = _form_tokens(html)
        assert tokens and all(t == cookie for t in tokens), path


def test_browser_like_login_submission_uses_only_the_page_token(client, db):
    from app.services import passwords

    user = make_user(db, "ana@example.org")
    user.password_hash = passwords.hash_password("uma frase bastante longa")
    db.commit()
    token = _form_tokens(client.get("/login").text)[0]
    r = client.post(
        "/login",
        data={"csrf_token": token, "email": "ana@example.org", "password": "uma frase bastante longa"},
        headers={"Origin": "http://testserver"},
    )
    assert r.status_code == 303
