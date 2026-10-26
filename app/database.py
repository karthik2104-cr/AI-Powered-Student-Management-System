"""Open a connection to PostgreSQL.

`engine` and `SessionLocal` are the only database connections used by the
application. Stage 1 checks the connection. Stage 2 uses the same connection
to create the academic tables and read them.
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# app/database.py -> app/ -> project folder. Load .env from that project folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Filled in by configure_database(). They stay empty when DATABASE_URL is missing.
engine = None
SessionLocal = None
_config_error = None


class Base(DeclarativeBase):
    """Shared base class. Every database table inherits from this."""


def hide_secrets(message: str) -> str:
    """Remove a password from an error message before the API shows it."""
    # postgresql+psycopg://user:password@host/db becomes postgresql+psycopg://***@host/db
    cleaned = re.sub(r"://[^/\s]+@", "://***@", message)
    cleaned = re.sub(
        r"(password\s*[=:]\s*)\S+",
        r"\1***",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned


def configure_database() -> None:
    """Build the SQLAlchemy engine and session factory from DATABASE_URL."""
    global engine, SessionLocal, _config_error

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        engine = None
        SessionLocal = None
        _config_error = (
            "DATABASE_URL is not set. Copy .env.example to .env and set "
            "the PostgreSQL connection URL."
        )
        return

    try:
        # The engine manages a pool of connections. pool_pre_ping checks that
        # a pooled connection still works before the app uses it again.
        engine = create_engine(database_url, pool_pre_ping=True)
        # SessionLocal is a factory. SessionLocal() opens one short database
        # session. SQLAlchemy waits for an explicit commit before saving changes.
        SessionLocal = sessionmaker(bind=engine, autoflush=False)
        _config_error = None
    except Exception as exc:
        engine = None
        SessionLocal = None
        _config_error = (
            "DATABASE_URL could not be used: " + hide_secrets(str(exc))
        )


def configuration_error() -> str | None:
    """Return a safe message when DATABASE_URL is missing or invalid."""
    return _config_error


def check_database_connection() -> dict:
    """Run SELECT 1. Python, not the LLM, decides whether the database answered."""
    if engine is None:
        return {
            "ok": False,
            "detail": _config_error or "Database is not configured.",
        }

    try:
        # engine.connect() borrows one connection and closes it when the block ends.
        with engine.connect() as connection:
            value = connection.execute(text("SELECT 1")).scalar()
    except Exception as exc:
        return {
            "ok": False,
            "detail": "PostgreSQL connection failed: " + hide_secrets(str(exc)),
        }

    if value != 1:
        return {
            "ok": False,
            "detail": "PostgreSQL responded, but SELECT 1 did not return 1.",
        }

    return {"ok": True, "detail": "PostgreSQL accepted SELECT 1."}


def prepare_application_database() -> str:
    """Create tables and the first administrator. This does not insert demo rows."""
    if engine is None or SessionLocal is None:
        raise RuntimeError(configuration_error() or "Database is not configured.")

    from app.bootstrap import bootstrap_admin
    from app.migrate import prepare_database

    prepare_database(engine)
    with SessionLocal() as session:
        return bootstrap_admin(session)


def init_database() -> None:
    """Create the tables and insert the synthetic demo rows.

    Calling this more than once does not create duplicate students, subjects,
    examinations, or marks. The demo loader uses each record's natural key.
    Startup does not call this. An administrator loads demo data on purpose.
    """
    if engine is None or SessionLocal is None:
        raise RuntimeError(configuration_error() or "Database is not configured.")

    from app.migrate import prepare_database
    from app.seed import seed_demo_data

    prepare_database(engine)
    with SessionLocal() as session:
        seed_demo_data(session)
        session.commit()


configure_database()
