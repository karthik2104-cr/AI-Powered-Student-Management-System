"""Database session helpers shared by the route modules."""

from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal, configuration_error, hide_secrets


def get_db() -> Generator[Session | None, None, None]:
    """Open one database session for a request, then close it.

    Yielding None lets FastAPI reject a bad id or body with HTTP 422 before
    the endpoint reports that PostgreSQL is not configured.
    """
    if SessionLocal is None:
        yield None
        return
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def require_db(db: Session | None) -> Session:
    """Return the open session, or explain that PostgreSQL is not configured."""
    if db is None:
        raise HTTPException(
            status_code=503,
            detail=configuration_error() or "Database is not configured.",
        )
    return db


def integrity_conflict(exc: IntegrityError) -> HTTPException:
    """Turn a unique-rule failure into HTTP 409."""
    detail = hide_secrets(str(exc.orig) if exc.orig else str(exc)).lower()
    if "admission_number" in detail:
        message = "A student with this admission number already exists."
    elif "users" in detail and "email" in detail:
        message = "An account with this email already exists."
    elif "email" in detail:
        message = "A student with this email already exists."
    elif "uq_attendance" in detail:
        message = "Attendance for this student, subject, and date already exists."
    elif "student_subject_exam" in detail or "uq_mark" in detail:
        message = "A mark for this student, subject, and examination already exists."
    elif "uq_examination" in detail:
        message = "An examination with this name and date already exists."
    elif "uq_resource" in detail or "uq_concern_resource" in detail:
        message = "This resource is already linked."
    elif "uq_notification" in detail:
        message = "This registration notice already exists."
    elif "seed_key" in detail:
        message = "This demo feedback row already exists."
    elif detail.startswith("ck_") or " check constraint " in f" {detail} ":
        message = "The database rejected this record because a value is outside the allowed rules."
    else:
        message = "This record duplicates an existing one."
    return HTTPException(status_code=409, detail=message)


def flush_session(db: Session) -> None:
    """Send pending rows so database ids exist, or turn a unique-rule failure into HTTP 409."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise integrity_conflict(exc) from None


def commit_session(db: Session) -> None:
    """Save the session, or turn a unique-rule failure into HTTP 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise integrity_conflict(exc) from None
