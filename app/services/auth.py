"""Password sign-in, invite-only registration and admin-issued reset links (docs/DECISIONS.md D26)."""

import hashlib
import secrets
from datetime import timedelta

from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import Invite, PasswordResetToken, User
from app.models.enums import Locale, Role, UserStatus
from app.services import audit, passwords, sessions, settings_store

INVITE_DEFAULT_DAYS = 14
RESET_TTL = timedelta(hours=48)


class AuthError(Exception):
    """Sign-in or registration refused. `code` maps to a translated message in the router."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_email(value: str) -> str:
    return value.strip().lower()


def safe_next(value: str | None) -> str | None:
    """Only same-site relative paths: '/…' but never '//…' or '/\\…' (TECH_SPEC §16)."""
    if not value or not value.startswith("/") or value.startswith("//") or value.startswith("/\\"):
        return None
    if any(c in value for c in "\r\n\t") or len(value) > 500:
        return None
    return value


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- sign-in ----------


def authenticate(db: Session, raw_email: str, password: str) -> User:
    """Same work and the same error whether the account exists or not (no enumeration)."""
    user = db.scalar(select(User).where(User.email == normalize_email(raw_email)))
    ok = passwords.verify_password(password, user.password_hash if user else None)
    if user is None or not ok:
        raise AuthError("bad_credentials")
    check_can_login(user)
    return user


def check_can_login(user: User) -> None:
    if user.status != UserStatus.active:
        raise AuthError("suspended")


def apply_admin_emails(db: Session, user: User) -> None:
    """ADMIN_EMAILS bootstrap: promote on login and audit it once."""
    if user.email in get_settings().admin_email_set and user.role != Role.admin:
        old = user.role
        user.role = Role.admin
        audit.log(
            db, None, "user.role_change", "user", user.id, old=old.value, new="admin", via="ADMIN_EMAILS"
        )


def set_password(db: Session, user: User, password: str) -> None:
    user.password_hash = passwords.hash_password(password)
    user.password_changed_at = utcnow()
    audit.log(db, user.id, "user.password_change", "user", user.id)


# ---------- invites ----------


def create_invite(
    db: Session,
    actor: User | None,
    email: str | None = None,
    note: str | None = None,
    max_uses: int = 1,
    days: int = INVITE_DEFAULT_DAYS,
) -> tuple[Invite, str]:
    """Returns the invite and its code. The code is shown once; only its hash is stored."""
    code = secrets.token_urlsafe(12)
    invite = Invite(
        code_hash=_hash(code),
        created_by=actor.id if actor else None,
        email=normalize_email(email) if email else None,
        note=(note or "").strip()[:200] or None,
        max_uses=max(1, min(max_uses, 500)),
        expires_at=utcnow() + timedelta(days=max(1, min(days, 365))),
    )
    db.add(invite)
    db.flush()
    audit.log(
        db,
        actor.id if actor else None,
        "invite.create",
        "invite",
        invite.id,
        max_uses=invite.max_uses,
        locked=bool(invite.email),
    )
    return invite, code


def find_invite(db: Session, code: str | None) -> Invite | None:
    if not code:
        return None
    invite = db.scalar(select(Invite).where(Invite.code_hash == _hash(code.strip())))
    if (
        invite is None
        or invite.revoked_at is not None
        or invite.uses >= invite.max_uses
        or invite.expires_at <= utcnow()
    ):
        return None
    return invite


def revoke_invite(db: Session, invite: Invite, actor: User) -> None:
    invite.revoked_at = utcnow()
    audit.log(db, actor.id, "invite.revoke", "invite", invite.id)


def registration_needs_invite(db: Session, email: str | None = None) -> bool:
    if email and normalize_email(email) in get_settings().admin_email_set:
        return False  # bootstrap: the first admin can always register
    return not settings_store.get(db, "site.registration_open")


# ---------- registration ----------


def register(db: Session, raw_email: str, password: str, invite_code: str | None, lang: str) -> User:
    address = normalize_email(raw_email)
    invite = None
    if registration_needs_invite(db, address):
        invite = find_invite(db, invite_code)
        if invite is None:
            raise AuthError("invalid_invite")
        if invite.email and invite.email != address:
            raise AuthError("invite_email_mismatch")
    if db.scalar(select(User.id).where(User.email == address)) is not None:
        raise AuthError("email_taken")
    user = User(
        email=address,
        display_name="",
        locale=Locale(lang) if lang in ("pt", "en") else Locale.pt,
        password_hash=passwords.hash_password(password),
        password_changed_at=utcnow(),
    )
    db.add(user)
    db.flush()
    if invite is not None:
        invite.uses += 1
    audit.log(db, None, "user.register", "user", user.id, invite_id=invite.id if invite else None)
    return user


# ---------- reset / set-password links ----------


def create_reset_link(db: Session, user: User, actor: User | None) -> str:
    """One-time link valid 48 h. Earlier unused links for the user stop working."""
    for old in db.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
        )
    ):
        old.used_at = utcnow()
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=_hash(token),
            created_by=actor.id if actor else None,
            expires_at=utcnow() + RESET_TTL,
        )
    )
    db.flush()  # autoflush is off: make the new link visible to a later call in this session
    audit.log(db, actor.id if actor else None, "user.reset_link", "user", user.id)
    return token


def find_reset_token(db: Session, token: str) -> PasswordResetToken | None:
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _hash(token)))
    if (
        row is None
        or row.used_at is not None
        or row.expires_at <= utcnow()
        or row.user.status != UserStatus.active
    ):
        return None
    return row


def reset_password(db: Session, token: str, password: str) -> User:
    row = find_reset_token(db, token)
    if row is None:
        raise AuthError("invalid_link")
    row.used_at = utcnow()
    user = row.user
    set_password(db, user, password)
    sessions.destroy_all(db, user.id)  # everyone else is signed out
    return user


# ---------- profile helpers ----------


def needs_onboarding(db: Session, user: User) -> bool:
    return user.onboarded_at is None or user.terms_version != settings_store.get(db, "terms.current_version")


def suggest_handle(db: Session, seed: str) -> str:
    base = slugify(seed or "", max_length=24, word_boundary=True) or "utilizador"
    if len(base) < 3:
        base = f"{base}-mgf"
    candidate = base
    n = 2
    while db.scalar(select(func.count()).select_from(User).where(User.handle == candidate)):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def handle_available(db: Session, handle: str, user_id: int) -> bool:
    other = db.scalar(select(User.id).where(User.handle == handle, User.id != user_id))
    return other is None
