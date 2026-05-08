"""Analysis report repository."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models.tables import (
    AnalysisReport,
    EvidenceItem as PersistedEvidenceItem,
    Finding as PersistedFinding,
    RiskAssessment as PersistedRiskAssessment,
)


def _report_load_options(*, include_evidence: bool) -> list:
    options = [
        selectinload(AnalysisReport.risk_assessment),
        selectinload(AnalysisReport.project),
        selectinload(AnalysisReport.workspace),
    ]
    findings_loader = selectinload(AnalysisReport.findings)
    if include_evidence:
        findings_loader = findings_loader.selectinload(PersistedFinding.evidence_items)
    options.append(findings_loader)
    return options


def create_analysis_report(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    risk_score: int,
    severity: str,
    recommendation: str,
    top_risk: str,
    report_schema_version: str,
    parse_summary: str,
    narrative_opening: str,
    narrative_explanation: str,
    warnings_json: str,
    contributors_json: str,
    analyzed_files_json: str,
    submission_manifest_json: str,
    submission_manifest_fallback_json: str,
    blast_radius_json: str,
    rollback_plan_json: str,
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
    context_completeness_json: str = "{}",
    findings_payload: list[dict[str, Any]] | None = None,
    evidence_payload: list[dict[str, Any]] | None = None,
) -> AnalysisReport:
    report = AnalysisReport(
        project_id=project_id,
        workspace_id=workspace_id,
        risk_score=risk_score,
        severity=severity,
        recommendation=recommendation,
        top_risk=top_risk,
        report_schema_version=report_schema_version,
        parse_summary=parse_summary,
        narrative_opening=narrative_opening,
        narrative_explanation=narrative_explanation,
        warnings_json=warnings_json,
        contributors_json=contributors_json,
        analyzed_files_json=analyzed_files_json,
        submission_manifest_json=submission_manifest_json,
        submission_manifest_fallback_json=submission_manifest_fallback_json,
        blast_radius_json=blast_radius_json,
        rollback_plan_json=rollback_plan_json,
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
    finding_rows: list[tuple[PersistedFinding, list[str]]] = []
    for finding in findings_payload or []:
        persisted_finding = PersistedFinding(
            finding_id=str(finding["finding_id"]),
            title=str(finding["title"]),
            description=str(finding["description"]),
            severity=str(finding["severity"]),
            category=str(finding["category"]),
            deterministic=bool(finding["deterministic"]),
            confidence=float(finding["confidence"]),
            uncertainty_note=(
                str(finding["uncertainty_note"])
                if finding.get("uncertainty_note") is not None
                else None
            ),
            evidence_refs_json=json.dumps(finding.get("evidence_refs", [])),
            skill_id=(
                str(finding["skill_id"])
                if finding.get("skill_id") is not None
                else None
            ),
        )
        finding_rows.append(
            (
                persisted_finding,
                [str(ref) for ref in finding.get("evidence_refs", [])],
            )
        )

    report.risk_assessment = PersistedRiskAssessment(
        overall_severity=severity,
        recommendation=recommendation,
        score=risk_score,
        confidence=1.0,
        top_risk_contributors_json=top_risk_contributors_json,
        context_completeness_json=context_completeness_json,
    )
    report.findings = [persisted_finding for persisted_finding, _ in finding_rows]
    session.add(report)
    session.flush()

    if evidence_payload:
        finding_by_id = {
            persisted_finding.finding_id: persisted_finding
            for persisted_finding in report.findings
        }
        evidence_owner_by_id: dict[str, str] = {}
        for persisted_finding, evidence_refs in finding_rows:
            for evidence_id in evidence_refs:
                evidence_owner_by_id.setdefault(
                    evidence_id, persisted_finding.finding_id
                )

        fallback_owner = report.findings[0] if len(report.findings) == 1 else None
        for evidence in evidence_payload:
            owner_id = evidence_owner_by_id.get(str(evidence["evidence_id"]))
            owner = (
                finding_by_id.get(owner_id) if owner_id is not None else fallback_owner
            )
            if owner is None:
                raise ValueError(
                    "Evidence item "
                    f"{evidence['evidence_id']} could not be attached to a persisted finding."
                )
            owner.evidence_items.append(
                PersistedEvidenceItem(
                    evidence_id=str(evidence["evidence_id"]),
                    analysis_id=report.id,
                    finding_id=owner.finding_id,
                    source_type=str(evidence["source_type"]),
                    source_ref=str(evidence["source_ref"]),
                    summary=str(evidence["summary"]),
                    severity_hint=str(evidence["severity_hint"]),
                    deterministic=bool(evidence["deterministic"]),
                    confidence=float(evidence["confidence"]),
                    related_change_ids_json=json.dumps(
                        evidence.get("related_change_ids", [])
                    ),
                )
            )

    session.commit()
    session.refresh(report, attribute_names=["risk_assessment", "findings"])
    return report


def get_analysis_report(
    session: Session,
    report_id: int,
    *,
    project_id: int | None = None,
    workspace_id: int | None = None,
    include_evidence: bool = True,
) -> AnalysisReport | None:
    stmt = (
        select(AnalysisReport)
        .options(*_report_load_options(include_evidence=include_evidence))
        .where(AnalysisReport.id == report_id)
    )
    if project_id is not None:
        stmt = stmt.where(AnalysisReport.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(AnalysisReport.workspace_id == workspace_id)
    return session.execute(stmt).scalar_one_or_none()


def update_analysis_report_share_settings(
    session: Session,
    report_id: int,
    *,
    share_password_hash: str | None,
    share_password_salt: str | None,
    share_redact_filenames: bool,
) -> AnalysisReport | None:
    report = session.get(AnalysisReport, report_id)
    if report is None:
        return None
    report.share_password_hash = share_password_hash
    report.share_password_salt = share_password_salt
    report.share_redact_filenames = share_redact_filenames
    session.commit()
    session.refresh(report)
    return report


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
    project_id: int | None = None,
    workspace_id: int | None = None,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    include_evidence: bool = False,
) -> list[AnalysisReport]:
    stmt = (
        select(AnalysisReport)
        .options(*_report_load_options(include_evidence=include_evidence))
        .order_by(AnalysisReport.id.desc())
    )
    if project_id is not None:
        stmt = stmt.where(AnalysisReport.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(AnalysisReport.workspace_id == workspace_id)
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
    project_id: int | None = None,
    workspace_id: int | None = None,
    severity: str | None = None,
    recommendation: str | None = None,
    search: str | None = None,
) -> int:
    stmt = select(func.count()).select_from(AnalysisReport)
    if project_id is not None:
        stmt = stmt.where(AnalysisReport.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(AnalysisReport.workspace_id == workspace_id)
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
    session: Session,
    field_name: str,
    *,
    project_id: int | None = None,
    workspace_id: int | None = None,
) -> dict[str, int]:
    column = getattr(AnalysisReport, field_name)
    stmt = select(column, func.count()).group_by(column)
    if project_id is not None:
        stmt = stmt.where(AnalysisReport.project_id == project_id)
    if workspace_id is not None:
        stmt = stmt.where(AnalysisReport.workspace_id == workspace_id)
    rows = session.execute(stmt).all()
    return {str(value): int(count) for value, count in rows if value is not None}


def latest_active_dashboard_report(
    session: Session,
    *,
    now: datetime | None = None,
    project_id: int | None = None,
    workspace_id: int | None = None,
) -> AnalysisReport | None:
    current_time = now or datetime.now(UTC)
    reports = list_analysis_reports(
        session,
        project_id=project_id,
        workspace_id=workspace_id,
        include_evidence=False,
    )
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
