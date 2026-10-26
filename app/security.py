"""Password hashes and login cookies.

The database stores a bcrypt hash and a SHA-256 hash of the session token.
The browser cookie contains only the random token.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

COOKIE_NAME = "sms_session"
SESSION_DAYS = 7


def hash_password(password: str) -> str:
    """Return a bcrypt hash. The plain password is not stored."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True when the password matches the stored hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    """Return a random token suitable for an HttpOnly cookie."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a session token before it is stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime | None = None) -> datetime:
    """Return the time at which a new login session stops being valid."""
    current = now or datetime.now(timezone.utc)
    return current + timedelta(days=SESSION_DAYS)
