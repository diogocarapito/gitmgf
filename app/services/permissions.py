"""Pure permission checks (PRD roles matrix, TECH_SPEC §6.5). Hidden resources must 404, not 403."""

from app.models import Colab, Comment, Report, Tool, User
from app.models.enums import ColabStatus, Role, ToolStatus


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


def counts_towards_usage(user: User | None, tool: Tool) -> bool:
    """Whether a visit or click feeds the popularity score (D40).

    Owners never count on their own tools, and moderators/admins never count on any tool:
    they open listings while testing and reviewing, which isn't real use.
    """
    if user is None:
        return True
    return not is_owner(user, tool) and user.role not in (Role.moderator, Role.admin)


def can_view_stats(user: User | None) -> bool:
    return is_moderator(user)


# ---------- community (D41): colab posts and comments ----------


def _active(user: User | None) -> bool:
    return user is not None and user.is_active and user.deleted_at is None


def _social(user: User | None) -> bool:
    """Active and not blocked from comments and reactions by a moderator."""
    return _active(user) and user is not None and user.social_blocked_at is None


def can_publish(user: User | None) -> bool:
    """New tools and colab posts; a moderator can block this per account (D41)."""
    return _active(user) and user is not None and user.publish_blocked_at is None


def can_view_colab(user: User | None, colab: Colab) -> bool:
    if colab.status == ColabStatus.deleted:
        return False
    if colab.is_public:
        return True
    return user is not None and (user.id == colab.author_id or is_moderator(user))


def can_post_colab(user: User | None) -> bool:
    return can_publish(user)


def can_edit_colab(user: User | None, colab: Colab) -> bool:
    return _active(user) and user is not None and user.id == colab.author_id and colab.is_public


def can_moderate_colab(user: User | None, colab: Colab) -> bool:
    return is_moderator(user) and user is not None and user.id != colab.author_id


def can_comment_on_tool(user: User | None, tool: Tool) -> bool:
    """Archived tools keep their comments read-only."""
    return _social(user) and tool.status == ToolStatus.published


def can_comment_on_colab(user: User | None, colab: Colab) -> bool:
    return _social(user) and colab.is_public


def comment_target_owner_id(comment: Comment) -> int | None:
    if comment.tool is not None:
        return comment.tool.owner_id
    if comment.colab is not None:
        return comment.colab.author_id
    return None


def can_edit_comment(user: User | None, comment: Comment) -> bool:
    return (
        _active(user)
        and user is not None
        and comment.author_id == user.id
        and comment.deleted_at is None
        and comment.hidden_at is None
    )


def can_delete_comment(user: User | None, comment: Comment) -> bool:
    """Only the author deletes; the tool owner reports like anyone else (no silencing critics)."""
    return user is not None and comment.author_id == user.id and comment.deleted_at is None


def can_moderate_comment(user: User | None, comment: Comment) -> bool:
    """Moderators, but not on their own comments nor on comments under their own tool or colab."""
    return (
        is_moderator(user)
        and user is not None
        and user.id != comment.author_id
        and user.id != comment_target_owner_id(comment)
    )


def can_react(user: User | None, comment: Comment) -> bool:
    return _social(user) and comment.is_visible


def can_handle_report(user: User | None, report: Report) -> bool:
    if report.tool is not None:
        return can_moderate(user, report.tool)
    if report.comment is not None:
        return can_moderate_comment(user, report.comment)
    if report.colab is not None:
        return can_moderate_colab(user, report.colab)
    return is_moderator(user)
