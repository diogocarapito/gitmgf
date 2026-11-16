"""Tool lifecycle (TECH_SPEC §7). `transition()` is the only place that changes `tool.status`."""

import difflib
import html
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from markupsafe import Markup
from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.i18n import N_, t
from app.i18n.labels import OSI_LICENSES
from app.models import (
    Category,
    Certification,
    Star,
    Tag,
    Tool,
    ToolGithub,
    ToolMedia,
    ToolRevision,
    User,
)
from app.models.enums import MediaState, RevisionStatus, ToolStatus
from app.services import (
    audit,
    certifications,
    email,
    github,
    markdown,
    media,
    permissions,
    search,
    settings_store,
)

SCALAR_FIELDS = (
    "title_pt", "title_en", "summary_pt", "summary_en", "description_pt", "description_en", "tool_type",
    "care_setting", "platforms", "tool_languages", "website_url", "repo_url", "download_url", "docs_url",
    "license_spdx", "pricing", "patient_data", "intended_use", "version_label",
)  # fmt: skip
IN_PLACE_STATUSES = (ToolStatus.draft, ToolStatus.rejected)
REVISION_STATUSES = (ToolStatus.published, ToolStatus.archived, ToolStatus.hidden)
PURGE_AFTER = timedelta(days=30)


class InvalidTransition(Exception):
    pass


class ToolError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message  # msgid


# ---------- state machine ----------

ANY_LIVE = (
    ToolStatus.draft, ToolStatus.pending, ToolStatus.published, ToolStatus.rejected, ToolStatus.hidden, ToolStatus.archived,
)  # fmt: skip

# (from, action) -> (to, who may do it)
TRANSITIONS: dict[tuple[ToolStatus, str], tuple[ToolStatus, str]] = {
    (ToolStatus.draft, "submit"): (ToolStatus.pending, "owner"),
    (ToolStatus.rejected, "submit"): (ToolStatus.pending, "owner"),
    (ToolStatus.pending, "withdraw"): (ToolStatus.draft, "owner"),
    (ToolStatus.pending, "approve"): (ToolStatus.published, "moderator"),
    (ToolStatus.pending, "reject"): (ToolStatus.rejected, "moderator"),
    (ToolStatus.pending, "request_changes"): (ToolStatus.draft, "moderator"),
    (ToolStatus.published, "hide"): (ToolStatus.hidden, "moderator"),
    (ToolStatus.archived, "hide"): (ToolStatus.hidden, "moderator"),
    (ToolStatus.published, "auto_hide"): (ToolStatus.hidden, "system"),
    (ToolStatus.archived, "auto_hide"): (ToolStatus.hidden, "system"),
    (ToolStatus.hidden, "unhide"): (ToolStatus.published, "moderator"),
    (ToolStatus.published, "archive"): (ToolStatus.archived, "owner"),
    (ToolStatus.archived, "unarchive"): (ToolStatus.published, "owner"),
    **{(status, "delete"): (ToolStatus.deleted, "owner_or_admin") for status in ANY_LIVE},
}
REASON_REQUIRED = {"reject", "request_changes", "hide", "auto_hide"}


def allowed_actions(tool: Tool) -> set[str]:
    return {action for (status, action) in TRANSITIONS if status == tool.status}


def _check_actor(who: str, tool: Tool, actor: User | None) -> None:
    if who == "system":
        if actor is not None:
            raise InvalidTransition("system only")
        return
    if actor is None or not actor.is_active:
        raise InvalidTransition("actor required")
    if who == "owner" and actor.id != tool.owner_id:
        raise InvalidTransition("owner only")
    if who == "moderator" and not permissions.can_moderate(actor, tool):
        raise InvalidTransition("moderator (not owner) only")
    if who == "owner_or_admin" and not (actor.id == tool.owner_id or actor.is_admin):
        raise InvalidTransition("owner or admin only")


def pending_count(db: Session, user_id: int) -> int:
    tools = db.scalar(
        select(func.count())
        .select_from(Tool)
        .where(Tool.owner_id == user_id, Tool.status == ToolStatus.pending)
    )
    revisions = db.scalar(
        select(func.count())
        .select_from(ToolRevision)
        .join(Tool, Tool.id == ToolRevision.tool_id)
        .where(Tool.owner_id == user_id, ToolRevision.status == RevisionStatus.pending)
    )
    return int(tools or 0) + int(revisions or 0)


def check_pending_limit(db: Session, user_id: int, exclude_tool: Tool | None = None) -> None:
    limit = settings_store.get_int(db, "limits.max_pending_per_user")
    current = pending_count(db, user_id)
    if exclude_tool is not None and pending_revision(db, exclude_tool) is not None:
        current -= 1  # updating an existing pending revision doesn't add one
    if current >= limit:
        raise ToolError(N_("Atingiu o limite de submissões pendentes. Aguarde a revisão das anteriores."))


def transition(
    db: Session,
    tool: Tool,
    action: str,
    actor: User | None,
    reason: str | None = None,
    claim_rejections: dict[str, str] | None = None,
) -> Tool:
    key = (tool.status, action)
    if key not in TRANSITIONS:
        raise InvalidTransition(f"{tool.status} -/-> {action}")
    target, who = TRANSITIONS[key]
    _check_actor(who, tool, actor)
    if action in REASON_REQUIRED and not (reason and reason.strip()):
        raise InvalidTransition("reason required")
    owner = tool.owner
    now = utcnow()
    previous = tool.status
    actor_id = actor.id if actor else None
    ctx = {"title": tool.title_pt, "slug": tool.slug, "reason": reason or "", "tool_id": tool.id}

    if action == "submit":
        errors = submission_problems(db, tool)
        if errors:
            raise ToolError(N_("Faltam campos obrigatórios. Reveja o formulário antes de submeter."))
        check_pending_limit(db, tool.owner_id)
        tool.submitted_at = now
        tool.rejection_reason = None
        email.enqueue(db, owner.email, "submission_received", ctx, owner.locale.value)
    elif action == "approve":
        rejected = certifications.approve_new_tool_claims(tool, actor_id or 0, claim_rejections or {})
        tool.published_at = tool.published_at or now
        tool.last_content_update_at = now
        tool.rejection_reason = None
        ctx["rejected_claims"] = _claims_text(db, rejected, owner.locale.value)
        email.enqueue(db, owner.email, "tool_approved", ctx, owner.locale.value)
    elif action in ("reject", "request_changes"):
        tool.rejection_reason = reason
        ctx["returned_to_draft"] = action == "request_changes"
        email.enqueue(db, owner.email, "tool_rejected", ctx, owner.locale.value)
    elif action in ("hide", "auto_hide"):
        ctx["automatic"] = action == "auto_hide"
        email.enqueue(db, owner.email, "tool_hidden", ctx, owner.locale.value)
    elif action == "unhide":
        email.enqueue(db, owner.email, "tool_unhidden", ctx, owner.locale.value)
    elif action == "delete":
        tool.deleted_at = now
        for revision in db.scalars(
            select(ToolRevision).where(
                ToolRevision.tool_id == tool.id, ToolRevision.status == RevisionStatus.pending
            )
        ):
            _close_revision(db, revision, RevisionStatus.withdrawn, actor_id, None)

    tool.status = target
    db.flush()
    if target == ToolStatus.published:
        search.reindex_tool(db, tool.id)
    elif previous == ToolStatus.published:
        search.remove_tool(db, tool.id)
    if ToolStatus.published in (target, previous):
        refresh_tag_counts(db, {tag.id for tag in tool.tags})
    audit.log(
        db,
        actor_id,
        f"tool.{action}",
        "tool",
        tool.id,
        **{"from": previous.value, "to": target.value, "reason": reason},
    )
    return tool


def _claims_text(db: Session, rejected: list[tuple[str, str]], lang: str) -> str:
    if not rejected:
        return ""
    names = {c.code: c.name(lang) for c in certifications.catalogue(db, active_only=False)}
    return "\n".join(f"- {names.get(code, code)}: {reason}" for code, reason in rejected)


# ---------- creating & editing ----------


def unique_slug(db: Session, title: str, tool_id: int | None = None) -> str:
    base = slugify(title, max_length=80, word_boundary=True) or "ferramenta"
    candidate, n = base, 2
    while True:
        query = select(Tool.id).where(Tool.slug == candidate)
        if tool_id is not None:
            query = query.where(Tool.id != tool_id)
        if db.scalar(query) is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def _tags(db: Session, labels: list[str]) -> list[Tag]:
    out = []
    for label in labels:
        slug = slugify(label)
        tag = db.scalar(select(Tag).where(Tag.slug == slug))
        if tag is None:
            tag = Tag(slug=slug, label=label)
            db.add(tag)
        out.append(tag)
    return out


def refresh_tag_counts(db: Session, tag_ids: set[int]) -> None:
    from app.models import tool_tags

    for tag_id in tag_ids:
        tag = db.get(Tag, tag_id)
        if tag is not None:
            count = db.scalar(
                select(func.count())
                .select_from(tool_tags)
                .join(Tool, Tool.id == tool_tags.c.tool_id)
                .where(tool_tags.c.tag_id == tag_id, Tool.status == ToolStatus.published)
            )
            tag.usage_count = int(count or 0)


def is_open_source(license_spdx: str | None, repo_url: str | None) -> bool:
    return bool(license_spdx in OSI_LICENSES and repo_url)


def apply_data(db: Session, tool: Tool, data: dict[str, Any]) -> None:
    """Writes a full snapshot (form data or approved revision) onto the tool."""
    for name in SCALAR_FIELDS:
        if name in data:
            setattr(tool, name, data[name])
    tool.title_pt = (data.get("title_pt") or tool.title_pt or "")[:80]
    tool.summary_pt = data.get("summary_pt") or ""
    tool.description_pt = data.get("description_pt") or ""
    tool.intended_use = data.get("intended_use") or ""
    tool.platforms = list(data.get("platforms") or [])
    tool.tool_languages = list(data.get("tool_languages") or [])
    tool.description_html_pt = markdown.render(tool.description_pt)
    tool.description_html_en = markdown.render(tool.description_en or "") or None
    tool.is_open_source = is_open_source(tool.license_spdx, tool.repo_url)
    if "category_ids" in data:
        ids = list(dict.fromkeys(int(i) for i in data["category_ids"]))[:5]
        cats = (
            db.scalars(select(Category).where(Category.id.in_(ids), Category.is_active.is_(True))).all()
            if ids
            else []
        )
        tool.categories = sorted(cats, key=lambda c: ids.index(c.id))
    if "tags" in data:
        old = {tag.id for tag in tool.tags}
        tool.tags = _tags(db, list(data["tags"]))
        db.flush()
        refresh_tag_counts(db, old | {tag.id for tag in tool.tags})
    _sync_github(tool)


def _sync_github(tool: Tool) -> None:
    parsed = github.parse_repo_url(tool.repo_url)
    if parsed is None:
        tool.github = None
        return
    owner, repo = parsed
    if tool.github is None or (tool.github.owner, tool.github.repo) != (owner, repo):
        tool.github = ToolGithub(owner=owner, repo=repo)


def snapshot(tool: Tool) -> dict[str, Any]:
    data: dict[str, Any] = {name: getattr(tool, name) for name in SCALAR_FIELDS}
    for key in ("tool_type", "care_setting", "pricing", "patient_data"):
        value = data[key]
        data[key] = value.value if value is not None and hasattr(value, "value") else value
    data["platforms"] = list(tool.platforms or [])
    data["tool_languages"] = list(tool.tool_languages or [])
    data["category_ids"] = [c.id for c in tool.categories]
    data["tags"] = [tag.label for tag in tool.tags]
    data["certifications"] = certifications.snapshot(tool)
    data["media_order"] = [m.id for m in tool.media if m.state == MediaState.live]
    return data


def create_tool(db: Session, owner: User, data: dict[str, Any], claims: dict[str, dict[str, Any]]) -> Tool:
    tool = Tool(owner_id=owner.id, status=ToolStatus.draft, title_pt=data["title_pt"])
    tool.owner = owner
    tool.slug = unique_slug(db, data["title_pt"])
    db.add(tool)
    apply_data(db, tool, data)
    db.flush()
    certifications.save_draft_claims(db, tool, claims, certifications.by_code(db))
    audit.log(db, owner.id, "tool.create", "tool", tool.id)
    return tool


def editable_in_place(tool: Tool) -> bool:
    return tool.status in IN_PLACE_STATUSES


def pending_revision(db: Session, tool: Tool) -> ToolRevision | None:
    return db.scalar(
        select(ToolRevision).where(
            ToolRevision.tool_id == tool.id, ToolRevision.status == RevisionStatus.pending
        )
    )


def save_edit(
    db: Session,
    tool: Tool,
    actor: User,
    data: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    declarations: bool,
) -> str:
    """Drafts/rejected are edited in place; public tools get a pending revision (live page unchanged).

    Returns "in_place", "revision" or "unchanged".
    """
    if not permissions.can_edit_tool(actor, tool):
        raise InvalidTransition("cannot edit")
    certs = certifications.by_code(db)
    if editable_in_place(tool):
        if tool.published_at is None:
            tool.slug = unique_slug(db, data["title_pt"], tool.id)
        apply_data(db, tool, data)
        certifications.save_draft_claims(db, tool, claims, certs)
        if declarations:
            tool.declarations_accepted_at = utcnow()
        tool.updated_at = utcnow()
        return "in_place"
    if tool.status not in REVISION_STATUSES:
        raise ToolError(N_("Retire a submissão para a poder editar."))

    # Removing a certification applies immediately: it only makes the listing more conservative.
    removed = certifications.remove_claims_now(db, tool, set(claims))
    if removed:
        audit.log(db, actor.id, "tool.cert_remove", "tool", tool.id, codes=removed)

    revision = pending_revision(db, tool)
    base = revision.data if revision is not None else snapshot(tool)
    proposed = {
        **base,
        **data,
        "certifications": [{"code": c, "details": claims[c]} for c in sorted(claims)],
    }
    proposed.setdefault("media_order", snapshot(tool)["media_order"])
    live = snapshot(tool)
    if revision is None and _same(live, proposed):
        return "unchanged"
    if revision is None:
        check_pending_limit(db, tool.owner_id)
        revision = ToolRevision(tool_id=tool.id, submitted_by=actor.id, data=proposed)
        db.add(revision)
        db.flush()
        audit.log(db, actor.id, "revision.submit", "tool", tool.id, revision_id=revision.id)
    else:
        revision.data = proposed
        revision.created_at = utcnow()
    if declarations:
        tool.declarations_accepted_at = utcnow()
    return "revision"


def _same(live: dict[str, Any], proposed: dict[str, Any]) -> bool:
    keys = set(SCALAR_FIELDS) | {"category_ids", "tags", "certifications", "media_order"}
    return all(_norm(live.get(k)) == _norm(proposed.get(k)) for k in keys)


def _norm(value: Any) -> Any:
    if value in ("", None, []):
        return None
    return value


def submission_problems(db: Session, tool: Tool) -> dict[str, Any]:
    from app.forms.tool import ToolForm

    data = snapshot(tool)
    form = ToolForm.model_validate(
        {
            **{k: v for k, v in data.items() if k in ToolForm.model_fields},
            "decl_author": tool.declarations_accepted_at is not None,
            "decl_no_patient_data": tool.declarations_accepted_at is not None,
            "decl_no_validation": tool.declarations_accepted_at is not None,
        }
    )
    problems: dict[str, Any] = dict(form.submission_errors())
    certs = certifications.by_code(db)
    check = certifications.check_claims(
        certs,
        {
            c["code"]: {
                k: str(v) if not isinstance(v, bool) else ("1" if v else "") for k, v in c["details"].items()
            }
            for c in data["certifications"]
        },
        data["tool_type"],
        [c.slug for c in tool.categories],
        data["patient_data"],
        full=True,
    )
    problems.update(check.errors)
    return problems


# ---------- revisions ----------


def _close_revision(
    db: Session, revision: ToolRevision, status: RevisionStatus, actor_id: int | None, reason: str | None
) -> None:
    revision.status = status
    revision.reviewer_id = actor_id if status in (RevisionStatus.approved, RevisionStatus.rejected) else None
    revision.review_reason = reason
    revision.reviewed_at = utcnow()
    if status != RevisionStatus.approved:
        for item in db.scalars(
            select(ToolMedia).where(
                ToolMedia.revision_id == revision.id, ToolMedia.state == MediaState.pending
            )
        ):
            media.delete_files(item.tool_id, item.file_name, item.thumb_name)
            db.delete(item)


def withdraw_revision(db: Session, revision: ToolRevision, actor: User) -> None:
    if revision.status != RevisionStatus.pending or actor.id != revision.tool.owner_id:
        raise InvalidTransition("cannot withdraw")
    _close_revision(db, revision, RevisionStatus.withdrawn, actor.id, None)
    audit.log(db, actor.id, "revision.withdraw", "tool", revision.tool_id, revision_id=revision.id)


def approve_revision(
    db: Session, revision: ToolRevision, actor: User, claim_rejections: dict[str, str] | None = None
) -> None:
    tool = revision.tool
    if revision.status != RevisionStatus.pending or not permissions.can_moderate(actor, tool):
        raise InvalidTransition("cannot approve revision")
    data = revision.data
    apply_data(db, tool, data)
    rejected = certifications.apply_revision_claims(
        db, tool, data.get("certifications", []), certifications.by_code(db), actor.id, claim_rejections or {}
    )
    order = [int(i) for i in data.get("media_order", [])]
    for item in list(tool.media):
        if item.id in order:
            item.state = MediaState.live
            item.sort_order = order.index(item.id)
            item.revision_id = None
        elif item.state in (MediaState.live, MediaState.pending) and (
            item.revision_id in (None, revision.id)
        ):
            media.delete_files(tool.id, item.file_name, item.thumb_name)
            tool.media.remove(item)
            db.delete(item)
    now = utcnow()
    tool.last_content_update_at = now
    tool.updated_at = now
    _close_revision(db, revision, RevisionStatus.approved, actor.id, None)
    db.flush()
    search.reindex_tool(db, tool.id)
    owner = tool.owner
    email.enqueue(
        db,
        owner.email,
        "revision_approved",
        {
            "title": tool.title_pt,
            "slug": tool.slug,
            "rejected_claims": _claims_text(db, rejected, owner.locale.value),
        },
        owner.locale.value,
    )
    audit.log(
        db,
        actor.id,
        "revision.approve",
        "tool",
        tool.id,
        revision_id=revision.id,
        rejected_claims=[c for c, _ in rejected],
    )


def reject_revision(db: Session, revision: ToolRevision, actor: User, reason: str) -> None:
    tool = revision.tool
    if revision.status != RevisionStatus.pending or not permissions.can_moderate(actor, tool):
        raise InvalidTransition("cannot reject revision")
    if not reason.strip():
        raise InvalidTransition("reason required")
    _close_revision(db, revision, RevisionStatus.rejected, actor.id, reason)
    owner = tool.owner
    email.enqueue(
        db,
        owner.email,
        "revision_rejected",
        {"title": tool.title_pt, "slug": tool.slug, "reason": reason},
        owner.locale.value,
    )
    audit.log(db, actor.id, "revision.reject", "tool", tool.id, revision_id=revision.id, reason=reason)


# ---------- media ----------


def effective_media(db: Session, tool: Tool) -> list[ToolMedia]:
    """What the editor shows: live media, or the pending revision's proposed order."""
    revision = pending_revision(db, tool) if not editable_in_place(tool) else None
    if revision is None:
        return [m for m in tool.media if m.state == MediaState.live]
    by_id = {m.id: m for m in tool.media}
    return [by_id[i] for i in revision.data.get("media_order", []) if i in by_id]


def _ensure_revision(db: Session, tool: Tool, actor: User) -> ToolRevision:
    revision = pending_revision(db, tool)
    if revision is None:
        check_pending_limit(db, tool.owner_id)
        revision = ToolRevision(tool_id=tool.id, submitted_by=actor.id, data=snapshot(tool))
        db.add(revision)
        db.flush()
        audit.log(db, actor.id, "revision.submit", "tool", tool.id, revision_id=revision.id)
    return revision


def add_media(
    db: Session, tool: Tool, actor: User, data: bytes, alt_pt: str, alt_en: str | None
) -> ToolMedia:
    if not permissions.can_edit_tool(actor, tool) or tool.status == ToolStatus.pending:
        raise InvalidTransition("cannot edit media")
    if len(effective_media(db, tool)) >= media.MAX_PER_TOOL:
        raise ToolError(N_("Máximo de 5 capturas de ecrã por ferramenta."))
    if not alt_pt.strip():
        raise ToolError(N_("O texto alternativo em português é obrigatório."))
    processed = media.process(data, tool.id)
    in_place = editable_in_place(tool)
    item = ToolMedia(
        tool_id=tool.id,
        state=MediaState.live if in_place else MediaState.pending,
        file_name=processed.file_name,
        thumb_name=processed.thumb_name,
        width=processed.width,
        height=processed.height,
        alt_text_pt=alt_pt.strip()[:200],
        alt_text_en=(alt_en or "").strip()[:200] or None,
        sort_order=len(effective_media(db, tool)),
    )
    tool.media.append(item)
    db.flush()
    if not in_place:
        revision = _ensure_revision(db, tool, actor)
        item.revision_id = revision.id
        revision.data = {**revision.data, "media_order": [*revision.data.get("media_order", []), item.id]}
    return item


def remove_media(db: Session, item: ToolMedia, actor: User) -> None:
    tool = item.tool
    if not permissions.can_edit_tool(actor, tool) or tool.status == ToolStatus.pending:
        raise InvalidTransition("cannot edit media")
    if editable_in_place(tool) or item.state == MediaState.pending:
        if item.state == MediaState.pending:
            revision = pending_revision(db, tool)
            if revision is not None:
                revision.data = {
                    **revision.data,
                    "media_order": [i for i in revision.data.get("media_order", []) if i != item.id],
                }
        media.delete_files(tool.id, item.file_name, item.thumb_name)
        tool.media.remove(item)
        db.delete(item)
        return
    revision = _ensure_revision(db, tool, actor)
    revision.data = {
        **revision.data,
        "media_order": [i for i in revision.data.get("media_order", []) if i != item.id],
    }


def move_media(db: Session, item: ToolMedia, actor: User, direction: int) -> None:
    tool = item.tool
    if not permissions.can_edit_tool(actor, tool) or tool.status == ToolStatus.pending:
        raise InvalidTransition("cannot edit media")
    if editable_in_place(tool):
        ordered = [m for m in tool.media if m.state == MediaState.live]
        ids = [m.id for m in ordered]
    else:
        revision = _ensure_revision(db, tool, actor)
        ids = list(revision.data.get("media_order", []))
    if item.id not in ids:
        return
    i = ids.index(item.id)
    j = max(0, min(len(ids) - 1, i + direction))
    ids[i], ids[j] = ids[j], ids[i]
    if editable_in_place(tool):
        by_id = {m.id: m for m in tool.media}
        for pos, mid in enumerate(ids):
            by_id[mid].sort_order = pos
    else:
        revision.data = {**revision.data, "media_order": ids}


# ---------- stars ----------


def toggle_star(db: Session, tool: Tool, user: User) -> bool:
    if not permissions.can_star(user, tool):
        raise InvalidTransition("cannot star")
    existing = db.get(Star, (user.id, tool.id))
    if existing is not None:
        db.delete(existing)
        starred = False
    else:
        db.add(Star(user_id=user.id, tool_id=tool.id))
        starred = True
    db.flush()
    tool.stars_count = int(
        db.scalar(select(func.count()).select_from(Star).where(Star.tool_id == tool.id)) or 0
    )
    return starred


def is_starred(db: Session, tool: Tool, user: User | None) -> bool:
    return user is not None and db.get(Star, (user.id, tool.id)) is not None


# ---------- revision diff (TECH_SPEC §7.2) ----------

FIELD_LABELS = {
    "title_pt": N_("Título (PT)"),
    "title_en": N_("Título (EN)"),
    "summary_pt": N_("Resumo (PT)"),
    "summary_en": N_("Resumo (EN)"),
    "description_pt": N_("Descrição (PT)"),
    "description_en": N_("Descrição (EN)"),
    "tool_type": N_("Tipo de ferramenta"),
    "care_setting": N_("Contexto de cuidados"),
    "platforms": N_("Plataformas"),
    "tool_languages": N_("Idiomas da ferramenta"),
    "website_url": N_("Site ou aplicação (URL)"),
    "repo_url": N_("Repositório (URL)"),
    "download_url": N_("Transferência / versões (URL)"),
    "docs_url": N_("Documentação (URL)"),
    "license_spdx": N_("Licença"),
    "pricing": N_("Preço"),
    "patient_data": N_("Dados de utentes"),
    "intended_use": N_("Utilização prevista"),
    "version_label": N_("Versão"),
    "category_ids": N_("Categorias"),
    "tags": N_("Etiquetas"),
    "certifications": N_("Certificações"),
    "media_order": N_("Capturas de ecrã"),
}
LONG_TEXT = {"description_pt", "description_en", "intended_use", "summary_pt", "summary_en"}


@dataclass
class FieldDiff:
    name: str
    label: str
    kind: str  # scalar | text | list | media | certs
    old: Any = None
    new: Any = None
    html: Markup | None = None
    added: list[Any] = field(default_factory=list)
    removed: list[Any] = field(default_factory=list)


def word_diff(old: str, new: str) -> Markup:
    a, b = re.findall(r"\S+|\s+", old or ""), re.findall(r"\S+|\s+", new or "")
    out: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(html.escape("".join(a[i1:i2])))
        if op in ("delete", "replace"):
            out.append(f"<del>{html.escape(''.join(a[i1:i2]))}</del>")
        if op in ("insert", "replace"):
            out.append(f"<ins>{html.escape(''.join(b[j1:j2]))}</ins>")
    return Markup("".join(out))  # noqa: S704 - inputs escaped above


def diff(db: Session, live: dict[str, Any], proposed: dict[str, Any], lang: str) -> list[FieldDiff]:
    out: list[FieldDiff] = []
    for name, label in FIELD_LABELS.items():
        old, new = live.get(name), proposed.get(name)
        if _norm(old) == _norm(new):
            continue
        label_text = t(lang, label)
        if name in LONG_TEXT:
            out.append(FieldDiff(name, label_text, "text", old, new, html=word_diff(old or "", new or "")))
        elif name == "category_ids":
            names = {c.id: c.name(lang) for c in db.scalars(select(Category)).all()}
            o, n = set(old or []), set(new or [])
            out.append(
                FieldDiff(
                    name,
                    label_text,
                    "list",
                    added=[names.get(i, i) for i in n - o],
                    removed=[names.get(i, i) for i in o - n],
                )
            )
        elif name in ("tags", "platforms", "tool_languages"):
            o, n = set(old or []), set(new or [])
            out.append(FieldDiff(name, label_text, "list", added=sorted(n - o), removed=sorted(o - n)))
        elif name == "media_order":
            old_ids, new_ids = list(old or []), list(new or [])
            out.append(
                FieldDiff(
                    name,
                    label_text,
                    "media",
                    old=old_ids,
                    new=new_ids,
                    added=[i for i in new_ids if i not in old_ids],
                    removed=[i for i in old_ids if i not in new_ids],
                )
            )
        elif name == "certifications":
            old_claims = {c["code"]: c["details"] for c in old or []}
            new_claims = {c["code"]: c["details"] for c in new or []}
            cert_names = {c.code: c.name(lang) for c in db.scalars(select(Certification)).all()}
            changed = [
                cert_names.get(c, c) for c in new_claims if c in old_claims and old_claims[c] != new_claims[c]
            ]
            out.append(
                FieldDiff(
                    name,
                    label_text,
                    "certs",
                    added=[cert_names.get(c, c) for c in new_claims if c not in old_claims],
                    removed=[cert_names.get(c, c) for c in old_claims if c not in new_claims],
                    new=changed,
                )
            )
        else:
            out.append(FieldDiff(name, label_text, "scalar", old, new))
    return out


# ---------- queries & purge ----------


def owned_tools(db: Session, user: User) -> list[Tool]:
    return list(
        db.scalars(
            select(Tool)
            .where(Tool.owner_id == user.id, Tool.status != ToolStatus.deleted)
            .order_by(Tool.updated_at.desc())
        )
        .unique()
        .all()
    )


def purge_deleted(db: Session) -> int:
    """Hard-deletes tools soft-deleted more than 30 days ago, files included."""
    cutoff = utcnow() - PURGE_AFTER
    tools = (
        db.scalars(select(Tool).where(Tool.status == ToolStatus.deleted, Tool.deleted_at < cutoff))
        .unique()
        .all()
    )
    for tool in tools:
        media.delete_tool_dir(tool.id)
        search.remove_tool(db, tool.id)
        db.delete(tool)
    return len(tools)
