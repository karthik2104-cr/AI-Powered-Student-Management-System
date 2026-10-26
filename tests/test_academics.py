"""Semester 1 internal, external, and grade calculations.

These tests do not need PostgreSQL. They check the formula directly.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.academics import (
    ACTIVE_SUBJECTS,
    assess_subject,
    external_mark,
    final_mark,
    grade_for,
    internal_mark,
)
from app.schemas import ExternalExaminationWrite, InternalAssessmentWrite


def test_the_worked_example_is_40_point_5_plus_40():
    internal = internal_mark(40, 45, 35, 40, 45, 40)
    converted = external_mark(80)
    overall = final_mark(internal, converted)
    grade, status = grade_for(overall)
    assert internal == Decimal("40.5")
    assert converted == Decimal("40.0")
    assert overall == Decimal("80.5")
    assert grade == "A+"
    assert status == "pass"


def test_pair_scores_are_not_rounded_before_the_average():
    internal = internal_mark(40, 45, 35, 40, 44, 42)
    assert internal == Decimal("40.5")


def test_external_conversion_uses_half_of_the_raw_mark():
    assert external_mark(0) == Decimal("0.0")
    assert external_mark(80) == Decimal("40.0")
    assert external_mark(100) == Decimal("50.0")


def test_grade_boundaries_use_the_displayed_final_mark():
    assert grade_for(Decimal("49.9")) == ("F", "fail")
    assert grade_for(Decimal("50.0")) == ("B", "pass")
    assert grade_for(Decimal("59.9")) == ("B", "pass")
    assert grade_for(Decimal("60.0")) == ("B+", "pass")
    assert grade_for(Decimal("70.0")) == ("A", "pass")
    assert grade_for(Decimal("80.0")) == ("A+", "pass")
    assert grade_for(Decimal("89.9")) == ("A+", "pass")
    assert grade_for(Decimal("90.0")) == ("O", "pass")
    assert grade_for(Decimal("100.0")) == ("O", "pass")


def test_a_missing_score_stays_incomplete_and_zero_is_a_real_score():
    missing = assess_subject(1, "DSA", "Data Structures and Algorithms", {
        "cat_1": 40,
        "assignment_1": 45,
        "cat_2": 35,
        "assignment_2": 40,
        "cat_3": 45,
        "assignment_3": None,
    }, 80)
    assert missing["internal_mark"] is None
    assert missing["final_mark"] is None
    assert missing["grade"] is None
    assert missing["official_status"] == "incomplete"
    assert missing["internal_mark"] != Decimal("0")

    zero = assess_subject(1, "DSA", "Data Structures and Algorithms", {
        "cat_1": 0,
        "assignment_1": 0,
        "cat_2": 0,
        "assignment_2": 0,
        "cat_3": 0,
        "assignment_3": 0,
    }, 0)
    assert zero["internal_mark"] == Decimal("0.0")
    assert zero["external_mark"] == Decimal("0.0")
    assert zero["final_mark"] == Decimal("0.0")
    assert zero["grade"] == "F"
    assert zero["official_status"] == "fail"


def test_composed_boundary_scores_follow_the_same_grade_scale():
    just_below = assess_subject(1, "DS", "Data Science", {
        "cat_1": 30, "assignment_1": 13,
        "cat_2": 30, "assignment_2": 13,
        "cat_3": 30, "assignment_3": 13,
    }, 50)
    assert just_below["internal_mark"] == Decimal("24.9")
    assert just_below["external_mark"] == Decimal("25.0")
    assert just_below["final_mark"] == Decimal("49.9")
    assert just_below["grade"] == "F"

    passing = assess_subject(1, "DS", "Data Science", {
        "cat_1": 25, "assignment_1": 25,
        "cat_2": 25, "assignment_2": 25,
        "cat_3": 25, "assignment_3": 25,
    }, 50)
    assert passing["final_mark"] == Decimal("50.0")
    assert passing["grade"] == "B"


def test_component_inputs_must_be_whole_numbers_inside_the_maximum():
    InternalAssessmentWrite(subject_id=1, cat_1=0, assignment_1=50, cat_2=None)
    ExternalExaminationWrite(subject_id=1, raw_mark=0)
    ExternalExaminationWrite(subject_id=1, raw_mark=100)
    with pytest.raises(ValidationError):
        InternalAssessmentWrite(subject_id=1, cat_1=51)
    with pytest.raises(ValidationError):
        InternalAssessmentWrite(subject_id=1, assignment_1=-1)
    with pytest.raises(ValidationError):
        InternalAssessmentWrite(subject_id=1, cat_2=40.5)
    with pytest.raises(ValidationError):
        ExternalExaminationWrite(subject_id=1, raw_mark=101)
    with pytest.raises(ValidationError):
        ExternalExaminationWrite(subject_id=1, raw_mark=80.5)


def test_there_are_five_semester_1_subjects():
    assert [code for code, _name in ACTIVE_SUBJECTS] == ["DSA", "DBMS", "DS", "AIML", "CN"]
