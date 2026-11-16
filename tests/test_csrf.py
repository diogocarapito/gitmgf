from tests.conftest import csrf_token, login, make_user


def test_post_without_token_is_rejected(client, db):
    csrf_token(client)
    r = client.post("/auth/magic-link", data={"email": "a@example.org"})
    assert r.status_code == 403


def test_post_with_wrong_token_is_rejected(client):
    csrf_token(client)
    r = client.post("/auth/magic-link", data={"email": "a@example.org", "csrf_token": "x" * 40})
    assert r.status_code == 403


def test_post_with_form_token_is_accepted(client):
    r = client.post("/auth/magic-link", data={"email": "a@example.org", "csrf_token": csrf_token(client)})
    assert r.status_code == 200


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
        "/auth/magic-link",
        data={"email": "a@example.org", "csrf_token": token},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_csrf_cookie_flags(client):
    r = client.get("/pt/")
    cookie = r.headers.get("set-cookie", "")
    assert (
        "gitmgf_csrf=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie.replace("Lax", "lax")
    )
