"""Academic tables.

A mark joins one student, one subject, and one examination. The database
allows only one mark for the same student, subject, and examination.
Percentage is not stored. Python calculates it when a result is requested.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# FAT, Assignment, and End Semester Examination are the only types that can be
# created or shown as current. Older type codes stay valid so historical rows
# do not have to be deleted.
ACTIVE_EXAM_TYPES = ("fat", "assignment", "end_semester")
EXAM_TYPE_NAMES = {
    "fat": "FAT",
    "assignment": "Assignment",
    "end_semester": "End Semester Examination",
}
EXAM_TYPES = ACTIVE_EXAM_TYPES + ("midterm", "final", "quiz")
PREFERRED_FORMATS = ("videos", "books", "examples", "exercises")
RESOURCE_RATINGS = ("useful", "unhelpful")
RESOURCE_TYPES = ("book", "website", "course", "video")
VERIFICATION_STATUSES = ("verified", "unverified")
USER_ROLES = ("admin", "student")
ATTENDANCE_STATUSES = ("present", "absent")
CONCERN_STATUSES = (
    "submitted",
    "under_review",
    "resources_recommended",
    "in_progress",
    "resolved",
    "closed",
)
CONCERN_PRIORITIES = ("low", "normal", "high")
ASSISTANCE_TYPES = ("explanation", "practice", "resources", "study_plan")
OPEN_CONCERN_STATUSES = (
    "submitted",
    "under_review",
    "resources_recommended",
    "in_progress",
)


class Student(Base):
    """One person in the school. admission_number is the business key."""

    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    admission_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    year_or_semester: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Demo rows are fictional records loaded for demonstrations.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    marks: Mapped[list["Mark"]] = relationship(back_populates="student")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="student")
    account: Mapped["User | None"] = relationship(back_populates="student")


class Subject(Base):
    """A taught subject. code is the short unique name.

    Inactive subjects stay in the database for historical marks. They are
    left out of the current Semester 1 subject lists.
    """

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    marks: Mapped[list["Mark"]] = relationship(back_populates="subject")
    resources: Mapped[list["LearningResource"]] = relationship(back_populates="subject")


class Examination(Base):
    """One examination type. The date is optional until an administrator sets it.

    Official CAT, assignment, and external scores are stored on the assessment
    tables. This row names the examination type and does not copy those scores.
    """

    __tablename__ = "examinations"
    __table_args__ = (
        UniqueConstraint("name", "held_on", name="uq_examination_name_date"),
        CheckConstraint(
            "exam_type IN ('fat', 'assignment', 'end_semester', 'midterm', 'final', 'quiz')",
            name="ck_examination_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    exam_type: Mapped[str] = mapped_column(String(20), nullable=False)
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    marks: Mapped[list["Mark"]] = relationship(back_populates="examination")


class Mark(Base):
    """Raw scores for one student in one subject in one examination.

    pass_marks is empty when the school has not set a pass mark. The
    application must not treat that row as an official failure.
    """

    __tablename__ = "marks"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "subject_id",
            "examination_id",
            name="uq_mark_student_subject_exam",
        ),
        CheckConstraint("marks_obtained >= 0", name="ck_marks_obtained_non_negative"),
        CheckConstraint("maximum_marks > 0", name="ck_maximum_marks_positive"),
        CheckConstraint(
            "marks_obtained <= maximum_marks",
            name="ck_marks_within_maximum",
        ),
        CheckConstraint(
            "pass_marks IS NULL OR (pass_marks >= 0 AND pass_marks <= maximum_marks)",
            name="ck_pass_marks_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id"),
        nullable=False,
        index=True,
    )
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("examinations.id"),
        nullable=False,
        index=True,
    )
    marks_obtained: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    maximum_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    pass_marks: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    student: Mapped[Student] = relationship(back_populates="marks")
    subject: Mapped[Subject] = relationship(back_populates="marks")
    examination: Mapped[Examination] = relationship(back_populates="marks")


def _score_check(column_name: str, maximum: int) -> CheckConstraint:
    """Allow a missing score, or a whole number from 0 through the maximum."""
    return CheckConstraint(
        f"{column_name} IS NULL OR ({column_name} >= 0 AND {column_name} <= {maximum})",
        name=f"ck_{column_name}_range",
    )


class InternalAssessment(Base):
    """Raw CAT and assignment scores for one student in one subject.

    Calculated pair scores and the internal mark are not stored.
    A null score has not been recorded. Zero is stored only when zero was entered.
    """

    __tablename__ = "internal_assessments"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_internal_student_subject"),
        _score_check("cat_1", 50),
        _score_check("assignment_1", 50),
        _score_check("cat_2", 50),
        _score_check("assignment_2", 50),
        _score_check("cat_3", 50),
        _score_check("assignment_3", 50),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    cat_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignment_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cat_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignment_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cat_3: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignment_3: Mapped[int | None] = mapped_column(Integer, nullable=True)

    student: Mapped[Student] = relationship()
    subject: Mapped[Subject] = relationship()


class ExternalExamination(Base):
    """The raw external examination mark out of 100 for one student and subject.

    The converted mark out of 50 is calculated when results are read.
    """

    __tablename__ = "external_examinations"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", name="uq_external_student_subject"),
        _score_check("raw_mark", 100),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    raw_mark: Mapped[int | None] = mapped_column(Integer, nullable=True)

    student: Mapped[Student] = relationship()
    subject: Mapped[Subject] = relationship()


class Feedback(Base):
    """Something a student reported about their own learning.

    These rows are not official academic results. A difficult topic here does
    not change a pass mark or a calculated percentage.
    """

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "preferred_format IN ('videos', 'books', 'examples', 'exercises')",
            name="ck_feedback_format",
        ),
        CheckConstraint(
            "resource_rating IS NULL OR resource_rating IN ('useful', 'unhelpful')",
            name="ck_feedback_rating",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True, index=True)
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    difficult_topics: Mapped[str | None] = mapped_column(String(500), nullable=True)
    explanation_request: Mapped[str | None] = mapped_column(String(500), nullable=True)
    practice_request: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferred_format: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resource_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Demo rows set this so loading them twice does not create duplicates.
    seed_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    student: Mapped[Student] = relationship(back_populates="feedback_entries")
    subject: Mapped[Subject | None] = relationship()


class LearningResource(Base):
    """A curated learning link. The language model does not invent these rows."""

    __tablename__ = "learning_resources"
    __table_args__ = (
        UniqueConstraint("url", name="uq_resource_url"),
        CheckConstraint(
            "resource_type IN ('book', 'website', 'course', 'video')",
            name="ck_resource_type",
        ),
        CheckConstraint(
            "verification_status IN ('verified', 'unverified')",
            name="ck_resource_verification",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_checked: Mapped[date | None] = mapped_column(Date, nullable=True)

    subject: Mapped[Subject] = relationship(back_populates="resources")


class User(Base):
    """A login account. A student account points at one student profile.

    Role is stored here and is not accepted from the registration form.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'student')", name="ck_user_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id"),
        unique=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    student: Mapped[Student | None] = relationship(back_populates="account")


class LoginSession(Base):
    """One signed-in browser. The cookie stores the random token, not this hash."""

    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()


class AttendanceRecord(Base):
    """One class session for one student and one subject.

    The same student, subject, and date can be stored only once.
    """

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "subject_id",
            "session_date",
            name="uq_attendance_student_subject_date",
        ),
        CheckConstraint(
            "status IN ('present', 'absent')",
            name="ck_attendance_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    student: Mapped[Student] = relationship()
    subject: Mapped[Subject] = relationship()


class Concern(Base):
    """A difficulty report owned by one student.

    The student writes the description. An administrator writes the response
    and changes the workflow status.
    """

    __tablename__ = "concerns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('submitted', 'under_review', 'resources_recommended', "
            "'in_progress', 'resolved', 'closed')",
            name="ck_concern_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high')",
            name="ck_concern_priority",
        ),
        CheckConstraint(
            "assistance_type IN ('explanation', 'practice', 'resources', 'study_plan')",
            name="ck_concern_assistance",
        ),
        CheckConstraint(
            "preferred_format IN ('videos', 'books', 'examples', 'exercises')",
            name="ck_concern_format",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    concept: Mapped[str] = mapped_column(String(300), nullable=False)
    assistance_type: Mapped[str] = mapped_column(String(30), nullable=False)
    preferred_format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="submitted", index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seed_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)

    student: Mapped[Student] = relationship()
    subject: Mapped[Subject] = relationship()
    updates: Mapped[list["ConcernUpdate"]] = relationship(back_populates="concern")
    recommendations: Mapped[list["ConcernResource"]] = relationship(back_populates="concern")


class ConcernUpdate(Base):
    """A follow-up note, admin response, or status change for one concern."""

    __tablename__ = "concern_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    concern_id: Mapped[int] = mapped_column(ForeignKey("concerns.id"), nullable=False, index=True)
    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    concern: Mapped[Concern] = relationship(back_populates="updates")


class ConcernResource(Base):
    """A curated resource an administrator attached to a concern."""

    __tablename__ = "concern_resources"
    __table_args__ = (
        UniqueConstraint("concern_id", "resource_id", name="uq_concern_resource"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    concern_id: Mapped[int] = mapped_column(ForeignKey("concerns.id"), nullable=False, index=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey("learning_resources.id"), nullable=False)
    recommended_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    concern: Mapped[Concern] = relationship(back_populates="recommendations")
    resource: Mapped[LearningResource] = relationship()


class StudyPlan(Base):
    """A stored copy of the rule-based study outline for one student."""

    __tablename__ = "study_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    outline_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    student: Mapped[Student] = relationship()


class AuditLog(Base):
    """A short record of an administrative change. Passwords are never stored here."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminNotification(Base):
    """A notice for administrators. It stores profile facts, never a password."""

    __tablename__ = "admin_notifications"
    __table_args__ = (
        UniqueConstraint("kind", "student_id", name="uq_notification_kind_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    admission_number: Mapped[str] = mapped_column(String(30), nullable=False)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    year_or_semester: Mapped[str | None] = mapped_column(String(40), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    student: Mapped[Student] = relationship()


class SchemaMigration(Base):
    """The version names of schema updates that have already been applied."""

    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
