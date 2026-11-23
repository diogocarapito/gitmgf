"""Popularity score (PRD F8, TECH_SPEC §9.4).

usage = Σ_d (w_sc·search_clicks_d + w_oc·outbound_clicks_d) · 0.5^(age_d / half_life)   (last 365 days, after reset)
score = usage + w_star·stars + w_gh·log10(1 + github_stars);   score_log = ln(1 + score)
"""

import math
from datetime import date, timedelta

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db import today
from app.models import InteractionEvent, Tool, ToolDailyStat, ToolGithub, User
from app.models.enums import EventKind, Role, ToolStatus
from app.services import settings_store

WINDOW_DAYS = 365


def decay(age_days: int, half_life: float) -> float:
    return float(0.5 ** (age_days / half_life))


def aggregate_day(db: Session, day: date) -> int:
    """Upserts raw events of one day into tool_daily_stats (idempotent: counts are recomputed)."""
    rows = db.execute(
        select(InteractionEvent.tool_id, InteractionEvent.kind, func.count())
        .where(InteractionEvent.day == day)
        .group_by(InteractionEvent.tool_id, InteractionEvent.kind)
    ).all()
    per_tool: dict[int, dict[str, int]] = {}
    for tool_id, kind, count in rows:
        per_tool.setdefault(tool_id, {"search_clicks": 0, "outbound_clicks": 0, "views": 0})
        column = {
            EventKind.search_click: "search_clicks",
            EventKind.outbound_click: "outbound_clicks",
            EventKind.view: "views",
        }[kind]
        per_tool[tool_id][column] = int(count)
    for tool_id, counts in per_tool.items():
        stmt = sqlite_insert(ToolDailyStat).values(tool_id=tool_id, day=day, **counts)
        db.execute(stmt.on_conflict_do_update(index_elements=["tool_id", "day"], set_=counts))
    return len(per_tool)


def purge_staff_events(db: Session) -> dict[str, int]:
    """Deletes past events made by current moderators/admins (D40), then rebuilds the affected daily
    stats and the scores. Raw events are kept 180 days, so older daily totals stay as they are."""
    staff = select(User.id).where(User.role.in_([Role.moderator, Role.admin]))
    affected = db.execute(
        select(InteractionEvent.tool_id, InteractionEvent.day)
        .where(InteractionEvent.user_id.in_(staff))
        .distinct()
    ).all()
    if not affected:
        return {"events": 0, "tool_days": 0}
    result = db.execute(delete(InteractionEvent).where(InteractionEvent.user_id.in_(staff)))
    pairs = [(tool_id, day) for tool_id, day in affected]
    db.execute(delete(ToolDailyStat).where(tuple_(ToolDailyStat.tool_id, ToolDailyStat.day).in_(pairs)))
    for day in sorted({day for _, day in pairs}):
        aggregate_day(db, day)
    recompute(db)
    return {"events": int(getattr(result, "rowcount", 0)), "tool_days": len(pairs)}


def recompute(db: Session, on: date | None = None) -> int:
    on = on or today()
    aggregate_day(db, on)
    aggregate_day(db, on - timedelta(days=1))
    w_sc = settings_store.get_float(db, "score.w_search_click")
    w_oc = settings_store.get_float(db, "score.w_outbound_click")
    w_star = settings_store.get_float(db, "score.w_star")
    w_gh = settings_store.get_float(db, "score.w_github")
    half_life = max(settings_store.get_float(db, "score.half_life_days"), 0.1)

    tools = db.execute(
        select(Tool.id, Tool.stars_count, Tool.score_reset_at, ToolGithub.stars)
        .outerjoin(ToolGithub, ToolGithub.tool_id == Tool.id)
        .where(Tool.status == ToolStatus.published)
    ).all()
    start = on - timedelta(days=WINDOW_DAYS)
    stats = db.execute(
        select(
            ToolDailyStat.tool_id,
            ToolDailyStat.day,
            ToolDailyStat.search_clicks,
            ToolDailyStat.outbound_clicks,
        ).where(ToolDailyStat.day > start, ToolDailyStat.day <= on)
    ).all()
    by_tool: dict[int, list[tuple[date, int, int]]] = {}
    for tool_id, day, sc, oc in stats:
        by_tool.setdefault(tool_id, []).append((day, sc, oc))

    updates = []
    for tool_id, stars_count, reset_at, gh_stars in tools:
        reset_day = reset_at.date() if reset_at else None
        usage = 0.0
        for day, sc, oc in by_tool.get(tool_id, []):
            if reset_day is not None and day < reset_day:
                continue
            usage += (w_sc * sc + w_oc * oc) * decay((on - day).days, half_life)
        score = usage + w_star * (stars_count or 0) + w_gh * math.log10(1 + (gh_stars or 0))
        updates.append({"id": tool_id, "score": score, "score_log": math.log1p(score)})
    if updates:
        db.execute(update(Tool), updates)
    return len(updates)
