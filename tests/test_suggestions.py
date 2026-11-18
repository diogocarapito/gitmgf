from datetime import timedelta

import time_machine
from sqlalchemy import select

from app.db import utcnow
from app.models import Suggestion
from app.services import email, gdpr
from tests.conftest import login, make_user, post
from tests.factories import make_tool

MESSAGE = "Seria útil poder exportar os resultados em PDF para anexar ao processo."


def _mails_to(address):
    return [m for m in email.SENT if m["To"] == address]


def test_link_sits_before_report_and_external_note_is_gone(client, db):
    tool = make_tool(db)
    page = client.get(f"/t/{tool.slug}").text
    assert page.index("Sugerir melhoria") < page.index("Reportar problema")
    assert "Vai abrir um site externo" not in page
    login(client, db, tool.owner)
    assert "Sugerir melhoria" not in client.get(f"/t/{tool.slug}").text  # not on your own tool


def test_suggesting_needs_sign_in_and_is_not_for_your_own_tool(client, db):
    tool = make_tool(db)
    r = client.get(f"/t/{tool.slug}/suggest", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]
    assert post(client, f"/t/{tool.slug}/suggest", {"kind": "feature", "message": MESSAGE}).status_code == 403
    login(client, db, tool.owner)
    assert client.get(f"/t/{tool.slug}/suggest").status_code == 404
    draft = make_tool(db, status="draft", title_pt="Rascunho")
    login(client, db, make_user(db, "x@example.org"))
    assert client.get(f"/t/{draft.slug}/suggest").status_code == 404


def test_suggestion_emails_the_author_and_reply_goes_to_sender_only_with_consent(client, db):
    tool = make_tool(db)
    sender = make_user(db, "rita@example.org")
    login(client, db, sender)
    assert post(client, f"/t/{tool.slug}/suggest", {"kind": "feature", "message": "curta"}).status_code == 422
    r = post(client, f"/t/{tool.slug}/suggest", {"kind": "feature", "message": MESSAGE})
    assert r.status_code == 303 and r.headers["location"].endswith("?flash=suggested")
    first = _mails_to(tool.owner.email)[-1]
    assert "Nova sugestão" in first["Subject"] and "rita@example.org" not in str(first)
    assert first["Reply-To"] != "rita@example.org"
    post(client, f"/t/{tool.slug}/suggest", {"kind": "improvement", "message": MESSAGE, "allow_reply": "1"})
    second = _mails_to(tool.owner.email)[-1]
    assert second["Reply-To"] == "rita@example.org"
    assert MESSAGE in second.get_body(preferencelist=("plain",)).get_content()
    assert db.query(Suggestion).count() == 2


def test_notifications_page_shows_unread_badge_marks_read_and_deletes(client, db):
    tool = make_tool(db)
    sender = make_user(db, "rita@example.org")
    login(client, db, sender)
    post(client, f"/t/{tool.slug}/suggest", {"kind": "feature", "message": MESSAGE, "allow_reply": "1"})
    login(client, db, tool.owner)
    home = client.get("/").text
    assert 'class="notif-count"' in home and "(1 por ler)" in home
    inbox = client.get("/me/notifications").text
    assert MESSAGE in inbox and "Nova" in inbox and "mailto:rita@example.org" in inbox
    assert 'class="notif-count"' not in client.get("/").text  # read now
    item = db.scalar(select(Suggestion))
    login(client, db, sender)
    assert post(client, f"/me/notifications/{item.id}/delete").status_code == 404  # not the recipient
    login(client, db, tool.owner)
    assert post(client, f"/me/notifications/{item.id}/delete").status_code == 303
    db.expire_all()
    assert db.query(Suggestion).count() == 0


def test_suggestions_are_rate_limited_per_tool(client, db):
    tool = make_tool(db)
    login(client, db, make_user(db, "rita@example.org"))
    for _ in range(3):
        assert (
            post(client, f"/t/{tool.slug}/suggest", {"kind": "other", "message": MESSAGE}).status_code == 303
        )
    assert post(client, f"/t/{tool.slug}/suggest", {"kind": "other", "message": MESSAGE}).status_code == 429


def test_gdpr_export_delete_and_retention(client, db):
    tool = make_tool(db)
    sender = make_user(db, "rita@example.org")
    login(client, db, sender)
    post(client, f"/t/{tool.slug}/suggest", {"kind": "feature", "message": MESSAGE})
    assert gdpr.export(db, sender)["suggestions_sent"][0]["message"] == MESSAGE
    assert gdpr.export(db, tool.owner)["suggestions_received"][0]["kind"] == "feature"
    with time_machine.travel(utcnow() + timedelta(days=366), tick=False):
        gdpr.purge(db)
        db.commit()
    assert db.query(Suggestion).count() == 0
    login(client, db, sender)
    post(client, f"/t/{tool.slug}/suggest", {"kind": "feature", "message": MESSAGE})
    gdpr.delete_account(db, sender, sender)
    db.commit()
    assert db.query(Suggestion).count() == 0
