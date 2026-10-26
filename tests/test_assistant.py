"""Tests for prompt construction and Ollama error handling.

The model itself is not required. HTTP calls are replaced with fakes.
"""

import httpx
import pytest

from app.assistant import (
    REQUEST_TIMEOUT_SECONDS,
    AssistantUnavailable,
    base_url,
    build_facts,
    build_prompt,
    clean_question,
    generate_text,
    model_name,
)
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
