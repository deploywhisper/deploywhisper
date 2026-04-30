"""Reviewer feedback repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.tables import FeedbackEvent


def create_feedback_event(
    session: Session,
    *,
    project_id: int,
    analysis_id: int,
    finding_id: str | None = None,
    reviewer_role: str | None = None,
    useful: bool | None = None,
    correctness_rating: int | None = None,
    false_positive_flag: bool = False,
    false_positive_reason: str | None = None,
    false_negative_note: str | None = None,
    outcome_label: str | None = None,
) -> FeedbackEvent:
    event = FeedbackEvent(
        project_id=project_id,
        analysis_id=analysis_id,
        finding_id=finding_id,
        reviewer_role=reviewer_role,
        useful=useful,
        correctness_rating=correctness_rating,
        false_positive_flag=false_positive_flag,
        false_positive_reason=false_positive_reason,
        false_negative_note=false_negative_note,
        outcome_label=outcome_label,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def list_feedback_events(
    session: Session,
    *,
    project_id: int | None = None,
    analysis_id: int | None = None,
    limit: int | None = None,
) -> list[FeedbackEvent]:
    stmt = select(FeedbackEvent).order_by(
        FeedbackEvent.created_at.desc(), FeedbackEvent.id.desc()
    )
    if project_id is not None:
        stmt = stmt.where(FeedbackEvent.project_id == project_id)
    if analysis_id is not None:
        stmt = stmt.where(FeedbackEvent.analysis_id == analysis_id)
    if limit is not None:
        stmt = stmt.limit(max(1, limit))
    result = session.execute(stmt)
    return list(result.scalars().all())
