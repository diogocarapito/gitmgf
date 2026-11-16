from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def log(
    db: Session,
    actor_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    **details: Any,
) -> AuditLog:
    """Append an audit entry (actor None = system). Never log raw emails, IPs or tokens here."""
    entry = AuditLog(
        actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, details=details
    )
    db.add(entry)
    return entry
