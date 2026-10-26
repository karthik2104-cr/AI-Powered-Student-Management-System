"""API tests.

Calculation tests do not need PostgreSQL. The tests below that read stored
students run only when DATABASE_URL can connect and the academic tables are ready.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.assistant import model_name
from app.database import SessionLocal, hide_secrets, init_database
from app.main import app
from app.models import Examination, Mark
from tests.support import login_admin, remove_test_admin


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def database_ready(client):
    health = client.get("/health")
    payload = health.json()
    if health.status_code != 200 or payload.get("academic_records") != "ready":
        reason = payload.get("academic_records_detail") or payload.get("detail")
        pytest.skip(reason)
    login_admin(client)
    yield client
    client.post("/auth/logout")
    remove_test_admin()


def test_hide_secrets_removes_a_password():
    message = (
        "connection failed for postgresql+psycopg://postgres:stage2-test-secret"
        "@localhost:5432/postgres password=stage2-test-secret"
    )
    cleaned = hide_secrets(message)
    assert "stage2-test-secret" not in cleaned
    assert "://***@" in cleaned


def test_dashboard_page_is_served(client):
    page = client.get("/")
    script = client.get("/static/auth.js")
    assert page.status_code == 200
    assert "Student Management System" in page.text
    assert "/static/auth.js" in page.text
    assert script.status_code == 200
    assert "/auth/login" in script.text
    assert client.get("/login").status_code == 200
    assert client.get("/register").status_code == 200
    student = client.get("/student", follow_redirects=False)
    admin = client.get("/admin", follow_redirects=False)
    assert student.status_code == 303
    assert student.headers["location"] == "/login"
    assert admin.status_code == 303
    assert admin.headers["location"] == "/admin/login"


def test_invalid_records_are_rejected_before_the_database(client):
    health = client.get("/health")
    if health.status_code != 200 or health.json().get("database") != "reachable":
        denied = client.post("/students", json={
            "admission_number": "ADM-9",
            "full_name": "Test Student",
            "email": "not-an-email",
        })
        assert denied.status_code == 401
        assert "postgresql+psycopg://" not in denied.text
        return

    login_admin(client)
    student = client.post("/students", json={
        "admission_number": "ADM-9",
        "full_name": "Test Student",
        "email": "not-an-email",
    })
    mark = client.post("/marks", json={
        "student_id": 1,
        "subject_id": 1,
        "examination_id": 1,
        "marks_obtained": "11",
        "maximum_marks": "10",
        "pass_marks": "5",
    })
    question = client.post("/students/1/assistant/ask", json={"question": " "})
    assert student.status_code == 422
    assert mark.status_code == 422
    assert question.status_code == 422


def test_assistant_status_names_the_selected_model(client):
    response = client.get("/assistant/status")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == model_name()
    assert isinstance(body["installed"], bool)
    assert isinstance(body["reachable"], bool)


def test_root_stays_available(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "status": "running",
        "message": "Student Management System is running",
    }
    assert "text/html" in client.get("/").headers["content-type"]


def test_non_integer_ids_are_rejected(client):
    for path in (
        "/students/not-a-number",
        "/subjects/not-a-number",
        "/examinations/not-a-number",
    ):
        response = client.get(path)
        assert response.status_code == 422


def test_missing_database_is_reported_without_secrets(client):
    health = client.get("/health")
    if health.status_code == 200 and health.json().get("academic_records") == "ready":
        pytest.skip("PostgreSQL is configured, so the missing-database check does not apply.")

    payload = health.json()
    assert health.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["application"] == "running"
    assert payload["database"] == "unreachable"
    assert payload["academic_records"] == "not_ready"
    assert "DATABASE_URL" in payload["detail"]
    assert "postgresql+psycopg://" not in response_text(health)

    for path in (
        "/students",
        "/subjects",
        "/examinations",
        "/students/1",
        "/students/1/results",
        "/students/1/feedback",
        "/students/1/resources",
        "/students/1/study-outline",
        "/subjects/1",
        "/examinations/1",
        "/summary",
        "/resources",
    ):
        response = client.get(path)
        assert response.status_code == 401
        assert "postgresql+psycopg://" not in response_text(response)

    created = client.post("/students", json={
        "admission_number": "ADM-9",
        "full_name": "Test Student",
        "email": "test.student@example.edu",
    })
    assert created.status_code == 401
    assert "postgresql+psycopg://" not in response_text(created)


def response_text(response) -> str:
    return response.text


def test_academic_reads_match_the_calculations(database_ready):
    students = database_ready.get("/students")
    subjects = database_ready.get("/subjects")
    examinations = database_ready.get("/examinations")
    assert students.status_code == 200
    assert subjects.status_code == 200
    assert examinations.status_code == 200

    student_rows = students.json()
    assert [row["admission_number"] for row in student_rows].count("ADM-1001") == 1
    asha = next(row for row in student_rows if row["admission_number"] == "ADM-1001")
    nila = next(row for row in student_rows if row["admission_number"] == "ADM-1002")

    subject_codes = {row["code"] for row in subjects.json()}
    assert subject_codes == {"DSA", "DBMS", "DS", "AIML", "CN"}
    assert {"MATH", "SCI", "ENG"}.isdisjoint(subject_codes)
    exam_names = [row["name"] for row in examinations.json()]
    assert exam_names == ["FAT", "Assignment", "End Semester Examination"]

    asha_response = database_ready.get(f"/students/{asha['id']}/results")
    assert asha_response.status_code == 200
    asha_results = asha_response.json()["results"]
    assert len(asha_results) >= 7
    math_final = next(
        row
        for row in asha_results
        if row["subject_code"] == "MATH" and row["examination_name"] == "End Semester Examination"
    )
    assert math_final["percentage"] == "68.00"
    assert math_final["official_status"] == "pass"
    assert math_final["guidance_label"] == "developing"
    assert math_final["previous_result"]["direction"] == "improved"
    assert math_final["previous_result"]["percentage_change"] == "30.00"

    database_midterm = next(
        row
        for row in asha_results
        if row["subject_code"] == "DBMS" and row["examination_name"] == "FAT"
    )
    assert database_midterm["pass_marks"] is None
    assert database_midterm["official_status"] == "not_assessed"
    assert "official result is fail" not in database_midterm["explanation"]

    nila_response = database_ready.get(f"/students/{nila['id']}/results")
    nila_database = next(
        row
        for row in nila_response.json()["results"]
        if row["subject_code"] == "DBMS"
    )
    assert nila_database["official_status"] == "pass"
    assert nila_database["guidance_label"] == "needs_attention"

    missing_student = database_ready.get("/students/999999")
    assert missing_student.status_code == 404
    subject_id = subjects.json()[0]["id"]
    examination_id = examinations.json()[0]["id"]
    assert database_ready.get(f"/subjects/{subject_id}").status_code == 200
    assert database_ready.get(f"/examinations/{examination_id}").status_code == 200
    assert database_ready.get("/subjects/999999").status_code == 404
    assert database_ready.get("/examinations/999999").status_code == 404

    health = database_ready.get("/health")
    assert health.status_code == 200
    assert health.json()["database"] == "reachable"
    assert health.json()["academic_records"] == "ready"
    assert "postgresql+psycopg://" not in response_text(health)


def test_loading_demo_data_twice_does_not_duplicate_rows(database_ready):
    init_database()
    before_students = database_ready.get("/students").json()
    asha = next(row for row in before_students if row["admission_number"] == "ADM-1001")
    before_results = database_ready.get(f"/students/{asha['id']}/results").json()

    init_database()

    after_students = database_ready.get("/students").json()
    after_results = database_ready.get(f"/students/{asha['id']}/results").json()
    assert [row["admission_number"] for row in after_students].count("ADM-1001") == 1
    assert after_students == before_students
    assert after_results == before_results
    assert len(after_results["results"]) >= 7


def test_feedback_resources_and_student_crud(database_ready):
    suffix = uuid4().hex[:8]
    admission = f"CRUD-{suffix}"
    created = database_ready.post("/students", json={
        "admission_number": admission,
        "full_name": "Case Student",
        "email": f"case-{suffix}@example.edu",
    })
    assert created.status_code == 201
    student_id = created.json()["id"]
    duplicate = database_ready.post("/students", json={
        "admission_number": admission,
        "full_name": "Another Name",
        "email": f"another-{suffix}@example.edu",
    })
    assert duplicate.status_code == 409

    subjects = database_ready.get("/subjects").json()
    database_subject = next(row for row in subjects if row["code"] == "DBMS")
    feedback = database_ready.post(f"/students/{student_id}/feedback", json={
        "subject_id": database_subject["id"],
        "topic": "indexes",
        "difficult_topics": "Indexes are unfamiliar.",
        "preferred_format": "examples",
    })
    assert feedback.status_code == 201
    assert feedback.json()["reported_by_student"] is True
    listed = database_ready.get(f"/students/{student_id}/feedback")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    asha = next(row for row in database_ready.get("/students").json() if row["admission_number"] == "ADM-1001")
    resources = database_ready.get(f"/students/{asha['id']}/resources")
    assert resources.status_code == 200
    titles = [row["title"] for row in resources.json()]
    assert "PostgreSQL Tutorial" in titles
    assert "College Algebra 2e" not in titles
    assert all(row["verification_status"] == "verified" for row in resources.json())

    outline = database_ready.get(f"/students/{asha['id']}/study-outline")
    assert outline.status_code == 200
    assert any(item["subject_name"] == "Database Management Systems" for item in outline.json()["items"])

    removed = database_ready.delete(f"/students/{student_id}")
    assert removed.status_code == 204
    assert database_ready.get(f"/students/{student_id}").status_code == 404


def test_live_model_can_explain_a_result(database_ready):
    status = database_ready.get("/assistant/status").json()
    if not status["reachable"] or not status["installed"]:
        pytest.skip(status.get("detail") or f"{model_name()} is not available.")
    asha = next(row for row in database_ready.get("/students").json() if row["admission_number"] == "ADM-1001")
    report = database_ready.post(f"/students/{asha['id']}/assistant/report")
    assert report.status_code == 200
    body = report.json()
    assert body["model"] == model_name()
    assert "not an official academic result" in body["notice"].lower()
    assert body["narrative"].strip()


def test_database_rejects_a_mark_above_the_maximum(database_ready):
    from datetime import date
    from decimal import Decimal

    from sqlalchemy.exc import IntegrityError

    students = database_ready.get("/students").json()
    subjects = database_ready.get("/subjects").json()
    session = SessionLocal()
    try:
        examination = Examination(
            name="Constraint Check",
            exam_type="quiz",
            held_on=date(2026, 1, 2),
        )
        session.add(examination)
        session.flush()
        session.add(
            Mark(
                student_id=students[0]["id"],
                subject_id=subjects[0]["id"],
                examination_id=examination.id,
                marks_obtained=Decimal("10.00"),
                maximum_marks=Decimal("5.00"),
                pass_marks=Decimal("3.00"),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
    finally:
        session.rollback()
        session.close()
