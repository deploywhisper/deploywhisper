"""Weekly outcome backtesting and calibration feed helpers."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from services.artifact_snapshot_service import load_report_artifact
from models.database import SessionLocal
from models.repositories.analysis_reports import get_analysis_report
from models.repositories.feedback_events import list_feedback_events
from models.repositories.incident_records import list_incident_records
from models.repositories.settings import (
    delete_setting,
    delete_settings_by_key_prefix,
    get_setting,
    upsert_setting,
)
from models.tables import (
    AnalysisReport,
    DeploymentOutcome,
    FeedbackEvent,
    IncidentRecord,
)
from models.tables import RiskAssessment as PersistedRiskAssessment
from services.project_service import (
    build_project_payload,
    build_workspace_payload,
    list_projects,
    resolve_project_reference,
    resolve_workspace_reference,
)

BACKTEST_WINDOW_DAYS = 7
BACKTEST_LAST_RUN_KEY = "backtesting:last_run_at:project:"
BACKTEST_SNAPSHOT_KEY = "backtesting:snapshot:project:"
INCIDENT_BACKTEST_STATUSES = (
    "detected",
    "missed",
    "unsupported",
    "insufficient_context",
    "error",
)

logger = logging.getLogger(__name__)


def _last_run_key(project_id: int) -> str:
    return f"{BACKTEST_LAST_RUN_KEY}{project_id}"


def _snapshot_key(project_id: int, workspace_id: int | None = None) -> str:
    key = f"{BACKTEST_SNAPSHOT_KEY}{project_id}"
    if workspace_id is not None:
        key = f"{key}:workspace:{workspace_id}"
    return key


def _warned(report: AnalysisReport | None) -> bool:
    if report is None:
        return False
    return str(report.recommendation or "").lower() != "go"


def _outcome_rows(
    *,
    project_id: int,
    workspace_id: int | None = None,
    window_start: datetime,
    window_end: datetime,
) -> list[
    tuple[DeploymentOutcome, AnalysisReport | None, PersistedRiskAssessment | None]
]:
    with SessionLocal() as session:
        stmt = (
            select(DeploymentOutcome, AnalysisReport, PersistedRiskAssessment)
            .join(
                AnalysisReport,
                DeploymentOutcome.analysis_id == AnalysisReport.id,
                isouter=True,
            )
            .join(
                PersistedRiskAssessment,
                AnalysisReport.id == PersistedRiskAssessment.analysis_id,
                isouter=True,
            )
            .where(DeploymentOutcome.project_id == project_id)
            .where(DeploymentOutcome.deployed_at >= window_start)
            .where(DeploymentOutcome.deployed_at <= window_end)
            .order_by(DeploymentOutcome.deployed_at.asc(), DeploymentOutcome.id.asc())
        )
        if workspace_id is not None:
            stmt = stmt.where(DeploymentOutcome.workspace_id == workspace_id)
        result = session.execute(stmt)
        return list(result.all())


def _feedback_rows(
    *,
    project_id: int,
    workspace_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> list[FeedbackEvent]:
    with SessionLocal() as session:
        return list_feedback_events(
            session,
            project_id=project_id,
            workspace_id=workspace_id,
            created_from=created_from,
            created_to=created_to,
        )


def _analysis_context_rows(
    *,
    project_id: int,
    workspace_id: int | None = None,
    analysis_ids: set[int],
) -> list[tuple[AnalysisReport, PersistedRiskAssessment | None]]:
    if not analysis_ids:
        return []
    with SessionLocal() as session:
        stmt = (
            select(AnalysisReport, PersistedRiskAssessment)
            .join(
                PersistedRiskAssessment,
                AnalysisReport.id == PersistedRiskAssessment.analysis_id,
                isouter=True,
            )
            .where(AnalysisReport.project_id == project_id)
            .where(AnalysisReport.id.in_(sorted(analysis_ids)))
        )
        if workspace_id is not None:
            stmt = stmt.where(AnalysisReport.workspace_id == workspace_id)
        result = session.execute(stmt)
        return list(result.all())


def _incident_rows(
    *,
    project_id: int,
    analysis_ids: set[int],
) -> list[IncidentRecord]:
    if not analysis_ids:
        return []
    with SessionLocal() as session:
        stmt = (
            select(IncidentRecord)
            .join(
                AnalysisReport,
                IncidentRecord.analysis_id == AnalysisReport.id,
            )
            .where(AnalysisReport.project_id == project_id)
            .where(IncidentRecord.analysis_id.is_not(None))
            .where(IncidentRecord.analysis_id.in_(sorted(analysis_ids)))
            .order_by(IncidentRecord.created_at.asc(), IncidentRecord.id.asc())
        )
        result = session.execute(stmt)
        return list(result.scalars().all())


def _incident_event_timestamp(incident: IncidentRecord) -> datetime:
    incident_date = str(incident.incident_date or "").strip()
    if incident_date:
        parsed = _parse_incident_date(incident_date)
        if parsed is not None:
            return parsed
    created_at = incident.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    else:
        created_at = created_at.astimezone(UTC)
    return created_at


def _parse_incident_date(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed


def _serialize_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat()


def _load_json_object(raw_value: str | None) -> dict[str, Any]:
    try:
        decoded = json.loads(raw_value or "{}")
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _load_json_list(raw_value: str | None) -> list[Any]:
    try:
        decoded = json.loads(raw_value or "[]")
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def _accepted_replay_artifact_names(report: AnalysisReport) -> list[str]:
    manifest = _load_json_object(report.submission_manifest_json)
    items = manifest.get("items")
    accepted = (
        [
            str(item.get("name"))
            for item in items
            if isinstance(item, dict)
            and item.get("status") == "accepted"
            and str(item.get("name") or "").strip()
        ]
        if isinstance(items, list)
        else []
    )
    if accepted:
        return list(dict.fromkeys(accepted))
    fallback = _load_json_list(report.analyzed_files_json)
    return list(
        dict.fromkeys(
            str(item) for item in fallback if isinstance(item, str) and item.strip()
        )
    )


def _replay_artifact_files(
    report: AnalysisReport,
) -> tuple[list[tuple[str, bytes | None]], list[str], list[str]]:
    missing: list[str] = []
    files: list[tuple[str, bytes | None]] = []
    for artifact_name in _accepted_replay_artifact_names(report):
        snapshot = load_report_artifact(int(report.id), artifact_name)
        if snapshot is None:
            missing.append(artifact_name)
            continue
        files.append((artifact_name, snapshot.content.encode("utf-8")))
    return files, [name for name, _ in files], missing


def _incident_payload(incident: IncidentRecord) -> dict[str, Any]:
    return {
        "id": incident.id,
        "project_id": incident.project_id,
        "workspace_id": incident.workspace_id,
        "title": incident.title,
        "severity": incident.severity,
        "source_file": incident.source_file,
        "incident_date": incident.incident_date,
        "analysis_id": incident.analysis_id,
    }


def _linked_report_payload(report: AnalysisReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "id": report.id,
        "project_id": report.project_id,
        "workspace_id": report.workspace_id,
        "severity": report.severity,
        "recommendation": report.recommendation,
        "risk_score": report.risk_score,
        "top_risk": report.top_risk,
        "created_at": _serialize_timestamp(report.created_at),
    }


def _expected_evidence_payload(report: AnalysisReport | None) -> list[dict[str, Any]]:
    if report is None:
        return []
    evidence_items: list[dict[str, Any]] = []
    for finding in report.findings:
        for evidence in finding.evidence_items:
            evidence_items.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "finding_id": evidence.finding_id,
                    "source_ref": evidence.source_ref,
                    "artifact": evidence.artifact,
                    "location": evidence.location,
                    "resource": evidence.resource,
                    "operation": evidence.operation,
                    "summary": evidence.summary,
                    "severity_hint": evidence.severity_hint,
                    "deterministic": evidence.deterministic,
                }
            )
    return evidence_items


def _observed_evidence_payload(evidence_items: list[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for evidence in evidence_items:
        if hasattr(evidence, "model_dump"):
            item = evidence.model_dump(mode="json")
        else:
            item = dict(evidence)
        payload.append(
            {
                "evidence_id": item.get("evidence_id"),
                "source_ref": item.get("source_ref"),
                "artifact": item.get("artifact"),
                "location": item.get("location"),
                "resource": item.get("resource"),
                "operation": item.get("operation"),
                "summary": item.get("summary"),
                "severity_hint": item.get("severity_hint"),
                "deterministic": item.get("deterministic"),
            }
        )
    return payload


def _observed_finding_payload(findings: list[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for finding in findings:
        if hasattr(finding, "model_dump"):
            item = finding.model_dump(mode="json")
        else:
            item = dict(finding)
        payload.append(
            {
                "finding_id": item.get("finding_id"),
                "title": item.get("title"),
                "severity": item.get("severity"),
                "category": item.get("category"),
                "deterministic": item.get("deterministic"),
                "confidence": item.get("confidence"),
                "evidence_refs": item.get("evidence_refs") or [],
            }
        )
    return payload


def _run_incident_replay_analysis(files: list[tuple[str, bytes | None]]):
    from services.analysis_service import build_analysis_artifacts

    return build_analysis_artifacts(
        files,
        include_topology_context=False,
        include_incident_context=False,
        include_narrative=False,
        allow_llm_assistance=False,
    )


def _incident_backtest_improvements(
    *,
    status: str,
    context_todos: list[str],
    missing_artifacts: list[str],
) -> list[str]:
    if status == "detected":
        return ["No immediate analyzer improvement identified for this replay."]
    if status == "missed":
        return [
            "Review incident prevention notes and add deterministic evidence/risk patterns for the missed change."
        ]
    if status == "insufficient_context":
        return context_todos or [
            "Import the missing topology, incident, scanner, or ownership context before rerunning the backtest."
        ]
    if missing_artifacts:
        return ["Store accepted replay artifact snapshots for the linked report."]
    return ["Link the incident to an analysis report with accepted replay artifacts."]


def _classify_incident_replay(analysis_artifacts) -> tuple[str, str]:
    assessment = analysis_artifacts.assessment
    manifest = analysis_artifacts.submission_manifest
    if getattr(manifest, "accepted_artifact_count", 0) == 0:
        return "unsupported", "unsupported"
    if assessment.context_completeness.insufficient_context:
        return "insufficient_context", "insufficient_context"
    if str(assessment.recommendation).lower() == "go":
        return "missed", "go"
    if (
        str(assessment.recommendation).lower() == "no-go"
        and assessment.severity == "critical"
    ):
        return "detected", "stop"
    return "detected", "warn"


def _unsupported_incident_scenario(
    *,
    incident: IncidentRecord,
    report: AnalysisReport | None,
    reasons: list[str],
    missing_artifacts: list[str] | None = None,
    replay_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    missing_artifacts = missing_artifacts or []
    replay_artifacts = replay_artifacts or []
    return {
        "incident": _incident_payload(incident),
        "linked_report": _linked_report_payload(report),
        "status": "unsupported",
        "actual_verdict": "unsupported",
        "actual_recommendation": None,
        "actual_severity": None,
        "actual_score": None,
        "replay_artifacts": replay_artifacts,
        "missing_replay_artifacts": missing_artifacts,
        "expected_evidence": _expected_evidence_payload(report),
        "observed_evidence": [],
        "observed_findings": [],
        "context_todos": [],
        "reasons": reasons,
        "what_would_need_to_improve": _incident_backtest_improvements(
            status="unsupported",
            context_todos=[],
            missing_artifacts=missing_artifacts,
        ),
    }


def _error_incident_scenario(
    *,
    incident: IncidentRecord,
    report: AnalysisReport | None,
    reasons: list[str],
    replay_artifacts: list[str] | None = None,
    missing_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "incident": _incident_payload(incident),
        "linked_report": _linked_report_payload(report),
        "status": "error",
        "actual_verdict": "error",
        "actual_recommendation": None,
        "actual_severity": None,
        "actual_score": None,
        "replay_artifacts": replay_artifacts or [],
        "missing_replay_artifacts": missing_artifacts or [],
        "expected_evidence": _expected_evidence_payload(report),
        "observed_evidence": [],
        "observed_findings": [],
        "context_todos": [],
        "reasons": reasons,
        "what_would_need_to_improve": [
            "Fix the replay execution error, then rerun incident backtesting."
        ],
    }


def _run_incident_backtest_scenario(
    *,
    incident: IncidentRecord,
    report: AnalysisReport | None,
) -> dict[str, Any]:
    if incident.analysis_id is None:
        return _unsupported_incident_scenario(
            incident=incident,
            report=report,
            reasons=["Incident is not linked to an analysis report."],
        )
    if report is None:
        return _unsupported_incident_scenario(
            incident=incident,
            report=report,
            reasons=["Linked analysis report is unavailable."],
        )

    try:
        files, replay_artifact_names, missing_artifacts = _replay_artifact_files(report)
    except Exception as exc:  # noqa: BLE001
        return _error_incident_scenario(
            incident=incident,
            report=report,
            reasons=[str(exc)],
        )

    if not files:
        return _unsupported_incident_scenario(
            incident=incident,
            report=report,
            reasons=["No accepted replay artifact snapshots are available."],
            missing_artifacts=missing_artifacts,
        )
    if missing_artifacts:
        return _unsupported_incident_scenario(
            incident=incident,
            report=report,
            reasons=[
                "Some accepted linked-report artifact snapshots were unavailable: "
                + ", ".join(missing_artifacts)
            ],
            missing_artifacts=missing_artifacts,
            replay_artifacts=replay_artifact_names,
        )

    try:
        analysis_artifacts = _run_incident_replay_analysis(files)
    except Exception as exc:  # noqa: BLE001
        return _error_incident_scenario(
            incident=incident,
            report=report,
            reasons=[str(exc)],
            replay_artifacts=replay_artifact_names,
            missing_artifacts=missing_artifacts,
        )

    status, actual_verdict = _classify_incident_replay(analysis_artifacts)
    assessment = analysis_artifacts.assessment
    context_todos = list(assessment.context_completeness.context_todos)
    reasons = list(assessment.warnings)
    return {
        "incident": _incident_payload(incident),
        "linked_report": _linked_report_payload(report),
        "status": status,
        "actual_verdict": actual_verdict,
        "actual_recommendation": assessment.recommendation,
        "actual_severity": assessment.severity,
        "actual_score": assessment.score,
        "replay_artifacts": replay_artifact_names,
        "missing_replay_artifacts": missing_artifacts,
        "expected_evidence": _expected_evidence_payload(report),
        "observed_evidence": _observed_evidence_payload(
            list(analysis_artifacts.evidence_items)
        ),
        "observed_findings": _observed_finding_payload(
            list(analysis_artifacts.findings)
        ),
        "context_todos": context_todos,
        "reasons": reasons,
        "what_would_need_to_improve": _incident_backtest_improvements(
            status=status,
            context_todos=context_todos,
            missing_artifacts=missing_artifacts,
        ),
    }


def _incident_linked_report(
    *,
    session,
    incident: IncidentRecord,
    project_id: int,
    workspace_id: int | None,
) -> AnalysisReport | None:
    if incident.analysis_id is None:
        return None
    report = get_analysis_report(
        session,
        int(incident.analysis_id),
        project_id=project_id,
        workspace_id=workspace_id,
        include_evidence=True,
    )
    if report is None or workspace_id is not None:
        return report
    if report.workspace_id != incident.workspace_id:
        return None
    return report


def _confidence_bucket(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.60:
        return "medium"
    return "low"


def _serialize_feedback_case(
    *,
    event: FeedbackEvent,
    report: AnalysisReport | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "analysis_id": event.analysis_id,
        "finding_id": event.finding_id,
        "reason": reason,
        "note": event.false_positive_reason or event.false_negative_note,
        "severity": report.severity if report is not None else None,
        "recommendation": report.recommendation if report is not None else None,
        "created_at": _serialize_timestamp(event.created_at),
    }


def _calibration_limitations(
    *,
    sample_size: int,
    feedback_event_count: int,
    feedback_history_event_count: int,
    false_positive_count: int,
    missed_feedback_count: int,
    useful_feedback_count: int,
    neutral_feedback_count: int,
) -> list[dict[str, str]]:
    limitations: list[dict[str, str]] = []
    if sample_size < 10:
        limitations.append(
            {
                "code": "sparse_outcomes",
                "label": "Sparse calibration data",
                "message": (
                    f"Only {sample_size} linked deployment outcomes are available; "
                    "treat precision, recall proxy, and error rates as directional."
                ),
            }
        )
    if feedback_event_count < 5:
        limitations.append(
            {
                "code": "sparse_feedback",
                "label": "Limited reviewer feedback",
                "message": (
                    f"Only {feedback_event_count} feedback events are linked to this "
                    "calibration window, so reviewer-error signals may be incomplete."
                ),
            }
        )
    feedback_type_counts = [
        false_positive_count,
        missed_feedback_count,
        useful_feedback_count,
        neutral_feedback_count,
    ]
    if feedback_event_count > 0 and max(feedback_type_counts) == feedback_event_count:
        limitations.append(
            {
                "code": "feedback_bias",
                "label": "Feedback may be biased",
                "message": (
                    "Current feedback is concentrated in one outcome type; do not "
                    "treat it as statistically representative."
                ),
            }
        )
    if (
        sample_size == 0
        and feedback_event_count == 0
        and feedback_history_event_count == 0
    ):
        limitations.append(
            {
                "code": "no_calibration_inputs",
                "label": "No calibration inputs",
                "message": (
                    "No deployment outcomes or feedback are linked yet; calibration "
                    "metrics cannot imply statistical certainty."
                ),
            }
        )
    return limitations


def _coerce_utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed


def _calibration_case_event_timestamp(case: dict[str, Any]) -> datetime:
    value = case.get("created_at") or case.get("deployed_at")
    if isinstance(value, str) and value.strip():
        try:
            return _coerce_utc_timestamp(value)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=UTC)


def _cached_snapshot_is_fresh(snapshot: dict[str, Any], *, now: datetime) -> bool:
    window = snapshot.get("window")
    if not isinstance(window, dict):
        return False
    window_start = window.get("start")
    if not isinstance(window_start, str) or not window_start.strip():
        return False
    window_end = window.get("end")
    if not isinstance(window_end, str) or not window_end.strip():
        return False
    try:
        snapshot_start = _coerce_utc_timestamp(window_start)
        snapshot_end = _coerce_utc_timestamp(window_end)
    except ValueError:
        return False
    if snapshot_end > now:
        return False
    if snapshot_end - snapshot_start != timedelta(days=BACKTEST_WINDOW_DAYS):
        return False
    return now - snapshot_end < timedelta(days=BACKTEST_WINDOW_DAYS)


def _payload_project_id(payload: dict[str, Any]) -> int | None:
    project = payload.get("project")
    if not isinstance(project, dict):
        return None
    project_id = project.get("id")
    return int(project_id) if isinstance(project_id, int) else None


def _payload_workspace_id(payload: dict[str, Any]) -> int | None:
    workspace = payload.get("workspace")
    if workspace is None:
        return None
    if not isinstance(workspace, dict):
        return None
    workspace_id = workspace.get("id")
    return int(workspace_id) if isinstance(workspace_id, int) else None


def _cached_snapshot_matches_scope(
    snapshot: dict[str, Any],
    *,
    project_id: int,
    workspace_id: int | None,
) -> bool:
    return (
        _payload_project_id(snapshot) == project_id
        and _payload_workspace_id(snapshot) == workspace_id
    )


def _is_int_payload_value(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_numeric_payload_value(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _has_required_fields(
    payload: dict[str, Any],
    fields: dict[str, type | tuple[type, ...]],
) -> bool:
    return all(
        isinstance(payload.get(field), field_type)
        for field, field_type in fields.items()
    )


def _cached_snapshot_has_required_shape(snapshot: dict[str, Any]) -> bool:
    window = snapshot.get("window")
    if not isinstance(window, dict):
        return False
    window_days = window.get("days")
    if not _is_int_payload_value(window_days) or window_days != BACKTEST_WINDOW_DAYS:
        return False
    if not isinstance(window.get("start"), str) or not isinstance(
        window.get("end"), str
    ):
        return False
    required_integer_fields = ["failed_deploy_count", "warned_failed_deploy_count"]
    for field in required_integer_fields:
        if not _is_int_payload_value(snapshot.get(field)):
            return False
    required_numeric_fields = ["overall_precision", "overall_recall"]
    for field in required_numeric_fields:
        if not _is_numeric_payload_value(snapshot.get(field)):
            return False
    if not _has_required_fields(
        snapshot,
        {
            "backtest_rows": list,
            "by_severity": dict,
            "false_positive_cases": list,
            "false_reassurance_cases": list,
            "confidence_trends": dict,
        },
    ):
        return False
    confidence_trends = snapshot["confidence_trends"]
    if not isinstance(confidence_trends.get("buckets"), dict):
        return False
    if not _is_int_payload_value(confidence_trends.get("sample_size")):
        return False
    if not isinstance(snapshot.get("confidence_limitations"), list):
        return False
    if not isinstance(snapshot.get("confidence_label"), str):
        return False
    if not isinstance(snapshot.get("statistical_certainty"), bool):
        return False
    calibration_metrics = snapshot.get("calibration_metrics")
    if not isinstance(calibration_metrics, dict):
        return False
    required_integer_metric_fields = [
        "sample_size",
        "feedback_event_count",
        "feedback_history_event_count",
        "false_positive_count",
        "false_reassurance_count",
        "deployment_false_reassurance_count",
        "reviewer_missed_feedback_count",
    ]
    for field in required_integer_metric_fields:
        if not _is_int_payload_value(calibration_metrics.get(field)):
            return False
    required_numeric_metric_fields = [
        "precision",
        "recall_proxy",
        "false_positive_rate",
        "false_reassurance_rate",
    ]
    for field in required_numeric_metric_fields:
        if not _is_numeric_payload_value(calibration_metrics.get(field)):
            return False
    recall_proxy_signals = calibration_metrics.get("recall_proxy_signals")
    if not isinstance(recall_proxy_signals, dict):
        return False
    return all(
        _is_int_payload_value(recall_proxy_signals.get(field))
        for field in [
            "failed_deploy_count",
            "warned_failed_deploy_count",
            "failed_without_warning_count",
            "missed_feedback_count",
        ]
    )


def _cached_snapshot_is_usable(
    snapshot: dict[str, Any],
    *,
    project_id: int,
    workspace_id: int | None,
    now: datetime,
) -> bool:
    return (
        _cached_snapshot_is_fresh(snapshot, now=now)
        and _cached_snapshot_matches_scope(
            snapshot,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        and _cached_snapshot_has_required_shape(snapshot)
    )


def _build_summary(
    *,
    project,
    workspace=None,
    rows: list[
        tuple[DeploymentOutcome, AnalysisReport | None, PersistedRiskAssessment | None]
    ],
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    failed_rows: list[dict[str, Any]] = []
    warned_total = 0
    true_positive = 0
    outcome_report_count = 0
    failed_without_warning_count = 0
    report_by_analysis_id: dict[int, AnalysisReport] = {}
    confidence_by_analysis_id: dict[int, float | None] = {}
    warning_by_analysis_id: dict[int, bool] = {}
    failed_by_analysis_id: dict[int, bool] = {}
    outcome_confidence_samples: list[tuple[int, float | None, bool, bool]] = []
    by_severity_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"warned": 0, "failed": 0, "true_positive": 0}
    )
    analysis_ids = {
        int(outcome.analysis_id)
        for outcome, _, _ in rows
        if outcome.analysis_id is not None
    }
    incidents = _incident_rows(project_id=project.id, analysis_ids=analysis_ids)
    feedback_history_events = _feedback_rows(
        project_id=project.id,
        workspace_id=workspace.id if workspace is not None else None,
    )
    feedback_history_events = [
        event for event in feedback_history_events if event.analysis_id is not None
    ]
    feedback_events = _feedback_rows(
        project_id=project.id,
        workspace_id=workspace.id if workspace is not None else None,
        created_from=window_start,
        created_to=window_end,
    )
    feedback_events = [
        event for event in feedback_events if event.analysis_id is not None
    ]
    feedback_analysis_ids = {
        int(event.analysis_id)
        for event in feedback_events
        if event.analysis_id is not None
    }
    feedback_only_analysis_ids = feedback_analysis_ids - analysis_ids
    for report, risk_assessment in _analysis_context_rows(
        project_id=project.id,
        workspace_id=workspace.id if workspace is not None else None,
        analysis_ids=feedback_only_analysis_ids,
    ):
        analysis_id = int(report.id)
        report_by_analysis_id[analysis_id] = report
        confidence_by_analysis_id[analysis_id] = (
            float(risk_assessment.confidence)
            if risk_assessment is not None and risk_assessment.confidence is not None
            else None
        )
        warning_by_analysis_id[analysis_id] = _warned(report)
        failed_by_analysis_id.setdefault(analysis_id, False)
    incident_by_analysis_id: dict[int, IncidentRecord] = {}
    for incident in incidents:
        analysis_id = (
            int(incident.analysis_id) if incident.analysis_id is not None else None
        )
        if analysis_id is None:
            continue
        current = incident_by_analysis_id.get(analysis_id)
        if current is None or _incident_event_timestamp(
            current
        ) <= _incident_event_timestamp(incident):
            incident_by_analysis_id[analysis_id] = incident

    for outcome, report, risk_assessment in rows:
        if outcome.analysis_id is None or report is None:
            continue
        outcome_report_count += 1
        did_warn = _warned(report)
        failed = outcome.outcome_label in {"failure", "rolled_back"}
        severity = str(report.severity if report is not None else "unknown").lower()
        analysis_id = int(outcome.analysis_id)
        confidence = (
            float(risk_assessment.confidence)
            if risk_assessment is not None and risk_assessment.confidence is not None
            else None
        )
        report_by_analysis_id[analysis_id] = report
        confidence_by_analysis_id[analysis_id] = confidence
        warning_by_analysis_id[analysis_id] = did_warn
        failed_by_analysis_id[analysis_id] = failed or failed_by_analysis_id.get(
            analysis_id, False
        )
        outcome_confidence_samples.append((analysis_id, confidence, did_warn, failed))
        if did_warn:
            warned_total += 1
            by_severity_counts[severity]["warned"] += 1
        if failed:
            linked_incident = incident_by_analysis_id.get(analysis_id)
            by_severity_counts[severity]["failed"] += 1
            failed_rows.append(
                {
                    "analysis_id": outcome.analysis_id,
                    "incident_id": outcome.linked_incident_id
                    or (linked_incident.id if linked_incident is not None else None),
                    "outcome": outcome.outcome_label,
                    "severity": severity,
                    "recommendation": report.recommendation
                    if report is not None
                    else None,
                    "did_warn": did_warn,
                    "deployed_at": _serialize_timestamp(outcome.deployed_at),
                }
            )
            if did_warn:
                true_positive += 1
                by_severity_counts[severity]["true_positive"] += 1
            else:
                failed_without_warning_count += 1

    failed_deploy_count = len(failed_rows)
    overall_precision = true_positive / warned_total if warned_total else 0.0
    overall_recall = true_positive / failed_deploy_count if failed_deploy_count else 0.0

    latest_finding_feedback: dict[tuple[int | None, str], FeedbackEvent] = {}
    latest_false_negative_feedback: dict[
        tuple[int | None, str | None], FeedbackEvent
    ] = {}
    for event in feedback_events:
        if event.finding_id is not None and event.false_negative_note is None:
            latest_finding_feedback.setdefault(
                (event.analysis_id, event.finding_id), event
            )
        if event.false_negative_note:
            latest_false_negative_feedback.setdefault(
                (event.analysis_id, event.finding_id), event
            )

    false_positive_cases = [
        _serialize_feedback_case(
            event=event,
            report=report_by_analysis_id.get(int(event.analysis_id)),
            reason="reviewer_false_positive_feedback",
        )
        for event in latest_finding_feedback.values()
        if event.analysis_id is not None and bool(event.false_positive_flag)
    ]
    false_positive_count = len(false_positive_cases)
    effective_finding_feedback_count = len(latest_finding_feedback)
    false_positive_denominator = max(
        effective_finding_feedback_count,
        false_positive_count,
    )
    false_positive_rate = (
        false_positive_count / false_positive_denominator
        if false_positive_denominator
        else 0.0
    )

    false_reassurance_cases: list[dict[str, Any]] = []
    for failed_row in failed_rows:
        if failed_row["did_warn"] or failed_row["analysis_id"] is None:
            continue
        analysis_id = int(failed_row["analysis_id"])
        false_reassurance_cases.append(
            {
                "analysis_id": analysis_id,
                "finding_id": None,
                "reason": "failed_without_warning",
                "note": "Deployment failed or rolled back after a GO report.",
                "severity": failed_row["severity"],
                "recommendation": failed_row["recommendation"],
                "deployed_at": failed_row["deployed_at"],
            }
        )
    for event in latest_false_negative_feedback.values():
        if event.analysis_id is None:
            continue
        analysis_id = int(event.analysis_id)
        if warning_by_analysis_id.get(analysis_id, False):
            continue
        if analysis_id in analysis_ids and not failed_by_analysis_id.get(
            analysis_id, False
        ):
            continue
        report = report_by_analysis_id.get(analysis_id)
        false_reassurance_cases.append(
            _serialize_feedback_case(
                event=event,
                report=report,
                reason="reviewer_missed_finding_feedback",
            )
        )
    false_reassurance_cases.sort(
        key=_calibration_case_event_timestamp,
        reverse=True,
    )
    false_reassurance_count = len(false_reassurance_cases)
    false_reassurance_rate = (
        failed_without_warning_count / failed_deploy_count
        if failed_deploy_count
        else 0.0
    )

    confidence_accumulators: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "sample_count": 0,
            "numeric_confidence_count": 0,
            "confidence_sum": 0.0,
            "warned_count": 0,
            "failed_count": 0,
            "true_positive_count": 0,
            "false_positive_count": 0,
            "false_reassurance_count": 0,
        }
    )
    for analysis_id, confidence, did_warn, failed in outcome_confidence_samples:
        bucket = _confidence_bucket(confidence)
        bucket_payload = confidence_accumulators[bucket]
        bucket_payload["sample_count"] = int(bucket_payload["sample_count"]) + 1
        if confidence is not None:
            bucket_payload["numeric_confidence_count"] = (
                int(bucket_payload["numeric_confidence_count"]) + 1
            )
            bucket_payload["confidence_sum"] = (
                float(bucket_payload["confidence_sum"]) + confidence
            )
        if did_warn:
            bucket_payload["warned_count"] = int(bucket_payload["warned_count"]) + 1
        if failed:
            bucket_payload["failed_count"] = int(bucket_payload["failed_count"]) + 1
            if did_warn:
                bucket_payload["true_positive_count"] = (
                    int(bucket_payload["true_positive_count"]) + 1
                )
    outcome_sample_analysis_ids = {
        analysis_id for analysis_id, _, _, _ in outcome_confidence_samples
    }
    false_positive_bucket_analysis_ids: set[int] = set()
    for case in false_positive_cases:
        analysis_id = case.get("analysis_id")
        if analysis_id is None or int(analysis_id) not in outcome_sample_analysis_ids:
            continue
        if int(analysis_id) in false_positive_bucket_analysis_ids:
            continue
        false_positive_bucket_analysis_ids.add(int(analysis_id))
        bucket = _confidence_bucket(confidence_by_analysis_id.get(int(analysis_id)))
        confidence_accumulators[bucket]["false_positive_count"] = (
            int(confidence_accumulators[bucket]["false_positive_count"]) + 1
        )
    false_reassurance_bucket_analysis_ids: set[int] = set()
    for case in false_reassurance_cases:
        analysis_id = case.get("analysis_id")
        if analysis_id is None or int(analysis_id) not in outcome_sample_analysis_ids:
            continue
        if int(analysis_id) in false_reassurance_bucket_analysis_ids:
            continue
        false_reassurance_bucket_analysis_ids.add(int(analysis_id))
        bucket = _confidence_bucket(confidence_by_analysis_id.get(int(analysis_id)))
        confidence_accumulators[bucket]["false_reassurance_count"] = (
            int(confidence_accumulators[bucket]["false_reassurance_count"]) + 1
        )
    confidence_buckets = {}
    for bucket, values in confidence_accumulators.items():
        sample_count = int(values["sample_count"])
        numeric_confidence_count = int(values["numeric_confidence_count"])
        confidence_buckets[bucket] = {
            "sample_count": sample_count,
            "average_confidence": (
                float(values["confidence_sum"]) / numeric_confidence_count
                if numeric_confidence_count
                else None
            ),
            "warned_count": int(values["warned_count"]),
            "failed_count": int(values["failed_count"]),
            "true_positive_count": int(values["true_positive_count"]),
            "false_positive_count": int(values["false_positive_count"]),
            "false_reassurance_count": int(values["false_reassurance_count"]),
        }

    useful_feedback_count = sum(
        1
        for event in latest_finding_feedback.values()
        if not bool(event.false_positive_flag) and bool(event.useful)
    )
    neutral_feedback_count = (
        effective_finding_feedback_count - false_positive_count - useful_feedback_count
    )
    effective_feedback_count = effective_finding_feedback_count + len(
        latest_false_negative_feedback
    )
    limitations = _calibration_limitations(
        sample_size=outcome_report_count,
        feedback_event_count=effective_feedback_count,
        feedback_history_event_count=len(feedback_history_events),
        false_positive_count=false_positive_count,
        missed_feedback_count=len(latest_false_negative_feedback),
        useful_feedback_count=useful_feedback_count,
        neutral_feedback_count=neutral_feedback_count,
    )

    by_severity = {
        severity: {
            "precision": (
                counts["true_positive"] / counts["warned"] if counts["warned"] else 0.0
            ),
            "recall": (
                counts["true_positive"] / counts["failed"] if counts["failed"] else 0.0
            ),
            "warned_count": counts["warned"],
            "failed_count": counts["failed"],
        }
        for severity, counts in by_severity_counts.items()
    }

    return {
        "project": build_project_payload(project),
        "workspace": build_workspace_payload(workspace)
        if workspace is not None
        else None,
        "window": {
            "start": _serialize_timestamp(window_start),
            "end": _serialize_timestamp(window_end),
            "days": BACKTEST_WINDOW_DAYS,
        },
        "failed_deploy_count": failed_deploy_count,
        "warned_failed_deploy_count": true_positive,
        "overall_precision": overall_precision,
        "overall_recall": overall_recall,
        "backtest_rows": failed_rows,
        "by_severity": by_severity,
        "false_positive_cases": false_positive_cases,
        "false_reassurance_cases": false_reassurance_cases,
        "confidence_trends": {
            "buckets": confidence_buckets,
            "sample_size": outcome_report_count,
        },
        "confidence_limitations": limitations,
        "confidence_label": "Calibrated" if not limitations else "Directional only",
        "statistical_certainty": not limitations,
        "calibration_metrics": {
            "sample_size": outcome_report_count,
            "feedback_event_count": effective_feedback_count,
            "feedback_history_event_count": len(feedback_history_events),
            "precision": overall_precision,
            "recall_proxy": overall_recall,
            "false_positive_count": false_positive_count,
            "false_positive_rate": false_positive_rate,
            "false_reassurance_count": false_reassurance_count,
            "false_reassurance_rate": false_reassurance_rate,
            "deployment_false_reassurance_count": failed_without_warning_count,
            "reviewer_missed_feedback_count": len(latest_false_negative_feedback),
            "recall_proxy_signals": {
                "failed_deploy_count": failed_deploy_count,
                "warned_failed_deploy_count": true_positive,
                "failed_without_warning_count": failed_without_warning_count,
                "missed_feedback_count": len(latest_false_negative_feedback),
            },
        },
    }


def invalidate_backtesting_snapshot(*, project_id: int) -> None:
    with SessionLocal() as session:
        delete_setting(session, _snapshot_key(project_id))
        delete_settings_by_key_prefix(
            session,
            f"{_snapshot_key(project_id)}:workspace:",
        )


def run_weekly_backtest(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    now: datetime | None = None,
    record_last_run: bool = True,
) -> dict[str, Any]:
    reference_now = now or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)
    project = resolve_project_reference(project_id=project_id, project_key=project_key)
    workspace = resolve_workspace_reference(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    window_start = reference_now - timedelta(days=BACKTEST_WINDOW_DAYS)
    rows = _outcome_rows(
        project_id=project.id,
        workspace_id=workspace.id if workspace is not None else None,
        window_start=window_start,
        window_end=reference_now,
    )
    summary = _build_summary(
        project=project,
        workspace=workspace,
        rows=rows,
        window_start=window_start,
        window_end=reference_now,
    )
    with SessionLocal() as session:
        if record_last_run and workspace is None:
            upsert_setting(
                session,
                key=_last_run_key(project.id),
                value=_serialize_timestamp(reference_now),
            )
        upsert_setting(
            session,
            key=_snapshot_key(
                project.id,
                workspace.id if workspace is not None else None,
            ),
            value=json.dumps(summary),
        )
    return summary


def run_incident_backtest(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Replay incident-linked artifacts through the current analysis core."""

    project = resolve_project_reference(project_id=project_id, project_key=project_key)
    workspace = resolve_workspace_reference(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    generated_at = _serialize_timestamp(now or datetime.now(UTC))
    with SessionLocal() as session:
        incidents = list_incident_records(
            session,
            project_id=project.id,
            workspace_id=workspace.id if workspace is not None else None,
        )
        scenarios = [
            _run_incident_backtest_scenario(
                incident=incident,
                report=_incident_linked_report(
                    session=session,
                    incident=incident,
                    project_id=project.id,
                    workspace_id=workspace.id if workspace is not None else None,
                ),
            )
            for incident in incidents
        ]
    counts = {
        status: sum(1 for scenario in scenarios if scenario["status"] == status)
        for status in INCIDENT_BACKTEST_STATUSES
    }
    summary = {
        "project_id": project.id,
        "project_key": project.project_key,
        "workspace_id": workspace.id if workspace is not None else None,
        "workspace_key": workspace.workspace_key if workspace is not None else None,
        "scenario_count": len(scenarios),
        "detected_count": counts["detected"],
        "missed_count": counts["missed"],
        "unsupported_count": counts["unsupported"],
        "insufficient_context_count": counts["insufficient_context"],
        "error_count": counts["error"],
        "generated_at": generated_at,
    }
    return {
        "passed": counts["missed"] == 0 and counts["error"] == 0,
        "project": build_project_payload(project),
        "workspace": build_workspace_payload(workspace)
        if workspace is not None
        else None,
        "summary": summary,
        "scenarios": scenarios,
        "errors": [
            reason
            for scenario in scenarios
            if scenario["status"] == "error"
            for reason in scenario["reasons"]
        ],
    }


def run_due_weekly_backtests(*, now: datetime | None = None) -> list[dict[str, Any]]:
    reference_now = now or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)
    summaries: list[dict[str, Any]] = []
    for project in list_projects():
        with SessionLocal() as session:
            last_run = get_setting(session, _last_run_key(project.id))
        if last_run is not None:
            last_run_at = _coerce_utc_timestamp(last_run.value)
            if reference_now - last_run_at < timedelta(days=BACKTEST_WINDOW_DAYS):
                continue
        try:
            summaries.append(
                run_weekly_backtest(project_id=project.id, now=reference_now)
            )
        except Exception:
            logger.exception("Weekly backtesting failed for project %s.", project.id)
    return summaries


def fetch_calibration_dashboard_seed(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    reference_now = now or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)
    else:
        reference_now = reference_now.astimezone(UTC)
    project = resolve_project_reference(project_id=project_id, project_key=project_key)
    workspace = resolve_workspace_reference(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    with SessionLocal() as session:
        snapshot = get_setting(
            session,
            _snapshot_key(
                project.id,
                workspace.id if workspace is not None else None,
            ),
        )
    if snapshot is not None:
        try:
            snapshot_payload = json.loads(snapshot.value)
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid cached calibration snapshot for project %s.",
                project.id,
            )
            snapshot_payload = None
        if isinstance(snapshot_payload, dict) and _cached_snapshot_is_usable(
            snapshot_payload,
            project_id=project.id,
            workspace_id=workspace.id if workspace is not None else None,
            now=reference_now,
        ):
            return snapshot_payload
    return run_weekly_backtest(
        project_id=project.id,
        workspace_id=workspace.id if workspace is not None else None,
        now=reference_now,
        record_last_run=False,
    )
