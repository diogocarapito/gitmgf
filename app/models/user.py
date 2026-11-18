from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import Locale, Profession, Role, UserStatus, str_enum

if TYPE_CHECKING:
    from app.models.taxonomy import Category


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    email_verified_at: Mapped[datetime | None]
    password_hash: Mapped[str | None] = mapped_column(String(200))
    password_changed_at: Mapped[datetime | None]
    display_name: Mapped[str] = mapped_column(String(80), default="")
    handle: Mapped[str | None] = mapped_column(String(30), unique=True)
    profession: Mapped[Profession | None] = mapped_column(str_enum(Profession, "profession"))
    specialty_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    workplace: Mapped[str | None] = mapped_column(String(120))
    github_username: Mapped[str | None] = mapped_column(String(39))
    locale: Mapped[Locale] = mapped_column(str_enum(Locale, "locale"), default=Locale.pt)
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"), default=Role.user)
    status: Mapped[UserStatus] = mapped_column(str_enum(UserStatus, "user_status"), default=UserStatus.active)
    suspended_reason: Mapped[str | None]
    onboarded_at: Mapped[datetime | None]
    terms_version: Mapped[str | None] = mapped_column(String(20))
    terms_accepted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]

    specialty: Mapped["Category | None"] = relationship(lazy="joined")

    @property
    def is_moderator(self) -> bool:
        return self.role in (Role.moderator, Role.admin)

    @property
    def is_admin(self) -> bool:
        return self.role == Role.admin

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.active

    def __repr__(self) -> str:
        return f"<User {self.id} {self.role}>"


class Invite(Base):
    """Invite-only registration: the code is shown once to the admin; only its sha256 is stored."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    email: Mapped[str | None] = mapped_column(String(254))  # if set, only this address may use it
    note: Mapped[str | None] = mapped_column(String(200))
    max_uses: Mapped[int] = mapped_column(default=1)
    uses: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def remaining(self) -> int:
        return max(0, self.max_uses - self.uses)


class PasswordResetToken(Base):
    """One-time set/reset-password link created by an admin (no email needed)."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship(lazy="joined", foreign_keys=[user_id])


class EmailCode(Base):
    """A 6-digit code emailed to confirm an address (registration) or to reset a password (D30).

    The browser holds `ticket` (in the URL); the person types the code from the email. Only hashes are
    stored. A pending registration keeps the form data (with the password already hashed) in `payload`
    until the code is entered: no account exists before that.
    """

    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(String(10))  # "register" | "reset"
    ticket_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    attempts: Mapped[int] = mapped_column(default=0)
    sends: Mapped[int] = mapped_column(default=1)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(cookie token)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_secret: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    user_agent: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(lazy="joined")
