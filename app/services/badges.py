"""Derived listing badges (PRD F3): Open source, Free, Maintained, Archived, New."""

from datetime import timedelta

from app.db import utcnow
from app.i18n import N_
from app.models import Tool
from app.models.enums import Pricing, ToolStatus

NEW_FOR = timedelta(days=30)
MAINTAINED_WITHIN = timedelta(days=365)


def derived_badges(tool: Tool) -> list[tuple[str, str]]:
    """[(css kind, msgid)] in display order."""
    now = utcnow()
    out: list[tuple[str, str]] = []
    if tool.is_open_source:
        out.append(("oss", N_("Open source")))
    if tool.pricing == Pricing.free:
        out.append(("free", N_("Gratuita")))
    if tool.published_at and now - tool.published_at < NEW_FOR:
        out.append(("new", N_("Nova")))
    gh = tool.github
    if tool.status == ToolStatus.archived or (gh is not None and gh.archived):
        out.append(("archived", N_("Arquivada")))
    elif gh is not None and gh.pushed_at and now - gh.pushed_at < MAINTAINED_WITHIN:
        out.append(("maintained", N_("Mantida")))
    return out
