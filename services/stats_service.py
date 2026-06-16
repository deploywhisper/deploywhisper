"""Read-only dashboard statistics service helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from models.database import SessionLocal
from models.repositories.analysis_reports import list_analysis_reports
from services.project_service import (
    resolve_project_reference,
    resolve_workspace_reference,
)

_SEVERITIES_HIGH_CRITICAL = {"high", "critical"}
_VERDICT_KEYS = ("go", "caution", "no-go")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_scope(
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
    if project_id is not None or project_key is not None:
        project = resolve_project_reference(
            project_id=project_id,
            project_key=project_key,
        )
        return project.id, None
    return None, None


def _bucket_dates(*, today: date) -> list[date]:
    start = today - timedelta(days=6)
    return [start + timedelta(days=offset) for offset in range(7)]


def _duration_values(reports) -> list[int]:
    values: list[int] = []
    for report in reports:
        duration = int(getattr(report, "analysis_duration_seconds", 0) or 0)
        if duration > 0:
            values.append(duration)
    return values


def _average_duration(reports) -> float | None:
    durations = _duration_values(reports)
    if not durations:
        return None
    return round(sum(durations) / len(durations), 2)


def _clean_rate(reports) -> float:
    total = len(reports)
    if total == 0:
        return 0.0
    clean = sum(1 for report in reports if report.severity == "low")
    return round((clean / total) * 100, 2)


def _bucket_payload(bucket: date, value: float | int | None) -> dict[str, float | str]:
    return {"date": bucket.isoformat(), "value": float(value or 0)}


def fetch_stats_summary(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Return dashboard KPI aggregates and seven daily sparkline buckets."""
    scoped_project_id, scoped_workspace_id = _resolve_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    with SessionLocal() as session:
        reports = list_analysis_reports(
            session,
            project_id=scoped_project_id,
            workspace_id=scoped_workspace_id,
            include_evidence=False,
            order_by_activity=False,
        )

    total_analyses = len(reports)
    open_high_critical_count = sum(
        1
        for report in reports
        if str(report.severity).lower() in _SEVERITIES_HIGH_CRITICAL
    )
    avg_time_to_verdict_seconds = _average_duration(reports)
    clean_verdict_rate = _clean_rate(reports)

    today = _as_utc(now or datetime.now(UTC)).date()
    buckets = _bucket_dates(today=today)
    bucketed: dict[date, list] = defaultdict(list)
    bucket_set = set(buckets)
    for report in reports:
        report_date = _as_utc(report.created_at).date()
        if report_date in bucket_set:
            bucketed[report_date].append(report)

    series = {
        "analyses": [],
        "clean_verdict_rate": [],
        "open_high_critical_count": [],
        "avg_time_to_verdict_seconds": [],
    }
    for bucket in buckets:
        bucket_reports = bucketed.get(bucket, [])
        series["analyses"].append(_bucket_payload(bucket, len(bucket_reports)))
        series["clean_verdict_rate"].append(
            _bucket_payload(bucket, _clean_rate(bucket_reports))
        )
        series["open_high_critical_count"].append(
            _bucket_payload(
                bucket,
                sum(
                    1
                    for report in bucket_reports
                    if str(report.severity).lower() in _SEVERITIES_HIGH_CRITICAL
                ),
            )
        )
        series["avg_time_to_verdict_seconds"].append(
            _bucket_payload(bucket, _average_duration(bucket_reports))
        )

    totals = {
        "analyses": total_analyses,
        "clean_verdict_rate": clean_verdict_rate,
        "open_high_critical_count": open_high_critical_count,
        "avg_time_to_verdict_seconds": avg_time_to_verdict_seconds,
    }
    return {
        "totals": totals,
        "total_analyses": total_analyses,
        "clean_verdict_rate": clean_verdict_rate,
        "open_high_critical_count": open_high_critical_count,
        "avg_time_to_verdict_seconds": avg_time_to_verdict_seconds,
        "series": series,
    }


def fetch_verdict_distribution(
    *,
    days: int = 30,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Return advisory recommendation counts for a lookback window."""
    days = max(1, min(int(days), 365))
    window_end = _as_utc(now or datetime.now(UTC))
    window_start = window_end - timedelta(days=days)
    scoped_project_id, scoped_workspace_id = _resolve_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    with SessionLocal() as session:
        reports = list_analysis_reports(
            session,
            project_id=scoped_project_id,
            workspace_id=scoped_workspace_id,
            created_from=window_start,
            created_to=window_end,
            include_evidence=False,
            order_by_activity=False,
        )

    counts = Counter(str(report.recommendation).strip().lower() for report in reports)
    distribution = {key: counts.get(key, 0) for key in _VERDICT_KEYS}
    return {
        "days": days,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "counts": distribution,
        "total": sum(distribution.values()),
    }
