"""Report workflow orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from collections import Counter
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
            total_count = count_analysis_reports(
                session,
                severity=severity,
                recommendation=recommendation,
                search=search,
            )
            return [
                _serialize_report(report, include_evidence=False) for report in reports
            ], total_count

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
