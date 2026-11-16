"""Full-text search (TECH_SPEC §8). The FTS index is written only here: reindex_tool() / remove_tool()."""

import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import today, utcnow
from app.models import Category, SearchQuery, Tag, Tool, tool_categories
from app.models.enums import ToolStatus
from app.services import markdown, settings_store

PAGE_SIZE = 20
MAX_PAGE = 50
MAX_TOKENS = 8
SORTS = ("relevance", "popular", "new", "stars", "updated")
BM25_WEIGHTS = "10, 10, 5, 5, 1, 1, 4, 3"
MERGE_WINDOW = timedelta(seconds=30)


# ---------- index ----------


def _row(db: Session, tool: Tool) -> dict[str, Any]:
    cats = db.execute(
        select(Category.name_pt, Category.name_en)
        .join(tool_categories, tool_categories.c.category_id == Category.id)
        .where(tool_categories.c.tool_id == tool.id, Category.is_active.is_(True))
    ).all()
    return {
        "rowid": tool.id,
        "title_pt": tool.title_pt,
        "title_en": tool.title_en or "",
        "summary_pt": tool.summary_pt,
        "summary_en": tool.summary_en or "",
        "description_pt": markdown.to_text(tool.description_pt),
        "description_en": markdown.to_text(tool.description_en or ""),
        "tags": " ".join(t.label for t in tool.tags),
        "categories": " ".join(f"{pt} {en}" for pt, en in cats),
        "tool_id": tool.id,
    }


def remove_tool(db: Session, tool_id: int) -> None:
    db.execute(text("DELETE FROM tool_search WHERE rowid = :id"), {"id": tool_id})


def reindex_tool(db: Session, tool_id: int) -> None:
    """Only published tools are indexed; anything else is removed from the index."""
    remove_tool(db, tool_id)
    tool = db.get(Tool, tool_id)
    if tool is None or tool.status != ToolStatus.published:
        return
    db.execute(
        text(
            "INSERT INTO tool_search (rowid, title_pt, title_en, summary_pt, summary_en, description_pt,"
            " description_en, tags, categories, tool_id) VALUES (:rowid, :title_pt, :title_en, :summary_pt,"
            " :summary_en, :description_pt, :description_en, :tags, :categories, :tool_id)"
        ),
        _row(db, tool),
    )


def reindex_tools(db: Session, tool_ids: list[int]) -> None:
    for tool_id in tool_ids:
        reindex_tool(db, tool_id)


def rebuild(db: Session) -> int:
    db.execute(text("DELETE FROM tool_search"))
    ids = db.scalars(select(Tool.id).where(Tool.status == ToolStatus.published)).all()
    for tool_id in ids:
        reindex_tool(db, tool_id)
    return len(ids)


# ---------- query building (no user syntax ever reaches MATCH) ----------


def normalise(q: str | None) -> str:
    if not q:
        return ""
    return unicodedata.normalize("NFKC", q).lower().strip()[:200]


def tokens(q: str) -> list[str]:
    found = re.findall(r"\w+", q, flags=re.UNICODE)
    kept = [t for t in found if len(t) > 1 or t.isdigit()]
    return kept[:MAX_TOKENS]


def fts_expression(toks: list[str], operator: str = "AND") -> str:
    quoted = [f'"{t.replace(chr(34), "")}"*' for t in toks]
    return (" OR " if operator == "OR" else " ").join(quoted)


@dataclass
class SearchParams:
    q: str = ""
    cat: list[str] = field(default_factory=list)
    type: str | None = None
    platform: list[str] = field(default_factory=list)
    setting: str | None = None
    oss: bool = False
    free: bool = False
    cert: list[str] = field(default_factory=list)
    lang: str | None = None
    sort: str | None = None
    page: int = 1

    @property
    def effective_sort(self) -> str:
        if self.sort in SORTS and not (self.sort == "relevance" and not self.q):
            return self.sort
        return "relevance" if self.q else "popular"

    def filters(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in ("cat", "platform", "cert"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        for key in ("type", "setting", "lang"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.oss:
            out["oss"] = True
        if self.free:
            out["free"] = True
        return out

    @property
    def is_active(self) -> bool:
        return bool(self.q or self.filters())


@dataclass
class SearchResult:
    ids: list[int]
    total: int
    partial: bool
    page: int

    @property
    def has_next(self) -> bool:
        return self.page < MAX_PAGE and self.page * PAGE_SIZE < self.total


def _filters_sql(params: SearchParams, on: date) -> tuple[list[str], dict[str, Any]]:
    where = ["t.status = 'published'"]
    bind: dict[str, Any] = {}

    def in_list(prefix: str, values: list[str]) -> str:
        names = []
        for i, value in enumerate(values[:20]):
            bind[f"{prefix}{i}"] = value
            names.append(f":{prefix}{i}")
        return ", ".join(names)

    if params.cat:
        where.append(
            "EXISTS (SELECT 1 FROM tool_categories tc JOIN categories c ON c.id = tc.category_id"
            f" WHERE tc.tool_id = t.id AND c.is_active = 1 AND c.slug IN ({in_list('cat', params.cat)}))"
        )
    if params.type:
        where.append("t.tool_type = :type")
        bind["type"] = params.type
    if params.platform:
        where.append(
            f"EXISTS (SELECT 1 FROM json_each(t.platforms) WHERE value IN ({in_list('pf', params.platform)}))"
        )
    if params.setting:
        where.append("t.care_setting IN (:setting, 'both')")
        bind["setting"] = params.setting
    if params.oss:
        where.append("t.is_open_source = 1")
    if params.free:
        where.append("t.pricing = 'free'")
    if params.lang:
        where.append("EXISTS (SELECT 1 FROM json_each(t.tool_languages) WHERE value = :tlang)")
        bind["tlang"] = params.lang
    for i, code in enumerate(params.cert[:10]):
        # AND semantics: one EXISTS per certification; present = approved and not expired.
        where.append(
            "EXISTS (SELECT 1 FROM tool_certifications x JOIN certifications ce ON ce.id = x.certification_id"
            f" WHERE x.tool_id = t.id AND ce.code = :cert{i} AND ce.is_active = 1 AND x.state = 'approved'"
            " AND (x.valid_until IS NULL OR x.valid_until >= :today))"
        )
        bind[f"cert{i}"] = code
    if params.cert:
        bind["today"] = on.isoformat()
    return where, bind


ORDER_BY = {
    "popular": "t.score DESC, t.id DESC",
    "new": "t.published_at DESC, t.id DESC",
    "stars": "t.stars_count DESC, t.id DESC",
    "updated": "COALESCE(t.last_content_update_at, t.published_at) DESC, t.id DESC",
}


def _run(db: Session, params: SearchParams, expr: str | None, on: date) -> tuple[list[int], int]:
    # SQL fragments below are built only from constants; every user value is a bound parameter.
    where, bind = _filters_sql(params, on)
    page = max(1, min(params.page, MAX_PAGE))
    bind.update({"limit": PAGE_SIZE, "offset": (page - 1) * PAGE_SIZE})
    sort = params.effective_sort
    if expr:
        bind["expr"] = expr
        bind["beta"] = settings_store.get_float(db, "search.beta_popularity")
        source = "tool_search JOIN tools t ON t.id = tool_search.rowid"
        where.insert(0, "tool_search MATCH :expr")
        order = (
            "(bm25(tool_search, " + BM25_WEIGHTS + ") - :beta * t.score_log) ASC, t.id DESC"
            if sort == "relevance"
            else ORDER_BY[sort]
        )
    else:
        source = "tools t"
        order = ORDER_BY.get(sort, ORDER_BY["popular"])
    clause = " AND ".join(where)
    ids = (
        db.execute(
            text(f"SELECT t.id FROM {source} WHERE {clause} ORDER BY {order} LIMIT :limit OFFSET :offset"),
            bind,
        )
        .scalars()
        .all()
    )
    total = db.execute(text(f"SELECT count(*) FROM {source} WHERE {clause}"), bind).scalar_one()
    return list(ids), int(total)


def search(db: Session, params: SearchParams, on: date | None = None) -> SearchResult:
    on = on or today()
    q = normalise(params.q)
    toks = tokens(q)
    page = max(1, min(params.page, MAX_PAGE))
    if not toks:
        ids, total = _run(db, params, None, on)
        return SearchResult(ids, total, False, page)
    ids, total = _run(db, params, fts_expression(toks, "AND"), on)
    if total == 0 and len(toks) > 1:
        ids, total = _run(db, params, fts_expression(toks, "OR"), on)
        return SearchResult(ids, total, total > 0, page)
    return SearchResult(ids, total, False, page)


def load_tools(db: Session, ids: list[int]) -> list[Tool]:
    if not ids:
        return []
    rows = {t.id: t for t in db.scalars(select(Tool).where(Tool.id.in_(ids))).unique().all()}
    return [rows[i] for i in ids if i in rows]


# ---------- search logging (TECH_SPEC §8.6) ----------

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(out))


ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def log_search(
    db: Session, params: SearchParams, lang: str, results_count: int, visitor_hash: str
) -> str | None:
    """Logs a query when there is text or a filter. Keystrokes within 30 s refine the same row."""
    if not params.is_active:
        return None
    q = normalise(params.q)
    now = utcnow()
    recent = db.scalar(
        select(SearchQuery)
        .where(SearchQuery.visitor_hash == visitor_hash, SearchQuery.updated_at >= now - MERGE_WINDOW)
        .order_by(SearchQuery.updated_at.desc())
        .limit(1)
    )
    if recent is not None and q and recent.q and (q.startswith(recent.q) or recent.q.startswith(q)):
        recent.q = q
        recent.filters = params.filters()
        recent.sort = params.effective_sort
        recent.results_count = results_count
        recent.updated_at = now
        return recent.id
    row = SearchQuery(
        id=new_ulid(),
        q=q,
        locale=lang,
        filters=params.filters(),
        sort=params.effective_sort,
        results_count=results_count,
        visitor_hash=visitor_hash,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    return row.id


def suggest_tags(db: Session, prefix: str, limit: int = 8) -> list[Tag]:
    from slugify import slugify

    slug = slugify(prefix or "")
    if len(slug) < 2:
        return []
    return list(
        db.scalars(
            select(Tag)
            .where(Tag.slug.like(f"{slug}%"))
            .order_by(Tag.usage_count.desc(), Tag.label)
            .limit(limit)
        ).all()
    )
