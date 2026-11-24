"""Comments on tools and colab posts, with one level of replies, @mentions and emoji reactions (D41).

Published immediately and reportable. Authors edit and delete their own comments; a deleted comment that
has replies stays as a tombstone so the thread still reads. Moderators hide with a reason (audited, the
author is notified); never their own comments or comments under their own tool or colab.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from html import escape

from markupsafe import Markup
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.i18n import labels, lang_path
from app.models import Colab, Comment, CommentReaction, Tool, User
from app.models.enums import NotificationKind, Reaction, UserStatus
from app.services import audit, notifications, permissions

MIN_LENGTH = 2
MAX_LENGTH = 2000
MAX_MENTIONS = 10
EMOJI = {Reaction(k): v for k, v in labels.REACTION_EMOJI.items()}
MENTION_RE = re.compile(r"(?<![\w@/.-])@([a-z0-9][a-z0-9-]{2,29})\b", re.I)
URL_RE = re.compile(r"\bhttps?://[^\s<>\"']+[^\s<>\"'.,;:!?)\]]")
USER_LINK_REL = "nofollow ugc noopener noreferrer"


class CommentError(Exception):
    pass


@dataclass
class ReactionCount:
    emoji: Reaction
    count: int
    mine: bool

    @property
    def char(self) -> str:
        return EMOJI[self.emoji]


@dataclass
class Node:
    comment: Comment
    replies: list["Node"] = field(default_factory=list)
    show_body: bool = True  # False → tombstone ("deleted" or "hidden by moderation")


@dataclass
class Thread:
    nodes: list[Node]
    count: int  # visible comments, for the heading
    bodies: dict[int, Markup]
    reactions: dict[int, list[ReactionCount]]


# ---------- reading ----------


def _target_filter(tool: Tool | None, colab: Colab | None):  # type: ignore[no-untyped-def]
    if tool is not None:
        return Comment.tool_id == tool.id
    assert colab is not None
    return Comment.colab_id == colab.id


def thread(
    db: Session, viewer: User | None, tool: Tool | None = None, colab: Colab | None = None, lang: str = "pt"
) -> Thread:
    """Top-level comments newest first, replies oldest first. Hidden comments are shown to the author and
    to moderators; otherwise hidden or deleted ones appear only as tombstones when they have replies."""
    rows = list(
        db.scalars(
            select(Comment).where(_target_filter(tool, colab)).order_by(Comment.created_at, Comment.id)
        )
        .unique()
        .all()
    )
    sees_hidden = permissions.is_moderator(viewer)

    def can_see(c: Comment) -> bool:
        if c.deleted_at is not None:
            return False
        if c.hidden_at is None:
            return True
        return sees_hidden or (viewer is not None and c.author_id == viewer.id)

    by_parent: dict[int, list[Comment]] = {}
    for c in rows:
        if c.parent_id is not None:
            by_parent.setdefault(c.parent_id, []).append(c)
    nodes: list[Node] = []
    count = 0
    for c in rows:
        if c.parent_id is not None:
            continue
        replies = [Node(r) for r in by_parent.get(c.id, []) if can_see(r)]
        count += sum(1 for r in replies if r.comment.is_visible)
        if can_see(c):
            count += 1 if c.is_visible else 0
            nodes.append(Node(c, replies))
        elif replies:
            nodes.append(Node(c, replies, show_body=False))
    nodes.reverse()
    shown = [n.comment for n in nodes if n.show_body] + [r.comment for n in nodes for r in n.replies]
    return Thread(
        nodes=nodes,
        count=count,
        bodies=render_bodies(db, shown, lang),
        reactions=reactions_for(db, [c.id for c in shown], viewer),
    )


def count_for_tools(db: Session, tool_ids: list[int]) -> dict[int, int]:
    return _counts(db, Comment.tool_id, tool_ids)


def count_for_colabs(db: Session, colab_ids: list[int]) -> dict[int, int]:
    return _counts(db, Comment.colab_id, colab_ids)


def _counts(db: Session, column, ids: list[int]) -> dict[int, int]:  # type: ignore[no-untyped-def]
    if not ids:
        return {}
    rows = db.execute(
        select(column, func.count())
        .where(column.in_(ids), Comment.deleted_at.is_(None), Comment.hidden_at.is_(None))
        .group_by(column)
    ).all()
    return {int(k): int(n) for k, n in rows}


def reactions_for(db: Session, comment_ids: list[int], viewer: User | None) -> dict[int, list[ReactionCount]]:
    if not comment_ids:
        return {}
    rows = db.execute(
        select(CommentReaction.comment_id, CommentReaction.emoji, CommentReaction.user_id).where(
            CommentReaction.comment_id.in_(comment_ids)
        )
    ).all()
    counts: Counter[tuple[int, Reaction]] = Counter()
    mine: set[tuple[int, Reaction]] = set()
    for comment_id, emoji, user_id in rows:
        counts[(comment_id, emoji)] += 1
        if viewer is not None and user_id == viewer.id:
            mine.add((comment_id, emoji))
    out: dict[int, list[ReactionCount]] = {}
    for comment_id in comment_ids:
        out[comment_id] = [
            ReactionCount(e, counts[(comment_id, e)], (comment_id, e) in mine)
            for e in EMOJI
            if counts[(comment_id, e)]
        ]
    return out


# ---------- rendering: plain text, clickable links and @mentions ----------


def mentioned_handles(text: str) -> list[str]:
    seen: list[str] = []
    for match in MENTION_RE.finditer(text or ""):
        handle = match.group(1).lower()
        if handle not in seen:
            seen.append(handle)
    return seen[:MAX_MENTIONS]


def _profiles(db: Session, handles: set[str]) -> dict[str, User]:
    if not handles:
        return {}
    users = db.scalars(select(User).where(User.handle.in_(handles))).unique().all()
    return {u.handle: u for u in users if u.handle and permissions.can_view_profile(u)}


def render_text(text: str, profiles: dict[str, User], lang: str = "pt") -> Markup:
    """Escaped plain text → paragraphs with links (nofollow ugc) and @mentions of real profiles."""

    def inline(chunk: str) -> str:
        out, pos = [], 0
        for match in URL_RE.finditer(chunk):
            out.append(_mentions(chunk[pos : match.start()], profiles, lang))
            href = escape(match.group(0))
            out.append(f'<a href="{href}" rel="{USER_LINK_REL}">{href}</a>')
            pos = match.end()
        out.append(_mentions(chunk[pos:], profiles, lang))
        return "".join(out)

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    html = "".join("<p>" + inline(p).replace("\n", "<br>") + "</p>" for p in paragraphs)
    return Markup(html)  # noqa: S704 - every piece is escaped above


def _mentions(chunk: str, profiles: dict[str, User], lang: str) -> str:
    out, pos = [], 0
    for match in MENTION_RE.finditer(chunk):
        person = profiles.get(match.group(1).lower())
        if person is None:
            continue
        out.append(escape(chunk[pos : match.start()]))
        href = lang_path(lang, f"/u/{person.handle}")
        out.append(f'<a class="mention" href="{escape(href)}">@{escape(person.handle or "")}</a>')
        pos = match.end()
    out.append(escape(chunk[pos:]))
    return "".join(out)


def render_bodies(db: Session, comments: list[Comment], lang: str = "pt") -> dict[int, Markup]:
    handles: set[str] = set()
    for c in comments:
        handles.update(mentioned_handles(c.body))
    profiles = _profiles(db, handles)
    return {c.id: render_text(c.body, profiles, lang) for c in comments}


def render_bodies_text(db: Session, text: str, lang: str = "pt") -> Markup:
    """A colab post body, rendered like a comment."""
    return render_text(text, _profiles(db, set(mentioned_handles(text))), lang)


# ---------- writing ----------


def _clean(body: str) -> str:
    text = (body or "").replace("\r\n", "\n").strip()
    if len(text) < MIN_LENGTH or len(text) > MAX_LENGTH:
        raise CommentError("length")
    return text


def post(
    db: Session,
    author: User,
    body: str,
    tool: Tool | None = None,
    colab: Colab | None = None,
    parent: Comment | None = None,
) -> Comment:
    if tool is not None and not permissions.can_comment_on_tool(author, tool):
        raise CommentError("not allowed")
    if colab is not None and not permissions.can_comment_on_colab(author, colab):
        raise CommentError("not allowed")
    if (tool is None) == (colab is None):
        raise CommentError("one target")
    text = _clean(body)
    if parent is not None:
        same_target = (tool is not None and parent.tool_id == tool.id) or (
            colab is not None and parent.colab_id == colab.id
        )
        if not same_target:
            raise CommentError("parent elsewhere")
        if parent.parent_id is not None:  # one level: a reply to a reply joins the same thread
            parent = db.get(Comment, parent.parent_id)
            assert parent is not None
    comment = Comment(
        tool_id=tool.id if tool else None,
        colab_id=colab.id if colab else None,
        parent_id=parent.id if parent else None,
        author_id=author.id,
        body=text,
    )
    db.add(comment)
    db.flush()
    db.refresh(comment)
    _notify_new(db, comment, author, parent)
    return comment


def edit(db: Session, user: User, comment: Comment, body: str) -> None:
    if not permissions.can_edit_comment(user, comment):
        raise CommentError("not allowed")
    text = _clean(body)
    if text != comment.body:
        comment.body = text
        comment.edited_at = utcnow()


def has_replies(db: Session, comment: Comment) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Comment).where(Comment.parent_id == comment.id)))


def remove(db: Session, comment: Comment) -> None:
    """Hard delete, or a tombstone (no text, no author) while other people's replies hang from it."""
    if comment.parent_id is None and has_replies(db, comment):
        comment.body = ""
        comment.author_id = None
        comment.deleted_at = utcnow()
        db.execute(delete(CommentReaction).where(CommentReaction.comment_id == comment.id))
    else:
        db.delete(comment)


def delete_own(db: Session, user: User, comment: Comment) -> None:
    if not permissions.can_delete_comment(user, comment):
        raise CommentError("not allowed")
    remove(db, comment)


def hide(db: Session, moderator: User, comment: Comment, reason: str) -> None:
    if not permissions.can_moderate_comment(moderator, comment) or comment.deleted_at is not None:
        raise CommentError("not allowed")
    if comment.hidden_at is not None:
        return
    comment.hidden_at = utcnow()
    comment.hidden_by = moderator.id
    comment.hidden_reason = reason.strip()
    audit.log(db, moderator.id, "comment.hide", "comment", comment.id, reason=comment.hidden_reason)
    if comment.author is not None:
        notifications.notify_moderation(db, comment.author, comment=comment, hidden=True, reason=reason)


def unhide(db: Session, moderator: User, comment: Comment) -> None:
    if not permissions.can_moderate_comment(moderator, comment) or comment.hidden_at is None:
        raise CommentError("not allowed")
    comment.hidden_at = None
    comment.hidden_by = None
    comment.hidden_reason = None
    audit.log(db, moderator.id, "comment.unhide", "comment", comment.id)
    if comment.author is not None:
        notifications.notify_moderation(db, comment.author, comment=comment, hidden=False)


def toggle_reaction(db: Session, user: User, comment: Comment, emoji: Reaction) -> bool:
    """Returns True if the reaction is now on."""
    if not permissions.can_react(user, comment):
        raise CommentError("not allowed")
    existing = db.get(CommentReaction, (comment.id, user.id, emoji))
    if existing is not None:
        db.delete(existing)
        return False
    db.add(CommentReaction(comment_id=comment.id, user_id=user.id, emoji=emoji))
    return True


# ---------- notifications ----------


def _can_be_told(user: User | None) -> bool:
    return user is not None and user.status == UserStatus.active and user.deleted_at is None


def _notify_new(db: Session, comment: Comment, author: User, parent: Comment | None) -> None:
    """One notification per person: reply to them > comment on their tool/colab > @mention."""
    told: set[int] = {author.id}
    owner_id = permissions.comment_target_owner_id(comment)
    plan: list[tuple[int, NotificationKind]] = []
    if parent is not None and parent.author_id is not None:
        plan.append((parent.author_id, NotificationKind.comment_reply))
    if owner_id is not None:
        plan.append((owner_id, NotificationKind.comment_new))
    handles = mentioned_handles(comment.body)
    if handles:
        for person in _profiles(db, set(handles)).values():
            plan.append((person.id, NotificationKind.comment_mention))
    for user_id, kind in plan:
        if user_id in told:
            continue
        told.add(user_id)
        recipient = db.get(User, user_id)
        if not _can_be_told(recipient):
            continue
        assert recipient is not None
        if comment.colab is not None and not permissions.can_view_colab(recipient, comment.colab):
            continue
        notifications.notify_comment(db, recipient, kind, comment, author)


def link(comment: Comment, lang: str) -> str:
    base = get_settings().base_url.rstrip("/")
    if comment.tool is not None:
        path = f"/t/{comment.tool.slug}"
    else:
        path = f"/colabs/{comment.colab_id}"
    return f"{base}{lang_path(lang, path)}#comment-{comment.id}"
