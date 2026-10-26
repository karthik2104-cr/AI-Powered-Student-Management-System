"""Demo student logins.

New demo accounts receive a random password. An account that already exists
keeps its hash until `assign_demo_student_passwords` is run. That operation
sets each demo student's hash from the stored name and the student's position
in `students.id` order. It does not change the administrator, non-demo
students, or any academic records. Plain passwords are written only to
.demo-credentials, which Git ignores.
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import PROJECT_ROOT
from app.models import Student, User
from app.security import hash_password
from app.validation import clean_email, clean_password

CREDENTIAL_FILE = PROJECT_ROOT / ".demo-credentials"
PASSWORD_ORDER = "students.id ascending among demo students, starting at 1"


def provision_demo_logins(session: Session, students: list[dict]) -> dict:
    """Create missing demo logins. Existing passwords and the admin account stay."""
    known = _read_credentials()
    created = 0
    skipped = 0
    fresh = []
    for spec in students:
        student = session.scalar(select(Student).where(Student.admission_number == spec["admission_number"]))
        if student is None:
            skipped += 1
            continue
        existing = session.scalar(select(User).where(User.email == student.email))
        if existing is not None:
            skipped += 1
            continue
        if student.email in known:
            password = known[student.email]["password"]
        else:
            password = secrets.token_urlsafe(12)
            fresh.append({
                "name": student.full_name,
                "email": student.email,
                "admission_number": student.admission_number,
                "password": password,
            })
        session.add(
            User(
                email=student.email,
                password_hash=hash_password(password),
                role="student",
                is_active=True,
                must_change_password=False,
                student_id=student.id,
                created_at=spec.get("registered_at") or datetime.now(timezone.utc),
            )
        )
        created += 1
    if fresh:
        _append_credentials(fresh)
    return {"accounts_created": created, "accounts_skipped": skipped}


def _read_credentials() -> dict[str, dict]:
    """Read a credential file when one exists. An empty or missing file adds nothing."""
    if not CREDENTIAL_FILE.exists():
        return {}
    text = CREDENTIAL_FILE.read_text(encoding="utf-8")
    records: dict[str, dict] = {}
    current: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            if current.get("email"):
                records[current["email"]] = current
                current = {}
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key] = value
    if current.get("email"):
        records[current["email"]] = current
    return records


def _append_credentials(rows: list[dict]) -> None:
    """Add new accounts to the local file. Existing lines are left as they are."""
    new_file = not CREDENTIAL_FILE.exists() or CREDENTIAL_FILE.stat().st_size == 0
    with CREDENTIAL_FILE.open("a", encoding="utf-8") as handle:
        if new_file:
            handle.write("# Local demo student passwords. Git ignores this file.\n")
            handle.write("# PostgreSQL stores only bcrypt hashes.\n\n")
        for row in rows:
            handle.write("name=" + row["name"] + "\n")
            handle.write("email=" + row["email"] + "\n")
            handle.write("admission_number=" + row["admission_number"] + "\n")
            handle.write("password=" + row["password"] + "\n\n")


def student_password(full_name: str, number: int) -> str | None:
    """Build FirstNameLastNameNumber from the stored name.

    The first word is the first name and the last word is the last name.
    Spaces and punctuation are removed from those words. A single name, or a
    number below 1, cannot be used.
    """
    if number < 1:
        return None
    parts = [part for part in (full_name or "").split() if part.strip()]
    if len(parts) < 2:
        return None
    first = "".join(character for character in parts[0] if character.isalnum())
    last = "".join(character for character in parts[-1] if character.isalnum())
    if not first or not last:
        return None
    try:
        return clean_password(f"{first}{last}{number}")
    except ValueError:
        return None


def assign_demo_student_passwords(session: Session) -> dict:
    """Hash a new password for every demo student login.

    Students are numbered by `students.id` ascending. Nothing is written when
    any demo login cannot be given a password, so a bad name does not leave a
    partial change. The caller commits. The result has no passwords.
    """
    plans, skipped, unchanged = _password_plan(session)
    summary = {
        "updated": 0,
        "skipped": skipped,
        "unchanged": unchanged,
        "ordering": PASSWORD_ORDER,
    }
    if skipped:
        return summary
    protected = _protected_hashes(session)
    for plan in plans:
        plan["user"].password_hash = hash_password(plan["password"])
    session.flush()
    _require_unchanged_hashes(session, protected)
    summary["updated"] = len(plans)
    return summary


def write_demo_credential_file(session: Session) -> int:
    """Replace .demo-credentials with the current demo passwords.

    The file is replaced only after its temporary copy is written. Passwords
    are calculated again from stored names; they are not read from the database.
    """
    plans, skipped, _unchanged = _password_plan(session)
    if skipped:
        raise ValueError("Demo credentials were not written because a student password could not be built.")
    lines = [
        "# Local demo student passwords. Git ignores this file.",
        "# PostgreSQL stores only bcrypt hashes.",
        "# Numbered by students.id ascending among demo students, starting at 1.",
        "",
    ]
    for plan in plans:
        student = plan["student"]
        lines.append("name=" + student.full_name)
        lines.append("email=" + student.email)
        lines.append("admission_number=" + student.admission_number)
        lines.append("password=" + plan["password"])
        lines.append("")
    temporary = CREDENTIAL_FILE.with_name(".demo-credentials.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(CREDENTIAL_FILE)
    return len(plans)


def _password_plan(session: Session) -> tuple[list[dict], list[dict], list[dict]]:
    demo_students = session.scalars(
        select(Student).where(Student.is_demo.is_(True)).order_by(Student.id.asc())
    ).all()
    other_students = session.scalars(
        select(Student).where(Student.is_demo.is_(False)).order_by(Student.id.asc())
    ).all()
    plans = []
    skipped = []
    for number, student in enumerate(demo_students, start=1):
        user = session.scalar(
            select(User).where(User.student_id == student.id, User.role == "student")
        )
        if user is None:
            skipped.append({"admission_number": student.admission_number, "reason": "no student login"})
            continue
        password = student_password(student.full_name, number)
        if password is None:
            skipped.append({
                "admission_number": student.admission_number,
                "reason": "the stored name does not have a first and last name",
            })
            continue
        plans.append({"user": user, "student": student, "password": password, "number": number})
    unchanged = [
        {"admission_number": student.admission_number, "reason": "not a demo account"}
        for student in other_students
    ]
    return plans, skipped, unchanged


def _protected_hashes(session: Session) -> dict[int, str]:
    users = session.scalars(select(User)).all()
    protected = {}
    for user in users:
        if user.role != "student":
            protected[user.id] = user.password_hash
            continue
        student = session.get(Student, user.student_id) if user.student_id is not None else None
        if student is None or not student.is_demo:
            protected[user.id] = user.password_hash
    return protected


def apply_demo_student_emails(session: Session) -> dict:
    """Set the 15 demo profile and login emails from the seed roster.

    Each student is matched by admission number and full name. Password hashes
    and non-demo accounts are not changed. Nothing is written when a target
    email belongs to a different account. The caller commits.
    """
    from app.demo_roster import EXTRA_STUDENTS
    from app.seed import DEMO_STUDENTS

    specs = [
        {
            "admission_number": row["admission_number"],
            "full_name": row["full_name"],
            "email": clean_email(row["email"]),
        }
        for row in (*DEMO_STUDENTS, *EXTRA_STUDENTS)
    ]
    if len({row["email"] for row in specs}) != len(specs):
        raise ValueError("The demo roster has duplicate email addresses.")
    if len(specs) != 15:
        raise ValueError("Expected 15 demo students in the roster.")

    planned = []
    missing = []
    for spec in specs:
        student = session.scalar(
            select(Student).where(Student.admission_number == spec["admission_number"])
        )
        if student is None or student.full_name != spec["full_name"] or not student.is_demo:
            missing.append(spec["admission_number"])
            continue
        user = session.scalar(
            select(User).where(User.student_id == student.id, User.role == "student")
        )
        if user is None:
            missing.append(spec["admission_number"])
            continue
        planned.append((student, user, spec["email"]))
    if missing:
        return {"updated": 0, "already_correct": 0, "missing": missing}

    for student, user, email in planned:
        other_student = session.scalar(
            select(Student).where(Student.email == email, Student.id != student.id)
        )
        other_user = session.scalar(
            select(User).where(User.email == email, User.id != user.id)
        )
        if other_student is not None or other_user is not None:
            raise ValueError("A demo email address is already used by another account.")

    protected_hashes = {user.id: user.password_hash for _student, user, _email in planned}
    other_emails = {
        student.id: (student.email, user.email if user is not None else None)
        for student, user in (
            (
                row,
                session.scalar(select(User).where(User.student_id == row.id)),
            )
            for row in session.scalars(select(Student).where(Student.is_demo.is_(False))).all()
        )
    }
    updated = 0
    already_correct = 0
    for student, user, email in planned:
        if student.email == email and user.email == email:
            already_correct += 1
            continue
        student.email = email
        user.email = email
        updated += 1
    session.flush()
    for user_id, password_hash in protected_hashes.items():
        if session.get(User, user_id).password_hash != password_hash:
            raise RuntimeError("A demo password hash changed while updating emails.")
    for student_id, (student_email, user_email) in other_emails.items():
        student = session.get(Student, student_id)
        user = session.scalar(select(User).where(User.student_id == student_id))
        if student.email != student_email or (user.email if user is not None else None) != user_email:
            raise RuntimeError("A non-demo email address was changed.")
    return {"updated": updated, "already_correct": already_correct, "missing": []}


def refresh_demo_credential_emails(session: Session) -> int:
    """Replace demo credential email addresses with the stored student emails.

    Password lines already in the file are copied unchanged.
    """
    students = session.scalars(
        select(Student).where(Student.is_demo.is_(True)).order_by(Student.id.asc())
    ).all()
    by_admission = {
        row["admission_number"]: row
        for row in _read_credentials().values()
        if row.get("admission_number")
    }
    lines = [
        "# Local demo student passwords. Git ignores this file.",
        "# PostgreSQL stores only bcrypt hashes.",
        "# Numbered by students.id ascending among demo students, starting at 1.",
        "",
    ]
    written = 0
    for student in students:
        current = by_admission.get(student.admission_number)
        if current is None or "password" not in current:
            continue
        lines.append("name=" + student.full_name)
        lines.append("email=" + student.email)
        lines.append("admission_number=" + student.admission_number)
        lines.append("password=" + current["password"])
        lines.append("")
        written += 1
    if written != len(students):
        raise ValueError("Demo credential file is missing a student, so it was not replaced.")
    temporary = CREDENTIAL_FILE.with_name(".demo-credentials.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    temporary.replace(CREDENTIAL_FILE)
    return written


def _require_unchanged_hashes(session: Session, protected: dict[int, str]) -> None:
    for user_id, password_hash in protected.items():
        user = session.get(User, user_id)
        if user is None or user.password_hash != password_hash:
            raise RuntimeError("A password outside the demo student accounts was changed.")


if __name__ == "__main__":
    from app.database import SessionLocal

    if SessionLocal is None:
        raise SystemExit("Database is not configured.")
    with SessionLocal() as session:
        summary = assign_demo_student_passwords(session)
        if summary["skipped"]:
            session.rollback()
        else:
            session.commit()
            write_demo_credential_file(session)
    print(f"updated={summary['updated']}")
    print(f"ordering={summary['ordering']}")
    skipped = ",".join(row["admission_number"] for row in summary["skipped"]) or "none"
    unchanged = ",".join(
        row["admission_number"] + " (" + row["reason"] + ")" for row in summary["unchanged"]
    ) or "none"
    print(f"skipped={skipped}")
    print(f"unchanged={unchanged}")
    if summary["skipped"]:
        raise SystemExit(1)
