"""Test data builders."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Tool, User
from app.models.enums import Role
from app.services import tools as tool_service
from tests.conftest import make_user


def category_ids(db: Session, *slugs: str) -> list[int]:
    return list(db.scalars(select(Category.id).where(Category.slug.in_(slugs))).all())


def tool_form(db: Session, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title_pt": "Calculadora SCORE2",
        "summary_pt": "Risco cardiovascular a 10 anos segundo as tabelas europeias.",
        "description_pt": "Calcula o **risco** cardiovascular (SCORE2 e SCORE2-OP).",
        "tool_type": "calculator",
        "category_ids": [str(i) for i in category_ids(db, "calculadoras-scores", "cardiologia")],
        "tags": "score2, risco cardiovascular",
        "care_setting": "primary",
        "platforms": ["web"],
        "tool_languages": ["pt"],
        "website_url": "https://example.org/score2",
        "repo_url": "https://github.com/example/score2",
        "license_spdx": "MIT",
        "pricing": "free",
        "patient_data": "none",
        "intended_use": "Médicos de família, para estimar o risco em consulta.",
        "decl_author": "1",
        "decl_no_patient_data": "1",
        "decl_no_validation": "1",
    }
    data.update(overrides)
    return data


def tool_data(db: Session, **overrides: Any) -> dict[str, Any]:
    form = tool_form(db, **overrides)
    from app.forms.tool import ToolForm

    raw = {k: v for k, v in form.items() if not k.startswith("decl_")}
    raw["category_ids"] = [int(i) for i in raw["category_ids"]]
    return ToolForm.model_validate(raw).tool_data()


def make_tool(
    db: Session,
    owner: User | None = None,
    status: str = "published",
    claims: dict[str, dict[str, Any]] | None = None,
    moderator: User | None = None,
    **overrides: Any,
) -> Tool:
    from app.db import utcnow

    owner = owner or make_user(db, f"owner{db.query(User).count()}@example.org")
    tool = tool_service.create_tool(db, owner, tool_data(db, **overrides), claims or {})
    tool.declarations_accepted_at = utcnow()
    db.commit()
    if status in ("pending", "published", "rejected", "hidden", "archived"):
        tool_service.transition(db, tool, "submit", owner)
    if status in ("published", "hidden", "archived"):
        mod = (
            moderator
            or db.scalar(select(User).where(User.role == Role.moderator))
            or make_user(db, "mod-factory@example.org", Role.moderator)
        )
        tool_service.transition(db, tool, "approve", mod)
        if status == "hidden":
            tool_service.transition(db, tool, "hide", mod, reason="x")
        if status == "archived":
            tool_service.transition(db, tool, "archive", owner)
    if status == "rejected":
        mod = moderator or make_user(db, "mod-factory@example.org", Role.moderator)
        tool_service.transition(db, tool, "reject", mod, reason="Informação incompleta.")
    db.commit()
    return tool
