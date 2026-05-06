"""Reviewer feedback capture and summary helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from models.database import SessionLocal
from models.repositories.analysis_reports import get_analysis_report
from models.repositories.feedback_events import (
    create_feedback_event,
    list_feedback_events,
)
from services.project_service import (
    build_project_payload,
    ensure_default_project,
    resolve_project_reference,
    resolve_workspace_reference,
)


class FeedbackError(ValueError):
    """Raised when reviewer feedback input is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _serialize_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat()


def _normalize_optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _serialize_event(event) -> dict[str, Any]:
    return {
        "id": event.id,
        "project_id": event.project_id,
        "workspace_id": event.workspace_id,
        "analysis_id": event.analysis_id,
        "finding_id": event.finding_id,
        "reviewer_role": event.reviewer_role,
        "useful": event.useful,
        "correctness_rating": event.correctness_rating,
        "false_positive_flag": bool(event.false_positive_flag),
        "false_positive_reason": event.false_positive_reason,
        "false_negative_note": event.false_negative_note,
        "outcome_label": event.outcome_label,
        "created_at": _serialize_timestamp(event.created_at),
    }


def _project_payload(
    project_id: int | None = None, project_key: str | None = None
) -> dict[str, Any]:
    if project_id is None and project_key is None:
        return build_project_payload(ensure_default_project())
    return build_project_payload(
        resolve_project_reference(project_id=project_id, project_key=project_key)
    )


def _resolve_summary_scope(
    *,
    project_id: int | None,
    project_key: str | None,
    workspace_id: int | None,
    workspace_key: str | None,
):
    if project_id is None and project_key is None:
        project = ensure_default_project()
    else:
        project = resolve_project_reference(
            project_id=project_id, project_key=project_key
        )
    workspace = resolve_workspace_reference(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    return project, workspace


def record_finding_feedback(
    *,
    analysis_id: int,
    finding_id: str,
    useful: bool,
    false_positive_flag: bool = False,
    false_positive_reason: str | None = None,
    reviewer_role: str = "reviewer",
) -> dict[str, Any]:
    normalized_finding_id = str(finding_id or "").strip()
    if not normalized_finding_id:
        raise FeedbackError("invalid_feedback_request", "finding_id is required.")
    normalized_reason = _normalize_optional_text(false_positive_reason)
    if normalized_reason is not None and not false_positive_flag:
        raise FeedbackError(
            "invalid_feedback_request",
            "False positive reason requires false_positive_flag=True.",
        )
    with SessionLocal() as session:
        report = get_analysis_report(session, analysis_id, include_evidence=False)
        if report is None:
            raise FeedbackError(
                "analysis_not_found",
                f"Analysis report not found: {analysis_id}.",
            )
        finding_ids = {finding.finding_id for finding in report.findings}
        if normalized_finding_id not in finding_ids:
            raise FeedbackError(
                "finding_not_found",
                f"Finding not found on analysis report {analysis_id}: {normalized_finding_id}.",
            )
        outcome_label = (
            "false_positive"
            if false_positive_flag
            else "useful"
            if useful
            else "not_useful"
        )
        event = create_feedback_event(
            session,
            project_id=report.project_id,
            workspace_id=report.workspace_id,
            analysis_id=analysis_id,
            finding_id=normalized_finding_id,
            reviewer_role=reviewer_role,
            useful=bool(useful),
            correctness_rating=1 if useful else 0,
            false_positive_flag=false_positive_flag,
            false_positive_reason=normalized_reason,
            outcome_label=outcome_label,
        )
        return _serialize_event(event)


def record_false_negative_feedback(
    *,
    analysis_id: int,
    note: str,
    reviewer_role: str = "reviewer",
) -> dict[str, Any]:
    normalized_note = _normalize_optional_text(note)
    if normalized_note is None:
        raise FeedbackError(
            "invalid_feedback_request",
            "False negative note is required.",
        )
    with SessionLocal() as session:
        report = get_analysis_report(session, analysis_id, include_evidence=False)
        if report is None:
            raise FeedbackError(
                "analysis_not_found",
                f"Analysis report not found: {analysis_id}.",
            )
        event = create_feedback_event(
            session,
            project_id=report.project_id,
            workspace_id=report.workspace_id,
            analysis_id=analysis_id,
            reviewer_role=reviewer_role,
            false_negative_note=normalized_note,
            outcome_label="missed",
        )
        return _serialize_event(event)


def fetch_report_feedback_state(analysis_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        report = get_analysis_report(session, analysis_id, include_evidence=False)
        if report is None:
            raise FeedbackError(
                "analysis_not_found",
                f"Analysis report not found: {analysis_id}.",
            )
        events = list_feedback_events(session, analysis_id=analysis_id)
    finding_feedback: dict[str, dict[str, Any]] = {}
    false_negative_notes: list[dict[str, Any]] = []
    for event in events:
        serialized = _serialize_event(event)
        if event.finding_id is not None and event.finding_id not in finding_feedback:
            finding_feedback[event.finding_id] = serialized
        if event.false_negative_note:
            false_negative_notes.append(serialized)
    return {
        "finding_feedback": finding_feedback,
        "false_negative_notes": false_negative_notes,
    }


def fetch_feedback_summary(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict[str, Any]:
    project, workspace = _resolve_summary_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    with SessionLocal() as session:
        events = list_feedback_events(
            session,
            project_id=project.id,
            workspace_id=workspace.id if workspace is not None else None,
        )

    latest_finding_feedback: dict[tuple[int | None, str], Any] = {}
    latest_false_negative_by_report: dict[int | None, Any] = {}
    recent_notes: list[dict[str, Any]] = []
    for event in events:
        if event.finding_id is not None:
            latest_finding_feedback.setdefault(
                (event.analysis_id, event.finding_id), event
            )
            if event.false_positive_reason:
                recent_notes.append(
                    {
                        "type": "false_positive",
                        "text": event.false_positive_reason,
                        "analysis_id": event.analysis_id,
                        "finding_id": event.finding_id,
                        "created_at": _serialize_timestamp(event.created_at),
                    }
                )
        if event.false_negative_note:
            latest_false_negative_by_report.setdefault(event.analysis_id, event)
            recent_notes.append(
                {
                    "type": "missed_finding",
                    "text": event.false_negative_note,
                    "analysis_id": event.analysis_id,
                    "finding_id": event.finding_id,
                    "created_at": _serialize_timestamp(event.created_at),
                }
            )

    latest_events = list(latest_finding_feedback.values())
    useful_count = sum(1 for event in latest_events if event.useful is True)
    not_useful_count = sum(1 for event in latest_events if event.useful is False)
    false_positive_count = sum(
        1 for event in latest_events if bool(event.false_positive_flag)
    )

    recent_notes.sort(key=lambda item: item["created_at"], reverse=True)
    return {
        "project": build_project_payload(project),
        "current_state": {
            "useful_count": useful_count,
            "not_useful_count": not_useful_count,
            "false_positive_count": false_positive_count,
            "missed_finding_count": len(latest_false_negative_by_report),
        },
        "totals": {
            "events_recorded": len(events),
        },
        "recent_notes": recent_notes[:5],
    }
