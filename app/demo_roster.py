"""Additional fictional students for the local demonstration database.

These names and addresses are made up. They are separate from the three
original demonstration records. Scores are examples for the portal, not
official results for real people.
"""

from datetime import date, datetime, timedelta, timezone

REGISTERED_ON = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
ATTENDANCE_DATES = (
    date(2026, 9, 1),
    date(2026, 9, 8),
    date(2026, 9, 15),
)

# Midterm and final scores out of 100. The pass mark for these rows is 40.
PROFILES = {
    "strong": {"MATH": (86, 92), "SCI": (84, 88), "ENG": (90, 93), "DBMS": (81, 85)},
    "weak_dbms": {"MATH": (72, 76), "SCI": (70, 74), "ENG": (78, 80), "DBMS": (30, 34)},
    "good_marks": {"MATH": (88, 91), "SCI": (85, 89), "ENG": (87, 90), "DBMS": (82, 86)},
    "open_concerns": {"MATH": (48, 52), "SCI": (44, 49), "ENG": (70, 73), "DBMS": (58, 61)},
    "resolved": {"MATH": (63, 78), "SCI": (66, 74), "ENG": (71, 84), "DBMS": (60, 77)},
    "developing": {"MATH": (55, 62), "SCI": (58, 64), "ENG": (70, 74), "DBMS": (60, 66)},
    "weak_science": {"MATH": (74, 78), "SCI": (32, 41), "ENG": (80, 84), "DBMS": (70, 73)},
    "mixed": {"MATH": (64, 71), "SCI": (48, 58), "ENG": (77, 81), "DBMS": (55, 63)},
    "weak_math": {"MATH": (36, 44), "SCI": (75, 79), "ENG": (88, 92), "DBMS": (68, 71)},
    "needs_attention": {"MATH": (42, 39), "SCI": (35, 44), "ENG": (60, 58), "DBMS": (28, 31)},
}

EXTRA_STUDENTS = (
    {"admission_number": "STU-001", "full_name": "Meera Iyer", "email": "meera.iyer@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "strong", "attendance": "present"},
    {"admission_number": "STU-002", "full_name": "Arjun Desai", "email": "arjun.desai@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "weak_dbms", "attendance": "present"},
    {"admission_number": "STU-003", "full_name": "Laila Rahman", "email": "laila.rahman@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "good_marks", "attendance": "low"},
    {"admission_number": "STU-004", "full_name": "Kabir Menon", "email": "kabir.menon@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "open_concerns", "attendance": "mixed"},
    {"admission_number": "STU-005", "full_name": "Sofia Almeida", "email": "sofia.almeida@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "resolved", "attendance": "present"},
    {"admission_number": "STU-006", "full_name": "Rohan Patel", "email": "rohan.patel@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "developing", "attendance": "present"},
    {"admission_number": "STU-007", "full_name": "Ananya Shah", "email": "ananya.shah@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "weak_science", "attendance": "present"},
    {"admission_number": "STU-008", "full_name": "Daniel Okonkwo", "email": "daniel.okonkwo@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "mixed", "attendance": "mixed"},
    {"admission_number": "STU-009", "full_name": "Priya Nair", "email": "priya.nair@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "weak_math", "attendance": "present"},
    {"admission_number": "STU-010", "full_name": "Hassan Ali", "email": "hassan.ali@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "developing", "attendance": "present"},
    {"admission_number": "STU-011", "full_name": "Elena Petrova", "email": "elena.petrova@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "resolved", "attendance": "present"},
    {"admission_number": "STU-012", "full_name": "Vikram Rao", "email": "vikram.rao@example.edu", "department": "Computer Science", "year_or_semester": "Semester 1", "profile": "needs_attention", "attendance": "low"},
)

EXTRA_CONCERNS = (
    {
        "seed_key": "demo-stu002-select",
        "admission_number": "STU-002",
        "subject_code": "DBMS",
        "topic": "SELECT queries",
        "description": "I mix up which table a column comes from when two tables are listed.",
        "concept": "choosing columns in a SELECT statement",
        "assistance_type": "explanation",
        "preferred_format": "examples",
        "priority": "normal",
        "status": "under_review",
        "response": "The office will review the stored SQL lesson with this student.",
        "resource_url": None,
    },
    {
        "seed_key": "demo-stu004-fractions",
        "admission_number": "STU-004",
        "subject_code": "DSA",
        "topic": "arrays",
        "description": "I cannot tell which index belongs to which value when an array is written in a problem.",
        "concept": "array indexes",
        "assistance_type": "explanation",
        "preferred_format": "examples",
        "priority": "high",
        "status": "submitted",
        "response": None,
        "resource_url": None,
    },
    {
        "seed_key": "demo-stu004-cells",
        "admission_number": "STU-004",
        "subject_code": "DS",
        "topic": "datasets",
        "description": "The difference between a sample and the full dataset is still unclear.",
        "concept": "samples and datasets",
        "assistance_type": "resources",
        "preferred_format": "books",
        "priority": "normal",
        "status": "submitted",
        "response": None,
        "resource_url": None,
    },
    {
        "seed_key": "demo-stu005-grammar",
        "admission_number": "STU-005",
        "subject_code": "CN",
        "topic": "IP addressing",
        "description": "I lose track of which part of an IP address identifies the network.",
        "concept": "network and host portions",
        "assistance_type": "resources",
        "preferred_format": "examples",
        "priority": "normal",
        "status": "resolved",
        "response": "Reviewed the stored grammar page and completed two example sentences.",
        "resource_url": "https://en.wikipedia.org/wiki/Computer_network",
    },
    {
        "seed_key": "demo-stu010-joins",
        "admission_number": "STU-010",
        "subject_code": "DBMS",
        "topic": "joins",
        "description": "I do not yet know when a join leaves a row out.",
        "concept": "matching rows between two tables",
        "assistance_type": "practice",
        "preferred_format": "exercises",
        "priority": "normal",
        "status": "submitted",
        "response": None,
        "resource_url": None,
    },
    {
        "seed_key": "demo-stu011-algebra",
        "admission_number": "STU-011",
        "subject_code": "DSA",
        "topic": "recursion",
        "description": "Tracing a recursive call still takes me too long.",
        "concept": "a function calling itself",
        "assistance_type": "resources",
        "preferred_format": "books",
        "priority": "low",
        "status": "resolved",
        "response": "The stored algebra book was recommended and the concern was closed.",
        "resource_url": "https://en.wikipedia.org/wiki/Data_structure",
    },
    {
        "seed_key": "demo-stu012-percent",
        "admission_number": "STU-012",
        "subject_code": "DS",
        "topic": "summary statistics",
        "description": "The difference between a mean and a median is confusing.",
        "concept": "mean and median",
        "assistance_type": "practice",
        "preferred_format": "exercises",
        "priority": "high",
        "status": "in_progress",
        "response": "Practice problems were assigned. This concern is still open.",
        "resource_url": None,
    },
    {
        "seed_key": "demo-stu012-science",
        "admission_number": "STU-012",
        "subject_code": "AIML",
        "topic": "training and testing",
        "description": "I cannot tell a training example apart from a test example.",
        "concept": "training data and test data",
        "assistance_type": "resources",
        "preferred_format": "videos",
        "priority": "normal",
        "status": "resources_recommended",
        "response": "The stored science course page was recommended.",
        "resource_url": "https://www.youtube.com/watch?v=aircAruvnKk",
    },
)

STUDY_PLAN_ADMISSIONS = ("STU-002", "STU-004", "STU-012")

VERIFIED_VIDEOS = (
    {
        "subject_code": "DSA",
        "title": "Vectors | Chapter 1, Essence of linear algebra",
        "resource_type": "video",
        "author": "3Blue1Brown",
        "topic": "linear algebra",
        "url": "https://www.youtube.com/watch?v=fNk_zzaMoSs",
        "description": "YouTube oEmbed returned this title and channel on 2026-10-26. The watch page returned HTTP 200.",
    },
    {
        "subject_code": "MATH",
        "title": "The essence of calculus",
        "resource_type": "video",
        "author": "3Blue1Brown",
        "topic": "calculus",
        "url": "https://www.youtube.com/watch?v=WUvTyaaNkzM",
        "description": "YouTube oEmbed returned this title and channel on 2026-10-26. The watch page returned HTTP 200.",
    },
    {
        "subject_code": "AIML",
        "title": "But what is a neural network? | Deep learning chapter 1",
        "resource_type": "video",
        "author": "3Blue1Brown",
        "topic": "models",
        "url": "https://www.youtube.com/watch?v=aircAruvnKk",
        "description": "YouTube oEmbed returned this title and channel on 2026-10-26. The watch page returned HTTP 200.",
    },
)


def extra_marks() -> list[dict]:
    """Build one midterm and one final for every subject in a student's profile."""
    rows = []
    for student in EXTRA_STUDENTS:
        scores = PROFILES[student["profile"]]
        for subject_code, (midterm, final) in scores.items():
            rows.append(_score(student["admission_number"], subject_code, "FAT", date(2026, 3, 15), midterm))
            rows.append(_score(student["admission_number"], subject_code, "End Semester Examination", date(2026, 6, 20), final))
    return rows


def extra_attendance() -> list[dict]:
    """Three September sessions. A low pattern is mostly absent; the others are mostly present."""
    rows = []
    for student in EXTRA_STUDENTS:
        pattern = _attendance_pattern(student["attendance"])
        for subject_code in ("DSA", "DBMS"):
            for session_date, status in zip(ATTENDANCE_DATES, pattern):
                rows.append({
                    "admission_number": student["admission_number"],
                    "subject_code": subject_code,
                    "session_date": session_date,
                    "status": status,
                })
    return rows


def login_specs() -> list[dict]:
    """Demo students that should receive a login when they do not already have one."""
    specs = []
    for index, student in enumerate(EXTRA_STUDENTS):
        specs.append({
            "admission_number": student["admission_number"],
            "registered_at": REGISTERED_ON + timedelta(days=index),
        })
    original = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    for admission_number in ("ADM-1001", "ADM-1002", "ADM-1003"):
        specs.append({"admission_number": admission_number, "registered_at": original})
    return specs


def _score(admission_number: str, subject_code: str, examination_name: str, held_on: date, obtained: int) -> dict:
    return {
        "admission_number": admission_number,
        "subject_code": subject_code,
        "examination_name": examination_name,
        "held_on": held_on,
        "marks_obtained": str(obtained),
        "maximum_marks": "100",
        "pass_marks": "40",
    }


def _component_scores(cat_1, assignment_1, cat_2, assignment_2, cat_3, assignment_3, external_raw):
    """Raw demo scores. None means that component has not been recorded."""
    return {
        "cat_1": cat_1,
        "assignment_1": assignment_1,
        "cat_2": cat_2,
        "assignment_2": assignment_2,
        "cat_3": cat_3,
        "assignment_3": assignment_3,
        "external_raw": external_raw,
    }


_EXAMPLE_SCORES = _component_scores(40, 45, 35, 40, 45, 40, 80)
_HIGH_SCORES = _component_scores(45, 45, 45, 45, 45, 45, 90)
_FAIL_SCORES = _component_scores(20, 20, 20, 20, 20, 20, 40)
_PASS_SCORES = _component_scores(30, 30, 30, 30, 30, 30, 50)
_MISSING_EXTERNAL = _component_scores(40, 45, 35, 40, 45, 40, None)
_MISSING_ASSIGNMENT = _component_scores(40, 45, 35, 40, 45, None, 80)
_ASSESSMENT_SUBJECTS = ("DSA", "DBMS", "DS", "AIML", "CN")
_PROFILE_ASSESSMENTS = {
    "strong": {"default": _HIGH_SCORES},
    "weak_dbms": {"default": _EXAMPLE_SCORES, "DBMS": _FAIL_SCORES},
    "good_marks": {"default": _HIGH_SCORES},
    "open_concerns": {"default": _PASS_SCORES, "DSA": _FAIL_SCORES},
    "resolved": {"default": _EXAMPLE_SCORES},
    "developing": {"default": _PASS_SCORES},
    "weak_science": {"default": _HIGH_SCORES, "DS": _FAIL_SCORES},
    "mixed": {"default": _PASS_SCORES, "CN": _FAIL_SCORES, "DSA": _EXAMPLE_SCORES},
    "weak_math": {"default": _EXAMPLE_SCORES, "DSA": _FAIL_SCORES},
    "needs_attention": {"default": _FAIL_SCORES, "DS": _MISSING_ASSIGNMENT, "AIML": _PASS_SCORES},
}
_ORIGINAL_ASSESSMENTS = {
    "ADM-1001": {"default": _EXAMPLE_SCORES, "DBMS": _FAIL_SCORES, "CN": _MISSING_EXTERNAL},
    "ADM-1002": {"default": _PASS_SCORES, "DSA": _EXAMPLE_SCORES},
    "ADM-1003": {"default": _HIGH_SCORES, "DS": _MISSING_ASSIGNMENT},
}


def demo_assessments() -> list[dict]:
    """Fictional Semester 1 scores for the demo students. Missing values stay missing."""
    rows = []

    def add(admission_number: str, plan: dict) -> None:
        for code in _ASSESSMENT_SUBJECTS:
            scores = plan.get(code, plan["default"])
            rows.append({"admission_number": admission_number, "subject_code": code, **scores})

    for admission_number, plan in _ORIGINAL_ASSESSMENTS.items():
        add(admission_number, plan)
    for student in EXTRA_STUDENTS:
        add(student["admission_number"], _PROFILE_ASSESSMENTS[student["profile"]])
    return rows


def _attendance_pattern(kind: str) -> tuple[str, str, str]:
    if kind == "low":
        return ("absent", "absent", "present")
    if kind == "mixed":
        return ("present", "absent", "present")
    return ("present", "present", "present")
