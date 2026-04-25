"""Report workflow orchestration."""

from __future__ import annotations

import json
import os
import secrets
import hashlib
import hmac
import re
from datetime import UTC, datetime
from collections import Counter, defaultdict
from typing import Any

from analysis.blast_radius import BlastRadiusResult
from analysis.rollback_planner import RollbackPlan
from analysis.risk_scorer import RiskAssessment
from evidence.models import EvidenceItem, Finding
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
from parsers.base import ParseBatchResult
from services.artifact_snapshot_service import (
    delete_report_artifacts,
    save_report_artifacts,
)
from services.settings_service import get_dashboard_result_display_duration_seconds
from services.settings_service import resolve_provider_runtime

LEGACY_REPORT_SCHEMA_VERSION = "v1"
REPORT_SCHEMA_VERSION = "v2"
_SEVERITY_PREFIX_PATTERN = re.compile(
    r"^\s*(critical|high|medium|low|info|warning|caution)\s*[:\-]\s*",
    flags=re.IGNORECASE,
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
        host = os.getenv("APP_HOST", "127.0.0.1")
        if host in {"0.0.0.0", "::"}:
            host = "localhost"
        port = int(os.getenv("APP_PORT", "8080"))
        base_url = f"http://{host}:{port}"
    return f"{base_url}/reports/{report_id}"


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
        if basename and basename_counts[basename] == 1:
            pairs.append((basename, replacement))
    return pairs


def _redact_text_value(value: Any, pairs: list[tuple[str, str]]) -> Any:
    if not isinstance(value, str):
        return value
    redacted = value
    for original, replacement in pairs:
        redacted = redacted.replace(original, replacement)
    return redacted


def _redact_report_file_names(report: dict[str, Any]) -> dict[str, Any]:
    original_names = list(report.get("audit", {}).get("files_analyzed") or [])
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
            "files_analyzed": [redaction_map[name] for name in original_names],
        },
        "findings": [
            {
                **finding,
                "title": _redact_text_value(finding.get("title"), pairs),
                "description": _redact_text_value(finding.get("description"), pairs),
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
                "summary": _redact_text_value(evidence_item.get("summary"), pairs),
            }
            for evidence_item in (report.get("evidence_items") or [])
        ],
    }
    return redacted


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
    return {
        "files_analyzed": [file_result.file_name for file_result in parse_batch.files],
        "llm_provider": runtime["provider"],
        "llm_model": runtime["model"],
        "llm_local_mode": runtime["local_mode"],
        "source_interface": context.get("source_interface"),
        "trigger_type": context.get("trigger_type"),
        "trigger_id": context.get("trigger_id"),
    }


def _extract_narrative_failure_notice(warnings: list[str]) -> str | None:
    for warning in warnings:
        if "narrative provider unavailable" in warning.lower():
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


def _artifact_signature(files_analyzed: list[str]) -> tuple[str, ...]:
    """Normalize analyzed-file identity for history diff grouping."""
    return tuple(sorted(str(name) for name in files_analyzed if str(name).strip()))


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
        str(finding.get("uncertainty_note") or ""),
        str(finding.get("skill_id") or ""),
    )


def _report_finding_maps(
    report: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    findings_by_fingerprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_by_finding_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evidence_item in report.get("evidence_items") or []:
        evidence_by_finding_id[str(evidence_item.get("finding_id") or "")].append(
            evidence_item
        )
    for finding in report.get("findings") or []:
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
    current_signature = _artifact_signature(
        current_report.get("audit", {}).get("files_analyzed") or []
    )
    if not current_signature:
        return None
    current_id = int(current_report["id"])
    previous_candidates = sorted(
        (
            report
            for report in candidate_reports
            if int(report["id"]) < current_id
            and _artifact_signature(report.get("audit", {}).get("files_analyzed") or [])
            == current_signature
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
    previous_report_id: int | None = None,
) -> dict | None:
    current_report = fetch_analysis_report(report_id)
    if current_report is None:
        return None
    if previous_report_id is not None:
        return fetch_analysis_report(previous_report_id)
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
        for original_name in report.get("audit", {}).get("files_analyzed") or []:
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
    latest_by_signature: dict[tuple[str, ...], dict[str, Any]] = {}
    previous_by_id: dict[int, dict[str, Any]] = {}

    for report in reversed(all_reports):
        signature = _artifact_signature(
            report.get("audit", {}).get("files_analyzed") or []
        )
        if signature:
            previous = latest_by_signature.get(signature)
            if previous is not None:
                previous_by_id[int(report["id"])] = previous
            latest_by_signature[signature] = report

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

    scoped_findings = (
        [
            finding.model_copy(
                update={
                    "finding_id": finding_id_map[finding.finding_id],
                    "evidence_refs": [
                        evidence_id_map.get(evidence_ref, evidence_ref)
                        for evidence_ref in finding.evidence_refs
                    ],
                }
            )
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
                    "finding_id": finding_id_map.get(
                        evidence_item.finding_id,
                        evidence_item.finding_id,
                    ),
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


def normalize_report_schema_version(schema_version: str | None) -> str:
    """Return a stable schema version for stored or in-memory reports."""
    return schema_version or LEGACY_REPORT_SCHEMA_VERSION


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


def _serialize_report(report, *, include_evidence: bool = True) -> dict:
    created_at = report.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    audit = {
        "files_analyzed": json.loads(report.analyzed_files_json or "[]"),
        "llm_provider": report.llm_provider,
        "llm_model": report.llm_model,
        "llm_local_mode": report.llm_local_mode == "true"
        if report.llm_local_mode is not None
        else None,
        "source_interface": report.source_interface,
        "trigger_type": report.trigger_type,
        "trigger_id": report.trigger_id,
    }
    warnings = json.loads(report.warnings_json or "[]")
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
                        "summary": evidence_item.summary,
                        "severity_hint": evidence_item.severity_hint,
                        "deterministic": evidence_item.deterministic,
                        "confidence": evidence_item.confidence,
                        "related_change_ids": json.loads(
                            evidence_item.related_change_ids_json or "[]"
                        ),
                    }
                )
    narrative_available = bool(
        (report.narrative_opening or "").strip()
        or (report.narrative_explanation or "").strip()
    )
    return {
        "id": report.id,
        "risk_score": report.risk_score,
        "severity": report.severity,
        "recommendation": report.recommendation,
        "top_risk": report.top_risk,
        "report_schema_version": normalize_report_schema_version(
            getattr(report, "report_schema_version", None)
        ),
        "top_risk_contributors": json.loads(
            report.risk_assessment.top_risk_contributors_json
            if report.risk_assessment is not None
            else "[]"
        ),
        "context_completeness": json.loads(
            report.risk_assessment.context_completeness_json
            if report.risk_assessment is not None
            else "{}"
        ),
        "blast_radius": (
            json.loads(report.blast_radius_json or "{}")
            or _default_blast_radius_payload()
        ),
        "rollback_plan": (
            json.loads(getattr(report, "rollback_plan_json", "") or "{}")
            or _default_rollback_plan_payload()
        ),
        "parse_summary": report.parse_summary,
        "narrative_opening": report.narrative_opening,
        "narrative_explanation": report.narrative_explanation,
        "narrative_available": narrative_available,
        "narrative_failure_notice": _extract_narrative_failure_notice(warnings),
        "assessment_source": report.assessment_source,
        "narrative_source": report.narrative_source,
        "narrative_provider": report.llm_provider,
        "narrative_model": report.llm_model,
        "narrative_local_mode": report.llm_local_mode == "true"
        if report.llm_local_mode is not None
        else None,
        "skills_applied": json.loads(report.narrative_skills_json or "[]"),
        "created_at": created_at.isoformat(),
        "warnings": warnings,
        "findings": [
            {
                "finding_id": finding.finding_id,
                "analysis_id": finding.analysis_id,
                "title": finding.title,
                "description": finding.description,
                "severity": finding.severity,
                "category": finding.category,
                "deterministic": finding.deterministic,
                "confidence": finding.confidence,
                "uncertainty_note": finding.uncertainty_note,
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


def persist_analysis_report(
    parse_batch: ParseBatchResult,
    assessment: RiskAssessment,
    narrative: NarrativeResult,
    blast_radius: BlastRadiusResult | None = None,
    rollback_plan: RollbackPlan | None = None,
    findings: list[Finding] | None = None,
    evidence_items: list[EvidenceItem] | None = None,
    artifact_snapshots: dict[str, bytes | None] | None = None,
    audit_context: dict[str, Any] | None = None,
) -> dict:
    """Persist the completed analysis before the UI treats it as final."""
    assessment, findings, evidence_items = _scope_report_entities(
        assessment,
        findings,
        evidence_items,
    )
    audit = _build_audit_metadata(parse_batch, audit_context=audit_context)
    combined_warnings = list(dict.fromkeys([*assessment.warnings, *narrative.warnings]))
    dashboard_display_duration_seconds = None
    if (
        audit.get("source_interface") == "ui"
        and audit.get("trigger_type") == "dashboard_upload"
    ):
        dashboard_display_duration_seconds = (
            get_dashboard_result_display_duration_seconds()
        )

    def operation():
        with SessionLocal() as session:
            report = create_analysis_report(
                session,
                risk_score=assessment.score,
                severity=assessment.severity,
                recommendation=assessment.recommendation,
                top_risk=assessment.top_risk,
                report_schema_version=REPORT_SCHEMA_VERSION,
                parse_summary=_build_parse_summary(parse_batch),
                narrative_opening=narrative.opening_sentence or "",
                narrative_explanation=narrative.explanation or "",
                warnings_json=json.dumps(combined_warnings),
                contributors_json=json.dumps(
                    [
                        contributor.model_dump()
                        for contributor in assessment.contributors
                    ]
                ),
                analyzed_files_json=json.dumps(audit["files_analyzed"]),
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
                top_risk_contributors_json=json.dumps(assessment.top_risk_contributors),
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
            save_report_artifacts(report.id, artifact_snapshots)
            return _serialize_report(report, include_evidence=True)

    return _run_with_schema_retry(operation)


def fetch_analysis_report(report_id: int) -> dict | None:
    def operation():
        with SessionLocal() as session:
            report = get_analysis_report(session, report_id, include_evidence=True)
            if report is None:
                return None
            return _serialize_report(report, include_evidence=True)

    return _run_with_schema_retry(operation)


def fetch_report_comparison(
    report_id: int,
    *,
    previous_report_id: int | None = None,
) -> dict | None:
    current_report = fetch_analysis_report(report_id)
    if current_report is None:
        return None
    previous_report = fetch_previous_comparable_report(
        report_id,
        previous_report_id=previous_report_id,
    )
    if previous_report is None:
        return None
    if previous_report_id is None:
        previous_report = fetch_analysis_report(int(previous_report["id"]))
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
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
) -> list[dict]:
    page = fetch_filtered_analysis_history_page(
        severity=severity,
        recommendation=recommendation,
        search=search,
    )
    return page["items"]


def fetch_filtered_analysis_history_page(
    *,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    def operation():
        with SessionLocal() as session:
            reports = list_analysis_reports(
                session,
                severity=severity,
                recommendation=recommendation,
                search=search,
                limit=page_size,
                offset=offset,
                include_evidence=False,
            )
            all_reports = list_analysis_reports(session, include_evidence=False)
            total_count = count_analysis_reports(
                session,
                severity=severity,
                recommendation=recommendation,
                search=search,
            )
            serialized_reports = [
                _serialize_report(report, include_evidence=False) for report in reports
            ]
            serialized_all_reports = [
                _serialize_report(report, include_evidence=False)
                for report in all_reports
            ]
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


def fetch_risk_trends() -> dict:
    """Return high-signal trend summaries over stored reports."""
    trend_sample_size = 100

    def operation():
        with SessionLocal() as session:
            reports = list_analysis_reports(
                session, limit=trend_sample_size, include_evidence=False
            )
            return {
                "reports": reports,
                "total_reports": count_analysis_reports(session),
                "severity_counts": count_analysis_reports_by_field(session, "severity"),
                "recommendation_counts": count_analysis_reports_by_field(
                    session, "recommendation"
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


def fetch_dashboard_stats() -> dict:
    """Return dashboard-friendly aggregate metrics for the latest persisted analyses."""

    def operation():
        with SessionLocal() as session:
            return list_analysis_reports(session, include_evidence=False)

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


def fetch_dashboard_briefing() -> dict[str, Any]:
    """Return dashboard hero metrics and latest-scan context from persisted reports."""

    def operation():
        with SessionLocal() as session:
            return [
                _serialize_report(report, include_evidence=False)
                for report in list_analysis_reports(session, include_evidence=False)
            ]

    serialized_reports = _run_with_schema_retry(operation)
    stats = fetch_dashboard_stats()
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


def fetch_active_dashboard_report(*, now: datetime | None = None) -> dict | None:
    """Return the most recent dashboard result still within its configured visibility window."""
    current_time = now or datetime.now(UTC)

    def operation():
        with SessionLocal() as session:
            report = latest_active_dashboard_report(session, now=current_time)
            if report is None:
                return None
            detailed_report = get_analysis_report(
                session, report.id, include_evidence=True
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
