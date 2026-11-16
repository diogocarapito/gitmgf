"""Password hashing with scrypt from the standard library (no extra dependency).

Stored format: scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>
"""

import base64
import hashlib
import hmac
import secrets

N, R, P = 2**15, 8, 1
DKLEN = 32
MAXMEM = 64 * 1024 * 1024
MIN_LENGTH = 10
MAX_LENGTH = 128

# Spent on unknown accounts so login timing doesn't reveal which emails exist.
_DUMMY = None


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, maxmem=MAXMEM, dklen=DKLEN)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def verify_password(password: str, stored: str | None) -> bool:
    global _DUMMY
    if not stored:
        if _DUMMY is None:
            _DUMMY = hash_password(secrets.token_hex(8))
        stored, password = _DUMMY, password + "\x00"  # always fails, same cost
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected) and bool(stored is not _DUMMY)


def password_problem(password: str, email: str | None = None) -> str | None:
    """Returns an error msgid, or None when the password is acceptable."""
    from app.i18n import N_

    if len(password) < MIN_LENGTH:
        return N_("A palavra-passe deve ter pelo menos 10 caracteres.")
    if len(password) > MAX_LENGTH:
        return N_("A palavra-passe é demasiado longa (máx. 128 caracteres).")
    if email and password.strip().lower() == email.strip().lower():
        return N_("A palavra-passe não pode ser igual ao email.")
    return None
