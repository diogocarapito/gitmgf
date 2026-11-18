import shutil
from datetime import timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from sqlalchemy import select, text

from app.config import get_settings
from app.db import utcnow
from app.deps import DB
from app.i18n import lang_prefix
from app.models import Category, Tool
from app.models.enums import ToolStatus
from app.services import blog, settings_store

router = APIRouter()
STATIC = Path(__file__).resolve().parents[1] / "static"


@router.get("/healthz")
def healthz(db: DB) -> JSONResponse:
    """DB read + disk free > 10 % (TECH_SPEC §20.3)."""
    settings = get_settings()
    db_ok = db.execute(text("SELECT 1")).scalar() == 1
    usage = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else ".")
    disk_free = usage.free / usage.total
    healthy = db_ok and disk_free > 0.10
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", "db": db_ok, "disk_free": round(disk_free, 3)},
        status_code=200 if healthy else 503,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    base = get_settings().base_url.rstrip("/")
    lines = [
        "User-agent: *",
        "Disallow: /r/",
        "Disallow: /go/",
        "Disallow: /auth/",
        "Disallow: /me/",
        "Disallow: /en/me/",
        "Disallow: /mod",
        "Disallow: /en/mod",
        "Disallow: /admin",
        "Disallow: /en/admin",
        "Disallow: /login",
        "Disallow: /en/login",
        "Disallow: /register",
        "Disallow: /en/register",
        "Disallow: /reset/",
        "Disallow: /en/reset/",
        f"Sitemap: {base}/sitemap.xml",
    ]
    return "\n".join(lines) + "\n"


@router.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(STATIC / "img" / "favicon.ico", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/.well-known/security.txt", response_class=PlainTextResponse)
def security_txt(db: DB) -> str:
    contact = settings_store.get(db, "legal.SECURITY_EMAIL")
    if not contact:
        raise HTTPException(status_code=404)
    base = get_settings().base_url.rstrip("/")
    expires = (utcnow() + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")
    return (
        f"Contact: mailto:{contact}\nExpires: {expires}\nPreferred-Languages: pt, en\n"
        f"Canonical: {base}/.well-known/security.txt\nPolicy: {base}/p/terms\n"
    )


@router.get("/sitemap.xml")
def sitemap(db: DB) -> Response:
    """Published tools and categories in both languages, with hreflang alternates (PRD F18)."""
    base = get_settings().base_url.rstrip("/")
    entries: list[tuple[str, str | None]] = [("/", None), ("/search", None)]
    entries += [
        (f"/p/{p}", None) for p in ("about", "guidelines", "terms", "privacy", "disclaimer", "contact")
    ]
    cats = db.scalars(
        select(Category.slug).where(Category.is_active.is_(True)).order_by(Category.sort_order)
    ).all()
    entries += [(f"/c/{slug}", None) for slug in cats]
    entries += [("/blog", None)]
    entries += [(f"/blog/{post.slug}", post.published.isoformat()) for post in blog.all_posts("pt")]
    tools = db.execute(
        select(Tool.slug, Tool.updated_at)
        .where(Tool.status == ToolStatus.published)
        .order_by(Tool.published_at)
    ).all()
    entries += [(f"/t/{slug}", updated.date().isoformat() if updated else None) for slug, updated in tools]

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for path, lastmod in entries:
        for lang in ("pt", "en"):
            out.append("<url>")
            out.append(f"<loc>{escape(f'{base}{lang_prefix(lang)}{path}')}</loc>")
            if lastmod:
                out.append(f"<lastmod>{lastmod}</lastmod>")
            out.append(f'<xhtml:link rel="alternate" hreflang="pt-PT" href="{escape(f"{base}{path}")}"/>')
            out.append(f'<xhtml:link rel="alternate" hreflang="en" href="{escape(f"{base}/en{path}")}"/>')
            out.append(f'<xhtml:link rel="alternate" hreflang="x-default" href="{escape(f"{base}{path}")}"/>')
            out.append("</url>")
    out.append("</urlset>")
    return Response("\n".join(out), media_type="application/xml")
