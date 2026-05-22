"""Incident ingestion source status repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.tables import IncidentIngestionSource


def _scope_predicate(stmt, *, project_id: int, workspace_id: int | None = None):
    stmt = stmt.where(IncidentIngestionSource.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(IncidentIngestionSource.workspace_id == workspace_id)
    return stmt


def get_incident_ingestion_source(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
    source_file: str,
) -> IncidentIngestionSource | None:
    stmt = select(IncidentIngestionSource).where(
        IncidentIngestionSource.project_id == project_id,
        IncidentIngestionSource.source_file == source_file,
    )
    if workspace_id is None:
        stmt = stmt.where(IncidentIngestionSource.workspace_id.is_(None))
    else:
        stmt = stmt.where(IncidentIngestionSource.workspace_id == workspace_id)
    return session.execute(stmt).scalar_one_or_none()


def list_incident_ingestion_sources(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
) -> list[IncidentIngestionSource]:
    stmt = select(IncidentIngestionSource).order_by(
        IncidentIngestionSource.workspace_id.asc(),
        IncidentIngestionSource.source_file.asc(),
        IncidentIngestionSource.id.asc(),
    )
    stmt = _scope_predicate(stmt, project_id=project_id, workspace_id=workspace_id)
    return list(session.execute(stmt).scalars().all())


def list_managed_incident_source_files(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
) -> list[str]:
    stmt = select(IncidentIngestionSource.source_file).where(
        IncidentIngestionSource.project_id == project_id,
        IncidentIngestionSource.status != "removed",
    )
    if workspace_id is None:
        stmt = stmt.where(IncidentIngestionSource.workspace_id.is_(None))
    else:
        stmt = stmt.where(IncidentIngestionSource.workspace_id == workspace_id)
    return list(session.execute(stmt).scalars().all())


def upsert_incident_ingestion_source(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
    source_file: str,
    status: str,
    indexed_count: int,
    rejected_count: int,
    redaction_status: str,
    failure_summaries_json: str,
    index_version: str | None,
    last_indexed_at: datetime | None = None,
) -> IncidentIngestionSource:
    now = datetime.now(UTC)
    source = get_incident_ingestion_source(
        session,
        project_id=project_id,
        workspace_id=workspace_id,
        source_file=source_file,
    )
    if source is None:
        source = IncidentIngestionSource(
            project_id=project_id,
            workspace_id=workspace_id,
            source_file=source_file,
            created_at=now,
        )
        session.add(source)
    source.status = status
    source.indexed_count = indexed_count
    source.rejected_count = rejected_count
    source.redaction_status = redaction_status
    source.failure_summaries_json = failure_summaries_json
    source.index_version = index_version
    source.last_indexed_at = last_indexed_at
    source.updated_at = now
    return source
