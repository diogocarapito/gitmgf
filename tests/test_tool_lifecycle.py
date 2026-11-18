import pytest
from sqlalchemy import select, text

from app.models import AuditLog, EmailOutbox, Tool, ToolRevision
from app.models.enums import RevisionStatus, Role, ToolStatus
from app.services import settings_store
from app.services import tools as svc
from app.services.tools import TRANSITIONS, InvalidTransition, ToolError
from tests.conftest import login, make_user, post
from tests.factories import make_tool, tool_data, tool_form


@pytest.fixture
def people(db):
    owner = make_user(db, "owner@example.org")
    mod = make_user(db, "mod@example.org", Role.moderator)
    admin = make_user(db, "admin@example.org", Role.admin)
    other = make_user(db, "other@example.org")
    return owner, mod, admin, other


def in_index(db, tool_id: int) -> bool:
    return (
        db.execute(text("SELECT count(*) FROM tool_search WHERE rowid = :id"), {"id": tool_id}).scalar() == 1
    )


def test_full_happy_path_with_audit_and_emails(db, people):
    owner, mod, _, _ = people
    tool = make_tool(db, owner, status="draft")
    assert tool.status == ToolStatus.draft and not in_index(db, tool.id)
    svc.transition(db, tool, "submit", owner)
    assert tool.status == ToolStatus.pending and tool.submitted_at
    svc.transition(db, tool, "approve", mod)
    db.commit()
    assert tool.status == ToolStatus.published and tool.published_at and in_index(db, tool.id)
    actions = [a.action for a in db.scalars(select(AuditLog).where(AuditLog.target_id == tool.id))]
    assert {"tool.create", "tool.submit", "tool.approve"} <= set(actions)
    subjects = [m.subject for m in db.scalars(select(EmailOutbox))]
    assert any("Recebemos" in s for s in subjects) and any("publicada" in s for s in subjects)


@pytest.mark.parametrize(("start", "action", "actor_key", "end"), [
    ("pending", "withdraw", "owner", "draft"),
    ("pending", "reject", "mod", "rejected"),
    ("pending", "request_changes", "mod", "draft"),
    ("rejected", "submit", "owner", "pending"),
    ("published", "hide", "mod", "hidden"),
    ("hidden", "unhide", "mod", "published"),
    ("published", "archive", "owner", "archived"),
    ("archived", "unarchive", "owner", "published"),
    ("published", "delete", "owner", "deleted"),
    ("draft", "delete", "admin", "deleted"),
])  # fmt: skip
def test_allowed_transitions(db, people, start, action, actor_key, end):
    owner, mod, admin, _ = people
    actors = {"owner": owner, "mod": mod, "admin": admin}
    tool = make_tool(db, owner, status=start, moderator=mod)
    svc.transition(db, tool, action, actors[actor_key], reason="Motivo de teste.")
    assert tool.status == ToolStatus(end)
    assert in_index(db, tool.id) == (end == "published")


def test_every_undeclared_transition_raises(db, people):
    owner, mod, _, _ = people
    actions = {a for (_, a) in TRANSITIONS}
    for status in ("draft", "pending", "published", "rejected", "hidden", "archived"):
        tool = make_tool(db, owner, status=status, moderator=mod)
        for action in actions:
            if (tool.status, action) in TRANSITIONS:
                continue
            with pytest.raises(InvalidTransition):
                svc.transition(db, tool, action, mod, reason="x")


def test_deleted_tool_cannot_transition(db, people):
    owner, _, _, _ = people
    tool = make_tool(db, owner, status="draft")
    svc.transition(db, tool, "delete", owner)
    with pytest.raises(InvalidTransition):
        svc.transition(db, tool, "submit", owner)


def test_moderator_cannot_moderate_own_tool(db, people):
    _, mod, _, _ = people
    tool = make_tool(db, mod, status="pending")
    with pytest.raises(InvalidTransition):
        svc.transition(db, tool, "approve", mod)


def test_only_owner_can_submit_and_regular_users_cannot_approve(db, people):
    owner, _, _, other = people
    tool = make_tool(db, owner, status="draft")
    with pytest.raises(InvalidTransition):
        svc.transition(db, tool, "submit", other)
    svc.transition(db, tool, "submit", owner)
    with pytest.raises(InvalidTransition):
        svc.transition(db, tool, "approve", other)


def test_reject_and_hide_require_reason(db, people):
    owner, mod, _, _ = people
    tool = make_tool(db, owner, status="pending")
    with pytest.raises(InvalidTransition):
        svc.transition(db, tool, "reject", mod, reason="  ")
    svc.transition(db, tool, "reject", mod, reason="Ligação quebrada.")
    assert tool.rejection_reason == "Ligação quebrada."


def test_submit_requires_complete_form(db, people):
    owner, _, _, _ = people
    tool = svc.create_tool(db, owner, {"title_pt": "Só um título"}, {})
    with pytest.raises(ToolError):
        svc.transition(db, tool, "submit", owner)


def test_pending_limit(db, people):
    owner, _, _, _ = people
    settings_store.set_value(db, "limits.max_pending_per_user", 2, None)
    make_tool(db, owner, status="pending", title_pt="Um")
    make_tool(db, owner, status="pending", title_pt="Dois")
    third = make_tool(db, owner, status="draft", title_pt="Três")
    with pytest.raises(ToolError):
        svc.transition(db, third, "submit", owner)


def test_editing_published_tool_creates_revision_and_keeps_live_content(db, people):
    owner, mod, _, _ = people
    tool = make_tool(db, owner, status="published", title_pt="Título original")
    outcome = svc.save_edit(
        db, tool, owner, tool_data(db, title_pt="Título novo", summary_pt="Resumo novo."), {}, True
    )
    db.commit()
    assert outcome == "revision"
    db.refresh(tool)
    assert tool.title_pt == "Título original"  # live page unchanged
    revision = svc.pending_revision(db, tool)
    assert revision.data["title_pt"] == "Título novo"
    # a second edit updates the same pending revision
    svc.save_edit(db, tool, owner, tool_data(db, title_pt="Título novíssimo"), {}, True)
    assert db.query(ToolRevision).count() == 1
    svc.approve_revision(db, revision, mod)
    db.commit()
    assert tool.title_pt == "Título novíssimo" and revision.status == RevisionStatus.approved
    hits = db.execute(text("SELECT title_pt FROM tool_search WHERE rowid = :id"), {"id": tool.id}).scalar()
    assert hits == "Título novíssimo"


def test_rejected_revision_leaves_tool_untouched(db, people):
    owner, mod, _, _ = people
    tool = make_tool(db, owner, status="published", title_pt="Original")
    svc.save_edit(db, tool, owner, tool_data(db, title_pt="Mudado"), {}, True)
    revision = svc.pending_revision(db, tool)
    svc.reject_revision(db, revision, mod, "Alegações enganadoras.")
    db.commit()
    assert tool.title_pt == "Original" and revision.status == RevisionStatus.rejected


def test_unchanged_edit_does_not_create_revision(db, people):
    owner, _, _, _ = people
    tool = make_tool(db, owner, status="published")
    data = svc.snapshot(tool)
    data = {k: v for k, v in data.items() if k not in ("certifications", "media_order")}
    assert svc.save_edit(db, tool, owner, data, {}, True) == "unchanged"
    assert svc.pending_revision(db, tool) is None


def test_revision_diff_marks_changes(db, people):
    owner, _, _, _ = people
    tool = make_tool(db, owner, status="published", description_pt="Calcula o risco anual.")
    live = svc.snapshot(tool)
    proposed = {**live, "description_pt": "Calcula o risco a dez anos.", "tags": ["score2", "novo"]}
    diffs = {d.name: d for d in svc.diff(db, live, proposed, "pt")}
    assert "<del>anual.</del>" in diffs["description_pt"].html or "<del>" in diffs["description_pt"].html
    assert "novo" in diffs["tags"].added


def test_draft_is_invisible_to_public_and_pending_visible_to_owner_and_mods(client, db, people):
    owner, mod, _, other = people
    draft = make_tool(db, owner, status="draft", title_pt="Rascunho")
    pending = make_tool(db, owner, status="pending", title_pt="Pendente")
    for tool in (draft, pending):
        assert client.get(f"/t/{tool.slug}").status_code == 404
    login(client, db, other)
    assert client.get(f"/t/{pending.slug}").status_code == 404
    login(client, db, owner)
    assert client.get(f"/t/{pending.slug}").status_code == 200
    login(client, db, mod)
    assert client.get(f"/t/{pending.slug}").status_code == 200


def test_form_submit_flow_and_validation(client, db, people):
    owner, _, _, _ = people
    login(client, db, owner)
    r = post(
        client,
        "/me/tools/new",
        {**tool_form(db, website_url="javascript:alert(1)", repo_url=""), "intent": "save"},
    )
    assert r.status_code == 422 and "http:// ou https://" in r.text
    r = post(client, "/me/tools/new", {"title_pt": "Rascunho rápido", "intent": "save"})
    assert r.status_code == 303
    tool = db.scalar(select(Tool).where(Tool.title_pt == "Rascunho rápido"))
    assert tool.status == ToolStatus.draft
    r = post(client, f"/me/tools/{tool.id}/edit", {"title_pt": "Rascunho rápido", "intent": "submit"})
    assert (r.status_code == 422 and "Faltam" in r.text) or "obrigatório" in r.text
    r = post(
        client,
        f"/me/tools/{tool.id}/edit",
        {**tool_form(db, title_pt="Rascunho rápido"), "intent": "submit"},
    )
    assert r.status_code == 303 and "flash=submitted" in r.headers["location"]
    db.refresh(tool)
    assert tool.status == ToolStatus.pending


def test_owner_can_withdraw_archive_and_delete_via_routes(client, db, people):
    owner, mod, _, _ = people
    login(client, db, owner)
    pending = make_tool(db, owner, status="pending")
    assert post(client, f"/me/tools/{pending.id}/withdraw").status_code == 303
    db.refresh(pending)
    assert pending.status == ToolStatus.draft
    live = make_tool(db, owner, status="published", title_pt="Publicada", moderator=mod)
    post(client, f"/me/tools/{live.id}/archive")
    db.refresh(live)
    assert live.status == ToolStatus.archived
    assert client.get(f"/t/{live.slug}").status_code == 200  # still reachable with banner
    post(client, f"/me/tools/{live.id}/delete")
    db.refresh(live)
    assert live.status == ToolStatus.deleted and client.get(f"/t/{live.slug}").status_code == 404


def test_other_user_cannot_edit(client, db, people):
    owner, _, _, other = people
    tool = make_tool(db, owner, status="draft")
    login(client, db, other)
    assert client.get(f"/me/tools/{tool.id}/edit").status_code == 404
    assert post(client, f"/me/tools/{tool.id}/delete").status_code == 404


def test_tags_are_normalised_and_counted(db, people):
    owner, _, _, _ = people
    tool = make_tool(db, owner, status="published", tags="Diabetes, diabetes , HbA1c,#HTA")
    labels = sorted(t.label for t in tool.tags)
    assert labels == ["diabetes", "hba1c", "hta"]
    assert all(t.usage_count == 1 for t in tool.tags)


def test_open_source_badge_needs_osi_license_and_repo(db, people):
    owner, _, _, _ = people
    assert make_tool(db, owner, status="draft", license_spdx="MIT", title_pt="A").is_open_source
    assert not make_tool(db, owner, status="draft", license_spdx="proprietary", title_pt="B").is_open_source
    assert not make_tool(
        db, owner, status="draft", license_spdx="MIT", repo_url="", title_pt="C"
    ).is_open_source


def test_cli_admin_can_self_approve_own_pending_tool(db_path, db):
    from typer.testing import CliRunner

    from app.cli import cli

    admin = make_user(db, "admin@example.org", Role.admin)
    tool = make_tool(db, admin, status="pending", repo_url="")
    result = CliRunner().invoke(cli, ["approve-own-tool", tool.slug, "--as", "Admin@Example.org"])
    assert result.exit_code == 0, result.output
    db.expire_all()
    assert db.get(Tool, tool.id).status == ToolStatus.published
    entry = db.scalar(
        select(AuditLog).where(AuditLog.action == "tool.approve", AuditLog.target_id == tool.id)
    )
    assert entry.details["self_approved"] is True and entry.actor_id == admin.id


def test_cli_self_approval_refuses_non_admins_and_non_pending(db_path, db):
    from typer.testing import CliRunner

    from app.cli import cli

    mod = make_user(db, "mod@example.org", Role.moderator)
    pending = make_tool(db, mod, status="pending")
    assert (
        CliRunner().invoke(cli, ["approve-own-tool", pending.slug, "--as", "mod@example.org"]).exit_code == 1
    )
    admin = make_user(db, "admin@example.org", Role.admin)
    draft = make_tool(db, admin, status="draft", title_pt="Rascunho do admin")
    assert (
        CliRunner().invoke(cli, ["approve-own-tool", str(draft.id), "--as", "admin@example.org"]).exit_code
        == 1
    )


def test_self_approval_is_not_reachable_from_the_web(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    tool = make_tool(db, admin, status="pending")
    login(client, db, admin)
    assert post(client, f"/mod/tools/{tool.id}/approve").status_code == 403


def test_cli_admin_can_self_approve_own_pending_edit(db_path, db):
    from typer.testing import CliRunner

    from app.cli import cli

    admin = make_user(db, "admin@example.org", Role.admin)
    mod = make_user(db, "mod@example.org", Role.moderator)
    tool = make_tool(db, admin, status="published", title_pt="Antes", repo_url="", moderator=mod)
    svc.save_edit(db, tool, admin, tool_data(db, title_pt="Depois", repo_url=""), {}, True)
    db.commit()
    runner = CliRunner()
    result = runner.invoke(cli, ["approve-own-tool", str(tool.id), "--as", "admin@example.org"])
    assert result.exit_code == 0 and "edit approved" in result.output, result.output
    db.expire_all()
    assert db.get(Tool, tool.id).title_pt == "Depois"
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "revision.approve"))
    assert entry.details["self_approved"] is True
    again = runner.invoke(cli, ["approve-own-tool", str(tool.id), "--as", "admin@example.org"])
    assert again.exit_code == 1  # nothing pending any more


def test_support_email_is_validated_and_shown_next_to_report(client, db):
    from app.forms.tool import ToolForm
    from tests.factories import make_tool, tool_form

    raw = {k: v for k, v in tool_form(db, support_email="não é email").items() if not k.startswith("decl_")}
    raw["category_ids"] = [int(i) for i in raw["category_ids"]]
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ToolForm.model_validate(raw)
    tool = make_tool(db, support_email="Ajuda@Example.org")
    assert tool.support_email == "ajuda@example.org"
    page = client.get(f"/t/{tool.slug}").text
    assert 'href="mailto:ajuda@example.org"' in page and "Contactar suporte" in page
    assert "Reportar problema" in page
    plain = make_tool(db, title_pt="Sem suporte")
    assert "mailto:" not in client.get(f"/t/{plain.slug}").text
