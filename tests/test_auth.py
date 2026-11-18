from datetime import timedelta

import time_machine
from sqlalchemy import select

from app.db import utcnow
from app.models import AuditLog, Invite, User, UserSession
from app.models.enums import Role, UserStatus
from app.services import auth as auth_service
from app.services import passwords, settings_store
from tests.conftest import get_cookie, login, make_user, post

PASSWORD = "uma frase bastante longa"


def with_password(db, user, password=PASSWORD):
    user.password_hash = passwords.hash_password(password)
    db.commit()
    return user


def sessions_of(db, user):
    return db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()


# ---------- login ----------


def test_login_with_password_sets_session_and_redirects(client, db):
    user = with_password(db, make_user(db, "ana@example.org"))
    r = post(client, "/login", {"email": "Ana@Example.org", "password": PASSWORD, "next": "/search"})
    assert r.status_code == 303 and r.headers["location"] == "/search"
    assert get_cookie(client, "gitmgf_session")
    assert len(sessions_of(db, user)) == 1


def test_wrong_password_and_unknown_email_look_the_same(client, db):
    with_password(db, make_user(db, "ana@example.org"))
    wrong = post(client, "/login", {"email": "ana@example.org", "password": "errada errada"})
    unknown = post(client, "/login", {"email": "ninguem@example.org", "password": "errada errada"})
    assert wrong.status_code == unknown.status_code == 401
    assert (
        "Email ou palavra-passe incorretos" in wrong.text
        and "Email ou palavra-passe incorretos" in unknown.text
    )
    assert not get_cookie(client, "gitmgf_session")


def test_login_is_rate_limited_per_email(client, db):
    with_password(db, make_user(db, "ana@example.org"))
    for _ in range(10):
        post(client, "/login", {"email": "ana@example.org", "password": "errada errada"})
    r = post(client, "/login", {"email": "ana@example.org", "password": PASSWORD})
    assert r.status_code == 429  # even the right password waits


def test_suspended_user_cannot_sign_in(client, db):
    user = with_password(db, make_user(db, "s@example.org"))
    user.status = UserStatus.suspended
    db.commit()
    r = post(client, "/login", {"email": "s@example.org", "password": PASSWORD})
    assert r.status_code == 403
    login(client, db, user)  # an old session must not work either
    assert client.get("/me/settings").status_code == 303


def test_new_session_on_every_login(client, db):
    user = with_password(db, make_user(db, "a@example.org"))
    login(client, db, user)
    old = get_cookie(client, "gitmgf_session")
    post(client, "/login", {"email": "a@example.org", "password": PASSWORD})
    assert get_cookie(client, "gitmgf_session") != old
    assert len(sessions_of(db, user)) == 1


def test_next_param_must_be_relative(client, db):
    with_password(db, make_user(db, "a@example.org"))
    r = post(client, "/login", {"email": "a@example.org", "password": PASSWORD, "next": "//evil.example/x"})
    assert "evil" not in r.headers["location"]


def test_logout_and_logout_everywhere(client, db):
    user = make_user(db, "a@example.org")
    login(client, db, user)
    login(client, db, user)
    assert len(sessions_of(db, user)) == 2
    assert post(client, "/auth/logout-all").status_code == 303
    db.expire_all()
    assert sessions_of(db, user) == []


# ---------- registration ----------


def _register(client, **data):
    payload = {"email": "nova@example.org", "password": PASSWORD, "password_confirm": PASSWORD, **data}
    return post(client, "/register", payload)


def test_registration_requires_invite_by_default(client, db):
    assert settings_store.get(db, "site.registration_open") is False
    r = _register(client)
    assert r.status_code == 422 and "convite" in r.text.lower()
    assert db.query(User).count() == 0


def test_invite_registers_then_onboarding(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    _, code = auth_service.create_invite(db, admin, note="Ana")
    db.commit()
    assert "Convite válido" in client.get(f"/register?invite={code}").text
    r = _register(client, invite=code)
    assert r.status_code == 303 and r.headers["location"].startswith("/onboarding")
    user = db.scalar(select(User).where(User.email == "nova@example.org"))
    assert user and passwords.verify_password(PASSWORD, user.password_hash)
    db.expire_all()
    assert db.scalar(select(Invite)).uses == 1
    client.cookies.clear()
    assert _register(client, invite=code, email="outra@example.org").status_code == 422  # single use


def test_email_locked_invite(client, db):
    _, code = auth_service.create_invite(db, None, email="certa@example.org")
    db.commit()
    assert _register(client, invite=code, email="errada@example.org").status_code == 422
    assert _register(client, invite=code, email="certa@example.org").status_code == 303


def test_expired_and_revoked_invites(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    invite, code = auth_service.create_invite(db, admin, days=1)
    db.commit()
    with time_machine.travel(utcnow() + timedelta(days=2), tick=False):
        assert _register(client, invite=code).status_code == 422
    auth_service.revoke_invite(db, invite, admin)
    db.commit()
    assert _register(client, invite=code).status_code == 422


def test_open_registration_needs_no_invite(client, db):
    settings_store.set_value(db, "site.registration_open", True, None)
    db.commit()
    assert _register(client).status_code == 303


def test_admin_emails_can_bootstrap_without_invite_and_get_promoted(client, db):
    assert _register(client, email="boss@example.org").status_code == 303
    user = db.scalar(select(User).where(User.email == "boss@example.org"))
    assert user.role == Role.admin
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.role_change"))
    assert entry.details["via"] == "ADMIN_EMAILS"


def test_registration_validates_password_and_duplicates(client, db):
    settings_store.set_value(db, "site.registration_open", True, None)
    db.commit()
    assert _register(client, password="curta", password_confirm="curta").status_code == 422
    assert _register(client, password_confirm="outra coisa diferente").status_code == 422
    assert _register(client).status_code == 303
    client.cookies.clear()
    r = _register(client)
    assert r.status_code == 422 and "Já existe uma conta" in r.text


# ---------- reset links ----------


def test_reset_link_sets_password_and_signs_out_other_sessions(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    user = with_password(db, make_user(db, "u@example.org"))
    login(client, db, user)  # some other device
    token = auth_service.create_reset_link(db, user, admin)
    db.commit()
    client.cookies.clear()
    assert client.get(f"/reset/{token}").status_code == 200
    new = "nova frase secreta"
    assert post(client, f"/reset/{token}", {"password": new, "password_confirm": new}).status_code == 303
    db.expire_all()
    assert passwords.verify_password(new, db.get(User, user.id).password_hash)
    assert len(sessions_of(db, user)) == 1  # only the new one
    assert client.get(f"/reset/{token}").status_code == 400  # single use


def test_reset_link_expires_and_new_link_invalidates_old(client, db):
    user = make_user(db, "u@example.org")
    first = auth_service.create_reset_link(db, user, None)
    second = auth_service.create_reset_link(db, user, None)
    db.commit()
    assert client.get(f"/reset/{first}").status_code == 400
    with time_machine.travel(utcnow() + timedelta(hours=49), tick=False):
        assert client.get(f"/reset/{second}").status_code == 400


def test_admin_generates_reset_link_from_user_page(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    user = make_user(db, "u@example.org")
    login(client, db, admin)
    r = post(client, f"/admin/users/{user.id}/reset-link")
    assert r.status_code == 200 and "http://testserver/reset/" in r.text


def test_admin_creates_invite_from_admin_page(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    login(client, db, admin)
    r = post(client, "/admin/invites", {"note": "Beta MGF", "max_uses": "5", "days": "30"})
    assert r.status_code == 200 and "/register?invite=" in r.text
    invite = db.scalar(select(Invite))
    assert invite.max_uses == 5 and invite.note == "Beta MGF"


def test_cli_create_admin_prints_set_password_link(db_path):
    from typer.testing import CliRunner

    from app.cli import cli

    result = CliRunner().invoke(cli, ["create-admin", "Chefe@Example.org"])
    assert result.exit_code == 0 and "/reset/" in result.output


# ---------- settings & onboarding ----------


def test_change_password_requires_current(client, db):
    user = with_password(db, make_user(db, "me@example.org"))
    login(client, db, user)
    new = "outra frase longa"
    r = post(client, "/me/password", {"current_password": "errada", "password": new, "password_confirm": new})
    assert r.status_code == 422
    r = post(client, "/me/password", {"current_password": PASSWORD, "password": new, "password_confirm": new})
    assert r.status_code == 303
    db.refresh(user)
    assert passwords.verify_password(new, user.password_hash)


def test_onboarding_completes_profile_and_terms(client, db):
    user = make_user(db, "n@example.org", onboarded=False)
    login(client, db, user)
    assert client.get("/me/settings").headers["location"].startswith("/onboarding")
    data = {"display_name": "Nova Pessoa", "handle": "nova-pessoa", "profession": "resident", "locale": "en"}
    r = post(client, "/onboarding", data)
    assert r.status_code == 422 and "Tem de aceitar" in r.text
    r = post(client, "/onboarding", {**data, "accept_terms": "1", "next": "/en/search"})
    assert r.status_code == 303 and r.headers["location"] == "/en/search"
    db.refresh(user)
    assert user.onboarded_at and user.terms_version == "2026-11" and user.locale.value == "en"


def test_onboarding_rejects_taken_handle(client, db):
    make_user(db, "taken@example.org")
    user = make_user(db, "n@example.org", onboarded=False)
    login(client, db, user)
    data = {"display_name": "X Y", "handle": "taken", "profession": "nurse", "accept_terms": "1"}
    r = post(client, "/onboarding", data)
    assert r.status_code == 422 and "já está a ser usado" in r.text


def test_settings_update_profile(client, db):
    user = make_user(db, "me@example.org")
    login(client, db, user)
    data = {
        "display_name": "Novo Nome",
        "handle": "novo-nome",
        "profession": "nurse",
        "locale": "pt",
        "github_username": "https://github.com/novo",
    }
    assert post(client, "/me/settings", data).status_code == 303
    db.refresh(user)
    assert user.display_name == "Novo Nome" and user.github_username == "novo"
    assert (
        post(
            client, "/me/settings", {"display_name": "X", "handle": "Bad Handle!", "profession": "nurse"}
        ).status_code
        == 422
    )


def test_cli_change_email_keeps_account_and_signs_out(client, db):
    from typer.testing import CliRunner

    from app.cli import cli

    user = with_password(db, make_user(db, "old@example.org", Role.admin))
    login(client, db, user)
    make_user(db, "taken@example.org")
    runner = CliRunner()
    assert runner.invoke(cli, ["change-email", "old@example.org", "taken@example.org"]).exit_code == 1
    result = runner.invoke(cli, ["change-email", "Old@Example.org", "New@Example.org"])
    assert result.exit_code == 0, result.output
    db.expire_all()
    moved = db.get(User, user.id)
    assert moved.email == "new@example.org" and moved.role == Role.admin
    assert sessions_of(db, moved) == []
    assert post(client, "/login", {"email": "new@example.org", "password": PASSWORD}).status_code == 303


# ---------- email flows (D29) ----------


def _mail_to(address):
    from app.services import email

    return [m for m in email.SENT if m["To"] == address]


def _link_in(msg):
    import re

    return re.search(
        r"http://testserver(/[\w/?=&.-]+)", msg.get_body(preferencelist=("plain",)).get_content()
    ).group(1)


def test_forgot_password_emails_a_one_hour_link_without_enumeration(client, db):
    with_password(db, make_user(db, "ana@example.org"))
    known = post(client, "/forgot", {"email": "ana@example.org"})
    unknown = post(client, "/forgot", {"email": "ninguem@example.org"})
    assert known.status_code == unknown.status_code == 200
    assert known.text.replace("ana@example.org", "X") == unknown.text.replace("ninguem@example.org", "X")
    assert not _mail_to("ninguem@example.org")
    link = _link_in(_mail_to("ana@example.org")[0])
    assert link.startswith("/reset/")
    with time_machine.travel(utcnow() + timedelta(minutes=61), tick=False):
        assert client.get(link).status_code == 400
    assert client.get(link).status_code == 200


def test_forgot_password_is_rate_limited(client, db):
    with_password(db, make_user(db, "ana@example.org"))
    for _ in range(5):
        post(client, "/forgot", {"email": "ana@example.org"})
    assert len(_mail_to("ana@example.org")) == 3


def test_forgot_page_hidden_without_smtp_in_prod(client, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(Settings, "email_backend", property(lambda self: "none"))
    assert client.get("/forgot").status_code == 404
    assert "/forgot" not in client.get("/login").text


def test_admin_can_email_invite_and_set_password_link(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    target = make_user(db, "u@example.org")
    login(client, db, admin)
    r = post(
        client,
        "/admin/invites",
        {"email": "nova@example.org", "send_email": "1", "invite_lang": "en", "max_uses": "1", "days": "7"},
    )
    assert r.status_code == 200 and "nova@example.org" in r.text
    invite_mail = _mail_to("nova@example.org")[0]
    assert invite_mail["Subject"] == "Invitation to gitmgf" and "/en/register?invite=" in _link_in(
        invite_mail
    )
    r = post(client, f"/admin/users/{target.id}/reset-email")
    assert r.status_code == 303 and "reset_emailed" in r.headers["location"]
    assert _link_in(_mail_to("u@example.org")[0]).startswith("/reset/")


def test_cli_send_test_email_requires_smtp(db_path):
    from typer.testing import CliRunner

    from app.cli import cli

    result = CliRunner().invoke(cli, ["send-test-email", "x@example.org"])
    assert result.exit_code == 1 and "SMTP_HOST is not set" in result.output


def test_cli_create_user_as_moderator(db_path, db):
    from typer.testing import CliRunner

    from app.cli import cli
    from app.services import email

    runner = CliRunner()
    printed = runner.invoke(cli, ["create-user", "Mod.Um@Example.org", "--role", "moderator"])
    assert printed.exit_code == 0 and "http://testserver/reset/" in printed.output
    sent = runner.invoke(
        cli, ["create-user", "mod2@example.org", "--role", "moderator", "--send", "--lang", "en"]
    )
    assert sent.exit_code == 0 and "emailed" in sent.output
    db.expire_all()
    users = {u.email: u for u in db.query(User).all()}
    assert (
        users["mod.um@example.org"].role == Role.moderator and users["mod2@example.org"].locale.value == "en"
    )
    assert any(
        m["To"] == "mod2@example.org" and "/en/reset/" in m.get_body(preferencelist=("plain",)).get_content()
        for m in email.SENT
    )
    assert runner.invoke(cli, ["create-user", "not-an-email", "--role", "moderator"]).exit_code == 1


def test_cli_create_user_reports_a_failed_send(db_path, db, monkeypatch):
    """--send must not claim success when SMTP refuses the message; `emails` shows why."""
    from typer.testing import CliRunner

    from app.cli import cli
    from app.services import email

    def refuse(msg):
        raise RuntimeError("535 Authentication failed")

    monkeypatch.setattr(email, "_send", refuse)
    runner = CliRunner()
    result = runner.invoke(cli, ["create-user", "mod3@example.org", "--role", "moderator", "--send"])
    assert result.exit_code == 1 and "emailed" not in result.output
    assert "email NOT sent: RuntimeError: 535 Authentication failed" in result.output
    listing = runner.invoke(cli, ["emails"])
    assert (
        listing.exit_code == 0
        and "failed" in listing.output
        and "535 Authentication failed" in listing.output
    )

    monkeypatch.undo()
    retried = runner.invoke(cli, ["emails", "--retry"])
    assert retried.exit_code == 0 and "sent now: 1" in retried.output
    assert any(m["To"] == "mod3@example.org" for m in email.SENT)
