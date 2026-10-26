"""Create the first administrator once.

An existing administrator is left unchanged, including the password.
When no administrator exists and the environment has no admin password,
this module creates admin@studentmanagement.local and writes the generated
password to .admin-credentials. That file is gitignored. The password is
not printed and is not returned to the API.
"""

import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import PROJECT_ROOT
from app.models import User
from app.security import hash_password
from app.validation import clean_email, clean_password

DEFAULT_ADMIN_EMAIL = "admin@studentmanagement.local"
CREDENTIAL_FILE = PROJECT_ROOT / ".admin-credentials"


def bootstrap_admin(session: Session) -> str:
    """Create one administrator when the users table has none.

    Returns a short status word. The password is never included.
    """
    existing = session.scalar(select(User.id).where(User.role == "admin").limit(1))
    if existing is not None:
        return "configured"

    email = os.getenv("ADMIN_EMAIL", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    if email or password:
        try:
            email = clean_email(email)
            password = clean_password(password)
        except ValueError:
            return "invalid"
    else:
        email = DEFAULT_ADMIN_EMAIL
        password = secrets.token_urlsafe(18)

    taken = session.scalar(select(User).where(User.email == email))
    if taken is not None:
        return "configured" if taken.role == "admin" else "email_taken"

    session.add(
        User(
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            must_change_password=True,
            student_id=None,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    _store_initial_password(email, password)
    return "created"


def _store_initial_password(email: str, password: str) -> None:
    """Write the initial password beside the project, not into source control."""
    if CREDENTIAL_FILE.exists():
        return
    CREDENTIAL_FILE.write_text(
        "email=" + email + "\n"
        "password=" + password + "\n"
        "note=Change this password after signing in. Keep this file on this computer.\n",
        encoding="utf-8",
    )
