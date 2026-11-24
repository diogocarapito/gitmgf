"""Account restrictions set by moderators (D41): no publishing (tools and colab posts) or no social
(comments and reactions). Each has a reason, is audited and emailed to the person as a statement of reasons."""

from typing import Literal

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import User
from app.services import audit, email, permissions

Kind = Literal["publish", "social"]
KINDS: tuple[Kind, ...] = ("publish", "social")


class RestrictionError(Exception):
    pass


def is_restricted(user: User, kind: Kind) -> bool:
    return getattr(user, f"{kind}_blocked_at") is not None


def restrict(db: Session, actor: User, target: User, kind: Kind, reason: str) -> None:
    if kind not in KINDS or not permissions.can_restrict(actor, target):
        raise RestrictionError("not allowed")
    setattr(target, f"{kind}_blocked_at", utcnow())
    setattr(target, f"{kind}_blocked_reason", reason.strip())
    audit.log(db, actor.id, f"user.restrict_{kind}", "user", target.id, reason=reason.strip())
    _tell(db, target, kind, lifted=False, reason=reason.strip())


def lift(db: Session, actor: User, target: User, kind: Kind) -> None:
    if kind not in KINDS or not permissions.can_restrict(actor, target) or not is_restricted(target, kind):
        raise RestrictionError("not allowed")
    setattr(target, f"{kind}_blocked_at", None)
    setattr(target, f"{kind}_blocked_reason", None)
    audit.log(db, actor.id, f"user.lift_{kind}", "user", target.id)
    _tell(db, target, kind, lifted=True, reason="")


def _tell(db: Session, target: User, kind: Kind, lifted: bool, reason: str) -> None:
    if not target.is_active:
        return
    email.enqueue(
        db,
        target.email,
        "account_restricted",
        {"name": target.display_name, "kind": kind, "lifted": lifted, "reason": reason},
        target.locale.value,
    )
