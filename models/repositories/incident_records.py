"""Incident records repository."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.tables import IncidentRecord


def create_incident_record(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    title: str,
    severity: str,
    source_file: str,
    incident_date: str | None,
    analysis_id: int | None = None,
    content: str,
    commit: bool = True,
) -> IncidentRecord:
    record = IncidentRecord(
        project_id=project_id,
        workspace_id=workspace_id,
        title=title,
        severity=severity,
        source_file=source_file,
        incident_date=incident_date,
        analysis_id=analysis_id,
        content=content,
    )
    session.add(record)
    if commit:
        session.commit()
        session.refresh(record)
    else:
        session.flush()
    return record


def list_incident_records(
    session: Session,
    *,
    project_id: int | None = None,
    workspace_id: int | None = None,
) -> list[IncidentRecord]:
    stmt = select(IncidentRecord).order_by(IncidentRecord.id.asc())
    if project_id is not None:
        stmt = stmt.where(IncidentRecord.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(IncidentRecord.workspace_id == workspace_id)
    result = session.execute(stmt)
    return list(result.scalars().all())


def get_incident_record(session: Session, record_id: int) -> IncidentRecord | None:
    return session.get(IncidentRecord, record_id)


def count_incident_records_by_sources(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    source_files: list[str] | None = None,
) -> int:
    stmt = select(IncidentRecord)
    stmt = stmt.where(IncidentRecord.project_id == project_id)
    if workspace_id is None:
        stmt = stmt.where(IncidentRecord.workspace_id.is_(None))
    else:
        stmt = stmt.where(IncidentRecord.workspace_id == workspace_id)
    if source_files is not None:
        stmt = stmt.where(IncidentRecord.source_file.in_(source_files))
    result = session.execute(stmt)
    return len(result.scalars().all())


def delete_incident_records_by_sources(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    source_files: list[str] | None = None,
    exclude_source_files: list[str] | None = None,
    commit: bool = True,
) -> int:
    stmt = delete(IncidentRecord).where(IncidentRecord.project_id == project_id)
    if workspace_id is None:
        stmt = stmt.where(IncidentRecord.workspace_id.is_(None))
    else:
        stmt = stmt.where(IncidentRecord.workspace_id == workspace_id)
    if source_files is not None:
        stmt = stmt.where(IncidentRecord.source_file.in_(source_files))
    if exclude_source_files is not None:
        stmt = stmt.where(IncidentRecord.source_file.not_in(exclude_source_files))
    result = session.execute(stmt)
    if commit:
        session.commit()
    return int(result.rowcount or 0)
