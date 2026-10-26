"""Talk to the local Ollama model.

The model explains facts that Python has already calculated. It does not
receive a database password, and its reply is not stored as an official result.
"""

import json
import os

import httpx

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_BASE_URL = "http://localhost:11434"
MAX_QUESTION_LENGTH = 1000
MAX_PROMPT_LENGTH = 12000
REQUEST_TIMEOUT_SECONDS = 180

REPORT_TASK = (
    "Write a short academic summary in plain language. "
    "Repeat each subject's stored internal mark, external mark, final mark, grade, and pass, fail, or incomplete status. "
    "Do not recalculate them. Do not mention GPA or CGPA. "
    "Mention reported concerns only as reports from the student."
)
SUGGESTIONS_TASK = (
    "Explain the difficult concepts the student reported. "
    "Suggest what to revise and one practical activity for each subject that failed, needs attention, or was reported as difficult. "
    "Use stored resources only when they appear in the facts. Do not invent titles or URLs."
)
PLAN_TASK = (
    "Explain the study plan the student is looking at. "
    "When displayed_plan is present, explain that text. Otherwise explain the rule-based outline. "
    "Do not add subjects that are absent from that plan. "
    "Do not change stored marks, official status, or attendance. "
    "Use the stored attendance percentage when it is present."
)
ASK_TASK = (
    "Answer the question using only the facts. "
    "When the question asks for a mark, attendance percentage, or pass result, repeat the stored value."
)

RULES = """
You are a study assistant for one student in Semester 1 Computer Science.
The active subjects are Data Structures and Algorithms, Database Management Systems, Data Science, Artificial Intelligence and Machine Learning, and Computer Networks.
Use only the JSON facts below.
Official marks and grades are already calculated. Do not recalculate or change them.
A missing CAT, assignment, or external mark is incomplete. It is not zero.
Do not calculate or mention GPA or CGPA.
Do not invent marks, attendance, assessment dates, concerns, book titles, authors, video titles, or URLs.
Do not claim anything about the student's ability, effort, motivation, or personal life.
Student feedback is what the student reported. It is not a verified academic fact.
A guidance label is not an official pass or fail.
If a fact is missing, say that it is not available.
Recommend a stored resource only for the subject it belongs to.
Do not say a plan or resource was saved unless the facts say it is saved.
Keep the answer concise and practical.
""".strip()


class AssistantUnavailable(Exception):
    """The local model could not answer. The rest of the application can continue."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def model_name() -> str:
    """Return the configured model name. The project default is qwen2.5:3b."""
    configured = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL).strip()
    return configured or DEFAULT_MODEL


def base_url() -> str:
    """Return the local Ollama address without a trailing slash."""
    configured = os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).strip()
    return (configured or DEFAULT_BASE_URL).rstrip("/")


def clean_question(question: str) -> str:
    """Reject an empty or very long question before it is sent to the model."""
    text = (question or "").strip()
    if not text:
        raise ValueError("A question is required.")
    if len(text) > MAX_QUESTION_LENGTH:
        raise ValueError(f"A question must be {MAX_QUESTION_LENGTH} characters or fewer.")
    return text


def build_facts(
    student: dict,
    results: list[dict],
    feedback: list[dict],
    resources: list[dict],
    outline: dict,
    attendance: dict | None = None,
    overall: dict | None = None,
) -> dict:
    """Copy only the fields the model needs. Email and database settings stay out."""
    compact_results = []
    for result in results:
        if result.get("grade") is not None or result.get("assessment_status") == "incomplete" or "external_raw" in result:
            compact_results.append(
                {
                    "subject": result["subject_name"],
                    "examination": "Semester 1",
                    "marks_obtained": "Not recorded" if result.get("final_mark") is None else str(result["final_mark"]),
                    "maximum_marks": "100",
                    "percentage": "Not recorded" if result.get("final_mark") is None else str(result["final_mark"]),
                    "official_status": result["official_status"],
                    "guidance_label": result["guidance_label"],
                    "grade": result.get("grade"),
                    "internal_mark": None if result.get("internal_mark") is None else str(result["internal_mark"]),
                    "external_mark": None if result.get("external_mark") is None else str(result["external_mark"]),
                    "final_mark": None if result.get("final_mark") is None else str(result["final_mark"]),
                    "external_raw": result.get("external_raw"),
                    "cat_1": result.get("cat_1"),
                    "assignment_1": result.get("assignment_1"),
                    "cat_2": result.get("cat_2"),
                    "assignment_2": result.get("assignment_2"),
                    "cat_3": result.get("cat_3"),
                    "assignment_3": result.get("assignment_3"),
                    "assessment_status": result.get("assessment_status"),
                }
            )
            continue
        previous = result.get("previous_result")
        compact_results.append(
            {
                "subject": result["subject_name"],
                "examination": result["examination_name"],
                "date": str(result["held_on"]),
                "marks_obtained": str(result["marks_obtained"]),
                "maximum_marks": str(result["maximum_marks"]),
                "pass_marks": None if result["pass_marks"] is None else str(result["pass_marks"]),
                "percentage": str(result["percentage"]),
                "official_status": result["official_status"],
                "guidance_label": result["guidance_label"],
                "previous_percentage": None if previous is None else str(previous["percentage"]),
                "percentage_change": None if previous is None else str(previous["percentage_change"]),
                "direction": None if previous is None else previous["direction"],
            }
        )
    compact_feedback = []
    for item in feedback:
        compact_feedback.append(
            {
                "subject": item.get("subject_name"),
                "topic": item.get("topic"),
                "reported_difficulty": item.get("difficult_topics"),
                "requested_explanation": item.get("explanation_request"),
                "requested_practice": item.get("practice_request"),
                "preferred_format": item.get("preferred_format"),
                "resource_comment": item.get("resource_note"),
                "resource_rating": item.get("resource_rating"),
                "meaning": "Reported by the student. Not a verified academic fact.",
            }
        )
    compact_resources = []
    for resource in resources:
        compact_resources.append(
            {
                "title": resource["title"],
                "type": resource["resource_type"],
                "author": resource.get("author"),
                "subject": resource["subject_name"],
                "topic": resource["topic"],
                "url": resource["url"],
                "verification_status": resource["verification_status"],
            }
        )
    facts = {
        "student_name": student["full_name"],
        "admission_number": student["admission_number"],
        "results": compact_results,
        "student_reported_feedback": compact_feedback,
        "stored_resources": compact_resources,
        "rule_based_outline": outline,
    }
    if overall is not None:
        facts["overall_percentage"] = overall
    if attendance is not None:
        facts["attendance"] = attendance
    return facts


def build_prompt(task: str, facts: dict, question: str | None = None) -> str:
    """Combine the fixed rules, one task, and the limited facts."""
    facts_json = json.dumps(facts, indent=2, default=str)
    question_text = ""
    if question:
        question_text = "\n\nQuestion:\n" + clean_question(question)
    prompt = f"{RULES}\n\nTask:\n{task.strip()}{question_text}\n\nFacts:\n{facts_json}"
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError("The assistant request is too large.")
    return prompt


def assistant_status() -> dict:
    """Check whether Ollama is running and whether the selected model is installed."""
    model = model_name()
    try:
        response = httpx.get(f"{base_url()}/api/tags", timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException:
        return {"reachable": False, "model": model, "installed": False, "detail": "Ollama did not answer before the timeout."}
    except httpx.HTTPError as exc:
        return {"reachable": False, "model": model, "installed": False, "detail": f"Ollama is not reachable: {exc.__class__.__name__}."}

    names = [item.get("name", "") for item in payload.get("models", [])]
    installed = model in names
    detail = "The selected model is installed." if installed else f"{model} is not installed. Pull it with ollama before using the assistant."
    return {"reachable": True, "model": model, "installed": installed, "detail": detail}


def generate_text(prompt: str) -> str:
    """Send one prompt to Ollama and return the text it produced."""
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError("The assistant request is too large.")
    try:
        response = httpx.post(
            f"{base_url()}/api/generate",
            json={
                "model": model_name(),
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.2, "num_predict": 500},
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise AssistantUnavailable("The local model timed out. Student records are still available.") from exc
    except httpx.HTTPError as exc:
        raise AssistantUnavailable("The local model is not reachable. Student records are still available.") from exc

    if response.status_code == 404:
        raise AssistantUnavailable(f"The model {model_name()} is not installed. Run: ollama pull {model_name()}")
    if response.status_code >= 400:
        raise AssistantUnavailable(f"Ollama returned HTTP {response.status_code}. Student records are still available.")

    try:
        body = response.json()
    except ValueError as exc:
        raise AssistantUnavailable("Ollama returned a response that was not JSON.") from exc
    text = str(body.get("response", "")).strip()
    if not text:
        raise AssistantUnavailable("The local model returned an empty answer.")
    return text
