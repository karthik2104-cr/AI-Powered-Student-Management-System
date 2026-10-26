"""Tests for official calculations. These do not connect to PostgreSQL."""

from datetime import date
from decimal import Decimal

import pytest

from app.calculations import (
    DEVELOPING,
    DECLINED,
    FAIL,
    IMPROVED,
    NEEDS_ATTENTION,
    NOT_ASSESSED,
    PASS,
    STRONG,
    UNCHANGED,
    ScoreInput,
    build_results,
    official_status,
    percentage,
    validate_mark_values,
)
from app.models import Mark
from app.schemas import AcademicResult
from app.seed import (
    DEMO_EXAMINATIONS,
    DEMO_MARKS,
    DEMO_STUDENTS,
    DEMO_SUBJECTS,
    validate_demo_data,
)


def make_score(**overrides) -> ScoreInput:
    values = {
        "student_id": 1,
        "subject_id": 1,
        "subject_code": "MATH",
        "subject_name": "Mathematics",
        "examination_id": 1,
        "examination_name": "End Semester Examination",
        "exam_type": "final",
        "held_on": date(2026, 6, 20),
        "marks_obtained": "50",
        "maximum_marks": "100",
        "pass_marks": "40",
    }
    values.update(overrides)
    return ScoreInput(**values)


def demo_scores() -> list[ScoreInput]:
    student_ids = {
        row["admission_number"]: index
        for index, row in enumerate(DEMO_STUDENTS, start=1)
    }
    subject_ids = {row["code"]: index for index, row in enumerate(DEMO_SUBJECTS, start=1)}
    subject_names = {row["code"]: row["name"] for row in DEMO_SUBJECTS}
    examinations = {}
    for index, exam in enumerate(DEMO_EXAMINATIONS, start=1):
        examinations[(exam["name"], exam["held_on"])] = (index, exam["exam_type"])

    scores = []
    for mark in DEMO_MARKS:
        exam_id, exam_type = examinations[(mark["examination_name"], mark["held_on"])]
        scores.append(
            ScoreInput(
                student_id=student_ids[mark["admission_number"]],
                subject_id=subject_ids[mark["subject_code"]],
                subject_code=mark["subject_code"],
                subject_name=subject_names[mark["subject_code"]],
                examination_id=exam_id,
                examination_name=mark["examination_name"],
                exam_type=exam_type,
                held_on=mark["held_on"],
                marks_obtained=mark["marks_obtained"],
                maximum_marks=mark["maximum_marks"],
                pass_marks=mark["pass_marks"],
            )
        )
    return scores


def one_result(results: list[dict], subject_code: str, examination_name: str) -> dict:
    found = [
        row
        for row in results
        if row["subject_code"] == subject_code and row["examination_name"] == examination_name
    ]
    assert len(found) == 1
    return found[0]


def results_for(admission_number: str) -> list[dict]:
    student_id = next(
        index
        for index, row in enumerate(DEMO_STUDENTS, start=1)
        if row["admission_number"] == admission_number
    )
    return build_results(
        [score for score in demo_scores() if score.student_id == student_id]
    )


def test_demo_data_follows_the_mark_rules():
    validate_demo_data()
    assert len(DEMO_MARKS) == 20


def test_percentage_is_rounded_half_up():
    assert percentage(Decimal("1"), Decimal("6")) == Decimal("16.67")
    assert percentage(Decimal("2"), Decimal("3")) == Decimal("66.67")
    assert percentage(Decimal("28"), Decimal("50")) == Decimal("56.00")


def test_official_status_uses_the_pass_mark_only():
    assert official_status(Decimal("39.00"), Decimal("40.00")) == FAIL
    assert official_status(Decimal("40.00"), Decimal("40.00")) == PASS
    assert official_status(Decimal("10.00"), None) == NOT_ASSESSED
    assert official_status(Decimal("0.00"), None) == NOT_ASSESSED


def test_invalid_marks_are_rejected():
    with pytest.raises(ValueError, match="greater than zero"):
        validate_mark_values("10", "0", "5")
    with pytest.raises(ValueError, match="cannot be greater than maximum_marks"):
        validate_mark_values("11", "10", "5")
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_mark_values("-1", "10", "5")
    with pytest.raises(ValueError, match="pass_marks cannot be greater"):
        validate_mark_values("8", "10", "11")


def test_guidance_boundaries_are_separate_from_pass_and_fail():
    strong = build_results([make_score(marks_obtained="75", pass_marks="40")])[0]
    developing = build_results([make_score(marks_obtained="74.99", pass_marks="40")])[0]
    exactly_50 = build_results([make_score(marks_obtained="50", pass_marks="40")])[0]
    low_pass = build_results([make_score(marks_obtained="40", pass_marks="30")])[0]
    low_fail = build_results([make_score(marks_obtained="49.99", pass_marks="50")])[0]
    missing = build_results([make_score(marks_obtained="10", pass_marks=None)])[0]

    assert strong["guidance_label"] == STRONG
    assert strong["official_status"] == PASS
    assert developing["percentage"] == Decimal("74.99")
    assert developing["guidance_label"] == DEVELOPING
    assert exactly_50["guidance_label"] == DEVELOPING
    assert low_pass["official_status"] == PASS
    assert low_pass["guidance_label"] == NEEDS_ATTENTION
    assert "official result is pass" in low_pass["explanation"]
    assert "not an official result" in low_pass["explanation"]
    assert low_fail["official_status"] == FAIL
    assert low_fail["guidance_label"] == NEEDS_ATTENTION
    assert missing["official_status"] == NOT_ASSESSED
    assert missing["guidance_label"] == NEEDS_ATTENTION
    assert "official result is fail" not in missing["explanation"]
    assert "not assessed as pass or fail" in missing["explanation"]


def test_history_uses_the_immediately_previous_result_only():
    scores = [
        make_score(
            examination_id=1,
            examination_name="January Test",
            held_on=date(2026, 1, 10),
            marks_obtained="40",
        ),
        make_score(
            examination_id=2,
            examination_name="February Test",
            held_on=date(2026, 2, 10),
            marks_obtained="50",
        ),
        make_score(
            examination_id=3,
            examination_name="March Test",
            held_on=date(2026, 3, 10),
            marks_obtained="80",
        ),
    ]
    march = build_results(scores)[-1]
    assert march["previous_result"]["examination_name"] == "February Test"
    assert march["previous_result"]["percentage"] == Decimal("50.00")
    assert march["previous_result"]["direction"] == IMPROVED
    assert march["previous_result"]["percentage_change"] == Decimal("30.00")


def test_same_date_results_are_not_compared():
    scores = [
        make_score(
            examination_id=1,
            examination_name="Quiz A",
            held_on=date(2026, 1, 10),
            marks_obtained="40",
        ),
        make_score(
            examination_id=2,
            examination_name="Quiz B",
            held_on=date(2026, 1, 10),
            marks_obtained="80",
        ),
        make_score(
            examination_id=3,
            examination_name="February Test",
            held_on=date(2026, 2, 10),
            marks_obtained="60",
        ),
    ]
    february = one_result(build_results(scores), "MATH", "February Test")
    assert february["previous_result"] is None
    assert "same most recent date" in february["history_note"]


def test_different_subjects_are_not_compared():
    scores = [
        make_score(subject_id=1, subject_code="MATH", marks_obtained="40", examination_id=1, held_on=date(2026, 3, 15), examination_name="FAT"),
        make_score(subject_id=2, subject_code="SCI", subject_name="Science", marks_obtained="90", examination_id=1, held_on=date(2026, 3, 15), examination_name="FAT"),
        make_score(subject_id=2, subject_code="SCI", subject_name="Science", marks_obtained="70", examination_id=2, held_on=date(2026, 6, 20), examination_name="End Semester Examination"),
    ]
    final_science = one_result(build_results(scores), "SCI", "End Semester Examination")
    assert final_science["previous_result"]["percentage"] == Decimal("90.00")
    assert final_science["previous_result"]["direction"] == DECLINED


def test_synthetic_student_results_cover_the_required_cases():
    asha = results_for("ADM-1001")
    nila = results_for("ADM-1002")
    farhan = results_for("ADM-1003")

    math_final = one_result(asha, "MATH", "End Semester Examination")
    assert math_final["marks_obtained"] == Decimal("68.00")
    assert math_final["percentage"] == Decimal("68.00")
    assert math_final["official_status"] == PASS
    assert math_final["guidance_label"] == DEVELOPING
    assert math_final["previous_result"]["direction"] == IMPROVED
    assert math_final["previous_result"]["percentage_change"] == Decimal("30.00")
    assert "increased by 30.00 points" in math_final["history_note"]

    database_midterm = one_result(asha, "DBMS", "FAT")
    assert database_midterm["pass_marks"] is None
    assert database_midterm["percentage"] == Decimal("56.00")
    assert database_midterm["official_status"] == NOT_ASSESSED
    assert database_midterm["previous_result"] is None

    database_final = one_result(asha, "DBMS", "End Semester Examination")
    assert database_final["official_status"] == FAIL
    assert database_final["guidance_label"] == NEEDS_ATTENTION
    assert database_final["previous_result"]["official_status"] == NOT_ASSESSED
    assert database_final["previous_result"]["direction"] == DECLINED

    nila_math = one_result(nila, "MATH", "End Semester Examination")
    assert nila_math["percentage"] == Decimal("74.00")
    assert nila_math["guidance_label"] == DEVELOPING
    assert nila_math["previous_result"]["percentage"] == Decimal("75.00")
    assert nila_math["previous_result"]["direction"] == DECLINED

    nila_database = one_result(nila, "DBMS", "End Semester Examination")
    assert nila_database["official_status"] == PASS
    assert nila_database["guidance_label"] == NEEDS_ATTENTION
    assert nila_database["previous_result"] is None

    nila_english = one_result(nila, "ENG", "End Semester Examination")
    assert nila_english["previous_result"]["direction"] == UNCHANGED
    assert "did not change" in nila_english["history_note"]

    farhan_english_midterm = one_result(farhan, "ENG", "FAT")
    assert farhan_english_midterm["official_status"] == NOT_ASSESSED
    assert farhan_english_midterm["guidance_label"] == STRONG
    assert "official result is pass" not in farhan_english_midterm["explanation"]

    farhan_database = one_result(farhan, "DBMS", "End Semester Examination")
    assert farhan_database["official_status"] == FAIL
    assert farhan_database["previous_result"]["direction"] == UNCHANGED


def test_api_schema_keeps_two_decimal_strings():
    row = one_result(results_for("ADM-1001"), "MATH", "End Semester Examination")
    payload = AcademicResult.model_validate(row).model_dump(mode="json")
    assert payload["percentage"] == "68.00"
    assert payload["pass_marks"] == "40.00"
    assert payload["previous_result"]["percentage_change"] == "30.00"
    assert payload["held_on"] == "2026-06-20"

    missing = one_result(results_for("ADM-1001"), "DBMS", "FAT")
    missing_payload = AcademicResult.model_validate(missing).model_dump(mode="json")
    assert missing_payload["pass_marks"] is None


def test_aggregate_percentage_omits_missing_assessments():
    from decimal import Decimal

    from app.calculations import aggregate_percentage, attendance_percentage

    empty = aggregate_percentage([])
    assert empty["marks_counted"] == 0
    assert empty["percentage"] is None

    overall = aggregate_percentage(
        [
            {"marks_obtained": Decimal("20"), "maximum_marks": Decimal("50")},
            {"marks_obtained": Decimal("30"), "maximum_marks": Decimal("50")},
        ]
    )
    assert overall["percentage"] == Decimal("50.00")
    assert overall["marks_counted"] == 2
    assert attendance_percentage(0, 0) is None
    assert attendance_percentage(1, 2) == Decimal("50.00")


def test_percentage_is_not_a_database_column():
    column_names = {column.name for column in Mark.__table__.columns}
    assert "percentage" not in column_names
    assert {"marks_obtained", "maximum_marks", "pass_marks"} <= column_names
