from datetime import date, timedelta

import httpx
import respx
import time_machine
from sqlalchemy import select

from app import jobs
from app.db import utcnow
from app.models import AuditLog, EmailOutbox, ToolDailyStat
from app.models.enums import EmailStatus, Role
from app.services import email, github, stats
from tests.conftest import login, make_user
from tests.factories import make_tool

MDR_IIA = {
    "class": "IIa",
    "nb_number": "0123",
    "certificate_no": "C-1",
    "valid_until": "2028-05-01",
    "evidence_url": "https://nb.example/c",
}
CE = {"legal_basis": "MDR", "manufacturer": "ACME", "evidence_url": "https://acme.example/doc"}


def test_parse_repo_url():
    assert github.parse_repo_url("https://github.com/org/repo") == ("org", "repo")
    assert github.parse_repo_url("https://github.com/org/repo.git/") == ("org", "repo")
    assert github.parse_repo_url("https://gitlab.com/org/repo") is None
    assert github.parse_repo_url("https://github.com/org") is None


@respx.mock
def test_github_sync_updates_and_handles_errors(db):
    tool = make_tool(db, repo_url="https://github.com/example/score2")
    other = make_tool(db, title_pt="Outra", repo_url="https://github.com/example/missing")
    respx.get("https://api.github.com/repos/example/score2").mock(
        return_value=httpx.Response(
            200,
            json={
                "stargazers_count": 12,
                "forks_count": 3,
                "open_issues_count": 1,
                "pushed_at": "2026-10-01T10:00:00Z",
                "license": {"spdx_id": "MIT"},
                "archived": False,
                "default_branch": "main",
            },
            headers={"etag": 'W/"abc"'},
        )
    )
    respx.get("https://api.github.com/repos/example/missing").mock(return_value=httpx.Response(404))
    counts = github.sync_all(db, delay=0)
    db.refresh(tool)
    db.refresh(other)
    assert counts == {"updated": 1, "not_found": 1}
    assert tool.github.stars == 12 and tool.github.license_spdx == "MIT" and tool.github.etag == 'W/"abc"'
    assert other.github.last_error == "not_found"
    # second run sends If-None-Match and accepts 304
    route = respx.get("https://api.github.com/repos/example/score2").mock(return_value=httpx.Response(304))
    github.sync_all(db, tool_id=tool.id, delay=0)
    assert route.calls.last.request.headers["if-none-match"] == 'W/"abc"'


def test_maintained_and_archived_badges(db):
    from app.services.badges import derived_badges

    tool = make_tool(db)
    tool.github.pushed_at = utcnow() - timedelta(days=10)
    assert ("maintained", "Mantida") in derived_badges(tool)
    tool.github.archived = True
    assert ("archived", "Arquivada") in derived_badges(tool)


def test_outbox_retries_with_backoff_then_sends(db, monkeypatch):
    email.enqueue(db, "a@example.org", "welcome", {"name": "Ana"}, "pt")
    db.commit()
    calls = {"n": 0}

    def flaky(msg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("smtp down")

    monkeypatch.setattr(email, "_send", flaky)
    assert email.deliver_queued(db) == 0
    row = db.scalar(select(EmailOutbox))
    assert row.status == EmailStatus.failed and row.attempts == 1 and "smtp down" in row.last_error
    assert email.deliver_queued(db) == 0  # backoff: not due yet
    with time_machine.travel(utcnow() + timedelta(minutes=5), tick=False):
        assert email.deliver_queued(db) == 1
    db.refresh(row)
    assert row.status == EmailStatus.sent and row.sent_at


def test_email_message_is_bilingual_multipart(db):
    row = email.enqueue(
        db, "a@example.org", "magic_link", {"link": "https://x/auth/magic/t", "minutes": 15}, "en"
    )
    msg = email.build_message(row)
    assert msg["Subject"] == "Your gitmgf sign-in link"
    assert msg.get_body(preferencelist=("html",)) is not None
    assert "https://x/auth/magic/t" in msg.get_body(preferencelist=("plain",)).get_content()


def test_cert_expiry_warns_at_t30_and_on_expiry(db):
    tool = make_tool(db, claims={"mdr": MDR_IIA, "ce": CE})
    with time_machine.travel(date(2028, 4, 5), tick=False):
        assert jobs.cert_expiry() == {"expiring": 1, "expired": 0}
        assert jobs.cert_expiry() == {"expiring": 0, "expired": 0}  # only once
    with time_machine.travel(date(2028, 5, 2), tick=False):
        assert jobs.cert_expiry() == {"expiring": 0, "expired": 1}
        assert jobs.cert_expiry()["expired"] == 0
    db.expire_all()
    templates = [
        r.template for r in db.scalars(select(EmailOutbox).where(EmailOutbox.template.like("cert_%")))
    ]
    assert templates == ["cert_expiring", "cert_expired"]
    assert db.scalar(select(AuditLog).where(AuditLog.action == "cert.expired")).details["tool_id"] == tool.id


def test_mod_digest_only_when_queue_not_empty(db):
    make_user(db, "mod@example.org", Role.moderator)
    assert jobs.mod_digest() == 0
    make_tool(db, status="pending")
    assert jobs.mod_digest() == 1
    db.expire_all()
    digest = db.scalar(select(EmailOutbox).where(EmailOutbox.template == "mod_digest"))
    assert digest.to_email == "mod@example.org" and "1" in digest.subject


def test_jobs_run_without_errors(db):
    make_tool(db)
    assert jobs.recompute_scores() >= 1
    jobs.rotate_salt()
    assert "interaction_events" in jobs.prune()
    jobs.heartbeat()  # no URL configured: no-op


def test_usage_stats_for_authors(client, db):
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner)
    today = utcnow().date()
    db.add(ToolDailyStat(tool_id=tool.id, day=today, search_clicks=2, outbound_clicks=3, views=7))
    db.add(
        ToolDailyStat(
            tool_id=tool.id, day=today - timedelta(days=60), search_clicks=5, outbound_clicks=0, views=1
        )
    )
    db.commit()
    usage = stats.usage_for(db, [tool.id])[tool.id]
    assert usage["search_30"] == 2 and usage["search_90"] == 7 and usage["views_30"] == 7
    login(client, db, owner)
    page = client.get(f"/pt/me/tools/{tool.id}/stats")
    assert page.status_code == 200 and "Estatísticas" in page.text
    assert "2 / 7" in client.get("/pt/me/tools").text
