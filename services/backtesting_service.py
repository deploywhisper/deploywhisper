"""Weekly outcome backtesting and calibration feed helpers."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from models.database import SessionLocal
from models.repositories.settings import delete_setting, get_setting, upsert_setting
from models.tables import AnalysisReport, DeploymentOutcome, IncidentRecord
from services.project_service import (
    build_project_payload,
    list_projects,
    resolve_project_reference,
)

BACKTEST_WINDOW_DAYS = 7
BACKTEST_LAST_RUN_KEY = "backtesting:last_run_at:project:"
BACKTEST_SNAPSHOT_KEY = "backtesting:snapshot:project:"

logger = logging.getLogger(__name__)


def _last_run_key(project_id: int) -> str:
    return f"{BACKTEST_LAST_RUN_KEY}{project_id}"


def _snapshot_key(project_id: int) -> str:
    return f"{BACKTEST_SNAPSHOT_KEY}{project_id}"


def _warned(report: AnalysisReport | None) -> bool:
    if report is None:
        return False
    return str(report.recommendation or "").lower() != "go"


def _outcome_rows(
    *,
    project_id: int,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[DeploymentOutcome, AnalysisReport | None]]:
    with SessionLocal() as session:
        stmt = (
            select(DeploymentOutcome, AnalysisReport)
            .join(
                AnalysisReport,
                DeploymentOutcome.analysis_id == AnalysisReport.id,
                isouter=True,
            )
            .where(DeploymentOutcome.project_id == project_id)
            .where(DeploymentOutcome.deployed_at >= window_start)
            .where(DeploymentOutcome.deployed_at <= window_end)
            .order_by(DeploymentOutcome.deployed_at.asc(), DeploymentOutcome.id.asc())
        )
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


def _coerce_utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed


def _build_summary(
    *,
    project,
    rows: list[tuple[DeploymentOutcome, AnalysisReport | None]],
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    failed_rows: list[dict[str, Any]] = []
    warned_total = 0
    true_positive = 0
    by_severity_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"warned": 0, "failed": 0, "true_positive": 0}
    )
    analysis_ids = {
        int(outcome.analysis_id)
        for outcome, _ in rows
        if outcome.analysis_id is not None
    }
    incidents = _incident_rows(project_id=project.id, analysis_ids=analysis_ids)
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

    for outcome, report in rows:
        if outcome.analysis_id is None or report is None:
            continue
        did_warn = _warned(report)
        failed = outcome.outcome_label in {"failure", "rolled_back"}
        severity = str(report.severity if report is not None else "unknown").lower()
        analysis_id = int(outcome.analysis_id)
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

    failed_deploy_count = len(failed_rows)
    overall_precision = true_positive / warned_total if warned_total else 0.0
    overall_recall = true_positive / failed_deploy_count if failed_deploy_count else 0.0

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
    }


def invalidate_backtesting_snapshot(*, project_id: int) -> None:
    with SessionLocal() as session:
        delete_setting(session, _snapshot_key(project_id))


def run_weekly_backtest(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    now: datetime | None = None,
    record_last_run: bool = True,
) -> dict[str, Any]:
    reference_now = now or datetime.now(UTC)
    if reference_now.tzinfo is None:
        reference_now = reference_now.replace(tzinfo=UTC)
    project = resolve_project_reference(project_id=project_id, project_key=project_key)
    window_start = reference_now - timedelta(days=BACKTEST_WINDOW_DAYS)
    rows = _outcome_rows(
        project_id=project.id,
        window_start=window_start,
        window_end=reference_now,
    )
    summary = _build_summary(
        project=project,
        rows=rows,
        window_start=window_start,
        window_end=reference_now,
    )
    with SessionLocal() as session:
        if record_last_run:
            upsert_setting(
                session,
                key=_last_run_key(project.id),
                value=_serialize_timestamp(reference_now),
            )
        upsert_setting(
            session,
            key=_snapshot_key(project.id),
            value=json.dumps(summary),
        )
    return summary


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
) -> dict[str, Any]:
    project = resolve_project_reference(project_id=project_id, project_key=project_key)
    with SessionLocal() as session:
        snapshot = get_setting(session, _snapshot_key(project.id))
    if snapshot is not None:
        return json.loads(snapshot.value)
    return run_weekly_backtest(project_id=project.id, record_last_run=False)
