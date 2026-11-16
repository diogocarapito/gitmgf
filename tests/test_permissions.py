"""PRD role matrix (TECH_SPEC §6.5): visitor / user / owner / moderator / admin × routes."""

import pytest

from app.models.enums import Role
from tests.conftest import login, make_user, post
from tests.factories import make_tool

ACTORS = ("visitor", "user", "owner", "mod", "admin")


@pytest.fixture
def world(db):
    owner = make_user(db, "owner@example.org")
    people = {
        "owner": owner,
        "user": make_user(db, "user@example.org"),
        "mod": make_user(db, "mod@example.org", Role.moderator),
        "admin": make_user(db, "admin@example.org", Role.admin),
    }
    tools = {
        "published": make_tool(db, owner, status="published", title_pt="Publicada", moderator=people["mod"]),
        "pending": make_tool(db, owner, status="pending", title_pt="Pendente"),
        "draft": make_tool(db, owner, status="draft", title_pt="Rascunho"),
        "hidden": make_tool(db, owner, status="hidden", title_pt="Oculta", moderator=people["mod"]),
    }
    return people, tools


def as_actor(client, db, people, actor):
    if actor != "visitor":
        login(client, db, people[actor])


# (method, path template, expected status per actor)
MATRIX = [
    ("GET", "/", dict.fromkeys(ACTORS, 200)),
    ("GET", "/search?q=publicada", dict.fromkeys(ACTORS, 200)),
    ("GET", "/t/{published}", dict.fromkeys(ACTORS, 200)),
    ("GET", "/t/{pending}", {"visitor": 404, "user": 404, "owner": 200, "mod": 200, "admin": 200}),
    ("GET", "/t/{draft}", {"visitor": 404, "user": 404, "owner": 200, "mod": 200, "admin": 200}),
    ("GET", "/t/{hidden}", {"visitor": 404, "user": 404, "owner": 200, "mod": 200, "admin": 200}),
    ("GET", "/t/{published}/report", dict.fromkeys(ACTORS, 200)),
    ("GET", "/t/{pending}/report", dict.fromkeys(ACTORS, 404)),
    ("POST", "/t/{published_id}/star", {"visitor": 303, "user": 303, "owner": 403, "mod": 303, "admin": 303}),
    ("GET", "/me/tools", {"visitor": 303, "user": 200, "owner": 200, "mod": 200, "admin": 200}),
    ("GET", "/me/stars", {"visitor": 303, "user": 200, "owner": 200, "mod": 200, "admin": 200}),
    ("GET", "/me/settings", {"visitor": 303, "user": 200, "owner": 200, "mod": 200, "admin": 200}),
    ("GET", "/me/export.json", {"visitor": 303, "user": 200, "owner": 200, "mod": 200, "admin": 200}),
    (
        "GET",
        "/me/tools/{draft_id}/edit",
        {"visitor": 303, "user": 404, "owner": 200, "mod": 404, "admin": 200},
    ),
    (
        "POST",
        "/me/tools/{draft_id}/submit",
        {"visitor": 403, "user": 404, "owner": 303, "mod": 404, "admin": 409},
    ),
    (
        "POST",
        "/me/tools/{published_id}/archive",
        {"visitor": 403, "user": 404, "owner": 303, "mod": 404, "admin": 409},
    ),
    ("GET", "/mod", {"visitor": 303, "user": 404, "owner": 404, "mod": 200, "admin": 200}),
    (
        "GET",
        "/mod/tools/{pending_id}",
        {"visitor": 303, "user": 404, "owner": 404, "mod": 200, "admin": 200},
    ),
    (
        "POST",
        "/mod/tools/{pending_id}/approve",
        {"visitor": 403, "user": 404, "owner": 404, "mod": 303, "admin": 303},
    ),
    (
        "POST",
        "/mod/tools/{published_id}/reset-score",
        {"visitor": 403, "user": 404, "owner": 404, "mod": 303, "admin": 303},
    ),
    ("GET", "/admin", {"visitor": 303, "user": 404, "owner": 404, "mod": 200, "admin": 200}),
    ("GET", "/admin/searches", {"visitor": 303, "user": 404, "owner": 404, "mod": 200, "admin": 200}),
    ("GET", "/admin/users", {"visitor": 303, "user": 404, "owner": 404, "mod": 404, "admin": 200}),
    ("GET", "/admin/categories", {"visitor": 303, "user": 404, "owner": 404, "mod": 404, "admin": 200}),
    ("GET", "/admin/tags", {"visitor": 303, "user": 404, "owner": 404, "mod": 404, "admin": 200}),
    (
        "GET",
        "/admin/certifications",
        {"visitor": 303, "user": 404, "owner": 404, "mod": 404, "admin": 200},
    ),
    ("GET", "/admin/settings", {"visitor": 303, "user": 404, "owner": 404, "mod": 404, "admin": 200}),
    ("GET", "/admin/audit", {"visitor": 303, "user": 404, "owner": 404, "mod": 404, "admin": 200}),
    (
        "POST",
        "/admin/users/{user_id}/role",
        {"visitor": 403, "user": 404, "owner": 404, "mod": 404, "admin": 303},
    ),
]


@pytest.mark.parametrize("actor", ACTORS)
@pytest.mark.parametrize(("method", "template", "expected"), MATRIX, ids=[f"{m} {p}" for m, p, _ in MATRIX])
def test_permission_matrix(client, db, world, actor, method, template, expected):
    people, tools = world
    path = template.format(
        published=tools["published"].slug,
        pending=tools["pending"].slug,
        draft=tools["draft"].slug,
        hidden=tools["hidden"].slug,
        published_id=tools["published"].id,
        pending_id=tools["pending"].id,
        draft_id=tools["draft"].id,
        user_id=people["user"].id,
    )
    as_actor(client, db, people, actor)
    if method == "GET":
        r = client.get(path)
    else:
        r = post(client, path, {"role": "moderator"} if "/role" in path else {})
    assert r.status_code == expected[actor], f"{actor} {method} {path} -> {r.status_code}"


def test_moderator_cannot_approve_own_tool_via_route(client, db):
    mod = make_user(db, "mod@example.org", Role.moderator)
    tool = make_tool(db, mod, status="pending")
    login(client, db, mod)
    assert post(client, f"/mod/tools/{tool.id}/approve").status_code == 403
    page = client.get(f"/mod/tools/{tool.id}")
    assert "outra pessoa tem de a moderar" in page.text


def test_hidden_resources_return_404_not_403(client, db, world):
    people, tools = world
    login(client, db, people["user"])
    assert client.get(f"/t/{tools['pending'].slug}").status_code == 404
    assert client.get("/admin/users").status_code == 404
