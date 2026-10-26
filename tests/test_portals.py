"""Portal, persistence, and authorization tests against PostgreSQL."""

from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.main import app
from app.models import AuditLog, LearningResource, Mark, Student
from tests.support import login_admin, remove_test_admin


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def admin(client):
    health = client.get("/health")
    payload = health.json()
    if health.status_code != 200 or payload.get("academic_records") != "ready":
        pytest.skip(payload.get("academic_records_detail") or payload.get("detail"))
    login_admin(client)
    yield client
    client.post("/auth/logout")
    remove_test_admin()


def test_anonymous_academic_routes_require_sign_in(client):
    with TestClient(app) as anonymous:
        response = anonymous.get("/students")
        assert response.status_code == 401
        assert "postgresql+psycopg://" not in response.text


def test_demo_students_are_labeled(admin):
    students = admin.get("/students").json()
    asha = next(row for row in students if row["admission_number"] == "ADM-1001")
    assert asha["is_demo"] is True
    assert asha["department"] == "Computer Science"
    assert asha["year_or_semester"] == "Semester 1"


def test_student_changes_persist_in_a_new_session(admin):
    suffix = uuid4().hex[:8]
    admission = f"PY{suffix}"[:30]
    email = f"py-{suffix}@example.edu"
    created = admin.post("/students", json={
        "admission_number": admission,
        "full_name": "Persist Student",
        "email": email,
        "department": "Testing",
        "year_or_semester": "1",
    })
    assert created.status_code == 201
    student_id = created.json()["id"]
    assert created.json()["is_demo"] is False

    session = SessionLocal()
    try:
        stored = session.get(Student, student_id)
        assert stored is not None
        assert stored.full_name == "Persist Student"
        assert stored.email == email
    finally:
        session.close()

    updated = admin.put(f"/students/{student_id}", json={
        "admission_number": admission,
        "full_name": "Persist Updated",
        "email": email,
        "department": "Testing",
        "year_or_semester": "2",
    })
    assert updated.status_code == 200

    session = SessionLocal()
    try:
        stored = session.get(Student, student_id)
        assert stored.full_name == "Persist Updated"
        assert stored.department == "Computer Science"
        assert stored.year_or_semester == "Semester 1"
    finally:
        session.close()

    duplicate = admin.post("/students", json={
        "admission_number": admission,
        "full_name": "Other",
        "email": f"other-{suffix}@example.edu",
    })
    assert duplicate.status_code == 409

    subject = admin.post("/subjects", json={"code": f"T{suffix[:6]}".upper(), "name": "Portal Subject"})
    assert subject.status_code == 201
    subject_id = subject.json()["id"]
    examination_id = next(row["id"] for row in admin.get("/examinations").json() if row["exam_type"] == "fat")
    mark = admin.post("/marks", json={
        "student_id": student_id,
        "subject_id": subject_id,
        "examination_id": examination_id,
        "marks_obtained": "8",
        "maximum_marks": "10",
        "pass_marks": "5",
    })
    assert mark.status_code == 201
    mark_id = mark.json()["id"]

    session = SessionLocal()
    try:
        stored_mark = session.get(Mark, mark_id)
        assert stored_mark.student_id == student_id
        assert stored_mark.subject_id == subject_id
        assert stored_mark.examination_id == examination_id
        assert stored_mark.marks_obtained == Decimal("8.00")
    finally:
        session.close()

    changed = admin.put(f"/marks/{mark_id}", json={
        "student_id": student_id,
        "subject_id": subject_id,
        "examination_id": examination_id,
        "marks_obtained": "9",
        "maximum_marks": "10",
        "pass_marks": "5",
    })
    assert changed.status_code == 200
    session = SessionLocal()
    try:
        stored_mark = session.get(Mark, mark_id)
        assert stored_mark.marks_obtained == Decimal("9.00")
    finally:
        session.close()

    invalid = admin.post("/marks", json={
        "student_id": student_id,
        "subject_id": subject_id,
        "examination_id": examination_id,
        "marks_obtained": "11",
        "maximum_marks": "10",
    })
    assert invalid.status_code == 422

    assert admin.delete(f"/marks/{mark_id}").status_code == 204
    assert admin.delete(f"/subjects/{subject_id}").status_code == 204
    assert admin.delete(f"/students/{student_id}").status_code == 204

    session = SessionLocal()
    try:
        assert session.get(Student, student_id) is None
        assert session.get(Mark, mark_id) is None
    finally:
        session.close()


def test_a_failed_mark_does_not_leave_the_student_insert(admin):
    suffix = uuid4().hex[:8]
    admission = f"PYR{suffix}"[:30]
    session = SessionLocal()
    try:
        student = Student(
            admission_number=admission,
            full_name="Rollback Student",
            email=f"rollback-{suffix}@example.edu",
            is_active=True,
            is_demo=False,
        )
        session.add(student)
        session.flush()
        session.add(
            Mark(
                student_id=student.id,
                subject_id=1,
                examination_id=1,
                marks_obtained=Decimal("9.00"),
                maximum_marks=Decimal("4.00"),
                pass_marks=None,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
    finally:
        session.close()

    check = SessionLocal()
    try:
        found = check.scalar(select(Student).where(Student.admission_number == admission))
        assert found is None
    finally:
        check.close()


def test_registration_login_and_student_isolation(admin):
    suffix = uuid4().hex[:8]

    def register(letter: str):
        portal = TestClient(app)
        portal.__enter__()
        response = portal.post("/auth/register", json={
            "full_name": f"Student {letter}",
            "admission_number": f"REG{letter}{suffix}"[:30],
            "email": f"reg-{letter}-{suffix}@example.edu",
            "password": "student-pass-1",
            "password_confirmation": "student-pass-1",
            "department": "Science",
            "year_or_semester": "2",
            "role": "admin",
        })
        assert response.status_code == 201, response.text
        assert response.json()["role"] == "student"
        assert "password_hash" not in response.text
        signed_in = portal.post("/auth/login", json={
            "email": f"reg-{letter}-{suffix}@example.edu",
            "password": "student-pass-1",
            "portal": "student",
        })
        assert signed_in.status_code == 200, signed_in.text
        return portal, response.json()["student_id"]

    first, first_id = register("a")
    second, second_id = register("b")
    try:
        assert first.get(f"/students/{second_id}/results").status_code == 403
        assert first.get("/students").status_code == 403
        assert first.get(f"/me/concerns").status_code == 200
        own = first.get("/me/results")
        assert own.status_code == 200
        assert own.json()["student"]["id"] == first_id
        assert own.json()["aggregate"]["marks_counted"] == 0
        assert own.json()["aggregate"]["percentage"] is None

        with TestClient(app) as guest:
            mismatch = guest.post("/auth/register", json={
            "full_name": "Mismatch",
            "admission_number": f"REGM{suffix}"[:30],
            "email": f"mismatch-{suffix}@example.edu",
            "password": "student-pass-1",
            "password_confirmation": "different-pass",
            "department": "Science",
            "year_or_semester": "2",
            })
        assert mismatch.status_code == 422

        bad_login = first.post("/auth/login", json={
            "email": f"reg-a-{suffix}@example.edu",
            "password": "wrong-password",
        })
        assert bad_login.status_code == 401
        assert bad_login.json()["detail"] == "Email or password is incorrect."

        subjects = first.get("/me/subjects").json()
        subject_id = next(row["id"] for row in subjects if row["code"] == "DBMS")
        concern = first.post("/me/concerns", json={
            "subject_id": subject_id,
            "topic": "fractions",
            "description": "I cannot tell which number is the denominator.",
            "concept": "numerator and denominator",
            "assistance_type": "explanation",
            "preferred_format": "examples",
            "priority": "normal",
            "status": "resolved",
        })
        assert concern.status_code == 201
        assert concern.json()["status"] == "submitted"
        concern_id = concern.json()["id"]
        assert second.get(f"/me/concerns/{concern_id}").status_code == 403
        assert first.post(f"/concerns/{concern_id}/response", json={"message": "I will approve myself."}).status_code == 403

        resources = admin.get("/resources").json()
        math_resource = next(row for row in resources if row["subject_id"] == subject_id)
        reply = admin.post(f"/concerns/{concern_id}/response", json={
            "message": "Review the stored mathematics page and try two examples.",
            "status": "resources_recommended",
            "resource_ids": [math_resource["id"]],
        })
        assert reply.status_code == 200
        assert reply.json()["status"] == "resources_recommended"
        assert math_resource["title"] in [row["title"] for row in reply.json()["resources"]]

        seen = first.get(f"/me/concerns/{concern_id}")
        assert seen.status_code == 200
        assert seen.json()["resources"][0]["url"] == math_resource["url"]

        attendance = admin.post("/attendance", json={
            "student_id": first_id,
            "subject_id": subject_id,
            "session_date": "2026-04-02",
            "status": "present",
        })
        assert attendance.status_code == 201
        absent = admin.post("/attendance", json={
            "student_id": first_id,
            "subject_id": subject_id,
            "session_date": "2026-04-03",
            "status": "absent",
        })
        assert absent.status_code == 201
        duplicate = admin.post("/attendance", json={
            "student_id": first_id,
            "subject_id": subject_id,
            "session_date": "2026-04-02",
            "status": "absent",
        })
        assert duplicate.status_code == 409
        report = first.get("/me/attendance")
        assert report.status_code == 200
        assert report.json()["summary"]["sessions"] == 2
        assert report.json()["summary"]["attended"] == 1
        assert report.json()["summary"]["percentage"] == "50.00"
        assert second.get(f"/students/{first_id}/attendance").status_code == 403

        unverified = admin.post("/resources", json={
            "title": f"Portal note {suffix}",
            "resource_type": "website",
            "subject_id": subject_id,
            "topic": "fractions",
            "url": f"https://example.edu/portal-{suffix}",
            "description": "A test resource that has not been checked.",
            "verification_status": "verified",
        })
        assert unverified.status_code == 422

        plan = first.post("/me/study-plan")
        assert plan.status_code == 201
        assert plan.json()["outline"]["source"] == "academic_rules"
    finally:
        first.__exit__(None, None, None)
        second.__exit__(None, None, None)
        admin.delete(f"/students/{first_id}")
        admin.delete(f"/students/{second_id}")


def test_long_resource_url_is_audited_by_the_resource_id(admin):
    suffix = uuid4().hex
    plain = "https://www.scribd.com/document/" + ("9" * 80) + f"/algebra-{suffix}"
    markdown = f"[College Algebra notes]({plain})"
    assert len(plain) > 40
    assert len(markdown) > len(plain)
    subject_id = next(row["id"] for row in admin.get("/subjects").json() if row["code"] == "DBMS")
    title = f"Scribd algebra {suffix}"
    created = admin.post("/resources", json={
        "title": title,
        "resource_type": "website",
        "subject_id": subject_id,
        "topic": "algebra",
        "url": markdown,
        "description": "A long Scribd link pasted as a Markdown link.",
        "verification_status": "unverified",
    })
    assert created.status_code == 201, created.text
    resource_id = created.json()["id"]
    try:
        assert created.json()["url"] == plain
        with SessionLocal() as session:
            resource = session.get(LearningResource, resource_id)
            audit = session.scalar(
                select(AuditLog)
                .where(
                    AuditLog.action == "resource_created",
                    AuditLog.entity_type == "resource",
                    AuditLog.entity_id == str(resource_id),
                )
                .order_by(AuditLog.id.desc())
            )
            assert resource is not None
            assert resource.url == plain
            assert audit is not None
            assert audit.entity_id == str(resource.id)
            assert audit.detail == title
            assert len(audit.entity_id) <= 40
            assert "scribd.com" not in audit.entity_id
    finally:
        with SessionLocal() as session:
            resource = session.get(LearningResource, resource_id)
            if resource is not None:
                session.delete(resource)
                session.commit()


def test_semester_1_assessment_uses_the_resource_id_style_result(admin):
    suffix = uuid4().hex[:8]
    created = admin.post("/students", json={
        "admission_number": f"STU-{suffix}"[:30],
        "full_name": "Assessment Student",
        "email": f"assess-{suffix}@example.edu",
        "department": "History",
        "year_or_semester": "Year 4",
    })
    assert created.status_code == 201, created.text
    student_id = created.json()["id"]
    assert created.json()["department"] == "Computer Science"
    assert created.json()["year_or_semester"] == "Semester 1"
    subjects = admin.get("/subjects").json()
    assert [row["code"] for row in subjects] == ["DSA", "DBMS", "DS", "AIML", "CN"]
    assert all(row["name"] != "Mathematics" for row in subjects)
    subject_id = next(row["id"] for row in subjects if row["code"] == "DSA")
    try:
        rejected = admin.put(f"/students/{student_id}/internal-assessment", json={
            "subject_id": subject_id,
            "cat_1": 40.5,
        })
        assert rejected.status_code == 422
        saved = admin.put(f"/students/{student_id}/internal-assessment", json={
            "subject_id": subject_id,
            "cat_1": 40,
            "assignment_1": 45,
            "cat_2": 35,
            "assignment_2": 40,
            "cat_3": 45,
            "assignment_3": 40,
        })
        assert saved.status_code == 200, saved.text
        external = admin.put(f"/students/{student_id}/external-examination", json={
            "subject_id": subject_id,
            "raw_mark": 80,
        })
        assert external.status_code == 200, external.text
        dsa = next(row for row in external.json()["final_results"] if row["subject_code"] == "DSA")
        assert dsa["internal_mark"] == "40.5"
        assert dsa["external_mark"] == "40.0"
        assert dsa["final_mark"] == "80.5"
        assert dsa["grade"] == "A+"
        assert dsa["official_status"] == "pass"
        blank = next(row for row in external.json()["final_results"] if row["subject_code"] == "CN")
        assert blank["grade"] is None
        assert blank["official_status"] == "incomplete"
        assert blank["final_mark"] is None
        report_text = external.text.lower()
        assert "gpa" not in report_text
        assert "cgpa" not in report_text
        assert "semester 2" not in report_text

        account = admin.post("/students/" + str(student_id) + "/access", json={"password": "student-pass-1"})
        assert account.status_code == 200, account.text
        with TestClient(app) as portal:
            signed_in = portal.post("/auth/login", json={
                "email": f"assess-{suffix}@example.edu",
                "password": "student-pass-1",
                "portal": "student",
            })
            assert signed_in.status_code == 200, signed_in.text
            own = portal.get("/me/results")
            assert own.status_code == 200
            own_dsa = next(row for row in own.json()["academic_report"]["final_results"] if row["subject_code"] == "DSA")
            assert own_dsa["final_mark"] == "80.5"
            assert own_dsa["grade"] == "A+"
            codes = [row["code"] for row in portal.get("/me/subjects").json()]
            assert codes == ["DSA", "DBMS", "DS", "AIML", "CN"]
            hidden = portal.get(f"/students/{student_id}/results")
            assert hidden.status_code == 403
    finally:
        assert admin.delete(f"/students/{student_id}").status_code == 204


def test_examination_types_subjects_and_inactive_concerns(admin):
    exams = admin.get("/examinations").json()
    assert [row["name"] for row in exams] == ["FAT", "Assignment", "End Semester Examination"]
    assert [row["exam_type"] for row in exams] == ["fat", "assignment", "end_semester"]
    rejected_name = admin.post("/examinations", json={
        "name": "Data Structures",
        "exam_type": "fat",
        "held_on": "2026-02-02",
    })
    assert rejected_name.status_code == 422
    rejected_type = admin.post("/examinations", json={
        "name": "Quiz Night",
        "exam_type": "quiz",
        "held_on": "2026-02-02",
    })
    assert rejected_type.status_code == 422
    duplicate_type = admin.post("/examinations", json={
        "name": "FAT",
        "exam_type": "fat",
        "held_on": "2026-02-02",
    })
    assert duplicate_type.status_code == 409

    suffix = uuid4().hex[:6]
    code = f"Z{suffix}".upper()
    created = admin.post("/subjects", json={"code": code, "name": "Temporary Subject", "is_active": True})
    assert created.status_code == 201, created.text
    subject_id = created.json()["id"]
    student = admin.post("/students", json={
        "admission_number": f"SUB-{suffix}",
        "full_name": "Subject Check",
        "email": f"subject-{suffix}@example.edu",
    })
    assert student.status_code == 201, student.text
    student_id = student.json()["id"]
    try:
        assert code in [row["code"] for row in admin.get("/subjects").json()]
        duplicate = admin.post("/subjects", json={"code": code, "name": "Again"})
        assert duplicate.status_code == 409
        renamed = admin.put(f"/subjects/{subject_id}", json={
            "code": code,
            "name": "Temporary Subject Lab",
            "is_active": True,
        })
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Temporary Subject Lab"
        hidden = admin.put(f"/subjects/{subject_id}", json={
            "code": code,
            "name": "Temporary Subject Lab",
            "is_active": False,
        })
        assert hidden.status_code == 200
        assert hidden.json()["is_active"] is False
        assert code not in [row["code"] for row in admin.get("/subjects").json()]
        catalog = admin.get("/subjects?include_inactive=true").json()
        assert any(row["code"] == code and row["is_active"] is False for row in catalog)
        blocked = admin.put(f"/students/{student_id}/internal-assessment", json={
            "subject_id": subject_id,
            "cat_1": 10,
        })
        assert blocked.status_code == 404
        math = next(row for row in catalog if row["code"] == "MATH")
        assert math["is_active"] is False
        assert admin.delete(f"/subjects/{math['id']}").status_code == 409
        assert admin.post(f"/students/{student_id}/access", json={"password": "student-pass-1"}).status_code == 200
        with TestClient(app) as portal:
            signed_in = portal.post("/auth/login", json={
                "email": f"subject-{suffix}@example.edu",
                "password": "student-pass-1",
                "portal": "student",
            })
            assert signed_in.status_code == 200
            assert portal.post("/subjects", json={"code": "NOPE", "name": "Not allowed"}).status_code == 403
            rejected = portal.post("/me/concerns", json={
                "subject_id": subject_id,
                "topic": "Old topic",
                "description": "This subject is inactive.",
                "concept": "Inactive subject",
                "assistance_type": "explanation",
                "preferred_format": "examples",
                "priority": "normal",
            })
            assert rejected.status_code == 422
            dsa_id = next(row["id"] for row in portal.get("/me/subjects").json() if row["code"] == "DSA")
            accepted = portal.post("/me/concerns", json={
                "subject_id": dsa_id,
                "topic": "Arrays",
                "description": "Indexing is unclear.",
                "concept": "Array index",
                "assistance_type": "explanation",
                "preferred_format": "examples",
                "priority": "normal",
            })
            assert accepted.status_code == 201, accepted.text
        from app.records import assistant_bundle

        with SessionLocal() as session:
            stored = session.scalar(select(Student).where(Student.admission_number == "STU-004"))
            bundle = assistant_bundle(session, stored.id)
            recommended = {row["subject_name"] for row in bundle["resources"]}
            assert "Mathematics" not in recommended
            assert "Data Structures" not in recommended
            outline = str(bundle["outline"])
            assert "Mathematics" not in outline
    finally:
        admin.delete(f"/students/{student_id}")
        admin.delete(f"/subjects/{subject_id}")


def test_unknown_login_does_not_reveal_whether_the_email_exists(admin):
    response = admin.post("/auth/login", json={
        "email": "missing-person@example.edu",
        "password": "student-pass-1",
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Email or password is incorrect."
