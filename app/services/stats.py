"""Per-tool usage for authors (PRD F15) from `tool_daily_stats` (refreshed by the score job)."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import today
from app.models import Star, ToolDailyStat


def usage_for(db: Session, tool_ids: list[int], on: date | None = None) -> dict[int, dict[str, int]]:
    on = on or today()
    out: dict[int, dict[str, int]] = {
        tid: {f"{k}_{d}": 0 for k in ("search", "outbound", "views") for d in (30, 90)} | {"stars": 0}
        for tid in tool_ids
    }
    if not tool_ids:
        return out
    for days in (30, 90):
        rows = db.execute(
            select(
                ToolDailyStat.tool_id,
                func.sum(ToolDailyStat.search_clicks),
                func.sum(ToolDailyStat.outbound_clicks),
                func.sum(ToolDailyStat.views),
            )
            .where(ToolDailyStat.tool_id.in_(tool_ids), ToolDailyStat.day > on - timedelta(days=days))
            .group_by(ToolDailyStat.tool_id)
        ).all()
        for tid, search_clicks, outbound, views in rows:
            out[tid][f"search_{days}"] = int(search_clicks or 0)
            out[tid][f"outbound_{days}"] = int(outbound or 0)
            out[tid][f"views_{days}"] = int(views or 0)
    for tid, count in db.execute(
        select(Star.tool_id, func.count()).where(Star.tool_id.in_(tool_ids)).group_by(Star.tool_id)
    ).all():
        out[tid]["stars"] = int(count)
    return out


def daily_series(db: Session, tool_id: int, days: int, on: date | None = None) -> list[dict[str, Any]]:
    on = on or today()
    start = on - timedelta(days=days - 1)
    rows = {
        r.day: r
        for r in db.scalars(
            select(ToolDailyStat).where(ToolDailyStat.tool_id == tool_id, ToolDailyStat.day >= start)
        ).all()
    }
    series = []
    for i in range(days):
        day = start + timedelta(days=i)
        row = rows.get(day)
        series.append(
            {
                "day": day,
                "search": row.search_clicks if row else 0,
                "outbound": row.outbound_clicks if row else 0,
                "views": row.views if row else 0,
            }
        )
    return series
