import re

from app.models.enums import Role
from tests.conftest import login, make_user
from tests.factories import make_tool


def test_no_pt_prefixed_links_and_internal_links_resolve(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    tool = make_tool(db, title_pt="Ferramenta de teste")
    login(client, db, admin)
    seen, bad, todo = (
        set(),
        [],
        ["/", "/en/", f"/t/{tool.slug}", f"/en/t/{tool.slug}", "/me/tools", "/admin", "/mod"],
    )
    while todo and len(seen) < 120:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        r = client.get(path)
        if r.status_code >= 400:
            bad.append((path, r.status_code))
            continue
        if "text/html" not in r.headers.get("content-type", ""):
            continue
        for href in re.findall(r'href="(/[^"#]*)"', r.text):
            assert not href.startswith("/pt/"), (path, href)
            if href.startswith(("/static/", "/media/", "/go/", "/r/", "/auth/", "/me/export")):
                continue
            todo.append(href.split("?")[0])
    assert not bad, bad
