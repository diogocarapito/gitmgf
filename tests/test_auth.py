import re
from datetime import timedelta

import httpx
import respx
import time_machine
from sqlalchemy import select

from app.db import utcnow
from app.models import AuditLog, MagicLinkToken, OAuthAccount, User, UserSession
from app.models.enums import Role, UserStatus
from app.services import email, oauth
from tests.conftest import clear_cookie, csrf_token, get_cookie, login, make_user, post


def _magic_token() -> str:
    body = email.SENT[-1].get_body(preferencelist=("plain",)).get_content()
    match = re.search(r"/auth/magic/([\w-]+)", body)
    assert match, body
    return match.group(1)


def test_magic_link_full_flow_creates_user_and_requires_onboarding(client, db):
    r = post(client, "/auth/magic-link", {"email": "Nova@Example.org", "next": "/pt/search"})
    assert r.status_code == 200
    assert "Verifique o seu email" in r.text
    assert email.SENT and email.SENT[-1]["To"] == "nova@example.org"
    token = _magic_token()

    # GET only shows a confirmation button (prefetch-safe): the token is not consumed.
    r = client.get(f"/auth/magic/{token}")
    assert r.status_code == 200 and "Confirmar entrada" in r.text
    row = db.scalar(select(MagicLinkToken))
    assert row.used_at is None

    r = post(client, f"/auth/magic/{token}")
    assert r.status_code == 303
    assert r.headers["location"].startswith("/pt/onboarding?next=/pt/search")
    assert get_cookie(client, "gitmgf_session")
    user = db.scalar(select(User).where(User.email == "nova@example.org"))
    assert user is not None and user.email_verified_at is not None


def test_magic_link_is_single_use(client, db):
    make_user(db, "a@example.org")
    post(client, "/auth/magic-link", {"email": "a@example.org"})
    token = _magic_token()
    assert post(client, f"/auth/magic/{token}").status_code == 303
    clear_cookie(client, "gitmgf_session")
    r = post(client, f"/auth/magic/{token}")
    assert r.status_code == 400
    assert client.get(f"/auth/magic/{token}").status_code == 400


def test_magic_link_expires_after_15_minutes(client, db):
    make_user(db, "a@example.org")
    post(client, "/auth/magic-link", {"email": "a@example.org"})
    token = _magic_token()
    with time_machine.travel(utcnow() + timedelta(minutes=16), tick=False):
        assert post(client, f"/auth/magic/{token}").status_code == 400


def test_magic_link_response_does_not_enumerate_accounts(client, db):
    make_user(db, "known@example.org")
    known = post(client, "/auth/magic-link", {"email": "known@example.org"})
    unknown = post(client, "/auth/magic-link", {"email": "unknown@example.org"})
    assert known.status_code == unknown.status_code == 200
    strip = lambda html: html.replace("unknown@example.org", "X").replace("known@example.org", "X")  # noqa: E731
    assert strip(known.text) == strip(unknown.text)


def test_magic_link_rate_limited_per_email(client, db):
    for _ in range(5):
        post(client, "/auth/magic-link", {"email": "spam@example.org"})
    sent_before = len(email.SENT)
    r = post(client, "/auth/magic-link", {"email": "spam@example.org"})
    assert r.status_code == 200  # same page
    assert len(email.SENT) == sent_before  # but nothing sent


def test_suspended_user_cannot_sign_in(client, db):
    user = make_user(db, "s@example.org")
    user.status = UserStatus.suspended
    db.commit()
    post(client, "/auth/magic-link", {"email": "s@example.org"})
    assert not email.SENT  # no link is sent to suspended accounts
    login(client, db, user)  # an old session must not work either
    assert client.get("/pt/me/settings").status_code == 303


def test_invalid_email_rerenders_form(client):
    r = post(client, "/auth/magic-link", {"email": "not-an-email"})
    assert r.status_code == 422
    assert "Indique um email válido" in r.text


def test_new_session_on_every_login(client, db):
    user = make_user(db, "a@example.org")
    login(client, db, user)
    old = get_cookie(client, "gitmgf_session")
    post(client, "/auth/magic-link", {"email": "a@example.org"})
    post(client, f"/auth/magic/{_magic_token()}")
    assert get_cookie(client, "gitmgf_session") != old
    assert db.scalar(select(UserSession).where(UserSession.user_id == user.id)) is not None
    assert len(db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()) == 1


def test_admin_emails_promotes_on_login_and_audits(client, db):
    post(client, "/auth/magic-link", {"email": "boss@example.org"})
    post(client, f"/auth/magic/{_magic_token()}")
    user = db.scalar(select(User).where(User.email == "boss@example.org"))
    assert user.role == Role.admin
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.role_change"))
    assert entry is not None and entry.details["via"] == "ADMIN_EMAILS"


def test_logout_and_logout_everywhere(client, db):
    user = make_user(db, "a@example.org")
    login(client, db, user)
    login(client, db, user)  # second device
    assert len(db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()) == 2
    assert post(client, "/auth/logout-all").status_code == 303
    db.expire_all()
    assert db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all() == []


def test_onboarding_completes_profile_and_terms(client, db):
    user = make_user(db, "n@example.org", onboarded=False)
    login(client, db, user)
    assert client.get("/pt/me/settings").headers["location"].startswith("/pt/onboarding")
    data = {"display_name": "Nova Pessoa", "handle": "nova-pessoa", "profession": "resident", "locale": "en"}
    r = post(client, "/pt/onboarding", data)
    assert r.status_code == 422 and "Tem de aceitar" in r.text
    r = post(client, "/pt/onboarding", {**data, "accept_terms": "1", "next": "/en/search"})
    assert r.status_code == 303 and r.headers["location"] == "/en/search"
    db.refresh(user)
    assert user.onboarded_at and user.terms_version == "2026-11" and user.locale.value == "en"
    assert any("Bem-vindo" in m["Subject"] or "Welcome" in m["Subject"] for m in email.SENT)


def test_onboarding_rejects_taken_handle(client, db):
    make_user(db, "taken@example.org")  # handle "taken"
    user = make_user(db, "n@example.org", onboarded=False)
    login(client, db, user)
    r = post(
        client,
        "/pt/onboarding",
        {"display_name": "X Y", "handle": "taken", "profession": "nurse", "accept_terms": "1"},
    )
    assert r.status_code == 422 and "já está a ser usado" in r.text


def test_next_param_must_be_relative(client, db):
    post(client, "/auth/magic-link", {"email": "a@example.org", "next": "//evil.example/x"})
    r = post(client, f"/auth/magic/{_magic_token()}")
    assert "evil" not in r.headers["location"]


# ---------- OAuth ----------


def _start(client, provider: str) -> str:
    r = client.get(f"/auth/{provider}/start?next=/pt/me/tools")
    assert r.status_code == 302
    return re.search(r"state=([^&]+)", r.headers["location"]).group(1)


@respx.mock
def test_github_oauth_links_to_existing_account_by_verified_email(client, db):
    existing = make_user(db, "dev@example.org")
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "t"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"id": 42, "login": "devgh", "name": "Dev"})
    )
    respx.get("https://api.github.com/user/emails").mock(
        return_value=httpx.Response(
            200, json=[{"email": "Dev@example.org", "primary": True, "verified": True}]
        )
    )
    state = _start(client, "github")
    r = client.get(f"/auth/github/callback?code=abc&state={state}")
    assert r.status_code == 303, r.text
    account = db.scalar(select(OAuthAccount))
    assert account.user_id == existing.id and account.provider_user_id == "42"
    assert db.query(User).count() == 1


@respx.mock
def test_google_oauth_refuses_unverified_email(client, db):
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t"})
    )
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
        return_value=httpx.Response(
            200, json={"sub": "g1", "email": "x@example.org", "email_verified": False}
        )
    )
    state = _start(client, "google")
    r = client.get(f"/auth/google/callback?code=abc&state={state}")
    assert r.status_code == 303 and "error=unverified_email" in r.headers["location"]
    assert db.query(User).count() == 0


@respx.mock
def test_google_oauth_creates_new_user(client, db):
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "t"})
    )
    respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
        return_value=httpx.Response(
            200, json={"sub": "g1", "email": "new@example.org", "email_verified": True, "name": "Nova"}
        )
    )
    state = _start(client, "google")
    r = client.get(f"/auth/google/callback?code=abc&state={state}")
    assert r.status_code == 303 and r.headers["location"].startswith("/pt/onboarding")
    user = db.scalar(select(User))
    assert user.email == "new@example.org" and user.display_name == "Nova"


def test_oauth_callback_rejects_bad_state(client, db):
    _start(client, "github")
    r = client.get("/auth/github/callback?code=abc&state=forged")
    assert r.status_code == 303 and "error=oauth_state" in r.headers["location"]


def test_oauth_state_cookie_is_signed():
    url, cookie = oauth.start(oauth.OAuthProvider.github, None, "pt", False)
    assert "code_challenge_method=S256" in url
    tampered = cookie[:-2] + ("AA" if not cookie.endswith("AA") else "BB")
    state = re.search(r"state=([^&]+)", url).group(1)
    try:
        oauth.read_state(tampered, oauth.OAuthProvider.github, state)
    except oauth.AuthError as exc:
        assert exc.code == "oauth_state"
    else:
        raise AssertionError("tampered cookie accepted")
    assert oauth.read_state(cookie, oauth.OAuthProvider.github, state)["s"] == state


def test_csrf_token_cookie_is_set(client):
    assert csrf_token(client)
