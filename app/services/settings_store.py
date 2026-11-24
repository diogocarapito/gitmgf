"""Admin-tunable site settings (TECH_SPEC §5.3 site_settings), cached in-process for 60 s."""

import os
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import SiteSetting
from app.services import audit

DEFAULTS: dict[str, Any] = {
    "score.w_search_click": 3.0,
    "score.w_outbound_click": 2.0,
    "score.w_star": 4.0,
    "score.w_github": 5.0,
    "score.half_life_days": 30.0,
    "search.beta_popularity": 1.0,
    "limits.max_pending_per_user": 3,
    "reports.auto_hide_threshold": 3,
    "site.registration_open": True,  # needs SMTP; False or no SMTP = invite-only (D26, D30)
    "site.banner_pt": "",
    "site.banner_en": "",
    "terms.current_version": "2026-11",
    "email.disabled": [],  # email types switched off by an admin (D42)
}

# Legal placeholders (content/legal/NOTES.md). Stored as `legal.<KEY>`; env `LEGAL_<KEY>` is the fallback,
# so a first production deploy can be configured before any admin exists.
LEGAL_KEYS = (
    "CONTROLLER_NAME",
    "CONTROLLER_TAX_ID",
    "CONTROLLER_ADDRESS",
    "PRIVACY_EMAIL",
    "CONTACT_EMAIL",
    "SECURITY_EMAIL",
    "DPO_STATEMENT",
    "DPO_STATEMENT_EN",
    "HOSTING_PROVIDER",
    "HOSTING_LOCATION",
    "EMAIL_PROVIDER",
    "EMAIL_PROVIDER_LOCATION",
    "BACKUP_PROVIDER",
    "BACKUP_LOCATION",
    "SITE_CODE_LICENSE_STATEMENT",
    "SITE_CODE_LICENSE_STATEMENT_EN",
    "COURT_DISTRICT",
    "ADR_STATEMENT",
    "ADR_STATEMENT_EN",
)
# Placeholders that may legitimately resolve to an empty string.
LEGAL_OPTIONAL = {
    "SITE_CODE_LICENSE_STATEMENT",
    "SITE_CODE_LICENSE_STATEMENT_EN",
    "ADR_STATEMENT",
    "ADR_STATEMENT_EN",
}

TTL_SECONDS = 60.0
_cache: dict[str, Any] = {}
_loaded_at = 0.0


def invalidate() -> None:
    global _loaded_at
    _cache.clear()
    _loaded_at = 0.0


def _load(db: Session) -> dict[str, Any]:
    global _loaded_at
    if not _loaded_at or time.monotonic() - _loaded_at > TTL_SECONDS:
        try:
            rows = db.execute(select(SiteSetting.key, SiteSetting.value)).all()
        except OperationalError:
            db.rollback()
            return {}  # not migrated yet (first deploy): defaults and env values apply
        _cache.clear()
        _cache.update({k: v for k, v in rows})
        _loaded_at = time.monotonic()
    return _cache


def get(db: Session, key: str) -> Any:
    stored = _load(db)
    if key in stored:
        return stored[key]
    if key.startswith("legal."):
        return os.environ.get("LEGAL_" + key.removeprefix("legal."))
    return DEFAULTS.get(key)


def get_float(db: Session, key: str) -> float:
    return float(get(db, key))


def get_int(db: Session, key: str) -> int:
    return int(get(db, key))


def set_value(db: Session, key: str, value: Any, actor_id: int | None) -> None:
    row = db.get(SiteSetting, key)
    old = row.value if row else get(db, key)
    if row is None:
        db.add(SiteSetting(key=key, value=value, updated_by=actor_id))
    else:
        row.value = value
        row.updated_at = utcnow()
        row.updated_by = actor_id
    if key != "tracking.daily_salt":
        audit.log(db, actor_id, "settings.change", "setting", None, key=key, old=old, new=value)
    invalidate()


def legal_values(db: Session) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in LEGAL_KEYS:
        value = get(db, f"legal.{key}")
        if value is not None:
            values[key] = str(value)
    values["AUTO_HIDE_THRESHOLD"] = str(get_int(db, "reports.auto_hide_threshold"))
    return values
