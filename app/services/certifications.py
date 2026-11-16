"""Certification & compliance badges (PRD F20, TECH_SPEC §11).

"Present" is computed at read time from claim state + valid_until (D9): approved and not expired.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import today, utcnow
from app.forms.common import INVALID_URL, REQUIRED, FieldError, clean_url
from app.i18n import N_
from app.models import Certification, Tool, ToolCertification
from app.models.enums import Assurance, ClaimState, PatientData, ToolType

NB_RE = re.compile(r"^\d{4}$")
FORM_PREFIX = "cert_"


@dataclass(frozen=True)
class Badge:
    code: str
    label: str
    name: str
    present: bool
    expired: bool
    is_core: bool
    assurance: str | None
    details: dict[str, Any] | None
    evidence_url: str | None
    valid_until: date | None


def catalogue(db: Session, active_only: bool = True) -> list[Certification]:
    query = select(Certification).order_by(Certification.sort_order, Certification.id)
    if active_only:
        query = query.where(Certification.is_active.is_(True))
    return list(db.scalars(query).all())


def by_code(db: Session) -> dict[str, Certification]:
    return {c.code: c for c in catalogue(db, active_only=False)}


def option_values(field: dict[str, Any]) -> list[str]:
    return [str(o["value"]) if isinstance(o, dict) else str(o) for o in field.get("options", [])]


def option_label(field: dict[str, Any], value: Any, lang: str) -> str:
    for o in field.get("options", []):
        if isinstance(o, dict) and str(o.get("value")) == str(value):
            return str(o.get(f"label_{lang}") or o.get("label_pt") or value)
    return str(value)


def field_label(field: dict[str, Any], lang: str) -> str:
    return str(field.get(f"label_{lang}") or field.get("label_pt") or field["key"])


def is_present(claim: ToolCertification, on: date | None = None) -> bool:
    if claim.state != ClaimState.approved:
        return False
    return claim.valid_until is None or claim.valid_until >= (on or today())


def is_expired(claim: ToolCertification, on: date | None = None) -> bool:
    return (
        claim.state == ClaimState.approved
        and claim.valid_until is not None
        and claim.valid_until < (on or today())
    )


def badge_label(cert: Certification, details: dict[str, Any] | None) -> str:
    if cert.label_template and details:
        try:
            return cert.label_template.format(**details)
        except (KeyError, IndexError, ValueError):
            pass
    return cert.badge_label


def _required(field: dict[str, Any], details: dict[str, Any]) -> bool:
    if field.get("required"):
        return True
    return any(details.get(other) in values for other, values in (field.get("required_if") or {}).items())


def validate_claim(
    cert: Certification, raw: dict[str, str], full: bool
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validates details against `field_schema`. Required checks only when `full` (submission)."""
    clean: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field in cert.field_schema:
        key = field["key"]
        ftype = field.get("type", "text")
        value = (raw.get(key) or "").strip()
        if ftype == "bool":
            clean[key] = value in ("1", "on", "true")
            continue
        if not value:
            continue
        if ftype == "enum":
            if value not in option_values(field):
                errors[key] = N_("Escolha uma opção válida.")
                continue
            clean[key] = value
        elif ftype == "url":
            try:
                clean[key] = clean_url(value)
            except FieldError:
                errors[key] = INVALID_URL
        elif ftype == "date":
            try:
                clean[key] = date.fromisoformat(value).isoformat()
            except ValueError:
                errors[key] = N_("Data inválida (use AAAA-MM-DD).")
        elif ftype == "nb_number":
            if not NB_RE.match(value):
                errors[key] = N_("O número do organismo notificado tem 4 dígitos.")
            else:
                clean[key] = value
        else:
            clean[key] = value[:200]
    if full:
        for field in cert.field_schema:
            key = field["key"]
            if (
                field.get("type") != "bool"
                and key not in errors
                and not clean.get(key)
                and _required(field, clean)
            ):
                errors[key] = REQUIRED
    return clean, errors


def resolve_assurance(cert: Certification, details: dict[str, Any]) -> Assurance:
    for field in cert.field_schema:
        rule = field.get("assurance_if")
        if not rule:
            continue
        for key, mapping in rule.items():
            value = details.get(key)
            if value is None:
                continue
            resolved = mapping.get(value, mapping.get("*"))
            if resolved:
                return Assurance(resolved)
    if cert.assurance_default == Assurance.mixed:
        return Assurance.self_declared
    return cert.assurance_default


def parse_form(form: Any, certs: list[Certification]) -> dict[str, dict[str, str]]:
    """{code: raw details} for each checked item. Unchecked items are ignored even if fields were filled."""
    claims: dict[str, dict[str, str]] = {}
    for cert in certs:
        if form.get(f"{FORM_PREFIX}{cert.code}") not in ("1", "on", "true"):
            continue
        raw: dict[str, str] = {}
        for field in cert.field_schema:
            value = form.get(f"{FORM_PREFIX}{cert.code}__{field['key']}")
            raw[field["key"]] = value if isinstance(value, str) else ""
        claims[cert.code] = raw
    return claims


@dataclass
class ClaimCheck:
    claims: dict[str, dict[str, Any]]
    errors: dict[str, str]  # form field name -> msgid
    warnings: list[str]


def check_claims(
    certs: dict[str, Certification],
    raw_claims: dict[str, dict[str, str]],
    tool_type: str | None,
    category_slugs: list[str],
    patient_data: str | None,
    full: bool,
) -> ClaimCheck:
    """Field validation + coherence rules (TECH_SPEC §11.2)."""
    raw_claims = {k: dict(v) for k, v in raw_claims.items() if k in certs and certs[k].is_active}
    errors: dict[str, str] = {}
    warnings: list[str] = []

    # MDR / IVDR imply CE with the matching legal basis.
    for implied, basis in (("mdr", "MDR"), ("ivdr", "IVDR")):
        if implied in raw_claims and "ce" in certs and certs["ce"].is_active:
            ce = raw_claims.setdefault("ce", {})
            if ce.get("legal_basis") not in (basis, "MDR", "IVDR"):
                ce["legal_basis"] = basis

    clean_claims: dict[str, dict[str, Any]] = {}
    for code, raw in raw_claims.items():
        clean, field_errors = validate_claim(certs[code], raw, full)
        clean_claims[code] = clean
        for key, msg in field_errors.items():
            errors[f"{FORM_PREFIX}{code}__{key}"] = msg

    if patient_data == PatientData.server.value and "rgpd" not in clean_claims:
        warnings.append(
            N_(
                "A ferramenta envia dados para um servidor mas não tem declaração RGPD. O moderador pode pedir alterações."
            )
        )
    is_ai = tool_type == ToolType.ai_prompt.value or "inteligencia-artificial" in category_slugs
    ai_act_available = "ai_act" in certs and certs["ai_act"].is_active
    if is_ai and ai_act_available and "ai_act" not in clean_claims:
        warnings.append(
            N_("Ferramenta de IA: considere declarar a conformidade com o Regulamento da IA (AI Act).")
        )
    return ClaimCheck(clean_claims, errors, warnings)


def _mirror(claim: ToolCertification, cert: Certification, details: dict[str, Any]) -> None:
    claim.details = details
    claim.assurance = resolve_assurance(cert, details)
    claim.evidence_url = details.get("evidence_url")
    claim.valid_until = date.fromisoformat(details["valid_until"]) if details.get("valid_until") else None
    claim.updated_at = utcnow()


def save_draft_claims(
    db: Session, tool: Tool, claims: dict[str, dict[str, Any]], certs: dict[str, Certification]
) -> None:
    """Drafts / rejected tools: claims are stored directly as `pending`."""
    existing = {c.certification.code: c for c in tool.claims}
    for code, row in existing.items():
        if code not in claims:
            tool.claims.remove(row)
            db.delete(row)
    for code, details in claims.items():
        cert = certs[code]
        found = existing.get(code)
        if found is None:
            row = ToolCertification(
                certification_id=cert.id, state=ClaimState.pending, assurance=Assurance.self_declared
            )
            row.certification = cert
            tool.claims.append(row)
        else:
            row = found
            if row.details != details:
                row.state = ClaimState.pending
                row.review_reason = None
        _mirror(row, cert, details)


def snapshot(tool: Tool) -> list[dict[str, Any]]:
    """Claims as stored in a revision: the declared set, whatever its moderation state."""
    return sorted(
        ({"code": c.certification.code, "details": c.details} for c in tool.claims),
        key=lambda item: item["code"],
    )


def remove_claims_now(db: Session, tool: Tool, keep_codes: set[str]) -> list[str]:
    """Published tools: removals apply immediately (they only make the listing more conservative)."""
    removed = []
    for row in list(tool.claims):
        if row.certification.code not in keep_codes:
            removed.append(row.certification.code)
            tool.claims.remove(row)
            db.delete(row)
    return removed


def approve_new_tool_claims(tool: Tool, actor_id: int, rejections: dict[str, str]) -> list[tuple[str, str]]:
    """On approval of a new submission: every pending claim is approved unless individually rejected."""
    rejected = []
    now = utcnow()
    for row in tool.claims:
        if row.state != ClaimState.pending:
            continue
        code = row.certification.code
        if code in rejections:
            row.state = ClaimState.rejected
            row.review_reason = rejections[code]
            rejected.append((code, rejections[code]))
        else:
            row.state = ClaimState.approved
            row.review_reason = None
        row.reviewed_by = actor_id
        row.reviewed_at = now
    return rejected


def changed_claims(tool: Tool, proposed: list[dict[str, Any]]) -> list[str]:
    """Codes whose details are new or differ from the live, approved row (need moderator review)."""
    live = {c.certification.code: c for c in tool.claims}
    out = []
    for item in proposed:
        row = live.get(item["code"])
        if row is None or row.details != item["details"] or row.state != ClaimState.approved:
            out.append(item["code"])
    return out


def apply_revision_claims(
    db: Session,
    tool: Tool,
    proposed: list[dict[str, Any]],
    certs: dict[str, Certification],
    actor_id: int,
    rejections: dict[str, str],
) -> list[tuple[str, str]]:
    rejected = []
    now = utcnow()
    live = {c.certification.code: c for c in tool.claims}
    wanted = {item["code"] for item in proposed}
    remove_claims_now(db, tool, wanted)
    for item in proposed:
        code, details = item["code"], item["details"]
        cert = certs.get(code)
        if cert is None:
            continue
        row = live.get(code)
        unchanged = row is not None and row.details == details and row.state == ClaimState.approved
        if unchanged:
            continue
        if code in rejections:
            rejected.append((code, rejections[code]))
            if row is not None and row.state == ClaimState.approved:
                continue  # keep the previously approved claim; the change is not applied
            if row is None:
                row = ToolCertification(certification_id=cert.id, assurance=Assurance.self_declared)
                row.certification = cert
                tool.claims.append(row)
            _mirror(row, cert, details)
            row.state = ClaimState.rejected
            row.review_reason = rejections[code]
        else:
            if row is None:
                row = ToolCertification(certification_id=cert.id, assurance=Assurance.self_declared)
                row.certification = cert
                tool.claims.append(row)
            _mirror(row, cert, details)
            row.state = ClaimState.approved
            row.review_reason = None
        row.reviewed_by = actor_id
        row.reviewed_at = now
    return rejected


def badges_for(db: Session, tool_ids: list[int], lang: str, on: date | None = None) -> dict[int, list[Badge]]:
    """One query. Per tool: every active core item (present or absent) then present additional items."""
    on = on or today()
    certs = catalogue(db)
    out: dict[int, list[Badge]] = {tid: [] for tid in tool_ids}
    if not tool_ids:
        return out
    rows = db.scalars(
        select(ToolCertification).where(
            ToolCertification.tool_id.in_(tool_ids), ToolCertification.state == ClaimState.approved
        )
    ).all()
    by_tool: dict[int, dict[int, ToolCertification]] = {}
    for row in rows:
        by_tool.setdefault(row.tool_id, {})[row.certification_id] = row
    for tid in tool_ids:
        claims = by_tool.get(tid, {})
        for cert in certs:
            claim = claims.get(cert.id)
            present = claim is not None and is_present(claim, on)
            if not cert.is_core and not present:
                continue
            out[tid].append(
                Badge(
                    code=cert.code,
                    label=badge_label(cert, claim.details if present and claim else None),
                    name=cert.name(lang),
                    present=present,
                    expired=claim is not None and is_expired(claim, on),
                    is_core=cert.is_core,
                    assurance=claim.assurance.value if present and claim else None,
                    details=claim.details if present and claim else None,
                    evidence_url=claim.evidence_url if present and claim else None,
                    valid_until=claim.valid_until if claim else None,
                )
            )
    return out


def detail_rows(cert: Certification, details: dict[str, Any], lang: str) -> list[tuple[str, str, str]]:
    """[(label, display value, type)] for the tool-page panel and moderator screens."""
    rows = []
    for field in cert.field_schema:
        value = details.get(field["key"])
        if value in (None, "", False):
            continue
        ftype = field.get("type", "text")
        if ftype == "enum":
            shown = option_label(field, value, lang)
        elif ftype == "bool":
            shown = "✓"
        else:
            shown = str(value)
        rows.append((field_label(field, lang), shown, ftype))
    return rows


def seed(db: Session, items: list[dict[str, Any]]) -> int:
    count = 0
    for item in items:
        cert = db.scalar(select(Certification).where(Certification.code == item["code"]))
        if cert is None:
            cert = Certification(code=item["code"])
            db.add(cert)
        cert.badge_label = item["badge_label"]
        cert.label_template = item.get("label_template")
        cert.name_pt = item["name_pt"]
        cert.name_en = item["name_en"]
        cert.help_pt = item.get("help_pt")
        cert.help_en = item.get("help_en")
        cert.assurance_default = Assurance(item.get("assurance_default", "self_declared"))
        cert.field_schema = item.get("field_schema", [])
        cert.is_core = bool(item.get("is_core", False))
        cert.is_active = bool(item.get("is_active", True))
        cert.sort_order = int(item.get("sort_order", 0))
        count += 1
    return count
