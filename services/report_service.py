"""Report workflow orchestration."""

from __future__ import annotations

import json
import math
import os
import secrets
import hashlib
import hmac
import ipaddress
import re
import unicodedata
from datetime import UTC, datetime
from collections import Counter, defaultdict
from urllib.parse import urlsplit
from typing import Any

from pydantic import ValidationError

from analysis.blast_radius import BlastRadiusResult
from analysis.rollback_planner import RollbackPlan
from analysis.risk_scorer import (
    RiskAssessment,
    RiskContributor,
    apply_context_uncertainty,
)
from api.schemas import IntakeItem, PendingAnalysis
from evidence.mappers import classify_finding_evidence
from evidence.models import ContextCompleteness, EvidenceItem, Finding
from llm.narrator import NarrativeResult

from models.database import SessionLocal
from models.repositories.analysis_reports import (
    count_analysis_reports,
    count_analysis_reports_by_field,
    create_analysis_report,
    delete_analysis_report,
    get_analysis_report,
    latest_active_dashboard_report,
    list_analysis_reports,
    update_analysis_report_share_settings,
)
from parsers.base import ParseBatchResult, ParsedFileResult
from services.artifact_snapshot_service import (
    delete_report_artifacts,
    save_report_artifacts,
)
from services.confidence_ledger import (
    LEDGER_KEYS,
    build_confidence_ledger,
    normalize_confidence_ledger_payload,
)
from services.project_service import (
    build_project_payload,
    build_workspace_payload,
    resolve_project_reference,
    resolve_workspace_reference,
)
from services.settings_service import get_dashboard_result_display_duration_seconds
from services.settings_service import resolve_provider_runtime
from services.submission_manifest import (
    SubmissionManifest,
    build_submission_manifest,
    normalize_manifest_redaction_status,
    normalize_submission_manifest_payload,
)
from services.topology_service import STALE_AFTER_DAYS

LEGACY_REPORT_SCHEMA_VERSION = "v1"
REPORT_SCHEMA_VERSION = "v2"
_SUBMISSION_MANIFEST_INFERRED_WARNING = (
    "Submission manifest metadata was inferred from available analysis artifacts "
    "because submitted artifact context was unavailable; excluded or sensitive "
    "submissions may be missing."
)
_AMBIGUOUS_ARTIFACT_REPLACEMENT = "Artifact file"
_NON_VISIBLE_NARRATIVE_CATEGORIES = {"Cc", "Cf", "Mc", "Me", "Mn"}
_EXTENSIONLESS_FILE_BASENAMES = {
    "Brewfile",
    "BUILD",
    "Containerfile",
    "Dockerfile",
    "Earthfile",
    "Gemfile",
    "Jenkinsfile",
    "Justfile",
    "Makefile",
    "Procfile",
    "Rakefile",
    "Taskfile",
    "Tiltfile",
    "Vagrantfile",
    "WORKSPACE",
}
_SEVERITY_PREFIX_PATTERN = re.compile(
    r"^\s*(critical|high|medium|low|info|warning|caution)\s*[:\-]\s*",
    flags=re.IGNORECASE,
)
_VERDICT_PREFIX_PATTERN = re.compile(
    r"^\s*(critical|high|medium|low|no-go|go|caution)"
    r"(?:\s*:\s*|\s+-\s+|"
    r"\s+(?=(?:because|due|risk|risks|finding|findings|claim|claims|unsupported|"
    r"severe|exposure|exposures|verdict|verdicts|deployment|database|"
    r"ingress|review|reviews|blocked|blocker|blockers|issue|issues|"
    r"incident|incidents|outage|outages|rollback|access|network|"
    r"security|permission|policy|blast|radius)\b))",
    flags=re.IGNORECASE,
)
_FINDING_SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_SEVERITY_SCORE_FLOOR = {"low": 0, "medium": 42, "high": 70, "critical": 90}
_SEVERITY_SCORE_CEILING = {"low": 39, "medium": 69, "high": 89, "critical": 100}
_CONTEXT_JSON_MALFORMED_WARNING = "Context completeness metadata was unavailable because persisted JSON was malformed."
_CONTEXT_JSON_SHAPE_WARNING = (
    "Context completeness metadata was unavailable because persisted JSON had an "
    "unexpected shape."
)
_CONTEXT_JSON_INCOMPLETE_WARNING = "Context completeness metadata was unavailable because persisted values were incomplete."
_CONTEXT_JSON_INVALID_WARNING = "Context completeness metadata was unavailable because persisted values were invalid."
_CONFIDENCE_INVALID_WARNING = (
    "Report confidence metadata was invalid and was reset to 0.0."
)
_CONTEXT_UNAVAILABLE_UNCERTAINTY = (
    "Context completeness metadata was unavailable; reviewer verification is "
    "required before trusting this report."
)
_AUDIT_ACTOR_MAX_LENGTH = 120
_CONTEXT_UNAVAILABLE_TODO = (
    "Re-run analysis to regenerate context completeness metadata."
)
_LEGACY_CONTEXT_CORE_FIELDS = {
    "topology_freshness_days",
    "topology_last_imported_at",
    "incident_index_size",
    "parser_success_rate",
    "parser_success_by_tool",
    "context_score",
}


class ReportSchemaVersionError(ValueError):
    """Raised when a stored report schema version cannot be safely read."""

    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _resolve_project_id(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
) -> int | None:
    if project_id is None and project_key is None:
        return None
    return resolve_project_reference(
        project_id=project_id,
        project_key=project_key,
    ).id


def _resolve_report_scope(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> tuple[int | None, int | None]:
    workspace = resolve_workspace_reference(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    if workspace is not None:
        return workspace.project_id, workspace.id
    return (
        _resolve_project_id(project_id=project_id, project_key=project_key),
        None,
    )


def build_share_report_link(report_id: int | None) -> str | None:
    if report_id is None:
        return None
    base_url = (
        (os.getenv("APP_BASE_URL") or os.getenv("PUBLIC_APP_URL") or "")
        .strip()
        .rstrip("/")
    )
    if not base_url:
        host = _share_link_host(os.getenv("APP_HOST", "127.0.0.1"))
        port = int(os.getenv("APP_PORT", "8080"))
        base_url = f"http://{host}:{port}"
    return f"{base_url}/reports/{report_id}"


def _share_link_host(host: str) -> str:
    cleaned = str(host).strip()
    if not cleaned:
        return "localhost"
    if "%" in cleaned and not cleaned.startswith("[") and cleaned.count(":") > 1:
        address_part, scope_part = cleaned.split("%", 1)
        scope_name, separator, candidate_port = scope_part.rpartition(":")
        if separator and candidate_port.isdigit() and scope_name:
            candidate_host = f"{address_part}%{scope_name}"
            try:
                ipaddress.ip_address(candidate_host)
            except ValueError:
                pass
            else:
                cleaned = candidate_host
    if cleaned.startswith("[") or cleaned.count(":") == 1:
        try:
            parsed_host = urlsplit(f"//{cleaned}").hostname
        except ValueError:
            parsed_host = None
        if parsed_host:
            cleaned = parsed_host
    if not cleaned.startswith("[") and cleaned.count(":") > 1:
        ip_literal = cleaned.removeprefix("[").removesuffix("]")
        try:
            ipaddress.ip_address(ip_literal)
        except ValueError:
            candidate_host, separator, candidate_port = cleaned.rpartition(":")
            if not (separator and candidate_port.isdigit() and len(candidate_port) > 4):
                candidate_host = ""
            try:
                ipaddress.ip_address(candidate_host)
            except ValueError:
                pass
            else:
                cleaned = candidate_host
    ip_literal = cleaned.removeprefix("[").removesuffix("]")
    try:
        parsed = ipaddress.ip_address(ip_literal)
    except ValueError:
        if cleaned.startswith("[") and cleaned.endswith("]"):
            return ip_literal
        return cleaned
    if parsed.is_unspecified:
        return "localhost"
    if parsed.version == 6:
        address = parsed.compressed
        if "%" in address and "%25" not in address:
            address = address.replace("%", "%25", 1)
        return f"[{address}]"
    return parsed.compressed


def _known_narrative_source(source: str | None) -> str | None:
    normalized = source or None
    if normalized in {"llm", "fallback"}:
        return normalized
    return None


def _has_visible_narrative_text(value: str) -> bool:
    return any(
        not character.isspace()
        and unicodedata.category(character) not in _NON_VISIBLE_NARRATIVE_CATEGORIES
        for character in value
    )


def _narrative_degraded_from_state(
    *,
    explicit_degraded: bool | None,
    narrative_source: str | None,
    failure_notice: str | None,
    narrative_available: bool,
) -> bool:
    return (
        bool(explicit_degraded)
        or _known_narrative_source(narrative_source) == "fallback"
        or failure_notice is not None
        or not narrative_available
    )


def _hash_share_password(password: str, *, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def _share_settings(report: dict[str, Any]) -> dict[str, Any]:
    report_id = int(report["id"])
    return {
        "share_url": build_share_report_link(report_id),
        "password_protected": bool(report.get("share_password_hash")),
        "redact_filenames": bool(report.get("share_redact_filenames", False)),
    }


def _redaction_pairs(original_names: list[str]) -> list[tuple[str, str]]:
    basename_counts: Counter[str] = Counter()
    for original_name in original_names:
        basename_counts[str(original_name).split("/")[-1]] += 1
    pairs: list[tuple[str, str]] = []
    for index, original_name in enumerate(original_names, start=1):
        replacement = f"Artifact {index}"
        pairs.append((original_name, replacement))
        basename = str(original_name).split("/")[-1]
        if _is_redactable_basename(basename):
            basename_replacement = (
                replacement
                if basename_counts[basename] == 1
                else _AMBIGUOUS_ARTIFACT_REPLACEMENT
            )
            basename_pair = (basename, basename_replacement)
            if basename_pair not in pairs:
                pairs.append(basename_pair)
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def _is_redactable_basename(basename: str) -> bool:
    return "." in basename or basename in _EXTENSIONLESS_FILE_BASENAMES


def _redact_text_value(value: Any, pairs: list[tuple[str, str]]) -> Any:
    if not isinstance(value, str):
        return value
    redacted = value
    for original, replacement in pairs:
        redacted = redacted.replace(original, replacement)
    return redacted


def _redact_report_file_names(report: dict[str, Any]) -> dict[str, Any]:
    audit_names = list(report.get("audit", {}).get("files_analyzed") or [])
    original_names = list(audit_names)
    for item in (report.get("submission_manifest") or {}).get("items") or []:
        item_name = str(item.get("name") or "")
        if item_name and item_name not in original_names:
            original_names.append(item_name)
    for item in report.get("submission_manifest_fallback") or []:
        item_name = str(item.get("name") or "")
        if item_name and item_name not in original_names:
            original_names.append(item_name)
    if not original_names:
        return report
    redaction_map = {
        original_name: f"Artifact {index}"
        for index, original_name in enumerate(original_names, start=1)
    }
    pairs = _redaction_pairs(original_names)
    redacted = {
        **report,
        "top_risk": _redact_text_value(report.get("top_risk"), pairs),
        "parse_summary": _redact_text_value(report.get("parse_summary"), pairs),
        "narrative_opening": _redact_text_value(report.get("narrative_opening"), pairs),
        "narrative_failure_notice": _redact_text_value(
            report.get("narrative_failure_notice"), pairs
        ),
        "warnings": [
            _redact_text_value(warning, pairs)
            for warning in (report.get("warnings") or [])
        ],
        "audit": {
            **dict(report.get("audit") or {}),
            "files_analyzed": [redaction_map[name] for name in audit_names],
        },
        "submission_manifest": _redact_submission_manifest_file_names(
            dict(report.get("submission_manifest") or {}),
            redaction_map,
            pairs,
        ),
        "submission_manifest_fallback": _redact_submission_manifest_fallback_file_names(
            report.get("submission_manifest_fallback") or [],
            redaction_map,
        ),
        "findings": [
            {
                **finding,
                "title": _redact_text_value(finding.get("title"), pairs),
                "description": _redact_text_value(finding.get("description"), pairs),
                "explanation": _redact_text_value(finding.get("explanation"), pairs),
                "guidance": [
                    _redact_text_value(guidance, pairs)
                    for guidance in (finding.get("guidance") or [])
                ],
                "uncertainty_note": _redact_text_value(
                    finding.get("uncertainty_note"), pairs
                ),
            }
            for finding in (report.get("findings") or [])
        ],
        "contributors": [
            {
                **contributor,
                "source_file": redaction_map.get(
                    contributor.get("source_file"),
                    contributor.get("source_file"),
                ),
                "summary": _redact_text_value(contributor.get("summary"), pairs),
                "reasoning": _redact_text_value(contributor.get("reasoning"), pairs),
            }
            for contributor in (report.get("contributors") or [])
        ],
        "evidence_items": [
            {
                **evidence_item,
                "source_ref": _redact_text_value(
                    evidence_item.get("source_ref", ""), pairs
                ),
                "artifact": redaction_map.get(
                    evidence_item.get("artifact"),
                    _redact_text_value(evidence_item.get("artifact", ""), pairs),
                ),
                "location": _redact_text_value(
                    evidence_item.get("location", ""), pairs
                ),
                "summary": _redact_text_value(evidence_item.get("summary"), pairs),
                "redaction_status": (
                    "sensitive_blocked"
                    if evidence_item.get("redaction_status") == "sensitive_blocked"
                    else "redacted"
                ),
            }
            for evidence_item in (report.get("evidence_items") or [])
        ],
        "confidence_ledger": _redact_confidence_ledger(
            report.get("confidence_ledger") or {},
            pairs,
        ),
    }
    return redacted


def _redact_confidence_ledger(
    ledger: dict[str, Any],
    pairs: list[tuple[str, str]],
) -> dict[str, list[str]]:
    normalized = normalize_confidence_ledger_payload(ledger)
    return {
        key: [
            str(_redact_text_value(item, pairs))
            for item in normalized[key]
            if str(item).strip()
        ]
        for key in LEDGER_KEYS
    }


def _redact_submission_manifest_file_names(
    manifest: dict[str, Any],
    redaction_map: dict[str, str],
    pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    if not manifest:
        return manifest
    redacted_items = []
    for item in manifest.get("items") or []:
        item_payload = dict(item)
        original_name = str(item_payload.get("name") or "")
        replacement = redaction_map.get(original_name, original_name)
        provenance = dict(item_payload.get("provenance") or {})
        provenance = {
            "submitted_index": provenance.get("submitted_index"),
            "submitted_name": replacement,
        }
        item_payload["name"] = replacement
        item_payload["message"] = _redact_text_value(item_payload.get("message"), pairs)
        item_payload["provenance"] = provenance
        if (
            normalize_manifest_redaction_status(item_payload.get("redaction_status"))
            != "sensitive_blocked"
        ):
            item_payload["redaction_status"] = "redacted"
        else:
            item_payload["redaction_status"] = "sensitive_blocked"
        redacted_items.append(item_payload)
    return {
        **manifest,
        "provenance": {},
        "items": redacted_items,
        "redaction": {
            **dict(manifest.get("redaction") or {}),
            "filenames_redacted": True,
        },
    }


def _redact_submission_manifest_fallback_file_names(
    fallback_items: list[dict[str, Any]],
    redaction_map: dict[str, str],
) -> list[dict[str, Any]]:
    redacted_items: list[dict[str, Any]] = []
    for item in fallback_items:
        item_payload = dict(item)
        original_name = str(item_payload.get("name") or "")
        item_payload["name"] = redaction_map.get(original_name, original_name)
        if (
            normalize_manifest_redaction_status(item_payload.get("redaction_status"))
            != "sensitive_blocked"
        ):
            item_payload["redaction_status"] = "redacted"
        else:
            item_payload["redaction_status"] = "sensitive_blocked"
        redacted_items.append(item_payload)
    return redacted_items


def _run_with_schema_retry(operation):
    """Execute one report operation without runtime schema mutation."""
    return operation()


def _build_parse_summary(parse_batch: ParseBatchResult) -> str:
    return (
        f"{parse_batch.parsed_count} parsed, "
        f"{parse_batch.failed_count} failed, "
        f"{parse_batch.skipped_count} skipped, "
        f"{parse_batch.total_change_count} normalized changes"
    )


def _build_audit_metadata(
    parse_batch: ParseBatchResult,
    *,
    audit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = resolve_provider_runtime()
    context = audit_context or {}
    source_interface = str(context.get("source_interface") or "service")
    trigger_type = context.get("trigger_type")
    trigger_id = context.get("trigger_id")
    return {
        "files_analyzed": [
            file_result.file_name
            for file_result in parse_batch.files
            if file_result.status == "parsed"
        ],
        "llm_provider": runtime["provider"],
        "llm_model": runtime["model"],
        "llm_local_mode": runtime["local_mode"],
        "source_interface": source_interface,
        "trigger_type": trigger_type,
        "trigger_id": trigger_id,
        "actor": _normalize_audit_actor(context.get("actor"), source_interface),
    }


def _default_audit_actor(source_interface: str | None) -> str:
    surface = str(source_interface or "service").strip().lower()
    defaults = {
        "api": "api_client",
        "cli": "cli_local_user",
        "github_app": "github_app",
        "ui": "ui_local_user",
    }
    return defaults.get(surface, f"{surface or 'service'}_actor")


def _normalize_audit_actor(value: Any, source_interface: str | None) -> str:
    fallback = _default_audit_actor(source_interface)
    normalized = " ".join(str(value or fallback).split())
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith("C")
    ).strip()
    if not normalized:
        return fallback
    return normalized[:_AUDIT_ACTOR_MAX_LENGTH]


def _redaction_status_from_items(items: Any) -> str | None:
    if not isinstance(items, list):
        return None
    item_statuses = {
        normalize_manifest_redaction_status(item.get("redaction_status"))
        for item in items
        if isinstance(item, dict) and "redaction_status" in item
    }
    if not item_statuses:
        return None
    if "sensitive_blocked" in item_statuses:
        return "sensitive_blocked"
    if "redacted" in item_statuses:
        return "redacted"
    return "none"


def _report_redaction_status(
    submission_manifest: dict[str, Any] | None,
    submission_manifest_fallback: list[dict[str, Any]] | None = None,
) -> str:
    if isinstance(submission_manifest, dict):
        redaction = submission_manifest.get("redaction")
        has_redaction_metadata = isinstance(redaction, dict) and any(
            key in redaction
            for key in ("filenames_redacted", "sensitive_content_excluded")
        )
        if isinstance(redaction, dict) and redaction.get("sensitive_content_excluded"):
            return "sensitive_blocked"
        item_status = _redaction_status_from_items(submission_manifest.get("items"))
        if item_status == "sensitive_blocked":
            return item_status
        if isinstance(redaction, dict) and redaction.get("filenames_redacted"):
            return "redacted"
        if item_status == "redacted":
            return item_status
        if item_status == "none" or has_redaction_metadata:
            return "none"
    fallback_status = _redaction_status_from_items(submission_manifest_fallback)
    return fallback_status or "unknown"


def _report_redaction_metadata(
    submission_manifest: dict[str, Any] | None,
    submission_manifest_fallback: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if isinstance(submission_manifest, dict):
        redaction = submission_manifest.get("redaction")
        if isinstance(redaction, dict) and redaction:
            return dict(redaction)
    if submission_manifest_fallback:
        statuses = {
            normalize_manifest_redaction_status(item.get("redaction_status"))
            for item in submission_manifest_fallback
            if isinstance(item, dict) and "redaction_status" in item
        }
        if statuses:
            return {
                "filenames_redacted": "redacted" in statuses,
                "sensitive_content_excluded": "sensitive_blocked" in statuses,
            }
    return {}


def _delivery_metadata(
    *,
    source_interface: str | None,
    trigger_type: str | None,
    trigger_id: str | None,
    report_id: int,
) -> dict[str, Any]:
    return {
        "surface": source_interface,
        "trigger_type": trigger_type,
        "trigger_id": trigger_id,
        "report_id": report_id,
        "status": "persisted",
    }


def _cleanup_partial_report(report_id: int | None) -> None:
    if report_id is None:
        return
    try:
        with SessionLocal() as session:
            delete_analysis_report(session, report_id)
    except Exception:
        pass
    try:
        delete_report_artifacts(report_id)
    except Exception:
        pass


def _extract_narrative_failure_notice(warnings: list[str]) -> str | None:
    for warning in warnings:
        normalized = warning.lower()
        if (
            "narrative provider unavailable" in normalized
            or "narrative setup unavailable" in normalized
            or normalized.startswith("narrative unavailable:")
        ):
            return warning
    return None


def _default_blast_radius_payload() -> dict[str, Any]:
    return {
        "affected": [],
        "direct_count": 0,
        "transitive_count": 0,
        "warning": None,
        "unmatched_resources": [],
    }


def _default_rollback_plan_payload() -> dict[str, Any]:
    return {
        "steps": [],
        "complexity": "low",
        "complexity_score": 1,
        "complexity_explanation": (
            "Minimal rollback effort based on the available change set."
        ),
        "warning": None,
    }


def _pending_analysis_from_parse_batch(
    parse_batch: ParseBatchResult,
) -> PendingAnalysis:
    def intake_item_for(file_result: ParsedFileResult) -> IntakeItem:
        if file_result.status == "skipped":
            return IntakeItem(
                name=file_result.file_name,
                tool=file_result.tool,
                status="unsupported",
                message=(
                    file_result.issue.message
                    if file_result.issue is not None
                    else "Artifact excluded from parser analysis."
                ),
            )
        return IntakeItem(
            name=file_result.file_name,
            tool=file_result.tool,
            status="ready",
            message=f"{file_result.tool.title()} artifact accepted for analysis.",
        )

    return PendingAnalysis(
        items=[intake_item_for(file_result) for file_result in parse_batch.files]
    )


def _artifact_signature(files_analyzed: list[str]) -> tuple[str, ...]:
    """Normalize analyzed-file identity for history diff grouping."""
    return tuple(sorted(str(name) for name in files_analyzed if str(name).strip()))


def _report_artifact_names(report: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for original_name in report.get("audit", {}).get("files_analyzed") or []:
        if original_name not in names:
            names.append(original_name)
    for item in (report.get("submission_manifest") or {}).get("items") or []:
        item_name = str(item.get("name") or "")
        if item_name and item_name not in names:
            names.append(item_name)
    return names


ComparisonArtifact = tuple[str, str, str, str, str, bool]


def _comparison_artifact_signature(
    report: dict[str, Any],
) -> tuple[ComparisonArtifact, ...]:
    manifest = report.get("submission_manifest", {})
    if manifest is None:
        return tuple()
    manifest_items = (manifest or {}).get("items") or []
    if manifest_items:
        return tuple(
            sorted(
                (
                    str(item.get("name") or ""),
                    str(item.get("tool") or ""),
                    str(item.get("status") or ""),
                    str(item.get("intake_status") or ""),
                    str(item.get("parse_status") or ""),
                    bool(item.get("partial", False)),
                )
                for item in manifest_items
                if str(item.get("name") or "").strip()
            )
        )
    legacy_tool_by_artifact = _legacy_tool_by_artifact(report)
    return tuple(
        (
            name,
            legacy_tool_by_artifact.get(name, ""),
            "accepted",
            "ready",
            "parsed",
            False,
        )
        for name in _artifact_signature(
            report.get("audit", {}).get("files_analyzed") or []
        )
    )


def _legacy_tool_by_artifact(report: dict[str, Any]) -> dict[str, str]:
    tools_by_artifact: dict[str, set[str]] = defaultdict(set)
    for contributor in report.get("contributors") or []:
        source_file = str(contributor.get("source_file") or "").strip()
        tool = str(contributor.get("tool") or "").strip()
        if source_file and tool:
            tools_by_artifact[source_file].add(tool)
    return {
        source_file: next(iter(tools))
        for source_file, tools in tools_by_artifact.items()
        if len(tools) == 1
    }


def _comparison_signatures_match(
    left: tuple[ComparisonArtifact, ...],
    right: tuple[ComparisonArtifact, ...],
) -> bool:
    return left == right


def _history_signature(
    report: dict[str, Any],
) -> tuple[int, int, tuple[ComparisonArtifact, ...]] | None:
    artifact_signature = _comparison_artifact_signature(report)
    if not artifact_signature:
        return None
    project_id = int(report.get("project", {}).get("id") or 0)
    workspace_id = int((report.get("workspace") or {}).get("id") or 0)
    return (project_id, workspace_id, artifact_signature)


def _normalize_free_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return " ".join(text.split())


def _normalize_finding_text(value: Any) -> str:
    return _normalize_free_text(_SEVERITY_PREFIX_PATTERN.sub("", str(value or "")))


def _finding_fingerprint(finding: dict[str, Any]) -> str:
    return "|".join(
        [
            _normalize_free_text(finding.get("category")),
            _normalize_finding_text(finding.get("title")),
            _normalize_finding_text(finding.get("description")),
        ]
    )


def _evidence_fingerprint(evidence_item: dict[str, Any]) -> str:
    related_change_ids = ",".join(
        sorted(
            str(change_id)
            for change_id in evidence_item.get("related_change_ids") or []
        )
    )
    return "|".join(
        [
            _normalize_free_text(evidence_item.get("source_type")),
            _normalize_free_text(evidence_item.get("source_ref")),
            _normalize_free_text(evidence_item.get("artifact")),
            _normalize_free_text(evidence_item.get("location")),
            _normalize_free_text(evidence_item.get("resource")),
            _normalize_free_text(evidence_item.get("operation")),
            _normalize_free_text(evidence_item.get("summary")),
            _normalize_free_text(evidence_item.get("severity_hint")),
            related_change_ids,
        ]
    )


def _comparison_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(report["id"]),
        "created_at": report["created_at"],
        "risk_score": int(report.get("risk_score") or 0),
        "severity": str(report.get("severity") or "unknown"),
        "recommendation": str(report.get("recommendation") or "unknown"),
        "top_risk": str(report.get("top_risk") or ""),
        "context_completeness": dict(report.get("context_completeness") or {}),
    }


def _comparison_finding_summary(
    finding: dict[str, Any],
    *,
    evidence_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_rows = evidence_items or []
    return {
        "title": str(finding.get("title") or "Untitled finding"),
        "severity": str(finding.get("severity") or "unknown"),
        "description": str(finding.get("description") or ""),
        "category": str(finding.get("category") or ""),
        "evidence_count": len(evidence_rows),
    }


def _comparison_evidence_summary(
    evidence_item: dict[str, Any],
    *,
    finding_title: str,
) -> dict[str, Any]:
    return {
        "finding_title": finding_title,
        "source_type": str(evidence_item.get("source_type") or "unknown"),
        "source_ref": str(evidence_item.get("source_ref") or ""),
        "summary": str(evidence_item.get("summary") or ""),
        "severity_hint": str(evidence_item.get("severity_hint") or "unknown"),
    }


def _comparison_finding_sort_key(
    finding: dict[str, Any],
    *,
    evidence_items: list[dict[str, Any]],
) -> tuple[Any, ...]:
    evidence_key = tuple(
        sorted(_evidence_fingerprint(evidence_item) for evidence_item in evidence_items)
    )
    return (
        evidence_key,
        str(finding.get("severity") or "unknown"),
        f"{float(finding.get('confidence') or 0.0):.6f}",
        str(finding.get("explanation") or ""),
        tuple(str(item) for item in (finding.get("guidance") or [])),
        str(finding.get("evidence_classification") or ""),
        str(finding.get("uncertainty_note") or ""),
        str(finding.get("skill_id") or ""),
    )


def _report_finding_maps(
    report: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    findings_by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_by_finding_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_items = list(report.get("evidence_items") or [])
    evidence_by_id = {
        str(evidence_item.get("evidence_id") or ""): evidence_item
        for evidence_item in evidence_items
    }
    for finding in report.get("findings") or []:
        finding_id = str(finding.get("finding_id") or "")
        seen_evidence_ids: set[str] = set()
        for evidence_ref in finding.get("evidence_refs") or []:
            evidence_id = str(evidence_ref)
            evidence_item = evidence_by_id.get(evidence_id)
            if evidence_item is None:
                continue
            evidence_by_finding_id[finding_id].append(evidence_item)
            seen_evidence_ids.add(evidence_id)
        for evidence_item in evidence_items:
            evidence_id = str(evidence_item.get("evidence_id") or "")
            if (
                str(evidence_item.get("finding_id") or "") == finding_id
                and evidence_id not in seen_evidence_ids
            ):
                evidence_by_finding_id[finding_id].append(evidence_item)
                seen_evidence_ids.add(evidence_id)
        findings_by_fingerprint[_finding_fingerprint(finding)].append(finding)
    return dict(findings_by_fingerprint), evidence_by_finding_id


def _evidence_diff(
    *,
    previous_finding: dict[str, Any],
    current_finding: dict[str, Any],
    previous_evidence_items: list[dict[str, Any]],
    current_evidence_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    previous_by_fingerprint = {
        _evidence_fingerprint(evidence_item): evidence_item
        for evidence_item in previous_evidence_items
    }
    current_by_fingerprint = {
        _evidence_fingerprint(evidence_item): evidence_item
        for evidence_item in current_evidence_items
    }
    added = [
        _comparison_evidence_summary(
            current_by_fingerprint[fingerprint],
            finding_title=str(current_finding.get("title") or "Untitled finding"),
        )
        for fingerprint in sorted(
            set(current_by_fingerprint) - set(previous_by_fingerprint)
        )
    ]
    removed = [
        _comparison_evidence_summary(
            previous_by_fingerprint[fingerprint],
            finding_title=str(previous_finding.get("title") or "Untitled finding"),
        )
        for fingerprint in sorted(
            set(previous_by_fingerprint) - set(current_by_fingerprint)
        )
    ]
    return added, removed


def _build_report_comparison(
    current_report: dict[str, Any],
    previous_report: dict[str, Any],
) -> dict[str, Any]:
    current_findings, current_evidence_by_finding = _report_finding_maps(current_report)
    previous_findings, previous_evidence_by_finding = _report_finding_maps(
        previous_report
    )
    findings_added: list[dict[str, Any]] = []
    findings_removed: list[dict[str, Any]] = []
    severity_changed: list[dict[str, Any]] = []
    evidence_added: list[dict[str, Any]] = []
    evidence_removed: list[dict[str, Any]] = []

    for fingerprint in sorted(set(previous_findings) | set(current_findings)):
        previous_group = sorted(
            previous_findings.get(fingerprint, []),
            key=lambda finding: _comparison_finding_sort_key(
                finding,
                evidence_items=previous_evidence_by_finding.get(
                    str(finding.get("finding_id") or ""),
                    [],
                ),
            ),
        )
        current_group = sorted(
            current_findings.get(fingerprint, []),
            key=lambda finding: _comparison_finding_sort_key(
                finding,
                evidence_items=current_evidence_by_finding.get(
                    str(finding.get("finding_id") or ""),
                    [],
                ),
            ),
        )
        shared_count = min(len(previous_group), len(current_group))

        for current_finding in current_group[shared_count:]:
            current_evidence = current_evidence_by_finding.get(
                str(current_finding.get("finding_id") or ""),
                [],
            )
            findings_added.append(
                _comparison_finding_summary(
                    current_finding,
                    evidence_items=current_evidence,
                )
            )
            evidence_added.extend(
                _comparison_evidence_summary(
                    evidence_item,
                    finding_title=str(
                        current_finding.get("title") or "Untitled finding"
                    ),
                )
                for evidence_item in current_evidence
            )
        for previous_finding in previous_group[shared_count:]:
            previous_evidence = previous_evidence_by_finding.get(
                str(previous_finding.get("finding_id") or ""),
                [],
            )
            findings_removed.append(
                _comparison_finding_summary(
                    previous_finding,
                    evidence_items=previous_evidence,
                )
            )
            evidence_removed.extend(
                _comparison_evidence_summary(
                    evidence_item,
                    finding_title=str(
                        previous_finding.get("title") or "Untitled finding"
                    ),
                )
                for evidence_item in previous_evidence
            )

        for previous_finding, current_finding in zip(
            previous_group[:shared_count],
            current_group[:shared_count],
        ):
            previous_evidence = previous_evidence_by_finding.get(
                str(previous_finding.get("finding_id") or ""),
                [],
            )
            current_evidence = current_evidence_by_finding.get(
                str(current_finding.get("finding_id") or ""),
                [],
            )
            if str(previous_finding.get("severity")) != str(
                current_finding.get("severity")
            ):
                severity_changed.append(
                    {
                        "title": str(
                            current_finding.get("title") or "Untitled finding"
                        ),
                        "description": str(
                            current_finding.get("description")
                            or previous_finding.get("description")
                            or ""
                        ),
                        "previous_severity": str(
                            previous_finding.get("severity") or "unknown"
                        ),
                        "current_severity": str(
                            current_finding.get("severity") or "unknown"
                        ),
                    }
                )
            added, removed = _evidence_diff(
                previous_finding=previous_finding,
                current_finding=current_finding,
                previous_evidence_items=previous_evidence,
                current_evidence_items=current_evidence,
            )
            evidence_added.extend(added)
            evidence_removed.extend(removed)

    current_score = int(current_report.get("risk_score") or 0)
    previous_score = int(previous_report.get("risk_score") or 0)
    risk_score_delta = current_score - previous_score
    if risk_score_delta > 0:
        score_direction = "up"
    elif risk_score_delta < 0:
        score_direction = "down"
    else:
        score_direction = "flat"
    return {
        "previous_report": _comparison_report_summary(previous_report),
        "current_report": _comparison_report_summary(current_report),
        "risk_score_delta": risk_score_delta,
        "risk_score_direction": score_direction,
        "findings": {
            "added": findings_added,
            "removed": findings_removed,
            "severity_changed": severity_changed,
        },
        "evidence": {
            "added": evidence_added,
            "removed": evidence_removed,
        },
        "summary": {
            "findings_added": len(findings_added),
            "findings_removed": len(findings_removed),
            "severity_changes": len(severity_changed),
            "evidence_added": len(evidence_added),
            "evidence_removed": len(evidence_removed),
        },
    }


def _find_previous_comparable_report(
    current_report: dict[str, Any],
    candidate_reports: list[dict[str, Any]],
) -> dict[str, Any] | None:
    current_signature = _comparison_artifact_signature(current_report)
    if not current_signature:
        return None
    current_id = int(current_report["id"])
    current_project_id = int(current_report.get("project", {}).get("id") or 0)
    current_workspace_id = int((current_report.get("workspace") or {}).get("id") or 0)
    previous_candidates = sorted(
        (
            report
            for report in candidate_reports
            if int(report["id"]) < current_id
            and int(report.get("project", {}).get("id") or 0) == current_project_id
            and int((report.get("workspace") or {}).get("id") or 0)
            == current_workspace_id
            and _comparison_signatures_match(
                _comparison_artifact_signature(report), current_signature
            )
        ),
        key=lambda report: int(report["id"]),
        reverse=True,
    )
    return previous_candidates[0] if previous_candidates else None


def _list_serialized_reports(*, include_evidence: bool) -> list[dict[str, Any]]:
    def operation():
        with SessionLocal() as session:
            reports = list_analysis_reports(session, include_evidence=include_evidence)
            return [
                _serialize_report(report, include_evidence=include_evidence)
                for report in reports
            ]

    return _run_with_schema_retry(operation)


def fetch_previous_comparable_report(
    report_id: int,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    previous_report_id: int | None = None,
) -> dict | None:
    current_report = fetch_analysis_report(
        report_id,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    if current_report is None:
        return None
    if previous_report_id is not None:
        return fetch_analysis_report(
            previous_report_id,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    serialized_reports = _list_serialized_reports(include_evidence=False)
    return _find_previous_comparable_report(current_report, serialized_reports)


def _redact_report_comparison(
    comparison: dict[str, Any],
    *,
    current_report: dict[str, Any],
    previous_report: dict[str, Any],
) -> dict[str, Any]:
    names: list[str] = []
    for report in (current_report, previous_report):
        for original_name in _report_artifact_names(report):
            if original_name not in names:
                names.append(original_name)
    pairs = _redaction_pairs(names)
    redacted = {
        **comparison,
        "previous_report": {
            **comparison["previous_report"],
            "top_risk": _redact_text_value(
                comparison["previous_report"].get("top_risk"),
                pairs,
            ),
        },
        "current_report": {
            **comparison["current_report"],
            "top_risk": _redact_text_value(
                comparison["current_report"].get("top_risk"),
                pairs,
            ),
        },
        "findings": {
            "added": [
                {
                    **item,
                    "title": _redact_text_value(item.get("title"), pairs),
                    "description": _redact_text_value(item.get("description"), pairs),
                }
                for item in comparison["findings"]["added"]
            ],
            "removed": [
                {
                    **item,
                    "title": _redact_text_value(item.get("title"), pairs),
                    "description": _redact_text_value(item.get("description"), pairs),
                }
                for item in comparison["findings"]["removed"]
            ],
            "severity_changed": [
                {
                    **item,
                    "title": _redact_text_value(item.get("title"), pairs),
                    "description": _redact_text_value(item.get("description"), pairs),
                }
                for item in comparison["findings"]["severity_changed"]
            ],
        },
        "evidence": {
            "added": [
                {
                    **item,
                    "finding_title": _redact_text_value(
                        item.get("finding_title"),
                        pairs,
                    ),
                    "source_ref": _redact_text_value(item.get("source_ref"), pairs),
                    "summary": _redact_text_value(item.get("summary"), pairs),
                }
                for item in comparison["evidence"]["added"]
            ],
            "removed": [
                {
                    **item,
                    "finding_title": _redact_text_value(
                        item.get("finding_title"),
                        pairs,
                    ),
                    "source_ref": _redact_text_value(item.get("source_ref"), pairs),
                    "summary": _redact_text_value(item.get("summary"), pairs),
                }
                for item in comparison["evidence"]["removed"]
            ],
        },
    }
    return redacted


def _build_previous_scan_diff(
    current_report: dict[str, Any],
    previous_report: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact diff summary against the previous scan of the same artifacts."""
    current_score = int(current_report.get("risk_score") or 0)
    previous_score = int(previous_report.get("risk_score") or 0)
    score_delta = current_score - previous_score
    if score_delta > 0:
        score_direction = "up"
    elif score_delta < 0:
        score_direction = "down"
    else:
        score_direction = "flat"
    return {
        "previous_report_id": previous_report["id"],
        "previous_created_at": previous_report["created_at"],
        "score_delta": score_delta,
        "score_direction": score_direction,
        "previous_severity": previous_report["severity"],
        "current_severity": current_report["severity"],
        "previous_recommendation": previous_report["recommendation"],
        "current_recommendation": current_report["recommendation"],
    }


def _attach_previous_scan_diffs(
    reports: list[dict[str, Any]],
    all_reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Annotate history rows with diff metadata for the previous scan of the same files."""
    previous_by_id: dict[int, dict[str, Any]] = {}
    latest_by_scope: dict[
        tuple[int, int],
        dict[tuple[ComparisonArtifact, ...], dict[str, Any]],
    ] = defaultdict(dict)

    for report in sorted(all_reports, key=lambda item: int(item["id"])):
        signature = _history_signature(report)
        if signature:
            scope = (signature[0], signature[1])
            scoped_reports = latest_by_scope[scope]
            previous = scoped_reports.get(signature[2])
            if previous is not None:
                previous_by_id[int(report["id"])] = previous
            scoped_reports[signature[2]] = report

    annotated: list[dict[str, Any]] = []
    for report in reports:
        previous = previous_by_id.get(int(report["id"]))
        if previous is None:
            annotated.append(report)
            continue
        annotated.append(
            {
                **report,
                "previous_scan_diff": _build_previous_scan_diff(report, previous),
            }
        )
    return annotated


def _scoped_identifier(*, kind: str, original_id: str, scope: str) -> str:
    """Return a per-report identifier safe for globally keyed persistence tables."""
    digest = hashlib.sha256(f"{scope}|{original_id}".encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{digest}"


def _scope_report_entities(
    assessment: RiskAssessment,
    findings: list[Finding] | None,
    evidence_items: list[EvidenceItem] | None,
) -> tuple[RiskAssessment, list[Finding] | None, list[EvidenceItem] | None]:
    """Namespace finding/evidence identifiers so repeated scans can persist safely."""
    if not findings and not evidence_items:
        return assessment, findings, evidence_items

    scope = secrets.token_hex(4)
    finding_id_map = {
        finding.finding_id: _scoped_identifier(
            kind="finding",
            original_id=finding.finding_id,
            scope=scope,
        )
        for finding in findings or []
    }
    evidence_id_map = {
        evidence_item.evidence_id: _scoped_identifier(
            kind="evidence",
            original_id=evidence_item.evidence_id,
            scope=scope,
        )
        for evidence_item in evidence_items or []
    }
    evidence_by_id = {
        evidence_item.evidence_id: evidence_item
        for evidence_item in evidence_items or []
    }
    evidence_claim_owner_by_id: dict[str, str] = {}
    for evidence_item in evidence_items or []:
        claimants = [
            finding
            for finding in findings or []
            if evidence_item.evidence_id in finding.evidence_refs
        ]
        if claimants:
            owner = max(
                claimants,
                key=lambda finding: _FINDING_SEVERITY_ORDER.get(
                    finding.severity,
                    0,
                ),
            )
            evidence_claim_owner_by_id[evidence_item.evidence_id] = owner.finding_id

    def _scoped_finding_updates(finding: Finding) -> dict[str, Any]:
        matched_evidence_items = [
            evidence_by_id[evidence_ref]
            for evidence_ref in finding.evidence_refs
            if evidence_ref in evidence_by_id
        ]
        updates: dict[str, Any] = {
            "finding_id": finding_id_map[finding.finding_id],
            "evidence_refs": [
                evidence_id_map[evidence_ref]
                for evidence_ref in finding.evidence_refs
                if evidence_ref in evidence_id_map
            ],
        }
        if matched_evidence_items:
            updates["evidence_classification"] = classify_finding_evidence(
                matched_evidence_items
            )
        elif finding.evidence_refs:
            updates["evidence_classification"] = "model_inferred"
        return updates

    def _scoped_evidence_finding_id(evidence_item: EvidenceItem) -> str:
        owner_id = evidence_item.finding_id
        if owner_id not in finding_id_map:
            owner_id = evidence_claim_owner_by_id.get(
                evidence_item.evidence_id, owner_id
            )
        return finding_id_map.get(owner_id, owner_id)

    scoped_findings = (
        [
            finding.model_copy(update=_scoped_finding_updates(finding))
            for finding in findings
        ]
        if findings is not None
        else None
    )
    scoped_evidence_items = (
        [
            evidence_item.model_copy(
                update={
                    "evidence_id": evidence_id_map[evidence_item.evidence_id],
                    "finding_id": _scoped_evidence_finding_id(evidence_item),
                }
            )
            for evidence_item in evidence_items
        ]
        if evidence_items is not None
        else None
    )
    scoped_assessment = assessment.model_copy(
        update={
            "top_risk_contributors": [
                evidence_id_map.get(evidence_id, evidence_id)
                for evidence_id in assessment.top_risk_contributors
            ],
            "contributors": [
                contributor.model_copy(
                    update={
                        "evidence_id": (
                            evidence_id_map.get(
                                contributor.evidence_id,
                                contributor.evidence_id,
                            )
                            if contributor.evidence_id is not None
                            else None
                        )
                    }
                )
                for contributor in assessment.contributors
            ],
        }
    )
    return scoped_assessment, scoped_findings, scoped_evidence_items


def _path_matches_contributor_source(evidence_artifact: str, source_file: str) -> bool:
    if not evidence_artifact or not source_file:
        return False
    return evidence_artifact == source_file


def _evidence_matches_contributor(
    evidence_item: EvidenceItem,
    contributor: RiskContributor,
) -> bool:
    source_matches = _path_matches_contributor_source(
        evidence_item.artifact,
        contributor.source_file,
    )
    resource_matches = evidence_item.resource == contributor.resource_id
    contributor_actions = {
        contributor.action,
        contributor.normalized_action,
    }
    operation_matches = evidence_item.operation in contributor_actions
    return source_matches and resource_matches and operation_matches


def _finding_matches_contributor(
    finding: Finding,
    contributor: RiskContributor,
) -> bool:
    finding_text = " ".join(
        (finding.title, finding.description, finding.explanation or "")
    )
    return (
        re.search(
            rf"(?<![A-Za-z0-9_./-]){re.escape(contributor.resource_id)}(?![A-Za-z0-9_./-])",
            finding_text,
        )
        is not None
    )


def _finding_with_evidence_ref(
    finding: Finding,
    evidence_id: str,
    evidence_by_id: dict[str, EvidenceItem],
) -> Finding:
    evidence_refs = list(finding.evidence_refs)
    if evidence_id not in evidence_refs:
        evidence_refs.append(evidence_id)
    matched_evidence_items = [
        evidence_by_id[evidence_ref]
        for evidence_ref in evidence_refs
        if evidence_ref in evidence_by_id
    ]
    updates: dict[str, Any] = {"evidence_refs": evidence_refs}
    if matched_evidence_items:
        updates["evidence_classification"] = classify_finding_evidence(
            matched_evidence_items
        )
    return finding.model_copy(update=updates)


def _has_linked_deterministic_evidence(
    finding: Finding,
    evidence_by_id: dict[str, EvidenceItem],
) -> bool:
    return any(
        (evidence_item := evidence_by_id.get(evidence_ref)) is not None
        and evidence_item.deterministic
        and evidence_item.determinism_level == "deterministic"
        for evidence_ref in finding.evidence_refs
    )


def _linked_deterministic_evidence_refs(
    finding: Finding,
    evidence_by_id: dict[str, EvidenceItem],
) -> list[str]:
    return [
        evidence_ref
        for evidence_ref in finding.evidence_refs
        if (evidence_item := evidence_by_id.get(evidence_ref)) is not None
        and evidence_item.deterministic
        and evidence_item.determinism_level == "deterministic"
    ]


def _top_risk_contributors_match_finding(
    contributor_refs: list[str],
    finding: Finding,
    evidence_by_id: dict[str, EvidenceItem],
) -> bool:
    deterministic_refs = set(
        _linked_deterministic_evidence_refs(finding, evidence_by_id)
    )
    return bool(contributor_refs) and set(contributor_refs).issubset(deterministic_refs)


def _downgraded_finding_without_deterministic_evidence(
    finding: Finding,
    evidence_by_id: dict[str, EvidenceItem],
) -> Finding:
    matched_evidence_items = [
        evidence_by_id[evidence_ref]
        for evidence_ref in finding.evidence_refs
        if evidence_ref in evidence_by_id
    ]
    downgraded_title = _VERDICT_PREFIX_PATTERN.sub("", finding.title).strip()
    if downgraded_title:
        downgraded_title = f"MEDIUM: {downgraded_title}"
    else:
        downgraded_title = f"MEDIUM: {finding.description}"
    downgrade_note = (
        "Evidence Law downgraded this finding to medium because it does not link to "
        "deterministic evidence."
    )
    return finding.model_copy(
        update={
            "title": downgraded_title,
            "explanation": downgrade_note,
            "guidance": [
                "Review the available linked evidence before deployment.",
                "Add deterministic evidence before treating this finding as severe.",
            ],
            "severity": "medium",
            "deterministic": False,
            "confidence": min(finding.confidence, 0.85),
            "evidence_classification": (
                classify_finding_evidence(matched_evidence_items)
                if matched_evidence_items
                else "model_inferred"
            ),
            "uncertainty_note": (
                finding.uncertainty_note
                or "Severity was downgraded because high/critical claims require linked deterministic evidence."
            ),
        }
    )


def _finding_with_supported_deterministic_evidence(
    finding: Finding,
    evidence_by_id: dict[str, EvidenceItem],
) -> Finding:
    matched_evidence_items = [
        evidence_by_id[evidence_ref]
        for evidence_ref in finding.evidence_refs
        if evidence_ref in evidence_by_id
    ]
    return finding.model_copy(
        update={
            "deterministic": True,
            "evidence_classification": classify_finding_evidence(
                matched_evidence_items
            ),
        }
    )


def _highest_severity_finding(findings: list[Finding]) -> Finding:
    return max(
        findings,
        key=lambda finding: _FINDING_SEVERITY_ORDER.get(finding.severity, 0),
    )


def _finding_risk_summary(finding: Finding) -> str:
    title = _VERDICT_PREFIX_PATTERN.sub("", finding.title).strip()
    title = title or finding.description
    description = finding.description.strip()
    if description and description != title:
        return f"{finding.severity.upper()}: {title} - {description}"
    return f"{finding.severity.upper()}: {title}"


def _recommendation_for_severity(severity: str) -> str:
    if severity in {"high", "critical"}:
        return "no-go"
    if severity == "medium":
        return "caution"
    return "go"


def _recommendation_matches_severity(recommendation: str, severity: str) -> bool:
    if severity in {"high", "critical"}:
        return recommendation == "no-go"
    if severity == "medium":
        return recommendation in {"go", "caution"}
    return recommendation == "go"


def _reconciled_score_for_severity(score: int, severity: str) -> int:
    return min(
        max(score, _SEVERITY_SCORE_FLOOR[severity]),
        _SEVERITY_SCORE_CEILING[severity],
    )


def _score_matches_severity(score: int, severity: str) -> bool:
    return _SEVERITY_SCORE_FLOOR[severity] <= score <= _SEVERITY_SCORE_CEILING[severity]


def _verdict_label(value: str | None) -> str | None:
    match = _VERDICT_PREFIX_PATTERN.match(str(value or ""))
    if match is None:
        return None
    return match.group(1).lower()


def _verdict_text_contradicts_metadata(
    value: str | None,
    severity: str,
    recommendation: str,
) -> bool:
    label = _verdict_label(value)
    if label is None:
        return False
    normalized_severity = str(severity).strip().lower()
    normalized_recommendation = str(recommendation).strip().lower()
    if normalized_severity not in _FINDING_SEVERITY_ORDER:
        return False
    if label in _FINDING_SEVERITY_ORDER:
        return label != normalized_severity
    if label in {"go", "caution", "no-go"}:
        return label != normalized_recommendation
    return False


def _sanitized_risk_summary(value: str | None, severity: str) -> str:
    summary = _VERDICT_PREFIX_PATTERN.sub("", str(value or "")).strip()
    if not summary:
        summary = "Evidence Law reconciled report verdict text."
    return f"{severity.upper()}: {summary}"


def _contributors_for_evidence_refs(
    contributors: list[RiskContributor],
    evidence_refs: list[str],
) -> list[RiskContributor]:
    supported_refs = set(evidence_refs)
    return [
        contributor
        for contributor in contributors
        if contributor.evidence_id in supported_refs
        or _is_neutral_parser_metadata_contributor(contributor)
    ]


def _is_neutral_parser_metadata_contributor(contributor: RiskContributor) -> bool:
    return (
        contributor.evidence_id is None
        and contributor.contribution <= 0
        and contributor.severity not in {"high", "critical"}
        and bool(contributor.metadata)
    )


def _apply_evidence_law_runtime_gate(
    assessment: RiskAssessment,
    findings: list[Finding] | None,
    evidence_items: list[EvidenceItem] | None,
) -> tuple[RiskAssessment, list[Finding] | None, list[str], str | None]:
    """Downgrade severe findings that lack linked deterministic evidence."""
    evidence_by_id = {
        evidence_item.evidence_id: evidence_item
        for evidence_item in evidence_items or []
    }
    updated_findings: list[Finding] = []
    downgraded_ids: list[str] = []
    for finding in findings or []:
        if finding.severity in {
            "high",
            "critical",
        } and _has_linked_deterministic_evidence(
            finding,
            evidence_by_id,
        ):
            updated_findings.append(
                _finding_with_supported_deterministic_evidence(
                    finding,
                    evidence_by_id,
                )
            )
            continue
        if finding.severity in {"high", "critical"}:
            updated_finding = _downgraded_finding_without_deterministic_evidence(
                finding,
                evidence_by_id,
            )
            updated_findings.append(updated_finding)
            downgraded_ids.append(finding.finding_id)
            continue
        updated_findings.append(finding)

    supported_severe_findings = [
        finding
        for finding in updated_findings
        if finding.severity in {"high", "critical"}
        and _has_linked_deterministic_evidence(finding, evidence_by_id)
    ]
    unsupported_report_severity = (
        assessment.severity in {"high", "critical"} and not supported_severe_findings
    )
    top_supported_finding = (
        _highest_severity_finding(supported_severe_findings)
        if supported_severe_findings
        else None
    )
    overclaimed_report_severity = (
        assessment.severity in {"high", "critical"}
        and top_supported_finding is not None
        and _FINDING_SEVERITY_ORDER[assessment.severity]
        > _FINDING_SEVERITY_ORDER[top_supported_finding.severity]
    )
    underclaimed_report_severity = (
        top_supported_finding is not None
        and _FINDING_SEVERITY_ORDER[assessment.severity]
        < _FINDING_SEVERITY_ORDER[top_supported_finding.severity]
    )
    inconsistent_supported_report_metadata = (
        top_supported_finding is not None
        and assessment.severity in {"high", "critical"}
        and (
            not _recommendation_matches_severity(
                assessment.recommendation,
                assessment.severity,
            )
            or not _score_matches_severity(assessment.score, assessment.severity)
        )
    )
    inconsistent_top_risk_contributors = (
        top_supported_finding is not None
        and assessment.severity in {"high", "critical"}
        and not _top_risk_contributors_match_finding(
            assessment.top_risk_contributors,
            top_supported_finding,
            evidence_by_id,
        )
    )
    expected_report_recommendation = _recommendation_for_severity(assessment.severity)
    inconsistent_report_recommendation = not _recommendation_matches_severity(
        assessment.recommendation,
        assessment.severity,
    )
    inconsistent_report_score = not _score_matches_severity(
        assessment.score,
        assessment.severity,
    )
    stale_top_risk_verdict_text = _verdict_text_contradicts_metadata(
        assessment.top_risk,
        assessment.severity,
        expected_report_recommendation
        if inconsistent_report_recommendation
        else assessment.recommendation,
    )

    if (
        not downgraded_ids
        and not unsupported_report_severity
        and not overclaimed_report_severity
        and not underclaimed_report_severity
        and not inconsistent_supported_report_metadata
        and not inconsistent_top_risk_contributors
        and not inconsistent_report_recommendation
        and not inconsistent_report_score
        and not stale_top_risk_verdict_text
    ):
        return (
            assessment,
            updated_findings if findings is not None else findings,
            [],
            None,
        )

    warnings: list[str] = []
    report_adjustment_warning: str | None = None
    if downgraded_ids:
        warnings.append(
            "Evidence Law downgraded high/critical findings without linked deterministic "
            f"evidence: {', '.join(downgraded_ids)}."
        )
    if unsupported_report_severity:
        report_adjustment_warning = (
            "Evidence Law downgraded a high/critical report verdict because no "
            "supported severe finding had linked deterministic evidence."
        )
        warnings.append(report_adjustment_warning)
    if overclaimed_report_severity and top_supported_finding is not None:
        report_adjustment_warning = (
            "Evidence Law downgraded a high/critical report verdict to match the "
            f"highest linked deterministic finding severity: {top_supported_finding.severity}."
        )
        warnings.append(report_adjustment_warning)
    if underclaimed_report_severity and top_supported_finding is not None:
        report_adjustment_warning = (
            "Evidence Law promoted report verdict to match the highest linked "
            f"deterministic finding severity: {top_supported_finding.severity}."
        )
        warnings.append(report_adjustment_warning)
    if stale_top_risk_verdict_text:
        stale_text_warning = (
            "Evidence Law refreshed report verdict text to match reconciled severity "
            "metadata."
        )
        if report_adjustment_warning is None:
            report_adjustment_warning = stale_text_warning
        warnings.append(stale_text_warning)
    if inconsistent_report_recommendation:
        recommendation_warning = (
            "Evidence Law reconciled report recommendation to match severity metadata."
        )
        if report_adjustment_warning is None:
            report_adjustment_warning = recommendation_warning
        warnings.append(recommendation_warning)
    if inconsistent_report_score:
        score_warning = (
            "Evidence Law reconciled report score to match severity metadata."
        )
        if report_adjustment_warning is None:
            report_adjustment_warning = score_warning
        warnings.append(score_warning)
    assessment_updates: dict[str, Any] = {
        "warnings": list(dict.fromkeys([*assessment.warnings, *warnings]))
    }
    if unsupported_report_severity:
        downgraded_target = (
            f"unsupported severe finding(s) {', '.join(downgraded_ids)}"
            if downgraded_ids
            else "unsupported severe report verdict"
        )
        assessment_updates.update(
            {
                "score": _reconciled_score_for_severity(assessment.score, "medium"),
                "severity": "medium",
                "recommendation": "caution",
                "top_risk": (
                    f"MEDIUM: Evidence Law downgraded {downgraded_target} "
                    "pending deterministic evidence."
                ),
                "top_risk_contributors": [],
                "contributors": [],
            }
        )
    elif top_supported_finding is not None and (
        downgraded_ids
        or overclaimed_report_severity
        or underclaimed_report_severity
        or inconsistent_supported_report_metadata
        or inconsistent_top_risk_contributors
        or stale_top_risk_verdict_text
    ):
        supported_contributors: list[str] = []
        for evidence_ref in _linked_deterministic_evidence_refs(
            top_supported_finding,
            evidence_by_id,
        ):
            if evidence_ref not in supported_contributors:
                supported_contributors.append(evidence_ref)
        assessment_updates.update(
            {
                "score": _reconciled_score_for_severity(
                    assessment.score,
                    top_supported_finding.severity,
                ),
                "severity": top_supported_finding.severity
                if (overclaimed_report_severity or underclaimed_report_severity)
                else assessment.severity,
                "recommendation": _recommendation_for_severity(
                    top_supported_finding.severity
                    if (overclaimed_report_severity or underclaimed_report_severity)
                    else assessment.severity
                ),
                "top_risk": _finding_risk_summary(top_supported_finding),
                "top_risk_contributors": supported_contributors,
                "contributors": _contributors_for_evidence_refs(
                    list(assessment.contributors),
                    supported_contributors,
                ),
            }
        )
    elif downgraded_ids:
        assessment_updates.update(
            {
                "score": _reconciled_score_for_severity(assessment.score, "medium"),
                "severity": "medium",
                "recommendation": "caution",
                "top_risk": (
                    "MEDIUM: Evidence Law downgraded unsupported severe finding(s) "
                    f"{', '.join(downgraded_ids)} pending deterministic evidence."
                ),
                "top_risk_contributors": [],
                "contributors": [],
            }
        )
    elif stale_top_risk_verdict_text:
        assessment_updates.update(
            {
                "top_risk": _sanitized_risk_summary(
                    assessment.top_risk,
                    assessment.severity,
                ),
                "score": _reconciled_score_for_severity(
                    assessment.score,
                    assessment.severity,
                ),
                "recommendation": expected_report_recommendation
                if inconsistent_report_recommendation
                else assessment.recommendation,
                "top_risk_contributors": []
                if stale_top_risk_verdict_text and not assessment.top_risk_contributors
                else assessment.top_risk_contributors,
                "contributors": assessment.contributors,
            }
        )
    elif inconsistent_report_recommendation or inconsistent_report_score:
        assessment_updates.update(
            {
                "score": _reconciled_score_for_severity(
                    assessment.score,
                    assessment.severity,
                ),
                "recommendation": expected_report_recommendation
                if inconsistent_report_recommendation
                else assessment.recommendation,
            }
        )
    return (
        assessment.model_copy(update=assessment_updates),
        updated_findings if findings is not None else findings,
        downgraded_ids,
        report_adjustment_warning,
    )


def _narrative_with_evidence_law_runtime_gate(
    narrative: NarrativeResult,
    assessment: RiskAssessment,
    downgraded_ids: list[str],
    report_adjustment_warning: str | None,
    findings: list[Finding] | None,
) -> NarrativeResult:
    stale_narrative_verdict_text = any(
        _verdict_text_contradicts_metadata(
            value,
            assessment.severity,
            assessment.recommendation,
        )
        for value in (narrative.opening_sentence, narrative.explanation)
    )
    if (
        not downgraded_ids
        and report_adjustment_warning is None
        and not stale_narrative_verdict_text
    ):
        return narrative
    remaining_severe = any(
        finding.severity in {"high", "critical"} for finding in findings or []
    )
    warnings: list[str] = []
    if downgraded_ids:
        warnings.append(
            "Evidence Law downgraded unsupported severe finding(s) pending deterministic "
            f"evidence: {', '.join(downgraded_ids)}."
        )
    if report_adjustment_warning is not None:
        warnings.append(report_adjustment_warning)
    if stale_narrative_verdict_text:
        warnings.append(
            "Evidence Law refreshed report narrative to match reconciled severity "
            "metadata."
        )
    if not warnings:
        warnings.append(
            report_adjustment_warning
            or "Evidence Law reconciled the report verdict to linked deterministic severe evidence."
        )
    warning = " ".join(warnings)
    remaining_severe_findings = [
        finding
        for finding in findings or []
        if finding.severity in {"high", "critical"}
    ]
    if remaining_severe:
        top_remaining_finding = _highest_severity_finding(remaining_severe_findings)
        opening_sentence = (
            "NO-GO: deterministic severe risk remains; unsupported or inconsistent "
            "severe claim(s) were reconciled."
        )
        explanation = (
            "Deterministic severe risk remains: "
            f"{_finding_risk_summary(top_remaining_finding)}. {warning}"
        )
    else:
        opening_sentence = (
            "CAUTION: severe risk claims need deterministic evidence."
            if assessment.recommendation == "caution"
            else f"{assessment.recommendation.upper()}: report verdict matches available deterministic evidence."
        )
        explanation = warning
    return narrative.model_copy(
        update={
            "opening_sentence": opening_sentence,
            "explanation": explanation,
            "warnings": list(dict.fromkeys([*narrative.warnings, *warnings])),
        }
    )


def _repair_assessment_evidence_links(
    assessment: RiskAssessment,
    findings: list[Finding] | None,
    evidence_items: list[EvidenceItem] | None,
) -> tuple[RiskAssessment, list[Finding] | None]:
    """Repair stale assessment evidence IDs only when evidence has one clear owner."""
    if not findings or not evidence_items:
        return assessment, findings

    evidence_by_id = {
        evidence_item.evidence_id: evidence_item for evidence_item in evidence_items
    }
    findings_by_id = {finding.finding_id: finding for finding in findings}
    evidence_replacements: dict[str, str] = {}
    updated_contributors: list[RiskContributor] = []

    for contributor in assessment.contributors:
        replacement_evidence_id: str | None = None
        has_stale_evidence_id = (
            contributor.evidence_id is not None
            and contributor.evidence_id not in evidence_by_id
        )
        if has_stale_evidence_id:
            matching_evidence_items = [
                evidence_item
                for evidence_item in evidence_items
                if _evidence_matches_contributor(evidence_item, contributor)
            ]
            matching_findings = [
                finding
                for finding in findings_by_id.values()
                if _finding_matches_contributor(finding, contributor)
            ]
            if len(matching_evidence_items) == 1 and len(matching_findings) == 1:
                evidence_item = matching_evidence_items[0]
                finding = matching_findings[0]
                findings_by_id[finding.finding_id] = _finding_with_evidence_ref(
                    finding,
                    evidence_item.evidence_id,
                    evidence_by_id,
                )
                replacement_evidence_id = evidence_item.evidence_id
                evidence_replacements[contributor.evidence_id] = replacement_evidence_id
        updated_contributors.append(
            contributor.model_copy(update={"evidence_id": replacement_evidence_id})
            if replacement_evidence_id is not None or has_stale_evidence_id
            else contributor
        )

    findings_changed = any(
        findings_by_id[finding.finding_id].evidence_refs != finding.evidence_refs
        for finding in findings
    )
    updated_top_risk_contributors: list[str] = []
    for evidence_id in assessment.top_risk_contributors:
        replacement_evidence_id = evidence_replacements.get(evidence_id, evidence_id)
        if replacement_evidence_id in evidence_by_id:
            updated_top_risk_contributors.append(replacement_evidence_id)
    assessment_changed = (
        updated_contributors != list(assessment.contributors)
        or updated_top_risk_contributors != assessment.top_risk_contributors
    )

    if not assessment_changed and not findings_changed:
        return assessment, findings

    return (
        assessment.model_copy(
            update={
                "top_risk_contributors": updated_top_risk_contributors,
                "contributors": updated_contributors,
            }
        ),
        [findings_by_id[finding.finding_id] for finding in findings],
    )


def _evidence_items_with_report_context(
    evidence_items: list[EvidenceItem] | None,
    *,
    project: Any,
    workspace: Any | None,
    submission_manifest: SubmissionManifest,
) -> list[EvidenceItem] | None:
    if evidence_items is None:
        return None
    redaction_status_by_artifact = {
        item.name: normalize_manifest_redaction_status(item.redaction_status)
        for item in submission_manifest.items
    }
    return [
        evidence_item.model_copy(
            update={
                "project_id": project.id,
                "project_key": project.project_key,
                "workspace_id": workspace.id if workspace is not None else None,
                "workspace_key": (
                    workspace.workspace_key if workspace is not None else None
                ),
                "source_kind": evidence_item.source_type,
                "determinism_level": evidence_item.determinism_level,
                "redaction_status": redaction_status_by_artifact.get(
                    evidence_item.artifact,
                    evidence_item.redaction_status,
                ),
            }
        )
        for evidence_item in evidence_items
    ]


def normalize_report_schema_version(schema_version: object | None) -> str:
    """Return a stable schema version for stored or in-memory reports."""
    if schema_version is None:
        normalized = ""
    elif isinstance(schema_version, str):
        normalized = schema_version.strip()
    else:
        raise ReportSchemaVersionError(
            "invalid_report_schema_version",
            f"Unsupported report schema version: {schema_version!r}",
            status_code=400,
        )
    if not normalized:
        return LEGACY_REPORT_SCHEMA_VERSION
    if normalized.startswith("v") and normalized[1:].isdigit():
        major = int(normalized[1:])
        if major >= 1:
            return f"v{major}"
    raise ReportSchemaVersionError(
        "invalid_report_schema_version",
        f"Unsupported report schema version: {normalized}",
        status_code=400,
    )


def readable_report_schema_version(schema_version: object | None) -> str:
    normalized = normalize_report_schema_version(schema_version)
    if not can_read_report_schema(REPORT_SCHEMA_VERSION, normalized):
        raise ReportSchemaVersionError(
            "unsupported_report_schema_version",
            (
                f"Report schema version {normalized} is newer than reader schema "
                f"{REPORT_SCHEMA_VERSION}."
            ),
        )
    return normalized


def _report_schema_major(schema_version: str) -> int:
    if not schema_version.startswith("v") or not schema_version[1:].isdigit():
        raise ValueError(f"Unsupported report schema version: {schema_version}")
    return int(schema_version[1:])


def can_read_report_schema(
    reader_schema_version: str, report_schema_version: str | None
) -> bool:
    """Return whether a reader contract can consume the stored report schema."""
    try:
        return _report_schema_major(reader_schema_version) >= _report_schema_major(
            normalize_report_schema_version(report_schema_version)
        )
    except ValueError:
        return False


def _load_submission_manifest_payload(
    raw_value: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        decoded = json.loads(raw_value or "{}")
    except json.JSONDecodeError:
        return (
            None,
            "Submission manifest metadata was unavailable because persisted JSON was malformed.",
        )
    if not isinstance(decoded, dict):
        return (
            None,
            "Submission manifest metadata was unavailable because persisted JSON had an unexpected shape.",
        )
    try:
        manifest = SubmissionManifest.model_validate(decoded)
    except ValidationError:
        return (
            None,
            "Submission manifest metadata was unavailable because persisted JSON had an unexpected shape.",
        )
    return normalize_submission_manifest_payload(manifest.model_dump(mode="json")), None


def _submission_manifest_fallback_items(
    manifest: SubmissionManifest,
) -> list[dict[str, Any]]:
    actor = _normalize_audit_actor(
        (manifest.provenance or {}).get("actor"),
        (manifest.provenance or {}).get("source_interface"),
    )
    return [
        {
            "name": item.name,
            "tool": item.tool,
            "status": item.status,
            "intake_status": item.intake_status,
            "parse_status": item.parse_status,
            "partial": item.partial,
            "redaction_status": normalize_manifest_redaction_status(
                item.redaction_status
            ),
            "actor": actor,
        }
        for item in manifest.items
    ]


def _load_submission_manifest_fallback_payload(
    raw_value: str | None,
) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(raw_value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    fallback_items: list[dict[str, Any]] = []
    for item in decoded:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        status = str(item.get("status") or "").strip()
        if not name or not status:
            continue
        fallback_item = {
            "name": name,
            "tool": str(item.get("tool") or "unknown"),
            "status": status,
            "intake_status": str(item.get("intake_status") or "unknown"),
            "parse_status": (
                str(item["parse_status"])
                if item.get("parse_status") is not None
                else None
            ),
            "partial": bool(item.get("partial", False)),
        }
        if "redaction_status" in item:
            fallback_item["redaction_status"] = normalize_manifest_redaction_status(
                item.get("redaction_status")
            )
        if "actor" in item:
            fallback_item["actor"] = _normalize_audit_actor(
                item.get("actor"),
                None,
            )
        fallback_items.append(fallback_item)
    return fallback_items


def _actor_from_submission_manifest_fallback(
    fallback_items: list[dict[str, Any]] | None,
) -> str | None:
    for item in fallback_items or []:
        if not isinstance(item, dict):
            continue
        actor = item.get("actor")
        if actor:
            return str(actor)
    return None


def _load_context_completeness_payload(
    raw_value: str | None,
) -> tuple[dict, str | None]:
    if raw_value is None or not str(raw_value).strip():
        return _unavailable_context_completeness(), _CONTEXT_JSON_INVALID_WARNING
    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError:
        return _unavailable_context_completeness(), _CONTEXT_JSON_MALFORMED_WARNING
    if not isinstance(decoded, dict):
        return _unavailable_context_completeness(), _CONTEXT_JSON_SHAPE_WARNING
    decoded = _upgrade_legacy_context_completeness_payload(decoded)
    if decoded is None:
        return _unavailable_context_completeness(), _CONTEXT_JSON_INCOMPLETE_WARNING
    try:
        return (
            ContextCompleteness.model_validate(decoded).model_dump(mode="json"),
            None,
        )
    except (TypeError, ValueError, ValidationError):
        return _unavailable_context_completeness(), _CONTEXT_JSON_INVALID_WARNING


def _context_confidence_level_from_score(context_score: float) -> str:
    if context_score >= 0.85:
        return "high"
    if context_score >= 0.7:
        return "medium"
    return "low"


def _context_float_value(
    decoded: dict,
    key: str,
    *,
    missing_default: float,
    invalid_default: float = 0.0,
) -> float:
    if key not in decoded:
        return missing_default
    try:
        value = float(decoded.get(key))
    except (TypeError, ValueError):
        return invalid_default
    if not math.isfinite(value):
        return invalid_default
    return max(0.0, min(value, 1.0))


def _context_int_value(decoded: dict, key: str) -> int:
    try:
        value = int(decoded.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def _context_todo_items(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item).strip()]


def _normalize_context_completeness_payload(decoded: dict) -> dict:
    context_score = _context_float_value(decoded, "context_score", missing_default=1.0)
    parser_success_rate = _context_float_value(
        decoded, "parser_success_rate", missing_default=1.0
    )
    evidence_success_rate = _context_float_value(
        decoded, "evidence_success_rate", missing_default=1.0
    )
    incident_index_size = _context_int_value(decoded, "incident_index_size")
    topology_freshness_days = decoded.get("topology_freshness_days")
    if topology_freshness_days is None:
        topology_gap = "missing"
    else:
        try:
            topology_freshness_days = int(topology_freshness_days)
            topology_gap = (
                "stale" if topology_freshness_days > STALE_AFTER_DAYS else None
            )
        except (TypeError, ValueError):
            topology_freshness_days = None
            topology_gap = "missing"

    normalized = dict(decoded)
    normalized["context_score"] = context_score
    normalized["parser_success_rate"] = parser_success_rate
    normalized["evidence_success_rate"] = evidence_success_rate
    normalized["incident_index_size"] = incident_index_size
    normalized["topology_freshness_days"] = topology_freshness_days

    insufficient_context = context_score < 0.7
    normalized["insufficient_context"] = insufficient_context
    normalized["confidence_level"] = (
        "low"
        if insufficient_context
        else _context_confidence_level_from_score(context_score)
    )

    todos = _context_todo_items(normalized.get("context_todos"))
    if topology_gap == "missing" and not any(
        "topology" in item.lower() for item in todos
    ):
        todos.append("Import or refresh topology context for this project/workspace.")
    if topology_gap == "stale" and not any(
        "topology" in item.lower() for item in todos
    ):
        todos.append("Refresh stale topology context for this project/workspace.")
    if incident_index_size == 0 and not any(
        "incident" in item.lower() for item in todos
    ):
        todos.append("Import relevant incident history for this project/workspace.")
    if parser_success_rate < 1.0 and not any(
        "parser" in item.lower() for item in todos
    ):
        todos.append("Review parser errors and resubmit supported artifacts.")
    if evidence_success_rate < 1.0 and not any(
        "evidence" in item.lower() for item in todos
    ):
        todos.append("Review evidence extraction gaps for supported artifacts.")
    if insufficient_context and not todos:
        todos.append(_CONTEXT_UNAVAILABLE_TODO)
    normalized["context_todos"] = todos

    uncertainty = str(normalized.get("uncertainty") or "").strip()
    if insufficient_context and not uncertainty:
        uncertainty = (
            "Insufficient context: persisted context metadata was normalized "
            "because stored values were internally inconsistent."
        )
    normalized["uncertainty"] = uncertainty or None
    return normalized


def _upgrade_legacy_context_completeness_payload(decoded: dict) -> dict | None:
    required_keys = set(ContextCompleteness.model_fields)
    if required_keys.issubset(decoded):
        return _normalize_context_completeness_payload(decoded)
    if not _LEGACY_CONTEXT_CORE_FIELDS.issubset(decoded):
        return None

    try:
        legacy_context_score = float(decoded["context_score"])
    except (TypeError, ValueError):
        return None
    if not math.isfinite(legacy_context_score):
        return None

    upgraded = dict(decoded)
    upgraded.setdefault("evidence_success_rate", 1.0)
    upgraded.setdefault("uncertainty", None)
    upgraded.setdefault("context_todos", [])
    upgraded.setdefault("insufficient_context", False)
    return _normalize_context_completeness_payload(upgraded)


def _unavailable_context_completeness() -> dict:
    return ContextCompleteness(
        incident_index_size=0,
        evidence_success_rate=0.0,
        parser_success_rate=0.0,
        parser_success_by_tool={},
        context_score=0.0,
        confidence_level="low",
        uncertainty=_CONTEXT_UNAVAILABLE_UNCERTAINTY,
        context_todos=[_CONTEXT_UNAVAILABLE_TODO],
        insufficient_context=True,
    ).model_dump(mode="json")


def _load_report_confidence(value: Any) -> tuple[float, str | None]:
    if value is None:
        return 0.0, _CONFIDENCE_INVALID_WARNING
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0, _CONFIDENCE_INVALID_WARNING
    if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
        return 0.0, _CONFIDENCE_INVALID_WARNING
    return confidence, None


def _clamp_confidence_to_context(
    confidence: float, context_completeness: dict
) -> float:
    if not context_completeness.get("insufficient_context"):
        return confidence
    try:
        context_score = float(context_completeness.get("context_score", 0.0))
    except (TypeError, ValueError):
        context_score = 0.0
    if not math.isfinite(context_score):
        context_score = 0.0
    return round(min(confidence, max(0.0, min(context_score, 1.0))), 2)


def _serialize_report(report, *, include_evidence: bool = True) -> dict:
    created_at = report.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    warnings = json.loads(report.warnings_json or "[]")
    submission_manifest, manifest_warning = _load_submission_manifest_payload(
        getattr(report, "submission_manifest_json", None)
    )
    submission_manifest_fallback = _load_submission_manifest_fallback_payload(
        getattr(report, "submission_manifest_fallback_json", None)
    )
    manifest_provenance = (
        dict(submission_manifest.get("provenance") or {})
        if isinstance(submission_manifest, dict)
        else {}
    )
    source_interface = report.source_interface or manifest_provenance.get(
        "source_interface"
    )
    trigger_type = report.trigger_type or manifest_provenance.get("trigger_type")
    trigger_id = report.trigger_id or manifest_provenance.get("trigger_id")
    actor = _normalize_audit_actor(
        manifest_provenance.get("actor")
        or _actor_from_submission_manifest_fallback(submission_manifest_fallback),
        source_interface,
    )
    persisted_at = created_at.isoformat()
    audit = {
        "files_analyzed": json.loads(report.analyzed_files_json or "[]"),
        "llm_provider": report.llm_provider,
        "llm_model": report.llm_model,
        "llm_local_mode": report.llm_local_mode == "true"
        if report.llm_local_mode is not None
        else None,
        "source_interface": source_interface,
        "trigger_type": trigger_type,
        "trigger_id": trigger_id,
        "actor": actor,
        "persisted_at": persisted_at,
        "redaction_status": _report_redaction_status(
            submission_manifest,
            submission_manifest_fallback,
        ),
        "redaction": _report_redaction_metadata(
            submission_manifest,
            submission_manifest_fallback,
        ),
        "delivery": _delivery_metadata(
            source_interface=source_interface,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            report_id=int(report.id),
        ),
    }
    if manifest_warning is not None and manifest_warning not in warnings:
        warnings.append(manifest_warning)
    confidence, confidence_warning = _load_report_confidence(
        report.risk_assessment.confidence
        if report.risk_assessment is not None
        else None
    )
    if confidence_warning is not None and confidence_warning not in warnings:
        warnings.append(confidence_warning)
    context_completeness, context_warning = _load_context_completeness_payload(
        report.risk_assessment.context_completeness_json
        if report.risk_assessment is not None
        else None
    )
    if context_warning is not None and context_warning not in warnings:
        warnings.append(context_warning)
    confidence = _clamp_confidence_to_context(confidence, context_completeness)
    evidence_items: list[dict[str, Any]] = []
    if include_evidence:
        seen_evidence_ids: set[str] = set()
        for finding in report.findings:
            for evidence_item in finding.evidence_items:
                if evidence_item.evidence_id in seen_evidence_ids:
                    continue
                seen_evidence_ids.add(evidence_item.evidence_id)
                evidence_items.append(
                    {
                        "evidence_id": evidence_item.evidence_id,
                        "analysis_id": evidence_item.analysis_id,
                        "finding_id": evidence_item.finding_id,
                        "source_type": evidence_item.source_type,
                        "source_ref": evidence_item.source_ref,
                        "artifact": evidence_item.artifact,
                        "location": evidence_item.location,
                        "resource": evidence_item.resource,
                        "operation": evidence_item.operation,
                        "project_id": evidence_item.project_id,
                        "project_key": evidence_item.project_key,
                        "workspace_id": evidence_item.workspace_id,
                        "workspace_key": evidence_item.workspace_key,
                        "source_kind": evidence_item.source_kind,
                        "determinism_level": evidence_item.determinism_level,
                        "redaction_status": evidence_item.redaction_status,
                        "summary": evidence_item.summary,
                        "severity_hint": evidence_item.severity_hint,
                        "deterministic": evidence_item.deterministic,
                        "confidence": evidence_item.confidence,
                        "related_change_ids": json.loads(
                            evidence_item.related_change_ids_json or "[]"
                        ),
                    }
                )
    narrative_available = _has_visible_narrative_text(
        report.narrative_opening or ""
    ) or _has_visible_narrative_text(report.narrative_explanation or "")
    stored_failure_notice = getattr(report, "narrative_failure_notice", None)
    narrative_failure_notice = (
        stored_failure_notice
        if stored_failure_notice is not None
        else _extract_narrative_failure_notice(warnings)
    )
    narrative_source = _known_narrative_source(report.narrative_source)
    stored_narrative_degraded = getattr(report, "narrative_degraded", None)
    narrative_degraded = _narrative_degraded_from_state(
        explicit_degraded=stored_narrative_degraded,
        narrative_source=narrative_source,
        failure_notice=narrative_failure_notice,
        narrative_available=narrative_available,
    )
    payload = {
        "id": report.id,
        "project": build_project_payload(
            {
                "id": report.project.id,
                "project_key": report.project.project_key,
                "display_name": report.project.display_name,
                "description": report.project.description,
                "repository_url": report.project.repository_url,
                "default_branch": report.project.default_branch,
                "is_default": report.project.is_default,
                "created_at": report.project.created_at.isoformat(),
                "updated_at": report.project.updated_at.isoformat(),
            }
        ),
        "workspace": (
            build_workspace_payload(
                {
                    "id": report.workspace.id,
                    "project_id": report.workspace.project_id,
                    "project_key": report.project.project_key,
                    "workspace_key": report.workspace.workspace_key,
                    "display_name": report.workspace.display_name,
                    "description": report.workspace.description,
                    "environment": report.workspace.environment,
                    "created_at": report.workspace.created_at.isoformat(),
                    "updated_at": report.workspace.updated_at.isoformat(),
                }
            )
            if report.workspace is not None
            else None
        ),
        "risk_score": report.risk_score,
        "severity": report.severity,
        "recommendation": report.recommendation,
        "top_risk": report.top_risk,
        "report_schema_version": readable_report_schema_version(
            getattr(report, "report_schema_version", None)
        ),
        "top_risk_contributors": json.loads(
            report.risk_assessment.top_risk_contributors_json
            if report.risk_assessment is not None
            else "[]"
        ),
        "confidence": confidence,
        "context_completeness": context_completeness,
        "blast_radius": (
            json.loads(report.blast_radius_json or "{}")
            or _default_blast_radius_payload()
        ),
        "rollback_plan": (
            json.loads(getattr(report, "rollback_plan_json", "") or "{}")
            or _default_rollback_plan_payload()
        ),
        "parse_summary": report.parse_summary,
        "submission_manifest": submission_manifest,
        "submission_manifest_fallback": submission_manifest_fallback,
        "narrative_opening": report.narrative_opening,
        "narrative_explanation": report.narrative_explanation,
        "narrative_available": narrative_available,
        "narrative_degraded": narrative_degraded,
        "narrative_failure_notice": narrative_failure_notice,
        "assessment_source": report.assessment_source,
        "narrative_source": narrative_source,
        "narrative_provider": report.llm_provider,
        "narrative_model": report.llm_model,
        "narrative_local_mode": report.llm_local_mode == "true"
        if report.llm_local_mode is not None
        else None,
        "skills_applied": json.loads(report.narrative_skills_json or "[]"),
        "created_at": persisted_at,
        "warnings": warnings,
        "findings": [
            {
                "finding_id": finding.finding_id,
                "analysis_id": finding.analysis_id,
                "title": finding.title,
                "description": finding.description,
                "explanation": finding.explanation or finding.description,
                "guidance": json.loads(finding.guidance_json or "[]"),
                "severity": finding.severity,
                "category": finding.category,
                "deterministic": finding.deterministic,
                "confidence": finding.confidence,
                "uncertainty_note": finding.uncertainty_note,
                "evidence_classification": finding.evidence_classification,
                "evidence_refs": json.loads(finding.evidence_refs_json or "[]"),
                "skill_id": finding.skill_id,
            }
            for finding in report.findings
        ],
        "evidence_items": evidence_items,
        "contributors": json.loads(report.contributors_json or "[]"),
        "dashboard_display_duration_seconds": report.dashboard_display_duration_seconds,
        "share_password_hash": getattr(report, "share_password_hash", None),
        "share_password_salt": getattr(report, "share_password_salt", None),
        "share_redact_filenames": bool(
            getattr(report, "share_redact_filenames", False)
        ),
        "audit": audit,
    }
    payload["confidence_ledger"] = build_confidence_ledger(
        payload,
        evidence_detail_available=include_evidence,
    )
    return payload


def persist_analysis_report(
    parse_batch: ParseBatchResult,
    assessment: RiskAssessment,
    narrative: NarrativeResult,
    blast_radius: BlastRadiusResult | None = None,
    rollback_plan: RollbackPlan | None = None,
    findings: list[Finding] | None = None,
    evidence_items: list[EvidenceItem] | None = None,
    artifact_snapshots: dict[str, bytes | None] | None = None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    audit_context: dict[str, Any] | None = None,
    submitted_artifacts: list[tuple[str, bytes | None]] | None = None,
) -> dict:
    """Persist the completed analysis before the UI treats it as final."""
    assessment = apply_context_uncertainty(assessment)
    assessment, findings = _repair_assessment_evidence_links(
        assessment,
        findings,
        evidence_items,
    )
    (
        assessment,
        findings,
        downgraded_finding_ids,
        report_adjustment_warning,
    ) = _apply_evidence_law_runtime_gate(
        assessment,
        findings,
        evidence_items,
    )
    narrative = _narrative_with_evidence_law_runtime_gate(
        narrative,
        assessment,
        downgraded_finding_ids,
        report_adjustment_warning,
        findings,
    )
    assessment, findings, evidence_items = _scope_report_entities(
        assessment,
        findings,
        evidence_items,
    )
    audit = _build_audit_metadata(parse_batch, audit_context=audit_context)
    audit["llm_provider"] = narrative.provider or audit["llm_provider"]
    audit["llm_model"] = narrative.model or audit["llm_model"]
    if narrative.local_mode is not None:
        audit["llm_local_mode"] = narrative.local_mode
    resolved_project_id, resolved_workspace_id = _resolve_report_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    resolved_project = resolve_project_reference(
        project_id=resolved_project_id,
    )
    resolved_workspace = (
        resolve_workspace_reference(
            project_id=resolved_project.id,
            workspace_id=resolved_workspace_id,
        )
        if resolved_workspace_id is not None
        else None
    )
    fallback_snapshots = {
        file_result.file_name: None for file_result in parse_batch.files
    }
    if submitted_artifacts is not None:
        submission_files = list(submitted_artifacts)
        pending_analysis = None
        manifest_warnings: list[str] = []
    elif artifact_snapshots is not None:
        submission_files = list(artifact_snapshots.items())
        pending_analysis = None
        manifest_warnings = [_SUBMISSION_MANIFEST_INFERRED_WARNING]
    else:
        submission_files = list(fallback_snapshots.items())
        pending_analysis = _pending_analysis_from_parse_batch(parse_batch)
        manifest_warnings = [_SUBMISSION_MANIFEST_INFERRED_WARNING]
    submission_manifest = build_submission_manifest(
        submission_files,
        pending_analysis=pending_analysis,
        parse_batch=parse_batch,
        audit_context={
            **(audit_context or {}),
            "source_interface": audit["source_interface"],
            "trigger_type": audit["trigger_type"],
            "trigger_id": audit["trigger_id"],
            "actor": audit["actor"],
            "project_id": resolved_project.id,
            "project_key": resolved_project.project_key,
            "workspace_id": resolved_workspace.id if resolved_workspace else None,
            "workspace_key": (
                resolved_workspace.workspace_key if resolved_workspace else None
            ),
        },
    )
    evidence_items = _evidence_items_with_report_context(
        evidence_items,
        project=resolved_project,
        workspace=resolved_workspace,
        submission_manifest=submission_manifest,
    )
    snapshot_allowed_names = {
        item.name for item in submission_manifest.items if item.status == "accepted"
    }
    snapshot_source = (
        artifact_snapshots if artifact_snapshots is not None else dict(submission_files)
    )
    safe_artifact_snapshots = {
        name: raw_content
        for name, raw_content in snapshot_source.items()
        if name in snapshot_allowed_names
    }
    combined_warnings = list(
        dict.fromkeys([*assessment.warnings, *narrative.warnings, *manifest_warnings])
    )
    narrative_available = _has_visible_narrative_text(
        narrative.opening_sentence or ""
    ) or _has_visible_narrative_text(narrative.explanation or "")
    narrative_degraded = _narrative_degraded_from_state(
        explicit_degraded=narrative.degraded,
        narrative_source=narrative.source,
        failure_notice=narrative.failure_notice,
        narrative_available=narrative_available,
    )
    dashboard_display_duration_seconds = None
    if (
        audit.get("source_interface") == "ui"
        and audit.get("trigger_type") == "dashboard_upload"
    ):
        dashboard_display_duration_seconds = (
            get_dashboard_result_display_duration_seconds()
        )

    def operation():
        report_id: int | None = None
        try:
            with SessionLocal() as session:
                report = create_analysis_report(
                    session,
                    project_id=resolved_project.id,
                    workspace_id=resolved_workspace_id,
                    risk_score=assessment.score,
                    severity=assessment.severity,
                    recommendation=assessment.recommendation,
                    risk_confidence=assessment.confidence,
                    top_risk=assessment.top_risk,
                    report_schema_version=REPORT_SCHEMA_VERSION,
                    parse_summary=_build_parse_summary(parse_batch),
                    narrative_opening=narrative.opening_sentence or "",
                    narrative_explanation=narrative.explanation or "",
                    narrative_degraded=narrative_degraded,
                    narrative_failure_notice=narrative.failure_notice,
                    warnings_json=json.dumps(combined_warnings),
                    contributors_json=json.dumps(
                        [
                            contributor.model_dump()
                            for contributor in assessment.contributors
                        ]
                    ),
                    analyzed_files_json=json.dumps(audit["files_analyzed"]),
                    submission_manifest_json=json.dumps(
                        submission_manifest.model_dump(mode="json")
                    ),
                    submission_manifest_fallback_json=json.dumps(
                        _submission_manifest_fallback_items(submission_manifest)
                    ),
                    blast_radius_json=json.dumps(
                        blast_radius.model_dump(mode="json")
                        if blast_radius is not None
                        else {}
                    ),
                    rollback_plan_json=json.dumps(
                        rollback_plan.model_dump(mode="json")
                        if rollback_plan is not None
                        else {}
                    ),
                    llm_provider=audit["llm_provider"],
                    llm_model=audit["llm_model"],
                    llm_local_mode="true" if audit["llm_local_mode"] else "false",
                    assessment_source=assessment.source,
                    narrative_source=narrative.source,
                    narrative_skills_json=json.dumps(narrative.skills_applied),
                    source_interface=audit["source_interface"],
                    trigger_type=audit["trigger_type"],
                    trigger_id=audit["trigger_id"],
                    dashboard_display_duration_seconds=dashboard_display_duration_seconds,
                    top_risk_contributors_json=json.dumps(
                        assessment.top_risk_contributors
                    ),
                    context_completeness_json=json.dumps(
                        assessment.context_completeness.model_dump(mode="json")
                    ),
                    findings_payload=[
                        finding.model_dump(mode="json") for finding in (findings or [])
                    ],
                    evidence_payload=[
                        evidence_item.model_dump(mode="json")
                        for evidence_item in (evidence_items or [])
                    ],
                )
                report_id = int(report.id)
                save_report_artifacts(report_id, safe_artifact_snapshots)
                return _serialize_report(report, include_evidence=True)
        except Exception:
            _cleanup_partial_report(report_id)
            raise

    return _run_with_schema_retry(operation)


def fetch_analysis_report(
    report_id: int,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict | None:
    scoped_project_id, scoped_workspace_id = _resolve_report_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )

    def operation():
        with SessionLocal() as session:
            report = get_analysis_report(
                session,
                report_id,
                project_id=scoped_project_id,
                workspace_id=scoped_workspace_id,
                include_evidence=True,
            )
            if report is None:
                return None
            return _serialize_report(report, include_evidence=True)

    return _run_with_schema_retry(operation)


def fetch_report_comparison(
    report_id: int,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    previous_report_id: int | None = None,
) -> dict | None:
    current_report = fetch_analysis_report(
        report_id,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    if current_report is None:
        return None
    previous_report = fetch_previous_comparable_report(
        report_id,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
        previous_report_id=previous_report_id,
    )
    if previous_report is None:
        return None
    if previous_report_id is None:
        previous_report = fetch_analysis_report(
            int(previous_report["id"]),
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
        if previous_report is None:
            return None
    return _build_report_comparison(current_report, previous_report)


def configure_report_share(
    report_id: int,
    *,
    password: str | None,
    redact_filenames: bool,
) -> dict | None:
    password_value = (password or "").strip()
    password_salt = secrets.token_hex(8) if password_value else None
    password_hash = (
        _hash_share_password(password_value, salt=password_salt)
        if password_salt is not None
        else None
    )

    def operation():
        with SessionLocal() as session:
            report = update_analysis_report_share_settings(
                session,
                report_id,
                share_password_hash=password_hash,
                share_password_salt=password_salt,
                share_redact_filenames=redact_filenames,
            )
            if report is None:
                return None
            return _serialize_report(report, include_evidence=False)

    payload = _run_with_schema_retry(operation)
    if payload is None:
        return None
    return _share_settings(payload)


def fetch_shared_analysis_report(
    report_id: int,
    *,
    password: str | None = None,
    bypass_password: bool = False,
) -> dict | None:
    report = fetch_analysis_report(report_id)
    if report is None:
        return None
    password_hash = str(report.get("share_password_hash") or "")
    password_salt = str(report.get("share_password_salt") or "")
    if password_hash and not bypass_password:
        candidate = (password or "").strip()
        if not candidate or not password_salt:
            return None
        if not hmac.compare_digest(
            password_hash,
            _hash_share_password(candidate, salt=password_salt),
        ):
            return None
    shared = {
        **report,
        "share": _share_settings(report),
    }
    if shared["share"]["redact_filenames"]:
        shared = _redact_report_file_names(shared)
    return shared


def fetch_shared_report_comparison(
    report_id: int,
    *,
    password: str | None = None,
    bypass_password: bool = False,
) -> dict | None:
    shared_current_report = fetch_shared_analysis_report(
        report_id,
        password=password,
        bypass_password=bypass_password,
    )
    if shared_current_report is None:
        return None
    previous_report = fetch_previous_comparable_report(report_id)
    if previous_report is None:
        return None
    shared_previous_report = fetch_shared_analysis_report(
        int(previous_report["id"]),
        password=password,
        bypass_password=False,
    )
    if shared_previous_report is None:
        return None
    current_report = fetch_analysis_report(report_id)
    previous_report = fetch_analysis_report(int(previous_report["id"]))
    if current_report is None or previous_report is None:
        return None
    comparison = _build_report_comparison(current_report, previous_report)
    if not (
        shared_current_report["share"]["redact_filenames"]
        or shared_previous_report["share"]["redact_filenames"]
    ):
        return comparison
    return _redact_report_comparison(
        comparison,
        current_report=current_report,
        previous_report=previous_report,
    )


def fetch_analysis_history() -> list[dict]:
    return fetch_filtered_analysis_history()


def fetch_filtered_analysis_history(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
) -> list[dict]:
    page = fetch_filtered_analysis_history_page(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
        severity=severity,
        recommendation=recommendation,
        search=search,
    )
    return page["items"]


def fetch_filtered_analysis_history_page(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    resolved_project_id, resolved_workspace_id = _resolve_report_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )

    def operation():
        with SessionLocal() as session:
            reports = list_analysis_reports(
                session,
                project_id=resolved_project_id,
                workspace_id=resolved_workspace_id,
                severity=severity,
                recommendation=recommendation,
                search=search,
                limit=page_size,
                offset=offset,
                include_evidence=False,
            )
            all_reports = list_analysis_reports(
                session,
                project_id=resolved_project_id,
                workspace_id=resolved_workspace_id,
                include_evidence=False,
            )
            total_count = count_analysis_reports(
                session,
                project_id=resolved_project_id,
                workspace_id=resolved_workspace_id,
                severity=severity,
                recommendation=recommendation,
                search=search,
            )
            serialized_reports = [
                _serialize_report(report, include_evidence=False) for report in reports
            ]
            serialized_all_reports = []
            for report in all_reports:
                try:
                    serialized_all_reports.append(
                        _serialize_report(report, include_evidence=False)
                    )
                except ReportSchemaVersionError:
                    continue
            return (
                _attach_previous_scan_diffs(serialized_reports, serialized_all_reports),
                total_count,
            )

    reports, total_count = _run_with_schema_retry(operation)
    return {
        "items": reports,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
    }


def fetch_risk_trends(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict:
    """Return high-signal trend summaries over stored reports."""
    trend_sample_size = 100
    resolved_project_id, resolved_workspace_id = _resolve_report_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )

    def operation():
        with SessionLocal() as session:
            reports = list_analysis_reports(
                session,
                project_id=resolved_project_id,
                workspace_id=resolved_workspace_id,
                limit=trend_sample_size,
                include_evidence=False,
            )
            return {
                "reports": reports,
                "total_reports": count_analysis_reports(
                    session,
                    project_id=resolved_project_id,
                    workspace_id=resolved_workspace_id,
                ),
                "severity_counts": count_analysis_reports_by_field(
                    session,
                    "severity",
                    project_id=resolved_project_id,
                    workspace_id=resolved_workspace_id,
                ),
                "recommendation_counts": count_analysis_reports_by_field(
                    session,
                    "recommendation",
                    project_id=resolved_project_id,
                    workspace_id=resolved_workspace_id,
                ),
            }

    trend_data = _run_with_schema_retry(operation)
    reports = trend_data["reports"]

    tool_counts: Counter[str] = Counter()
    audit_rows: list[dict] = []

    for report in reports:
        contributors = json.loads(report.contributors_json or "[]")
        tools = sorted(
            {contributor.get("tool", "unknown") for contributor in contributors}
        )
        for tool in tools:
            tool_counts[tool] += 1
        audit_rows.append(
            {
                "id": report.id,
                "created_at": report.created_at.isoformat(),
                "severity": report.severity,
                "recommendation": report.recommendation,
                "top_risk": report.top_risk,
                "tools": tools,
                "audit": {
                    "llm_provider": report.llm_provider,
                    "source_interface": report.source_interface,
                },
            }
        )

    return {
        "total_reports": trend_data["total_reports"],
        "severity_counts": trend_data["severity_counts"],
        "recommendation_counts": trend_data["recommendation_counts"],
        "tool_counts": dict(tool_counts),
        "audit_rows": audit_rows,
        "trend_sample_size": trend_sample_size,
    }


def fetch_dashboard_stats(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict:
    """Return dashboard-friendly aggregate metrics for the latest persisted analyses."""
    resolved_project_id, resolved_workspace_id = _resolve_report_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )

    def operation():
        with SessionLocal() as session:
            return list_analysis_reports(
                session,
                project_id=resolved_project_id,
                workspace_id=resolved_workspace_id,
                include_evidence=False,
            )

    reports = _run_with_schema_retry(operation)

    severity_counts: Counter[str] = Counter()
    total_files_scanned = 0
    for report in reports:
        severity_counts[report.severity] += 1
        total_files_scanned += len(json.loads(report.analyzed_files_json or "[]"))

    return {
        "total_files_scanned": total_files_scanned,
        "severity_counts": {
            "low": severity_counts.get("low", 0),
            "medium": severity_counts.get("medium", 0),
            "high": severity_counts.get("high", 0),
            "critical": severity_counts.get("critical", 0),
        },
    }


def fetch_dashboard_briefing(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict[str, Any]:
    """Return dashboard hero metrics and latest-scan context from persisted reports."""
    resolved_project_id, resolved_workspace_id = _resolve_report_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )

    def operation():
        with SessionLocal() as session:
            return [
                _serialize_report(report, include_evidence=False)
                for report in list_analysis_reports(
                    session,
                    project_id=resolved_project_id,
                    workspace_id=resolved_workspace_id,
                    include_evidence=False,
                )
            ]

    serialized_reports = _run_with_schema_retry(operation)
    stats = fetch_dashboard_stats(
        project_id=resolved_project_id,
        workspace_id=resolved_workspace_id,
    )
    severity_counts = stats["severity_counts"]
    saved_briefings = len(serialized_reports)
    high_focus = severity_counts["high"] + severity_counts["critical"]
    weighted_focus_score = (
        severity_counts["critical"] * 4
        + severity_counts["high"] * 3
        + severity_counts["medium"] * 2
        + severity_counts["low"] * 1
    )

    latest_summary = "Last scan: none yet"
    latest_report: dict[str, Any] | None = (
        serialized_reports[0] if serialized_reports else None
    )
    if latest_report is not None:
        latest_files = latest_report.get("audit", {}).get("files_analyzed") or []
        latest_file = latest_files[0] if latest_files else "unknown artifact"
        created_at = datetime.fromisoformat(
            latest_report["created_at"].replace("Z", "+00:00")
        )
        elapsed_seconds = max(int((datetime.now(UTC) - created_at).total_seconds()), 0)
        if elapsed_seconds < 60:
            age_label = "just now"
        elif elapsed_seconds < 3600:
            minutes = max(1, elapsed_seconds // 60)
            age_label = f"{minutes} min ago"
        elif elapsed_seconds < 86400:
            hours = max(1, elapsed_seconds // 3600)
            age_label = f"{hours} hr ago"
        else:
            days = max(1, elapsed_seconds // 86400)
            age_label = f"{days} day ago" if days == 1 else f"{days} days ago"
        latest_summary = (
            f"Last scan: {latest_file} · {latest_report['severity'].upper()} · "
            f"{latest_report['recommendation'].upper()} · {age_label}"
        )

    return {
        "total_files_scanned": stats["total_files_scanned"],
        "saved_briefings": saved_briefings,
        "high_focus": high_focus,
        "severity_counts": severity_counts,
        "weighted_focus_score": weighted_focus_score,
        "latest_summary": latest_summary,
    }


def fetch_active_dashboard_report(
    *,
    now: datetime | None = None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> dict | None:
    """Return the most recent dashboard result still within its configured visibility window."""
    current_time = now or datetime.now(UTC)
    resolved_project_id, resolved_workspace_id = _resolve_report_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )

    def operation():
        with SessionLocal() as session:
            report = latest_active_dashboard_report(
                session,
                now=current_time,
                project_id=resolved_project_id,
                workspace_id=resolved_workspace_id,
            )
            if report is None:
                return None
            detailed_report = get_analysis_report(
                session,
                report.id,
                project_id=resolved_project_id,
                workspace_id=resolved_workspace_id,
                include_evidence=True,
            )
            if detailed_report is None:
                return None
            return _serialize_report(detailed_report, include_evidence=True)

    payload = _run_with_schema_retry(operation)
    if payload is None:
        return None
    duration = payload.get("dashboard_display_duration_seconds") or 0
    created_at = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
    remaining_seconds = max(
        int((created_at.timestamp() + duration) - current_time.timestamp()), 0
    )
    if remaining_seconds <= 0:
        return None
    payload["dashboard_remaining_seconds"] = remaining_seconds
    return payload


def remove_analysis_report(report_id: int) -> bool:
    with SessionLocal() as session:
        removed = delete_analysis_report(session, report_id)
    if removed:
        delete_report_artifacts(report_id)
    return removed


def remove_analysis_reports(report_ids: list[int]) -> int:
    removed = 0
    for report_id in report_ids:
        if remove_analysis_report(report_id):
            removed += 1
    return removed
