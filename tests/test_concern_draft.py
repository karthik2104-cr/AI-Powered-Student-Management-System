"""Concern-draft prompts stay small and a failed draft does not change the concern.

Ollama is not called. The tests replace the HTTP call or the text generator.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.academics import academic_report
from app.assistant import (
    CONCERN_DRAFT_RULES,
    DRAFT_TASK,
    MAX_PROMPT_LENGTH,
    REPORT_TASK,
    build_prompt,
)
from app.database import SessionLocal
from app.main import app
from app.models import (
    AttendanceRecord,
    Concern,
    ConcernUpdate,
    Examination,
    ExternalExamination,
    Feedback,
    InternalAssessment,
    LearningResource,
    Mark,
    Student,
    StudyPlan,
    Subject,
)
from app.records import assistant_bundle, concern_draft_context, load_concern
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


def _subjects(admin):
    rows = admin.get("/subjects", params={"include_inactive": True}).json()
    return {row["code"]: row for row in rows}


def _create_student(admin, full_name):
    suffix = uuid4().hex[:8]
    created = admin.post("/students", json={
        "admission_number": f"DR{suffix}",
        "full_name": full_name,
        "email": f"draft-{suffix}@example.edu",
        "department": "Computer Science",
        "year_or_semester": "Semester 1",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    body["email"] = f"draft-{suffix}@example.edu"
    return body


def _insert_concern(student_id, subject_id, **fields):
    values = {
        "topic": "Recursion",
        "description": "The recursive case is unclear.",
        "concept": "Recursion trees",
        "assistance_type": "explanation",
        "preferred_format": "examples",
        "status": "submitted",
        "priority": "normal",
    }
    values.update(fields)
    with SessionLocal() as session:
        row = Concern(
            student_id=student_id,
            subject_id=subject_id,
            created_at=datetime.now(timezone.utc),
            **values,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _create_resource(admin, subject_id, title, topic, description="Short recursion note."):
    created = admin.post("/resources", json={
        "title": title,
        "resource_type": "website",
        "subject_id": subject_id,
        "topic": topic,
        "url": f"https://example.edu/draft/{uuid4().hex}",
        "description": description,
        "verification_status": "unverified",
    })
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _snapshot(concern_id):
    with SessionLocal() as session:
        row = session.get(Concern, concern_id)
        updates = session.scalar(
            select(func.count()).select_from(ConcernUpdate).where(ConcernUpdate.concern_id == concern_id)
        )
        return {
            "status": row.status,
            "topic": row.topic,
            "description": row.description,
            "concept": row.concept,
            "assistance_type": row.assistance_type,
            "preferred_format": row.preferred_format,
            "priority": row.priority,
            "updates": updates,
        }


def _delete_resources(resource_ids):
    if not resource_ids:
        return
    with SessionLocal() as session:
        session.execute(delete(LearningResource).where(LearningResource.id.in_(resource_ids)))
        session.commit()


def _draft(admin, concern_id, monkeypatch, narrative="Review the listed recursion resource."):
    seen = {}

    def fake_generate(prompt):
        seen["prompt"] = prompt
        return narrative

    monkeypatch.setattr("app.records.generate_text", fake_generate)
    response = admin.post(f"/concerns/{concern_id}/assistant/draft")
    return response, seen


def test_draft_button_shows_the_error_and_does_not_save_the_reply():
    script = Path("static/admin.js").read_text(encoding="utf-8")
    assert "/assistant/draft" in script
    assert 'output.textContent = "Drafting…"' in script
    assert "output.textContent = error.message" in script
    assert "output.textContent = `${answer.notice} ${answer.narrative}`" in script


def test_short_concern_draft_uses_only_that_concern(admin, monkeypatch):
    student_ids = []
    resource_ids = []
    try:
        student = _create_student(admin, "Draft Target Student")
        student_ids.append(student["id"])
        subject = _subjects(admin)["DSA"]
        concern_id = _insert_concern(
            student["id"],
            subject["id"],
            topic="Loops",
            description="The loop boundary is unclear.",
            concept="Loop bounds",
            assistance_type="practice",
            preferred_format="exercises",
            priority="low",
        )
        before = _snapshot(concern_id)
        response, seen = _draft(admin, concern_id, monkeypatch, "Practice the loop boundary with an exercise.")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["narrative"] == "Practice the loop boundary with an exercise."
        assert "official academic result" in body["notice"]
        assert set(body["facts"]) == {
            "student_name",
            "subject",
            "subject_is_active",
            "topic",
            "description",
            "concept",
            "assistance_requested",
            "preferred_format",
            "status",
            "priority",
            "resources",
        }
        assert body["facts"]["student_name"] == "Draft Target Student"
        assert body["facts"]["topic"] == "Loops"
        assert body["facts"]["subject_is_active"] is True
        prompt = seen["prompt"]
        assert len(prompt) <= MAX_PROMPT_LENGTH
        assert "The loop boundary is unclear." in prompt
        assert student["email"] not in prompt
        assert student["admission_number"] not in prompt
        assert "rule_based_outline" not in prompt
        assert "cat_1" not in prompt
        assert _snapshot(concern_id) == before
    finally:
        _delete_resources(resource_ids)
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_long_description_and_concept_stay_in_the_prompt(admin, monkeypatch):
    student_ids = []
    try:
        student = _create_student(admin, "Draft Long Student")
        student_ids.append(student["id"])
        subject = _subjects(admin)["DSA"]
        description = ("Core recursion request. " + ("The recursive case stays difficult. " * 40))[:991] + "ENDMARKER"
        concept = ("Core recursion concept. " + ("Step through the call. " * 20))[:290] + "CONCEPTEND"
        assert len(description) == 1000
        assert len(concept) == 300
        concern_id = _insert_concern(
            student["id"],
            subject["id"],
            description=description,
            concept=concept,
            priority="high",
        )
        before = _snapshot(concern_id)
        response, seen = _draft(admin, concern_id, monkeypatch)
        assert response.status_code == 200, response.text
        prompt = seen["prompt"]
        assert description in prompt
        assert concept in prompt
        assert response.json()["facts"]["description"] == description
        assert response.json()["facts"]["concept"] == concept
        assert len(prompt) <= MAX_PROMPT_LENGTH
        assert _snapshot(concern_id) == before
    finally:
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_many_matching_resources_are_capped_and_other_subjects_stay_out(admin, monkeypatch):
    student_ids = []
    resource_ids = []
    try:
        student = _create_student(admin, "Draft Resource Student")
        student_ids.append(student["id"])
        subjects = _subjects(admin)
        head = "Recursion notes for the selected concern. "
        tail = "TAILMARKER"
        long_description = head + ("x" * (500 - len(head) - len(tail))) + tail
        assert len(long_description) == 500
        for number in range(1, 7):
            resource_ids.append(_create_resource(
                admin,
                subjects["DSA"]["id"],
                f"Zqdraft Resource {number:02d}",
                "zqdrafttoken",
                long_description if number == 1 else "Short recursion note.",
            ))
        resource_ids.append(_create_resource(
            admin,
            subjects["DSA"]["id"],
            "Graph Theory Resource ZZ",
            "Graph theory",
            "Graphs only.",
        ))
        resource_ids.append(_create_resource(
            admin,
            subjects["DBMS"]["id"],
            "Zqdraft Resource Other Subject",
            "zqdrafttoken",
            "This belongs to another subject.",
        ))
        concern_id = _insert_concern(
            student["id"],
            subjects["DSA"]["id"],
            topic="zqdrafttoken",
            concept="zqconceptdetail",
        )
        before = _snapshot(concern_id)
        response, seen = _draft(admin, concern_id, monkeypatch)
        assert response.status_code == 200, response.text
        prompt = seen["prompt"]
        titles = [item["title"] for item in response.json()["facts"]["resources"]]
        assert titles == [f"Zqdraft Resource {number:02d}" for number in range(1, 6)]
        assert "Zqdraft Resource 06" not in prompt
        assert "Graph Theory Resource ZZ" not in prompt
        assert "Zqdraft Resource Other Subject" not in prompt
        assert "Recursion notes for the selected concern." in prompt
        assert "TAILMARKER" not in prompt
        assert len(prompt) <= MAX_PROMPT_LENGTH
        assert _snapshot(concern_id) == before
    finally:
        _delete_resources(resource_ids)
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_unrelated_history_does_not_enlarge_the_selected_prompt(admin, monkeypatch):
    student_ids = []
    resource_ids = []
    try:
        student = _create_student(admin, "Draft Target Student")
        other = _create_student(admin, "Zeddrafter Otherperson")
        student_ids.extend([student["id"], other["id"]])
        subjects = _subjects(admin)
        dsa_id = subjects["DSA"]["id"]
        resource_ids.append(_create_resource(admin, dsa_id, "Recursion Resource Kept", "Recursion"))
        concern_id = _insert_concern(student["id"], dsa_id, topic="Recursion", description="Keep this recursion concern.")
        first, seen = _draft(admin, concern_id, monkeypatch)
        assert first.status_code == 200, first.text
        original = seen["prompt"]

        for number in range(12):
            _insert_concern(
                student["id"],
                dsa_id,
                topic=f"Noise{number:02d}topic",
                description=f"ZZOTHERCONCERN {number} is a different concern.",
                concept="Unrelated noise concept",
            )
        _insert_concern(
            other["id"],
            subjects["CN"]["id"],
            topic="Beta networks",
            description="ZZOTHERSTUDENT concern about networks.",
            concept="Routing tables",
        )
        resource_ids.append(_create_resource(admin, dsa_id, "Topology Resource ZZ", "Topology", "Topology only."))
        resource_ids.append(_create_resource(
            admin,
            subjects["DBMS"]["id"],
            "Other Subject Recursion ZZ",
            "Recursion",
            "Wrong subject.",
        ))
        with SessionLocal() as session:
            for offset in range(30):
                session.add(AttendanceRecord(
                    student_id=student["id"],
                    subject_id=dsa_id,
                    session_date=date(2019, 1, 1) + timedelta(days=offset),
                    status="present" if offset % 2 == 0 else "absent",
                ))
            session.add(Feedback(
                student_id=student["id"],
                subject_id=dsa_id,
                topic="Historical feedback",
                difficult_topics="ZZHISTORICALFEEDBACK",
                preferred_format="books",
                created_at=datetime.now(timezone.utc),
            ))
            session.add(InternalAssessment(
                student_id=student["id"],
                subject_id=dsa_id,
                cat_1=41,
                assignment_1=41,
                cat_2=41,
                assignment_2=41,
                cat_3=41,
                assignment_3=41,
            ))
            session.add(ExternalExamination(student_id=student["id"], subject_id=dsa_id, raw_mark=73))
            session.add(StudyPlan(
                student_id=student["id"],
                source="student_edit",
                outline_text="ZZSTUDYPLANTEXT",
                created_at=datetime.now(timezone.utc),
            ))
            examination_id = session.scalar(select(Examination.id).limit(1))
            if examination_id is not None:
                session.add(Mark(
                    student_id=student["id"],
                    subject_id=dsa_id,
                    examination_id=examination_id,
                    marks_obtained=Decimal("17.00"),
                    maximum_marks=Decimal("40.00"),
                    pass_marks=Decimal("16.00"),
                ))
            session.commit()

        second, seen = _draft(admin, concern_id, monkeypatch)
        assert second.status_code == 200, second.text
        prompt = seen["prompt"]
        assert prompt == original
        assert len(prompt) <= MAX_PROMPT_LENGTH
        assert "Keep this recursion concern." in prompt
        assert "ZZOTHERCONCERN" not in prompt
        assert "ZZOTHERSTUDENT" not in prompt
        assert "ZZHISTORICALFEEDBACK" not in prompt
        assert "ZZSTUDYPLANTEXT" not in prompt
        assert "Zeddrafter Otherperson" not in prompt
        assert "Topology Resource ZZ" not in prompt
        assert "Noise00topic" not in prompt
        assert "cat_1" not in prompt
    finally:
        _delete_resources(resource_ids)
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_drafts_for_different_students_stay_separate(admin, monkeypatch):
    student_ids = []
    try:
        alpha = _create_student(admin, "Draft Alpha Student")
        beta = _create_student(admin, "Draft Beta Student")
        student_ids.extend([alpha["id"], beta["id"]])
        subjects = _subjects(admin)
        alpha_id = _insert_concern(
            alpha["id"],
            subjects["DSA"]["id"],
            topic="Alpha recursion",
            description="Alpha needs the recursive case explained.",
            concept="Alpha recursion trees",
        )
        beta_id = _insert_concern(
            beta["id"],
            subjects["CN"]["id"],
            topic="Beta networks",
            description="Beta needs routing explained.",
            concept="Beta routing tables",
        )
        alpha_response, alpha_seen = _draft(admin, alpha_id, monkeypatch, "Explain alpha recursion.")
        beta_response, beta_seen = _draft(admin, beta_id, monkeypatch, "Explain beta routing.")
        assert alpha_response.status_code == 200, alpha_response.text
        assert beta_response.status_code == 200, beta_response.text
        assert "Draft Alpha Student" in alpha_seen["prompt"]
        assert "Alpha recursion" in alpha_seen["prompt"]
        assert "Draft Beta Student" not in alpha_seen["prompt"]
        assert "Beta networks" not in alpha_seen["prompt"]
        assert "Draft Beta Student" in beta_seen["prompt"]
        assert "Draft Alpha Student" not in beta_seen["prompt"]
        assert len(alpha_seen["prompt"]) <= MAX_PROMPT_LENGTH
        assert len(beta_seen["prompt"]) <= MAX_PROMPT_LENGTH
    finally:
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_inactive_subject_concern_can_still_be_drafted(admin, monkeypatch):
    student_ids = []
    try:
        student = _create_student(admin, "Draft Inactive Student")
        student_ids.append(student["id"])
        with SessionLocal() as session:
            inactive = session.scalar(select(Subject).where(Subject.is_active.is_(False)).order_by(Subject.code))
            assert inactive is not None
            inactive_id = inactive.id
            inactive_name = inactive.name
        concern_id = _insert_concern(
            student["id"],
            inactive_id,
            topic="Retiredfactoringtopic",
            description="This historical concern remains on an inactive subject.",
            concept="Factoring expressions",
        )
        before = _snapshot(concern_id)
        response, seen = _draft(admin, concern_id, monkeypatch, "Explain factoring from the stored concern.")
        assert response.status_code == 200, response.text
        assert response.json()["facts"]["subject"] == inactive_name
        assert response.json()["facts"]["subject_is_active"] is False
        assert "Retiredfactoringtopic" in seen["prompt"]
        assert len(seen["prompt"]) <= MAX_PROMPT_LENGTH
        assert _snapshot(concern_id) == before
        with SessionLocal() as session:
            assert session.get(Subject, inactive_id).is_active is False
    finally:
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_missing_and_invalid_concern_ids_are_rejected(admin):
    missing = admin.post("/concerns/99999999/assistant/draft")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "No concern found with id 99999999."
    invalid = admin.post("/concerns/not-an-id/assistant/draft")
    assert invalid.status_code == 422


def test_student_cannot_draft_an_administrator_reply(admin, monkeypatch):
    student_ids = []
    try:
        student = _create_student(admin, "Draft Portal Student")
        student_ids.append(student["id"])
        access = admin.post(f"/students/{student['id']}/access", json={"password": "Draft-student-pass-1"})
        assert access.status_code == 200, access.text
        subject = _subjects(admin)["DSA"]
        concern_id = _insert_concern(student["id"], subject["id"])
        before = _snapshot(concern_id)

        def boom(prompt):
            raise AssertionError("Ollama was called")

        monkeypatch.setattr("app.records.generate_text", boom)
        with TestClient(app) as portal:
            signed_in = portal.post("/auth/login", json={
                "email": student["email"],
                "password": "Draft-student-pass-1",
                "portal": "student",
            })
            assert signed_in.status_code == 200, signed_in.text
            denied = portal.post(f"/concerns/{concern_id}/assistant/draft")
            assert denied.status_code == 403
            assert denied.json()["detail"] == "An administrator account is required."
        assert _snapshot(concern_id) == before
    finally:
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_ollama_failures_do_not_change_the_concern(admin, monkeypatch):
    student_ids = []
    try:
        student = _create_student(admin, "Draft Failure Student")
        student_ids.append(student["id"])
        concern_id = _insert_concern(student["id"], _subjects(admin)["DSA"]["id"])
        before = _snapshot(concern_id)

        def timeout(url, json, timeout):
            raise httpx.TimeoutException("timed out")

        monkeypatch.setattr(httpx, "post", timeout)
        timed_out = admin.post(f"/concerns/{concern_id}/assistant/draft")
        assert timed_out.status_code == 503
        assert "timed out" in timed_out.json()["detail"]
        assert _snapshot(concern_id) == before

        def unavailable(url, json, timeout):
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "post", unavailable)
        down = admin.post(f"/concerns/{concern_id}/assistant/draft")
        assert down.status_code == 503
        assert "not reachable" in down.json()["detail"]
        assert _snapshot(concern_id) == before
    finally:
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_oversized_draft_is_rejected_without_calling_the_model_or_changing_the_concern(admin, monkeypatch, caplog):
    student_ids = []
    try:
        student = _create_student(admin, "Draft Oversize Student")
        student_ids.append(student["id"])
        concern_id = _insert_concern(student["id"], _subjects(admin)["DSA"]["id"])
        before = _snapshot(concern_id)

        def huge(db, concern):
            return {"description": "SECRET-STUDENT-TEXT " + ("y" * 20000)}

        def boom(prompt):
            raise AssertionError("Ollama was called")

        monkeypatch.setattr("app.portal_routes.concern_draft_context", huge)
        monkeypatch.setattr("app.records.generate_text", boom)
        with caplog.at_level("WARNING", logger="app.assistant"):
            response = admin.post(f"/concerns/{concern_id}/assistant/draft")
        assert response.status_code == 422
        assert "too large" in response.json()["detail"]
        assert "not changed" in response.json()["detail"]
        assert "SECRET-STUDENT-TEXT" not in response.text
        assert "task=concern_draft" in caplog.text
        assert "SECRET-STUDENT-TEXT" not in caplog.text
        assert _snapshot(concern_id) == before
    finally:
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_stored_concern_drafts_stay_within_the_prompt_limit(admin):
    with SessionLocal() as session:
        concern_ids = list(session.scalars(select(Concern.id)).all())
        assert concern_ids
        for concern_id in concern_ids:
            concern = load_concern(session, concern_id)
            facts = concern_draft_context(session, concern)
            prompt = build_prompt(
                DRAFT_TASK,
                facts,
                task_name="concern_draft",
                rules=CONCERN_DRAFT_RULES,
            )
            assert len(prompt) <= MAX_PROMPT_LENGTH, concern_id
            assert len(facts["resources"]) <= 5
            assert "results" not in facts
            assert "attendance" not in facts
            assert "email" not in facts


def test_incomplete_subjects_are_unstored_scores_and_resources_remain_in_the_catalog(admin):
    student_ids = []
    resource_ids = []
    try:
        student = _create_student(admin, "Draft Incomplete Student")
        student_ids.append(student["id"])
        subject = _subjects(admin)["DSA"]
        resource_ids.append(_create_resource(
            admin,
            subject["id"],
            "Catalog Only Resource ZZ",
            "Sorting",
            "Stored for the subject, not invented.",
        ))
        with SessionLocal() as session:
            report = academic_report(session, student["id"])
            assert report["final_results"]
            assert {row["official_status"] for row in report["final_results"]} == {"incomplete"}
            assert all(row["final_mark"] is None for row in report["final_results"])
            stored = session.scalar(select(LearningResource).where(LearningResource.id == resource_ids[0]))
            assert stored is not None
            active_ids = {row["subject_id"] for row in report["final_results"]}
            catalog_count = session.scalar(
                select(func.count()).select_from(LearningResource).where(LearningResource.subject_id.in_(active_ids))
            )
            facts = assistant_bundle(session, student["id"])["facts"]
        titles = [item["title"] for item in facts["stored_resources"]]
        assert "Catalog Only Resource ZZ" not in titles
        assert catalog_count >= 1
        prompt = build_prompt(REPORT_TASK, facts, task_name="academic_report")
        assert len(prompt) <= MAX_PROMPT_LENGTH
        assert "none were selected for a failed or reported subject" in prompt
    finally:
        _delete_resources(resource_ids)
        for student_id in student_ids:
            admin.delete(f"/students/{student_id}")


def test_existing_academic_report_prompts_stay_within_the_limit(admin):
    with SessionLocal() as session:
        student_ids = list(session.scalars(select(Student.id)).all())
        assert student_ids
        for student_id in student_ids:
            facts = assistant_bundle(session, student_id)["facts"]
            prompt = build_prompt(REPORT_TASK, facts, task_name="academic_report")
            assert len(prompt) <= MAX_PROMPT_LENGTH, f"student {student_id} prompt length {len(prompt)}"
