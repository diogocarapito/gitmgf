from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from markupsafe import escape
from sqlalchemy import func, select

from app import i18n
from app.config import get_settings
from app.deps import DB, CurrentUser, Form
from app.forms.search import SearchQueryParams
from app.i18n import N_, lang_prefix
from app.models import Category, Tool, ToolMedia, tool_categories
from app.models.enums import EventKind, MediaState, ToolStatus
from app.routers.auth import client_key
from app.services import blog, certifications, email, legal, permissions, ratelimit, search, tracking
from app.services import reports as report_service
from app.services import tools as tool_service
from app.templating import is_htmx, render

root = APIRouter()
pages = APIRouter()
actions = APIRouter()


@root.api_route("/pt", methods=["GET", "HEAD", "POST"])
@root.api_route("/pt/{rest:path}", methods=["GET", "HEAD", "POST"])
def legacy_pt_redirect(request: Request, rest: str = "") -> Response:
    """Old /pt/… URLs (before D28) → the same page at the root. 308 keeps the method for POSTs."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/{rest}{query}", status_code=308 if request.method == "POST" else 301)


def first_visit_redirect(request: Request, user: Any) -> Response | None:
    """Only on a first visit to the PT home: English browsers go to /en/ (PRD F13). Never on later visits,
    so choosing PT in the language switcher always sticks."""
    if request.cookies.get(i18n.LANG_COOKIE) in i18n.LANGS:
        return None
    lang = user.locale.value if user is not None else i18n.negotiate(request.headers.get("accept-language"))
    if lang != "en":
        return None
    return RedirectResponse("/en/", status_code=302, headers={"Vary": "Accept-Language, Cookie"})


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
def home(request: Request, db: DB, user: CurrentUser) -> Response:
    if request.state.lang == "pt" and request.url.path == "/":
        redirect = first_visit_redirect(request, user)
        if redirect is not None:
            return redirect
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
        return f"{lang_prefix(lang)}/t/{t.slug}"

    query_pairs: list[tuple[str, Any]] = []
    for key, value in qp.model_dump().items():
        if key == "page" or value in (None, "", [], False):
            continue
        if isinstance(value, list):
            query_pairs += [(key, v) for v in value]
        else:
            query_pairs.append((key, "1" if value is True else value))
    base_path = f"{lang_prefix(lang)}/c/{category.slug}" if category else f"{lang_prefix(lang)}/search"
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


@pages.get("/blog")
def blog_index(request: Request) -> Response:
    return render(request, "pages/blog_index.html", {"posts": blog.all_posts(request.state.lang)})


@pages.get("/blog/{slug}")
def blog_post(request: Request, slug: str) -> Response:
    post = blog.get(slug, request.state.lang)
    if post is None:
        raise HTTPException(status_code=404)
    return render(request, "pages/blog_post.html", {"post": post})


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
        link = f"{base}{lang_prefix(lang)}/t/{t.slug}"
        stamp = (t.published_at or t.created_at).strftime("%Y-%m-%dT%H:%M:%SZ")
        entries.append(
            f'<entry><title>{escape(title)}</title><link href="{escape(link)}"/><id>{escape(link)}</id>'
            f"<updated>{stamp}</updated><summary>{escape(summary)}</summary>"
            f"<author><name>{escape(t.owner.display_name)}</name></author></entry>"
        )
    title = "gitmgf — " + i18n.t(lang, "Novas ferramentas")
    body = (
        '<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
        f'<title>{escape(title)}</title><link href="{base}{lang_prefix(lang)}/"/><link rel="self" href="{base}{lang_prefix(lang)}/feed.xml"/>'
        f"<id>{base}{lang_prefix(lang)}/feed.xml</id><updated>{(updated.strftime('%Y-%m-%dT%H:%M:%SZ') if updated else '1970-01-01T00:00:00Z')}</updated>"
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


# ---------- reports (DSA notice and action) ----------

MIN_FORM_SECONDS = 3
MAX_FORM_SECONDS = 24 * 3600


def _form_stamp() -> str:
    from itsdangerous import URLSafeTimedSerializer

    return URLSafeTimedSerializer(get_settings().secret_key, salt="report-form").dumps("t")


def _stamp_age(value: str | None) -> float | None:
    """Seconds since the form was rendered, or None if the stamp is missing or forged."""
    import time

    from itsdangerous import BadSignature, URLSafeTimedSerializer

    if not value:
        return None
    try:
        _, signed_at = URLSafeTimedSerializer(get_settings().secret_key, salt="report-form").loads(
            value, max_age=MAX_FORM_SECONDS, return_timestamp=True
        )
    except BadSignature:
        return None
    return time.time() - signed_at.timestamp()


def _reportable(db: DB, slug: str) -> Tool:
    tool = db.scalar(select(Tool).where(Tool.slug == slug))
    if tool is None or not tool.is_public:
        raise HTTPException(status_code=404)
    return tool


def _report_page(
    request: Request, tool: Tool, values: dict[str, Any], errors: dict[str, Any], status_code: int = 200
) -> Response:
    return render(
        request,
        "public/report.html",
        {"tool": tool, "values": values, "errors": errors, "stamp": _form_stamp()},
        status_code=status_code,
    )


@pages.get("/t/{slug}/report")
def report_form(request: Request, db: DB, user: CurrentUser, slug: str) -> Response:
    return _report_page(request, _reportable(db, slug), {}, {})


@pages.post("/t/{slug}/report")
def report_submit(
    request: Request, db: DB, user: CurrentUser, slug: str, form: Form, background: BackgroundTasks
) -> Response:
    from pydantic import ValidationError

    from app.forms.common import INVALID_EMAIL, errors_from, form_to_dict
    from app.forms.report import ReportForm
    from app.models.enums import ReportReason

    tool = _reportable(db, slug)
    lang = request.state.lang
    raw = form_to_dict(form)
    raw["csam"] = form.get("csam") == "1"
    raw["good_faith"] = form.get("good_faith") == "1"
    raw["anonymous"] = user is None
    # Spam checks without third-party CAPTCHA: honeypot + minimum fill time (PRD Q6).
    age = _stamp_age(form.get("stamp") if isinstance(form.get("stamp"), str) else None)
    if form.get("website") or age is None or age < MIN_FORM_SECONDS:
        return _report_page(
            request,
            tool,
            raw,
            {"__all__": (N_("Não foi possível enviar. Aguarde uns segundos e tente novamente."), {})},
            422,
        )
    try:
        data = ReportForm.model_validate(raw)
    except ValidationError as exc:
        errors = errors_from(exc)
        if "__all__" in errors or any(e.get("loc") == () for e in exc.errors()):
            errors.pop("__all__", None)
            errors["email"] = (INVALID_EMAIL, {})
        return _report_page(request, tool, raw, errors, 422)
    visitor = tracking.visitor_hash(db, request)
    if not ratelimit.hit(ratelimit.REPORTS_VISITOR, "report", visitor):
        raise HTTPException(status_code=429)
    report_service.create(
        db,
        tool,
        ReportReason(data.reason),
        data.details,
        user,
        str(data.email) if data.email else None,
        data.csam,
        lang,
        visitor,
    )
    db.commit()
    background.add_task(email.deliver_queued)
    target = (
        f"{lang_prefix(lang)}/t/{tool.slug}?flash=reported"
        if tool.status in ("published", "archived")
        else f"{lang_prefix(lang)}/?flash=reported"
    )
    return RedirectResponse(target, status_code=303)
