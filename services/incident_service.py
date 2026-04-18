"""Incident workflow orchestration."""

from __future__ import annotations

import re

from models.database import SessionLocal
from models.repositories.incident_records import (
    create_incident_record,
    list_incident_records,
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


def ingest_incident_document(source_file: str, content: str) -> dict:
    """Normalize and persist an incident document from markdown/plain text input."""
    normalized_content = content.strip()
    title = _extract_title(normalized_content, source_file)
    severity = _extract_severity(normalized_content)
    incident_date = _extract_incident_date(normalized_content)
    with SessionLocal() as session:
        record = create_incident_record(
            session,
            title=title,
            severity=severity,
            source_file=source_file,
            incident_date=incident_date,
            content=normalized_content,
        )
    return {
        "id": record.id,
        "title": record.title,
        "severity": record.severity,
        "source_file": record.source_file,
        "incident_date": record.incident_date,
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
            "content": record.content,
        }
        for record in records
    ]
