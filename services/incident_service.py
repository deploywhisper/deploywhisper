"""Incident workflow orchestration."""

from __future__ import annotations

import re
import json
import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from operator import attrgetter
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.database import SessionLocal
from models.repositories.incident_ingestion_sources import (
    list_incident_ingestion_sources,
    upsert_incident_ingestion_source,
)
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
REDACTION_PATTERN = re.compile(r"^Redaction status:\s*(.+?)\s*$", re.IGNORECASE)


IncidentFreshnessStatus = Literal["current", "empty", "stale"]


class IncidentIngestionFailureSummary(BaseModel):
    """Actionable import/index failure surfaced to admins."""

    source_file: str
    field: str
    message: str
    correction_path: str


class IncidentIngestionSourceStatus(BaseModel):
    """Management view for one incident import source."""

    import_source: str
    project_id: int
    workspace_id: int | None = None
    scope_label: str = "Project"
    indexed_count: int = 0
    rejected_count: int = 0
    last_indexed_at: str | None = None
    redaction_status: str = "unknown"
    freshness_status: IncidentFreshnessStatus = "empty"
    title: str | None = None
    incident_ids: list[int] = Field(default_factory=list)
    failure_summaries: list[IncidentIngestionFailureSummary] = Field(
        default_factory=list
    )


class IncidentIngestionStatus(BaseModel):
    """Project-scoped incident ingestion management status."""

    project_id: int
    workspace_id: int | None = None
    indexed_count: int = 0
    rejected_count: int = 0
    last_indexed_at: str | None = None
    index_version: str | None = None
    redaction_status: str = "unknown"
    freshness_status: IncidentFreshnessStatus = "empty"
    sources: list[IncidentIngestionSourceStatus] = Field(default_factory=list)


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


def _datetime_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _extract_redaction_status(content: str) -> str:
    for line in content.splitlines():
        match = REDACTION_PATTERN.match(line.strip())
        if match:
            value = match.group(1).strip().lower()
            return value or "unknown"
    return "unknown"


def _rollup_redaction_status(values: list[str]) -> str:
    known_values = sorted({value for value in values if value and value != "unknown"})
    if not known_values:
        return "unknown"
    if len(known_values) == 1:
        return known_values[0]
    return "mixed"


def _latest_timestamp(values: list[datetime | None]) -> str | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return _datetime_iso(max(present))


def _index_version_for_records(records: list) -> str:
    if not records:
        return "incidents:empty"
    latest = max(
        (record.created_at for record in records if record.created_at), default=None
    )
    latest_value = _datetime_iso(latest) or "unknown"
    source_parts = [
        f"{record.id}:{record.source_file}:{_datetime_iso(record.created_at) or ''}"
        for record in sorted(records, key=attrgetter("id"))
    ]
    digest = hashlib.sha256("|".join(source_parts).encode("utf-8")).hexdigest()[:12]
    return f"incidents:{len(records)}:{latest_value}:{digest}"


def _failure_summaries_from_json(
    raw_value: str | None,
) -> list[IncidentIngestionFailureSummary]:
    try:
        decoded = json.loads(raw_value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    summaries: list[IncidentIngestionFailureSummary] = []
    for item in decoded:
        if not isinstance(item, dict):
            continue
        try:
            summaries.append(IncidentIngestionFailureSummary.model_validate(item))
        except ValueError:
            continue
    return summaries


def _scope_label(workspace_id: int | None) -> str:
    if workspace_id is None:
        return "Project"
    return f"Workspace #{workspace_id}"


def _group_key(record) -> tuple[int | None, str]:
    return record.workspace_id, record.source_file


def _scope_sort_key(scope_key: tuple[int | None, str]) -> tuple[bool, int, str]:
    workspace_id, source_file = scope_key
    return workspace_id is not None, workspace_id or 0, source_file


def _source_status_from_records(
    *,
    project_id: int,
    workspace_id: int | None,
    source_file: str,
    source_records: list,
    failure_summaries: list[IncidentIngestionFailureSummary] | None = None,
    rejected_count: int = 0,
    status: str = "indexed",
) -> IncidentIngestionSourceStatus:
    redaction_statuses = [
        _extract_redaction_status(record.content) for record in source_records
    ]
    indexed_count = len(source_records)
    freshness_status: IncidentFreshnessStatus = (
        "current" if indexed_count and status != "removed" else "empty"
    )
    return IncidentIngestionSourceStatus(
        import_source=source_file,
        project_id=project_id,
        workspace_id=workspace_id,
        scope_label=_scope_label(workspace_id),
        indexed_count=indexed_count,
        rejected_count=rejected_count,
        last_indexed_at=_latest_timestamp(
            [record.created_at for record in source_records]
        ),
        redaction_status=_rollup_redaction_status(redaction_statuses),
        freshness_status=freshness_status,
        title=source_records[-1].title if source_records else None,
        incident_ids=[record.id for record in source_records],
        failure_summaries=failure_summaries or [],
    )


def create_incident_record_in_session(
    session: Session,
    *,
    source_file: str,
    content: str,
    project_id: int,
    workspace_id: int | None = None,
    analysis_id: int | None = None,
):
    """Stage a normalized incident record in an existing transaction."""
    normalized_content = content.strip()
    return create_incident_record(
        session,
        project_id=project_id,
        workspace_id=workspace_id,
        title=_extract_title(normalized_content, source_file),
        severity=_extract_severity(normalized_content),
        source_file=source_file,
        incident_date=_extract_incident_date(normalized_content),
        analysis_id=analysis_id,
        content=normalized_content,
        commit=False,
    )


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
        "created_at": _datetime_iso(record.created_at),
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
            "created_at": _datetime_iso(record.created_at),
        }
        for record in records
    ]


def get_incident_ingestion_status(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> IncidentIngestionStatus:
    """Return admin-facing incident ingestion/index status for one scope."""
    if project_id is None and project_key is None:
        raise ValueError("Project scope is required for incident ingestion status.")
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
        registered_sources = list_incident_ingestion_sources(
            session,
            project_id=project.id,
            workspace_id=workspace.id if workspace is not None else None,
        )

    grouped: dict[tuple[int | None, str], list] = defaultdict(list)
    for record in records:
        grouped[_group_key(record)].append(record)

    sources: list[IncidentIngestionSourceStatus] = []
    registry_by_key = {
        (source.workspace_id, source.source_file): source
        for source in registered_sources
    }
    for key, source_records in sorted(
        grouped.items(), key=lambda item: _scope_sort_key(item[0])
    ):
        registered = registry_by_key.pop(key, None)
        failures = (
            _failure_summaries_from_json(registered.failure_summaries_json)
            if registered is not None
            else []
        )
        rejected_count = registered.rejected_count if registered is not None else 0
        sources.append(
            _source_status_from_records(
                project_id=project.id,
                workspace_id=key[0],
                source_file=key[1],
                source_records=source_records,
                failure_summaries=failures,
                rejected_count=rejected_count,
                status=registered.status if registered is not None else "indexed",
            )
        )
    for registered in registry_by_key.values():
        failures = _failure_summaries_from_json(registered.failure_summaries_json)
        if registered.status in {"indexed", "removed"} and not failures:
            continue
        sources.append(
            IncidentIngestionSourceStatus(
                import_source=registered.source_file,
                project_id=project.id,
                workspace_id=registered.workspace_id,
                scope_label=_scope_label(registered.workspace_id),
                indexed_count=registered.indexed_count,
                rejected_count=registered.rejected_count,
                last_indexed_at=_datetime_iso(registered.last_indexed_at),
                redaction_status=registered.redaction_status,
                freshness_status=(
                    "current" if registered.status == "indexed" else "empty"
                ),
                failure_summaries=failures,
            )
        )
    sources.sort(key=lambda source: (source.workspace_id or 0, source.import_source))

    indexed_count = sum(source.indexed_count for source in sources)
    rejected_count = sum(source.rejected_count for source in sources)
    redaction_status = _rollup_redaction_status(
        [source.redaction_status for source in sources]
    )
    index_version = _index_version_for_records(records)
    return IncidentIngestionStatus(
        project_id=project.id,
        workspace_id=workspace.id if workspace is not None else None,
        indexed_count=indexed_count,
        rejected_count=rejected_count,
        last_indexed_at=_latest_timestamp(
            [
                record.created_at
                for source_records in grouped.values()
                for record in source_records
            ]
        ),
        index_version=index_version,
        redaction_status=redaction_status,
        freshness_status="current" if indexed_count else "empty",
        sources=sources,
    )


def get_incident_index_snapshot(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict[str, str | int | None]:
    """Return compact incident index state for report context snapshots."""
    status = get_incident_ingestion_status(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    return {
        "incident_index_size": status.indexed_count,
        "incident_index_version": status.index_version,
        "incident_index_last_indexed_at": status.last_indexed_at,
        "incident_index_freshness_status": status.freshness_status,
    }


def record_incident_ingestion_source_status(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
    source_file: str,
    status: str,
    indexed_count: int,
    rejected_count: int,
    redaction_status: str = "unknown",
    failure_summaries: list[IncidentIngestionFailureSummary] | None = None,
    index_version: str | None = None,
    last_indexed_at: datetime | None = None,
) -> None:
    """Persist source-level ingestion status in the current transaction."""
    upsert_incident_ingestion_source(
        session,
        project_id=project_id,
        workspace_id=workspace_id,
        source_file=source_file,
        status=status,
        indexed_count=indexed_count,
        rejected_count=rejected_count,
        redaction_status=redaction_status,
        failure_summaries_json=json.dumps(
            [failure.model_dump(mode="json") for failure in (failure_summaries or [])]
        ),
        index_version=index_version,
        last_indexed_at=last_indexed_at,
    )
