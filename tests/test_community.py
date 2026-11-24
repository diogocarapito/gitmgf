"""Comments, reactions, colab posts and their moderation (D41)."""

import json

from sqlalchemy import select

from app.db import utcnow
from app.models import AuditLog, Colab, Comment, CommentReaction, Notification, Report
from app.models.enums import NotificationKind, Role
from app.services import email, gdpr
from tests.conftest import login, make_user, post
from tests.factories import make_tool

BODY = "Excelente ferramenta, uso todos os dias na consulta!"
COLAB = {
    "kind": "idea",
    "title": "Calculadora de doses pediátricas",
    "body": "Gostava de ter uma ferramenta simples para calcular doses de paracetamol por peso, em ml.",
    "link_url": "",
}


def mails_to(address):
    """Community emails only (making a published tool also emails its approval)."""
    return [
        m
        for m in email.SENT
        if m["To"] == address and not m["Subject"].startswith(("Recebemos", "Ferramenta"))
    ]


def comments(db):
    db.expire_all()
    return db.scalars(select(Comment).order_by(Comment.id)).unique().all()


def notes(db, user):
    """Community notifications only (making a published tool also notifies its approval)."""
    db.expire_all()
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id)).unique().all()
    return [n for n in rows if n.kind.startswith(("comment_", "colab_"))]


def comment_on(client, tool, body=BODY, parent=None):
    data = {"body": body}
    if parent is not None:
        data["parent_id"] = str(parent.id)
    return post(client, f"/t/{tool.slug}/comments", data)


# ---------- comments on tools ----------


def test_signed_in_users_comment_and_the_owner_is_notified_in_app_and_by_email(client, db):
    tool = make_tool(db)
    assert comment_on(client, tool).status_code == 403  # anonymous
    page = client.get(f"/t/{tool.slug}").text
    assert 'id="comentarios"' in page and "Inicia sessão" in page
    fan = make_user(db, "fan@example.org", name="Rui Fã")
    login(client, db, fan)
    r = comment_on(client, tool)
    assert r.status_code == 303 and "flash=commented#comment-" in r.headers["location"]
    page = client.get(f"/t/{tool.slug}").text
    assert BODY in page and "Rui Fã" in page
    [n] = notes(db, tool.owner)
    assert n.kind == NotificationKind.comment_new and n.actor_id == fan.id and n.message == BODY
    [mail] = mails_to(tool.owner.email)
    assert "Novo comentário" in mail["Subject"] and BODY in mail.get_body(("plain",)).get_content()


def test_owner_comment_gets_author_badge_and_no_self_notification(client, db):
    tool = make_tool(db)
    login(client, db, tool.owner)
    comment_on(client, tool, "Obrigado a todos pelo feedback!")
    assert notes(db, tool.owner) == []
    page = client.get(f"/t/{tool.slug}").text
    assert '<span class="badge badge--oss">Autor</span>' in page


def test_replies_stay_one_level_and_notify_the_parent_author(client, db):
    tool = make_tool(db)
    first = make_user(db, "first@example.org")
    second = make_user(db, "second@example.org")
    login(client, db, first)
    comment_on(client, tool)
    top = comments(db)[0]
    login(client, db, second)
    comment_on(client, tool, "Concordo totalmente.", parent=top)
    reply = comments(db)[1]
    comment_on(client, tool, "E mais uma coisa.", parent=reply)  # reply to a reply joins the same thread
    assert [c.parent_id for c in comments(db)] == [None, top.id, top.id]
    kinds = sorted(n.kind.value for n in notes(db, first))
    assert kinds == ["comment_reply", "comment_reply"]
    assert {n.kind for n in notes(db, tool.owner)} == {NotificationKind.comment_new}


def test_mentions_link_to_profiles_notify_and_text_is_escaped(client, db):
    tool = make_tool(db)
    ana = make_user(db, "ana-silva@example.org", name="Ana Silva")
    login(client, db, make_user(db, "rui@example.org"))
    comment_on(
        client, tool, "@ana-silva olha isto <script>alert(1)</script> e @ninguem-aqui https://example.org/x"
    )
    page = client.get(f"/t/{tool.slug}").text
    assert '<a class="mention" href="/u/ana-silva">@ana-silva</a>' in page
    assert "@ninguem-aqui" in page and 'href="/u/ninguem-aqui"' not in page
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert 'href="https://example.org/x" rel="nofollow ugc noopener noreferrer"' in page
    [n] = notes(db, ana)
    assert n.kind == NotificationKind.comment_mention
    assert "mencionou-te" in mails_to(ana.email)[0]["Subject"]


def test_email_opt_out_keeps_the_in_app_notification(client, db):
    tool = make_tool(db)
    login(client, db, tool.owner)
    assert post(client, "/me/email-preferences", {}).status_code == 303
    db.refresh(tool.owner)
    assert tool.owner.email_on_comments is False
    login(client, db, make_user(db, "fan@example.org"))
    comment_on(client, tool)
    assert len(notes(db, tool.owner)) == 1 and mails_to(tool.owner.email) == []


def test_authors_edit_and_delete_their_own_comments_only(client, db):
    tool = make_tool(db)
    author = make_user(db, "author@example.org")
    login(client, db, author)
    comment_on(client, tool)
    c = comments(db)[0]
    assert post(client, f"/comments/{c.id}/edit", {"body": "Texto corrigido."}).status_code == 303
    db.refresh(c)
    assert c.body == "Texto corrigido." and c.edited_at is not None
    login(client, db, tool.owner)  # the tool owner can't silence a comment: only report it
    assert post(client, f"/comments/{c.id}/delete").status_code == 404
    assert post(client, f"/comments/{c.id}/edit", {"body": "Hack"}).status_code == 404
    login(client, db, author)
    assert post(client, f"/comments/{c.id}/delete").status_code == 303
    assert comments(db) == []


def test_deleted_comment_with_replies_leaves_a_tombstone(client, db):
    tool = make_tool(db)
    author = make_user(db, "author@example.org")
    login(client, db, author)
    comment_on(client, tool, "Comentário original que vai ser apagado.")
    top = comments(db)[0]
    login(client, db, make_user(db, "other@example.org"))
    comment_on(client, tool, "Uma resposta.", parent=top)
    login(client, db, author)
    post(client, f"/comments/{top.id}/delete")
    db.refresh(top)
    assert top.deleted_at is not None and top.body == "" and top.author_id is None
    page = client.get(f"/t/{tool.slug}").text
    assert "Comentário eliminado." in page and "Uma resposta." in page


def test_archived_tools_keep_comments_read_only(client, db):
    tool = make_tool(db, status="archived")
    login(client, db, make_user(db, "fan@example.org"))
    assert comment_on(client, tool).status_code == 403
    assert "os comentários estão fechados" in client.get(f"/t/{tool.slug}").text


def test_validation_errors_keep_the_text(client, db):
    tool = make_tool(db)
    login(client, db, make_user(db, "fan@example.org"))
    r = comment_on(client, tool, "x" * 2001)
    assert r.status_code == 422 and "x" * 50 in r.text and "demasiado longo" in r.text


# ---------- reactions ----------


def test_reactions_toggle_and_return_a_partial_for_htmx(client, db):
    tool = make_tool(db)
    login(client, db, make_user(db, "a@example.org"))
    comment_on(client, tool)
    c = comments(db)[0]
    client.cookies.clear()
    r = post(client, f"/comments/{c.id}/react", {"emoji": "heart"})
    assert r.status_code == 303 and "/login" in r.headers["location"]
    login(client, db, make_user(db, "b@example.org"))
    r = post(client, f"/comments/{c.id}/react", {"emoji": "heart"}, headers={"HX-Request": "true"})
    assert r.status_code == 200 and f'id="reactions-{c.id}"' in r.text and 'aria-pressed="true"' in r.text
    assert db.scalar(select(CommentReaction).where(CommentReaction.comment_id == c.id)) is not None
    post(client, f"/comments/{c.id}/react", {"emoji": "heart"})
    db.expire_all()
    assert db.scalar(select(CommentReaction)) is None
    assert post(client, f"/comments/{c.id}/react", {"emoji": "poop"}).status_code == 422


# ---------- account restrictions ----------


def test_social_block_stops_comments_and_reactions(client, db):
    tool = make_tool(db)
    login(client, db, make_user(db, "a@example.org"))
    comment_on(client, tool)
    c = comments(db)[0]
    blocked = make_user(db, "blocked@example.org")
    blocked.social_blocked_at = utcnow()
    db.commit()
    login(client, db, blocked)
    assert comment_on(client, tool).status_code == 403
    assert post(client, f"/comments/{c.id}/react", {"emoji": "heart"}).status_code == 403
    assert "não pode comentar nem reagir" in client.get(f"/t/{tool.slug}").text


def test_publish_block_stops_new_colabs(client, db):
    user = make_user(db, "a@example.org")
    user.publish_blocked_at = utcnow()
    user.publish_blocked_reason = "Spam repetido."
    db.commit()
    login(client, db, user)
    r = client.get("/colabs/new")
    assert r.status_code == 403 and "Spam repetido." in r.text
    assert post(client, "/colabs/new", COLAB).status_code == 403


# ---------- colabs ----------


def test_colab_lifecycle(client, db):
    author = make_user(db, "author@example.org")
    assert client.get("/colabs/new").status_code == 303  # sign in first
    login(client, db, author)
    r = post(client, "/colabs/new", {**COLAB, "title": "curto"})
    assert r.status_code == 422
    r = post(client, "/colabs/new", COLAB)
    assert r.status_code == 303
    colab = db.scalar(select(Colab))
    assert r.headers["location"] == f"/colabs/{colab.id}?flash=colab_posted"
    listing = client.get("/colabs").text
    assert COLAB["title"] in listing
    assert COLAB["title"] not in client.get("/colabs?status=resolved").text
    assert COLAB["title"] not in client.get("/colabs?kind=help").text
    assert COLAB["title"] in client.get("/en/colabs?kind=idea").text
    page = client.get(f"/colabs/{colab.id}").text
    assert COLAB["body"] in page and "Marcar como resolvida" in page
    assert post(client, f"/colabs/{colab.id}/resolve").status_code == 303
    assert COLAB["title"] in client.get("/colabs?status=resolved").text
    login(client, db, make_user(db, "other@example.org"))
    assert client.get(f"/colabs/{colab.id}/edit").status_code == 404
    assert post(client, f"/colabs/{colab.id}/delete").status_code == 404
    assert post(client, f"/colabs/{colab.id}/comments", {"body": "Posso ajudar!"}).status_code == 303
    assert [n.kind for n in notes(db, author)] == [NotificationKind.comment_new]
    login(client, db, author)
    assert post(client, f"/colabs/{colab.id}/delete").status_code == 303
    assert client.get(f"/colabs/{colab.id}").status_code == 404


def test_colab_can_only_attach_the_authors_own_tools(client, db):
    author = make_user(db, "author@example.org")
    mine = make_tool(db, author, title_pt="A minha")
    theirs = make_tool(db, title_pt="De outra pessoa")
    login(client, db, author)
    assert (
        post(client, "/colabs/new", {**COLAB, "kind": "feedback", "tool_id": str(theirs.id)}).status_code
        == 422
    )
    assert (
        post(client, "/colabs/new", {**COLAB, "kind": "feedback", "tool_id": str(mine.id)}).status_code == 303
    )
    assert db.scalar(select(Colab)).tool_id == mine.id


# ---------- moderation and reports ----------


def test_moderator_hides_a_comment_with_a_reason(client, db):
    tool = make_tool(db)
    author = make_user(db, "author@example.org")
    login(client, db, author)
    comment_on(client, tool, "Conteúdo ofensivo aqui.")
    c = comments(db)[0]
    mod = make_user(db, "mod@example.org", role=Role.moderator)
    login(client, db, mod)
    assert client.get(f"/mod/comments/{c.id}").status_code == 200
    r = post(client, f"/mod/comments/{c.id}/hide", {"reason": "curto"})
    assert "reason_required" in r.headers["location"]
    post(
        client,
        f"/mod/comments/{c.id}/hide",
        {"reason": "Linguagem ofensiva, contrária às regras (Termos §6)."},
    )
    db.refresh(c)
    assert c.hidden_at is not None and c.hidden_by == mod.id
    assert db.scalar(select(AuditLog).where(AuditLog.action == "comment.hide")) is not None
    assert [n.kind for n in notes(db, author)] == [NotificationKind.comment_hidden]
    assert "Comentário ocultado" in mails_to(author.email)[0]["Subject"]
    client.cookies.clear()
    assert "Conteúdo ofensivo" not in client.get(f"/t/{tool.slug}").text
    login(client, db, author)
    assert "Linguagem ofensiva" in client.get(f"/t/{tool.slug}").text  # the author sees why
    login(client, db, mod)
    post(client, f"/mod/comments/{c.id}/unhide")
    db.refresh(c)
    assert c.hidden_at is None


def test_moderators_cannot_moderate_comments_under_their_own_tool(client, db):
    mod = make_user(db, "mod@example.org", role=Role.moderator)
    tool = make_tool(db, mod, moderator=make_user(db, "admin@example.org", role=Role.admin))
    login(client, db, make_user(db, "critic@example.org"))
    comment_on(client, tool, "Crítica legítima à ferramenta.")
    c = comments(db)[0]
    login(client, db, mod)
    assert (
        post(client, f"/mod/comments/{c.id}/hide", {"reason": "Não gosto desta crítica."}).status_code == 403
    )
    assert "Não podes moderar" in client.get(f"/mod/comments/{c.id}").text


def test_comments_and_colabs_can_be_reported_and_handled(client, db):
    tool = make_tool(db)
    login(client, db, make_user(db, "a@example.org"))
    comment_on(client, tool, "Spam: compra já em example.com")
    c = comments(db)[0]
    reporter = make_user(db, "reporter@example.org")
    login(client, db, reporter)
    form = client.get(f"/comments/{c.id}/report").text
    assert "Denunciar comentário" in form and "Ligação quebrada" not in form
    import re

    stamp = re.search(r'name="stamp" value="([^"]+)"', form).group(1)
    import time_machine

    with time_machine.travel(utcnow().timestamp() + 10):
        r = post(
            client,
            f"/comments/{c.id}/report",
            {
                "reason": "spam",
                "details": "Publicidade sem relação com a ferramenta.",
                "good_faith": "1",
                "stamp": stamp,
            },
        )
    assert r.status_code == 303 and r.headers["location"] == f"/t/{tool.slug}?flash=reported"
    report = db.scalar(select(Report))
    assert report.comment_id == c.id and report.tool_id is None
    mod = make_user(db, "mod@example.org", role=Role.moderator)
    login(client, db, mod)
    queue = client.get("/mod?tab=reports").text
    assert "comentário" in queue and tool.title_pt in queue
    page = client.get(f"/mod/reports/{report.id}").text
    assert "Abrir moderação do comentário" in page
    assert post(client, f"/mod/reports/{report.id}/resolve", {"note": "Removido."}).status_code == 303


def test_hidden_colab_is_gone_for_the_public_but_not_for_its_author(client, db):
    author = make_user(db, "author@example.org")
    login(client, db, author)
    post(client, "/colabs/new", COLAB)
    colab = db.scalar(select(Colab))
    login(client, db, make_user(db, "mod@example.org", role=Role.moderator))
    post(client, f"/mod/colabs/{colab.id}/hide", {"reason": "Pedido com dados de utentes identificáveis."})
    db.refresh(colab)
    assert colab.status == "hidden"
    client.cookies.clear()
    assert client.get(f"/colabs/{colab.id}").status_code == 404
    assert COLAB["title"] not in client.get("/colabs?status=all").text
    login(client, db, author)
    page = client.get(f"/colabs/{colab.id}").text
    assert "dados de utentes identificáveis" in page
    assert [n.kind for n in notes(db, author)] == [NotificationKind.colab_hidden]


def test_notifications_page_lists_comment_activity(client, db):
    tool = make_tool(db)
    login(client, db, make_user(db, "fan@example.org", name="Rui Fã"))
    comment_on(client, tool)
    login(client, db, tool.owner)
    page = client.get("/me/notifications").text
    assert "Novo comentário" in page and "Rui Fã" in page and "Ver e responder" in page


# ---------- GDPR ----------


def test_export_and_account_deletion_cover_community_data(client, db):
    tool = make_tool(db)
    user = make_user(db, "me@example.org")
    login(client, db, user)
    comment_on(client, tool)
    post(client, "/colabs/new", COLAB)
    c = comments(db)[0]
    post(client, f"/comments/{c.id}/react", {"emoji": "tada"})
    data = json.loads(client.get("/me/export.json").text)
    assert data["comments"][0]["body"] == BODY
    assert data["colabs"][0]["title"] == COLAB["title"]
    assert data["reactions"][0]["emoji"] == "tada"
    gdpr.delete_account(db, user, user)
    db.commit()
    assert comments(db) == []
    assert db.scalar(select(CommentReaction)) is None
    assert db.scalar(select(Colab)).status == "deleted"
