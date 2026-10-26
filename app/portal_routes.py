"""Login, student portal, and administrator actions.

Academic percentages stay in the calculation modules. These routes decide
who may see a row, then call those modules.
"""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.academics import DEPARTMENT, SEMESTER, ordered_active_subjects
from app.access import owns_student_or_admin, require_admin, require_student, require_user
from app.assistant import (
    ASK_TASK,
    CONCERN_DRAFT_RULES,
    DRAFT_TASK,
    PLAN_TASK,
    REPORT_TASK,
    SUGGESTIONS_TASK,
)
from app.deps import commit_session, flush_session, get_db, require_db
from app.models import (
    OPEN_CONCERN_STATUSES,
    AdminNotification,
    AttendanceRecord,
    Concern,
    ExternalExamination,
    InternalAssessment,
    Mark,
    ConcernResource,
    ConcernUpdate,
    LearningResource,
    LoginSession,
    Student,
    Subject,
    User,
)
from app.records import (
    assistant_answer,
    assistant_bundle,
    attendance_report,
    concern_draft_context,
    concern_payload,
    latest_study_plan,
    load_concern,
    resource_payload,
    save_study_plan,
    require_active_subject,
    student_or_404,
    write_audit,
)
from app.schemas import (
    AttendanceUpdate,
    AttendanceWrite,
    ConcernDetailWrite,
    ConcernResponseWrite,
    ConcernWrite,
    LoginWrite,
    PasswordChangeWrite,
    PasswordWrite,
    ProfileWrite,
    PlanExplainWrite,
    QuestionWrite,
    StudyPlanWrite,
    RegisterWrite,
    ResourceWrite,
    StudentRead,
    StudentResults,
)
from app.security import (
    COOKIE_NAME,
    hash_password,
    hash_token,
    new_session_token,
    session_expiry,
    verify_password,
)
from app.seed import seed_demo_data

router = APIRouter()


def _account_payload(user: User) -> dict:
    student = user.student
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "must_change_password": bool(user.must_change_password),
        "student_id": user.student_id,
        "student": None
        if student is None
        else {
            "id": student.id,
            "admission_number": student.admission_number,
            "full_name": student.full_name,
            "email": student.email,
            "department": student.department,
            "year_or_semester": student.year_or_semester,
            "is_active": student.is_active,
            "is_demo": student.is_demo,
        },
    }


def _start_session(response: Response, db: Session, user: User) -> None:
    token = new_session_token()
    now = datetime.now(timezone.utc)
    db.add(
        LoginSession(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=session_expiry(now),
        )
    )
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )


def _reject_unknown_login() -> None:
    raise HTTPException(status_code=401, detail="Email or password is incorrect.")


@router.post("/auth/register", status_code=201)
def register(payload: RegisterWrite, db: Session | None = Depends(get_db)):
    """Create a student profile and a student login in one transaction.

    The role is always student. A registration cannot create an administrator.
    """
    database = require_db(db)
    now = datetime.now(timezone.utc)
    student = Student(
        admission_number=payload.admission_number,
        full_name=payload.full_name,
        email=payload.email,
        department=DEPARTMENT,
        year_or_semester=SEMESTER,
        is_active=True,
        is_demo=False,
    )
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="student",
        is_active=True,
        must_change_password=False,
        created_at=now,
    )
    database.add(student)
    try:
        database.flush()
    except IntegrityError:
        database.rollback()
        raise HTTPException(
            status_code=409,
            detail="A student with this admission number or email already exists.",
        ) from None
    user.student_id = student.id
    database.add(user)
    database.add(
        AdminNotification(
            kind="student_registered",
            student_id=student.id,
            full_name=student.full_name,
            email=student.email,
            admission_number=student.admission_number,
            department=student.department,
            year_or_semester=student.year_or_semester,
            registered_at=now,
            is_read=False,
            created_at=now,
        )
    )
    commit_session(database)
    return {
        "detail": "Account created. Sign in with your email and password.",
        "role": "student",
        "email": student.email,
        "student_id": student.id,
        "admission_number": student.admission_number,
    }


@router.post("/auth/login")
def login(payload: LoginWrite, response: Response, db: Session | None = Depends(get_db)):
    """Start a session when the email and password match an active account."""
    database = require_db(db)
    user = database.scalar(select(User).options(joinedload(User.student)).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        _reject_unknown_login()
    if not user.is_active:
        raise HTTPException(status_code=401, detail="This account is inactive.")
    if user.role == "student" and (user.student is None or not user.student.is_active):
        raise HTTPException(status_code=401, detail="This account is inactive.")
    if payload.portal == "student" and user.role != "student":
        raise HTTPException(status_code=403, detail="Use the administrator sign-in page.")
    if payload.portal == "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="This page is for administrators.")
    _start_session(response, database, user)
    return _account_payload(user)


@router.post("/auth/password")
def change_password(
    payload: PasswordChangeWrite,
    request: Request,
    user: User = Depends(require_user),
    db: Session | None = Depends(get_db),
):
    """Replace the signed-in user's password. The hash is the only stored form."""
    database = require_db(db)
    account = database.get(User, user.id)
    if account is None or not verify_password(payload.current_password, account.password_hash):
        raise HTTPException(status_code=401, detail="The current password is incorrect.")
    account.password_hash = hash_password(payload.new_password)
    account.must_change_password = False
    current_hash = hash_token(request.cookies.get(COOKIE_NAME, ""))
    database.execute(
        delete(LoginSession).where(
            LoginSession.user_id == account.id,
            LoginSession.token_hash != current_hash,
        )
    )
    write_audit(database, account, "password_changed", "user", account.id, "Changed the account password.")
    commit_session(database)
    return {"detail": "Password updated."}


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(require_user),
    db: Session | None = Depends(get_db),
):
    """Remove the current session. The academic records stay in PostgreSQL."""
    database = require_db(db)
    token = request.cookies.get(COOKIE_NAME, "")
    if token:
        database.execute(
            delete(LoginSession).where(
                LoginSession.token_hash == hash_token(token),
                LoginSession.user_id == user.id,
            )
        )
        database.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=204)


@router.get("/auth/me")
def read_me(user: User = Depends(require_user), db: Session | None = Depends(get_db)):
    """Return the signed-in account. Students also receive their own profile."""
    database = require_db(db)
    loaded = database.scalar(select(User).options(joinedload(User.student)).where(User.id == user.id))
    return _account_payload(loaded)


def _notification_payload(note: AdminNotification) -> dict:
    """Public notice fields. Password hashes and tokens are not on this model."""
    return {
        "id": note.id,
        "kind": note.kind,
        "student_id": note.student_id,
        "full_name": note.full_name,
        "email": note.email,
        "admission_number": note.admission_number,
        "department": note.department,
        "year_or_semester": note.year_or_semester,
        "registered_at": note.registered_at.isoformat(),
        "is_read": note.is_read,
        "read_at": None if note.read_at is None else note.read_at.isoformat(),
    }


@router.get("/notifications/unread-count")
def unread_notification_count(_: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    total = database.scalar(
        select(func.count()).select_from(AdminNotification).where(AdminNotification.is_read.is_(False))
    )
    return {"unread": int(total or 0)}


@router.get("/notifications")
def list_notifications(_: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    rows = database.scalars(
        select(AdminNotification).order_by(AdminNotification.created_at.desc(), AdminNotification.id.desc())
    ).all()
    return [_notification_payload(row) for row in rows]


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    _: User = Depends(require_admin),
    db: Session | None = Depends(get_db),
):
    database = require_db(db)
    note = database.get(AdminNotification, notification_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    if not note.is_read:
        note.is_read = True
        note.read_at = datetime.now(timezone.utc)
        commit_session(database)
    return _notification_payload(note)


@router.get("/registrations")
def list_registrations(
    q: str | None = None,
    department: str | None = None,
    active: bool | None = None,
    page: int = 1,
    page_size: int = 8,
    _: User = Depends(require_admin),
    db: Session | None = Depends(get_db),
):
    """Paginated student directory for the administrator. No password fields."""
    database = require_db(db)
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 50:
        page_size = 8
    filters = []
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Student.full_name).like(term),
                func.lower(Student.email).like(term),
                func.lower(Student.admission_number).like(term),
            )
        )
    if department and department.strip():
        filters.append(func.lower(Student.department) == department.strip().lower())
    if active is not None:
        filters.append(Student.is_active.is_(active))
    count_query = select(func.count()).select_from(Student)
    row_query = select(Student)
    if filters:
        count_query = count_query.where(*filters)
        row_query = row_query.where(*filters)
    total = database.scalar(count_query)
    rows = database.scalars(
        row_query.order_by(Student.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    accounts = {}
    if rows:
        for account in database.scalars(select(User).where(User.student_id.in_([row.id for row in rows]))).all():
            accounts[account.student_id] = account
    items = []
    for row in rows:
        account = accounts.get(row.id)
        if account is None:
            account_status = "no account"
        elif account.is_active and row.is_active:
            account_status = "active"
        else:
            account_status = "inactive"
        items.append(
            {
                "id": row.id,
                "full_name": row.full_name,
                "email": row.email,
                "admission_number": row.admission_number,
                "department": row.department,
                "year_or_semester": row.year_or_semester,
                "is_active": row.is_active,
                "is_demo": row.is_demo,
                "registered_at": None if account is None else account.created_at.isoformat(),
                "account_status": account_status,
            }
        )
    return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


@router.get("/me", response_model=StudentRead)
def read_profile(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    return student_or_404(database, user.student_id)


@router.put("/me", response_model=StudentRead)
def update_profile(payload: ProfileWrite, user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    """Update the signed-in student's permitted profile fields.

    Admission number, role, demo flag, and active flag cannot be changed here.
    """
    database = require_db(db)
    student = student_or_404(database, user.student_id)
    student.full_name = payload.full_name
    student.email = payload.email
    student.department = DEPARTMENT
    student.year_or_semester = SEMESTER
    account = database.get(User, user.id)
    account.email = payload.email
    commit_session(database)
    database.refresh(student)
    return student


@router.get("/me/results", response_model=StudentResults)
def read_my_results(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    bundle = assistant_bundle(database, user.student_id)
    return {
        "student": bundle["student"],
        "results": bundle["results"],
        "aggregate": bundle["aggregate"],
        "academic_report": bundle["academic_report"],
    }


@router.get("/me/attendance")
def read_my_attendance(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    student_or_404(database, user.student_id)
    return attendance_report(database, user.student_id)


@router.get("/me/subjects")
def list_my_subjects(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    """Return subjects so a student can choose one when submitting a concern."""
    database = require_db(db)
    rows = ordered_active_subjects(database)
    return [{"id": row.id, "code": row.code, "name": row.name} for row in rows]


@router.get("/me/resources")
def read_my_resources(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    return assistant_bundle(database, user.student_id)["resources"]


@router.get("/me/videos")
def read_my_videos(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    """Video resources for subjects this student has studied or reported."""
    database = require_db(db)
    subject_ids = set(database.scalars(select(Mark.subject_id).where(Mark.student_id == user.student_id)).all())
    subject_ids.update(database.scalars(select(InternalAssessment.subject_id).where(InternalAssessment.student_id == user.student_id)).all())
    subject_ids.update(database.scalars(select(ExternalExamination.subject_id).where(ExternalExamination.student_id == user.student_id)).all())
    subject_ids.update(database.scalars(select(AttendanceRecord.subject_id).where(AttendanceRecord.student_id == user.student_id)).all())
    subject_ids.update(database.scalars(select(Concern.subject_id).where(Concern.student_id == user.student_id)).all())
    active_ids = {row.id for row in ordered_active_subjects(database)}
    subject_ids &= active_ids
    if not subject_ids:
        return []
    rows = database.scalars(
        select(LearningResource)
        .options(joinedload(LearningResource.subject))
        .where(LearningResource.resource_type == "video", LearningResource.subject_id.in_(subject_ids))
        .order_by(LearningResource.title)
    ).unique().all()
    return [resource_payload(row) for row in rows]


@router.get("/me/study-plan")
def read_my_study_plan(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    bundle = assistant_bundle(database, user.student_id)
    return {"stored": latest_study_plan(database, user.student_id), "current_outline": bundle["outline"]}


@router.post("/me/study-plan", status_code=201)
def save_my_study_plan(
    payload: StudyPlanWrite | None = Body(default=None),
    user: User = Depends(require_student),
    db: Session | None = Depends(get_db),
):
    """Store the edited plan, or the current rule-based outline when no text is sent."""
    database = require_db(db)
    if payload is not None and payload.outline_text:
        outline = {"source": "student_edit", "items": [], "note": payload.outline_text}
    else:
        outline = assistant_bundle(database, user.student_id)["outline"]
    plan = save_study_plan(database, user.student_id, outline)
    commit_session(database)
    database.refresh(plan)
    stored = latest_study_plan(database, user.student_id)
    if stored is None or stored["id"] != plan.id:
        raise HTTPException(status_code=500, detail="The study plan was not stored.")
    return stored


@router.post("/me/assistant/report")
def my_report(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    facts = assistant_bundle(database, user.student_id)["facts"]
    return assistant_answer(REPORT_TASK, facts, task_name="academic_report")


@router.post("/me/assistant/suggestions")
def my_suggestions(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    facts = assistant_bundle(database, user.student_id)["facts"]
    return assistant_answer(SUGGESTIONS_TASK, facts, task_name="revision_suggestions")


@router.post("/me/assistant/plan")
def my_plan(
    payload: PlanExplainWrite | None = Body(default=None),
    user: User = Depends(require_student),
    db: Session | None = Depends(get_db),
):
    database = require_db(db)
    facts = dict(assistant_bundle(database, user.student_id)["facts"])
    if payload is not None and payload.plan_text:
        facts["displayed_plan"] = payload.plan_text
    return assistant_answer(PLAN_TASK, facts, task_name="study_plan")


@router.post("/me/assistant/ask")
def my_question(payload: QuestionWrite, user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    facts = assistant_bundle(database, user.student_id)["facts"]
    return assistant_answer(ASK_TASK, facts, payload.question, task_name="ask")


@router.get("/me/concerns")
def list_my_concerns(user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    rows = database.scalars(
        select(Concern)
        .options(joinedload(Concern.student), joinedload(Concern.subject))
        .where(Concern.student_id == user.student_id)
        .order_by(Concern.created_at.desc(), Concern.id.desc())
    ).unique().all()
    return [concern_payload(database, row) for row in rows]


@router.post("/me/concerns", status_code=201)
def create_my_concern(payload: ConcernWrite, user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    """Store a concern as submitted. The student cannot set the admin response or status."""
    database = require_db(db)
    subject = require_active_subject(database, payload.subject_id)
    concern = Concern(
        student_id=user.student_id,
        subject_id=subject.id,
        topic=payload.topic,
        description=payload.description,
        concept=payload.concept,
        assistance_type=payload.assistance_type,
        preferred_format=payload.preferred_format,
        status="submitted",
        priority=payload.priority,
        created_at=datetime.now(timezone.utc),
    )
    database.add(concern)
    commit_session(database)
    database.refresh(concern)
    return concern_payload(database, load_concern(database, concern.id))


@router.get("/me/concerns/{concern_id}")
def read_my_concern(concern_id: int, user: User = Depends(require_student), db: Session | None = Depends(get_db)):
    database = require_db(db)
    concern = load_concern(database, concern_id)
    owns_student_or_admin(user, concern.student_id)
    return concern_payload(database, concern)


@router.post("/me/concerns/{concern_id}/details", status_code=201)
def add_my_concern_detail(
    concern_id: int,
    payload: ConcernDetailWrite,
    user: User = Depends(require_student),
    db: Session | None = Depends(get_db),
):
    database = require_db(db)
    concern = load_concern(database, concern_id)
    owns_student_or_admin(user, concern.student_id)
    if concern.status in ("resolved", "closed"):
        raise HTTPException(status_code=409, detail="This concern is closed. Open a new concern if you need more help.")
    database.add(
        ConcernUpdate(
            concern_id=concern.id,
            author_user_id=user.id,
            kind="student_detail",
            message=payload.message,
            created_at=datetime.now(timezone.utc),
        )
    )
    commit_session(database)
    return concern_payload(database, load_concern(database, concern.id))


@router.get("/students/{student_id}/attendance")
def read_student_attendance(student_id: int, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    student_or_404(database, student_id)
    return attendance_report(database, student_id)


@router.post("/attendance", status_code=201)
def create_attendance(payload: AttendanceWrite, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    student_or_404(database, payload.student_id)
    require_active_subject(database, payload.subject_id)
    record = AttendanceRecord(
        student_id=payload.student_id,
        subject_id=payload.subject_id,
        session_date=payload.session_date,
        status=payload.status,
        recorded_by_user_id=admin.id,
    )
    database.add(record)
    write_audit(
        database,
        admin,
        "attendance_recorded",
        "attendance",
        f"{payload.student_id}:{payload.subject_id}:{payload.session_date.isoformat()}",
        f"Recorded {payload.status}.",
    )
    commit_session(database)
    database.refresh(record)
    return attendance_report(database, payload.student_id)


@router.put("/attendance/{attendance_id}")
def update_attendance(
    attendance_id: int,
    payload: AttendanceUpdate,
    admin: User = Depends(require_admin),
    db: Session | None = Depends(get_db),
):
    """Change one stored session. The student, subject, and date stay the same."""
    database = require_db(db)
    record = database.get(AttendanceRecord, attendance_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No attendance record found with id {attendance_id}.")
    record.status = payload.status
    write_audit(database, admin, "attendance_updated", "attendance", record.id, f"Updated status to {payload.status}.")
    commit_session(database)
    return attendance_report(database, record.student_id)


@router.delete("/attendance/{attendance_id}", status_code=204)
def delete_attendance(attendance_id: int, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    record = database.get(AttendanceRecord, attendance_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No attendance record found with id {attendance_id}.")
    write_audit(database, admin, "attendance_deleted", "attendance", record.id, "Deleted one attendance session.")
    database.delete(record)
    commit_session(database)
    return Response(status_code=204)


@router.get("/concerns")
def list_concerns(
    student_id: int | None = None,
    subject_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    admin: User = Depends(require_admin),
    db: Session | None = Depends(get_db),
):
    """List concerns for administrators. Filters use stored columns only."""
    database = require_db(db)
    statement = select(Concern).options(joinedload(Concern.student), joinedload(Concern.subject))
    if student_id is not None:
        statement = statement.where(Concern.student_id == student_id)
    if subject_id is not None:
        statement = statement.where(Concern.subject_id == subject_id)
    if status:
        statement = statement.where(Concern.status == status.strip().lower())
    if priority:
        statement = statement.where(Concern.priority == priority.strip().lower())
    if date_from is not None:
        start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        statement = statement.where(Concern.created_at >= start)
    if date_to is not None:
        end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        statement = statement.where(Concern.created_at <= end)
    rows = database.scalars(statement.order_by(Concern.created_at.desc(), Concern.id.desc())).unique().all()
    return [concern_payload(database, row) for row in rows]


@router.get("/concerns/open-count")
def count_open_concerns(admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    from sqlalchemy import func

    total = database.scalar(select(func.count()).select_from(Concern)) or 0
    open_count = database.scalar(
        select(func.count()).select_from(Concern).where(Concern.status.in_(OPEN_CONCERN_STATUSES))
    ) or 0
    return {"concerns": total, "open_concerns": open_count, "resolved_concerns": total - open_count}


@router.get("/concerns/{concern_id}")
def read_concern(concern_id: int, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    return concern_payload(database, load_concern(database, concern_id))


@router.post("/concerns/{concern_id}/response")
def respond_to_concern(
    concern_id: int,
    payload: ConcernResponseWrite,
    admin: User = Depends(require_admin),
    db: Session | None = Depends(get_db),
):
    """Save an administrator's reply and any curated resources they selected."""
    database = require_db(db)
    concern = load_concern(database, concern_id)
    now = datetime.now(timezone.utc)
    database.add(
        ConcernUpdate(
            concern_id=concern.id,
            author_user_id=admin.id,
            kind="admin_response",
            message=payload.message,
            created_at=now,
        )
    )
    if payload.status and payload.status != concern.status:
        concern.status = payload.status
        database.add(
            ConcernUpdate(
                concern_id=concern.id,
                author_user_id=admin.id,
                kind="status_change",
                message=f"Status set to {payload.status}.",
                created_at=now,
            )
        )
    if payload.priority:
        concern.priority = payload.priority
    if concern.status in ("resolved", "closed"):
        if concern.resolved_at is None:
            concern.resolved_at = now
    elif payload.status:
        concern.resolved_at = None

    for resource_id in payload.resource_ids:
        resource = database.get(LearningResource, resource_id)
        if resource is None:
            database.rollback()
            raise HTTPException(status_code=404, detail=f"No resource found with id {resource_id}.")
        already = database.scalar(
            select(ConcernResource.id).where(
                ConcernResource.concern_id == concern.id,
                ConcernResource.resource_id == resource_id,
            )
        )
        if already is None:
            database.add(
                ConcernResource(
                    concern_id=concern.id,
                    resource_id=resource_id,
                    recommended_by_user_id=admin.id,
                    created_at=now,
                )
            )
    write_audit(database, admin, "concern_updated", "concern", concern.id, "Recorded an admin response.")
    commit_session(database)
    return concern_payload(database, load_concern(database, concern.id))


@router.post("/concerns/{concern_id}/assistant/draft")
def draft_concern_reply(concern_id: int, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    """Ask the local model for a draft reply. The draft is not saved as the response."""
    database = require_db(db)
    concern = load_concern(database, concern_id)
    facts = concern_draft_context(database, concern)
    return assistant_answer(
        DRAFT_TASK,
        facts,
        task_name="concern_draft",
        rules=CONCERN_DRAFT_RULES,
    )


@router.post("/students/{student_id}/access")
def set_student_access(
    student_id: int,
    payload: PasswordWrite,
    admin: User = Depends(require_admin),
    db: Session | None = Depends(get_db),
):
    """Create or replace the student login. The role remains student."""
    database = require_db(db)
    student = student_or_404(database, student_id)
    account = database.scalar(select(User).where(User.student_id == student.id))
    other = database.scalar(select(User).where(User.email == student.email, User.student_id != student.id))
    if other is not None and (account is None or other.id != account.id):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    if account is None:
        account = User(
            email=student.email,
            password_hash=hash_password(payload.password),
            role="student",
            is_active=student.is_active,
            student_id=student.id,
            created_at=datetime.now(timezone.utc),
        )
        database.add(account)
        action = "student_access_created"
    else:
        account.password_hash = hash_password(payload.password)
        account.email = student.email
        account.role = "student"
        account.is_active = student.is_active
        action = "student_access_reset"
    write_audit(database, admin, action, "student", student.id, "Updated the student login. The password is not stored in the audit log.")
    commit_session(database)
    return {"detail": "Student access saved.", "student_id": student.id}


@router.post("/students/{student_id}/deactivate", response_model=StudentRead)
def deactivate_student(student_id: int, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    """Mark a student inactive. Marks, attendance, and concerns remain stored."""
    database = require_db(db)
    student = student_or_404(database, student_id)
    student.is_active = False
    account = database.scalar(select(User).where(User.student_id == student.id))
    if account is not None:
        account.is_active = False
        from sqlalchemy import delete

        database.execute(delete(LoginSession).where(LoginSession.user_id == account.id))
    write_audit(database, admin, "student_deactivated", "student", student.id, "Deactivated the student account.")
    commit_session(database)
    database.refresh(student)
    return student


@router.post("/students/{student_id}/study-plan", status_code=201)
def save_student_study_plan(student_id: int, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    student_or_404(database, student_id)
    bundle = assistant_bundle(database, student_id)
    save_study_plan(database, student_id, bundle["outline"])
    write_audit(database, admin, "study_plan_saved", "student", student_id, "Saved the rule-based study outline.")
    commit_session(database)
    return latest_study_plan(database, student_id)


@router.get("/audit-logs")
def list_audit_logs(admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    from app.models import AuditLog

    rows = database.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()
    return [
        {
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "detail": row.detail,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/resources", status_code=201)
def create_resource(payload: ResourceWrite, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    subject = require_active_subject(database, payload.subject_id)
    resource = LearningResource(
        title=payload.title,
        resource_type=payload.resource_type,
        author=payload.author,
        subject_id=subject.id,
        topic=payload.topic,
        url=payload.url,
        description=payload.description,
        verification_status=payload.verification_status,
        last_checked=payload.last_checked,
    )
    database.add(resource)
    flush_session(database)
    write_audit(database, admin, "resource_created", "resource", resource.id, payload.title)
    commit_session(database)
    database.refresh(resource)
    loaded = database.scalar(
        select(LearningResource).options(joinedload(LearningResource.subject)).where(LearningResource.id == resource.id)
    )
    return resource_payload(loaded)


@router.post("/demo-data")
def load_demo_data(admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    """Insert fictional demo rows that are not already present. Existing rows stay."""
    database = require_db(db)
    summary = seed_demo_data(database)
    write_audit(database, admin, "demo_data_loaded", "database", "demo", "Loaded fictional demo rows. They are marked as demo.")
    commit_session(database)
    return {
        "detail": "Demo data is loaded. Existing students and passwords were left unchanged.",
        **summary,
    }


@router.get("/students/{student_id}/concerns")
def list_student_concerns(student_id: int, admin: User = Depends(require_admin), db: Session | None = Depends(get_db)):
    database = require_db(db)
    student_or_404(database, student_id)
    rows = database.scalars(
        select(Concern)
        .options(joinedload(Concern.student), joinedload(Concern.subject))
        .where(Concern.student_id == student_id)
        .order_by(Concern.id)
    ).unique().all()
    return [concern_payload(database, row) for row in rows]
