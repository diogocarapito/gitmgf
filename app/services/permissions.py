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


def can_suggest(user: User | None, tool: Tool) -> bool:
    """Signed-in, active users may send suggestions to the author of a public tool that isn't theirs."""
    return user is not None and user.is_active and tool.is_public and not is_owner(user, tool)


def can_view_profile(profile: User) -> bool:
    """Profiles of active, onboarded accounts are public; suspended or deleted ones are hidden (404)."""
    return (
        profile.is_active
        and profile.deleted_at is None
        and profile.handle is not None
        and profile.onboarded_at is not None
    )


def can_view_stats(user: User | None) -> bool:
    return is_moderator(user)
