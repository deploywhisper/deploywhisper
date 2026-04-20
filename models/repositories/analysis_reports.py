"""Analysis report repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.tables import AnalysisReport, RiskAssessment as PersistedRiskAssessment


def create_analysis_report(
    session: Session,
    *,
    risk_score: int,
    severity: str,
    recommendation: str,
    top_risk: str,
    parse_summary: str,
    narrative_opening: str,
    narrative_explanation: str,
    warnings_json: str,
    contributors_json: str,
    analyzed_files_json: str,
    llm_provider: str | None,
    llm_model: str | None,
    llm_local_mode: str | None,
    assessment_source: str | None,
    narrative_source: str | None,
    narrative_skills_json: str | None,
    source_interface: str | None,
    trigger_type: str | None,
    trigger_id: str | None,
    dashboard_display_duration_seconds: int | None,
    top_risk_contributors_json: str = "[]",
) -> AnalysisReport:
    report = AnalysisReport(
        risk_score=risk_score,
        severity=severity,
        recommendation=recommendation,
        top_risk=top_risk,
        parse_summary=parse_summary,
        narrative_opening=narrative_opening,
        narrative_explanation=narrative_explanation,
        warnings_json=warnings_json,
        contributors_json=contributors_json,
        analyzed_files_json=analyzed_files_json,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_local_mode=llm_local_mode,
        assessment_source=assessment_source,
        narrative_source=narrative_source,
        narrative_skills_json=narrative_skills_json,
        source_interface=source_interface,
        trigger_type=trigger_type,
        trigger_id=trigger_id,
        dashboard_display_duration_seconds=dashboard_display_duration_seconds,
    )
    report.risk_assessment = PersistedRiskAssessment(
        overall_severity=severity,
        recommendation=recommendation,
        score=risk_score,
        confidence=1.0,
        top_risk_contributors_json=top_risk_contributors_json,
        context_completeness_json="{}",
    )
    session.add(report)
    session.commit()
    session.refresh(report, attribute_names=["risk_assessment"])
    return report


def get_analysis_report(session: Session, report_id: int) -> AnalysisReport | None:
    stmt = (
        select(AnalysisReport)
        .options(selectinload(AnalysisReport.risk_assessment))
        .where(AnalysisReport.id == report_id)
    )
    return session.execute(stmt).scalar_one_or_none()


def delete_analysis_report(session: Session, report_id: int) -> bool:
    report = session.get(AnalysisReport, report_id)
    if report is None:
        return False
    session.delete(report)
    session.commit()
    return True


def list_analysis_reports(
    session: Session,
    *,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[AnalysisReport]:
    stmt = (
        select(AnalysisReport)
        .options(selectinload(AnalysisReport.risk_assessment))
        .order_by(AnalysisReport.id.desc())
    )
    if severity:
        stmt = stmt.where(AnalysisReport.severity == severity)
    if recommendation:
        stmt = stmt.where(AnalysisReport.recommendation == recommendation)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            AnalysisReport.top_risk.ilike(like)
            | AnalysisReport.narrative_opening.ilike(like)
            | AnalysisReport.parse_summary.ilike(like)
        )
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = session.execute(stmt)
    return list(result.scalars().all())


def count_analysis_reports(
    session: Session,
    *,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(AnalysisReport)
    if severity:
        stmt = stmt.where(AnalysisReport.severity == severity)
    if recommendation:
        stmt = stmt.where(AnalysisReport.recommendation == recommendation)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            AnalysisReport.top_risk.ilike(like)
            | AnalysisReport.narrative_opening.ilike(like)
            | AnalysisReport.parse_summary.ilike(like)
        )
    return int(session.execute(stmt).scalar_one())


def count_analysis_reports_by_field(
    session: Session, field_name: str
) -> dict[str, int]:
    column = getattr(AnalysisReport, field_name)
    stmt = select(column, func.count()).group_by(column)
    rows = session.execute(stmt).all()
    return {str(value): int(count) for value, count in rows if value is not None}


def latest_active_dashboard_report(
    session: Session, *, now: datetime | None = None
) -> AnalysisReport | None:
    current_time = now or datetime.now(UTC)
    reports = list_analysis_reports(session)
    for report in reports:
        duration = report.dashboard_display_duration_seconds or 0
        if duration <= 0:
            continue
        created_at = report.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if created_at + timedelta(seconds=duration) > current_time:
            return report
    return None
