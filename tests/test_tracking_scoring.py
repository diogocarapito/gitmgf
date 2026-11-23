import math
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.db import today
from app.models import InteractionEvent, SearchQuery, ToolDailyStat
from app.models.enums import EventKind, Role
from app.services import scoring, settings_store, tracking
from tests.conftest import login, make_user, post
from tests.factories import make_tool

BROWSER = {"user-agent": "Mozilla/5.0 (Macintosh) Firefox/140"}


def events(db, kind=None):
    query = select(InteractionEvent)
    if kind:
        query = query.where(InteractionEvent.kind == kind)
    return db.scalars(query).all()


@pytest.mark.parametrize(("age", "expected"), [(0, 1.0), (30, 0.5), (60, 0.25)])
def test_decay_half_life(age, expected):
    assert math.isclose(scoring.decay(age, 30), expected)


def test_outbound_redirect_uses_stored_url_and_dedupes_per_day(client, db):
    tool = make_tool(db, website_url="https://example.org/app")
    r = client.get(f"/go/{tool.id}/website", headers=BROWSER)
    assert r.status_code == 302 and r.headers["location"] == "https://example.org/app"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-store"
    client.get(f"/go/{tool.id}/website", headers=BROWSER)
    assert len(events(db, EventKind.outbound_click)) == 1


def test_no_open_redirect(client, db):
    draft = make_tool(db, status="draft", title_pt="Rascunho")
    published = make_tool(db, title_pt="Publicada", docs_url=None)
    assert client.get(f"/go/{draft.id}/website").status_code == 404
    assert client.get(f"/go/{published.id}/docs").status_code == 404  # no stored URL of that kind
    assert client.get(f"/go/{published.id}/evil").status_code == 404
    assert client.get("/go/99999/website").status_code == 404


def test_owner_and_bots_are_not_counted(client, db):
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner)
    client.get(f"/go/{tool.id}/website", headers={"user-agent": "Googlebot/2.1"})
    client.get(f"/go/{tool.id}/website", headers={"user-agent": ""})
    login(client, db, owner)
    client.get(f"/go/{tool.id}/website", headers=BROWSER)
    client.get(f"/t/{tool.slug}", headers=BROWSER)
    assert events(db) == []


@pytest.mark.parametrize("role", ["moderator", "admin"])
def test_moderators_and_admins_are_not_counted_on_any_tool(client, db, role):
    tool = make_tool(db, website_url="https://example.org/app")
    staff = make_user(db, f"{role}@example.org", role=Role(role))
    login(client, db, staff)
    client.get(f"/t/{tool.slug}", headers=BROWSER)
    client.get(f"/go/{tool.id}/website", headers=BROWSER)
    assert events(db) == []


def test_other_signed_in_members_are_counted(client, db):
    tool = make_tool(db, website_url="https://example.org/app")
    login(client, db, make_user(db, "member@example.org"))
    client.get(f"/t/{tool.slug}", headers=BROWSER)
    client.get(f"/go/{tool.id}/website", headers=BROWSER)
    assert {e.kind for e in events(db)} == {EventKind.view, EventKind.outbound_click}


def test_search_click_is_recorded_only_for_real_search_ids(client, db):
    tool = make_tool(db, title_pt="Calculadora de vacinas")
    html = client.get("/search?q=vacinas", headers=BROWSER).text
    query = db.scalar(select(SearchQuery))
    assert query is not None and query.results_count == 1
    assert f"/r/{query.id}/{tool.id}?pos=0" in html
    r = client.get(f"/r/{query.id}/{tool.id}?pos=0", headers=BROWSER)
    assert r.status_code == 302 and r.headers["location"] == f"/t/{tool.slug}"
    client.get(f"/r/01ARZ3NDEKTSV4RRFFQ69G5FAV/{tool.id}", headers=BROWSER)  # well-formed but unknown
    assert len(events(db, EventKind.search_click)) == 1


def test_keystrokes_refine_the_same_search_row(client, db):
    make_tool(db, title_pt="Diabetes tipo 2")
    for q in ("di", "dia", "diab", "diabetes"):
        client.get(f"/search?q={q}", headers=BROWSER)
    rows = db.scalars(select(SearchQuery)).all()
    assert len(rows) == 1 and rows[0].q == "diabetes"


def test_zero_result_searches_are_logged(client, db):
    client.get("/search?q=inexistentexyz", headers=BROWSER)
    assert db.scalar(select(SearchQuery)).results_count == 0


def test_daily_salt_rotation_changes_visitor_hash(client, db):
    class Req:
        headers = {"user-agent": "Mozilla"}
        client = type("C", (), {"host": "203.0.113.7"})()

    first = tracking.visitor_hash(db, Req())
    tracking.rotate_salt(db)
    db.commit()
    assert tracking.visitor_hash(db, Req()) != first
    assert "203.0.113.7" not in str(db.execute(select(InteractionEvent)).all())


def test_score_job_aggregates_and_blends_signals(client, db):
    fan = make_user(db, "fan@example.org")
    tool = make_tool(db)
    tool.github.stars = 99
    db.commit()
    client.get(f"/go/{tool.id}/website", headers=BROWSER)
    login(client, db, fan)
    post(client, f"/t/{tool.id}/star")
    scoring.recompute(db)
    db.commit()
    db.refresh(tool)
    stat = db.get(ToolDailyStat, (tool.id, today()))
    assert stat.outbound_clicks == 1
    expected = 2 * 1 + 4 * 1 + 5 * math.log10(100)
    assert math.isclose(tool.score, expected) and math.isclose(tool.score_log, math.log1p(expected))


def test_score_decays_and_respects_reset(db):
    tool = make_tool(db)
    tool.github = None
    db.add(
        ToolDailyStat(
            tool_id=tool.id, day=today() - timedelta(days=30), search_clicks=10, outbound_clicks=0, views=0
        )
    )
    db.commit()
    scoring.recompute(db)
    db.refresh(tool)
    assert math.isclose(tool.score, 3 * 10 * 0.5)
    from app.db import utcnow

    tool.score_reset_at = utcnow()
    db.commit()
    scoring.recompute(db)
    db.refresh(tool)
    assert tool.score == 0


def test_weights_are_tunable(db):
    tool = make_tool(db)
    tool.github = None
    db.add(ToolDailyStat(tool_id=tool.id, day=today(), search_clicks=1, outbound_clicks=0, views=0))
    settings_store.set_value(db, "score.w_search_click", 10, None)
    db.commit()
    scoring.recompute(db, on=date.today())
    db.refresh(tool)
    assert math.isclose(tool.score, 10)


def test_star_toggle_updates_count(client, db):
    tool = make_tool(db)
    fan = make_user(db, "fan@example.org")
    login(client, db, fan)
    post(client, f"/t/{tool.id}/star", headers={"HX-Request": "true"})
    db.refresh(tool)
    assert tool.stars_count == 1
    r = post(client, f"/t/{tool.id}/star", headers={"HX-Request": "true"})
    db.refresh(tool)
    assert tool.stars_count == 0 and 'aria-pressed="false"' in r.text
