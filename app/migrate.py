"""Additive schema updates.

create_all adds missing tables. It does not add columns to a table that
already exists, so this module adds those columns itself. It does not drop
tables, columns, or rows.
"""

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import Base

MIGRATION_VERSION = "2026-10-27-examination-types"

STUDENT_COLUMNS = (
    ("department", "VARCHAR(120)"),
    ("year_or_semester", "VARCHAR(40)"),
    ("is_active", "BOOLEAN NOT NULL DEFAULT true"),
    ("is_demo", "BOOLEAN NOT NULL DEFAULT false"),
)
USER_COLUMNS = (
    ("must_change_password", "BOOLEAN NOT NULL DEFAULT false"),
)
CONCERN_COLUMNS = (
    ("seed_key", "VARCHAR(80)"),
)


def _column_exists(connection, table_name: str, column_name: str) -> bool:
    found = connection.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()
    return found is not None


def _table_exists(connection, table_name: str) -> bool:
    found = connection.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).scalar()
    return found is not None


def prepare_database(engine: Engine) -> None:
    """Create missing tables and columns, then record the migration version."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        if _table_exists(connection, "subjects") and not _column_exists(connection, "subjects", "is_active"):
            connection.execute(text(
                "ALTER TABLE subjects ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true"
            ))
        if _table_exists(connection, "students"):
            for column_name, column_sql in STUDENT_COLUMNS:
                if not _column_exists(connection, "students", column_name):
                    connection.execute(text(f"ALTER TABLE students ADD COLUMN {column_name} {column_sql}"))
            connection.execute(
                text(
                    """
                    UPDATE students
                    SET is_demo = true,
                        department = COALESCE(department, 'Demonstration')
                    WHERE admission_number IN ('ADM-1001', 'ADM-1002', 'ADM-1003')
                      AND is_demo = false
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE students
                    SET year_or_semester = 'Demo'
                    WHERE is_demo = true
                      AND (year_or_semester IS NULL OR year_or_semester = '')
                    """
                )
            )
        if _table_exists(connection, "users"):
            for column_name, column_sql in USER_COLUMNS:
                if not _column_exists(connection, "users", column_name):
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_sql}"))
        if _table_exists(connection, "concerns"):
            for column_name, column_sql in CONCERN_COLUMNS:
                if not _column_exists(connection, "concerns", column_name):
                    connection.execute(text(f"ALTER TABLE concerns ADD COLUMN {column_name} {column_sql}"))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_concern_seed_key ON concerns (seed_key)"
            ))
        if _table_exists(connection, "examinations"):
            if not _column_exists(connection, "examinations", "is_active"):
                connection.execute(text(
                    "ALTER TABLE examinations ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT true"
                ))
            connection.execute(text("ALTER TABLE examinations ALTER COLUMN held_on DROP NOT NULL"))
            connection.execute(text("ALTER TABLE examinations DROP CONSTRAINT IF EXISTS ck_examination_type"))
            connection.execute(text(
                """
                ALTER TABLE examinations ADD CONSTRAINT ck_examination_type
                CHECK (exam_type IN ('fat', 'assignment', 'end_semester', 'midterm', 'final', 'quiz'))
                """
            ))
            connection.execute(text(
                """
                UPDATE examinations
                SET name = 'FAT', exam_type = 'fat', is_active = true
                WHERE name = 'Midterm Examination'
                """
            ))
            connection.execute(text(
                """
                UPDATE examinations
                SET name = 'End Semester Examination', exam_type = 'end_semester', is_active = true
                WHERE name = 'Final Examination'
                """
            ))
            connection.execute(text(
                """
                UPDATE examinations
                SET is_active = false
                WHERE NOT (
                    (exam_type = 'fat' AND name = 'FAT')
                    OR (exam_type = 'assignment' AND name = 'Assignment')
                    OR (exam_type = 'end_semester' AND name = 'End Semester Examination')
                )
                """
            ))
            connection.execute(text(
                """
                UPDATE examinations
                SET is_active = false
                WHERE exam_type IN ('fat', 'assignment', 'end_semester')
                  AND id NOT IN (
                    SELECT DISTINCT ON (exam_type) id
                    FROM examinations
                    WHERE (exam_type = 'fat' AND name = 'FAT')
                       OR (exam_type = 'assignment' AND name = 'Assignment')
                       OR (exam_type = 'end_semester' AND name = 'End Semester Examination')
                    ORDER BY exam_type, (held_on IS NULL), id
                  )
                """
            ))
            connection.execute(text(
                """
                INSERT INTO examinations (name, exam_type, held_on, is_active)
                SELECT 'FAT', 'fat', NULL, true
                WHERE NOT EXISTS (
                    SELECT 1 FROM examinations WHERE exam_type = 'fat' AND name = 'FAT' AND is_active = true
                )
                """
            ))
            connection.execute(text(
                """
                INSERT INTO examinations (name, exam_type, held_on, is_active)
                SELECT 'Assignment', 'assignment', NULL, true
                WHERE NOT EXISTS (
                    SELECT 1 FROM examinations
                    WHERE exam_type = 'assignment' AND name = 'Assignment' AND is_active = true
                )
                """
            ))
            connection.execute(text(
                """
                INSERT INTO examinations (name, exam_type, held_on, is_active)
                SELECT 'End Semester Examination', 'end_semester', NULL, true
                WHERE NOT EXISTS (
                    SELECT 1 FROM examinations
                    WHERE exam_type = 'end_semester' AND name = 'End Semester Examination' AND is_active = true
                )
                """
            ))
        already = connection.execute(
            text("SELECT 1 FROM schema_migrations WHERE version = :version"),
            {"version": MIGRATION_VERSION},
        ).scalar()
        if already is None:
            connection.execute(
                text(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (:version, :applied_at)"
                ),
                {"version": MIGRATION_VERSION, "applied_at": datetime.now(timezone.utc)},
            )
