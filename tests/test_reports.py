import re
from datetime import timedelta

import time_machine
from sqlalchemy import select

from app.db import utcnow
from app.models import EmailOutbox, Report
from app.models.enums import ReportStatus, Role, ToolStatus
from tests.conftest import login, make_user, post
from tests.factories import make_tool

DETAILS = "A fórmula usa a versão antiga das tabelas e dá valores errados."


def _stamp(client, slug):
    html = client.get(f"/t/{slug}/report").text
    return re.search(r'name="stamp" value="([^"]+)"', html).group(1)


def _report(client, slug, **data):
    stamp = _stamp(client, slug)
    payload = {"stamp": stamp, "reason": "dangerous_content", "details": DETAILS, "good_faith": "1", **data}
    with time_machine.travel(utcnow() + timedelta(seconds=10), tick=False):
        return post(client, f"/t/{slug}/report", payload)


def test_anonymous_report_requires_email(client, db):
    tool = make_tool(db)
    r = _report(client, tool.slug)
    assert r.status_code == 422
    assert db.query(Report).count() == 0
    r = _report(client, tool.slug, email="quem@example.org")
    assert r.status_code == 303
    report = db.scalar(select(Report))
    assert report.reporter_email == "quem@example.org" and report.reporter_id is None
    assert db.scalar(
        select(EmailOutbox).where(
            EmailOutbox.template == "report_ack", EmailOutbox.to_email == "quem@example.org"
        )
    )


def test_inappropriate_material_is_a_reason_and_needs_an_email_like_any_other(client, db):
    tool = make_tool(db)
    form = client.get(f"/t/{tool.slug}/report").text
    assert "Material desadequado" in form and 'name="csam"' not in form
    assert _report(client, tool.slug, reason="inappropriate", csam="1").status_code == 422  # no exemption
    assert _report(client, tool.slug, reason="inappropriate", email="q@example.org").status_code == 303
    assert db.scalar(select(Report)).reason.value == "inappropriate"


def test_inappropriate_material_counts_towards_auto_hide(db):
    from app.models.enums import ReportReason
    from app.services import reports

    assert ReportReason.inappropriate in reports.AUTO_HIDE_REASONS


def test_honeypot_and_minimum_time(client, db):
    tool = make_tool(db)
    assert _report(client, tool.slug, email="a@example.org", website="http://spam.example").status_code == 422
    stamp = _stamp(client, tool.slug)
    r = post(
        client,
        f"/t/{tool.slug}/report",
        {"stamp": stamp, "reason": "spam", "details": DETAILS, "good_faith": "1", "email": "a@example.org"},
    )
    assert r.status_code == 422  # submitted instantly
    assert db.query(Report).count() == 0


def test_details_min_length_and_good_faith(client, db):
    tool = make_tool(db)
    assert _report(client, tool.slug, email="a@example.org", details="curto").status_code == 422
    assert _report(client, tool.slug, email="a@example.org", good_faith="").status_code == 422


def test_logged_in_report_and_outcome_email(client, db):
    tool = make_tool(db)
    user = make_user(db, "rep@example.org")
    login(client, db, user)
    assert _report(client, tool.slug).status_code == 303
    report = db.scalar(select(Report))
    assert report.reporter_id == user.id
    mod = make_user(db, "mod@example.org", Role.moderator)
    login(client, db, mod)
    post(client, f"/mod/reports/{report.id}/dismiss", {"note": "A fórmula está correta."})
    db.refresh(report)
    assert report.status == ReportStatus.dismissed and report.handled_by == mod.id
    outcome = db.scalar(select(EmailOutbox).where(EmailOutbox.template == "report_outcome"))
    assert outcome.to_email == "rep@example.org" and "A fórmula está correta." in outcome.body_text


def test_auto_hide_at_threshold_and_moderators_emailed(client, db):
    make_user(db, "mod@example.org", Role.moderator)
    tool = make_tool(db)
    for i in range(3):
        _report(client, tool.slug, email=f"r{i}@example.org")
    db.refresh(tool)
    assert tool.status == ToolStatus.hidden
    assert client.get(f"/t/{tool.slug}").status_code == 404
    assert db.scalar(
        select(EmailOutbox).where(
            EmailOutbox.template == "mod_auto_hide", EmailOutbox.to_email == "mod@example.org"
        )
    )
    hidden = db.scalar(select(EmailOutbox).where(EmailOutbox.template == "tool_hidden"))
    assert "automaticamente" in hidden.body_text


def test_other_reasons_do_not_auto_hide(client, db):
    tool = make_tool(db)
    for i in range(4):
        _report(client, tool.slug, email=f"r{i}@example.org", reason="broken_link")
    db.refresh(tool)
    assert tool.status == ToolStatus.published


def test_csam_reason_may_stay_anonymous_and_any_email_is_discarded(client, db):
    tool = make_tool(db)
    form = client.get(f"/t/{tool.slug}/report").text
    assert '<option value="csam"' in form and "Material de abuso sexual de crianças" in form
    assert "data-report-email" in form and "data-csam-note" in form
    assert _report(client, tool.slug, reason="csam").status_code == 303  # no email needed
    assert _report(client, tool.slug, reason="csam", email="quem@example.org").status_code == 303
    rows = db.scalars(select(Report)).all()
    assert [r.reason.value for r in rows] == ["csam", "csam"]
    assert all(r.reporter_email is None for r in rows)  # sent, but never kept
    assert not db.scalar(select(EmailOutbox).where(EmailOutbox.to_email == "quem@example.org"))


def test_csam_reports_come_first_in_the_moderation_queue(client, db):
    mod = make_user(db, "m@example.org", Role.moderator)
    tool = make_tool(db, moderator=mod)
    _report(
        client,
        tool.slug,
        reason="spam",
        email="a@example.org",
        details="Isto é publicidade sem relação com saúde.",
    )
    _report(client, tool.slug, reason="csam")
    login(client, db, mod)
    queue = client.get("/mod?tab=reports").text
    assert queue.index("Material de abuso sexual de crianças") < queue.index("Spam")
