"""External scanner import repository helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.tables import ExternalScannerEvidence, ScannerImport


def create_scanner_import(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
    workspace_key: str | None,
    source_file: str,
    scanner_format: str = "sarif",
    tool_names: list[str],
    imported_count: int,
    rejected_count: int,
    failure_summaries: list[dict[str, str]],
) -> ScannerImport:
    """Create one scanner import status row."""
    now = datetime.now(UTC)
    record = ScannerImport(
        project_id=project_id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
        source_file=source_file,
        format=scanner_format,
        tool_names_json=json.dumps(tool_names),
        status="imported" if rejected_count == 0 else "failed",
        imported_count=imported_count,
        rejected_count=rejected_count,
        failure_summaries_json=json.dumps(failure_summaries),
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    session.flush()
    return record


def create_external_scanner_evidence(
    session: Session,
    *,
    import_id: int,
    evidence_id: str,
    project_id: int,
    project_key: str,
    workspace_id: int | None,
    workspace_key: str | None,
    source_file: str,
    source_ref: str,
    tool_name: str,
    rule_id: str,
    rule_name: str | None,
    severity: str,
    level: str | None,
    message: str,
    location: str,
    artifact_uri: str,
    region: dict,
    properties: dict,
) -> ExternalScannerEvidence:
    """Create an external scanner evidence row."""
    record = ExternalScannerEvidence(
        import_id=import_id,
        evidence_id=evidence_id,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
        source_type="external_scanner",
        source_file=source_file,
        source_ref=source_ref,
        tool_name=tool_name,
        rule_id=rule_id,
        rule_name=rule_name,
        severity=severity,
        level=level,
        message=message,
        location=location,
        artifact_uri=artifact_uri,
        region_json=json.dumps(region),
        properties_json=json.dumps(properties),
    )
    session.add(record)
    return record


def find_existing_external_scanner_evidence_by_source_ref(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
    workspace_key: str | None,
    source_refs: list[str],
) -> dict[str, ExternalScannerEvidence]:
    """Return already persisted scanner evidence keyed by source ref."""
    if not source_refs:
        return {}
    stmt = select(ExternalScannerEvidence).where(
        ExternalScannerEvidence.project_id == project_id,
        ExternalScannerEvidence.source_ref.in_(source_refs),
    )
    if workspace_id is None:
        stmt = stmt.where(
            ExternalScannerEvidence.workspace_id.is_(None),
            ExternalScannerEvidence.workspace_key.is_(None),
        )
    elif workspace_key:
        stmt = stmt.where(
            (ExternalScannerEvidence.workspace_id == workspace_id)
            | (
                (ExternalScannerEvidence.workspace_id.is_(None))
                & (ExternalScannerEvidence.workspace_key == workspace_key)
            )
        )
    else:
        stmt = stmt.where(ExternalScannerEvidence.workspace_id == workspace_id)
    return {record.source_ref: record for record in session.execute(stmt).scalars()}


def refresh_external_scanner_evidence(
    record: ExternalScannerEvidence,
    *,
    import_id: int,
    project_key: str,
    workspace_id: int | None,
    workspace_key: str | None,
    source_file: str,
    tool_name: str,
    rule_id: str,
    rule_name: str | None,
    severity: str,
    level: str | None,
    message: str,
    location: str,
    artifact_uri: str,
    region: dict,
    properties: dict,
) -> ExternalScannerEvidence:
    """Refresh an existing scanner evidence row during a rescan."""
    record.import_id = import_id
    record.project_key = project_key
    record.workspace_id = workspace_id
    record.workspace_key = workspace_key
    record.source_file = source_file
    record.tool_name = tool_name
    record.rule_id = rule_id
    record.rule_name = rule_name
    record.severity = severity
    record.level = level
    record.message = message
    record.location = location
    record.artifact_uri = artifact_uri
    record.region_json = json.dumps(region)
    record.properties_json = json.dumps(properties)
    return record


def list_external_scanner_evidence(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
) -> list[ExternalScannerEvidence]:
    """List scanner evidence in a project or workspace scope."""
    stmt = select(ExternalScannerEvidence).where(
        ExternalScannerEvidence.project_id == project_id
    )
    if workspace_id is None:
        stmt = stmt.where(
            ExternalScannerEvidence.workspace_id.is_(None),
            ExternalScannerEvidence.workspace_key.is_(None),
        )
    else:
        stmt = stmt.where(ExternalScannerEvidence.workspace_id == workspace_id)
    return list(
        session.execute(
            stmt.order_by(
                ExternalScannerEvidence.created_at.asc(),
                ExternalScannerEvidence.id.asc(),
            )
        )
        .scalars()
        .all()
    )
