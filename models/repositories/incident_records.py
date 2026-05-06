"""Incident records repository."""

from __future__ import annotations

from sqlalchemy import select
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
    session.commit()
    session.refresh(record)
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
