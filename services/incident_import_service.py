"""Incident file import validation and normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from models.database import SessionLocal
from models.repositories.incident_ingestion_sources import (
    list_incident_ingestion_sources,
    list_managed_incident_source_files,
)
from models.repositories.incident_records import (
    count_incident_records_by_sources,
    delete_incident_records_by_sources,
)
from services.backtesting_service import invalidate_backtesting_snapshot
from services.incident_service import (
    IncidentIngestionFailureSummary,
    IncidentIngestionStatus,
    create_incident_record_in_session,
    get_incident_ingestion_status,
    record_incident_ingestion_source_status,
)
from services.project_service import (
    ProjectResolutionError,
    resolve_project_reference,
    resolve_workspace_reference,
)


MARKDOWN_SUFFIXES = {".md", ".markdown"}
YAML_SUFFIXES = {".yaml", ".yml"}
JSON_SUFFIXES = {".json"}
REQUIRED_FIELDS = {
    "title": "title",
    "severity": "severity",
    "incident_date": "incident_date",
    "root_cause": "root_cause",
    "trigger_change": "trigger_change",
    "affected_services": "affected_services",
    "rollback_path": "rollback_path",
    "prevention_notes": "prevention_notes",
    "source.system": "source.system",
    "source.reference": "source.reference",
    "redaction.status": "redaction.status",
}


class IncidentImportFile(BaseModel):
    """A raw incident file supplied for import."""

    source_file: str
    content: str


class IncidentImportFieldError(BaseModel):
    """Field-level validation error for an incident import file."""

    source_file: str
    field: str
    message: str


class IncidentImportResult(BaseModel):
    """Result of a successful incident import batch."""

    imported: int = 0
    records: list[dict[str, Any]] = Field(default_factory=list)


class IncidentReindexResult(BaseModel):
    """Result of rebuilding incident index entries for a project scope."""

    indexed_count: int = 0
    replaced_count: int = 0
    removed_count: int = 0
    rejected_count: int = 0
    failures: list[IncidentIngestionFailureSummary] = Field(default_factory=list)
    status: IncidentIngestionStatus


class IncidentImportValidationError(ValueError):
    """Raised when incident import validation fails."""

    def __init__(self, field_errors: list[IncidentImportFieldError]) -> None:
        self.field_errors = field_errors
        detail = "; ".join(
            f"{error.source_file}:{error.field}: {error.message}"
            for error in field_errors
        )
        super().__init__(f"Incident import validation failed: {detail}")


def import_incident_files(
    files: list[IncidentImportFile],
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> IncidentImportResult:
    """Validate and import simple Markdown, YAML, and JSON incident files."""
    field_errors: list[IncidentImportFieldError] = []
    if project_id is None and project_key is None:
        field_errors.append(
            IncidentImportFieldError(
                source_file="batch",
                field="project",
                message="Project scope is required for incident imports.",
            )
        )
        raise IncidentImportValidationError(field_errors)

    try:
        project = resolve_project_reference(
            project_id=project_id, project_key=project_key
        )
        workspace = resolve_workspace_reference(
            project_id=project.id,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    except ProjectResolutionError as exc:
        raise IncidentImportValidationError(
            [
                IncidentImportFieldError(
                    source_file="batch",
                    field=_scope_error_field(exc),
                    message=exc.message,
                )
            ]
        ) from exc

    resolved_workspace_id = workspace.id if workspace is not None else None
    parsed_records: list[tuple[IncidentImportFile, dict[str, Any]]] = []
    for item in files:
        try:
            parsed = _parse_incident_file(item)
        except ValueError as exc:
            field_errors.append(
                IncidentImportFieldError(
                    source_file=item.source_file,
                    field="content",
                    message=str(exc),
                )
            )
            continue
        field_errors.extend(_validate_record(item.source_file, parsed))
        parsed_records.append((item, parsed))

    if not files:
        field_errors.append(
            IncidentImportFieldError(
                source_file="batch",
                field="files",
                message="At least one incident file is required.",
            )
        )
    if field_errors:
        _record_source_failures(
            project_id=project.id,
            workspace_id=resolved_workspace_id,
            errors=field_errors,
        )
        raise IncidentImportValidationError(field_errors)

    records: list[dict[str, Any]] = []
    with SessionLocal() as session:
        with session.begin():
            for item, parsed in parsed_records:
                record = create_incident_record_in_session(
                    session,
                    source_file=item.source_file,
                    content=_normalized_incident_content(parsed),
                    project_id=project.id,
                    workspace_id=resolved_workspace_id,
                )
                record_incident_ingestion_source_status(
                    session,
                    project_id=project.id,
                    workspace_id=resolved_workspace_id,
                    source_file=item.source_file,
                    status="indexed",
                    indexed_count=1,
                    rejected_count=0,
                    redaction_status=_redaction_status(parsed),
                    failure_summaries=[],
                    index_version=None,
                    last_indexed_at=record.created_at,
                )
                records.append(
                    {
                        "id": record.id,
                        "project_id": record.project_id,
                        "workspace_id": record.workspace_id,
                        "title": record.title,
                        "severity": record.severity,
                        "source_file": record.source_file,
                        "incident_date": record.incident_date,
                        "analysis_id": record.analysis_id,
                        "created_at": record.created_at.isoformat()
                        if record.created_at is not None
                        else None,
                    }
                )
    invalidate_backtesting_snapshot(project_id=project.id)
    return IncidentImportResult(imported=len(records), records=records)


def reindex_incident_files(
    files: list[IncidentImportFile],
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    remove_missing_sources: bool = False,
) -> IncidentReindexResult:
    """Replace indexed incident entries from source files within one project scope."""
    field_errors: list[IncidentImportFieldError] = []
    if project_id is None and project_key is None:
        field_errors.append(
            IncidentImportFieldError(
                source_file="batch",
                field="project",
                message="Project scope is required for incident reindexing.",
            )
        )
        raise IncidentImportValidationError(field_errors)

    project = resolve_project_reference(project_id=project_id, project_key=project_key)
    workspace = resolve_workspace_reference(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    resolved_workspace_id = workspace.id if workspace is not None else None

    seen_source_files: set[str] = set()
    duplicate_source_files: set[str] = set()
    for item in files:
        if item.source_file in seen_source_files:
            duplicate_source_files.add(item.source_file)
        seen_source_files.add(item.source_file)
    for source_file in sorted(duplicate_source_files):
        field_errors.append(
            IncidentImportFieldError(
                source_file=source_file,
                field="source_file",
                message="Each source_file may appear only once per reindex request.",
            )
        )

    parsed_records: list[tuple[IncidentImportFile, dict[str, Any]]] = []
    for item in files:
        try:
            parsed = _parse_incident_file(item)
        except ValueError as exc:
            field_errors.append(
                IncidentImportFieldError(
                    source_file=item.source_file,
                    field="content",
                    message=str(exc),
                )
            )
            continue
        field_errors.extend(_validate_record(item.source_file, parsed))
        parsed_records.append((item, parsed))

    if not files and not remove_missing_sources:
        field_errors.append(
            IncidentImportFieldError(
                source_file="batch",
                field="files",
                message="At least one incident file is required.",
            )
        )
    if field_errors:
        _record_source_failures(
            project_id=project.id,
            workspace_id=resolved_workspace_id,
            errors=field_errors,
        )
        raise IncidentImportValidationError(field_errors)

    source_files = sorted({item.source_file for item, _ in parsed_records})
    with SessionLocal() as session:
        with session.begin():
            project_wide_scope = resolved_workspace_id is None
            removed_source_refs: list[tuple[int | None, str]]
            if project_wide_scope:
                managed_source_refs = [
                    (source.workspace_id, source.source_file)
                    for source in list_incident_ingestion_sources(
                        session,
                        project_id=project.id,
                    )
                    if source.status != "removed"
                ]
                removed_source_refs = (
                    sorted(
                        [
                            source_ref
                            for source_ref in managed_source_refs
                            if source_ref[1] not in source_files
                        ],
                        key=lambda source_ref: (
                            source_ref[0] is not None,
                            source_ref[0] or 0,
                            source_ref[1],
                        ),
                    )
                    if remove_missing_sources
                    else []
                )
            else:
                managed_source_files = list_managed_incident_source_files(
                    session,
                    project_id=project.id,
                    workspace_id=resolved_workspace_id,
                )
                removed_source_refs = (
                    [
                        (resolved_workspace_id, source_file)
                        for source_file in sorted(
                            set(managed_source_files) - set(source_files)
                        )
                    ]
                    if remove_missing_sources
                    else []
                )
            replaced_count = (
                count_incident_records_by_sources(
                    session,
                    project_id=project.id,
                    workspace_id=resolved_workspace_id,
                    source_files=source_files,
                )
                if source_files
                else 0
            )
            removed_count = sum(
                count_incident_records_by_sources(
                    session,
                    project_id=project.id,
                    workspace_id=source_workspace_id,
                    source_files=[source_file],
                )
                for source_workspace_id, source_file in removed_source_refs
            )
            delete_incident_records_by_sources(
                session,
                project_id=project.id,
                workspace_id=resolved_workspace_id,
                source_files=source_files,
                commit=False,
            )
            for source_workspace_id, source_file in removed_source_refs:
                delete_incident_records_by_sources(
                    session,
                    project_id=project.id,
                    workspace_id=source_workspace_id,
                    source_files=[source_file],
                    commit=False,
                )
            for item, parsed in parsed_records:
                record = create_incident_record_in_session(
                    session,
                    source_file=item.source_file,
                    content=_normalized_incident_content(parsed),
                    project_id=project.id,
                    workspace_id=resolved_workspace_id,
                )
                record_incident_ingestion_source_status(
                    session,
                    project_id=project.id,
                    workspace_id=resolved_workspace_id,
                    source_file=item.source_file,
                    status="indexed",
                    indexed_count=1,
                    rejected_count=0,
                    redaction_status=_redaction_status(parsed),
                    failure_summaries=[],
                    index_version=None,
                    last_indexed_at=record.created_at,
                )
            for source_workspace_id, source_file in removed_source_refs:
                record_incident_ingestion_source_status(
                    session,
                    project_id=project.id,
                    workspace_id=source_workspace_id,
                    source_file=source_file,
                    status="removed",
                    indexed_count=0,
                    rejected_count=0,
                    redaction_status="unknown",
                    failure_summaries=[],
                    index_version=None,
                )

    invalidate_backtesting_snapshot(project_id=project.id)
    return IncidentReindexResult(
        indexed_count=len(parsed_records),
        replaced_count=replaced_count,
        removed_count=removed_count,
        rejected_count=0,
        failures=[],
        status=get_incident_ingestion_status(
            project_id=project.id,
            workspace_id=resolved_workspace_id,
        ),
    )


def incident_import_failure_summaries(
    errors: list[IncidentImportFieldError],
) -> list[IncidentIngestionFailureSummary]:
    """Convert validation failures into admin-actionable correction paths."""
    return [
        IncidentIngestionFailureSummary(
            source_file=error.source_file,
            field=error.field,
            message=error.message,
            correction_path=_correction_path(error.field),
        )
        for error in errors
    ]


def _record_source_failures(
    *,
    project_id: int,
    workspace_id: int | None,
    errors: list[IncidentImportFieldError],
) -> None:
    source_errors = [error for error in errors if error.source_file != "batch"]
    if not source_errors:
        return
    summaries = incident_import_failure_summaries(source_errors)
    summaries_by_source: dict[str, list[IncidentIngestionFailureSummary]] = {}
    for summary in summaries:
        summaries_by_source.setdefault(summary.source_file, []).append(summary)
    with SessionLocal() as session:
        with session.begin():
            for source_file, failures in summaries_by_source.items():
                record_incident_ingestion_source_status(
                    session,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    source_file=source_file,
                    status="failed",
                    indexed_count=0,
                    rejected_count=len(failures),
                    redaction_status="unknown",
                    failure_summaries=failures,
                    index_version=None,
                )


def _parse_incident_file(item: IncidentImportFile) -> dict[str, Any]:
    suffix = Path(item.source_file).suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:
        return _parse_markdown_incident(item.content)
    if suffix in YAML_SUFFIXES:
        try:
            payload = yaml.safe_load(item.content)
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML incident is invalid: {exc}") from exc
        return _ensure_mapping(payload, "YAML incident")
    if suffix in JSON_SUFFIXES:
        try:
            payload = json.loads(item.content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON incident is invalid: {exc}") from exc
        return _ensure_mapping(payload, "JSON incident")
    raise ValueError(
        "Unsupported incident file type. Expected Markdown, YAML, or JSON."
    )


def _parse_markdown_incident(content: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    body = content
    if content.startswith("---\n"):
        frontmatter, body = _split_markdown_frontmatter(content)
        try:
            payload = yaml.safe_load(frontmatter) if frontmatter.strip() else {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Markdown frontmatter is invalid: {exc}") from exc
        metadata = _ensure_mapping(
            payload,
            "Markdown frontmatter",
        )
    sections = _markdown_sections(body)
    parsed = dict(metadata)
    parsed.setdefault("title", _markdown_title(body))
    parsed.setdefault("root_cause", sections.get("root cause", ""))
    parsed.setdefault("trigger_change", sections.get("trigger change", ""))
    parsed.setdefault("rollback_path", sections.get("rollback path", ""))
    parsed.setdefault("prevention_notes", sections.get("prevention notes", ""))
    return parsed


def _split_markdown_frontmatter(content: str) -> tuple[str, str]:
    lines = content.splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            frontmatter = "\n".join(lines[1:index])
            body = "\n".join(lines[index + 1 :])
            return frontmatter, body
    raise ValueError("Markdown frontmatter is missing a closing delimiter.")


def _markdown_title(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _markdown_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).strip().lower()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _ensure_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def _validate_record(
    source_file: str,
    record: dict[str, Any],
) -> list[IncidentImportFieldError]:
    errors: list[IncidentImportFieldError] = []
    for field, label in REQUIRED_FIELDS.items():
        if not _has_value(_field_value(record, field)):
            errors.append(
                IncidentImportFieldError(
                    source_file=source_file,
                    field=field,
                    message=f"{label} is required.",
                )
            )
    for field in ("affected_services", "prevention_notes"):
        if _has_value(record.get(field)) and not _string_list(record[field]):
            errors.append(
                IncidentImportFieldError(
                    source_file=source_file,
                    field=field,
                    message=f"{field} must contain at least one text value.",
                )
            )
    redaction_value = _field_value(record, "redaction.contains_sensitive_data")
    if redaction_value is not None and _boolean_text(redaction_value) is None:
        errors.append(
            IncidentImportFieldError(
                source_file=source_file,
                field="redaction.contains_sensitive_data",
                message="redaction.contains_sensitive_data must be true or false.",
            )
        )
    return errors


def _field_value(record: dict[str, Any], field: str) -> Any:
    value: Any = record
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return True


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        if not value:
            return []
        values: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                return []
            values.append(item.strip())
        return values
    return []


def _scope_error_field(exc: ProjectResolutionError) -> str:
    if "workspace" in exc.code:
        return "workspace"
    return "project"


def _correction_path(field: str) -> str:
    if field == "project":
        return "Select an existing project or provide project_id/project_key before importing incidents."
    if field == "workspace":
        return "Select a workspace that belongs to the chosen project or omit workspace scope."
    if field == "files":
        return "Add at least one Markdown, YAML, or JSON incident file."
    if field == "content":
        return "Fix the file syntax or use a supported Markdown, YAML, or JSON incident format."
    if field.startswith("source."):
        return "Add source.system and source.reference so admins can trace the incident origin."
    if field.startswith("redaction."):
        return "Add redaction.status and use true or false for redaction.contains_sensitive_data."
    return f"Add or correct the {field} field in this incident file."


def _boolean_text(value: Any) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return "true"
        if normalized in {"false", "no", "0"}:
            return "false"
    return None


def _normalized_incident_content(record: dict[str, Any]) -> str:
    source = _field_value(record, "source") or {}
    redaction = _field_value(record, "redaction") or {}
    prevention_notes = _string_list(record["prevention_notes"])
    if not prevention_notes and isinstance(record["prevention_notes"], str):
        prevention_notes = [record["prevention_notes"]]
    lines = [
        f"# {record['title']}",
        f"Date: {record['incident_date']}",
        f"Severity: {record['severity']}",
        f"Source system: {source['system']}",
        f"Source reference: {source['reference']}",
        f"Redaction status: {redaction['status']}",
        "",
        "## Root cause",
        str(record["root_cause"]).strip(),
        "",
        "## Trigger change",
        str(record["trigger_change"]).strip(),
        "",
        "## Affected services",
        *_bullet_lines(_string_list(record["affected_services"])),
        "",
        "## Rollback path",
        str(record["rollback_path"]).strip(),
        "",
        "## Prevention notes",
        *_bullet_lines(prevention_notes),
    ]
    contains_sensitive_data = redaction.get("contains_sensitive_data")
    if contains_sensitive_data is not None:
        lines.insert(
            6,
            f"Contains sensitive data: {_boolean_text(contains_sensitive_data)}",
        )
    return "\n".join(lines).strip()


def _redaction_status(record: dict[str, Any]) -> str:
    value = _field_value(record, "redaction.status")
    normalized = str(value or "").strip().lower()
    return normalized or "unknown"


def _bullet_lines(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values]
