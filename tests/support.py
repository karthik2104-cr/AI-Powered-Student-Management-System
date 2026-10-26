"""Helpers for tests that sign in as a temporary administrator.

The account exists only while the tests run. It is not a default password
for the application.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import AuditLog, LoginSession, User
from app.security import hash_password

TEST_ADMIN_EMAIL = "pytest-admin@example.edu"
TEST_ADMIN_PASSWORD = "Portal-test-admin-1"


def login_admin(client):
    """Create the test administrator if needed, then store the session cookie."""
    if SessionLocal is None:
        raise RuntimeError("Database is not configured.")
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == TEST_ADMIN_EMAIL))
        if user is None:
            session.add(
                User(
                    email=TEST_ADMIN_EMAIL,
                    password_hash=hash_password(TEST_ADMIN_PASSWORD),
                    role="admin",
                    is_active=True,
                    student_id=None,
                    created_at=datetime.now(timezone.utc),
                )
            )
        else:
            user.role = "admin"
            user.is_active = True
            user.password_hash = hash_password(TEST_ADMIN_PASSWORD)
        session.commit()
    finally:
        session.close()

    response = client.post(
        "/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"
    assert "password_hash" not in response.text
    return response


def remove_test_admin() -> None:
    """Delete the temporary administrator, sessions, and audit rows it created."""
    if SessionLocal is None:
        return
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == TEST_ADMIN_EMAIL))
        if user is None:
            return
        session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        session.execute(delete(AuditLog).where(AuditLog.actor_user_id == user.id))
        session.delete(user)
        session.commit()
    finally:
        session.close()
