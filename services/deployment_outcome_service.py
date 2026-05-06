"""Deployment outcome capture and retrieval helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from models.database import SessionLocal
from models.repositories.analysis_reports import get_analysis_report
from models.repositories.deployment_outcomes import (
    create_deployment_outcome as create_deployment_outcome_record,
)
from models.repositories.deployment_outcomes import (
    list_deployment_outcomes as list_deployment_outcome_records,
)
from models.repositories.incident_records import get_incident_record
from models.repositories.projects import get_project, get_project_by_key
from services.backtesting_service import invalidate_backtesting_snapshot
from services.project_service import ensure_default_project, normalize_project_key
from services.project_service import resolve_workspace_reference

ALLOWED_DEPLOYMENT_OUTCOMES = {"success", "failure", "rolled_back"}


class DeploymentOutcomeError(ValueError):
    """Raised when a deployment outcome request is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_outcome(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized not in ALLOWED_DEPLOYMENT_OUTCOMES:
        raise DeploymentOutcomeError(
            "invalid_deployment_outcome",
            "Outcome must be one of: success, failure, rolled_back.",
        )
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _coerce_timestamp(value: str | datetime | None) -> datetime:
    if value is None or (isinstance(value, str) and not value.strip()):
        return datetime.now(UTC)
    if isinstance(value, datetime):
        timestamp = value
    else:
        candidate = str(value).strip()
        try:
            timestamp = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DeploymentOutcomeError(
                "invalid_deployed_at",
                "deployed_at must be a valid ISO 8601 timestamp.",
            ) from exc
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _serialize_project(project) -> dict[str, Any]:
    created_at = project.created_at
    updated_at = project.updated_at
    return {
        "id": project.id,
        "project_key": project.project_key,
        "display_name": project.display_name,
        "description": project.description,
        "repository_url": project.repository_url,
        "default_branch": project.default_branch,
        "is_default": bool(project.is_default),
        "created_at": _isoformat_utc(created_at),
        "updated_at": _isoformat_utc(updated_at),
    }


def _serialize_workspace(workspace) -> dict[str, Any]:
    created_at = workspace.created_at
    updated_at = workspace.updated_at
    project_key = workspace.project.project_key if workspace.project is not None else ""
    return {
        "id": workspace.id,
        "project_id": workspace.project_id,
        "project_key": project_key,
        "workspace_key": workspace.workspace_key,
        "display_name": workspace.display_name,
        "description": workspace.description,
        "environment": workspace.environment,
        "created_at": _isoformat_utc(created_at),
        "updated_at": _isoformat_utc(updated_at),
    }


def _serialize_deployment_outcome(outcome) -> dict[str, Any]:
    deployed_at = outcome.deployed_at or outcome.created_at
    return {
        "id": outcome.id,
        "project": _serialize_project(outcome.project),
        "workspace": _serialize_workspace(outcome.workspace)
        if outcome.workspace is not None
        else None,
        "analysis_id": outcome.analysis_id,
        "outcome": outcome.outcome_label,
        "deployed_at": _isoformat_utc(deployed_at),
        "linked_incident_id": outcome.linked_incident_id,
        "environment": outcome.environment,
        "summary": outcome.summary,
        "created_at": _isoformat_utc(outcome.created_at),
    }


def _isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat()


def _resolve_requested_project(
    session,
    *,
    project_id: int | None,
    project_key: str | None,
):
    try:
        normalized_key = normalize_project_key(project_key) if project_key else None
    except ValueError as exc:
        raise DeploymentOutcomeError(
            "invalid_project_request",
            str(exc),
        ) from exc
    project_by_id = get_project(session, project_id) if project_id is not None else None
    project_by_key = (
        get_project_by_key(session, normalized_key)
        if normalized_key is not None
        else None
    )
    if project_id is not None and project_by_id is None:
        detail = (
            f"project_id={project_id}, project_key={normalized_key}"
            if normalized_key is not None
            else f"project_id={project_id}"
        )
        raise DeploymentOutcomeError(
            "project_not_found",
            f"Unknown project reference: {detail}.",
        )
    if normalized_key is not None and project_by_key is None:
        detail = (
            f"project_id={project_id}, project_key={normalized_key}"
            if project_id is not None
            else f"project_key={normalized_key}"
        )
        raise DeploymentOutcomeError(
            "project_not_found",
            f"Unknown project reference: {detail}.",
        )
    if (
        project_by_id is not None
        and project_by_key is not None
        and project_by_id.id != project_by_key.id
    ):
        raise DeploymentOutcomeError(
            "conflicting_project_reference",
            "The supplied project_id and project_key refer to different projects.",
        )
    return project_by_id or project_by_key


def record_deployment_outcome(
    *,
    analysis_id: int,
    outcome: str,
    deployed_at: str | datetime | None = None,
    linked_incident_id: int | None = None,
    environment: str | None = None,
    summary: str | None = None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    source_interface: str | None = None,
) -> dict[str, Any]:
    del source_interface
    normalized_outcome = _normalize_outcome(outcome)
    normalized_timestamp = _coerce_timestamp(deployed_at)
    linked_project_id: int | None = None

    with SessionLocal() as session:
        report = get_analysis_report(session, analysis_id, include_evidence=False)
        if report is None:
            raise DeploymentOutcomeError(
                "analysis_not_found",
                f"Analysis report not found: {analysis_id}.",
            )
        requested_project = _resolve_requested_project(
            session,
            project_id=project_id,
            project_key=project_key,
        )
        if requested_project is not None and requested_project.id != report.project_id:
            raise DeploymentOutcomeError(
                "conflicting_project_reference",
                "The supplied project reference does not match the analysis report project.",
            )
        requested_workspace = resolve_workspace_reference(
            project_id=report.project_id,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
        if (
            requested_workspace is not None
            and requested_workspace.id != report.workspace_id
        ):
            raise DeploymentOutcomeError(
                "conflicting_workspace_reference",
                "The supplied workspace reference does not match the analysis report workspace.",
            )
        linked_project_id = report.project_id
        if linked_incident_id is not None:
            incident = get_incident_record(session, linked_incident_id)
            if incident is None:
                raise DeploymentOutcomeError(
                    "incident_not_found",
                    f"Incident record not found: {linked_incident_id}.",
                )
            if incident.project_id != report.project_id:
                raise DeploymentOutcomeError(
                    "conflicting_incident_scope",
                    "The linked incident belongs to a different project.",
                )
            if (
                incident.workspace_id is not None
                and report.workspace_id is not None
                and incident.workspace_id != report.workspace_id
            ):
                raise DeploymentOutcomeError(
                    "conflicting_incident_scope",
                    "The linked incident belongs to a different workspace.",
                )
        recorded = create_deployment_outcome_record(
            session,
            project_id=report.project_id,
            workspace_id=report.workspace_id,
            analysis_id=analysis_id,
            outcome_label=normalized_outcome,
            deployed_at=normalized_timestamp,
            linked_incident_id=linked_incident_id,
            environment=_normalize_optional_text(environment),
            summary=_normalize_optional_text(summary),
        )
        payload = _serialize_deployment_outcome(recorded)
    if linked_project_id is not None:
        invalidate_backtesting_snapshot(project_id=linked_project_id)
    return payload


def list_deployment_outcomes(
    *,
    analysis_id: int | None = None,
    outcome: str | None = None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    normalized_outcome = _normalize_outcome(outcome) if outcome is not None else None
    with SessionLocal() as session:
        requested_project = _resolve_requested_project(
            session,
            project_id=project_id,
            project_key=project_key,
        )
        resolved_project_id = (
            requested_project.id if requested_project is not None else None
        )
        resolved_workspace_id = None
        if analysis_id is not None:
            report = get_analysis_report(session, analysis_id, include_evidence=False)
            if report is None:
                raise DeploymentOutcomeError(
                    "analysis_not_found",
                    f"Analysis report not found: {analysis_id}.",
                )
            if (
                requested_project is not None
                and requested_project.id != report.project_id
            ):
                raise DeploymentOutcomeError(
                    "conflicting_project_reference",
                    "The supplied project reference does not match the analysis report project.",
                )
            resolved_project_id = report.project_id
            resolved_workspace_id = report.workspace_id
        if resolved_project_id is None:
            resolved_project_id = ensure_default_project().id
        requested_workspace = resolve_workspace_reference(
            project_id=resolved_project_id,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
        if requested_workspace is not None:
            if (
                resolved_workspace_id is not None
                and requested_workspace.id != resolved_workspace_id
            ):
                raise DeploymentOutcomeError(
                    "conflicting_workspace_reference",
                    "The supplied workspace reference does not match the analysis report workspace.",
                )
            resolved_workspace_id = requested_workspace.id
        outcomes = list_deployment_outcome_records(
            session,
            project_id=resolved_project_id,
            workspace_id=resolved_workspace_id,
            analysis_id=analysis_id,
            outcome_label=normalized_outcome,
            limit=limit,
        )
        return [_serialize_deployment_outcome(item) for item in outcomes]
