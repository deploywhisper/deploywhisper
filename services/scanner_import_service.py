"""SARIF scanner import validation and normalization."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlencode, urlsplit

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from models.database import SessionLocal
from models.repositories.scanner_imports import (
    create_external_scanner_evidence,
    create_scanner_import,
    find_existing_external_scanner_evidence_by_source_ref,
    list_external_scanner_evidence as list_external_scanner_evidence_records,
    refresh_external_scanner_evidence,
)
from services.intake_service import (
    MAX_TOTAL_UPLOAD_BYTES,
    artifact_name_is_ownership_untrusted,
    is_sensitive_file,
    normalize_artifact_name,
    trusted_relative_artifact_path,
)
from services.project_service import (
    resolve_project_reference,
    resolve_workspace_reference,
)

SARIF_IMPORT_MAX_CONTENT_BYTES = MAX_TOTAL_UPLOAD_BYTES
SARIF_IMPORT_MAX_REQUEST_BYTES = SARIF_IMPORT_MAX_CONTENT_BYTES * 6 + 65_536
SARIF_IMPORT_MAX_RESULTS = 1000
SARIF_SOURCE_FILE_MAX_LENGTH = 255
SARIF_SOURCE_REF_MAX_LENGTH = 512
SARIF_TOOL_NAME_MAX_LENGTH = 120
SARIF_RULE_ID_MAX_LENGTH = 255
SARIF_RULE_NAME_MAX_LENGTH = 255
SARIF_LEVEL_MAX_LENGTH = 40
SUPPORTED_SARIF_SOURCE_EXTENSIONS = {".sarif", ".json"}
SEVERITY_BY_LEVEL = {
    "error": "high",
    "warning": "medium",
    "note": "low",
    "none": "low",
}
SUPPORTED_SARIF_LEVELS = frozenset(SEVERITY_BY_LEVEL)
DIRECT_SEVERITIES = {"critical", "high", "medium", "low"}
SUPPORTED_SEMGREP_SOURCE_EXTENSIONS = {".json"}
SEMGREP_IMPORT_MAX_RESULTS = SARIF_IMPORT_MAX_RESULTS
SEMGREP_SEVERITY_BY_LEVEL = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}
SEMGREP_METADATA_REPORT_FIELDS = frozenset(
    {
        "category",
        "confidence",
        "cwe",
        "impact",
        "likelihood",
        "owasp",
        "subcategory",
        "technology",
        "vulnerability_class",
    }
)
SEMGREP_METADATA_STRING_MAX_LENGTH = 512
SEMGREP_METADATA_LIST_MAX_ITEMS = 20
SEMGREP_FINGERPRINT_MAX_LENGTH = 255
SEMGREP_ENGINE_KIND_MAX_LENGTH = 80
SEMGREP_PERCENT_DECODE_MAX_ROUNDS = 8
SEMGREP_METADATA_URL_SCHEMES = frozenset({"file", "ftp", "gs", "http", "https", "s3"})
SEMGREP_METADATA_WINDOWS_PATH_RE = re.compile(r"^[a-zA-Z]:[\\/]")
SEMGREP_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


class ScannerImportFile(BaseModel):
    """A raw scanner file supplied for import."""

    source_file: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class ScannerImportFieldError(BaseModel):
    """Field-level validation error for a scanner import file."""

    source_file: str
    field: str
    message: str
    correction_path: str


class ExternalScannerEvidenceRecord(BaseModel):
    """Scanner finding normalized as external evidence."""

    id: int
    import_id: int
    evidence_id: str
    project_id: int
    project_key: str
    workspace_id: int | None = None
    workspace_key: str | None = None
    source_type: str
    source_file: str
    source_ref: str
    tool_name: str
    rule_id: str
    rule_name: str | None = None
    severity: str
    level: str | None = None
    message: str
    location: str
    artifact_uri: str
    region: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)


class ScannerImportResult(BaseModel):
    """Result of a successful scanner import."""

    import_id: int
    project_id: int
    project_key: str
    workspace_id: int | None = None
    workspace_key: str | None = None
    source_file: str
    tool_names: list[str] = Field(default_factory=list)
    imported_count: int = 0
    rejected_count: int = 0
    evidence: list[ExternalScannerEvidenceRecord] = Field(default_factory=list)


class ScannerImportValidationError(ValueError):
    """Raised when scanner import validation fails."""

    def __init__(self, field_errors: list[ScannerImportFieldError]) -> None:
        self.field_errors = field_errors
        detail = "; ".join(
            f"{error.source_file}:{error.field}: {error.message}"
            for error in field_errors
        )
        super().__init__(f"Scanner import validation failed: {detail}")


class ScannerImportPayloadTooLarge(ValueError):
    """Raised when a scanner import exceeds the local intake limit."""

    def __init__(self, *, limit_bytes: int, scope: str = "SARIF content") -> None:
        self.limit_bytes = limit_bytes
        self.scope = scope
        super().__init__(
            "Total scanner import "
            f"{scope} exceeds the {_format_limit_bytes(limit_bytes)} "
            "analysis-session limit."
        )


def _format_limit_bytes(limit_bytes: int) -> str:
    if limit_bytes % (1024 * 1024) == 0:
        return f"{limit_bytes // (1024 * 1024)} MB"
    return f"{limit_bytes} bytes"


def _decode_percent_encoded_to_fixed_point(
    value: str,
    *,
    max_rounds: int = SEMGREP_PERCENT_DECODE_MAX_ROUNDS,
) -> tuple[str, bool]:
    decoded = value
    for _ in range(max_rounds):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded, True
        decoded = next_value
    return decoded, unquote(decoded) == decoded


def _contains_control_characters(text: str) -> bool:
    return SEMGREP_CONTROL_CHAR_RE.search(text) is not None


class _ParsedSarifEvidence(BaseModel):
    field_prefix: str
    source_format: str = "sarif"
    tool_name: str
    rule_id: str
    rule_name: str | None = None
    severity: str
    level: str | None = None
    message: str
    location: str
    artifact_uri: str
    region: dict[str, Any] = Field(default_factory=dict)
    identity: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)


class _SarifRuleMetadata(BaseModel):
    name: str | None = None
    severity: str | None = None
    level: str | None = None
    message_strings: dict[str, str] = Field(default_factory=dict)


def import_sarif_file(
    file: ScannerImportFile,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> ScannerImportResult:
    """Validate and import SARIF results as project-scoped external evidence."""
    file = _validate_sarif_file_envelope(file)
    parsed = _parse_sarif(file)
    return _import_parsed_scanner_evidence(
        file,
        parsed=parsed,
        scanner_format="sarif",
        format_label="SARIF",
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )


def import_semgrep_json_file(
    file: ScannerImportFile,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> ScannerImportResult:
    """Validate and import Semgrep native JSON results as external evidence."""
    file = _validate_semgrep_file_envelope(file)
    parsed = _parse_semgrep_json(file)
    return _import_parsed_scanner_evidence(
        file,
        parsed=parsed,
        scanner_format="semgrep",
        format_label="Semgrep JSON",
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )


def _import_parsed_scanner_evidence(
    file: ScannerImportFile,
    *,
    parsed: list[_ParsedSarifEvidence],
    scanner_format: str,
    format_label: str,
    project_id: int | None,
    project_key: str | None,
    workspace_id: int | None,
    workspace_key: str | None,
) -> ScannerImportResult:
    if project_id is None and project_key is None:
        raise ScannerImportValidationError(
            [
                ScannerImportFieldError(
                    source_file=file.source_file,
                    field="project",
                    message=f"Project scope is required for {format_label} imports.",
                    correction_path=(
                        f"Submit project_id or project_key with every {format_label} import."
                    ),
                )
            ]
        )

    project = resolve_project_reference(
        project_id=project_id,
        project_key=project_key,
    )
    workspace = resolve_workspace_reference(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    _validate_parsed_storage_bounds(file, parsed)
    workspace_id_value = workspace.id if workspace is not None else None
    workspace_key_value = workspace.workspace_key if workspace is not None else None
    tool_names = sorted({item.tool_name for item in parsed})
    source_refs = _source_refs_by_field(file, parsed)
    _validate_unique_source_refs(file, source_refs)

    try:
        with SessionLocal() as session:
            with session.begin():
                existing_by_source_ref = (
                    find_existing_external_scanner_evidence_by_source_ref(
                        session,
                        project_id=project.id,
                        workspace_id=workspace_id_value,
                        workspace_key=workspace_key_value,
                        source_refs=list(source_refs.values()),
                    )
                )
                scanner_import = create_scanner_import(
                    session,
                    project_id=project.id,
                    workspace_id=workspace_id_value,
                    workspace_key=workspace_key_value,
                    source_file=file.source_file,
                    scanner_format=scanner_format,
                    tool_names=tool_names,
                    imported_count=len(parsed),
                    rejected_count=0,
                    failure_summaries=[],
                )
                persisted = []
                for index, item in enumerate(parsed, start=1):
                    source_ref = source_refs[item.field_prefix]
                    existing = existing_by_source_ref.get(source_ref)
                    if existing is not None:
                        persisted.append(
                            refresh_external_scanner_evidence(
                                existing,
                                import_id=scanner_import.id,
                                project_key=project.project_key,
                                workspace_id=workspace_id_value,
                                workspace_key=workspace_key_value,
                                source_file=file.source_file,
                                tool_name=item.tool_name,
                                rule_id=item.rule_id,
                                rule_name=item.rule_name,
                                severity=item.severity,
                                level=item.level,
                                message=item.message,
                                location=item.location,
                                artifact_uri=item.artifact_uri,
                                region=item.region,
                                properties=item.properties,
                            )
                        )
                        continue
                    evidence_id = f"scanner-{scanner_import.id}-{index}"
                    persisted.append(
                        create_external_scanner_evidence(
                            session,
                            import_id=scanner_import.id,
                            evidence_id=evidence_id,
                            project_id=project.id,
                            project_key=project.project_key,
                            workspace_id=workspace_id_value,
                            workspace_key=workspace_key_value,
                            source_file=file.source_file,
                            source_ref=source_ref,
                            tool_name=item.tool_name,
                            rule_id=item.rule_id,
                            rule_name=item.rule_name,
                            severity=item.severity,
                            level=item.level,
                            message=item.message,
                            location=item.location,
                            artifact_uri=item.artifact_uri,
                            region=item.region,
                            properties=item.properties,
                        )
                    )
                session.flush()
                evidence = [_serialize_evidence(record) for record in persisted]
                import_id = scanner_import.id
    except IntegrityError as exc:
        if _is_duplicate_source_ref_integrity_error(exc):
            raise _duplicate_source_ref_error(file, format_label=format_label) from exc
        if _is_scope_integrity_error(exc):
            raise _scope_changed_error(file, format_label=format_label) from exc
        raise

    return ScannerImportResult(
        import_id=import_id,
        project_id=project.id,
        project_key=project.project_key,
        workspace_id=workspace_id_value,
        workspace_key=workspace_key_value,
        source_file=file.source_file,
        tool_names=tool_names,
        imported_count=len(evidence),
        rejected_count=0,
        evidence=evidence,
    )


def list_external_scanner_evidence(
    *,
    project_id: int,
    workspace_id: int | None = None,
) -> list[ExternalScannerEvidenceRecord]:
    """List external scanner evidence for a project or workspace scope."""
    with SessionLocal() as session:
        return [
            _serialize_evidence(record)
            for record in list_external_scanner_evidence_records(
                session,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        ]


def scanner_import_failure_summaries(
    errors: list[ScannerImportFieldError],
) -> list[dict[str, str]]:
    """Return API-safe scanner import validation failures."""
    return [error.model_dump(mode="json") for error in errors]


def _validate_sarif_file_envelope(file: ScannerImportFile) -> ScannerImportFile:
    try:
        payload_size = len(file.content.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ScannerImportValidationError(
            [
                ScannerImportFieldError(
                    source_file=file.source_file,
                    field="content",
                    message=(
                        "SARIF content contains invalid Unicode surrogate characters."
                    ),
                    correction_path=(
                        "Export SARIF as valid UTF-8 JSON without lone surrogate "
                        "escapes."
                    ),
                )
            ]
        ) from exc
    if payload_size > SARIF_IMPORT_MAX_CONTENT_BYTES:
        raise ScannerImportPayloadTooLarge(limit_bytes=SARIF_IMPORT_MAX_CONTENT_BYTES)

    errors: list[ScannerImportFieldError] = []
    source_file = normalize_artifact_name(file.source_file)
    suffix = Path(source_file).suffix.lower()
    if artifact_name_is_ownership_untrusted(source_file):
        _add_error(
            errors,
            file,
            field="source_file",
            message="SARIF source_file must be a safe relative file name.",
            correction_path="Submit a relative SARIF file name without traversal or reserved prefixes.",
        )
    if is_sensitive_file(source_file):
        _add_error(
            errors,
            file,
            field="source_file",
            message="SARIF source_file looks sensitive and cannot be imported.",
            correction_path="Export scanner findings to a non-sensitive .sarif or .json file.",
        )
    if suffix not in SUPPORTED_SARIF_SOURCE_EXTENSIONS:
        _add_error(
            errors,
            file,
            field="source_file",
            message="SARIF source_file must use a .sarif or .json extension.",
            correction_path="Export SARIF as a .sarif or .json file and retry the import.",
        )
    if len(source_file) > SARIF_SOURCE_FILE_MAX_LENGTH:
        _add_error(
            errors,
            file,
            field="source_file",
            message=(
                f"SARIF source_file must be {SARIF_SOURCE_FILE_MAX_LENGTH} "
                "characters or fewer."
            ),
            correction_path="Use a shorter SARIF source file name.",
        )
    if errors:
        raise ScannerImportValidationError(errors)
    if source_file == file.source_file:
        return file
    return ScannerImportFile(source_file=source_file, content=file.content)


def _validate_semgrep_file_envelope(file: ScannerImportFile) -> ScannerImportFile:
    try:
        payload_size = len(file.content.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ScannerImportValidationError(
            [
                ScannerImportFieldError(
                    source_file=file.source_file,
                    field="content",
                    message=(
                        "Semgrep JSON content contains invalid Unicode surrogate "
                        "characters."
                    ),
                    correction_path=(
                        "Export Semgrep JSON as valid UTF-8 JSON without lone "
                        "surrogate escapes."
                    ),
                )
            ]
        ) from exc
    if payload_size > SARIF_IMPORT_MAX_CONTENT_BYTES:
        raise ScannerImportPayloadTooLarge(
            limit_bytes=SARIF_IMPORT_MAX_CONTENT_BYTES,
            scope="Semgrep JSON content",
        )

    errors: list[ScannerImportFieldError] = []
    decoded_source_file, source_file_decode_settled = (
        _decode_percent_encoded_to_fixed_point(file.source_file)
    )
    source_file = normalize_artifact_name(decoded_source_file)
    suffix = Path(source_file).suffix.lower()
    if not source_file_decode_settled:
        _add_error(
            errors,
            file,
            field="source_file",
            message="Semgrep JSON source_file is too deeply percent-encoded.",
            correction_path="Submit a Semgrep JSON file name with fewer percent-encoding layers.",
        )
    if _contains_control_characters(decoded_source_file):
        _add_error(
            errors,
            file,
            field="source_file",
            message="Semgrep JSON source_file must not include control characters.",
            correction_path="Submit a printable Semgrep JSON file name.",
        )
    if artifact_name_is_ownership_untrusted(source_file):
        _add_error(
            errors,
            file,
            field="source_file",
            message="Semgrep JSON source_file must be a safe relative file name.",
            correction_path="Submit a relative Semgrep JSON file name without traversal or reserved prefixes.",
        )
    if is_sensitive_file(source_file):
        _add_error(
            errors,
            file,
            field="source_file",
            message="Semgrep JSON source_file looks sensitive and cannot be imported.",
            correction_path="Export scanner findings to a non-sensitive .json file.",
        )
    if suffix not in SUPPORTED_SEMGREP_SOURCE_EXTENSIONS:
        _add_error(
            errors,
            file,
            field="source_file",
            message="Semgrep JSON source_file must use a .json extension.",
            correction_path="Export Semgrep findings as a .json file and retry the import.",
        )
    if len(source_file) > SARIF_SOURCE_FILE_MAX_LENGTH:
        _add_error(
            errors,
            file,
            field="source_file",
            message=(
                f"Semgrep JSON source_file must be {SARIF_SOURCE_FILE_MAX_LENGTH} "
                "characters or fewer."
            ),
            correction_path="Use a shorter Semgrep JSON source file name.",
        )
    if errors:
        raise ScannerImportValidationError(errors)
    if source_file == file.source_file:
        return file
    return ScannerImportFile(source_file=source_file, content=file.content)


def _parse_sarif(file: ScannerImportFile) -> list[_ParsedSarifEvidence]:
    errors: list[ScannerImportFieldError] = []
    try:
        payload = json.loads(file.content)
    except json.JSONDecodeError as exc:
        raise ScannerImportValidationError(
            [
                ScannerImportFieldError(
                    source_file=file.source_file,
                    field="content",
                    message=f"Content is not valid JSON: {exc.msg}.",
                    correction_path="Export SARIF as JSON and retry the import.",
                )
            ]
        ) from exc

    if not isinstance(payload, dict):
        _add_error(
            errors,
            file,
            field="content",
            message="SARIF content must be a JSON object.",
            correction_path="Use a SARIF 2.1.0 JSON object with a runs array.",
        )
        raise ScannerImportValidationError(errors)
    _add_surrogate_string_errors(errors, file, payload, path="", format_label="SARIF")
    version = str(payload.get("version") or "").strip()
    if version != "2.1.0":
        _add_error(
            errors,
            file,
            field="version",
            message="SARIF version 2.1.0 is required.",
            correction_path="Export SARIF using version 2.1.0.",
        )
    runs = payload.get("runs")
    if not isinstance(runs, list):
        _add_error(
            errors,
            file,
            field="runs",
            message="SARIF runs must be an array.",
            correction_path="Use a SARIF 2.1.0 runs array.",
        )
        raise ScannerImportValidationError(errors)

    parsed: list[_ParsedSarifEvidence] = []
    for run_index, run in enumerate(runs):
        if not isinstance(run, dict):
            _add_error(
                errors,
                file,
                field=f"runs[{run_index}]",
                message="Each SARIF run must be an object.",
                correction_path="Export SARIF with object entries in runs.",
            )
            continue
        tool_name = _tool_name(
            run,
            file=file,
            field=f"runs[{run_index}].tool.driver.name",
            errors=errors,
        )
        if not tool_name:
            _add_error(
                errors,
                file,
                field=f"runs[{run_index}].tool.driver.name",
                message="SARIF run is missing the scanner tool name.",
                correction_path="Add tool.driver.name to each SARIF run.",
            )
        rules_by_id = _rules_by_id(
            run,
            file=file,
            run_index=run_index,
            errors=errors,
        )
        results = run.get("results", [])
        if not isinstance(results, list):
            _add_error(
                errors,
                file,
                field=f"runs[{run_index}].results",
                message="SARIF run results must be an array.",
                correction_path="Use a SARIF results array for each run.",
            )
            continue
        for result_index, result in enumerate(results):
            parsed_item = _parse_result(
                file=file,
                run_index=run_index,
                result_index=result_index,
                result=result,
                tool_name=tool_name,
                rules_by_id=rules_by_id,
                errors=errors,
            )
            if parsed_item is not None:
                parsed.append(parsed_item)
                if len(parsed) > SARIF_IMPORT_MAX_RESULTS:
                    _add_error(
                        errors,
                        file,
                        field=f"runs[{run_index}].results",
                        message=(
                            "SARIF imports support at most "
                            f"{SARIF_IMPORT_MAX_RESULTS} results."
                        ),
                        correction_path=(
                            "Split scanner output into smaller SARIF files or "
                            "filter findings before import."
                        ),
                    )
                    raise ScannerImportValidationError(errors)

    if errors:
        raise ScannerImportValidationError(errors)
    return parsed


def _parse_semgrep_json(file: ScannerImportFile) -> list[_ParsedSarifEvidence]:
    errors: list[ScannerImportFieldError] = []
    try:
        payload = json.loads(file.content)
    except json.JSONDecodeError as exc:
        raise ScannerImportValidationError(
            [
                ScannerImportFieldError(
                    source_file=file.source_file,
                    field="content",
                    message=f"Content is not valid JSON: {exc.msg}.",
                    correction_path="Export Semgrep findings as JSON and retry the import.",
                )
            ]
        ) from exc

    if not isinstance(payload, dict):
        _add_error(
            errors,
            file,
            field="content",
            message="Semgrep JSON content must be a JSON object.",
            correction_path="Use a Semgrep JSON object with a results array.",
        )
        raise ScannerImportValidationError(errors)
    _add_surrogate_string_errors(
        errors,
        file,
        payload,
        path="",
        format_label="Semgrep JSON",
    )
    results = payload.get("results")
    if not isinstance(results, list):
        _add_error(
            errors,
            file,
            field="results",
            message="Semgrep JSON results must be an array.",
            correction_path="Run Semgrep with JSON output and include the results array.",
        )
        raise ScannerImportValidationError(errors)

    scan_errors = payload.get("errors")
    if "errors" in payload and not isinstance(scan_errors, list):
        _add_error(
            errors,
            file,
            field="errors",
            message="Semgrep JSON errors must be an array.",
            correction_path="Export Semgrep JSON with a top-level errors array.",
        )
        raise ScannerImportValidationError(errors)
    if isinstance(scan_errors, list) and scan_errors:
        _add_error(
            errors,
            file,
            field="errors",
            message=(
                "Semgrep JSON reported scan errors and cannot be imported as "
                "complete evidence."
            ),
            correction_path=(
                "Rerun Semgrep until the top-level errors array is empty, "
                "then retry the import."
            ),
        )
        raise ScannerImportValidationError(errors)

    if len(results) > SEMGREP_IMPORT_MAX_RESULTS:
        _add_error(
            errors,
            file,
            field="results",
            message=(
                "Semgrep JSON imports support at most "
                f"{SEMGREP_IMPORT_MAX_RESULTS} results."
            ),
            correction_path=(
                "Split scanner output into smaller files or filter findings before "
                "import."
            ),
        )
        raise ScannerImportValidationError(errors)

    parsed: list[_ParsedSarifEvidence] = []
    for result_index, result in enumerate(results):
        parsed_item = _parse_semgrep_result(
            file=file,
            result_index=result_index,
            result=result,
            errors=errors,
        )
        if parsed_item is not None:
            parsed.append(parsed_item)

    if errors:
        raise ScannerImportValidationError(errors)
    return parsed


def _parse_semgrep_result(
    *,
    file: ScannerImportFile,
    result_index: int,
    result: object,
    errors: list[ScannerImportFieldError],
) -> _ParsedSarifEvidence | None:
    field_prefix = f"results[{result_index}]"
    if not isinstance(result, dict):
        _add_error(
            errors,
            file,
            field=field_prefix,
            message="Each Semgrep result must be an object.",
            correction_path="Export Semgrep JSON with object entries in results.",
        )
        return None

    rule_id = _semgrep_string_value(
        result,
        "check_id",
        file=file,
        field=f"{field_prefix}.check_id",
        errors=errors,
        required=True,
        reject_controls=True,
    )
    if rule_id == "":
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.check_id",
            message="Semgrep result is missing check_id.",
            correction_path="Export Semgrep JSON with check_id on every result.",
        )
    artifact_uri = _semgrep_artifact_uri(
        result,
        file=file,
        field=f"{field_prefix}.path",
        errors=errors,
    )
    region = _semgrep_region(
        result,
        file=file,
        field_prefix=field_prefix,
        errors=errors,
    )
    extra = result.get("extra") if isinstance(result.get("extra"), dict) else {}
    if not isinstance(result.get("extra"), dict):
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.extra",
            message="Semgrep result is missing extra metadata.",
            correction_path="Export Semgrep JSON with an extra object on every result.",
        )
    invalid_metadata = False
    if "metadata" in extra and not isinstance(extra.get("metadata"), dict):
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.extra.metadata",
            message="Semgrep JSON extra.metadata must be an object.",
            correction_path=(
                "Export Semgrep JSON with extra.metadata encoded as an object."
            ),
        )
        invalid_metadata = True
    message = _semgrep_string_value(
        extra,
        "message",
        file=file,
        field=f"{field_prefix}.extra.message",
        errors=errors,
        required=True,
        reject_controls=True,
    )
    if message == "":
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.extra.message",
            message="Semgrep result is missing extra.message.",
            correction_path="Export Semgrep JSON with extra.message on every result.",
        )
    level = _semgrep_level(
        extra,
        file=file,
        field=f"{field_prefix}.extra.severity",
        errors=errors,
    )
    if (
        not rule_id
        or not artifact_uri
        or not region
        or not message
        or not level
        or invalid_metadata
    ):
        return None

    location = artifact_uri
    if region.get("startLine") is not None:
        location = f"{location}:{region['startLine']}"
        if region.get("startColumn") is not None:
            location = f"{location}:{region['startColumn']}"
    fingerprint = _semgrep_fingerprint(
        result,
        extra,
        file=file,
        field_prefix=field_prefix,
        errors=errors,
    )
    properties = _semgrep_properties(
        extra,
        fingerprint=fingerprint or None,
    )
    identity_fingerprint = (
        fingerprint if _semgrep_fingerprint_is_report_safe(fingerprint) else ""
    )
    identity: dict[str, Any] = {
        "tool_name": "Semgrep",
        "rule_id": rule_id,
        "artifact_uri": artifact_uri,
        "region": _source_identity_region(region),
    }
    if identity_fingerprint:
        identity["fingerprint"] = identity_fingerprint
    else:
        identity["message_text"] = message
    return _ParsedSarifEvidence(
        field_prefix=field_prefix,
        source_format="semgrep",
        tool_name="Semgrep",
        rule_id=rule_id,
        rule_name=rule_id,
        severity=SEMGREP_SEVERITY_BY_LEVEL[level],
        level=level,
        message=message,
        location=location,
        artifact_uri=artifact_uri,
        region=region,
        identity=identity,
        properties=properties,
    )


def _semgrep_fingerprint(
    result: dict[str, Any],
    extra: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> str:
    extra_fingerprint = _semgrep_string_value(
        extra,
        "fingerprint",
        file=file,
        field=f"{field_prefix}.extra.fingerprint",
        errors=errors,
        required=False,
    )
    top_level_fingerprint = _semgrep_string_value(
        result,
        "fingerprint",
        file=file,
        field=f"{field_prefix}.fingerprint",
        errors=errors,
        required=False,
    )
    for fingerprint in (extra_fingerprint, top_level_fingerprint):
        if _semgrep_fingerprint_is_report_safe(fingerprint):
            return fingerprint
    return extra_fingerprint or top_level_fingerprint or ""


def _semgrep_string_value(
    owner: dict[str, Any],
    key: str,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
    required: bool,
    reject_controls: bool = False,
) -> str | None:
    value = owner.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        _add_error(
            errors,
            file,
            field=field,
            message=f"Semgrep JSON {field} must be a string.",
            correction_path=f"Export Semgrep JSON with {field} encoded as a string.",
        )
        return None
    text = value.strip()
    if reject_controls and _contains_control_characters(text):
        _add_error(
            errors,
            file,
            field=field,
            message=f"Semgrep JSON {field} must not include control characters.",
            correction_path=f"Export Semgrep JSON with printable {field} text.",
        )
        return None
    if required or text:
        return text
    return ""


def _semgrep_artifact_uri(
    result: dict[str, Any],
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str | None:
    artifact_uri = _semgrep_string_value(
        result,
        "path",
        file=file,
        field=field,
        errors=errors,
        required=True,
    )
    if artifact_uri is None:
        return None
    if not artifact_uri:
        _add_error(
            errors,
            file,
            field=field,
            message="Semgrep result is missing path.",
            correction_path="Export Semgrep JSON with a repository-relative path.",
        )
        return None
    return _safe_semgrep_artifact_uri(
        artifact_uri,
        file=file,
        field=field,
        errors=errors,
    )


def _safe_semgrep_artifact_uri(
    artifact_uri: str,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str | None:
    parsed_uri = urlsplit(artifact_uri)
    decoded_uri, uri_decode_settled = _decode_percent_encoded_to_fixed_point(
        artifact_uri
    )
    parsed_decoded_uri = urlsplit(decoded_uri)
    if not uri_decode_settled:
        _add_error(
            errors,
            file,
            field=field,
            message="Semgrep path is too deeply percent-encoded.",
            correction_path="Export Semgrep JSON with fewer percent-encoding layers in paths.",
        )
        return None
    if _contains_control_characters(decoded_uri):
        _add_error(
            errors,
            file,
            field=field,
            message="Semgrep path must not include control characters.",
            correction_path="Export Semgrep JSON with printable repository-relative paths.",
        )
        return None
    if parsed_uri.scheme or parsed_decoded_uri.scheme:
        _add_error(
            errors,
            file,
            field=field,
            message=(
                "Semgrep path must be repository-relative and must not include "
                "a URI scheme."
            ),
            correction_path="Export Semgrep JSON with repository-relative paths only.",
        )
        return None
    if (
        parsed_uri.query
        or parsed_uri.fragment
        or parsed_decoded_uri.query
        or parsed_decoded_uri.fragment
    ):
        _add_error(
            errors,
            file,
            field=field,
            message="Semgrep path must not include query or fragment components.",
            correction_path="Export Semgrep JSON with repository-relative paths only.",
        )
        return None
    normalized_uri = trusted_relative_artifact_path(decoded_uri)
    if normalized_uri is None:
        _add_error(
            errors,
            file,
            field=field,
            message="Semgrep path must be a concrete repository-relative path.",
            correction_path="Export Semgrep JSON with a concrete repository-relative path.",
        )
        return None
    if artifact_name_is_ownership_untrusted(normalized_uri):
        _add_error(
            errors,
            file,
            field=field,
            message="Semgrep path must be a safe relative artifact path.",
            correction_path="Export Semgrep JSON with repository-relative paths only.",
        )
        return None
    if is_sensitive_file(normalized_uri):
        _add_error(
            errors,
            file,
            field=field,
            message="Semgrep path looks sensitive and cannot be imported.",
            correction_path="Remove sensitive file paths from Semgrep output.",
        )
        return None
    return normalized_uri


def _semgrep_region(
    result: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> dict[str, Any]:
    start_object = result.get("start")
    if start_object is not None and not isinstance(start_object, dict):
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.start",
            message="Semgrep start coordinates must be an object.",
            correction_path="Export Semgrep JSON with start.line/start.col as object fields.",
        )
        return {}
    start = start_object if isinstance(start_object, dict) else {}
    end_object = result.get("end")
    if end_object is not None and not isinstance(end_object, dict):
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.end",
            message="Semgrep end coordinates must be an object when provided.",
            correction_path="Export Semgrep JSON with end.line/end.col as object fields.",
        )
        return {}
    end = end_object if isinstance(end_object, dict) else {}
    if not start:
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.start",
            message="Semgrep result is missing start coordinates.",
            correction_path="Export Semgrep JSON with start.line on every result.",
        )
        return {}
    region: dict[str, Any] = {
        "startLine": start.get("line"),
        "startColumn": start.get("col"),
        "endLine": end.get("line"),
        "endColumn": end.get("col"),
    }
    region = {key: value for key, value in region.items() if value is not None}
    invalid_region = False
    for coordinate_name, field_name in (
        ("startLine", "start.line"),
        ("startColumn", "start.col"),
        ("endLine", "end.line"),
        ("endColumn", "end.col"),
    ):
        if not _invalid_region_coordinate(region.get(coordinate_name)):
            continue
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.{field_name}",
            message=f"Semgrep {field_name} must be a positive integer.",
            correction_path=(
                f"Export Semgrep JSON with numeric positive integer {field_name} "
                "values."
            ),
        )
        invalid_region = True
    if invalid_region:
        return {}
    if "startLine" not in region:
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.start.line",
            message="Semgrep start.line is required.",
            correction_path="Export Semgrep JSON with start.line on every result.",
        )
        return {}
    if _invalid_region_bounds(region):
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.start",
            message="Semgrep region bounds are inconsistent.",
            correction_path="Export Semgrep JSON with coherent start/end coordinates.",
        )
        return {}
    return region


def _semgrep_level(
    extra: dict[str, Any],
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str | None:
    level_text = _semgrep_string_value(
        extra,
        "severity",
        file=file,
        field=field,
        errors=errors,
        required=False,
        reject_controls=True,
    )
    if level_text is None:
        return None
    level = level_text.upper()
    if not level:
        if (
            "severity" not in extra
            or extra.get("severity") is None
            or isinstance(extra.get("severity"), str)
        ):
            _add_error(
                errors,
                file,
                field=field,
                message="Semgrep result is missing extra.severity.",
                correction_path=(
                    "Export Semgrep JSON with extra.severity on every result."
                ),
            )
        return None
    if level in SEMGREP_SEVERITY_BY_LEVEL:
        return level
    _add_error(
        errors,
        file,
        field=field,
        message="Semgrep severity must be one of ERROR, WARNING, or INFO.",
        correction_path="Export Semgrep JSON with a supported extra.severity value.",
    )
    return None


def _semgrep_properties(
    extra: dict[str, Any],
    *,
    fingerprint: str | None,
) -> dict[str, Any]:
    semgrep: dict[str, Any] = {}
    metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
    report_metadata = {}
    for key, value in sorted(metadata.items(), key=lambda item: str(item[0])):
        if key not in SEMGREP_METADATA_REPORT_FIELDS:
            continue
        report_value = _semgrep_report_metadata_value(value)
        if report_value is not None:
            report_metadata[str(key)] = report_value
    if report_metadata:
        semgrep["metadata"] = report_metadata
    if _semgrep_fingerprint_is_report_safe(fingerprint):
        semgrep["fingerprint"] = fingerprint
    engine_kind = extra.get("engine_kind")
    if isinstance(engine_kind, str):
        engine_kind_text = engine_kind.strip()
        if (
            engine_kind_text
            and len(engine_kind_text) <= SEMGREP_ENGINE_KIND_MAX_LENGTH
            and _semgrep_metadata_string_is_report_safe(engine_kind_text)
        ):
            semgrep["engine_kind"] = engine_kind_text
    return {"semgrep": semgrep} if semgrep else {}


def _semgrep_report_metadata_value(value: object) -> object | None:
    if isinstance(value, str):
        text = value.strip()
        if not text or len(text) > SEMGREP_METADATA_STRING_MAX_LENGTH:
            return None
        if not _semgrep_metadata_string_is_report_safe(text):
            return None
        return text
    if type(value) in {bool, int, float}:
        if isinstance(value, bool) or math.isfinite(value):
            return value
        return None
    if isinstance(value, list):
        if not value or len(value) > SEMGREP_METADATA_LIST_MAX_ITEMS:
            return None
        normalized_items = []
        for item in value:
            if isinstance(item, (dict, list)):
                return None
            report_item = _semgrep_report_metadata_value(item)
            if report_item is None:
                return None
            normalized_items.append(report_item)
        return normalized_items
    return None


def _semgrep_metadata_string_is_report_safe(text: str) -> bool:
    decoded_value, decode_settled = _decode_percent_encoded_to_fixed_point(text)
    if not decode_settled:
        return False
    decoded = decoded_value.strip()
    if _contains_control_characters(decoded):
        return False
    parsed_values = (urlsplit(text), urlsplit(decoded))
    if any(
        parsed.scheme.lower() in SEMGREP_METADATA_URL_SCHEMES
        or parsed.scheme.isalpha()
        or (parsed.scheme and parsed.netloc)
        for parsed in parsed_values
    ):
        return False
    if decoded.startswith(("/", "\\", "~/", "~\\", "../", "..\\", "./", ".\\")):
        return False
    if SEMGREP_METADATA_WINDOWS_PATH_RE.match(decoded):
        return False
    if "\\" in decoded:
        return False
    if "/" in decoded and (
        Path(decoded).suffix or trusted_relative_artifact_path(decoded) is not None
    ):
        return False
    return True


def _semgrep_fingerprint_is_report_safe(fingerprint: str | None) -> bool:
    return bool(
        fingerprint
        and len(fingerprint) <= SEMGREP_FINGERPRINT_MAX_LENGTH
        and _semgrep_metadata_string_is_report_safe(fingerprint)
    )


def _parse_result(
    *,
    file: ScannerImportFile,
    run_index: int,
    result_index: int,
    result: object,
    tool_name: str,
    rules_by_id: dict[str, _SarifRuleMetadata],
    errors: list[ScannerImportFieldError],
) -> _ParsedSarifEvidence | None:
    field_prefix = f"runs[{run_index}].results[{result_index}]"
    if not isinstance(result, dict):
        _add_error(
            errors,
            file,
            field=field_prefix,
            message="Each SARIF result must be an object.",
            correction_path="Export SARIF with object entries in results.",
        )
        return None

    rule_id = _string_value(
        result,
        "ruleId",
        file=file,
        field=f"{field_prefix}.ruleId",
        errors=errors,
        required=True,
    )
    if not rule_id:
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.ruleId",
            message="SARIF result is missing ruleId.",
            correction_path="Add ruleId to each SARIF result.",
        )
    rule_metadata = rules_by_id.get(rule_id)
    message = _message_text(
        result,
        rule_metadata,
        file=file,
        field_prefix=field_prefix,
        errors=errors,
    )
    if not message:
        message_object = (
            result.get("message") if isinstance(result.get("message"), dict) else {}
        )
        message_id = _message_id(
            message_object,
            file=file,
            field=f"{field_prefix}.message.id",
            errors=errors,
        )
        if message_id:
            if (
                rule_metadata is not None
                and message_id in rule_metadata.message_strings
            ):
                return None
            _add_error(
                errors,
                file,
                field=f"{field_prefix}.message.id",
                message=(
                    "SARIF message.id must reference a rule.messageStrings "
                    "entry when message text is not provided."
                ),
                correction_path=(
                    "Add message.text or define the referenced rule.messageStrings "
                    "entry."
                ),
            )
            return None
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.message.text",
            message="SARIF result is missing message text.",
            correction_path="Add message.text to each SARIF result.",
        )
    locations = _locations(
        result,
        file=file,
        field_prefix=field_prefix,
        errors=errors,
    )
    if not locations:
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.locations[0].physicalLocation",
            message="SARIF result is missing an artifact location.",
            correction_path=("Add locations[0].physicalLocation.artifactLocation.uri."),
        )
    if not tool_name or not rule_id or not message or not locations:
        return None

    properties: dict[str, Any] = {}
    if len(locations) > 1:
        properties["deploywhisper_import"] = {
            "additional_locations": locations[1:],
        }
    level = _sarif_level(
        result,
        "level",
        file=file,
        field=f"{field_prefix}.level",
        errors=errors,
    )
    location = locations[0]
    identity = _source_identity(
        item_tool_name=tool_name,
        rule_id=rule_id,
        message=message,
        location=location,
        result=result,
        file=file,
        field_prefix=field_prefix,
        errors=errors,
    )
    return _ParsedSarifEvidence(
        field_prefix=field_prefix,
        tool_name=tool_name,
        rule_id=rule_id,
        rule_name=(rule_metadata or _SarifRuleMetadata()).name,
        severity=_severity(
            result,
            level,
            rule_metadata,
            file=file,
            field_prefix=field_prefix,
            errors=errors,
        ),
        level=level,
        message=message,
        location=location["location"],
        artifact_uri=location["artifact_uri"],
        region=location["region"],
        identity=identity,
        properties=properties,
    )


def _tool_name(
    run: dict[str, Any],
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str:
    tool = run.get("tool") if isinstance(run.get("tool"), dict) else {}
    driver = tool.get("driver") if isinstance(tool.get("driver"), dict) else {}
    return _string_value(
        driver,
        "name",
        file=file,
        field=field,
        errors=errors,
        required=True,
    )


def _rules_by_id(
    run: dict[str, Any],
    *,
    file: ScannerImportFile,
    run_index: int,
    errors: list[ScannerImportFieldError],
) -> dict[str, _SarifRuleMetadata]:
    tool = run.get("tool") if isinstance(run.get("tool"), dict) else {}
    driver = tool.get("driver") if isinstance(tool.get("driver"), dict) else {}
    rules_by_id: dict[str, _SarifRuleMetadata] = {}
    for rule, field_prefix in _rule_entries(
        driver,
        field_prefix=f"runs[{run_index}].tool.driver",
    ):
        if not isinstance(rule, dict):
            continue
        _add_rule_metadata(
            rules_by_id,
            rule,
            file=file,
            field_prefix=field_prefix,
            errors=errors,
        )
    extensions = (
        tool.get("extensions") if isinstance(tool.get("extensions"), list) else []
    )
    for extension_index, extension in enumerate(extensions):
        if not isinstance(extension, dict):
            continue
        for rule, field_prefix in _rule_entries(
            extension,
            field_prefix=(f"runs[{run_index}].tool.extensions[{extension_index}]"),
        ):
            if not isinstance(rule, dict):
                continue
            _add_rule_metadata(
                rules_by_id,
                rule,
                file=file,
                field_prefix=field_prefix,
                errors=errors,
            )
    return rules_by_id


def _add_rule_metadata(
    rules_by_id: dict[str, _SarifRuleMetadata],
    rule: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> None:
    rule_id = _string_value(
        rule,
        "id",
        file=file,
        field=f"{field_prefix}.id",
        errors=errors,
        required=False,
    )
    if not rule_id:
        return
    if rule_id in rules_by_id:
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.id",
            message=(
                "SARIF rule id duplicates another driver or extension rule in this run."
            ),
            correction_path=(
                "Export SARIF with unique rule IDs per run or disambiguate "
                "extension rules before import."
            ),
        )
        return
    rules_by_id[rule_id] = _rule_metadata(
        rule,
        fallback_name=rule_id,
        file=file,
        field_prefix=field_prefix,
        errors=errors,
    )


def _rule_entries(
    component: dict[str, Any],
    *,
    field_prefix: str,
) -> list[tuple[object, str]]:
    rules = component.get("rules") if isinstance(component.get("rules"), list) else []
    return [
        (rule, f"{field_prefix}.rules[{rule_index}]")
        for rule_index, rule in enumerate(rules)
    ]


def _rule_metadata(
    rule: dict[str, Any],
    *,
    fallback_name: str,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> _SarifRuleMetadata:
    default_configuration = (
        rule.get("defaultConfiguration")
        if isinstance(rule.get("defaultConfiguration"), dict)
        else {}
    )
    rule_properties = (
        rule.get("properties") if isinstance(rule.get("properties"), dict) else {}
    )
    default_properties = (
        default_configuration.get("properties")
        if isinstance(default_configuration.get("properties"), dict)
        else {}
    )
    level = _sarif_level(
        default_configuration,
        "level",
        file=file,
        field=f"{field_prefix}.defaultConfiguration.level",
        errors=errors,
    )
    return _SarifRuleMetadata(
        name=(
            _rule_name(
                rule,
                file=file,
                field_prefix=field_prefix,
                errors=errors,
            )
            or fallback_name
        ),
        severity=(
            _severity_from_properties(
                rule_properties,
                file=file,
                field_prefix=f"{field_prefix}.properties",
                errors=errors,
            )
            or _severity_from_properties(
                default_properties,
                file=file,
                field_prefix=f"{field_prefix}.defaultConfiguration.properties",
                errors=errors,
            )
        ),
        level=level,
        message_strings=_message_strings(
            rule,
            file=file,
            field_prefix=field_prefix,
            errors=errors,
        ),
    )


def _rule_name(
    rule: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> str | None:
    for field_name in ("shortDescription", "fullDescription"):
        description = rule.get(field_name)
        if isinstance(description, dict):
            text = _string_value(
                description,
                "text",
                file=file,
                field=f"{field_prefix}.{field_name}.text",
                errors=errors,
                required=False,
            )
            if text:
                return text
    name = _string_value(
        rule,
        "name",
        file=file,
        field=f"{field_prefix}.name",
        errors=errors,
        required=False,
    )
    return name or None


def _message_strings(
    rule: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> dict[str, str]:
    message_strings = rule.get("messageStrings")
    if not isinstance(message_strings, dict):
        return {}
    resolved: dict[str, str] = {}
    for message_id, message_value in message_strings.items():
        if not isinstance(message_value, dict):
            continue
        text = _multiformat_rule_message_text(
            message_value,
            file=file,
            field_prefix=f"{field_prefix}.messageStrings.{message_id}",
            errors=errors,
        )
        if text:
            resolved[str(message_id)] = text
    return resolved


def _message_text(
    result: dict[str, Any],
    rule_metadata: _SarifRuleMetadata | None,
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> str:
    message = result.get("message") if isinstance(result.get("message"), dict) else {}
    text = _multiformat_message_text(
        message,
        file=file,
        field_prefix=field_prefix,
        errors=errors,
    )
    if text:
        return text
    message_id = _message_id(
        message,
        file=file,
        field=f"{field_prefix}.message.id",
        errors=errors,
    )
    if not message_id:
        return ""
    message_template = (
        rule_metadata.message_strings.get(message_id)
        if rule_metadata is not None
        else None
    )
    if message_template:
        arguments = message.get("arguments")
        if arguments is None:
            arguments = []
        elif not isinstance(arguments, list):
            _add_error(
                errors,
                file,
                field=f"{field_prefix}.message.arguments",
                message="SARIF message.arguments must be an array.",
                correction_path=(
                    "Export SARIF with message.arguments as an array when "
                    "referencing rule.messageStrings."
                ),
            )
            return ""
        if not _message_arguments_are_strings(
            arguments,
            file=file,
            field_prefix=field_prefix,
            errors=errors,
        ):
            return ""
        return _format_message_string(
            message_template,
            arguments,
            file=file,
            field=f"{field_prefix}.message.arguments",
            errors=errors,
        )
    return ""


def _message_arguments_are_strings(
    arguments: list[Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> bool:
    valid = True
    for argument_index, argument in enumerate(arguments):
        if isinstance(argument, str):
            continue
        _add_error(
            errors,
            file,
            field=f"{field_prefix}.message.arguments[{argument_index}]",
            message="SARIF message.arguments entries must be strings.",
            correction_path="Export SARIF message.arguments as a string array.",
        )
        valid = False
    return valid


def _message_id(
    message: dict[str, Any],
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str:
    return _string_value(
        message,
        "id",
        file=file,
        field=field,
        errors=errors,
        required=False,
    )


def _multiformat_message_text(
    message: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> str:
    for field_name in ("text", "markdown"):
        text = _string_value(
            message,
            field_name,
            file=file,
            field=f"{field_prefix}.message.{field_name}",
            errors=errors,
            required=False,
        )
        if text:
            return text
    return ""


def _format_message_string(
    template: str,
    arguments: list[str],
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str:
    placeholder_pattern = re.compile(r"\{(\d+)\}")
    missing_placeholders = [
        placeholder
        for placeholder in placeholder_pattern.finditer(template)
        if int(placeholder.group(1)) >= len(arguments)
    ]
    if missing_placeholders:
        _add_error(
            errors,
            file,
            field=field,
            message="SARIF message template placeholders must be satisfied.",
            correction_path=(
                "Export SARIF with message.arguments for every referenced "
                "rule.messageStrings placeholder."
            ),
        )
        return ""
    return placeholder_pattern.sub(
        lambda match: arguments[int(match.group(1))],
        template,
    ).strip()


def _multiformat_rule_message_text(
    message: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> str:
    for field_name in ("text", "markdown"):
        text = _string_value(
            message,
            field_name,
            file=file,
            field=f"{field_prefix}.{field_name}",
            errors=errors,
            required=False,
        )
        if text:
            return text
    return ""


def _locations(
    result: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> list[dict[str, Any]]:
    locations = result.get("locations")
    if not isinstance(locations, list) or not locations:
        return []
    parsed: list[dict[str, Any]] = []
    for location_index, location in enumerate(locations):
        error_count = len(errors)
        parsed_location = _physical_location(
            location,
            file=file,
            field=f"{field_prefix}.locations[{location_index}].physicalLocation",
            errors=errors,
        )
        if parsed_location is not None:
            parsed.append(parsed_location)
        elif len(errors) == error_count:
            _add_error(
                errors,
                file,
                field=f"{field_prefix}.locations[{location_index}].physicalLocation",
                message="SARIF location is missing artifactLocation.uri.",
                correction_path=(
                    "Add physicalLocation.artifactLocation.uri to each SARIF "
                    "location entry or remove the malformed location."
                ),
            )
    return parsed


def _physical_location(
    location: object,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> dict[str, Any] | None:
    if not isinstance(location, dict):
        return None
    physical = location.get("physicalLocation")
    if not isinstance(physical, dict):
        return None
    artifact = physical.get("artifactLocation")
    if not isinstance(artifact, dict):
        return None
    uri_base_id = str(artifact.get("uriBaseId") or "").strip()
    if uri_base_id:
        _add_error(
            errors,
            file,
            field=f"{field}.artifactLocation.uriBaseId",
            message=(
                "SARIF artifactLocation.uriBaseId is not supported by this importer."
            ),
            correction_path=(
                "Export SARIF with repository-relative artifactLocation.uri values "
                "and no uriBaseId."
            ),
        )
        return None
    artifact_uri = _string_value(
        artifact,
        "uri",
        file=file,
        field=f"{field}.artifactLocation.uri",
        errors=errors,
        required=True,
    )
    if not artifact_uri:
        return None
    safe_artifact_uri = _safe_artifact_uri(
        artifact_uri,
        file=file,
        field=f"{field}.artifactLocation.uri",
        errors=errors,
    )
    if safe_artifact_uri is None:
        return None
    region = physical.get("region") if isinstance(physical.get("region"), dict) else {}
    line = region.get("startLine")
    column = region.get("startColumn")
    invalid_region = False
    for coordinate_name in ("startLine", "startColumn", "endLine", "endColumn"):
        if not _invalid_region_coordinate(region.get(coordinate_name)):
            continue
        _add_error(
            errors,
            file,
            field=f"{field}.region.{coordinate_name}",
            message=f"SARIF region.{coordinate_name} must be a positive integer.",
            correction_path=(
                f"Export SARIF with numeric positive integer {coordinate_name} values."
            ),
        )
        invalid_region = True
    if invalid_region:
        return None
    if _invalid_region_bounds(region):
        _add_error(
            errors,
            file,
            field=f"{field}.region",
            message="SARIF region bounds are inconsistent.",
            correction_path=(
                "Export SARIF with coherent start/end line and column values."
            ),
        )
        return None
    location = safe_artifact_uri
    if line is not None:
        location = f"{location}:{line}"
        if column is not None:
            location = f"{location}:{column}"
    return {
        "artifact_uri": safe_artifact_uri,
        "region": region,
        "location": location,
    }


def _invalid_region_coordinate(value: object) -> bool:
    if value is None:
        return False
    return type(value) is not int or value <= 0


def _invalid_region_bounds(region: dict[str, Any]) -> bool:
    start_line = region.get("startLine")
    start_column = region.get("startColumn")
    end_line = region.get("endLine")
    end_column = region.get("endColumn")
    if start_column is not None and start_line is None:
        return True
    if end_column is not None and end_line is None:
        return True
    if end_line is not None and start_line is None:
        return True
    if type(start_line) is int and type(end_line) is int and end_line < start_line:
        return True
    same_line = type(start_line) is int and start_line == end_line
    if (
        same_line
        and type(start_column) is int
        and type(end_column) is int
        and end_column < start_column
    ):
        return True
    return False


def _safe_artifact_uri(
    artifact_uri: str,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str | None:
    parsed_uri = urlsplit(artifact_uri)
    decoded_uri = unquote(artifact_uri)
    parsed_decoded_uri = urlsplit(decoded_uri)
    if parsed_uri.scheme or parsed_decoded_uri.scheme:
        _add_error(
            errors,
            file,
            field=field,
            message=(
                "SARIF artifactLocation.uri must be repository-relative and must "
                "not include a URI scheme."
            ),
            correction_path="Export SARIF with repository-relative path URIs only.",
        )
        return None
    if (
        parsed_uri.query
        or parsed_uri.fragment
        or parsed_decoded_uri.query
        or parsed_decoded_uri.fragment
    ):
        _add_error(
            errors,
            file,
            field=field,
            message=(
                "SARIF artifactLocation.uri must not include query or fragment "
                "components."
            ),
            correction_path="Export SARIF with repository-relative path URIs only.",
        )
        return None
    normalized_uri = trusted_relative_artifact_path(decoded_uri)
    if normalized_uri is None:
        _add_error(
            errors,
            file,
            field=field,
            message="SARIF artifactLocation.uri must be a concrete repository-relative path.",
            correction_path="Export SARIF with a concrete repository-relative file path.",
        )
        return None
    if artifact_name_is_ownership_untrusted(normalized_uri):
        _add_error(
            errors,
            file,
            field=field,
            message="SARIF artifactLocation.uri must be a safe relative artifact path.",
            correction_path=(
                "Export SARIF with repository-relative artifactLocation.uri values."
            ),
        )
        return None
    if is_sensitive_file(normalized_uri):
        _add_error(
            errors,
            file,
            field=field,
            message="SARIF artifactLocation.uri looks sensitive and cannot be imported.",
            correction_path="Remove sensitive file paths from SARIF artifact locations.",
        )
        return None
    return normalized_uri


def _severity(
    result: dict[str, Any],
    level: str | None,
    rule_metadata: _SarifRuleMetadata | None,
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> str:
    properties = (
        result.get("properties") if isinstance(result.get("properties"), dict) else {}
    )
    severity = _severity_from_properties(
        properties,
        file=file,
        field_prefix=f"{field_prefix}.properties",
        errors=errors,
    )
    if severity is not None:
        return severity
    if level in SEVERITY_BY_LEVEL:
        return SEVERITY_BY_LEVEL[level]
    if rule_metadata is not None:
        if rule_metadata.severity is not None:
            return rule_metadata.severity
        if rule_metadata.level in SEVERITY_BY_LEVEL:
            return SEVERITY_BY_LEVEL[rule_metadata.level or ""]
    return "low"


def _severity_from_properties(
    properties: dict[str, Any],
    *,
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> str | None:
    if "severity" in properties and properties.get("severity") is not None:
        severity_value = properties.get("severity")
        if not isinstance(severity_value, str):
            _add_error(
                errors,
                file,
                field=f"{field_prefix}.severity",
                message="SARIF severity must be a supported severity string.",
                correction_path=(
                    "Export SARIF severity as critical, high, medium, or low."
                ),
            )
            return None
        severity = severity_value.strip().lower()
        if severity in DIRECT_SEVERITIES:
            return severity
        if severity:
            _add_error(
                errors,
                file,
                field=f"{field_prefix}.severity",
                message="SARIF severity must be critical, high, medium, or low.",
                correction_path=(
                    "Export SARIF severity as critical, high, medium, or low."
                ),
            )
            return None
    if "security-severity" not in properties:
        return None
    security_severity = properties.get("security-severity")
    security_severity_text = (
        security_severity.strip().lower() if isinstance(security_severity, str) else ""
    )
    if security_severity_text in DIRECT_SEVERITIES:
        return security_severity_text
    numeric_security_severity = _numeric_security_severity(
        security_severity,
        file=file,
        field=f"{field_prefix}.security-severity",
        errors=errors,
    )
    if numeric_security_severity is not None:
        return _severity_from_security_score(numeric_security_severity)
    return None


def _numeric_security_severity(
    value: object,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> float | None:
    if value is None:
        return None
    if type(value) not in {int, float, str}:
        _add_error(
            errors,
            file,
            field=field,
            message=(
                "SARIF security-severity must be a number from 0 to 10 or a "
                "supported severity string."
            ),
            correction_path=(
                "Export SARIF security-severity as critical, high, medium, low, "
                "or a numeric score between 0 and 10."
            ),
        )
        return None
    try:
        score = float(str(value).strip())
    except (TypeError, ValueError):
        _add_error(
            errors,
            file,
            field=field,
            message=(
                "SARIF security-severity must be a number from 0 to 10 or a "
                "supported severity string."
            ),
            correction_path=(
                "Export SARIF security-severity as critical, high, medium, low, "
                "or a numeric score between 0 and 10."
            ),
        )
        return None
    if math.isfinite(score) and 0 <= score <= 10:
        return score
    _add_error(
        errors,
        file,
        field=field,
        message="SARIF security-severity numeric scores must be between 0 and 10.",
        correction_path="Export SARIF security-severity as a score between 0 and 10.",
    )
    return None


def _severity_from_security_score(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


def _sarif_level(
    owner: dict[str, Any],
    key: str,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> str | None:
    level = (
        _string_value(
            owner,
            key,
            file=file,
            field=field,
            errors=errors,
            required=False,
        ).lower()
        or None
    )
    if level is None:
        return None
    if len(level) > SARIF_LEVEL_MAX_LENGTH:
        _add_length_error(
            errors,
            file,
            field=field,
            value=level,
            max_length=SARIF_LEVEL_MAX_LENGTH,
        )
        return None
    if level not in SUPPORTED_SARIF_LEVELS:
        _add_error(
            errors,
            file,
            field=field,
            message=("SARIF level must be one of error, warning, note, or none."),
            correction_path=(
                "Export SARIF with a supported result or rule "
                "defaultConfiguration.level value."
            ),
        )
        return None
    return level


def _source_format_label(source_format: str | None) -> str:
    if source_format == "semgrep":
        return "Semgrep JSON"
    return "SARIF"


def _rule_id_field(item: _ParsedSarifEvidence) -> str:
    if item.source_format == "semgrep":
        return f"{item.field_prefix}.check_id"
    return f"{item.field_prefix}.ruleId"


def _validate_parsed_storage_bounds(
    file: ScannerImportFile,
    parsed: list[_ParsedSarifEvidence],
) -> None:
    errors: list[ScannerImportFieldError] = []
    for item in parsed:
        format_label = _source_format_label(item.source_format)
        _add_length_error(
            errors,
            file,
            field=f"{item.field_prefix}.tool.driver.name",
            value=item.tool_name,
            max_length=SARIF_TOOL_NAME_MAX_LENGTH,
            format_label=format_label,
        )
        _add_length_error(
            errors,
            file,
            field=_rule_id_field(item),
            value=item.rule_id,
            max_length=SARIF_RULE_ID_MAX_LENGTH,
            format_label=format_label,
        )
        if item.source_format != "semgrep":
            _add_length_error(
                errors,
                file,
                field=f"{item.field_prefix}.rule.name",
                value=item.rule_name,
                max_length=SARIF_RULE_NAME_MAX_LENGTH,
                format_label=format_label,
            )
        source_ref = _source_ref(
            item=item,
            tool_name=item.tool_name,
            rule_id=item.rule_id,
        )
        _add_length_error(
            errors,
            file,
            field=f"{item.field_prefix}.source_ref",
            value=source_ref,
            max_length=SARIF_SOURCE_REF_MAX_LENGTH,
            format_label=format_label,
        )
    if errors:
        raise ScannerImportValidationError(errors)


def _source_refs_by_field(
    file: ScannerImportFile,
    parsed: list[_ParsedSarifEvidence],
) -> dict[str, str]:
    return {
        item.field_prefix: _source_ref(
            item=item,
            tool_name=item.tool_name,
            rule_id=item.rule_id,
        )
        for item in parsed
    }


def _validate_unique_source_refs(
    file: ScannerImportFile,
    source_refs: dict[str, str],
) -> None:
    seen: dict[str, str] = {}
    errors: list[ScannerImportFieldError] = []
    for field_prefix, source_ref in source_refs.items():
        previous_field = seen.get(source_ref)
        if previous_field is None:
            seen[source_ref] = field_prefix
            continue
        _add_error(
            errors,
            file,
            field=field_prefix,
            message=(
                "Scanner result duplicates another finding in this import "
                f"({previous_field})."
            ),
            correction_path="Remove duplicate scanner findings before import.",
        )
    if errors:
        raise ScannerImportValidationError(errors)


def _duplicate_source_ref_error(
    file: ScannerImportFile,
    *,
    format_label: str,
) -> ScannerImportValidationError:
    return ScannerImportValidationError(
        [
            ScannerImportFieldError(
                source_file=file.source_file,
                field="content",
                message=(
                    f"One or more {format_label} findings changed concurrently "
                    "during import."
                ),
                correction_path=f"Retry the {format_label} import.",
            )
        ]
    )


def _scope_changed_error(
    file: ScannerImportFile,
    *,
    format_label: str,
) -> ScannerImportValidationError:
    return ScannerImportValidationError(
        [
            ScannerImportFieldError(
                source_file=file.source_file,
                field="project",
                message=(
                    f"Project or workspace scope changed during {format_label} import."
                ),
                correction_path=(
                    f"Retry the {format_label} import with an existing "
                    "project/workspace scope."
                ),
            )
        ]
    )


def _is_duplicate_source_ref_integrity_error(exc: IntegrityError) -> bool:
    detail = str(getattr(exc, "orig", exc)).lower()
    if "source_ref" not in detail:
        return False
    if "uq_external_scanner_evidence" in detail:
        return True
    return "unique" in detail and "external_scanner_evidence" in detail


def _is_scope_integrity_error(exc: IntegrityError) -> bool:
    detail = str(getattr(exc, "orig", exc)).lower()
    return "foreign key" in detail or "violates foreign key" in detail


def _add_length_error(
    errors: list[ScannerImportFieldError],
    file: ScannerImportFile,
    *,
    field: str,
    value: str | None,
    max_length: int,
    format_label: str = "SARIF",
) -> None:
    if value is None or len(value) <= max_length:
        return
    _add_error(
        errors,
        file,
        field=field,
        message=f"{format_label} field exceeds the {max_length} character storage limit.",
        correction_path=f"Shorten {field} to {max_length} characters or fewer.",
    )


def _source_ref(
    *,
    item: _ParsedSarifEvidence,
    tool_name: str,
    rule_id: str,
) -> str:
    identity_json = json.dumps(item.identity, sort_keys=True, separators=(",", ":"))
    source_format = item.source_format or "sarif"
    digest = hashlib.blake2b(
        identity_json.encode("utf-8"),
        digest_size=16,
        person=f"dw-{source_format}-src".encode("ascii")[:16],
    ).hexdigest()
    query_fields = {}
    if "tool_name" in item.identity:
        query_fields["tool"] = tool_name
    if "rule_id" in item.identity:
        query_fields["ruleId"] = rule_id
    query = urlencode(query_fields)
    if query:
        return f"{source_format}://finding/{digest}?{query}"
    return f"{source_format}://finding/{digest}"


def _source_identity(
    *,
    item_tool_name: str,
    rule_id: str,
    message: str,
    location: dict[str, Any],
    result: dict[str, Any],
    file: ScannerImportFile,
    field_prefix: str,
    errors: list[ScannerImportFieldError],
) -> dict[str, Any]:
    fallback_identity: dict[str, Any] = {
        "tool_name": item_tool_name,
        "rule_id": rule_id,
    }
    fingerprints = _identity_mapping(
        result["fingerprints"] if "fingerprints" in result else {},
        file=file,
        field=f"{field_prefix}.fingerprints",
        errors=errors,
    )
    partial_fingerprints = _identity_mapping(
        result["partialFingerprints"] if "partialFingerprints" in result else {},
        file=file,
        field=f"{field_prefix}.partialFingerprints",
        errors=errors,
    )
    if fingerprints:
        identity: dict[str, Any] = {
            "tool_name": item_tool_name,
            "rule_id": rule_id,
        }
        identity["fingerprints"] = fingerprints
        if partial_fingerprints:
            identity["partial_fingerprints"] = partial_fingerprints
        identity["artifact_uri"] = location["artifact_uri"]
        identity["region"] = _source_identity_region(location["region"])
        return identity
    if partial_fingerprints:
        identity = {
            "tool_name": item_tool_name,
            "rule_id": rule_id,
        }
        identity["partial_fingerprints"] = partial_fingerprints
        identity["artifact_uri"] = location["artifact_uri"]
        identity["region"] = _source_identity_region(location["region"])
        return identity
    message_object = (
        result.get("message") if isinstance(result.get("message"), dict) else {}
    )
    message_id = str(message_object.get("id") or "").strip()
    if message_id:
        fallback_identity["message_id"] = message_id
    fallback_identity.update(
        {
            "artifact_uri": location["artifact_uri"],
            "message_text": message,
            "region": _source_identity_region(location["region"]),
        }
    )
    return fallback_identity


def _source_identity_region(region: dict[str, Any]) -> dict[str, int]:
    identity_region: dict[str, int] = {}
    for field_name in ("startLine", "startColumn", "endLine", "endColumn"):
        value = region.get(field_name)
        if type(value) is int:
            identity_region[field_name] = value
    return identity_region


def _identity_mapping(
    value: object,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
) -> dict[str, str]:
    if not isinstance(value, dict):
        _add_error(
            errors,
            file,
            field=field,
            message="SARIF fingerprints must be string maps.",
            correction_path="Export SARIF fingerprints and partialFingerprints as objects with string keys and string values.",
        )
        return {}
    resolved: dict[str, str] = {}
    for key, mapping_value in sorted(value.items(), key=lambda item: str(item[0])):
        if mapping_value is None:
            continue
        if not isinstance(key, str):
            _add_error(
                errors,
                file,
                field=f"{field}.{key}",
                message="SARIF fingerprint names must be strings.",
                correction_path="Export SARIF fingerprints as string maps.",
            )
            continue
        if not key.strip():
            _add_error(
                errors,
                file,
                field=f"{field}.<blank>",
                message="SARIF fingerprint names must not be blank.",
                correction_path="Export SARIF fingerprints with non-empty string names.",
            )
            continue
        if not isinstance(mapping_value, str):
            _add_error(
                errors,
                file,
                field=f"{field}.{key}",
                message="SARIF fingerprint values must be strings.",
                correction_path="Export SARIF fingerprints as string maps.",
            )
            continue
        if not mapping_value.strip():
            _add_error(
                errors,
                file,
                field=f"{field}.{key}",
                message="SARIF fingerprint values must not be blank.",
                correction_path="Export SARIF fingerprints with non-empty string values.",
            )
            continue
        resolved[key] = mapping_value
    return resolved


def _string_value(
    owner: dict[str, Any],
    key: str,
    *,
    file: ScannerImportFile,
    field: str,
    errors: list[ScannerImportFieldError],
    required: bool,
) -> str:
    value = owner.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        _add_error(
            errors,
            file,
            field=field,
            message=f"SARIF {field} must be a string.",
            correction_path=f"Export SARIF with {field} encoded as a string.",
        )
        return ""
    text = value.strip()
    if required or text:
        return text
    return ""


def _add_surrogate_string_errors(
    errors: list[ScannerImportFieldError],
    file: ScannerImportFile,
    value: object,
    *,
    path: str,
    format_label: str = "SARIF",
) -> None:
    if isinstance(value, str):
        if _contains_surrogate(value):
            _add_error(
                errors,
                file,
                field=path or "content",
                message=(
                    f"{format_label} content contains invalid Unicode surrogate "
                    "characters."
                ),
                correction_path=(
                    f"Export {format_label} as valid UTF-8 JSON without lone "
                    "surrogate escapes."
                ),
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _add_surrogate_string_errors(
                errors,
                file,
                item,
                path=f"{path}[{index}]" if path else f"[{index}]",
                format_label=format_label,
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _contains_surrogate(key):
                _add_error(
                    errors,
                    file,
                    field=f"{path}.<key>" if path else "<key>",
                    message=(
                        f"{format_label} content contains invalid Unicode surrogate "
                        "characters."
                    ),
                    correction_path=(
                        f"Export {format_label} as valid UTF-8 JSON without lone "
                        "surrogate escapes."
                    ),
                )
            field = f"{path}.{key}" if path else str(key)
            _add_surrogate_string_errors(
                errors,
                file,
                item,
                path=field,
                format_label=format_label,
            )


def _contains_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _serialize_evidence(record) -> ExternalScannerEvidenceRecord:
    return ExternalScannerEvidenceRecord(
        id=record.id,
        import_id=record.import_id,
        evidence_id=record.evidence_id,
        project_id=record.project_id,
        project_key=record.project_key,
        workspace_id=record.workspace_id,
        workspace_key=record.workspace_key,
        source_type=record.source_type,
        source_file=record.source_file,
        source_ref=record.source_ref,
        tool_name=record.tool_name,
        rule_id=record.rule_id,
        rule_name=record.rule_name,
        severity=record.severity,
        level=record.level,
        message=record.message,
        location=record.location,
        artifact_uri=record.artifact_uri,
        region=json.loads(record.region_json or "{}"),
        properties=json.loads(record.properties_json or "{}"),
    )


def _add_error(
    errors: list[ScannerImportFieldError],
    file: ScannerImportFile,
    *,
    field: str,
    message: str,
    correction_path: str,
) -> None:
    errors.append(
        ScannerImportFieldError(
            source_file=file.source_file,
            field=field,
            message=message,
            correction_path=correction_path,
        )
    )
