"""Semester 1 Computer Science results.

Official marks are calculated here from stored whole-number scores.
A language model must not calculate or replace these results.

Rounding rule:
CAT, assignment, and external raw scores are stored as whole numbers.
Each pair score is (CAT × 0.70) + (Assignment × 0.30), kept exact.
The internal mark is the mean of the three pair scores.
The displayed internal mark is that mean rounded half up to one decimal place.
The external mark out of 50 is the raw mark out of 100 multiplied by 0.50,
then rounded half up to one decimal place. A raw score of 80 becomes 40.0.
The final mark is the displayed internal mark plus the displayed external mark.
It is already one decimal place and is capped at 100.0.
The grade uses that final mark, with no further rounding to a whole number:
below 50 is F, 50 up to but not including 60 is B, 60 to 70 is B+,
70 to 80 is A, 80 to 90 is A+, and 90 to 100 is O.
A missing score stays missing. It is not treated as zero.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculations import guidance_label
from app.models import ExternalExamination, InternalAssessment, Subject

DEPARTMENT = "Computer Science"
SEMESTER = "Semester 1"
SEMESTER_RESULT_DATE = date(2026, 6, 20)
ONE_PLACE = Decimal("0.1")
COMPONENT_MAXIMUM = 50
EXTERNAL_RAW_MAXIMUM = 100

ACTIVE_SUBJECTS = (
    ("DSA", "Data Structures and Algorithms"),
    ("DBMS", "Database Management Systems"),
    ("DS", "Data Science"),
    ("AIML", "Artificial Intelligence and Machine Learning"),
    ("CN", "Computer Networks"),
)
ACTIVE_SUBJECT_CODES = {code for code, _name in ACTIVE_SUBJECTS}
RETIRED_SUBJECT_CODES = ("MATH", "SCI", "ENG")
INTERNAL_FIELDS = (
    "cat_1",
    "assignment_1",
    "cat_2",
    "assignment_2",
    "cat_3",
    "assignment_3",
)

ROUNDING_RULE = (
    "Pair score = (CAT × 0.70) + (Assignment × 0.30). "
    "Internal mark out of 50 = (pair 1 + pair 2 + pair 3) / 3, "
    "rounded half up to one decimal place. "
    "External mark out of 50 = raw mark out of 100 × 0.50, "
    "rounded half up to one decimal place. "
    "Final mark out of 100 = internal mark + external mark. "
    "Grades use that final mark: F below 50, B from 50, B+ from 60, "
    "A from 70, A+ from 80, and O from 90. "
    "A missing score stays incomplete and is not treated as zero."
)


def quantize_mark(value: Decimal) -> Decimal:
    """Round a calculated mark half up to one decimal place."""
    return value.quantize(ONE_PLACE, rounding=ROUND_HALF_UP)


def format_mark(value: Decimal | None) -> str | None:
    """Show a calculated mark with one decimal place."""
    if value is None:
        return None
    return format(quantize_mark(value), "f")


def _pair(cat: int, assignment: int) -> Decimal:
    return Decimal(cat) * Decimal("0.70") + Decimal(assignment) * Decimal("0.30")


def internal_mark(
    cat_1: int | None,
    assignment_1: int | None,
    cat_2: int | None,
    assignment_2: int | None,
    cat_3: int | None,
    assignment_3: int | None,
) -> Decimal | None:
    """Return the displayed internal mark out of 50, or None when any score is missing."""
    scores = (cat_1, assignment_1, cat_2, assignment_2, cat_3, assignment_3)
    if any(score is None for score in scores):
        return None
    pairs = (
        _pair(cat_1, assignment_1),
        _pair(cat_2, assignment_2),
        _pair(cat_3, assignment_3),
    )
    exact = sum(pairs, Decimal("0")) / Decimal(3)
    return quantize_mark(exact)


def external_mark(raw_mark: int | None) -> Decimal | None:
    """Convert an external raw mark out of 100 into a mark out of 50."""
    if raw_mark is None:
        return None
    return quantize_mark(Decimal(raw_mark) * Decimal("0.50"))


def final_mark(internal: Decimal | None, external: Decimal | None) -> Decimal | None:
    """Add the two displayed marks out of 50. The result cannot exceed 100."""
    if internal is None or external is None:
        return None
    total = quantize_mark(internal + external)
    if total > Decimal("100.0"):
        return Decimal("100.0")
    return total


def grade_for(mark: Decimal | None) -> tuple[str | None, str]:
    """Return the grade and pass, fail, or incomplete for a final mark."""
    if mark is None:
        return None, "incomplete"
    if mark < Decimal("50"):
        return "F", "fail"
    if mark < Decimal("60"):
        return "B", "pass"
    if mark < Decimal("70"):
        return "B+", "pass"
    if mark < Decimal("80"):
        return "A", "pass"
    if mark < Decimal("90"):
        return "A+", "pass"
    return "O", "pass"


def ordered_active_subjects(session: Session) -> list[Subject]:
    """Return the current subjects, with the five Semester 1 subjects first."""
    rows = session.scalars(select(Subject).where(Subject.is_active.is_(True))).all()
    rank = {code: index for index, (code, _name) in enumerate(ACTIVE_SUBJECTS)}
    return sorted(rows, key=lambda row: (rank.get(row.code, len(rank)), row.code))


def _components(row: InternalAssessment | None) -> dict[str, int | None]:
    if row is None:
        return {name: None for name in INTERNAL_FIELDS}
    return {name: getattr(row, name) for name in INTERNAL_FIELDS}


def assess_subject(
    subject_id: int,
    code: str,
    name: str,
    components: dict[str, int | None],
    external_raw: int | None,
) -> dict:
    """Calculate one subject's official Semester 1 result from raw scores."""
    scores = {field: components.get(field) for field in INTERNAL_FIELDS}
    internal = internal_mark(
        scores["cat_1"],
        scores["assignment_1"],
        scores["cat_2"],
        scores["assignment_2"],
        scores["cat_3"],
        scores["assignment_3"],
    )
    converted = external_mark(external_raw)
    overall = final_mark(internal, converted)
    grade, status = grade_for(overall)
    internal_status = "complete" if internal is not None else "incomplete"
    external_status = "complete" if external_raw is not None else "incomplete"
    guidance = "not_available" if overall is None else guidance_label(overall)
    return {
        "subject_id": subject_id,
        "subject_code": code,
        "subject_name": name,
        "held_on": SEMESTER_RESULT_DATE,
        "cat_1": scores["cat_1"],
        "assignment_1": scores["assignment_1"],
        "cat_2": scores["cat_2"],
        "assignment_2": scores["assignment_2"],
        "cat_3": scores["cat_3"],
        "assignment_3": scores["assignment_3"],
        "external_raw": external_raw,
        "internal_mark": internal,
        "external_mark": converted,
        "final_mark": overall,
        "percentage": overall,
        "grade": grade,
        "official_status": status,
        "guidance_label": guidance,
        "internal_status": internal_status,
        "external_status": external_status,
        "assessment_status": "complete" if status != "incomplete" else "incomplete",
    }


def academic_report(session: Session, student_id: int) -> dict:
    """Build the three official tables for the active subjects."""
    subjects = ordered_active_subjects(session)
    subject_ids = [subject.id for subject in subjects]
    internals = {}
    externals = {}
    if subject_ids:
        internal_rows = session.scalars(
            select(InternalAssessment).where(
                InternalAssessment.student_id == student_id,
                InternalAssessment.subject_id.in_(subject_ids),
            )
        ).all()
        external_rows = session.scalars(
            select(ExternalExamination).where(
                ExternalExamination.student_id == student_id,
                ExternalExamination.subject_id.in_(subject_ids),
            )
        ).all()
        internals = {row.subject_id: row for row in internal_rows}
        externals = {row.subject_id: row for row in external_rows}

    assessed = [
        assess_subject(
            subject.id,
            subject.code,
            subject.name,
            _components(internals.get(subject.id)),
            None if externals.get(subject.id) is None else externals[subject.id].raw_mark,
        )
        for subject in subjects
    ]
    return {
        "department": DEPARTMENT,
        "semester": SEMESTER,
        "rounding_rule": ROUNDING_RULE,
        "subjects": assessed,
        "internal_assessments": [_internal_view(row) for row in assessed],
        "external_examinations": [_external_view(row) for row in assessed],
        "final_results": [_final_view(row) for row in assessed],
    }


def _internal_view(row: dict) -> dict:
    return {
        "subject_id": row["subject_id"],
        "subject_code": row["subject_code"],
        "subject_name": row["subject_name"],
        "cat_1": row["cat_1"],
        "assignment_1": row["assignment_1"],
        "cat_2": row["cat_2"],
        "assignment_2": row["assignment_2"],
        "cat_3": row["cat_3"],
        "assignment_3": row["assignment_3"],
        "internal_mark": format_mark(row["internal_mark"]),
        "assessment_status": row["internal_status"],
    }


def _external_view(row: dict) -> dict:
    return {
        "subject_id": row["subject_id"],
        "subject_code": row["subject_code"],
        "subject_name": row["subject_name"],
        "external_raw": row["external_raw"],
        "external_mark": format_mark(row["external_mark"]),
        "assessment_status": row["external_status"],
    }


def _final_view(row: dict) -> dict:
    return {
        "subject_id": row["subject_id"],
        "subject_code": row["subject_code"],
        "subject_name": row["subject_name"],
        "internal_mark": format_mark(row["internal_mark"]),
        "external_mark": format_mark(row["external_mark"]),
        "final_mark": format_mark(row["final_mark"]),
        "grade": row["grade"],
        "official_status": row["official_status"],
    }


def performance_counts(session: Session) -> dict[str, int]:
    """Count official pass, fail, and incomplete subject results."""
    from app.models import Student

    counts = {"pass": 0, "fail": 0, "incomplete": 0}
    for student_id in session.scalars(select(Student.id)).all():
        for row in academic_report(session, student_id)["final_results"]:
            counts[row["official_status"]] += 1
    return counts
