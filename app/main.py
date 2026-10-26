"""The FastAPI application.

The public landing page is GET /. JSON process status is GET /api/status.
Official numbers are calculated in Python. Ollama only writes explanations.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.academics import (
    DEPARTMENT,
    INTERNAL_FIELDS,
    SEMESTER,
    academic_report,
    ordered_active_subjects,
    performance_counts,
)
from app.access import require_admin, signed_in_role
from app.assistant import ASK_TASK, PLAN_TASK, REPORT_TASK, SUGGESTIONS_TASK, assistant_status
from app.calculations import validate_mark_values
from app.database import (
    PROJECT_ROOT,
    check_database_connection,
    hide_secrets,
    prepare_application_database,
)
from app.deps import commit_session, flush_session, get_db, require_db
from app.guidance import subjects_needing_support
from app.models import (
    ACTIVE_EXAM_TYPES,
    OPEN_CONCERN_STATUSES,
    AttendanceRecord,
    Concern,
    Examination,
    ExternalExamination,
    Feedback,
    InternalAssessment,
    LearningResource,
    Mark,
    Student,
    Subject,
    User,
)
from app.portal_routes import router as portal_router
from app.records import (
    assistant_answer,
    assistant_bundle,
    delete_student_graph,
    feedback_payload,
    resource_payload,
    stored_feedback,
    stored_resources,
    require_active_subject,
    student_or_404,
    write_audit,
)
from app.results import results_for_student
from app.schemas import (
    AssistantAnswer,
    ExaminationRead,
    ExaminationWrite,
    ExternalExaminationWrite,
    FeedbackRead,
    InternalAssessmentWrite,
    FeedbackWrite,
    MarkWrite,
    QuestionWrite,
    ResourceRead,
    StudentRead,
    StudentResults,
    StudentWrite,
    SubjectRead,
    SubjectWrite,
)

STATIC_DIR = PROJECT_ROOT / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepare PostgreSQL when it is configured.

    Demo rows are not inserted here. A missing database does not stop the
    process. Routes that need rows return an error instead.
    """
    app.state.academic_records_ready = False
    app.state.academic_records_error = None
    app.state.admin_account = "not_checked"
    try:
        app.state.admin_account = prepare_application_database()
    except Exception as exc:
        app.state.academic_records_error = hide_secrets(str(exc))
    else:
        app.state.academic_records_ready = True
    yield


app = FastAPI(
    title="Student Management System",
    version="1.0.0",
    description=(
        "Manage students and academic records, collect learning feedback, "
        "and explain calculated results with a local Ollama model."
    ),
    lifespan=lifespan,
)


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request, exc: SQLAlchemyError):
    """Turn an unexpected database failure into a response without the password."""
    return JSONResponse(
        status_code=503,
        content={"detail": "The database request failed. " + hide_secrets(str(exc))},
    )


@app.get("/api/status")
def read_root():
    """Tell the caller that the API process is running. This does not use PostgreSQL."""
    return {"status": "running", "message": "Student Management System is running"}


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC_DIR / name)


@app.get("/", include_in_schema=False)
def read_landing_page():
    """Public welcome page. Sign-in and registration are separate pages."""
    return _page("landing.html")


@app.get("/login", include_in_schema=False)
def read_login_page():
    """Student sign-in. Registration is not on this page."""
    return _page("login.html")


@app.get("/register", include_in_schema=False)
def read_register_page():
    """Student registration. This page cannot create an administrator."""
    return _page("register.html")


@app.get("/admin/login", include_in_schema=False)
def read_admin_login_page():
    """Administrator sign-in. The password is never written into this page."""
    return _page("admin-login.html")


@app.get("/app", include_in_schema=False)
def read_old_dashboard():
    """The previous combined address now returns to the public landing page."""
    return RedirectResponse("/", status_code=303)


@app.get("/student", include_in_schema=False)
@app.get("/student/dashboard", include_in_schema=False)
def read_student_portal(request: Request):
    """Serve the student dashboard only after the session cookie is a student."""
    if signed_in_role(request) != "student":
        return RedirectResponse("/login", status_code=303)
    return _page("student.html")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/dashboard", include_in_schema=False)
def read_admin_portal(request: Request):
    """Serve the administrator dashboard only after the session cookie is an admin."""
    if signed_in_role(request) != "admin":
        return RedirectResponse("/admin/login", status_code=303)
    return _page("admin.html")


@app.get("/health")
def read_health():
    """Report whether PostgreSQL accepted SELECT 1 and whether the tables are ready."""
    result = check_database_connection()
    records_ready = bool(getattr(app.state, "academic_records_ready", False))
    admin_account = getattr(app.state, "admin_account", "not_checked")
    if result["ok"]:
        from app.database import SessionLocal

        try:
            with SessionLocal() as session:
                found = session.scalar(select(User.id).where(User.role == "admin").limit(1))
            admin_account = "configured" if found else "missing"
        except SQLAlchemyError:
            admin_account = "not_checked"
    body = {
        "status": "healthy" if result["ok"] else "unhealthy",
        "application": "running",
        "database": "reachable" if result["ok"] else "unreachable",
        "detail": result["detail"],
        "academic_records": "ready" if records_ready else "not_ready",
        "admin_account": admin_account,
    }
    records_error = getattr(app.state, "academic_records_error", None)
    if not records_ready and records_error:
        body["academic_records_detail"] = records_error
    if result["ok"]:
        return body
    return JSONResponse(status_code=503, content=body)


@app.get("/assistant/status")
def read_assistant_status():
    """Report whether the local Ollama model can be called. This does not use PostgreSQL."""
    return assistant_status()


@app.get("/summary")
def read_summary(db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Count records and subjects whose latest result needs support."""
    database = require_db(db)
    attention = 0
    for student_id in database.scalars(select(Student.id)).all():
        attention += len(subjects_needing_support(academic_report(database, student_id)["subjects"]))
    performance = performance_counts(database)
    attendance_total = database.scalar(select(func.count()).select_from(AttendanceRecord)) or 0
    attendance_present = database.scalar(
        select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.status == "present")
    ) or 0
    difficult = database.execute(
        select(Subject.name, func.count(Concern.id))
        .join(Concern, Concern.subject_id == Subject.id)
        .where(Subject.is_active.is_(True))
        .group_by(Subject.name)
        .order_by(func.count(Concern.id).desc(), Subject.name)
    ).all()
    recent_users = database.scalars(
        select(User).options(joinedload(User.student)).where(User.role == "student").order_by(User.created_at.desc()).limit(5)
    ).unique().all()
    return {
        "students": database.scalar(select(func.count()).select_from(Student)) or 0,
        "subjects": database.scalar(select(func.count()).select_from(Subject).where(Subject.is_active.is_(True))) or 0,
        "examinations": database.scalar(
            select(func.count()).select_from(Examination).where(
                Examination.is_active.is_(True),
                Examination.exam_type.in_(ACTIVE_EXAM_TYPES),
            )
        ) or 0,
        "feedback_entries": database.scalar(select(func.count()).select_from(Feedback)) or 0,
        "resources": database.scalar(select(func.count()).select_from(LearningResource)) or 0,
        "marks": database.scalar(select(func.count()).select_from(Mark)) or 0,
        "subjects_needing_support": attention,
        "demo_students": database.scalar(select(func.count()).select_from(Student).where(Student.is_demo.is_(True))) or 0,
        "active_students": database.scalar(select(func.count()).select_from(Student).where(Student.is_active.is_(True))) or 0,
        "open_concerns": database.scalar(
            select(func.count()).select_from(Concern).where(Concern.status.in_(OPEN_CONCERN_STATUSES))
        ) or 0,
        "resolved_concerns": database.scalar(
            select(func.count()).select_from(Concern).where(Concern.status.in_(("resolved", "closed")))
        ) or 0,
        "attendance_sessions": attendance_total,
        "attendance_present": attendance_present,
        "performance": performance,
        "difficult_subjects": [{"subject": name, "concerns": count} for name, count in difficult],
        "recent_registrations": [
            {
                "full_name": None if row.student is None else row.student.full_name,
                "email": row.email,
                "registered_at": row.created_at.isoformat(),
                "is_demo": False if row.student is None else bool(row.student.is_demo),
            }
            for row in recent_users
        ],
    }


@app.get("/students", response_model=list[StudentRead], summary="List students")
def list_students(
    q: str | None = None,
    department: str | None = None,
    active: bool | None = None,
    db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return students, optionally filtered by name, admission number, email, or department."""
    database = require_db(db)
    statement = select(Student).order_by(Student.admission_number)
    if q and q.strip():
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Student.full_name.ilike(term),
                Student.admission_number.ilike(term),
                Student.email.ilike(term),
            )
        )
    if department and department.strip():
        statement = statement.where(Student.department.ilike(f"%{department.strip()}%"))
    if active is not None:
        statement = statement.where(Student.is_active.is_(active))
    return database.scalars(statement).all()


@app.post("/students", response_model=StudentRead, status_code=201, summary="Create a student")
def create_student(payload: StudentWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Store a new student. Admission number and email must each be unique."""
    database = require_db(db)
    student = Student(
        admission_number=payload.admission_number,
        full_name=payload.full_name,
        email=payload.email,
        department=DEPARTMENT,
        year_or_semester=SEMESTER,
        is_active=payload.is_active,
        is_demo=False,
    )
    database.add(student)
    write_audit(database, admin, "student_created", "student", payload.admission_number, "Created a student profile.")
    commit_session(database)
    database.refresh(student)
    return student


@app.get("/students/{student_id}", response_model=StudentRead, summary="Get one student")
def read_student(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return one student, or 404 when the id is not stored."""
    return student_or_404(require_db(db), student_id)


@app.put("/students/{student_id}", response_model=StudentRead, summary="Update a student")
def update_student(student_id: int, payload: StudentWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Replace the student's admission number, name, and email."""
    database = require_db(db)
    student = student_or_404(database, student_id)
    student.admission_number = payload.admission_number
    student.full_name = payload.full_name
    student.email = payload.email
    student.department = DEPARTMENT
    student.year_or_semester = SEMESTER
    student.is_active = payload.is_active
    account = database.scalar(select(User).where(User.student_id == student.id))
    if account is not None:
        account.email = payload.email
        account.is_active = payload.is_active
    write_audit(database, admin, "student_updated", "student", student.id, "Updated the student profile.")
    commit_session(database)
    database.refresh(student)
    return student


@app.delete("/students/{student_id}", status_code=204, summary="Delete a student")
def delete_student(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete a student together with that student's own academic rows."""
    database = require_db(db)
    student = student_or_404(database, student_id)
    write_audit(database, admin, "student_deleted", "student", student.admission_number, "Deleted the student and that student's own rows.")
    delete_student_graph(database, student)
    commit_session(database)
    return Response(status_code=204)


@app.get("/students/{student_id}/results", response_model=StudentResults, summary="Get calculated results")
def read_student_results(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return stored marks with percentages and official status calculated in Python."""
    database = require_db(db)
    student = student_or_404(database, student_id)
    try:
        results = results_for_student(database, student_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    from app.calculations import aggregate_percentage

    return {
        "student": student,
        "results": results,
        "aggregate": aggregate_percentage(results),
        "academic_report": academic_report(database, student_id),
    }


@app.get("/students/{student_id}/feedback", response_model=list[FeedbackRead])
def list_feedback(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return feedback the student reported. These rows are not official results."""
    database = require_db(db)
    student_or_404(database, student_id)
    return stored_feedback(database, student_id)


@app.post("/students/{student_id}/feedback", response_model=FeedbackRead, status_code=201)
def create_feedback(student_id: int, payload: FeedbackWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Store one piece of student-reported feedback."""
    database = require_db(db)
    student_or_404(database, student_id)
    if payload.subject_id is not None:
        require_active_subject(database, payload.subject_id)

    item = Feedback(
        student_id=student_id,
        subject_id=payload.subject_id,
        topic=payload.topic,
        difficult_topics=payload.difficult_topics,
        explanation_request=payload.explanation_request,
        practice_request=payload.practice_request,
        preferred_format=payload.preferred_format,
        resource_note=payload.resource_note,
        resource_rating=payload.resource_rating,
        created_at=datetime.now(timezone.utc),
    )
    database.add(item)
    commit_session(database)
    database.refresh(item)
    loaded = database.scalars(
        select(Feedback).options(joinedload(Feedback.subject)).where(Feedback.id == item.id)
    ).unique().one()
    return feedback_payload(loaded)


@app.get("/students/{student_id}/resources", response_model=list[ResourceRead])
def list_student_resources(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return curated resources for subjects whose latest result needs support."""
    database = require_db(db)
    bundle = assistant_bundle(database, student_id)
    return bundle["resources"]


@app.get("/students/{student_id}/study-outline")
def read_study_outline(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return the rule-based outline. This route does not call the language model."""
    database = require_db(db)
    return assistant_bundle(database, student_id)["outline"]


@app.post("/students/{student_id}/assistant/report", response_model=AssistantAnswer)
def create_report(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Ask the local model to summarize the calculated results."""
    database = require_db(db)
    facts = assistant_bundle(database, student_id)["facts"]
    return assistant_answer(REPORT_TASK, facts, task_name="academic_report")


@app.post("/students/{student_id}/assistant/suggestions", response_model=AssistantAnswer)
def create_suggestions(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Ask the local model for study activities based on weak or failed subjects."""
    database = require_db(db)
    facts = assistant_bundle(database, student_id)["facts"]
    return assistant_answer(SUGGESTIONS_TASK, facts, task_name="revision_suggestions")


@app.post("/students/{student_id}/assistant/plan", response_model=AssistantAnswer)
def create_plan(student_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Ask the local model to explain the rule-based weekly outline."""
    database = require_db(db)
    facts = assistant_bundle(database, student_id)["facts"]
    return assistant_answer(PLAN_TASK, facts, task_name="study_plan")


@app.post("/students/{student_id}/assistant/ask", response_model=AssistantAnswer)
def ask_about_student(student_id: int, payload: QuestionWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Answer one question from the selected student's stored facts."""
    database = require_db(db)
    facts = assistant_bundle(database, student_id)["facts"]
    return assistant_answer(ASK_TASK, facts, payload.question, task_name="ask")


@app.get("/subjects", response_model=list[SubjectRead], summary="List subjects")
def list_subjects(
    include_inactive: bool = False,
    db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return active subjects, or every subject when an administrator asks for the full list."""
    database = require_db(db)
    if include_inactive:
        return database.scalars(select(Subject).order_by(Subject.is_active.desc(), Subject.code)).all()
    return ordered_active_subjects(database)


@app.post("/subjects", response_model=SubjectRead, status_code=201, summary="Create a subject")
def create_subject(payload: SubjectWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Store a subject. The code must be unique."""
    database = require_db(db)
    subject = Subject(
        code=payload.code,
        name=payload.name,
        is_active=payload.is_active,
    )
    database.add(subject)
    commit_session(database)
    database.refresh(subject)
    return subject


@app.get("/subjects/{subject_id}", response_model=SubjectRead, summary="Get one subject")
def read_subject(subject_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return one subject, or 404 when the id is not stored."""
    database = require_db(db)
    subject = database.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail=f"No subject found with id {subject_id}.")
    return subject


@app.put("/subjects/{subject_id}", response_model=SubjectRead, summary="Update a subject")
def update_subject(subject_id: int, payload: SubjectWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Replace a subject's code and name."""
    database = require_db(db)
    subject = database.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail=f"No subject found with id {subject_id}.")
    subject.code = payload.code
    subject.name = payload.name
    subject.is_active = payload.is_active
    commit_session(database)
    database.refresh(subject)
    return subject


@app.delete("/subjects/{subject_id}", status_code=204, summary="Delete a subject")
def delete_subject(subject_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete a subject that has no marks and no learning resources."""
    database = require_db(db)
    subject = database.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail=f"No subject found with id {subject_id}.")
    mark_count = database.scalar(select(func.count()).select_from(Mark).where(Mark.subject_id == subject.id)) or 0
    resource_count = database.scalar(
        select(func.count()).select_from(LearningResource).where(LearningResource.subject_id == subject.id)
    ) or 0
    feedback_count = database.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.subject_id == subject.id)
    ) or 0
    concern_count = database.scalar(
        select(func.count()).select_from(Concern).where(Concern.subject_id == subject.id)
    ) or 0
    attendance_count = database.scalar(
        select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.subject_id == subject.id)
    ) or 0
    internal_count = database.scalar(
        select(func.count()).select_from(InternalAssessment).where(InternalAssessment.subject_id == subject.id)
    ) or 0
    external_count = database.scalar(
        select(func.count()).select_from(ExternalExamination).where(ExternalExamination.subject_id == subject.id)
    ) or 0
    if any((mark_count, resource_count, feedback_count, concern_count, attendance_count, internal_count, external_count)):
        raise HTTPException(
            status_code=409,
            detail="This subject still has academic records. Deactivate it instead of deleting it.",
        )
    database.delete(subject)
    commit_session(database)
    return Response(status_code=204)


@app.get("/examinations", response_model=list[ExaminationRead], summary="List examinations")
def list_examinations(db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return the three current examination types."""
    database = require_db(db)
    rows = database.scalars(
        select(Examination).where(
            Examination.is_active.is_(True),
            Examination.exam_type.in_(ACTIVE_EXAM_TYPES),
        )
    ).all()
    rank = {exam_type: index for index, exam_type in enumerate(ACTIVE_EXAM_TYPES)}
    return sorted(rows, key=lambda row: rank.get(row.exam_type, len(rank)))


@app.post("/examinations", response_model=ExaminationRead, status_code=201, summary="Create an examination")
def create_examination(payload: ExaminationWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Store one of the three examination types. A second copy of the same type is rejected."""
    database = require_db(db)
    existing = database.scalar(
        select(Examination.id).where(
            Examination.exam_type == payload.exam_type,
            Examination.is_active.is_(True),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This examination type already exists. Edit the existing one instead of adding another.",
        )
    examination = Examination(
        name=payload.name,
        exam_type=payload.exam_type,
        held_on=payload.held_on,
        is_active=True,
    )
    database.add(examination)
    commit_session(database)
    database.refresh(examination)
    return examination


@app.get("/examinations/{examination_id}", response_model=ExaminationRead, summary="Get one examination")
def read_examination(examination_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return one examination, or 404 when the id is not stored."""
    database = require_db(db)
    examination = database.get(Examination, examination_id)
    if examination is None:
        raise HTTPException(status_code=404, detail=f"No examination found with id {examination_id}.")
    return examination


@app.put("/examinations/{examination_id}", response_model=ExaminationRead, summary="Update an examination")
def update_examination(examination_id: int, payload: ExaminationWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update the date for one of the three examination types."""
    database = require_db(db)
    examination = database.get(Examination, examination_id)
    if examination is None:
        raise HTTPException(status_code=404, detail=f"No examination found with id {examination_id}.")
    other = database.scalar(
        select(Examination.id).where(
            Examination.exam_type == payload.exam_type,
            Examination.is_active.is_(True),
            Examination.id != examination.id,
        )
    )
    if other is not None:
        raise HTTPException(
            status_code=409,
            detail="This examination type already exists. Edit the existing one instead of adding another.",
        )
    examination.name = payload.name
    examination.exam_type = payload.exam_type
    examination.held_on = payload.held_on
    examination.is_active = True
    commit_session(database)
    database.refresh(examination)
    return examination


@app.delete("/examinations/{examination_id}", status_code=204, summary="Delete an examination")
def delete_examination(examination_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete an examination that does not yet have marks."""
    database = require_db(db)
    examination = database.get(Examination, examination_id)
    if examination is None:
        raise HTTPException(status_code=404, detail=f"No examination found with id {examination_id}.")
    if examination.is_active and examination.exam_type in ACTIVE_EXAM_TYPES:
        raise HTTPException(
            status_code=409,
            detail="The three examination types stay in the active list. Edit the date instead of deleting the type.",
        )
    mark_count = database.scalar(
        select(func.count()).select_from(Mark).where(Mark.examination_id == examination.id)
    ) or 0
    if mark_count:
        raise HTTPException(status_code=409, detail="This examination still has marks. Delete those marks first.")
    database.delete(examination)
    commit_session(database)
    return Response(status_code=204)


@app.post("/marks", status_code=201, summary="Create a mark")
def create_mark(payload: MarkWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Store raw scores. Python will calculate the percentage when results are read."""
    database = require_db(db)
    if database.get(Student, payload.student_id) is None:
        raise HTTPException(status_code=404, detail=f"No student found with id {payload.student_id}.")
    require_active_subject(database, payload.subject_id)
    examination = database.get(Examination, payload.examination_id)
    if examination is None or not examination.is_active:
        raise HTTPException(status_code=404, detail="No active examination found with that id.")
    try:
        obtained, maximum, passing = validate_mark_values(
            payload.marks_obtained,
            payload.maximum_marks,
            payload.pass_marks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    mark = Mark(
        student_id=payload.student_id,
        subject_id=payload.subject_id,
        examination_id=payload.examination_id,
        marks_obtained=obtained,
        maximum_marks=maximum,
        pass_marks=passing,
    )
    database.add(mark)
    flush_session(database)
    write_audit(database, admin, "mark_saved", "mark", mark.id, "Saved a mark. The percentage is calculated when results are read.")
    commit_session(database)
    database.refresh(mark)
    return {"id": mark.id, "detail": "Mark saved. The percentage is calculated when results are requested."}


@app.put("/marks/{mark_id}", summary="Update a mark")
def update_mark(mark_id: int, payload: MarkWrite, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Replace one stored score. The percentage is still calculated on read."""
    database = require_db(db)
    mark = database.get(Mark, mark_id)
    if mark is None:
        raise HTTPException(status_code=404, detail=f"No mark found with id {mark_id}.")
    if database.get(Student, payload.student_id) is None:
        raise HTTPException(status_code=404, detail=f"No student found with id {payload.student_id}.")
    subject = database.get(Subject, payload.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail=f"No subject found with id {payload.subject_id}.")
    if not subject.is_active and subject.id != mark.subject_id:
        raise HTTPException(status_code=422, detail="Choose an active subject.")
    examination = database.get(Examination, payload.examination_id)
    if examination is None:
        raise HTTPException(status_code=404, detail=f"No examination found with id {payload.examination_id}.")
    if not examination.is_active and examination.id != mark.examination_id:
        raise HTTPException(status_code=422, detail="Choose an active examination type.")
    try:
        obtained, maximum, passing = validate_mark_values(
            payload.marks_obtained,
            payload.maximum_marks,
            payload.pass_marks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    mark.student_id = payload.student_id
    mark.subject_id = payload.subject_id
    mark.examination_id = payload.examination_id
    mark.marks_obtained = obtained
    mark.maximum_marks = maximum
    mark.pass_marks = passing
    write_audit(database, admin, "mark_updated", "mark", mark.id, "Updated a mark.")
    commit_session(database)
    database.refresh(mark)
    return {"id": mark.id, "detail": "Mark updated. The percentage is calculated when results are requested."}


def _active_subject(database: Session, subject_id: int) -> Subject:
    """Return one subject from the current Semester 1 list."""
    subject = database.get(Subject, subject_id)
    if subject is None or not subject.is_active:
        raise HTTPException(status_code=404, detail="No active subject found with that id.")
    return subject


@app.put("/students/{student_id}/internal-assessment", summary="Save internal assessment scores")
def save_internal_assessment(
    student_id: int,
    payload: InternalAssessmentWrite,
    db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Store raw CAT and assignment scores. Calculated marks are not stored."""
    database = require_db(db)
    student_or_404(database, student_id)
    subject = _active_subject(database, payload.subject_id)
    row = database.scalar(
        select(InternalAssessment).where(
            InternalAssessment.student_id == student_id,
            InternalAssessment.subject_id == subject.id,
        )
    )
    if row is None:
        row = InternalAssessment(student_id=student_id, subject_id=subject.id)
        database.add(row)
    for name in INTERNAL_FIELDS:
        setattr(row, name, getattr(payload, name))
    flush_session(database)
    write_audit(database, admin, "internal_assessment_saved", "internal_assessment", row.id, subject.code)
    commit_session(database)
    report = academic_report(database, student_id)
    report.pop("subjects", None)
    return report


@app.put("/students/{student_id}/external-examination", summary="Save an external examination mark")
def save_external_examination(
    student_id: int,
    payload: ExternalExaminationWrite,
    db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Store the raw external mark out of 100. The converted mark is calculated on read."""
    database = require_db(db)
    student_or_404(database, student_id)
    subject = _active_subject(database, payload.subject_id)
    row = database.scalar(
        select(ExternalExamination).where(
            ExternalExamination.student_id == student_id,
            ExternalExamination.subject_id == subject.id,
        )
    )
    if row is None:
        row = ExternalExamination(student_id=student_id, subject_id=subject.id)
        database.add(row)
    row.raw_mark = payload.raw_mark
    flush_session(database)
    write_audit(database, admin, "external_examination_saved", "external_examination", row.id, subject.code)
    commit_session(database)
    report = academic_report(database, student_id)
    report.pop("subjects", None)
    return report


@app.delete("/marks/{mark_id}", status_code=204, summary="Delete a mark")
def delete_mark(mark_id: int, db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete one stored score. This does not delete the student or subject."""
    database = require_db(db)
    mark = database.get(Mark, mark_id)
    if mark is None:
        raise HTTPException(status_code=404, detail=f"No mark found with id {mark_id}.")
    database.delete(mark)
    commit_session(database)
    return Response(status_code=204)


@app.get("/resources", response_model=list[ResourceRead], summary="List curated resources")
def list_resources(db: Session | None = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Return every curated resource, including its verification status."""
    return stored_resources(require_db(db))


app.include_router(portal_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
