"""Report workflow orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from collections import Counter
from typing import Any

from analysis.risk_scorer import RiskAssessment
from llm.narrator import NarrativeResult
from sqlalchemy.exc import OperationalError

from models.database import SessionLocal, init_db
from models.repositories.analysis_reports import (
    create_analysis_report,
    delete_analysis_report,
    get_analysis_report,
    latest_active_dashboard_report,
    list_analysis_reports,
)
from parsers.base import ParseBatchResult
from services.settings_service import get_dashboard_result_display_duration_seconds
from services.settings_service import resolve_provider_runtime


def _run_with_schema_retry(operation):
    """Retry one report operation after applying runtime DB upgrades."""
    try:
        return operation()
    except OperationalError as exc:
        if "dashboard_display_duration_seconds" not in str(exc):
            raise
        init_db()
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


def _serialize_report(report) -> dict:
    created_at = report.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    audit = {
        "files_analyzed": json.loads(report.analyzed_files_json or "[]"),
        "llm_provider": report.llm_provider,
        "llm_model": report.llm_model,
        "llm_local_mode": report.llm_local_mode == "true" if report.llm_local_mode is not None else None,
        "source_interface": report.source_interface,
        "trigger_type": report.trigger_type,
        "trigger_id": report.trigger_id,
    }
    return {
        "id": report.id,
        "risk_score": report.risk_score,
        "severity": report.severity,
        "recommendation": report.recommendation,
        "top_risk": report.top_risk,
        "parse_summary": report.parse_summary,
        "narrative_opening": report.narrative_opening,
        "created_at": created_at.isoformat(),
        "warnings": json.loads(report.warnings_json or "[]"),
        "contributors": json.loads(report.contributors_json or "[]"),
        "dashboard_display_duration_seconds": report.dashboard_display_duration_seconds,
        "audit": audit,
    }


def persist_analysis_report(
    parse_batch: ParseBatchResult,
    assessment: RiskAssessment,
    narrative: NarrativeResult,
    audit_context: dict[str, Any] | None = None,
) -> dict:
    """Persist the completed analysis before the UI treats it as final."""
    audit = _build_audit_metadata(parse_batch, audit_context=audit_context)
    dashboard_display_duration_seconds = None
    if audit.get("source_interface") == "ui" and audit.get("trigger_type") == "dashboard_upload":
        dashboard_display_duration_seconds = get_dashboard_result_display_duration_seconds()
    def operation():
        with SessionLocal() as session:
            return create_analysis_report(
                session,
                risk_score=assessment.score,
                severity=assessment.severity,
                recommendation=assessment.recommendation,
                top_risk=assessment.top_risk,
                parse_summary=_build_parse_summary(parse_batch),
                narrative_opening=narrative.opening_sentence,
                narrative_explanation=narrative.explanation,
                warnings_json=json.dumps(assessment.warnings),
                contributors_json=json.dumps([contributor.model_dump() for contributor in assessment.contributors]),
                analyzed_files_json=json.dumps(audit["files_analyzed"]),
                llm_provider=audit["llm_provider"],
                llm_model=audit["llm_model"],
                llm_local_mode="true" if audit["llm_local_mode"] else "false",
                source_interface=audit["source_interface"],
                trigger_type=audit["trigger_type"],
                trigger_id=audit["trigger_id"],
                dashboard_display_duration_seconds=dashboard_display_duration_seconds,
            )
    report = _run_with_schema_retry(operation)
    return _serialize_report(report)


def fetch_analysis_report(report_id: int) -> dict | None:
    def operation():
        with SessionLocal() as session:
            return get_analysis_report(session, report_id)
    report = _run_with_schema_retry(operation)
    if report is None:
        return None
    return _serialize_report(report)


def fetch_analysis_history() -> list[dict]:
    return fetch_filtered_analysis_history()


def fetch_filtered_analysis_history(
    *,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
) -> list[dict]:
    def operation():
        with SessionLocal() as session:
            return list_analysis_reports(
                session,
                severity=severity,
                recommendation=recommendation,
                search=search,
            )
    reports = _run_with_schema_retry(operation)
    return [_serialize_report(report) for report in reports]


def fetch_risk_trends() -> dict:
    """Return high-signal trend summaries over stored reports."""
    def operation():
        with SessionLocal() as session:
            return list_analysis_reports(session)
    reports = _run_with_schema_retry(operation)

    severity_counts: Counter[str] = Counter()
    recommendation_counts: Counter[str] = Counter()
    tool_counts: Counter[str] = Counter()
    audit_rows: list[dict] = []

    for report in reports:
        severity_counts[report.severity] += 1
        recommendation_counts[report.recommendation] += 1
        contributors = json.loads(report.contributors_json or "[]")
        tools = sorted({contributor.get("tool", "unknown") for contributor in contributors})
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
        "total_reports": len(reports),
        "severity_counts": dict(severity_counts),
        "recommendation_counts": dict(recommendation_counts),
        "tool_counts": dict(tool_counts),
        "audit_rows": audit_rows,
    }


def fetch_dashboard_stats() -> dict:
    """Return dashboard-friendly aggregate metrics for the latest persisted analyses."""
    def operation():
        with SessionLocal() as session:
            return list_analysis_reports(session)
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


def fetch_active_dashboard_report(*, now: datetime | None = None) -> dict | None:
    """Return the most recent dashboard result still within its configured visibility window."""
    current_time = now or datetime.now(UTC)
    def operation():
        with SessionLocal() as session:
            return latest_active_dashboard_report(session, now=current_time)
    report = _run_with_schema_retry(operation)
    if report is None:
        return None
    payload = _serialize_report(report)
    duration = payload.get("dashboard_display_duration_seconds") or 0
    created_at = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
    remaining_seconds = max(int((created_at.timestamp() + duration) - current_time.timestamp()), 0)
    if remaining_seconds <= 0:
        return None
    payload["dashboard_remaining_seconds"] = remaining_seconds
    return payload


def remove_analysis_report(report_id: int) -> bool:
    with SessionLocal() as session:
        return delete_analysis_report(session, report_id)


def remove_analysis_reports(report_ids: list[int]) -> int:
    removed = 0
    for report_id in report_ids:
        if remove_analysis_report(report_id):
            removed += 1
    return removed
