from datetime import date

from app.models import Category, ToolDailyStat
from app.models.enums import Role
from tests.conftest import login, make_user
from tests.factories import category_ids, make_tool


def test_moderators_get_a_statistics_menu_and_admin_area_stays_admin_only(client, db):
    mod = make_user(db, "m@example.org", Role.moderator)
    login(client, db, mod)
    home = client.get("/").text
    assert 'href="/stats"' in home and 'href="/admin/users"' not in home
    page = client.get("/stats").text
    for tab in ('href="/stats"', 'href="/stats/searches"', 'href="/stats/categories"'):
        assert tab in page
    assert "/admin/categories" not in page  # managing categories is still admin-only
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/stats"
    admin = make_user(db, "a@example.org", Role.admin)
    login(client, db, admin)
    r = client.get("/admin", follow_redirects=False)
    assert r.headers["location"] == "/admin/users"
    assert (
        client.get("/admin/searches?days=7", follow_redirects=False).headers["location"]
        == "/stats/searches?days=7"
    )


def test_category_statistics_count_tools_stars_and_usage_in_the_period(client, db):
    mod = make_user(db, "m@example.org", Role.moderator)
    tool = make_tool(db, moderator=mod)  # in calculadoras-scores and cardiologia
    make_tool(db, status="draft", moderator=mod, title_pt="Rascunho")  # not counted
    tool.stars_count = 4
    db.add(ToolDailyStat(tool_id=tool.id, day=date.today(), views=12, search_clicks=3, outbound_clicks=5))
    db.add(
        ToolDailyStat(tool_id=tool.id, day=date(2020, 1, 1), views=999, search_clicks=0, outbound_clicks=0)
    )
    db.commit()
    login(client, db, mod)
    page = client.get("/stats/categories?days=30").text
    calc = db.get(Category, category_ids(db, "calculadoras-scores")[0])
    row = page.split(calc.name_pt, 1)[1].split("</tr>", 1)[0]
    cells = [c.split("<", 1)[0] for c in row.split('class="num">')[1:]]
    assert cells == ["1", "4", "12", "3", "5"]
    assert "999" not in page and "Especialidades" in page
