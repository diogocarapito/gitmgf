from sqlalchemy import select

from app.models import Notification
from app.models.enums import NotificationKind, Role, ToolStatus
from app.services import notifications
from app.services import tools as svc
from tests.conftest import login, make_user, post
from tests.factories import make_tool, tool_data


def _badge(html: str) -> str | None:
    marker = '<span class="notif-badge" aria-hidden="true">'
    if marker not in html:
        return None
    return html.split(marker, 1)[1].split("<", 1)[0]


def test_approval_posts_notification_with_suggestions_and_badge(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner, status="pending", title_pt="Calculadora SCORE2")
    login(client, db, mod)
    checks = {"check": svc.review_checklist_keys(tool)}
    post(client, f"/mod/tools/{tool.id}/approve", {"suggestions": "Juntar capturas de ecrã.", **checks})
    note = db.scalar(select(Notification).where(Notification.user_id == owner.id))
    assert note.kind == NotificationKind.tool_approved and note.message == "Juntar capturas de ecrã."
    login(client, db, owner)
    assert _badge(client.get("/").text) == "1"
    page = client.get("/me/notifications").text
    assert "Publicada" in page and "Juntar capturas de ecrã." in page and "Nova" in page
    assert _badge(client.get("/").text) is None  # opening the page marks it read


def test_request_changes_and_revision_rejection_notify_with_reason(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    owner = make_user(db, "o@example.org")
    pending = make_tool(db, owner, status="pending")
    login(client, db, mod)
    post(client, f"/mod/tools/{pending.id}/request-changes", {"reason_text": "Falta a licença."})
    published = make_tool(db, owner, status="published", title_pt="Outra", moderator=mod)
    svc.save_edit(db, published, owner, tool_data(db, description_pt="Texto novo e mais longo."), {}, True)
    db.commit()
    revision = svc.pending_revision(db, published)
    post(client, f"/mod/revisions/{revision.id}/reject", {"reason_text": "Ligação partida."})
    kinds = {
        n.kind: n.message for n in db.scalars(select(Notification).where(Notification.user_id == owner.id))
    }
    assert kinds[NotificationKind.tool_changes_requested] == "Falta a licença."
    assert kinds[NotificationKind.revision_rejected] == "Ligação partida."
    login(client, db, owner)
    page = client.get("/me/notifications").text
    assert "Alterações pedidas" in page and "Alteração rejeitada" in page and "Editar ficha" in page


def test_moderators_see_queue_as_todos_excluding_their_own_tools(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    make_tool(db, status="pending")
    make_tool(db, mod, status="pending")  # the moderator's own: someone else reviews it
    assert notifications.todos(db, mod) == {"new": 1, "edits": 0, "reports": 0}
    login(client, db, mod)
    assert _badge(client.get("/").text) == "1"
    page = client.get("/me/notifications").text
    assert "1 ferramenta nova por aprovar" in page
    assert _badge(client.get("/").text) == "1"  # to-dos stay until the queue is handled
    regular = make_user(db, "u@example.org")
    assert notifications.todos(db, regular) == {}


def test_only_the_recipient_can_remove_a_notification(client, db):
    owner = make_user(db, "o@example.org")
    other = make_user(db, "x@example.org")
    tool = make_tool(db, owner, status="published")
    note = notifications.notify(db, owner, NotificationKind.tool_unhidden, tool)
    db.commit()
    note_id = note.id
    login(client, db, other)
    assert post(client, f"/me/notifications/decisions/{note_id}/delete").status_code == 404
    login(client, db, owner)
    assert post(client, f"/me/notifications/decisions/{note_id}/delete").status_code == 303
    db.expire_all()
    assert db.get(Notification, note_id) is None
    assert tool.status == ToolStatus.published
