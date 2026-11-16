import json
from datetime import timedelta

import time_machine
from sqlalchemy import select, text

from app.db import utcnow
from app.models import EmailOutbox, Report, Star, Tool, User, UserSession
from app.models.enums import ReportReason, ToolStatus, UserStatus
from app.services import gdpr
from app.services import reports as report_service
from app.services import tools as svc
from tests.conftest import login, make_user, post
from tests.factories import make_tool
from tests.test_media import png_with_exif


def test_export_contains_all_user_data(client, db):
    user = make_user(db, "me@example.org")
    mine = make_tool(db, user, title_pt="A minha ferramenta")
    other = make_tool(db, title_pt="De outra pessoa")
    svc.toggle_star(db, other, user)
    report_service.create(
        db,
        other,
        ReportReason.broken_link,
        "A ligação principal devolve erro 404.",
        user,
        None,
        False,
        "pt",
        None,
    )
    db.commit()
    login(client, db, user)
    r = client.get("/me/export.json")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = json.loads(r.text)
    assert data["profile"]["email"] == "me@example.org"
    assert [t["title_pt"] for t in data["tools"]] == ["A minha ferramenta"]
    assert data["stars"][0]["tool_id"] == other.id
    assert data["reports_filed"][0]["reason"] == "broken_link"
    assert mine.slug in r.text


def test_delete_account_unpublishes_tools_removes_stars_and_anonymises_reports(client, db):
    user = make_user(db, "me@example.org")
    mine = make_tool(db, user, title_pt="A minha ferramenta")
    other = make_tool(db, title_pt="De outra pessoa")
    svc.toggle_star(db, other, user)
    report_service.create(
        db,
        other,
        ReportReason.broken_link,
        "A ligação principal devolve erro 404.",
        user,
        None,
        False,
        "pt",
        None,
    )
    db.commit()
    assert other.stars_count == 1
    login(client, db, user)
    assert post(client, "/pt/me/delete-account", {}).status_code == 422  # needs confirmation
    r = post(client, "/pt/me/delete-account", {"confirm": "1"})
    assert r.status_code == 303 and "account_deleted" in r.headers["location"]
    assert 'gitmgf_session=""' in r.headers["set-cookie"] and "Max-Age=0" in r.headers["set-cookie"]
    db.expire_all()
    assert db.get(Tool, mine.id).status == ToolStatus.deleted
    assert (
        db.execute(text("SELECT count(*) FROM tool_search WHERE rowid = :id"), {"id": mine.id}).scalar() == 0
    )
    assert db.query(Star).count() == 0 and db.get(Tool, other.id).stars_count == 0
    report = db.scalar(select(Report))
    assert report.reporter_id is None and report.reporter_email is None
    deleted = db.get(User, user.id)
    assert deleted.status == UserStatus.deleted and "example.org" not in deleted.email
    assert db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all() == []
    assert db.scalar(
        select(EmailOutbox).where(
            EmailOutbox.template == "account_deleted", EmailOutbox.to_email == "me@example.org"
        )
    )
    assert client.get(f"/pt/t/{mine.slug}").status_code == 404


def test_purge_job_removes_account_tools_and_files_after_30_days(db):
    user = make_user(db, "me@example.org")
    tool = make_tool(db, user, status="draft")
    item = svc.add_media(db, tool, user, png_with_exif((640, 480)), "Ecrã", None)
    db.commit()
    from app.services import media

    path = media.tool_dir(tool.id) / item.file_name
    assert path.exists()
    gdpr.delete_account(db, user, user)
    db.commit()
    gdpr.purge(db)
    db.commit()
    assert db.get(User, user.id) is not None  # not yet
    with time_machine.travel(utcnow() + timedelta(days=31), tick=False):
        counts = gdpr.purge(db)
        db.commit()
    assert counts["users"] == 1
    db.expire_all()
    assert db.get(User, user.id) is None and db.get(Tool, tool.id) is None
    assert not path.exists()


def test_retention_prunes_old_events_and_tokens(db):
    from app.models import InteractionEvent, MagicLinkToken

    tool = make_tool(db)
    old = utcnow() - timedelta(days=181)
    db.add(
        InteractionEvent(tool_id=tool.id, kind="view", visitor_hash="x" * 32, day=old.date(), created_at=old)
    )
    db.add(MagicLinkToken(email="a@example.org", token_hash="h" * 64, expires_at=old, created_at=old))
    db.commit()
    counts = gdpr.purge(db)
    db.commit()
    assert counts["interaction_events"] == 1 and counts["magic_link_tokens"] == 1
