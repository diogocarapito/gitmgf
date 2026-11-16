"""Pure permission checks (PRD roles matrix, TECH_SPEC §6.5). Hidden resources must 404, not 403."""

from app.models import Tool, User
from app.models.enums import Role, ToolStatus


def is_owner(user: User | None, tool: Tool) -> bool:
    return user is not None and user.id == tool.owner_id


def is_moderator(user: User | None) -> bool:
    return user is not None and user.is_active and user.role in (Role.moderator, Role.admin)


def can_view_tool(user: User | None, tool: Tool) -> bool:
    if tool.status in (ToolStatus.published, ToolStatus.archived):
        return True
    if tool.status == ToolStatus.deleted:
        return False
    return is_owner(user, tool) or is_moderator(user)


def can_edit_tool(user: User | None, tool: Tool) -> bool:
    if user is None or not user.is_active or tool.status == ToolStatus.deleted:
        return False
    return is_owner(user, tool) or user.role == Role.admin


def can_moderate(user: User | None, tool: Tool) -> bool:
    return is_moderator(user) and not is_owner(user, tool)


def can_admin(user: User | None) -> bool:
    return user is not None and user.is_active and user.role == Role.admin


def can_star(user: User | None, tool: Tool) -> bool:
    return (
        user is not None
        and user.is_active
        and not is_owner(user, tool)
        and tool.status == ToolStatus.published
    )


def can_view_stats(user: User | None) -> bool:
    return is_moderator(user)
