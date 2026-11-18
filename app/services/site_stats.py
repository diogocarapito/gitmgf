"""Site-wide statistics for moderators and administrators (D35): overview, searches, categories.

Per-tool usage for authors lives in `services.stats`.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Category, SearchQuery, Tool, ToolDailyStat, ToolRevision, User, tool_categories
from app.models.enums import RevisionStatus, ToolStatus, UserStatus

PERIODS = (7, 30, 90)


def period(days: int) -> int:
    return days if days in PERIODS else 30


def top_searches(db: Session, since: Any, zero: bool, limit: int) -> list[tuple[str, int]]:
    query = select(SearchQuery.q, func.count()).where(SearchQuery.created_at >= since, SearchQuery.q != "")
    if zero:
        query = query.where(SearchQuery.results_count == 0)
    rows = db.execute(query.group_by(SearchQuery.q).order_by(func.count().desc()).limit(limit)).all()
    return [(q, int(n)) for q, n in rows]


def overview(db: Session) -> dict[str, Any]:
    now = utcnow()
    by_status = dict(db.execute(select(Tool.status, func.count()).group_by(Tool.status)).all())
    weeks = []
    for i in range(7, -1, -1):
        start, end = now - timedelta(days=7 * (i + 1)), now - timedelta(days=7 * i)
        weeks.append(
            {
                "start": start,
                "signups": db.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.created_at >= start, User.created_at < end)
                )
                or 0,
                "submissions": db.scalar(
                    select(func.count())
                    .select_from(Tool)
                    .where(Tool.submitted_at >= start, Tool.submitted_at < end)
                )
                or 0,
            }
        )
    oldest_pending = db.scalar(select(func.min(Tool.submitted_at)).where(Tool.status == ToolStatus.pending))
    oldest_revision = db.scalar(
        select(func.min(ToolRevision.created_at)).where(ToolRevision.status == RevisionStatus.pending)
    )
    top_tools = (
        db.scalars(
            select(Tool).where(Tool.status == ToolStatus.published).order_by(Tool.score.desc()).limit(10)
        )
        .unique()
        .all()
    )
    since = now - timedelta(days=7)
    return {
        "users_total": db.scalar(
            select(func.count()).select_from(User).where(User.status != UserStatus.deleted)
        )
        or 0,
        "by_status": {k.value: v for k, v in by_status.items()},
        "weeks": weeks,
        "oldest": min([d for d in (oldest_pending, oldest_revision) if d], default=None),
        "top_tools": top_tools,
        "top_searches": top_searches(db, since, zero=False, limit=10),
        "zero_searches": top_searches(db, since, zero=True, limit=10),
    }


def searches(db: Session, days: int) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    total = (
        db.scalar(select(func.count()).select_from(SearchQuery).where(SearchQuery.created_at >= since)) or 0
    )
    zero = (
        db.scalar(
            select(func.count())
            .select_from(SearchQuery)
            .where(SearchQuery.created_at >= since, SearchQuery.results_count == 0)
        )
        or 0
    )
    return {
        "total": total,
        "zero_rate": (zero / total) if total else 0,
        "top": top_searches(db, since, zero=False, limit=50),
        "zero_rows": top_searches(db, since, zero=True, limit=50),
    }


def categories(db: Session, days: int) -> dict[str, list[dict[str, Any]]]:
    """Per active category: published tools, stars, and views/clicks in the period (sorted by views)."""
    since = (utcnow() - timedelta(days=days)).date()
    published = Tool.status == ToolStatus.published
    listing = dict(
        (cid, (int(n), int(stars)))
        for cid, n, stars in db.execute(
            select(
                tool_categories.c.category_id,
                func.count(Tool.id),
                func.coalesce(func.sum(Tool.stars_count), 0),
            )
            .join(Tool, Tool.id == tool_categories.c.tool_id)
            .where(published)
            .group_by(tool_categories.c.category_id)
        ).all()
    )
    usage = {
        cid: (int(v), int(s), int(o))
        for cid, v, s, o in db.execute(
            select(
                tool_categories.c.category_id,
                func.coalesce(func.sum(ToolDailyStat.views), 0),
                func.coalesce(func.sum(ToolDailyStat.search_clicks), 0),
                func.coalesce(func.sum(ToolDailyStat.outbound_clicks), 0),
            )
            .join(ToolDailyStat, ToolDailyStat.tool_id == tool_categories.c.tool_id)
            .join(Tool, Tool.id == tool_categories.c.tool_id)
            .where(published, ToolDailyStat.day >= since)
            .group_by(tool_categories.c.category_id)
        ).all()
    }
    rows: dict[str, list[dict[str, Any]]] = {"categories": [], "specialties": []}
    for c in db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
    ).all():
        tools, stars = listing.get(c.id, (0, 0))
        views, search_clicks, outbound = usage.get(c.id, (0, 0, 0))
        rows["specialties" if c.is_specialty else "categories"].append(
            {
                "category": c,
                "tools": tools,
                "stars": stars,
                "views": views,
                "search_clicks": search_clicks,
                "outbound": outbound,
            }
        )
    for key in rows:
        rows[key].sort(key=lambda r: (-r["views"], -r["tools"], r["category"].sort_order))
    return rows
