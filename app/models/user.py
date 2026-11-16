from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow
from app.models.enums import Locale, OAuthProvider, Profession, Role, UserStatus, str_enum

if TYPE_CHECKING:
    from app.models.taxonomy import Category


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    email_verified_at: Mapped[datetime | None]
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
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

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


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[OAuthProvider] = mapped_column(str_enum(OAuthProvider, "oauth_provider"))
    provider_user_id: Mapped[str] = mapped_column(String(64))
    provider_email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship(back_populates="oauth_accounts")


class MagicLinkToken(Base):
    __tablename__ = "magic_link_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    next_path: Mapped[str | None] = mapped_column(String(500))
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
