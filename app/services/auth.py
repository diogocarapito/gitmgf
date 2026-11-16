"""Magic-link and OAuth sign-in, account linking and admin bootstrap (PRD F1, TECH_SPEC §6)."""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import MagicLinkToken, OAuthAccount, User
from app.models.enums import Locale, OAuthProvider, Role, UserStatus
from app.services import audit, email, settings_store

MAGIC_LINK_TTL = timedelta(minutes=15)
HANDLE_RE = re.compile(r"^[a-z0-9-]{3,30}$")


class AuthError(Exception):
    """Sign-in refused. `code` maps to a translated message in the router."""

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


def request_magic_link(db: Session, raw_email: str, next_path: str | None, lang: str) -> None:
    address = normalize_email(raw_email)
    token = secrets.token_urlsafe(32)
    db.add(
        MagicLinkToken(
            email=address,
            token_hash=_hash(token),
            next_path=safe_next(next_path),
            expires_at=utcnow() + MAGIC_LINK_TTL,
        )
    )
    user = db.scalar(select(User).where(User.email == address))
    if user is not None and user.status != UserStatus.active:
        return  # same response, no email: suspended/deleted accounts cannot sign in
    locale = user.locale.value if user else lang
    link = f"{get_settings().base_url.rstrip('/')}/auth/magic/{token}"
    email.enqueue(db, address, "magic_link", {"link": link, "minutes": 15}, locale)


def find_magic_token(db: Session, token: str) -> MagicLinkToken | None:
    row = db.scalar(select(MagicLinkToken).where(MagicLinkToken.token_hash == _hash(token)))
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None
    return row


def consume_magic_token(db: Session, token: str, lang: str) -> tuple[User, str | None, bool]:
    row = find_magic_token(db, token)
    if row is None:
        raise AuthError("invalid_link")
    row.used_at = utcnow()
    user, created = find_or_create_by_email(db, row.email, lang)
    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    return user, row.next_path, created


def find_or_create_by_email(
    db: Session, address: str, lang: str, display_name: str = ""
) -> tuple[User, bool]:
    address = normalize_email(address)
    user = db.scalar(select(User).where(User.email == address))
    if user is not None:
        if user.status != UserStatus.active:
            raise AuthError("suspended")
        return user, False
    if not settings_store.get(db, "site.registration_open"):
        raise AuthError("registration_closed")
    user = User(
        email=address,
        display_name=display_name[:80],
        locale=Locale(lang) if lang in ("pt", "en") else Locale.pt,
        email_verified_at=utcnow(),
    )
    db.add(user)
    db.flush()
    return user, True


def apply_admin_emails(db: Session, user: User) -> None:
    """ADMIN_EMAILS bootstrap: promote on login and audit it once."""
    if user.email in get_settings().admin_email_set and user.role != Role.admin:
        old = user.role
        user.role = Role.admin
        audit.log(
            db, None, "user.role_change", "user", user.id, old=old.value, new="admin", via="ADMIN_EMAILS"
        )


def check_can_login(user: User) -> None:
    if user.status != UserStatus.active:
        raise AuthError("suspended")


@dataclass(frozen=True)
class OAuthProfile:
    provider: OAuthProvider
    provider_user_id: str
    email: str | None
    email_verified: bool
    name: str
    github_login: str | None = None


def oauth_login(
    db: Session, profile: OAuthProfile, lang: str, link_to: User | None = None
) -> tuple[User, bool]:
    """Linking rule (TECH_SPEC §6.2): existing provider account › verified email match › new user."""
    account = db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == profile.provider,
            OAuthAccount.provider_user_id == profile.provider_user_id,
        )
    )
    if link_to is not None:
        if account is not None and account.user_id != link_to.id:
            raise AuthError("provider_taken")
        if account is None:
            db.add(_account(link_to, profile))
            audit.log(
                db, link_to.id, "user.provider_link", "user", link_to.id, provider=profile.provider.value
            )
        _prefill(link_to, profile)
        return link_to, False
    if account is not None:
        user = account.user
        check_can_login(user)
        return user, False
    if not profile.email or not profile.email_verified:
        raise AuthError("unverified_email")
    user, created = find_or_create_by_email(db, profile.email, lang, display_name=profile.name)
    db.add(_account(user, profile))
    _prefill(user, profile)
    return user, created


def _account(user: User, profile: OAuthProfile) -> OAuthAccount:
    return OAuthAccount(
        user_id=user.id,
        provider=profile.provider,
        provider_user_id=profile.provider_user_id,
        provider_email=normalize_email(profile.email) if profile.email else None,
    )


def _prefill(user: User, profile: OAuthProfile) -> None:
    if not user.display_name and profile.name:
        user.display_name = profile.name[:80]
    if profile.github_login and not user.github_username:
        user.github_username = profile.github_login[:39]


def unlink_provider(db: Session, user: User, provider: OAuthProvider) -> None:
    """Email magic link always works, so unlinking never locks anyone out."""
    for account in list(user.oauth_accounts):
        if account.provider == provider:
            db.delete(account)
    audit.log(db, user.id, "user.provider_unlink", "user", user.id, provider=provider.value)


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
