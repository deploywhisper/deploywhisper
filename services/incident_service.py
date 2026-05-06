"""Incident workflow orchestration."""

from __future__ import annotations

import re

from models.database import SessionLocal
from models.repositories.analysis_reports import get_analysis_report
from models.repositories.incident_records import (
    create_incident_record,
    list_incident_records,
)
from services.backtesting_service import invalidate_backtesting_snapshot
from services.project_service import (
    resolve_project_reference,
    resolve_workspace_reference,
)

SEVERITY_PATTERN = re.compile(r"\b(P0|P1|P2|critical|high|medium|low)\b", re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"\b(20\d{2}-\d{2}-\d{2}|20\d{2}/\d{2}/\d{2}|[A-Z][a-z]+ \d{1,2}, 20\d{2})\b"
)


def _extract_title(content: str, source_file: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()
        if stripped:
            return stripped[:120]
    return source_file


def _extract_severity(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("severity"):
            continue
        match = SEVERITY_PATTERN.search(stripped)
        if match:
            severity = match.group(1).lower()
            if severity in {"p0", "p1"}:
                return "critical"
            if severity == "p2":
                return "high"
            return severity
    return "unknown"


def _extract_incident_date(content: str) -> str | None:
    match = DATE_PATTERN.search(content)
    if not match:
        return None
    return match.group(1)


def ingest_incident_document(
    source_file: str,
    content: str,
    *,
    analysis_id: int | None = None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict:
    """Normalize and persist an incident document from markdown/plain text input."""
    normalized_content = content.strip()
    title = _extract_title(normalized_content, source_file)
    severity = _extract_severity(normalized_content)
    incident_date = _extract_incident_date(normalized_content)
    report = None
    resolved_project_id: int | None = None
    resolved_workspace_id: int | None = None
    with SessionLocal() as session:
        if analysis_id is not None:
            report = get_analysis_report(session, analysis_id, include_evidence=False)
        if analysis_id is not None and report is None:
            raise ValueError(f"Analysis report not found: {analysis_id}.")
        if report is not None:
            resolved_project_id = report.project_id
            resolved_workspace_id = report.workspace_id
            requested_project = (
                resolve_project_reference(
                    project_id=project_id, project_key=project_key
                )
                if project_id is not None or project_key is not None
                else None
            )
            if (
                requested_project is not None
                and requested_project.id != resolved_project_id
            ):
                raise ValueError(
                    "The supplied project reference does not match the analysis report project."
                )
            requested_workspace = resolve_workspace_reference(
                project_id=resolved_project_id,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )
            if (
                requested_workspace is not None
                and requested_workspace.id != resolved_workspace_id
            ):
                raise ValueError(
                    "The supplied workspace reference does not match the analysis report workspace."
                )
        else:
            if project_id is None and project_key is None:
                raise ValueError("Project scope is required for incident records.")
            project = resolve_project_reference(
                project_id=project_id,
                project_key=project_key,
            )
            workspace = resolve_workspace_reference(
                project_id=project.id,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )
            resolved_project_id = project.id
            resolved_workspace_id = workspace.id if workspace is not None else None
        record = create_incident_record(
            session,
            project_id=resolved_project_id,
            workspace_id=resolved_workspace_id,
            title=title,
            severity=severity,
            source_file=source_file,
            incident_date=incident_date,
            analysis_id=analysis_id,
            content=normalized_content,
        )
    if resolved_project_id is not None:
        invalidate_backtesting_snapshot(project_id=resolved_project_id)
    return {
        "id": record.id,
        "project_id": record.project_id,
        "workspace_id": record.workspace_id,
        "title": record.title,
        "severity": record.severity,
        "source_file": record.source_file,
        "incident_date": record.incident_date,
        "analysis_id": record.analysis_id,
    }


def get_incident_records(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> list[dict]:
    """Return stored incidents for later matching workflows."""
    if project_id is None and project_key is None:
        raise ValueError("Project scope is required for incident records.")
    project = resolve_project_reference(project_id=project_id, project_key=project_key)
    workspace = resolve_workspace_reference(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    with SessionLocal() as session:
        records = list_incident_records(
            session,
            project_id=project.id,
            workspace_id=workspace.id if workspace is not None else None,
        )
    return [
        {
            "id": record.id,
            "project_id": record.project_id,
            "workspace_id": record.workspace_id,
            "title": record.title,
            "severity": record.severity,
            "source_file": record.source_file,
            "incident_date": record.incident_date,
            "analysis_id": record.analysis_id,
            "content": record.content,
        }
        for record in records
    ]
