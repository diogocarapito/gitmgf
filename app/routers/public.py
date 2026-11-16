from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from markupsafe import escape
from sqlalchemy import func, select

from app import i18n
from app.config import get_settings
from app.deps import DB, CurrentUser
from app.forms.search import SearchQueryParams
from app.models import Category, Tool, ToolMedia, tool_categories
from app.models.enums import EventKind, MediaState, ToolStatus
from app.routers.auth import client_key
from app.services import certifications, legal, permissions, ratelimit, search, tracking
from app.services import tools as tool_service
from app.templating import is_htmx, render

root = APIRouter()
pages = APIRouter()
actions = APIRouter()


@root.get("/")
def locale_redirect(request: Request, user: CurrentUser) -> Response:
    """Cookie › user locale › Accept-Language (any pt* → pt) › pt (TECH_SPEC §13)."""
    cookie = request.cookies.get(i18n.LANG_COOKIE)
    if cookie in i18n.LANGS:
        lang = cookie
    elif user is not None:
        lang = user.locale.value
    else:
        lang = i18n.negotiate(request.headers.get("accept-language"))
    return RedirectResponse(f"/{lang}/", status_code=302, headers={"Vary": "Accept-Language, Cookie"})


def category_counts(db: DB) -> list[tuple[Category, int]]:
    rows = db.execute(
        select(Category, func.count(Tool.id))
        .outerjoin(tool_categories, tool_categories.c.category_id == Category.id)
        .outerjoin(Tool, (Tool.id == tool_categories.c.tool_id) & (Tool.status == ToolStatus.published))
        .where(Category.is_active.is_(True))
        .group_by(Category.id)
        .order_by(Category.sort_order, Category.name_pt)
    ).all()
    return [(c, int(n)) for c, n in rows]


def _published(db: DB, order: Any, limit: int) -> list[Tool]:
    return list(
        db.scalars(
            select(Tool)
            .where(Tool.status == ToolStatus.published)
            .order_by(order, Tool.id.desc())
            .limit(limit)
        )
        .unique()
        .all()
    )


@pages.get("/")
def home(request: Request, db: DB) -> Response:
    popular = _published(db, Tool.score.desc(), 6)
    newest = _published(db, Tool.published_at.desc(), 6)
    lang = request.state.lang
    badges = certifications.badges_for(db, list({t.id for t in popular + newest}), lang)
    cats = [(c, n) for c, n in category_counts(db) if n > 0 or not c.is_specialty][:18]
    return render(
        request,
        "public/home.html",
        {"popular": popular, "newest": newest, "categories": cats, "badges": badges},
    )


def _filter_options(db: DB) -> dict[str, Any]:
    cats = db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name_pt)
    ).all()
    return {
        "all_categories": cats,
        "all_certs": certifications.catalogue(db),
    }


def _search_context(
    request: Request, db: DB, user: Any, qp: SearchQueryParams, category: Category | None = None
) -> dict[str, Any]:
    lang = request.state.lang
    params = qp.to_params()
    result = search.search(db, params)
    tools = search.load_tools(db, result.ids)
    search_id = None
    if params.is_active and not tracking.is_bot(request.headers.get("user-agent")):
        search_id = search.log_search(db, params, lang, result.total, tracking.visitor_hash(db, request))
        db.commit()
    offset = (result.page - 1) * search.PAGE_SIZE

    def card_href(t: Tool, index: int | None) -> str:
        if search_id:
            return f"/r/{search_id}/{t.id}?pos={offset + (index or 0)}"
        return f"/{lang}/t/{t.slug}"

    query_pairs: list[tuple[str, Any]] = []
    for key, value in qp.model_dump().items():
        if key == "page" or value in (None, "", [], False):
            continue
        if isinstance(value, list):
            query_pairs += [(key, v) for v in value]
        else:
            query_pairs.append((key, "1" if value is True else value))
    base_path = f"/{lang}/c/{category.slug}" if category else f"/{lang}/search"
    next_url = (
        f"{base_path}?{urlencode([*query_pairs, ('page', result.page + 1)])}" if result.has_next else None
    )
    return {
        "qp": qp,
        "params": params,
        "result": result,
        "tools": tools,
        "badges": certifications.badges_for(db, [t.id for t in tools], lang),
        "card_href": card_href,
        "next_url": next_url,
        "category": category,
        "form_action": base_path,
        **_filter_options(db),
    }


def _search_response(request: Request, db: DB, user: Any, category: Category | None = None) -> Response:
    if not ratelimit.hit(ratelimit.SEARCH_IP, "search", client_key(request)):
        raise HTTPException(status_code=429)
    qp = SearchQueryParams.from_query(request.query_params)
    if category is not None and category.slug not in qp.cat:
        qp.cat = [category.slug, *qp.cat]
    ctx = _search_context(request, db, user, qp, category)
    if is_htmx(request):
        template = (
            "partials/search_more.html"
            if request.query_params.get("more")
            else "partials/search_results.html"
        )
        return render(request, template, ctx)
    return render(request, "public/search.html", ctx)


@pages.get("/search")
def search_page(request: Request, db: DB, user: CurrentUser) -> Response:
    return _search_response(request, db, user)


@pages.get("/c/")
def categories_index(request: Request, db: DB) -> Response:
    return render(request, "public/categories.html", {"categories": category_counts(db)})


@pages.get("/c/{slug}")
def category_page(request: Request, db: DB, user: CurrentUser, slug: str) -> Response:
    category = db.scalar(select(Category).where(Category.slug == slug, Category.is_active.is_(True)))
    if category is None:
        raise HTTPException(status_code=404)
    return _search_response(request, db, user, category)


def tool_page_context(request: Request, db: DB, user: Any, tool: Tool) -> dict[str, Any]:
    lang = request.state.lang
    badges = certifications.badges_for(db, [tool.id], lang)[tool.id]
    certs = {c.code: c for c in certifications.catalogue(db)}
    panel = [
        {"badge": b, "rows": certifications.detail_rows(certs[b.code], b.details or {}, lang)}
        for b in badges
        if b.present and b.code in certs
    ]
    links = [
        (kind, getattr(tool, f"{kind}_url"))
        for kind in ("website", "download", "repo", "docs")
        if getattr(tool, f"{kind}_url")
    ]
    media = [m for m in tool.media if m.state == MediaState.live]
    return {
        "tool": tool,
        "badges": badges,
        "cert_panel": panel,
        "absent_core": [b for b in badges if b.is_core and not b.present],
        "links": links,
        "primary_link": links[0] if links else None,
        "media": media,
        "starred": tool_service.is_starred(db, tool, user),
        "can_star": permissions.can_star(user, tool),
        "is_owner": permissions.is_owner(user, tool),
        "can_moderate": permissions.can_moderate(user, tool),
        "revision": tool_service.pending_revision(db, tool) if permissions.is_owner(user, tool) else None,
        "derived": tool_service_badges(tool),
    }


def tool_service_badges(tool: Tool) -> list[tuple[str, str]]:
    from app.services.badges import derived_badges

    return derived_badges(tool)


@pages.get("/t/{slug}")
def tool_page(request: Request, db: DB, user: CurrentUser, slug: str) -> Response:
    tool = db.scalar(select(Tool).where(Tool.slug == slug))
    if tool is None or not permissions.can_view_tool(user, tool):
        raise HTTPException(status_code=404)
    if tool.status == ToolStatus.published:
        tracking.record(db, request, tool, EventKind.view, user)
        db.commit()
    return render(request, "public/tool.html", tool_page_context(request, db, user, tool))


@pages.get("/p/{page}")
def static_page(request: Request, db: DB, page: str) -> Response:
    rendered = legal.render_page(db, page, request.state.lang)
    if rendered is None:
        raise HTTPException(status_code=404)
    return render(request, "pages/legal.html", {"page": rendered})


@pages.get("/feed.xml")
def feed(request: Request, db: DB) -> Response:
    """Atom feed of newly published tools (PRD F18)."""
    lang = request.state.lang
    base = get_settings().base_url.rstrip("/")
    tools = _published(db, Tool.published_at.desc(), 30)
    updated = tools[0].published_at if tools and tools[0].published_at else None
    entries = []
    for t in tools:
        title, _ = i18n.localized(t, "title", lang)
        summary, _ = i18n.localized(t, "summary", lang)
        link = f"{base}/{lang}/t/{t.slug}"
        stamp = (t.published_at or t.created_at).strftime("%Y-%m-%dT%H:%M:%SZ")
        entries.append(
            f'<entry><title>{escape(title)}</title><link href="{escape(link)}"/><id>{escape(link)}</id>'
            f"<updated>{stamp}</updated><summary>{escape(summary)}</summary>"
            f"<author><name>{escape(t.owner.display_name)}</name></author></entry>"
        )
    title = "gitmgf — " + i18n.t(lang, "Novas ferramentas")
    body = (
        '<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
        f'<title>{escape(title)}</title><link href="{base}/{lang}/"/><link rel="self" href="{base}/{lang}/feed.xml"/>'
        f"<id>{base}/{lang}/feed.xml</id><updated>{(updated.strftime('%Y-%m-%dT%H:%M:%SZ') if updated else '1970-01-01T00:00:00Z')}</updated>"
        + "".join(entries)
        + "</feed>"
    )
    return Response(body, media_type="application/atom+xml")


@actions.get("/api/tags/suggest")
def tag_suggest(db: DB, q: str = "", tags: str = "") -> HTMLResponse:
    """HTMX tag autocomplete: returns chips (no JSON); app.js appends a clicked tag to the input."""
    term = (q or tags).split(",")[-1].strip()
    items = search.suggest_tags(db, term)
    html = "".join(
        f'<button type="button" class="chip chip--sm" data-tag-suggestion="{escape(t.label)}">{escape(t.label)}</button>'
        for t in items
    )
    return HTMLResponse(html)


def media_url(item: ToolMedia, thumb: bool = False) -> str:
    return f"/media/tools/{item.tool_id}/{item.thumb_name if thumb else item.file_name}"
