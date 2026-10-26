"""Tests for prompt construction and Ollama error handling.

The model itself is not required. HTTP calls are replaced with fakes.
"""

import logging

import httpx
import pytest

from app.assistant import (
    CONCERN_DRAFT_RULES,
    DRAFT_TASK,
    MAX_PROMPT_LENGTH,
    REQUEST_TIMEOUT_SECONDS,
    AssistantUnavailable,
    base_url,
    build_concern_draft_facts,
    build_facts,
    build_prompt,
    clean_question,
    clip_text,
    generate_text,
    model_name,
)
from app.records import select_draft_resources
from app.schemas import FeedbackWrite, MarkWrite, QuestionWrite, ResourceWrite, StudentWrite
from app.validation import clean_https_url


def sample_facts():
    return build_facts(
        {"full_name": "Asha Raman", "admission_number": "ADM-1001", "email": "asha.raman@example.edu"},
        [{
            "subject_name": "Mathematics",
            "examination_name": "Final Examination",
            "held_on": "2026-06-20",
            "marks_obtained": "68.00",
            "maximum_marks": "100.00",
            "pass_marks": "40.00",
            "percentage": "68.00",
            "official_status": "pass",
            "guidance_label": "developing",
            "previous_result": {
                "percentage": "38.00",
                "percentage_change": "30.00",
                "direction": "improved",
            },
        }],
        [{
            "subject_name": "Database Management",
            "topic": "SELECT queries",
            "difficult_topics": "Writing SELECT queries is difficult.",
            "explanation_request": None,
            "practice_request": None,
            "preferred_format": "videos",
            "resource_note": None,
            "resource_rating": None,
        }],
        [{
            "title": "PostgreSQL Tutorial",
            "resource_type": "website",
            "author": "PostgreSQL Global Development Group",
            "subject_name": "Database Management",
            "topic": "SQL",
            "url": "https://www.postgresql.org/docs/current/tutorial.html",
            "verification_status": "verified",
        }],
        {"source": "academic_rules", "items": [], "note": "Outline note."},
        attendance={"sessions": 6, "attended": 5, "absent": 1, "percentage": "83.33", "by_subject": []},
        overall={"marks_counted": 1, "percentage": "68.00"},
    )


def test_prompt_contains_facts_and_not_secrets():
    facts = sample_facts()
    prompt = build_prompt("Summarize the results.", facts, "Which subject improved?")
    assert "68.00" in prompt
    assert "83.33" in prompt
    assert "overall_percentage" in prompt
    assert "official_status" in prompt
    assert "Not a verified academic fact." in prompt
    assert "asha.raman@example.edu" not in prompt
    assert "postgresql+psycopg://" not in prompt
    assert "password" not in prompt.lower()


def test_question_limits():
    assert clean_question("  Which subject failed? ") == "Which subject failed?"
    with pytest.raises(ValueError):
        clean_question("   ")
    with pytest.raises(ValueError):
        clean_question("a" * 1001)


def test_model_name_and_base_url_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/")
    assert model_name() == "qwen3:8b"
    assert base_url() == "http://localhost:11434"


def test_generate_text_reads_the_model_response(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"response": " Mathematics improved from 38.00% to 68.00%."}

    def fake_post(url, json, timeout):
        assert url.endswith("/api/generate")
        assert json["model"] == model_name()
        assert json["stream"] is False
        assert json["think"] is False
        assert timeout == REQUEST_TIMEOUT_SECONDS
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    assert "68.00%" in generate_text("Explain the facts.")


def test_generate_text_reports_timeout_and_missing_model(monkeypatch):
    def fake_timeout(url, json, timeout):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "post", fake_timeout)
    with pytest.raises(AssistantUnavailable, match="timed out"):
        generate_text("Explain the facts.")

    class MissingModel:
        status_code = 404

        def json(self):
            return {"error": "model not found"}

    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: MissingModel())
    with pytest.raises(AssistantUnavailable, match="not installed"):
        generate_text("Explain the facts.")

    class EmptyAnswer:
        status_code = 200

        def json(self):
            return {"response": "  "}

    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: EmptyAnswer())
    with pytest.raises(AssistantUnavailable, match="empty answer"):
        generate_text("Explain the facts.")

    def fake_down(url, json, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", fake_down)
    with pytest.raises(AssistantUnavailable, match="not reachable"):
        generate_text("Explain the facts.")


def test_request_models_reject_bad_input():
    with pytest.raises(Exception):
        StudentWrite(admission_number="ADM-9", full_name="Test Student", email="not-an-email")
    with pytest.raises(Exception):
        MarkWrite(
            student_id=1,
            subject_id=1,
            examination_id=1,
            marks_obtained="11",
            maximum_marks="10",
            pass_marks="5",
        )
    with pytest.raises(Exception):
        FeedbackWrite(preferred_format="podcasts", difficult_topics="Algebra is hard.")
    with pytest.raises(Exception):
        FeedbackWrite(preferred_format="videos")
    with pytest.raises(Exception):
        QuestionWrite(question=" ")
    accepted = StudentWrite(admission_number=" adm-9 ", full_name=" Test Student ", email="Test.Student@Example.EDU")
    assert accepted.email == "test.student@example.edu"
    assert accepted.admission_number == "adm-9"
    plain = "https://en.wikipedia.org/wiki/Markdown_(markup)"
    assert clean_https_url(plain) == plain
    long_url = "https://www.scribd.com/document/" + ("9" * 80) + "/College-Algebra"
    wrapped = f"[College Algebra notes]({long_url})"
    assert len(wrapped) > 40
    assert clean_https_url(wrapped) == long_url
    assert clean_https_url(f"<{long_url}>") == long_url
    resource = ResourceWrite(
        title="College Algebra",
        resource_type="website",
        subject_id=1,
        topic="algebra",
        url=wrapped,
        description="Pasted as a Markdown link.",
        verification_status="unverified",
    )
    assert resource.url == long_url
    with pytest.raises(Exception):
        clean_https_url("javascript:alert(1)")


def test_concern_text_keeps_its_meaning_inside_the_field_limit():
    description = "Core recursion request. " + ("n" * 1100)
    kept = clip_text(description, 1000)
    assert kept.startswith("Core recursion request.")
    assert kept.endswith("…")
    assert len(kept) <= 1000
    exact = ("Core recursion request. " + ("n" * 1100))[:1000]
    assert clip_text(exact, 1000) == exact


def test_concern_draft_facts_are_limited_to_one_concern():
    long_url = "https://example.edu/" + ("a" * 180) + "LONGURLTAIL"
    description = "Recursion notes. " + ("x" * 260) + "TAILMARKER"
    resources = [
        {
            "title": f"Recursion Resource {index:02d}",
            "resource_type": "website",
            "subject_name": "Data Structures and Algorithms",
            "topic": "Recursion",
            "url": long_url if index == 1 else "https://example.edu/recursion",
            "verification_status": "unverified",
            "description": description,
            "email": "student@example.edu",
        }
        for index in range(1, 9)
    ]
    facts = build_concern_draft_facts(
        student_name="Draft Target Student",
        subject_name="Data Structures and Algorithms",
        subject_is_active=True,
        topic="Recursion",
        description="Core recursion request. " + ("detail " * 200),
        concept="Core recursion concept.",
        assistance_requested="explanation",
        preferred_format="examples",
        status="submitted",
        priority="high",
        resources=resources,
    )
    assert len(facts["resources"]) == 5
    assert facts["student_name"] == "Draft Target Student"
    assert "email" not in facts
    assert "student@example.edu" not in str(facts)
    assert facts["description"].startswith("Core recursion request.")
    assert facts["concept"] == "Core recursion concept."
    assert facts["resources"][0]["description"].startswith("Recursion notes.")
    assert "TAILMARKER" not in facts["resources"][0]["description"]
    assert "url" not in facts["resources"][0]
    assert "LONGURLTAIL" not in str(facts)
    assert facts["resources"][0]["url_note"]
    assert facts["resources"][1]["url"] == "https://example.edu/recursion"
    prompt = build_prompt(DRAFT_TASK, facts, task_name="concern_draft", rules=CONCERN_DRAFT_RULES)
    assert len(prompt) <= MAX_PROMPT_LENGTH
    assert "rule_based_outline" not in prompt
    assert "cat_1" not in prompt


def test_draft_resource_selection_ignores_other_subjects_and_extra_matches():
    catalog = [
        {"id": index, "subject_id": 7, "title": f"Recursion Resource {index:02d}", "topic": "Recursion"}
        for index in range(1, 9)
    ]
    catalog.append({"id": 20, "subject_id": 7, "title": "Graph Theory Resource", "topic": "Graph theory"})
    catalog.append({"id": 21, "subject_id": 8, "title": "Recursion Resource Other Subject", "topic": "Recursion"})
    selected = select_draft_resources(catalog, 7, "Recursion", "Recursion trees")
    titles = [item["title"] for item in selected]
    assert titles == [f"Recursion Resource {index:02d}" for index in range(1, 6)]
    assert select_draft_resources(catalog, 7, "Queues", "Array index") == []


def test_oversized_prompt_logs_the_task_and_length_without_student_text(caplog):
    facts = {"description": "SECRET-STUDENT-TEXT " * 2000}
    with caplog.at_level(logging.WARNING, logger="app.assistant"):
        with pytest.raises(ValueError, match="The assistant request is too large"):
            build_prompt("Draft a reply.", facts, task_name="concern_draft")
    assert "task=concern_draft" in caplog.text
    assert "length=" in caplog.text
    assert "SECRET-STUDENT-TEXT" not in caplog.text


def test_generate_text_rejects_an_oversized_prompt_before_calling_ollama(monkeypatch, caplog):
    def boom(url, json, timeout):
        raise AssertionError("Ollama was called")

    monkeypatch.setattr(httpx, "post", boom)
    with caplog.at_level(logging.WARNING, logger="app.assistant"):
        with pytest.raises(ValueError, match="too large"):
            generate_text("x" * (MAX_PROMPT_LENGTH + 1))
    assert "task=generate_text" in caplog.text
    assert "x" * 50 not in caplog.text
