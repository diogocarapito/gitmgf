"""Admins switch email types off to save sending quota (D42)."""

from sqlalchemy import select

from app.models import EmailOutbox, Notification
from app.models.enums import Role
from app.services import content, email
from tests.conftest import login, make_user, post
from tests.factories import make_tool


def outbox(db, template):
    db.expire_all()
    return db.scalars(select(EmailOutbox).where(EmailOutbox.template == template)).all()


def test_every_email_template_is_listed_on_the_admin_page():
    files = {
        p.stem.removesuffix("_en")
        for p in (content.ROOT / "emails").glob("*.md")
        if not p.stem.startswith("_")
    }
    listed = {t for group in email.GROUPS.values() for t in group}
    assert files == listed
    assert listed >= email.ESSENTIAL


def test_admin_switches_a_type_off_and_essentials_stay_on(client, db):
    admin = make_user(db, "boss@example.org", role=Role.admin)
    login(client, db, make_user(db, "user@example.org"))
    assert client.get("/admin/emails").status_code == 404
    login(client, db, admin)
    page = client.get("/admin/emails").text
    assert "Tipos de email" in page and "Sempre ativo" in page
    known = [t for group in email.GROUPS.values() for t in group]
    enabled = [t for t in known if t not in ("comment_notice", "register_code")]
    assert post(client, "/admin/emails/types", {"enabled": enabled}).status_code == 303
    assert email.disabled_templates(db) == {"comment_notice"}  # register_code can't be switched off
    tool = make_tool(db)
    login(client, db, make_user(db, "fan@example.org"))
    post(client, f"/t/{tool.slug}/comments", {"body": "Muito útil, obrigado!"})
    assert outbox(db, "comment_notice") == []
    notes = db.scalars(select(Notification).where(Notification.user_id == tool.owner_id)).all()
    assert any(n.kind == "comment_new" for n in notes)  # the in-app notification still arrives


def test_bulk_off_keeps_account_emails_and_bulk_on_restores(client, db):
    admin = make_user(db, "boss@example.org", role=Role.admin)
    login(client, db, admin)
    post(client, "/admin/emails/types", {"bulk": "all_off"})
    assert email.is_enabled(db, "password_code") and not email.is_enabled(db, "tool_approved")
    make_tool(db)
    assert outbox(db, "tool_approved") == [] and outbox(db, "submission_received") == []
    post(client, "/admin/emails/types", {"bulk": "all_on"})
    assert email.disabled_templates(db) == set()
