"""Password sign-in, registration with an emailed code, invites, reset codes and links (D26, D29, D30)."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

from slugify import slugify
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import EmailCode, EmailOutbox, Invite, PasswordResetToken, User
from app.models.enums import Locale, Profession, Role, UserStatus
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
    return invite if invite is not None and _usable(invite) else None


def _usable(invite: Invite) -> bool:
    return invite.revoked_at is None and invite.uses < invite.max_uses and invite.expires_at > utcnow()


def revoke_invite(db: Session, invite: Invite, actor: User) -> None:
    invite.revoked_at = utcnow()
    audit.log(db, actor.id, "invite.revoke", "invite", invite.id)


def registration_needs_invite(db: Session, email: str | None = None) -> bool:
    """Open registration needs email (to verify the address, D30); without SMTP only invites work."""
    if email and normalize_email(email) in get_settings().admin_email_set:
        return False  # bootstrap: the first admin can always register
    return not (email_enabled() and settings_store.get(db, "site.registration_open"))


# ---------- registration ----------


def _check_invite(db: Session, address: str, invite_code: str | None) -> Invite | None:
    if not registration_needs_invite(db, address):
        return None
    invite = find_invite(db, invite_code)
    if invite is None:
        raise AuthError("invalid_invite")
    if invite.email and invite.email != address:
        raise AuthError("invite_email_mismatch")
    return invite


def _profile(profile: dict[str, Any]) -> dict[str, Any]:
    """The registration form's basic info (PRD F2), as stored in a pending registration."""
    return {
        "display_name": str(profile["display_name"]),
        "profession": Profession(profile["profession"]).value,
        "specialty_category_id": profile.get("specialty_category_id"),
    }


def _create_account(
    db: Session,
    address: str,
    password_hash: str,
    profile: dict[str, Any],
    lang: str,
    invite: Invite | None,
    verified: bool,
) -> User:
    """Name, profession and terms come from the registration form, so there is no onboarding step."""
    if db.scalar(select(User.id).where(User.email == address)) is not None:
        raise AuthError("email_taken")
    now = utcnow()
    user = User(
        email=address,
        email_verified_at=now if verified else None,
        display_name=profile["display_name"],
        handle=suggest_handle(db, profile["display_name"]),
        profession=Profession(profile["profession"]),
        specialty_category_id=profile.get("specialty_category_id"),
        locale=Locale(lang) if lang in ("pt", "en") else Locale.pt,
        password_hash=password_hash,
        password_changed_at=now,
        onboarded_at=now,
        terms_version=settings_store.get(db, "terms.current_version"),
        terms_accepted_at=now,
    )
    db.add(user)
    db.flush()
    if invite is not None:
        invite.uses += 1
    audit.log(
        db, None, "user.register", "user", user.id, invite_id=invite.id if invite else None, verified=verified
    )
    _welcome(db, user)
    return user


def _welcome(db: Session, user: User) -> None:
    from app.services import email

    email.enqueue(db, user.email, "welcome", {"name": user.display_name}, user.locale.value)


def register(
    db: Session,
    raw_email: str,
    password: str,
    invite_code: str | None,
    lang: str,
    profile: dict[str, Any],
) -> User:
    """Immediate registration with an invite, used when SMTP is not configured (D26)."""
    address = normalize_email(raw_email)
    invite = _check_invite(db, address, invite_code)
    return _create_account(
        db, address, passwords.hash_password(password), _profile(profile), lang, invite, verified=False
    )


# ---------- reset / set-password links ----------


def create_reset_link(db: Session, user: User, actor: User | None, ttl: timedelta = RESET_TTL) -> str:
    """One-time link (48 h by default). Earlier unused links for the user stop working."""
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
            expires_at=utcnow() + ttl,
        )
    )
    db.flush()  # autoflush is off: make the new link visible to a later call in this session
    audit.log(db, actor.id if actor else None, "user.reset_link", "user", user.id, self_service=actor is None)
    return token


# ---------- email-based flows (only when SMTP is configured, D29/D30) ----------

CODE_TTL = timedelta(minutes=15)
CODE_ATTEMPTS = 5  # wrong codes per email sent
CODE_SENDS = 3  # the first email plus two resends


def email_enabled() -> bool:
    return get_settings().email_backend in ("smtp", "memory", "console")


def reset_url(lang: str, token: str) -> str:
    from app.i18n import lang_path

    return get_settings().base_url.rstrip("/") + lang_path(lang, f"/reset/{token}")


def invite_url(lang: str, code: str) -> str:
    from app.i18n import lang_path

    return get_settings().base_url.rstrip("/") + lang_path(lang, f"/register?invite={code}")


def mask_email(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:1]}{'•' * min(max(len(local) - 1, 1), 6)}@{domain}"


def _code_hash(ticket: str, code: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{ticket}:{code}".encode(), hashlib.sha256).hexdigest()


def _issue_code(db: Session, purpose: str, address: str, payload: dict[str, Any]) -> tuple[str, str]:
    """A new ticket and code. Earlier unused codes for the same address and purpose stop working."""
    now = utcnow()
    for old in db.scalars(
        select(EmailCode).where(
            EmailCode.purpose == purpose, EmailCode.email == address, EmailCode.used_at.is_(None)
        )
    ):
        old.used_at = now
    ticket = secrets.token_urlsafe(24)
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(
        EmailCode(
            purpose=purpose,
            ticket_hash=_hash(ticket),
            email=address,
            code_hash=_code_hash(ticket, code),
            payload=payload,
            expires_at=now + CODE_TTL,
        )
    )
    db.flush()
    return ticket, code


def find_code(db: Session, purpose: str, ticket: str | None) -> EmailCode | None:
    if not ticket:
        return None
    row = db.scalar(
        select(EmailCode).where(EmailCode.purpose == purpose, EmailCode.ticket_hash == _hash(ticket))
    )
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None
    return row


def _check_code(row: EmailCode, ticket: str, code: str) -> None:
    """Counts the attempt; the caller commits even when this raises."""
    if row.attempts >= CODE_ATTEMPTS:
        raise AuthError("code_expired")
    row.attempts += 1
    given = "".join(ch for ch in code if ch.isdigit())
    if not hmac.compare_digest(row.code_hash, _code_hash(ticket, given)):
        raise AuthError("code_expired" if row.attempts >= CODE_ATTEMPTS else "bad_code")
    row.used_at = utcnow()


def _send_code(db: Session, row: EmailCode, code: str) -> None:
    from app.services import email

    lang = row.payload.get("lang", "pt")
    minutes = int(CODE_TTL.total_seconds() // 60)
    if row.payload.get("decoy"):
        return  # unknown account (reset): nothing is sent
    if row.payload.get("exists"):
        email.enqueue(db, row.email, "account_exists", {}, lang)  # registering a taken address
    elif row.purpose == "register":
        email.enqueue(db, row.email, "register_code", {"code": code, "minutes": minutes}, lang)
    else:
        email.enqueue(db, row.email, "password_code", {"code": code, "minutes": minutes}, lang)


def start_registration(
    db: Session,
    raw_email: str,
    password: str,
    invite_code: str | None,
    lang: str,
    profile: dict[str, Any],
) -> str:
    """Step 1: keep the form, email a code, return the ticket. No account exists until step 2.

    A taken address gets the same next screen, and its owner gets an email saying an account exists,
    so the form doesn't reveal who is registered.
    """
    address = normalize_email(raw_email)
    invite = _check_invite(db, address, invite_code)
    if db.scalar(select(User.id).where(User.email == address)) is not None:
        payload: dict[str, Any] = {"exists": True, "lang": lang}
    else:
        payload = {
            "lang": lang,
            "password_hash": passwords.hash_password(password),
            "profile": _profile(profile),
            "invite_id": invite.id if invite else None,
        }
    ticket, code = _issue_code(db, "register", address, payload)
    row = find_code(db, "register", ticket)
    assert row is not None
    _send_code(db, row, code)
    return ticket


def resend_code(db: Session, purpose: str, ticket: str) -> bool:
    """New code on the same ticket. False when the ticket is gone or has used up its resends."""
    row = find_code(db, purpose, ticket)
    if row is None or row.sends >= CODE_SENDS:
        return False
    code = f"{secrets.randbelow(10**6):06d}"
    row.code_hash = _code_hash(ticket, code)
    row.sends += 1
    row.attempts = 0
    row.expires_at = utcnow() + CODE_TTL
    _send_code(db, row, code)
    return True


def complete_registration(db: Session, ticket: str, code: str) -> User:
    """Step 2: the right code creates the account (address verified) and signs in."""
    row = find_code(db, "register", ticket)
    if row is None:
        raise AuthError("code_expired")
    _check_code(row, ticket, code)
    data = row.payload
    if data.get("exists"):
        raise AuthError("email_taken")  # unreachable in practice: that code is never emailed
    invite = db.get(Invite, data["invite_id"]) if data.get("invite_id") else None
    if invite is not None and not _usable(invite):
        raise AuthError("invalid_invite")
    return _create_account(
        db, row.email, data["password_hash"], data["profile"], data.get("lang", "pt"), invite, verified=True
    )


def start_password_reset(db: Session, raw_email: str, lang: str) -> str:
    """Self-service reset. Unknown or suspended accounts get a ticket too, but no email (no enumeration)."""
    address = normalize_email(raw_email)
    user = db.scalar(select(User).where(User.email == address))
    if user is None or user.status != UserStatus.active:
        payload: dict[str, Any] = {"decoy": True, "lang": lang}
    else:
        payload = {"user_id": user.id, "lang": user.locale.value}
    ticket, code = _issue_code(db, "reset", address, payload)
    row = find_code(db, "reset", ticket)
    assert row is not None
    _send_code(db, row, code)
    return ticket


def complete_password_reset(db: Session, ticket: str, code: str, password: str) -> User:
    row = find_code(db, "reset", ticket)
    if row is None:
        raise AuthError("code_expired")
    _check_code(row, ticket, code)
    user = db.get(User, row.payload["user_id"]) if row.payload.get("user_id") else None
    if user is None or user.status != UserStatus.active:
        raise AuthError("code_expired")
    set_password(db, user, password)
    user.email_verified_at = user.email_verified_at or utcnow()  # the code proves the address
    sessions.destroy_all(db, user.id)
    return user


def email_reset_link(db: Session, user: User, actor: User | None) -> EmailOutbox:
    """Admin action: email a 48 h set-password link to the user. Returns the queued outbox row."""
    from app.services import email

    token = create_reset_link(db, user, actor)
    locale = user.locale.value
    row = email.enqueue(
        db, user.email, "password_set", {"link": reset_url(locale, token), "hours": 48}, locale
    )
    assert row is not None  # essential: never switched off
    return row


def email_invite(db: Session, invite: Invite, code: str, lang: str, inviter: User | None) -> None:
    from app.services import email

    assert invite.email, "only invites locked to an address can be emailed"
    email.enqueue(
        db,
        invite.email,
        "invite",
        {
            "link": invite_url(lang, code),
            "inviter": inviter.display_name if inviter and inviter.display_name else "gitmgf",
            "days": max(1, (invite.expires_at - utcnow()).days),
        },
        lang,
    )
    audit.log(db, inviter.id if inviter else None, "invite.email", "invite", invite.id)


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
