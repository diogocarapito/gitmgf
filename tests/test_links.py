import re

from app.models.enums import Role
from tests.conftest import login, make_user
from tests.factories import make_tool


def _about_team_handles() -> set[str]:
    from app.services import legal

    text = (legal.CONTENT_DIR / "pt" / "about.md").read_text(encoding="utf-8")
    return set(re.findall(r"\(/u/([a-z0-9-]+)\)", text))


def test_no_pt_prefixed_links_and_internal_links_resolve(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    for handle in _about_team_handles():  # the About page links to the team's profiles
        make_user(db, f"{handle}@example.org").handle = handle
    db.commit()
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


def test_about_page_links_to_the_team_profiles_in_both_languages(client, db):
    handles = _about_team_handles()
    assert len(handles) == 5
    pt, en = client.get("/p/about").text, client.get("/en/p/about").text
    assert (
        "Inteligência Artificial e Literacia Digital" in pt
        and "Inteligência Artificial e Literacia Digital" in en
    )
    for handle in handles:
        assert f'href="/u/{handle}"' in pt and f'href="/en/u/{handle}"' in en
