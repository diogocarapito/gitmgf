"""Statistics area for moderators and administrators (D35)."""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.deps import DB, ModDep
from app.services import site_stats as stats
from app.templating import render

pages = APIRouter()
actions = APIRouter()


@pages.get("/stats")
def overview(request: Request, db: DB, user: ModDep) -> Response:
    return render(request, "stats/overview.html", {"active": "overview", **stats.overview(db)})


@pages.get("/stats/searches")
def searches(request: Request, db: DB, user: ModDep, days: int = 30) -> Response:
    days = stats.period(days)
    return render(
        request, "stats/searches.html", {"active": "searches", "days": days, **stats.searches(db, days)}
    )


@pages.get("/stats/categories")
def categories(request: Request, db: DB, user: ModDep, days: int = 30) -> Response:
    days = stats.period(days)
    return render(
        request, "stats/categories.html", {"active": "categories", "days": days, **stats.categories(db, days)}
    )
