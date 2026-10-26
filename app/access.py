"""Server-side checks for who is signed in and which records they may open.

Hiding a button in the browser is not enough. These dependencies run on the
API before a route reads or changes a record.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, require_db
from app.models import LoginSession, Student, User
from app.security import COOKIE_NAME, hash_token


def require_user(request: Request, db: Session | None = Depends(get_db)) -> User:
    """Return the active user for the session cookie, or HTTP 401."""
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required.")

    database = require_db(db)
    login = database.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(token)))
    if login is None or login.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Sign in required.")

    user = database.get(User, login.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Sign in required.")
    if user.role == "student":
        student = database.get(Student, user.student_id) if user.student_id else None
        if student is None or not student.is_active:
            raise HTTPException(status_code=401, detail="This student account is inactive.")
    return user


def signed_in_role(request: Request) -> str | None:
    """Return admin or student for a valid cookie, or None. Pages use this to redirect."""
    from app.database import SessionLocal

    token = request.cookies.get(COOKIE_NAME, "")
    if not token or SessionLocal is None:
        return None
    with SessionLocal() as database:
        login = database.scalar(select(LoginSession).where(LoginSession.token_hash == hash_token(token)))
        if login is None or login.expires_at <= datetime.now(timezone.utc):
            return None
        user = database.get(User, login.user_id)
        if user is None or not user.is_active:
            return None
        if user.role == "student":
            student = database.get(Student, user.student_id) if user.student_id else None
            if student is None or not student.is_active:
                return None
        return user.role


def require_admin(user: User = Depends(require_user)) -> User:
    """Allow only an active administrator."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="An administrator account is required.")
    return user


def require_student(user: User = Depends(require_user)) -> User:
    """Allow only a student account that is linked to a student profile."""
    if user.role != "student" or user.student_id is None:
        raise HTTPException(status_code=403, detail="A student account is required.")
    return user


def owns_student_or_admin(user: User, student_id: int) -> None:
    """Block a student from opening another student's records."""
    if user.role == "admin":
        return
    if user.role == "student" and user.student_id == student_id:
        return
    raise HTTPException(
        status_code=403,
        detail="You can only open your own academic records.",
    )
