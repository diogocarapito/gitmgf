from sqlalchemy import select

from app.models import AuditLog, EmailOutbox, Tool
from app.models.enums import ClaimState, Role, ToolStatus
from app.services import settings_store
from app.services import tools as svc
from tests.conftest import login, make_user, post
from tests.factories import make_tool, tool_data


def _emails(db, template: str) -> list[EmailOutbox]:
    return list(db.scalars(select(EmailOutbox).where(EmailOutbox.template == template)))


def test_queue_lists_pending_items_oldest_first(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    first = make_tool(db, status="pending", title_pt="Primeira")
    make_tool(db, status="pending", title_pt="Segunda")
    login(client, db, mod)
    html = client.get("/pt/mod").text
    assert html.index("Primeira") < html.index("Segunda")
    assert f"/pt/mod/tools/{first.id}" in html


def test_approve_with_claim_rejection_emails_owner(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    owner = make_user(db, "o@example.org")
    tool = make_tool(
        db,
        owner,
        status="pending",
        claims={"rgpd": {"evidence_url": "https://x.example/p", "data_location": "eu_eea"}},
    )
    login(client, db, mod)
    r = post(
        client,
        f"/mod/tools/{tool.id}/approve",
        {"claim_rgpd": "reject", "claim_rgpd_reason": "A política não abre."},
    )
    assert r.status_code == 303
    db.refresh(tool)
    assert tool.status == ToolStatus.published
    assert (
        tool.claims[0].state == ClaimState.rejected and tool.claims[0].review_reason == "A política não abre."
    )
    approved = _emails(db, "tool_approved")
    assert approved and "A política não abre." in approved[-1].body_text


def test_reject_builds_reason_in_owner_language_and_states_appeal(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    owner = make_user(
        db, "o@example.org", locale=__import__("app.models.enums", fromlist=["Locale"]).Locale.en
    )
    tool = make_tool(db, owner, status="pending")
    login(client, db, mod)
    r = post(
        client,
        f"/mod/tools/{tool.id}/reject",
        {"reason_template": "broken_link", "reason_text": "The repo 404s."},
    )
    assert r.status_code == 303
    db.refresh(tool)
    assert tool.status == ToolStatus.rejected
    assert "Broken or unsafe link" in tool.rejection_reason and "The repo 404s." in tool.rejection_reason
    body = _emails(db, "tool_rejected")[-1].body_text
    assert "6 months" in body and "not by automated means" in body


def test_reject_without_reason_is_refused(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    tool = make_tool(db, status="pending")
    login(client, db, mod)
    r = post(client, f"/mod/tools/{tool.id}/reject", {})
    assert "flash=reason_required" in r.headers["location"]
    db.refresh(tool)
    assert tool.status == ToolStatus.pending


def test_request_changes_returns_tool_to_draft(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    tool = make_tool(db, status="pending")
    login(client, db, mod)
    post(client, f"/mod/tools/{tool.id}/request-changes", {"reason_template": "incomplete"})
    db.refresh(tool)
    assert tool.status == ToolStatus.draft and tool.rejection_reason


def test_revision_review_shows_diff_and_approves(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner, status="published", description_pt="Versão antiga do texto.", moderator=mod)
    svc.save_edit(db, tool, owner, tool_data(db, description_pt="Versão nova do texto."), {}, True)
    db.commit()
    revision = svc.pending_revision(db, tool)
    login(client, db, mod)
    html = client.get(f"/pt/mod/revisions/{revision.id}").text
    assert "<ins>" in html and "<del>" in html
    assert post(client, f"/mod/revisions/{revision.id}/approve").status_code == 303
    db.refresh(tool)
    assert tool.description_pt == "Versão nova do texto."
    assert _emails(db, "revision_approved")


def test_hide_and_unhide_with_audit_and_statement_of_reasons(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    tool = make_tool(db, status="published", moderator=mod)
    login(client, db, mod)
    post(client, f"/mod/tools/{tool.id}/hide", {"reason_template": "patient_data"})
    db.refresh(tool)
    assert tool.status == ToolStatus.hidden
    assert client.get(f"/pt/t/{tool.slug}").status_code == 200  # moderator still sees it
    hidden = _emails(db, "tool_hidden")[-1].body_text
    assert "Medida:" in hidden and "Contestação" in hidden
    post(client, f"/mod/tools/{tool.id}/unhide")
    db.refresh(tool)
    assert tool.status == ToolStatus.published
    actions = {a.action for a in db.scalars(select(AuditLog).where(AuditLog.target_id == tool.id))}
    assert {"tool.hide", "tool.unhide"} <= actions


def test_reset_score_ignores_older_events(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    tool = make_tool(db, status="published", moderator=mod)
    tool.score = 42.0
    db.commit()
    login(client, db, mod)
    post(client, f"/mod/tools/{tool.id}/reset-score")
    db.refresh(tool)
    assert tool.score == 0 and tool.score_reset_at is not None


def test_admin_role_change_is_audited_and_last_admin_protected(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    user = make_user(db, "u@example.org")
    login(client, db, admin)
    post(client, f"/admin/users/{user.id}/role", {"role": "moderator"})
    db.refresh(user)
    assert user.role == Role.moderator
    entry = db.scalar(
        select(AuditLog).where(AuditLog.action == "user.role_change", AuditLog.target_id == user.id)
    )
    assert entry.details == {"old": "user", "new": "moderator"}
    r = post(client, f"/admin/users/{admin.id}/role", {"role": "user"})
    assert "forbidden_last_admin" in r.headers["location"]
    db.refresh(admin)
    assert admin.role == Role.admin


def test_suspension_kills_sessions(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    user = make_user(db, "u@example.org")
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, follow_redirects=False) as other:
        login(other, db, user)
        assert other.get("/pt/me/settings").status_code == 200
        login(client, db, admin)
        post(client, f"/admin/users/{user.id}/suspend", {"reason": "Spam repetido."})
        assert other.get("/pt/me/settings").status_code == 303


def test_admin_adds_category_without_deploy(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    login(client, db, admin)
    r = post(
        client,
        "/pt/admin/categories",
        {"name_pt": "Medicina Desportiva", "name_en": "Sports Medicine", "is_specialty": "1"},
    )
    assert r.status_code == 303
    assert client.get("/pt/c/medicina-desportiva").status_code == 200
    assert "Sports Medicine" in client.get("/en/c/").text


def test_settings_change_is_audited_and_applied(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    login(client, db, admin)
    values = {
        k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in settings_store.DEFAULTS.items()
    }
    values["site.registration_open"] = "1"
    values["site.banner_pt"] = "Manutenção às 22h"
    values["reports.auto_hide_threshold"] = "5"
    r = post(client, "/pt/admin/settings", values)
    assert r.status_code == 303
    settings_store.invalidate()
    assert settings_store.get(db, "reports.auto_hide_threshold") == 5
    assert "Manutenção às 22h" in client.get("/pt/").text
    assert db.scalar(select(AuditLog).where(AuditLog.action == "settings.change"))


def test_tag_merge(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    a = make_tool(db, status="published", tags="hta", title_pt="A")
    make_tool(db, status="published", tags="hipertensão", title_pt="B")
    login(client, db, admin)
    from app.models import Tag

    hta = db.scalar(select(Tag).where(Tag.slug == "hta"))
    hip = db.scalar(select(Tag).where(Tag.slug == "hipertensao"))
    post(client, "/admin/tags/merge", {"target": str(hip.id), "source": [str(hta.id)]})
    db.expire_all()
    assert db.scalar(select(Tag).where(Tag.slug == "hta")) is None
    assert [t.label for t in db.get(Tool, a.id).tags] == ["hipertensão"]
    assert db.get(Tag, hip.id).usage_count == 2
