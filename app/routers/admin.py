"""Administration (PRD F12). Stats and searches: moderators too; everything else: admins only."""

import json
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from slugify import slugify
from sqlalchemy import func, or_, select

from app.db import utcnow
from app.deps import DB, AdminDep, Form, ModDep
from app.models import (
    AuditLog,
    Category,
    Certification,
    SearchQuery,
    Tag,
    Tool,
    ToolRevision,
    User,
    tool_categories,
    tool_tags,
)
from app.models.enums import RevisionStatus, Role, ToolStatus, UserStatus
from app.services import audit, email, gdpr, search, sessions, settings_store
from app.services import tools as tool_service
from app.templating import render

pages = APIRouter()
actions = APIRouter()

PAGE = 50
SETTING_FIELDS: list[tuple[str, str]] = [
    ("score.w_search_click", "float"),
    ("score.w_outbound_click", "float"),
    ("score.w_star", "float"),
    ("score.w_github", "float"),
    ("score.half_life_days", "float"),
    ("search.beta_popularity", "float"),
    ("limits.max_pending_per_user", "int"),
    ("reports.auto_hide_threshold", "int"),
    ("site.registration_open", "bool"),
    ("site.banner_pt", "str"),
    ("site.banner_en", "str"),
    ("terms.current_version", "str"),
]


def _back(request: Request, path: str, flash: str | None = None) -> RedirectResponse:
    return RedirectResponse(
        f"/{request.state.lang}{path}{f'?flash={flash}' if flash else ''}", status_code=303
    )


# ---------- dashboard ----------


@pages.get("/admin")
def dashboard(request: Request, db: DB, user: ModDep) -> Response:
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
    oldest = min([d for d in (oldest_pending, oldest_revision) if d], default=None)
    top_tools = (
        db.scalars(
            select(Tool).where(Tool.status == ToolStatus.published).order_by(Tool.score.desc()).limit(10)
        )
        .unique()
        .all()
    )
    since = now - timedelta(days=7)
    return render(
        request,
        "admin/dashboard.html",
        {
            "users_total": db.scalar(
                select(func.count()).select_from(User).where(User.status != UserStatus.deleted)
            )
            or 0,
            "by_status": {k.value: v for k, v in by_status.items()},
            "weeks": weeks,
            "week_peak": max([max(w["signups"], w["submissions"]) for w in weeks] + [1]),
            "oldest": oldest,
            "top_tools": top_tools,
            "top_searches": _top_searches(db, since, zero=False, limit=10),
            "zero_searches": _top_searches(db, since, zero=True, limit=10),
            "now": now,
        },
    )


def _top_searches(db: DB, since: Any, zero: bool, limit: int) -> list[tuple[str, int]]:
    query = select(SearchQuery.q, func.count()).where(SearchQuery.created_at >= since, SearchQuery.q != "")
    if zero:
        query = query.where(SearchQuery.results_count == 0)
    rows = db.execute(query.group_by(SearchQuery.q).order_by(func.count().desc()).limit(limit)).all()
    return [(q, int(n)) for q, n in rows]


@pages.get("/admin/searches")
def searches(request: Request, db: DB, user: ModDep, days: int = 30) -> Response:
    days = days if days in (7, 30, 90) else 30
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
    return render(
        request,
        "admin/searches.html",
        {
            "days": days,
            "total": total,
            "zero_rate": (zero / total) if total else 0,
            "top": _top_searches(db, since, zero=False, limit=50),
            "zero_rows": _top_searches(db, since, zero=True, limit=50),
        },
    )


# ---------- users ----------


@pages.get("/admin/users")
def users(
    request: Request, db: DB, user: AdminDep, q: str = "", role: str = "", status: str = "", page: int = 1
) -> Response:
    query = select(User).where(User.status != UserStatus.deleted).order_by(User.created_at.desc())
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(User.email).like(like),
                func.lower(User.display_name).like(like),
                User.handle.like(like),
            )
        )
    if role in {r.value for r in Role}:
        query = query.where(User.role == Role(role))
    if status in {s.value for s in UserStatus}:
        query = query.where(User.status == UserStatus(status))
    page = max(1, page)
    rows = db.scalars(query.offset((page - 1) * PAGE).limit(PAGE + 1)).unique().all()
    return render(
        request,
        "admin/users.html",
        {
            "rows": rows[:PAGE],
            "has_next": len(rows) > PAGE,
            "page": page,
            "q": q,
            "role": role,
            "status": status,
        },
    )


def _user(db: DB, user_id: int) -> User:
    target = db.get(User, user_id)
    if target is None or target.status == UserStatus.deleted:
        raise HTTPException(status_code=404)
    return target


@pages.get("/admin/users/{user_id}")
def user_detail(request: Request, db: DB, user: AdminDep, user_id: int) -> Response:
    target = _user(db, user_id)
    tools = tool_service.owned_tools(db, target)
    log = db.scalars(
        select(AuditLog)
        .where(
            or_(
                AuditLog.actor_id == target.id,
                (AuditLog.target_type == "user") & (AuditLog.target_id == target.id),
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(30)
    ).all()
    return render(request, "admin/user.html", {"target": target, "tools": tools, "log": log})


def _admin_count(db: DB) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.admin, User.status == UserStatus.active)
        )
        or 0
    )


@actions.post("/admin/users/{user_id}/role")
def change_role(request: Request, db: DB, user: AdminDep, user_id: int, form: Form) -> Response:
    target = _user(db, user_id)
    try:
        new_role = Role(str(form.get("role")))
    except ValueError as exc:
        raise HTTPException(status_code=400) from exc
    if target.role == Role.admin and new_role != Role.admin and _admin_count(db) <= 1:
        return _back(request, f"/admin/users/{target.id}", "forbidden_last_admin")
    if new_role != target.role:
        audit.log(
            db, user.id, "user.role_change", "user", target.id, old=target.role.value, new=new_role.value
        )
        target.role = new_role
        db.commit()
    return _back(request, f"/admin/users/{target.id}", "role_changed")


@actions.post("/admin/users/{user_id}/suspend")
def suspend(request: Request, db: DB, user: AdminDep, user_id: int, form: Form) -> Response:
    target = _user(db, user_id)
    reason = str(form.get("reason") or "").strip()
    if not reason:
        return _back(request, f"/admin/users/{target.id}", "reason_required")
    if target.id == user.id or (target.role == Role.admin and _admin_count(db) <= 1):
        return _back(request, f"/admin/users/{target.id}", "forbidden_last_admin")
    target.status = UserStatus.suspended
    target.suspended_reason = reason
    sessions.destroy_all(db, target.id)
    audit.log(db, user.id, "user.suspend", "user", target.id, reason=reason)
    db.commit()
    return _back(request, f"/admin/users/{target.id}", "suspended")


@actions.post("/admin/users/{user_id}/unsuspend")
def unsuspend(request: Request, db: DB, user: AdminDep, user_id: int) -> Response:
    target = _user(db, user_id)
    target.status = UserStatus.active
    target.suspended_reason = None
    audit.log(db, user.id, "user.unsuspend", "user", target.id)
    db.commit()
    return _back(request, f"/admin/users/{target.id}", "unsuspended")


@actions.post("/admin/users/{user_id}/delete")
def delete_user(
    request: Request, db: DB, user: AdminDep, user_id: int, background: BackgroundTasks
) -> Response:
    target = _user(db, user_id)
    if target.id == user.id or (target.role == Role.admin and _admin_count(db) <= 1):
        return _back(request, f"/admin/users/{target.id}", "forbidden_last_admin")
    if target.status == UserStatus.suspended:
        target.status = (
            UserStatus.active
        )  # transitions need an active owner; the account is deleted right after
    gdpr.delete_account(db, target, user)
    db.commit()
    background.add_task(email.deliver_queued)
    return _back(request, "/admin/users", "user_deleted")


# ---------- categories ----------


def _category_counts(db: DB) -> dict[int, int]:
    rows = db.execute(
        select(tool_categories.c.category_id, func.count()).group_by(tool_categories.c.category_id)
    ).all()
    return {cid: int(n) for cid, n in rows}


@pages.get("/admin/categories")
def categories(request: Request, db: DB, user: AdminDep) -> Response:
    rows = db.scalars(select(Category).order_by(Category.sort_order, Category.name_pt)).all()
    return render(
        request,
        "admin/categories.html",
        {"rows": rows, "counts": _category_counts(db), "values": {}, "errors": {}},
    )


def _category_from_form(form: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    values = {
        k: str(form.get(k) or "").strip()
        for k in ("name_pt", "name_en", "description_pt", "description_en", "slug", "sort_order")
    }
    values["is_specialty"] = form.get("is_specialty") == "1"
    values["is_active"] = form.get("is_active") == "1"
    errors: dict[str, Any] = {}
    for key in ("name_pt", "name_en"):
        if not 2 <= len(values[key]) <= 80:
            errors[key] = ("Texto demasiado curto (mín. %(min_length)s caracteres).", {"min_length": 2})
    values["slug"] = slugify(values["slug"] or values["name_pt"], max_length=80)
    try:
        values["sort_order"] = int(values["sort_order"] or 0)
    except ValueError:
        errors["sort_order"] = ("Valor inválido.", {})
    return values, errors


@pages.post("/admin/categories")
def create_category(request: Request, db: DB, user: AdminDep, form: Form) -> Response:
    values, errors = _category_from_form(form)
    if db.scalar(select(Category.id).where(Category.slug == values["slug"])):
        errors["slug"] = ("Este identificador já está a ser usado.", {})
    if errors:
        rows = db.scalars(select(Category).order_by(Category.sort_order, Category.name_pt)).all()
        return render(
            request,
            "admin/categories.html",
            {"rows": rows, "counts": _category_counts(db), "values": values, "errors": errors},
            422,
        )
    cat = Category(
        slug=values["slug"],
        name_pt=values["name_pt"],
        name_en=values["name_en"],
        description_pt=values["description_pt"] or None,
        description_en=values["description_en"] or None,
        sort_order=values["sort_order"],
        is_specialty=values["is_specialty"],
        is_active=True,
    )
    db.add(cat)
    db.flush()
    audit.log(db, user.id, "category.create", "category", cat.id, slug=cat.slug)
    db.commit()
    return _back(request, "/admin/categories", "category_saved")


@pages.get("/admin/categories/{category_id}")
def category_detail(request: Request, db: DB, user: AdminDep, category_id: int) -> Response:
    cat = db.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404)
    values = {
        k: getattr(cat, k) or ""
        for k in ("name_pt", "name_en", "description_pt", "description_en", "slug", "sort_order")
    }
    values.update(is_specialty=cat.is_specialty, is_active=cat.is_active)
    return render(request, "admin/category.html", {"cat": cat, "values": values, "errors": {}})


@pages.post("/admin/categories/{category_id}")
def update_category(request: Request, db: DB, user: AdminDep, category_id: int, form: Form) -> Response:
    cat = db.get(Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404)
    values, errors = _category_from_form(form)
    other = db.scalar(select(Category.id).where(Category.slug == values["slug"], Category.id != cat.id))
    if other:
        errors["slug"] = ("Este identificador já está a ser usado.", {})
    if errors:
        return render(request, "admin/category.html", {"cat": cat, "values": values, "errors": errors}, 422)
    before = {
        k: getattr(cat, k) for k in ("slug", "name_pt", "name_en", "is_active", "is_specialty", "sort_order")
    }
    for key in ("slug", "name_pt", "name_en", "sort_order", "is_specialty", "is_active"):
        setattr(cat, key, values[key])
    cat.description_pt = values["description_pt"] or None
    cat.description_en = values["description_en"] or None
    audit.log(db, user.id, "category.update", "category", cat.id, before=before)
    affected = db.scalars(
        select(tool_categories.c.tool_id).where(tool_categories.c.category_id == cat.id)
    ).all()
    search.reindex_tools(db, list(affected))  # names are part of the index
    db.commit()
    return _back(request, "/admin/categories", "category_saved")


@actions.post("/admin/categories/{category_id}/move")
def move_category(request: Request, db: DB, user: AdminDep, category_id: int, form: Form) -> Response:
    rows = list(db.scalars(select(Category).order_by(Category.sort_order, Category.name_pt)).all())
    ids = [c.id for c in rows]
    if category_id not in ids:
        raise HTTPException(status_code=404)
    i = ids.index(category_id)
    j = max(0, min(len(rows) - 1, i + (-1 if form.get("direction") == "up" else 1)))
    rows[i], rows[j] = rows[j], rows[i]
    for pos, cat in enumerate(rows):
        cat.sort_order = (pos + 1) * 10
    audit.log(db, user.id, "category.move", "category", category_id)
    db.commit()
    return _back(request, "/admin/categories")


# ---------- tags ----------


@pages.get("/admin/tags")
def tags(request: Request, db: DB, user: AdminDep, q: str = "") -> Response:
    query = select(Tag).order_by(Tag.usage_count.desc(), Tag.label)
    if q:
        query = query.where(Tag.slug.like(f"%{slugify(q)}%"))
    return render(request, "admin/tags.html", {"rows": db.scalars(query.limit(300)).all(), "q": q})


@actions.post("/admin/tags/merge")
def merge_tags(request: Request, db: DB, user: AdminDep, form: Form) -> Response:
    """Moves every tool from the source tags to the target tag, then deletes the sources."""
    try:
        target_id = int(str(form.get("target")))
        source_ids = [int(v) for v in form.getlist("source") if str(v).isdigit() and int(v) != target_id]
    except ValueError as exc:
        raise HTTPException(status_code=400) from exc
    target = db.get(Tag, target_id)
    if target is None or not source_ids:
        return _back(request, "/admin/tags")
    affected: set[int] = set()
    for source_id in source_ids:
        source = db.get(Tag, source_id)
        if source is None:
            continue
        tool_ids = db.scalars(select(tool_tags.c.tool_id).where(tool_tags.c.tag_id == source_id)).all()
        for tool_id in tool_ids:
            affected.add(tool_id)
            tool = db.get(Tool, tool_id)
            if tool is not None:
                tool.tags = [t for t in tool.tags if t.id != source_id] + (
                    [] if any(t.id == target_id for t in tool.tags) else [target]
                )
        db.flush()
        db.delete(source)
    db.flush()
    tool_service.refresh_tag_counts(db, {target_id})
    search.reindex_tools(db, sorted(affected))
    audit.log(db, user.id, "tag.merge", "tag", target_id, sources=source_ids)
    db.commit()
    return _back(request, "/admin/tags", "merged")


@actions.post("/admin/tags/{tag_id}/delete")
def delete_tag(request: Request, db: DB, user: AdminDep, tag_id: int) -> Response:
    tag = db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404)
    affected = db.scalars(select(tool_tags.c.tool_id).where(tool_tags.c.tag_id == tag_id)).all()
    audit.log(db, user.id, "tag.delete", "tag", tag_id, label=tag.label)
    db.delete(tag)
    db.flush()
    search.reindex_tools(db, list(affected))
    db.commit()
    return _back(request, "/admin/tags", "tag_deleted")


# ---------- certification catalogue ----------


@pages.get("/admin/certifications")
def cert_catalogue(request: Request, db: DB, user: AdminDep) -> Response:
    rows = db.scalars(select(Certification).order_by(Certification.sort_order)).all()
    return render(request, "admin/certifications.html", {"rows": rows})


@pages.get("/admin/certifications/{cert_id}")
def cert_detail(request: Request, db: DB, user: AdminDep, cert_id: int) -> Response:
    cert = db.get(Certification, cert_id)
    if cert is None:
        raise HTTPException(status_code=404)
    values = {
        k: getattr(cert, k) or ""
        for k in ("badge_label", "label_template", "name_pt", "name_en", "help_pt", "help_en", "sort_order")
    }
    values["assurance_default"] = cert.assurance_default.value
    values["field_schema"] = json.dumps(cert.field_schema, ensure_ascii=False, indent=2)
    return render(request, "admin/certification.html", {"cert": cert, "values": values, "errors": {}})


@pages.post("/admin/certifications/{cert_id}")
def cert_update(request: Request, db: DB, user: AdminDep, cert_id: int, form: Form) -> Response:
    from app.models.enums import Assurance

    cert = db.get(Certification, cert_id)
    if cert is None:
        raise HTTPException(status_code=404)
    values = {
        k: str(form.get(k) or "").strip()
        for k in (
            "badge_label",
            "label_template",
            "name_pt",
            "name_en",
            "help_pt",
            "help_en",
            "sort_order",
            "assurance_default",
            "field_schema",
        )
    }
    errors: dict[str, Any] = {}
    try:
        schema = json.loads(values["field_schema"] or "[]")
        if not isinstance(schema, list) or not all(isinstance(f, dict) and f.get("key") for f in schema):
            raise ValueError
    except ValueError:
        errors["field_schema"] = ("Valor inválido.", {})
        schema = cert.field_schema
    for key in ("badge_label", "name_pt", "name_en"):
        if not values[key]:
            errors[key] = ("Campo obrigatório.", {})
    if values["assurance_default"] not in {a.value for a in Assurance}:
        errors["assurance_default"] = ("Escolha uma opção válida.", {})
    try:
        sort_order = int(values["sort_order"] or 0)
    except ValueError:
        errors["sort_order"] = ("Valor inválido.", {})
        sort_order = cert.sort_order
    if errors:
        return render(
            request, "admin/certification.html", {"cert": cert, "values": values, "errors": errors}, 422
        )
    cert.badge_label = values["badge_label"][:30]
    cert.label_template = values["label_template"] or None
    cert.name_pt, cert.name_en = values["name_pt"], values["name_en"]
    cert.help_pt, cert.help_en = values["help_pt"] or None, values["help_en"] or None
    cert.assurance_default = Assurance(values["assurance_default"])
    cert.field_schema = schema
    cert.sort_order = sort_order
    cert.is_core = form.get("is_core") == "1"
    cert.is_active = form.get("is_active") == "1"
    audit.log(db, user.id, "certification.update", "certification", cert.id, code=cert.code)
    db.commit()
    return _back(request, "/admin/certifications", "certification_saved")


# ---------- settings ----------


def _settings_values(db: DB) -> dict[str, Any]:
    values: dict[str, Any] = {key: settings_store.get(db, key) for key, _ in SETTING_FIELDS}
    for key in settings_store.LEGAL_KEYS:
        values[f"legal.{key}"] = settings_store.get(db, f"legal.{key}") or ""
    return values


@pages.get("/admin/settings")
def settings_page(request: Request, db: DB, user: AdminDep) -> Response:
    return render(
        request,
        "admin/settings.html",
        {
            "values": _settings_values(db),
            "errors": {},
            "fields": SETTING_FIELDS,
            "legal_keys": settings_store.LEGAL_KEYS,
        },
    )


@pages.post("/admin/settings")
def settings_save(request: Request, db: DB, user: AdminDep, form: Form) -> Response:
    errors: dict[str, Any] = {}
    parsed: dict[str, Any] = {}
    for key, kind in SETTING_FIELDS:
        raw = form.get(key)
        try:
            if kind == "bool":
                parsed[key] = raw == "1"
            elif kind == "int":
                parsed[key] = int(str(raw))
                if parsed[key] < 1:
                    raise ValueError
            elif kind == "float":
                parsed[key] = float(str(raw).replace(",", "."))
                if parsed[key] < 0:
                    raise ValueError
            else:
                parsed[key] = str(raw or "").strip()[:300]
        except (TypeError, ValueError):
            errors[key] = ("Valor inválido.", {})
    if errors:
        values = {**_settings_values(db), **{k: form.get(k) for k, _ in SETTING_FIELDS}}
        return render(
            request,
            "admin/settings.html",
            {
                "values": values,
                "errors": errors,
                "fields": SETTING_FIELDS,
                "legal_keys": settings_store.LEGAL_KEYS,
            },
            422,
        )
    current = _settings_values(db)
    for key, value in parsed.items():
        if current.get(key) != value:
            settings_store.set_value(db, key, value, user.id)
    for key in settings_store.LEGAL_KEYS:
        raw = form.get(f"legal.{key}")
        if raw is None:
            continue
        value = str(raw).strip()
        if value != (current.get(f"legal.{key}") or ""):
            settings_store.set_value(db, f"legal.{key}", value, user.id)
    db.commit()
    return _back(request, "/admin/settings", "saved")


# ---------- audit ----------


@pages.get("/admin/audit")
def audit_log(
    request: Request, db: DB, user: AdminDep, actor: str = "", action: str = "", page: int = 1
) -> Response:
    query = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if actor.isdigit():
        query = query.where(AuditLog.actor_id == int(actor))
    if action:
        query = query.where(AuditLog.action.like(f"{action.strip()[:40]}%"))
    page = max(1, page)
    rows = db.scalars(query.offset((page - 1) * PAGE).limit(PAGE + 1)).all()
    actors = {
        u.id: u
        for u in db.scalars(select(User).where(User.id.in_({r.actor_id for r in rows if r.actor_id}))).all()
    }
    return render(
        request,
        "admin/audit.html",
        {
            "rows": rows[:PAGE],
            "has_next": len(rows) > PAGE,
            "page": page,
            "actor": actor,
            "action": action,
            "actors": actors,
        },
    )


# ---------- invites & reset links (D26) ----------


def _invite_page(
    request: Request,
    db: DB,
    created_link: str | None = None,
    errors: dict[str, Any] | None = None,
    status: int = 200,
) -> Response:
    from app.models import Invite

    rows = db.scalars(select(Invite).order_by(Invite.created_at.desc()).limit(100)).all()
    return render(
        request,
        "admin/invites.html",
        {
            "rows": rows,
            "created_link": created_link,
            "errors": errors or {},
            "registration_open": settings_store.get(db, "site.registration_open"),
            "now": utcnow(),
        },
        status_code=status,
    )


@pages.get("/admin/invites")
def invites(request: Request, db: DB, user: AdminDep) -> Response:
    return _invite_page(request, db)


@pages.post("/admin/invites")
def create_invite(request: Request, db: DB, user: AdminDep, form: Form) -> Response:
    from app.config import get_settings
    from app.services import auth as auth_service

    errors: dict[str, Any] = {}
    address = str(form.get("email") or "").strip() or None
    try:
        max_uses = int(str(form.get("max_uses") or 1))
        days = int(str(form.get("days") or auth_service.INVITE_DEFAULT_DAYS))
        if max_uses < 1 or days < 1:
            raise ValueError
    except ValueError:
        errors["max_uses"] = ("Valor inválido.", {})
        max_uses, days = 1, auth_service.INVITE_DEFAULT_DAYS
    if address and "@" not in address:
        errors["email"] = ("Indique um email válido.", {})
    if errors:
        return _invite_page(request, db, errors=errors, status=422)
    _, code = auth_service.create_invite(db, user, address, str(form.get("note") or ""), max_uses, days)
    db.commit()
    link = f"{get_settings().base_url.rstrip('/')}/{request.state.lang}/register?invite={code}"
    return _invite_page(request, db, created_link=link)


@actions.post("/admin/invites/{invite_id}/revoke")
def revoke_invite(request: Request, db: DB, user: AdminDep, invite_id: int) -> Response:
    from app.models import Invite
    from app.services import auth as auth_service

    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status_code=404)
    auth_service.revoke_invite(db, invite, user)
    db.commit()
    return _back(request, "/admin/invites", "invite_revoked")


@pages.post("/admin/users/{user_id}/reset-link")
def reset_link(request: Request, db: DB, user: AdminDep, user_id: int) -> Response:
    from app.config import get_settings
    from app.services import auth as auth_service

    target = _user(db, user_id)
    token = auth_service.create_reset_link(db, target, user)
    db.commit()
    link = f"{get_settings().base_url.rstrip('/')}/{target.locale.value}/reset/{token}"
    tools = tool_service.owned_tools(db, target)
    log = db.scalars(
        select(AuditLog)
        .where(
            or_(
                AuditLog.actor_id == target.id,
                (AuditLog.target_type == "user") & (AuditLog.target_id == target.id),
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(30)
    ).all()
    return render(
        request, "admin/user.html", {"target": target, "tools": tools, "log": log, "reset_link": link}
    )


@pages.get("/admin/emails")
def outbox(request: Request, db: DB, user: AdminDep, page: int = 1) -> Response:
    """Notifications waiting for delivery (or kept for reference) while SMTP is not configured."""
    from app.config import get_settings
    from app.models import EmailOutbox

    page = max(1, page)
    rows = db.scalars(
        select(EmailOutbox).order_by(EmailOutbox.id.desc()).offset((page - 1) * PAGE).limit(PAGE + 1)
    ).all()
    return render(
        request,
        "admin/emails.html",
        {
            "rows": rows[:PAGE],
            "has_next": len(rows) > PAGE,
            "page": page,
            "smtp": bool(get_settings().smtp_host),
        },
    )
