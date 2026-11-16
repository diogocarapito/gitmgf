"""GitHub repository sync (PRD F14, TECH_SPEC §10). Failures never break a tool page."""

import logging
import re
import time
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import ToolGithub

log = logging.getLogger("gitmgf.github")
REPO_RE = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
API = "https://api.github.com/repos/{owner}/{repo}"


def parse_repo_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    match = REPO_RE.match(url.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def client() -> httpx.Client:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gitmgf-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_settings().github_api_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(timeout=10.0, headers=headers)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def sync_one(row: ToolGithub, http: httpx.Client) -> str:
    """Updates one row in place. Returns "updated", "not_modified" or an error code."""
    headers = {"If-None-Match": row.etag} if row.etag else {}
    try:
        resp = http.get(API.format(owner=row.owner, repo=row.repo), headers=headers)
    except httpx.HTTPError as exc:
        row.last_error = f"network:{type(exc).__name__}"[:200]
        return "error"
    row.fetched_at = utcnow()
    if resp.status_code == 304:
        row.last_error = None
        return "not_modified"
    if resp.status_code == 404:
        row.last_error = "not_found"
        return "not_found"
    if resp.status_code != 200:
        row.last_error = f"http_{resp.status_code}"
        return "error"
    data = resp.json()
    row.stars = int(data.get("stargazers_count") or 0)
    row.forks = int(data.get("forks_count") or 0)
    row.open_issues = int(data.get("open_issues_count") or 0)
    row.pushed_at = _parse_dt(data.get("pushed_at"))
    row.license_spdx = ((data.get("license") or {}).get("spdx_id") or None) if data.get("license") else None
    row.archived = bool(data.get("archived"))
    row.default_branch = data.get("default_branch")
    row.etag = resp.headers.get("etag")
    row.last_error = None
    return "updated"


def sync_all(db: Session, tool_id: int | None = None, delay: float = 1.0) -> dict[str, int]:
    """Nightly job: 1 request per second; commits after each repo (no transaction held during I/O)."""
    query = select(ToolGithub)
    if tool_id is not None:
        query = query.where(ToolGithub.tool_id == tool_id)
    ids = [r.tool_id for r in db.scalars(query).all()]
    counts: dict[str, int] = {}
    with client() as http:
        for i, tid in enumerate(ids):
            row = db.get(ToolGithub, tid)
            if row is None:
                continue
            db.commit()  # release the read transaction before network I/O
            outcome = sync_one(row, http)
            db.commit()
            counts[outcome] = counts.get(outcome, 0) + 1
            if delay and i < len(ids) - 1:
                time.sleep(delay)
    return counts
