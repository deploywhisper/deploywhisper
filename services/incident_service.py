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
) -> dict:
    """Normalize and persist an incident document from markdown/plain text input."""
    normalized_content = content.strip()
    title = _extract_title(normalized_content, source_file)
    severity = _extract_severity(normalized_content)
    incident_date = _extract_incident_date(normalized_content)
    report = None
    linked_project_id: int | None = None
    with SessionLocal() as session:
        if analysis_id is not None:
            report = get_analysis_report(session, analysis_id, include_evidence=False)
        if analysis_id is not None and report is None:
            raise ValueError(f"Analysis report not found: {analysis_id}.")
        if report is not None:
            linked_project_id = report.project_id
        record = create_incident_record(
            session,
            title=title,
            severity=severity,
            source_file=source_file,
            incident_date=incident_date,
            analysis_id=analysis_id,
            content=normalized_content,
        )
    if linked_project_id is not None:
        invalidate_backtesting_snapshot(project_id=linked_project_id)
    return {
        "id": record.id,
        "title": record.title,
        "severity": record.severity,
        "source_file": record.source_file,
        "incident_date": record.incident_date,
        "analysis_id": record.analysis_id,
    }


def get_incident_records() -> list[dict]:
    """Return stored incidents for later matching workflows."""
    with SessionLocal() as session:
        records = list_incident_records(session)
    return [
        {
            "id": record.id,
            "title": record.title,
            "severity": record.severity,
            "source_file": record.source_file,
            "incident_date": record.incident_date,
            "analysis_id": record.analysis_id,
            "content": record.content,
        }
        for record in records
    ]
