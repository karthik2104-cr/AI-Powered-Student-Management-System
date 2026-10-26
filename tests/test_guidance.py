"""Tests for support selection and the rule-based study outline."""

from datetime import date

from app.calculations import build_results, ScoreInput
from app.guidance import build_study_outline, select_resources, subjects_needing_support


def score(**overrides):
    values = {
        "student_id": 1,
        "subject_id": 1,
        "subject_code": "MATH",
        "subject_name": "Mathematics",
        "examination_id": 1,
        "examination_name": "Final Examination",
        "exam_type": "final",
        "held_on": date(2026, 6, 20),
        "marks_obtained": "80",
        "maximum_marks": "100",
        "pass_marks": "40",
        "mark_id": 1,
    }
    values.update(overrides)
    return ScoreInput(**values)


def test_latest_pass_hides_an_older_failure():
    results = build_results([
        score(examination_id=1, examination_name="Midterm Examination", held_on=date(2026, 3, 15), marks_obtained="30", mark_id=1),
        score(examination_id=2, examination_name="Final Examination", held_on=date(2026, 6, 20), marks_obtained="80", mark_id=2),
    ])
    assert subjects_needing_support(results) == []


def test_fail_and_low_unassessed_score_need_support():
    results = build_results([
        score(subject_id=2, subject_code="DBMS", subject_name="Database Management", marks_obtained="22", maximum_marks="50", pass_marks="25"),
        score(subject_id=3, subject_code="ENG", subject_name="English", marks_obtained="40", pass_marks=None),
        score(subject_id=4, subject_code="SCI", subject_name="Science", marks_obtained="90", pass_marks=None),
    ])
    names = [item["subject_name"] for item in subjects_needing_support(results)]
    assert names == ["Database Management", "English"]


def test_resources_follow_subjects_that_need_support():
    results = build_results([
        score(subject_id=4, subject_code="DBMS", subject_name="Database Management", marks_obtained="20", pass_marks="40"),
        score(subject_id=1, subject_name="Mathematics", marks_obtained="90", pass_marks="40"),
    ])
    resources = [
        {"subject_id": 4, "subject_name": "Database Management", "title": "PostgreSQL Tutorial"},
        {"subject_id": 1, "subject_name": "Mathematics", "title": "College Algebra 2e"},
    ]
    selected = select_resources(resources, results)
    assert [item["title"] for item in selected] == ["PostgreSQL Tutorial"]


def test_outline_uses_reported_topic_without_judging_the_student():
    results = build_results([
        score(subject_id=4, subject_code="DBMS", subject_name="Database Management", marks_obtained="20", pass_marks="40"),
    ])
    feedback = [{
        "subject_id": 4,
        "topic": "SELECT queries",
        "preferred_format": "videos",
    }]
    outline = build_study_outline(results, feedback)
    assert outline["items"][0]["day"] == "Monday"
    assert "SELECT queries" in outline["items"][0]["activity"]
    assert "videos" in outline["items"][0]["activity"]
    assert "lazy" not in outline["items"][0]["activity"]
    assert "not an official academic decision" in outline["note"]
