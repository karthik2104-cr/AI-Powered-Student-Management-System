"""Load one student's stored marks and hand them to the calculation functions."""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.calculations import ScoreInput, build_results
from app.models import Mark


def results_for_student(session: Session, student_id: int) -> list[dict]:
    """Return calculated results for every mark stored for this student.

    joinedload reads the subject and examination in the same query. unique()
    removes the duplicate parent rows that a join can produce.
    """
    statement = (
        select(Mark)
        .options(joinedload(Mark.subject), joinedload(Mark.examination))
        .where(Mark.student_id == student_id)
    )
    marks = session.scalars(statement).unique().all()
    scores = [
        ScoreInput(
            student_id=mark.student_id,
            subject_id=mark.subject_id,
            subject_code=mark.subject.code,
            subject_name=mark.subject.name,
            examination_id=mark.examination_id,
            examination_name=mark.examination.name,
            exam_type=mark.examination.exam_type,
            held_on=mark.examination.held_on,
            marks_obtained=mark.marks_obtained,
            maximum_marks=mark.maximum_marks,
            pass_marks=mark.pass_marks,
            mark_id=mark.id,
        )
        for mark in marks
    ]
    return build_results(scores)
