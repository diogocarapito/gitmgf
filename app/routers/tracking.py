"""Tracking redirects and stars (TECH_SPEC §9.2–9.3)."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select

from app import i18n
from app.deps import DB, CurrentUser
from app.models import PUBLIC_STATUSES, SearchQuery, Tool
from app.models.enums import EventKind, LinkKind
from app.services import ratelimit, search, tracking
from app.services import tools as tool_service
from app.services.tools import InvalidTransition
from app.templating import is_htmx, render

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


def _lang(request: Request) -> str:
    referer_lang = i18n.lang_from_path(_path_of(request.headers.get("referer", "")))
    return referer_lang or request.state.lang


def _path_of(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).path if url else ""


@router.get("/r/{search_id}/{tool_id}")
def search_click(
    request: Request, db: DB, user: CurrentUser, search_id: str, tool_id: int, pos: int | None = None
) -> Response:
    tool = db.get(Tool, tool_id)
    if tool is None or tool.status not in PUBLIC_STATUSES:
        raise HTTPException(status_code=404)
    if search.ULID_RE.match(search_id) and db.get(SearchQuery, search_id) is not None:
        tracking.record(db, request, tool, EventKind.search_click, user, search_id=search_id, position=pos)
        db.commit()
    return RedirectResponse(f"/{_lang(request)}/t/{tool.slug}", status_code=302, headers=NO_STORE)


@router.get("/go/{tool_id}/{link_kind}")
def outbound(
    request: Request, db: DB, user: CurrentUser, tool_id: int, link_kind: str, s: str | None = None
) -> Response:
    """No open redirect: only URLs stored on a published/archived tool."""
    try:
        kind = LinkKind(link_kind)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    tool = db.get(Tool, tool_id)
    if tool is None or tool.status not in PUBLIC_STATUSES:
        raise HTTPException(status_code=404)
    target = getattr(tool, f"{kind.value}_url")
    if not target or not target.startswith(("https://", "http://")):
        raise HTTPException(status_code=404)
    tracking.record(db, request, tool, EventKind.outbound_click, user, link_kind=kind)
    if s and search.ULID_RE.match(s) and db.scalar(select(SearchQuery.id).where(SearchQuery.id == s)):
        tracking.record(db, request, tool, EventKind.search_click, user, search_id=s)
    db.commit()
    return RedirectResponse(target, status_code=302, headers={**NO_STORE, "Referrer-Policy": "no-referrer"})


@router.post("/t/{tool_id}/star")
def star(request: Request, db: DB, user: CurrentUser, tool_id: int) -> Response:
    tool = db.get(Tool, tool_id)
    if tool is None or tool.status not in PUBLIC_STATUSES:
        raise HTTPException(status_code=404)
    if user is None:
        if is_htmx(request):
            return Response(
                status_code=204,
                headers={
                    "HX-Redirect": f"/{request.state.lang}/login?next=/{request.state.lang}/t/{tool.slug}"
                },
            )
        return RedirectResponse(
            f"/{request.state.lang}/login?next=/{request.state.lang}/t/{tool.slug}", status_code=303
        )
    if not ratelimit.hit(ratelimit.STAR_USER, "star", str(user.id)):
        raise HTTPException(status_code=429)
    try:
        starred = tool_service.toggle_star(db, tool, user)
    except InvalidTransition as exc:
        raise HTTPException(status_code=403) from exc
    db.commit()
    if is_htmx(request):
        return render(
            request, "partials/star_button.html", {"tool": tool, "starred": starred, "can_star": True}
        )
    return RedirectResponse(f"/{request.state.lang}/t/{tool.slug}", status_code=303)
