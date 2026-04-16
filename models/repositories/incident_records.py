"""Incident records repository."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.tables import IncidentRecord


def create_incident_record(
    session: Session,
    *,
    title: str,
    severity: str,
    source_file: str,
    incident_date: str | None,
    content: str,
) -> IncidentRecord:
    record = IncidentRecord(
        title=title,
        severity=severity,
        source_file=source_file,
        incident_date=incident_date,
        content=content,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_incident_records(session: Session) -> list[IncidentRecord]:
    result = session.execute(select(IncidentRecord).order_by(IncidentRecord.id.asc()))
    return list(result.scalars().all())


def get_incident_record(session: Session, record_id: int) -> IncidentRecord | None:
    return session.get(IncidentRecord, record_id)
