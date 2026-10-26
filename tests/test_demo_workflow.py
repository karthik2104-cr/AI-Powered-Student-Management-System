"""Password changes, demo seeding, and academic access.

These tests use the configured PostgreSQL database. They add the fictional
demo catalog when it is missing and do not delete existing students.
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import PROJECT_ROOT, SessionLocal, init_database
from app.demo_access import (
    CREDENTIAL_FILE,
    _read_credentials,
    apply_demo_student_emails,
    assign_demo_student_passwords,
    refresh_demo_credential_emails,
    student_password,
    write_demo_credential_file,
)
from app.main import app
from app.models import (
    AttendanceRecord,
    Concern,
    ConcernResource,
    Examination,
    LearningResource,
    Mark,
    Student,
    StudyPlan,
    Subject,
    User,
)
from app.security import hash_password, verify_password
from app.videos import youtube_embed_url
from tests.support import TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD, login_admin, remove_test_admin


def test_youtube_embed_accepts_only_a_video_id():
    embed = youtube_embed_url("https://www.youtube.com/watch?v=fNk_zzaMoSs")
    assert embed == "https://www.youtube-nocookie.com/embed/fNk_zzaMoSs"
    assert youtube_embed_url("https://youtu.be/WUvTyaaNkzM") == "https://www.youtube-nocookie.com/embed/WUvTyaaNkzM"
    assert youtube_embed_url("https://www.youtube.com/@3blue1brown") is None
    assert youtube_embed_url("javascript:alert(1)") is None
    assert youtube_embed_url("https://www.khanacademy.org/math") is None


def test_admin_password_form_is_not_part_of_the_dashboard():
    page = Path("static/admin.html").read_text(encoding="utf-8")
    dashboard = page.split('id="dashboard"', 1)[1].split("</section>", 1)[0]
    assert "password-form" not in dashboard
    assert "password-banner" not in page
    assert 'id="password-dialog"' in page
    assert 'id="open-password"' in page
    assert "Change password" in page
    assert "Log out" in page
    script = Path("static/admin.js").read_text(encoding="utf-8")
    assert "password-banner" not in script
    assert "must_change_password" in script


@pytest.fixture(scope="module")
def admin():
    with TestClient(app) as client:
        health = client.get("/health")
        if health.status_code != 200 or health.json().get("academic_records") != "ready":
            pytest.skip(health.json().get("academic_records_detail") or health.json().get("detail"))
        login_admin(client)
        yield client
        client.post("/auth/logout")
    remove_test_admin()


def _counts():
    with SessionLocal() as session:
        return {
            "students": session.scalar(select(func.count()).select_from(Student)),
            "marks": session.scalar(select(func.count()).select_from(Mark)),
            "attendance": session.scalar(select(func.count()).select_from(AttendanceRecord)),
            "concerns": session.scalar(select(func.count()).select_from(Concern)),
            "resources": session.scalar(select(func.count()).select_from(LearningResource)),
            "plans": session.scalar(select(func.count()).select_from(StudyPlan)),
        }


def test_demo_seed_is_idempotent_and_keeps_the_admin_password(admin):
    with SessionLocal() as session:
        admin_user = session.scalar(select(User).where(User.email == "admin@studentmanagement.local"))
        assert admin_user is not None
        admin_hash = admin_user.password_hash
    init_database()
    first = _counts()
    init_database()
    assert _counts() == first
    with SessionLocal() as session:
        admin_user = session.scalar(select(User).where(User.email == "admin@studentmanagement.local"))
        assert admin_user.password_hash == admin_hash
        demo_students = session.scalars(select(Student).where(Student.admission_number.like("STU-%"))).all()
        expected = {f"STU-{index:03d}" for index in range(1, 13)}
        known = [row for row in demo_students if row.admission_number in expected]
        assert len(known) == 12
        assert all(row.is_demo for row in known)
        emails = {row.email for row in known}
        assert "meera.iyer@example.edu" in emails
        assert "student001@example.com" not in emails
        assert len(emails) == 12


def test_demo_credentials_match_stored_hashes_and_can_sign_in(admin):
    assert ".demo-credentials" in (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert CREDENTIAL_FILE.exists()
    known = _read_credentials()
    email = "meera.iyer@example.edu"
    assert email in known
    password = known[email]["password"]
    assert password
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.role == "student"
        assert user.password_hash != password
        assert user.password_hash.startswith("$2")
        assert verify_password(password, user.password_hash)
        second = session.scalar(select(User).where(User.email == "arjun.desai@example.edu"))
        assert second.password_hash != user.password_hash
    admin.post("/auth/logout")
    try:
        signed_in = admin.post("/auth/login", json={"email": email, "password": password, "portal": "student"})
        assert signed_in.status_code == 200
        assert signed_in.json()["role"] == "student"
        assert password not in signed_in.text
        assert "password_hash" not in signed_in.text
        videos = admin.get("/me/videos")
        assert videos.status_code == 200
        embeds = [row["embed_url"] for row in videos.json() if row["embed_url"]]
        assert "https://www.youtube-nocookie.com/embed/fNk_zzaMoSs" in embeds
        assert all(row["url"].startswith("https://") for row in videos.json())
        own = admin.get("/me/results")
        assert own.status_code == 200
        assert own.json()["student"]["admission_number"] == "STU-001"
        assert admin.get("/students").status_code == 403
        assert admin.get("/summary").status_code == 403
        assert admin.post("/demo-data", json={}).status_code == 403
    finally:
        admin.post("/auth/logout")
        login_admin(admin)


def test_students_cannot_read_another_students_concern(admin):
    concerns = admin.get("/concerns").json()
    foreign = next(row for row in concerns if row["admission_number"] == "STU-004")
    known = _read_credentials()
    password = known["meera.iyer@example.edu"]["password"]
    admin.post("/auth/logout")
    try:
        signed_in = admin.post("/auth/login", json={
            "email": "meera.iyer@example.edu",
            "password": password,
            "portal": "student",
        })
        assert signed_in.status_code == 200
        denied = admin.get(f"/me/concerns/{foreign['id']}")
        assert denied.status_code == 403
        own = admin.get("/me/concerns")
        assert own.status_code == 200
        assert all(row["admission_number"] == "STU-001" for row in own.json())
    finally:
        admin.post("/auth/logout")
        login_admin(admin)


def test_marks_attendance_concerns_and_resources_survive_a_new_session(admin):
    with SessionLocal() as first:
        mark = first.scalar(
            select(Mark)
            .join(Student, Mark.student_id == Student.id)
            .where(Student.admission_number == "STU-003")
        )
        attendance = first.scalar(
            select(AttendanceRecord)
            .join(Student, AttendanceRecord.student_id == Student.id)
            .where(Student.admission_number == "STU-003")
        )
        concern = first.scalar(select(Concern).where(Concern.seed_key == "demo-stu005-grammar"))
        assert mark is not None and attendance is not None and concern is not None
        mark_id = mark.id
        attendance_id = attendance.id
        concern_id = concern.id
        obtained = mark.marks_obtained
        status = attendance.status
    with SessionLocal() as second:
        stored_mark = second.get(Mark, mark_id)
        stored_attendance = second.get(AttendanceRecord, attendance_id)
        stored_concern = second.get(Concern, concern_id)
        link = second.scalar(select(ConcernResource).where(ConcernResource.concern_id == concern_id))
        plan = second.scalar(select(StudyPlan).where(StudyPlan.source == "demo_seed"))
        assert stored_mark.marks_obtained == obtained
        assert stored_attendance.status == status
        assert stored_concern.status == "resolved"
        assert link is not None
        resource = second.get(LearningResource, link.resource_id)
        assert resource.url == "https://www.khanacademy.org/humanities/grammar"
        assert resource.verification_status == "verified"
        assert plan is not None


def test_summary_matches_database_counts(admin):
    summary = admin.get("/summary")
    assert summary.status_code == 200
    body = summary.json()
    with SessionLocal() as session:
        assert body["students"] == session.scalar(select(func.count()).select_from(Student))
        assert body["demo_students"] == session.scalar(
            select(func.count()).select_from(Student).where(Student.is_demo.is_(True))
        )
        assert body["subjects"] == session.scalar(
            select(func.count()).select_from(Subject).where(Subject.is_active.is_(True))
        )
        assert body["subjects"] == 5
        assert body["examinations"] == session.scalar(
            select(func.count()).select_from(Examination).where(Examination.is_active.is_(True))
        )
        assert body["examinations"] == 3
        assert body["marks"] == session.scalar(select(func.count()).select_from(Mark))
        assert body["attendance_sessions"] == session.scalar(select(func.count()).select_from(AttendanceRecord))
        assert body["open_concerns"] + body["resolved_concerns"] == session.scalar(
            select(func.count()).select_from(Concern)
        )
    performance = body["performance"]
    assert performance["pass"] + performance["fail"] + performance["incomplete"] == body["students"] * body["subjects"]
    assert body["demo_students"] >= 15
    repeated = admin.post("/demo-data", json={})
    assert repeated.status_code == 200
    assert repeated.json()["students_created"] == 0
    assert "password" not in repeated.json()
    for row in _read_credentials().values():
        assert row["password"] not in repeated.text


def test_video_urls_and_admin_routes_are_protected(admin):
    anonymous = TestClient(app)
    assert anonymous.get("/summary").status_code == 401
    assert anonymous.post("/marks", json={}).status_code == 401
    assert anonymous.post("/attendance", json={}).status_code == 401
    anonymous.close()
    subjects = admin.get("/subjects")
    assert subjects.status_code == 200
    subject_id = subjects.json()[0]["id"]
    rejected = admin.post("/resources", json={
        "title": "Unsafe video",
        "resource_type": "video",
        "subject_id": subject_id,
        "topic": "safety",
        "url": "javascript:alert(1)",
        "description": "This must not be stored.",
        "verification_status": "unverified",
    })
    assert rejected.status_code == 422
    students = admin.get("/students").json()
    student = next(row for row in students if row["admission_number"] == "STU-001")
    created = admin.post("/attendance", json={
        "student_id": student["id"],
        "subject_id": subject_id,
        "session_date": "2024-01-15",
        "status": "present",
    })
    assert created.status_code == 201
    record_id = next(row["id"] for row in created.json()["records"] if row["session_date"] == "2024-01-15")
    try:
        updated = admin.put(f"/attendance/{record_id}", json={"status": "absent"})
        assert updated.status_code == 200
        with SessionLocal() as session:
            stored = session.get(AttendanceRecord, record_id)
            assert stored.status == "absent"
        invalid = admin.put(f"/attendance/{record_id}", json={"status": "late"})
        assert invalid.status_code == 422
    finally:
        assert admin.delete(f"/attendance/{record_id}").status_code == 204


def test_password_change_persists_across_login(admin):
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == TEST_ADMIN_EMAIL))
        user.must_change_password = True
        session.commit()
    admin.post("/auth/logout")
    try:
        signed_in = admin.post("/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": TEST_ADMIN_PASSWORD,
            "portal": "admin",
        })
        assert signed_in.status_code == 200
        assert signed_in.json()["must_change_password"] is True
        page = admin.get("/admin/dashboard")
        assert page.status_code == 200
        assert 'id="open-password"' in page.text
        wrong = admin.post("/auth/password", json={
            "current_password": "not-the-password",
            "new_password": "Menu-change-pass-1",
            "new_password_confirmation": "Menu-change-pass-1",
        })
        assert wrong.status_code == 401
        mismatch = admin.post("/auth/password", json={
            "current_password": TEST_ADMIN_PASSWORD,
            "new_password": "Menu-change-pass-1",
            "new_password_confirmation": "Menu-change-pass-2",
        })
        assert mismatch.status_code == 422
        changed = admin.post("/auth/password", json={
            "current_password": TEST_ADMIN_PASSWORD,
            "new_password": "Menu-change-pass-1",
            "new_password_confirmation": "Menu-change-pass-1",
        })
        assert changed.status_code == 200
        assert admin.get("/auth/me").json()["must_change_password"] is False
        admin.post("/auth/logout")
        again = admin.post("/auth/login", json={
            "email": TEST_ADMIN_EMAIL,
            "password": "Menu-change-pass-1",
            "portal": "admin",
        })
        assert again.status_code == 200
        assert again.json()["must_change_password"] is False
    finally:
        admin.post("/auth/logout")
        login_admin(admin)
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.email == TEST_ADMIN_EMAIL))
            user.must_change_password = False
            session.commit()


def test_student_assistant_explains_only_that_student(admin, monkeypatch):
    from app.assistant import AssistantUnavailable

    password = _read_credentials()["meera.iyer@example.edu"]["password"]
    seen = {}

    def fake_generate(prompt):
        seen["prompt"] = prompt
        return "Mathematics is stored as a pass. Attendance uses the supplied percentage."

    monkeypatch.setattr("app.records.generate_text", fake_generate)
    admin.post("/auth/logout")
    try:
        signed_in = admin.post("/auth/login", json={
            "email": "meera.iyer@example.edu",
            "password": password,
            "portal": "student",
        })
        assert signed_in.status_code == 200
        report = admin.post("/me/assistant/report", json={})
        assert report.status_code == 200
        body = report.json()
        assert body["facts"]["admission_number"] == "STU-001"
        assert body["facts"]["attendance"]["sessions"] > 0
        assert "STU-002" not in seen["prompt"]
        assert "asha.raman@example.edu" not in seen["prompt"]
        assert "stored as a pass" in body["narrative"]
        with SessionLocal() as session:
            other = session.scalar(select(Student).where(Student.admission_number == "STU-002"))
        denied = admin.post(f"/students/{other.id}/assistant/report")
        assert denied.status_code == 403
        results = admin.get("/me/results")
        assert results.status_code == 200

        def unavailable(prompt):
            raise AssistantUnavailable("The local model is not reachable. Student records are still available.")

        monkeypatch.setattr("app.records.generate_text", unavailable)
        failed = admin.post("/me/assistant/suggestions", json={})
        assert failed.status_code == 503
        assert "not reachable" in failed.json()["detail"]
        assert admin.get("/me/results").status_code == 200
    finally:
        admin.post("/auth/logout")
        login_admin(admin)


def test_study_plan_page_clears_loading_and_has_result_panels():
    page = Path("static/student.html").read_text(encoding="utf-8")
    script = Path("static/student.js").read_text(encoding="utf-8")
    auth = Path("static/auth.js").read_text(encoding="utf-8")
    for element_id in ("plan-text", "plan-status", "plan-explanation", "revision-result", "report-result", "ask-result"):
        assert f'id="{element_id}"' in page
    assert "Generating explanation…" in script
    assert "timeoutMs: ASSISTANT_TIMEOUT_MS" in script
    assert "finally" in script
    assert "assistantRequest = null" in script
    assert "Study plan saved." in script
    assert "The server did not confirm the saved plan." in script
    assert "innerHTML = render(answer)" in script
    assert "You have unsaved changes." in script
    assert "plan.stored ? plan.stored.outline : plan.current_outline" not in script
    assert "Your Study Plan" in page
    assert "No study plan yet" in page
    assert 'data-panel="ask"' in page
    assert "View My Academic Report" in page
    assert "Get Revision Suggestions" in page
    assert 'id="ask-button"' in page
    assert 'querySelector("#ask-button")' in script
    assert "AbortError" in auth
    assert 'credentials: "same-origin"' in auth


def test_edited_study_plan_persists_and_explanation_uses_it(admin, monkeypatch):
    password = _read_credentials()["meera.iyer@example.edu"]["password"]
    note = "Monday: revise the stored mathematics result only."
    seen = {}

    def fake_generate(prompt):
        seen["prompt"] = prompt
        return "Monday stays on the stored mathematics result."

    monkeypatch.setattr("app.records.generate_text", fake_generate)
    admin.post("/auth/logout")
    created_id = None
    try:
        signed_in = admin.post("/auth/login", json={
            "email": "meera.iyer@example.edu",
            "password": password,
            "portal": "student",
        })
        assert signed_in.status_code == 200
        empty = admin.post("/me/study-plan", json={"outline_text": "   "})
        assert empty.status_code == 422
        saved = admin.post("/me/study-plan", json={"outline_text": note})
        assert saved.status_code == 201
        assert saved.json()["outline"]["source"] == "student_edit"
        assert saved.json()["outline"]["note"] == note
        created_id = saved.json()["id"]
        loaded = admin.get("/me/study-plan")
        assert loaded.status_code == 200
        assert loaded.json()["stored"]["id"] == created_id
        assert loaded.json()["stored"]["outline"]["note"] == note
        explained = admin.post("/me/assistant/plan", json={"plan_text": note})
        assert explained.status_code == 200
        assert note in seen["prompt"]
        assert explained.json()["facts"]["displayed_plan"] == note
        assert explained.json()["facts"]["admission_number"] == "STU-001"
        assert explained.json()["narrative"] == "Monday stays on the stored mathematics result."
        suggestions = admin.post("/me/assistant/suggestions", json={})
        assert suggestions.status_code == 200
        assert suggestions.json()["facts"]["results"]
        report = admin.post("/me/assistant/report", json={})
        assert report.status_code == 200
        facts = report.json()["facts"]
        assert "overall_percentage" not in facts
        assert "cgpa" not in str(facts).lower()
        assert "gpa" not in str(facts).lower()
        assert facts["academic_rules"]["semester"] == "Semester 1"
        assert "Data Structures and Algorithms" in facts["academic_rules"]["active_subjects"]
        failed = admin.post("/me/assistant/ask", json={"question": "  "})
        assert failed.status_code == 422
    finally:
        if created_id is not None:
            with SessionLocal() as session:
                row = session.get(StudyPlan, created_id)
                if row is not None:
                    session.delete(row)
                    session.commit()
        admin.post("/auth/logout")
        login_admin(admin)


def test_student_password_uses_the_first_and_last_name():
    assert student_password("Priya Sharma", 2) == "PriyaSharma2"
    assert student_password("Rahul Kumar", 3) == "RahulKumar3"
    assert student_password("Mary-Jane O'Neil", 4) == "MaryJaneONeil4"
    assert student_password("Mary Ann Smith", 5) == "MarySmith5"
    assert student_password("Solo", 1) is None
    assert student_password("Priya Sharma", 0) is None


def test_demo_passwords_authenticate_and_hashes_are_stored(admin):
    with SessionLocal() as session:
        admin_hashes = {
            user.email: user.password_hash
            for user in session.scalars(select(User).where(User.role == "admin")).all()
        }
        protected = {
            user.id: user.password_hash
            for user in session.scalars(select(User)).all()
            if user.role != "student" or user.student is None or not user.student.is_demo
        }
        profiles = [
            (row.full_name, row.email, row.admission_number)
            for row in session.scalars(
                select(Student).where(Student.is_demo.is_(True)).order_by(Student.id.asc())
            ).all()
        ]
        mark_count = session.scalar(select(func.count()).select_from(Mark))
        summary = assign_demo_student_passwords(session)
        assert summary["updated"] == len(profiles)
        assert summary["skipped"] == []
        assert summary["ordering"] == "students.id ascending among demo students, starting at 1"
        assert "password" not in summary
        session.commit()
        written = write_demo_credential_file(session)
    assert written == len(profiles)
    known = _read_credentials()
    with SessionLocal() as session:
        admin_after = {
            user.email: user.password_hash
            for user in session.scalars(select(User).where(User.role == "admin")).all()
        }
        assert admin_after == admin_hashes
        for user_id, password_hash in protected.items():
            assert session.get(User, user_id).password_hash == password_hash
        assert session.scalar(select(func.count()).select_from(Mark)) == mark_count
        for number, (full_name, email, admission_number) in enumerate(profiles, start=1):
            user = session.scalar(select(User).where(User.email == email))
            student = user.student
            password = student_password(full_name, number)
            assert student.full_name == full_name
            assert student.admission_number == admission_number
            assert user.password_hash != password
            assert user.password_hash.startswith("$2")
            assert verify_password(password, user.password_hash)
            assert verify_password("wrong-password", user.password_hash) is False
            assert known[email]["password"] == password
            assert known[email]["admission_number"] == admission_number
    assert "PORTAL-CHECK" not in CREDENTIAL_FILE.read_text(encoding="utf-8")
    first_name, first_email, _first_admission = profiles[0]
    first_password = student_password(first_name, 1)
    admin.post("/auth/logout")
    try:
        signed_in = admin.post("/auth/login", json={
            "email": first_email,
            "password": first_password,
            "portal": "student",
        })
        assert signed_in.status_code == 200
        assert signed_in.json()["role"] == "student"
        assert first_password not in signed_in.text
        assert "password_hash" not in signed_in.text
        rejected = admin.post("/auth/login", json={
            "email": first_email,
            "password": "wrong-password",
            "portal": "student",
        })
        assert rejected.status_code == 401
        assert rejected.json()["detail"] == "Email or password is incorrect."
    finally:
        admin.post("/auth/logout")
        login_admin(admin)


def test_a_student_name_without_two_parts_changes_no_passwords():
    suffix = uuid4().hex[:8]
    with SessionLocal() as session:
        sample = session.scalar(select(User).where(User.email == "meera.iyer@example.edu"))
        before = sample.password_hash
        student = Student(
            admission_number=f"TMP{suffix}"[:30],
            full_name="Solo",
            email=f"solo-{suffix}@example.edu",
            is_active=True,
            is_demo=True,
        )
        session.add(student)
        session.flush()
        session.add(User(
            email=student.email,
            password_hash=hash_password("temporary-pass"),
            role="student",
            is_active=True,
            must_change_password=False,
            student_id=student.id,
            created_at=datetime.now(timezone.utc),
        ))
        session.flush()
        summary = assign_demo_student_passwords(session)
        assert summary["updated"] == 0
        assert any(row["admission_number"] == student.admission_number for row in summary["skipped"])
        session.refresh(sample)
        assert sample.password_hash == before
        session.rollback()


def test_demo_emails_are_unique_and_the_old_addresses_do_not_sign_in(admin):
    expected = {
        "ADM-1001": "asha.raman@example.edu",
        "ADM-1002": "nila.krishnan@example.edu",
        "ADM-1003": "farhan.qureshi@example.edu",
        "STU-001": "meera.iyer@example.edu",
        "STU-002": "arjun.desai@example.edu",
        "STU-003": "laila.rahman@example.edu",
        "STU-004": "kabir.menon@example.edu",
        "STU-005": "sofia.almeida@example.edu",
        "STU-006": "rohan.patel@example.edu",
        "STU-007": "ananya.shah@example.edu",
        "STU-008": "daniel.okonkwo@example.edu",
        "STU-009": "priya.nair@example.edu",
        "STU-010": "hassan.ali@example.edu",
        "STU-011": "elena.petrova@example.edu",
        "STU-012": "vikram.rao@example.edu",
    }
    former = {
        "STU-001": "student001@example.com",
        "STU-002": "student002@example.com",
        "STU-003": "student003@example.com",
        "STU-004": "student004@example.com",
        "STU-005": "student005@example.com",
        "STU-006": "student006@example.com",
        "STU-007": "student007@example.com",
        "STU-008": "student008@example.com",
        "STU-009": "student009@example.com",
        "STU-010": "student010@example.com",
        "STU-011": "student011@example.com",
        "STU-012": "student012@example.com",
    }
    with SessionLocal() as session:
        before = {
            user.student.admission_number: (user.id, user.password_hash, user.student.id)
            for user in session.scalars(select(User).where(User.role == "student")).all()
            if user.student is not None and user.student.is_demo
        }
        mark_count = session.scalar(select(func.count()).select_from(Mark))
        summary = apply_demo_student_emails(session)
        assert summary["missing"] == []
        assert summary["updated"] + summary["already_correct"] == 15
        session.commit()
        refresh_demo_credential_emails(session)
    known = _read_credentials()
    assert len(set(expected.values())) == 15
    with SessionLocal() as session:
        stored = session.scalars(select(Student).where(Student.is_demo.is_(True))).all()
        assert {row.email for row in stored} == set(expected.values())
        assert session.scalar(select(func.count()).select_from(Mark)) == mark_count
        for admission_number, email in expected.items():
            student = session.scalar(select(Student).where(Student.admission_number == admission_number))
            user = session.scalar(select(User).where(User.student_id == student.id))
            user_id, password_hash, student_id = before[admission_number]
            assert student.id == student_id
            assert student.email == email
            assert user.email == email
            assert user.id == user_id
            assert user.password_hash == password_hash
            assert verify_password(known[email]["password"], user.password_hash)
    admin.post("/auth/logout")
    try:
        for email in expected.values():
            signed_in = admin.post("/auth/login", json={
                "email": email,
                "password": known[email]["password"],
                "portal": "student",
            })
            assert signed_in.status_code == 200
            assert signed_in.json()["email"] == email
            assert "password_hash" not in signed_in.text
            admin.post("/auth/logout")
        for admission_number, email in former.items():
            rejected = admin.post("/auth/login", json={
                "email": email,
                "password": known[expected[admission_number]]["password"],
                "portal": "student",
            })
            assert rejected.status_code == 401
            assert known[expected[admission_number]]["password"] not in rejected.text
    finally:
        admin.post("/auth/logout")
        login_admin(admin)
