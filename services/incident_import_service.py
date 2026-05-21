"""Incident file import validation and normalization."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from services.incident_service import ingest_incident_document
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

    records = [
        ingest_incident_document(
            item.source_file,
            _normalized_incident_content(parsed),
            project_id=project.id,
            workspace_id=workspace.id if workspace is not None else None,
        )
        for item, parsed in parsed_records
    ]
    return IncidentImportResult(imported=len(records), records=records)


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


def _bullet_lines(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values]
