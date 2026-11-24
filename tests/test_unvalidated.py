"""Tools are public from submission, marked until a moderator validates them (D43); account restrictions (D41)."""

from sqlalchemy import select

from app.models import AuditLog, EmailOutbox
from app.models.enums import Role, ToolStatus
from app.services import tools as svc
from tests.conftest import login, make_user, post
from tests.factories import make_tool


def test_submitted_tool_is_listed_with_a_badge_but_not_popular_or_in_the_feed(client, db):
    tool = make_tool(db, status="pending", title_pt="Ferramenta por validar")
    home = client.get("/").text
    assert "Ferramenta por validar" in home and "Por validar" in home
    assert "Ferramenta por validar" in client.get("/search?q=validar").text
    assert "Ferramenta por validar" not in client.get("/feed.xml").text
    assert "Ferramenta por validar" in client.get(f"/u/{tool.owner.handle}").text
    assert client.get(f"/go/{tool.id}/website").status_code == 404  # no redirect to an unreviewed URL
    page = client.get(f"/t/{tool.slug}").text
    assert "Os comentários abrem quando" in page and "Dar estrela" not in page
    assert "Reportar problema" in page


def test_request_changes_keeps_the_page_up_and_reject_takes_it_down(client, db):
    owner = make_user(db, "owner@example.org")
    mod = make_user(db, "mod@example.org", role=Role.moderator)
    tool = make_tool(db, owner, status="pending")
    svc.transition(db, tool, "request_changes", mod, reason="Falta a utilização prevista.")
    db.commit()
    assert tool.status == ToolStatus.draft and tool.is_unvalidated
    page = client.get(f"/t/{tool.slug}").text
    assert "Em revisão." in page
    svc.transition(db, tool, "submit", owner)
    svc.transition(db, tool, "reject", mod, reason="Conteúdo fora do âmbito.")
    db.commit()
    assert client.get(f"/t/{tool.slug}").status_code == 404
    svc.transition(db, tool, "submit", owner)  # resubmitting a rejected tool doesn't bring it back
    db.commit()
    assert tool.status == ToolStatus.pending and client.get(f"/t/{tool.slug}").status_code == 404
    svc.transition(db, tool, "approve", mod)
    db.commit()
    assert client.get(f"/t/{tool.slug}").status_code == 200


def test_withdrawing_makes_the_tool_private_again(client, db):
    owner = make_user(db, "owner@example.org")
    tool = make_tool(db, owner, status="pending")
    svc.transition(db, tool, "withdraw", owner)
    db.commit()
    assert client.get(f"/t/{tool.slug}").status_code == 404


def test_moderator_restricts_and_lifts_publishing(client, db):
    target = make_user(db, "target@example.org")
    mod = make_user(db, "mod@example.org", role=Role.moderator)
    login(client, db, mod)
    assert client.get(f"/mod/users/{target.id}").status_code == 200
    r = post(client, f"/mod/users/{target.id}/restrict/publish", {"reason": "Publicações repetidas de spam."})
    assert r.status_code == 303 and "flash=restricted" in r.headers["location"]
    db.refresh(target)
    assert target.publish_blocked_at is not None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "user.restrict_publish")) is not None
    mail = db.scalar(select(EmailOutbox).where(EmailOutbox.template == "account_restricted"))
    assert mail is not None and "Publicações repetidas de spam." in mail.body_text
    login(client, db, target)
    assert client.get("/me/tools/new").status_code == 403
    assert post(client, "/me/tools/new", {"title_pt": "Nova"}).status_code == 403
    login(client, db, mod)
    post(client, f"/mod/users/{target.id}/lift/publish")
    db.refresh(target)
    assert target.publish_blocked_at is None


def test_restriction_permissions(client, db):
    mod = make_user(db, "mod@example.org", role=Role.moderator)
    other_mod = make_user(db, "mod2@example.org", role=Role.moderator)
    admin = make_user(db, "admin@example.org", role=Role.admin)
    login(client, db, make_user(db, "user@example.org"))
    assert client.get(f"/mod/users/{mod.id}").status_code == 404  # moderators only
    login(client, db, mod)
    reason = {"reason": "Motivo suficientemente longo."}
    assert post(client, f"/mod/users/{other_mod.id}/restrict/social", reason).status_code == 403
    assert post(client, f"/mod/users/{admin.id}/restrict/social", reason).status_code == 403
    assert post(client, f"/mod/users/{mod.id}/restrict/social", reason).status_code == 403
    login(client, db, admin)
    assert post(client, f"/mod/users/{other_mod.id}/restrict/social", reason).status_code == 303
