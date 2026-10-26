"""Shapes of the JSON returned by the read endpoints.

Pydantic checks that each response has the expected fields before FastAPI
sends it. Decimal scores are sent as strings with two decimal places so the
JSON does not turn them into binary floating-point numbers.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from app.calculations import validate_mark_values
from app.validation import (
    clean_assistance_type,
    clean_attendance_status,
    clean_concern_status,
    clean_email,
    clean_exam_type,
    clean_https_url,
    clean_password,
    clean_preferred_format,
    clean_priority,
    clean_resource_rating,
    clean_resource_type,
    clean_text,
    clean_verification_status,
    clean_whole_number,
)


def _score_to_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


DecimalScore = Annotated[
    Decimal,
    PlainSerializer(_score_to_json, return_type=str, when_used="json"),
]
OptionalDecimalScore = Annotated[
    Decimal | None,
    PlainSerializer(_score_to_json, return_type=str | None, when_used="json"),
]


class StudentRead(BaseModel):
    """A student row returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    admission_number: str
    full_name: str
    email: str
    department: str | None = None
    year_or_semester: str | None = None
    is_active: bool = True
    is_demo: bool = False


class SubjectRead(BaseModel):
    """A subject row returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    is_active: bool = True


class ExaminationRead(BaseModel):
    """An examination row returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    exam_type: str
    held_on: date | None = None
    is_active: bool = True


class PreviousResult(BaseModel):
    """The most recent earlier result used for a percentage comparison."""

    examination_id: int
    examination_name: str
    exam_type: str
    held_on: date
    percentage: DecimalScore
    official_status: str
    percentage_change: DecimalScore
    direction: str


class AcademicResult(BaseModel):
    """One calculated result. The numbers come from Python, not from the model."""

    mark_id: int
    subject_id: int
    subject_code: str
    subject_name: str
    examination_id: int
    examination_name: str
    exam_type: str
    held_on: date
    marks_obtained: DecimalScore
    maximum_marks: DecimalScore
    pass_marks: OptionalDecimalScore
    percentage: DecimalScore
    official_status: str = Field(
        description="pass, fail, or not_assessed. fail is used only when a pass mark exists and the score is below it."
    )
    guidance_label: str = Field(
        description="strong, developing, or needs_attention. This is study guidance, not an official result."
    )
    explanation: str
    history_note: str
    previous_result: PreviousResult | None


class AggregateSummary(BaseModel):
    """The overall percentage. Missing assessments are omitted, not scored as zero."""

    marks_counted: int
    marks_obtained: OptionalDecimalScore
    maximum_marks: OptionalDecimalScore
    percentage: OptionalDecimalScore
    method: str


class InternalAssessmentView(BaseModel):
    """Table A. Raw scores stay separate from the calculated internal mark."""

    subject_id: int
    subject_code: str
    subject_name: str
    cat_1: int | None
    assignment_1: int | None
    cat_2: int | None
    assignment_2: int | None
    cat_3: int | None
    assignment_3: int | None
    internal_mark: str | None
    assessment_status: str


class ExternalAssessmentView(BaseModel):
    """Table B. The raw mark out of 100 is stored separately from the converted mark."""

    subject_id: int
    subject_code: str
    subject_name: str
    external_raw: int | None
    external_mark: str | None
    assessment_status: str


class FinalSubjectView(BaseModel):
    """Table C. Grade and pass or fail come from the calculated final mark."""

    subject_id: int
    subject_code: str
    subject_name: str
    internal_mark: str | None
    external_mark: str | None
    final_mark: str | None
    grade: str | None
    official_status: str


class AcademicReport(BaseModel):
    """The Semester 1 Computer Science report. It does not include GPA or CGPA."""

    department: str
    semester: str
    rounding_rule: str
    internal_assessments: list[InternalAssessmentView]
    external_examinations: list[ExternalAssessmentView]
    final_results: list[FinalSubjectView]


class StudentResults(BaseModel):
    """A student, earlier examination rows, and the official Semester 1 report."""

    student: StudentRead
    results: list[AcademicResult]
    aggregate: AggregateSummary
    academic_report: AcademicReport


class StudentWrite(BaseModel):
    """Fields an administrator sends when creating or replacing a student."""

    admission_number: str
    full_name: str
    email: str
    department: str | None = None
    year_or_semester: str | None = None
    is_active: bool = True

    @field_validator("department")
    @classmethod
    def department_length(cls, value: str | None) -> str | None:
        return clean_text(value, "department", 120)

    @field_validator("year_or_semester")
    @classmethod
    def year_length(cls, value: str | None) -> str | None:
        return clean_text(value, "year_or_semester", 40)

    @field_validator("admission_number")
    @classmethod
    def admission_number_is_present(cls, value: str) -> str:
        cleaned = clean_text(value, "admission_number", 30, required=True)
        return cleaned

    @field_validator("full_name")
    @classmethod
    def full_name_is_present(cls, value: str) -> str:
        return clean_text(value, "full_name", 120, required=True)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return clean_email(value)


class SubjectWrite(BaseModel):
    """Fields used to create or replace a subject."""

    code: str
    name: str
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def code_is_present(cls, value: str) -> str:
        return clean_text(value, "code", 20, required=True).upper()

    @field_validator("name")
    @classmethod
    def name_is_present(cls, value: str) -> str:
        return clean_text(value, "name", 120, required=True)


class ExaminationWrite(BaseModel):
    """Fields used to create or replace one of the three examination types."""

    name: str
    exam_type: str
    held_on: date | None = None

    @field_validator("name")
    @classmethod
    def name_is_present(cls, value: str) -> str:
        return clean_text(value, "name", 120, required=True)

    @field_validator("exam_type")
    @classmethod
    def exam_type_is_known(cls, value: str) -> str:
        return clean_exam_type(value)

    @model_validator(mode="after")
    def name_matches_the_type(self):
        from app.models import EXAM_TYPE_NAMES

        expected = EXAM_TYPE_NAMES[self.exam_type]
        if self.name != expected:
            raise ValueError(f"The name for this examination type must be {expected}.")
        return self


class MarkWrite(BaseModel):
    """Raw scores for one student, subject, and examination."""

    student_id: int
    subject_id: int
    examination_id: int
    marks_obtained: Decimal
    maximum_marks: Decimal
    pass_marks: Decimal | None = None

    @model_validator(mode="after")
    def scores_are_possible(self):
        validate_mark_values(self.marks_obtained, self.maximum_marks, self.pass_marks)
        return self


class InternalAssessmentWrite(BaseModel):
    """Six raw internal scores. Each one is a whole number from 0 through 50, or missing."""

    subject_id: int
    cat_1: int | None = None
    assignment_1: int | None = None
    cat_2: int | None = None
    assignment_2: int | None = None
    cat_3: int | None = None
    assignment_3: int | None = None

    @field_validator("cat_1", "assignment_1", "cat_2", "assignment_2", "cat_3", "assignment_3", mode="before")
    @classmethod
    def component_is_a_whole_number(cls, value, info):
        return clean_whole_number(value, info.field_name, 50)


class ExternalExaminationWrite(BaseModel):
    """One external raw mark. It is a whole number from 0 through 100, or missing."""

    subject_id: int
    raw_mark: int | None = None

    @field_validator("raw_mark", mode="before")
    @classmethod
    def raw_mark_is_a_whole_number(cls, value):
        return clean_whole_number(value, "raw_mark", 100)


class FeedbackWrite(BaseModel):
    """Learning feedback reported by a student. This is not an official result."""

    subject_id: int | None = None
    topic: str | None = None
    difficult_topics: str | None = None
    explanation_request: str | None = None
    practice_request: str | None = None
    preferred_format: str
    resource_note: str | None = None
    resource_rating: str | None = None

    @field_validator("topic")
    @classmethod
    def topic_length(cls, value: str | None) -> str | None:
        return clean_text(value, "topic", 120)

    @field_validator("difficult_topics", "explanation_request", "practice_request", "resource_note")
    @classmethod
    def note_length(cls, value: str | None) -> str | None:
        return clean_text(value, "feedback text", 500)

    @field_validator("preferred_format")
    @classmethod
    def format_is_known(cls, value: str) -> str:
        return clean_preferred_format(value)

    @field_validator("resource_rating")
    @classmethod
    def rating_is_known(cls, value: str | None) -> str | None:
        return clean_resource_rating(value)

    @model_validator(mode="after")
    def at_least_one_comment(self):
        comments = (
            self.difficult_topics,
            self.explanation_request,
            self.practice_request,
            self.resource_note,
        )
        if not any(comments):
            raise ValueError("Feedback needs a difficulty, an explanation request, a practice request, or a resource note.")
        return self


class FeedbackRead(BaseModel):
    """One stored feedback row, including the reminder that the student reported it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    subject_id: int | None
    subject_name: str | None = None
    topic: str | None
    difficult_topics: str | None
    explanation_request: str | None
    practice_request: str | None
    preferred_format: str
    resource_note: str | None
    resource_rating: str | None
    created_at: datetime
    reported_by_student: bool = True


class ResourceRead(BaseModel):
    """A curated resource. verified means the link was checked, not that a model invented it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    resource_type: str
    author: str | None
    subject_id: int
    subject_name: str | None = None
    topic: str
    url: str
    description: str
    verification_status: str
    last_checked: date | None


class PlanExplainWrite(BaseModel):
    """The plan currently shown on the page, so the model explains that text."""

    plan_text: str | None = None

    @field_validator("plan_text")
    @classmethod
    def plan_text_limit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if len(text) > 8000:
            raise ValueError("The study plan must be 8000 characters or fewer.")
        return text or None


class StudyPlanWrite(BaseModel):
    """The study plan text the student edited. Omit it to store the rule-based outline."""

    outline_text: str | None = None

    @field_validator("outline_text")
    @classmethod
    def outline_text_is_usable(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("The study plan cannot be empty.")
        if len(text) > 8000:
            raise ValueError("The study plan must be 8000 characters or fewer.")
        return text


class QuestionWrite(BaseModel):
    """A question about one student's stored records."""

    question: str

    @field_validator("question")
    @classmethod
    def question_limit(cls, value: str) -> str:
        from app.assistant import clean_question

        return clean_question(value)


class AssistantAnswer(BaseModel):
    """The model narrative, kept separate from the official facts."""

    notice: str
    model: str
    narrative: str
    facts: dict


class LoginWrite(BaseModel):
    """Email and password for an existing account."""

    email: str
    password: str
    portal: str | None = None

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("password")
    @classmethod
    def password_is_present(cls, value: str) -> str:
        if not value:
            raise ValueError("Password is required.")
        return value

    @field_validator("portal")
    @classmethod
    def portal_is_known(cls, value: str | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        cleaned = str(value).strip().lower()
        if cleaned not in ("student", "admin"):
            raise ValueError("portal must be student or admin.")
        return cleaned


class PasswordChangeWrite(BaseModel):
    """Replace the signed-in account's password. The old password must match."""

    current_password: str
    new_password: str
    new_password_confirmation: str

    @field_validator("current_password")
    @classmethod
    def current_password_is_present(cls, value: str) -> str:
        if not value:
            raise ValueError("Current password is required.")
        return value

    @field_validator("new_password")
    @classmethod
    def new_password_is_strong_enough(cls, value: str) -> str:
        return clean_password(value)

    @model_validator(mode="after")
    def confirmation_matches(self):
        if self.new_password != self.new_password_confirmation:
            raise ValueError("Password confirmation does not match.")
        return self


class RegisterWrite(BaseModel):
    """Public student registration. Role is not part of this form."""

    full_name: str
    admission_number: str
    email: str
    password: str
    password_confirmation: str
    department: str | None = None
    year_or_semester: str | None = None

    @field_validator("full_name")
    @classmethod
    def full_name_is_present(cls, value: str) -> str:
        return clean_text(value, "full_name", 120, required=True)

    @field_validator("admission_number")
    @classmethod
    def admission_number_is_present(cls, value: str) -> str:
        return clean_text(value, "admission_number", 30, required=True)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("department")
    @classmethod
    def department_length(cls, value: str | None) -> str | None:
        return clean_text(value, "department", 120)

    @field_validator("year_or_semester")
    @classmethod
    def year_length(cls, value: str | None) -> str | None:
        return clean_text(value, "year_or_semester", 40)

    @field_validator("password")
    @classmethod
    def password_is_strong_enough(cls, value: str) -> str:
        return clean_password(value)

    @model_validator(mode="after")
    def confirmation_matches(self):
        if self.password != self.password_confirmation:
            raise ValueError("Password confirmation does not match.")
        return self


class ProfileWrite(BaseModel):
    """Profile fields a student is allowed to change."""

    full_name: str
    email: str
    department: str | None = None
    year_or_semester: str | None = None

    @field_validator("full_name")
    @classmethod
    def full_name_is_present(cls, value: str) -> str:
        return clean_text(value, "full_name", 120, required=True)

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, value: str) -> str:
        return clean_email(value)

    @field_validator("department")
    @classmethod
    def department_length(cls, value: str | None) -> str | None:
        return clean_text(value, "department", 120)

    @field_validator("year_or_semester")
    @classmethod
    def year_length(cls, value: str | None) -> str | None:
        return clean_text(value, "year_or_semester", 40)


class PasswordWrite(BaseModel):
    """A new password chosen by an administrator. It is stored only as a hash."""

    password: str

    @field_validator("password")
    @classmethod
    def password_is_strong_enough(cls, value: str) -> str:
        return clean_password(value)


class AttendanceUpdate(BaseModel):
    """Change the status of one stored session."""

    status: str

    @field_validator("status")
    @classmethod
    def status_is_known(cls, value: str) -> str:
        return clean_attendance_status(value)


class AttendanceWrite(BaseModel):
    """One class session."""

    student_id: int
    subject_id: int
    session_date: date
    status: str

    @field_validator("status")
    @classmethod
    def status_is_known(cls, value: str) -> str:
        return clean_attendance_status(value)


class ConcernWrite(BaseModel):
    """A concern submitted by the signed-in student."""

    subject_id: int
    topic: str
    description: str
    concept: str
    assistance_type: str
    preferred_format: str
    priority: str = "normal"

    @field_validator("topic")
    @classmethod
    def topic_is_present(cls, value: str) -> str:
        return clean_text(value, "topic", 120, required=True)

    @field_validator("description")
    @classmethod
    def description_is_present(cls, value: str) -> str:
        return clean_text(value, "description", 1000, required=True)

    @field_validator("concept")
    @classmethod
    def concept_is_present(cls, value: str) -> str:
        return clean_text(value, "concept", 300, required=True)

    @field_validator("assistance_type")
    @classmethod
    def assistance_is_known(cls, value: str) -> str:
        return clean_assistance_type(value)

    @field_validator("preferred_format")
    @classmethod
    def format_is_known(cls, value: str) -> str:
        return clean_preferred_format(value)

    @field_validator("priority")
    @classmethod
    def priority_is_known(cls, value: str) -> str:
        return clean_priority(value)


class ConcernDetailWrite(BaseModel):
    """Extra detail from the student. This does not change the workflow status."""

    message: str

    @field_validator("message")
    @classmethod
    def message_is_present(cls, value: str) -> str:
        return clean_text(value, "message", 1000, required=True)


class ConcernResponseWrite(BaseModel):
    """An administrator's reply, status change, and optional resource links."""

    message: str
    status: str | None = None
    priority: str | None = None
    resource_ids: list[int] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def message_is_present(cls, value: str) -> str:
        return clean_text(value, "message", 1000, required=True)

    @field_validator("status")
    @classmethod
    def status_is_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_concern_status(value)

    @field_validator("priority")
    @classmethod
    def priority_is_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_priority(value)


class ResourceWrite(BaseModel):
    """A curated resource. verified is allowed only with the date it was checked."""

    title: str
    resource_type: str
    author: str | None = None
    subject_id: int
    topic: str
    url: str
    description: str
    verification_status: str = "unverified"
    last_checked: date | None = None

    @field_validator("title")
    @classmethod
    def title_is_present(cls, value: str) -> str:
        return clean_text(value, "title", 200, required=True)

    @field_validator("author")
    @classmethod
    def author_length(cls, value: str | None) -> str | None:
        return clean_text(value, "author", 200)

    @field_validator("topic")
    @classmethod
    def topic_is_present(cls, value: str) -> str:
        return clean_text(value, "topic", 120, required=True)

    @field_validator("description")
    @classmethod
    def description_is_present(cls, value: str) -> str:
        return clean_text(value, "description", 500, required=True)

    @field_validator("resource_type")
    @classmethod
    def type_is_known(cls, value: str) -> str:
        return clean_resource_type(value)

    @field_validator("url")
    @classmethod
    def url_is_http(cls, value: str) -> str:
        return clean_https_url(value)

    @field_validator("verification_status")
    @classmethod
    def verification_is_known(cls, value: str) -> str:
        return clean_verification_status(value)

    @model_validator(mode="after")
    def verified_resources_have_a_check_date(self):
        if self.verification_status == "verified" and self.last_checked is None:
            raise ValueError("A verified resource needs the date the link was checked.")
        return self
