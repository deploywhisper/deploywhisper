"""Analysis report repository."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from evidence.models import EvidenceItem as EvidenceItemPayload
from evidence.models import Finding as FindingPayload
from models.tables import (
    AnalysisReport,
    EvidenceItem as PersistedEvidenceItem,
    Finding as PersistedFinding,
    RiskAssessment as PersistedRiskAssessment,
)

_FINDING_SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_SEVERITY_SCORE_FLOOR = {"low": 0, "medium": 42, "high": 70, "critical": 90}
_SEVERITY_SCORE_CEILING = {"low": 39, "medium": 69, "high": 89, "critical": 100}
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


def _normalize_report_severity(severity: str) -> str:
    normalized_severity = str(severity).strip().lower()
    if normalized_severity not in _FINDING_SEVERITY_ORDER:
        raise ValueError(f"Unsupported report severity {severity!r}.")
    return normalized_severity


def _normalize_risk_confidence(confidence: float) -> float:
    normalized = float(confidence)
    if not math.isfinite(normalized) or normalized < 0.0 or normalized > 1.0:
        raise ValueError("Risk confidence must be between 0 and 1.")
    return normalized


def _verdict_label(value: str | None) -> str | None:
    match = _VERDICT_PREFIX_PATTERN.match(str(value or ""))
    if match is None:
        return None
    return match.group(1).lower()


def _verdict_text_contradicts_metadata(
    value: str | None,
    report_severity: str,
    report_recommendation: str,
) -> bool:
    label = _verdict_label(value)
    if label is None:
        return False
    recommendation = str(report_recommendation).strip().lower()
    if label in _FINDING_SEVERITY_ORDER:
        return label != report_severity
    if label in {"go", "caution", "no-go"}:
        return label != recommendation
    return False


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


def _validate_report_verdict_text(
    report_severity: str,
    report_recommendation: str,
    *values: str | None,
) -> None:
    if any(
        _verdict_text_contradicts_metadata(
            value,
            report_severity,
            report_recommendation,
        )
        for value in values
    ):
        raise ValueError("Report verdict text contradicts severity metadata.")


def _validate_top_risk_contributor_refs(
    top_risk_contributors_json: str,
    evidence_finding_by_id: dict[str, PersistedFinding],
    report_severity: str,
) -> None:
    try:
        top_risk_contributors = json.loads(top_risk_contributors_json or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Top-risk contributors must be valid JSON.") from exc
    if not isinstance(top_risk_contributors, list) or any(
        not isinstance(evidence_id, str) or not evidence_id.strip()
        for evidence_id in top_risk_contributors
    ):
        raise ValueError("Top-risk contributors must be a list of evidence IDs.")
    if len(top_risk_contributors) != len(set(top_risk_contributors)):
        raise ValueError("Top-risk contributors must not repeat evidence IDs.")
    if report_severity in {"high", "critical"} and not top_risk_contributors:
        raise ValueError(
            "High/critical reports must persist top-risk contributor evidence IDs."
        )
    missing_evidence_ids = [
        evidence_id
        for evidence_id in top_risk_contributors
        if evidence_id not in evidence_finding_by_id
    ]
    if missing_evidence_ids:
        raise ValueError(
            "Top-risk contributor "
            f"{missing_evidence_ids[0]} does not reference persisted evidence."
        )
    owner_ids = {
        evidence_finding_by_id[evidence_id].finding_id
        for evidence_id in top_risk_contributors
    }
    if len(owner_ids) > 1:
        raise ValueError("Top-risk contributors must belong to one persisted finding.")
    if report_severity in {"high", "critical"} and any(
        evidence_finding_by_id[evidence_id].severity != report_severity
        for evidence_id in top_risk_contributors
    ):
        raise ValueError(
            "Top-risk contributors must reference the report's severe finding."
        )


def _validate_finding_evidence_refs(
    finding_rows: list[tuple[PersistedFinding, list[str]]],
    evidence_payload: list[dict[str, Any]] | None,
    report_severity: str,
    report_score: int,
    report_recommendation: str,
) -> dict[str, PersistedFinding]:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for evidence in evidence_payload or []:
        evidence_id = str(evidence["evidence_id"])
        if evidence_id in evidence_by_id:
            raise ValueError(
                f"Duplicate evidence item {evidence_id} in report payload."
            )
        evidence_by_id[evidence_id] = evidence

    evidence_claims_by_id: dict[str, list[PersistedFinding]] = {}
    evidence_finding_by_id: dict[str, PersistedFinding] = {}
    for persisted_finding, evidence_refs in finding_rows:
        if len(evidence_refs) != len(set(evidence_refs)):
            raise ValueError(
                f"Finding {persisted_finding.finding_id} repeats evidence refs."
            )
        for evidence_id in evidence_refs:
            if evidence_id not in evidence_by_id:
                raise ValueError(
                    "Finding "
                    f"{persisted_finding.finding_id} references missing evidence item "
                    f"{evidence_id}."
                )
            evidence_claims_by_id.setdefault(evidence_id, []).append(persisted_finding)
        if persisted_finding.severity in {"high", "critical"}:
            linked_deterministic_classifications = {
                _evidence_classification(evidence_by_id[evidence_id])
                for evidence_id in evidence_refs
                if evidence_id in evidence_by_id
                and _is_deterministic_evidence(evidence_by_id[evidence_id])
            }
            if not linked_deterministic_classifications:
                raise ValueError(
                    "Finding "
                    f"{persisted_finding.finding_id} has {persisted_finding.severity} "
                    "severity without linked deterministic evidence."
                )
            if (
                not persisted_finding.deterministic
                or persisted_finding.evidence_classification
                not in linked_deterministic_classifications
            ):
                raise ValueError(
                    "Finding "
                    f"{persisted_finding.finding_id} metadata contradicts linked "
                    "deterministic evidence."
                )

    for evidence_id, claimants in evidence_claims_by_id.items():
        evidence_owner_id = str(evidence_by_id[evidence_id].get("finding_id") or "")
        owner = next(
            (
                persisted_finding
                for persisted_finding in claimants
                if persisted_finding.finding_id == evidence_owner_id
            ),
            None,
        )
        if owner is None:
            if len(claimants) == 1:
                owner = claimants[0]
            else:
                raise ValueError(
                    f"Evidence item {evidence_id} has ambiguous finding ownership."
                )
        evidence_finding_by_id[evidence_id] = owner

    strongest_supported_severity = max(
        (
            _FINDING_SEVERITY_ORDER[persisted_finding.severity]
            for persisted_finding, evidence_refs in finding_rows
            if persisted_finding.severity in {"high", "critical"}
            and any(
                _is_deterministic_evidence(evidence_by_id[evidence_id])
                for evidence_id in evidence_refs
                if evidence_id in evidence_by_id
            )
        ),
        default=0,
    )
    if (
        report_severity in {"high", "critical"}
        and strongest_supported_severity < (_FINDING_SEVERITY_ORDER[report_severity])
    ):
        raise ValueError(
            "Report has high/critical severity without a linked deterministic severe "
            "finding."
        )
    if (
        strongest_supported_severity >= _FINDING_SEVERITY_ORDER["high"]
        and _FINDING_SEVERITY_ORDER[report_severity] < strongest_supported_severity
    ):
        raise ValueError(
            "Report severity understates linked deterministic severe finding."
        )
    if (
        not _recommendation_matches_severity(
            report_recommendation,
            report_severity,
        )
        or report_score < _SEVERITY_SCORE_FLOOR[report_severity]
        or report_score > _SEVERITY_SCORE_CEILING[report_severity]
    ):
        raise ValueError("Report has severity with inconsistent verdict metadata.")
    unclaimed_evidence_ids = set(evidence_by_id) - set(evidence_finding_by_id)
    if unclaimed_evidence_ids:
        evidence_id = sorted(unclaimed_evidence_ids)[0]
        raise ValueError(
            f"Evidence item {evidence_id} is not referenced by any persisted finding."
        )
    return evidence_finding_by_id


def _is_deterministic_evidence(evidence: dict[str, Any]) -> bool:
    determinism_level = str(evidence.get("determinism_level") or "deterministic")
    return (
        evidence.get("deterministic") is True and determinism_level == "deterministic"
    )


def _evidence_classification(evidence: dict[str, Any]) -> str:
    source_kind = str(evidence.get("source_kind") or evidence.get("source_type") or "")
    if source_kind == "external_scanner":
        return "external"
    if source_kind == "user_context":
        return "user_provided"
    determinism_level = str(evidence.get("determinism_level") or "deterministic")
    if determinism_level == "heuristic":
        return "derived"
    if determinism_level == "inferred":
        return "model_inferred"
    return "deterministic" if _is_deterministic_evidence(evidence) else "model_inferred"


def _normalize_evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    if "deterministic" not in evidence:
        return EvidenceItemPayload.model_validate(evidence).model_dump(mode="json")
    strict_evidence = {
        **evidence,
        "deterministic": evidence.get("deterministic")
        if isinstance(evidence.get("deterministic"), bool)
        else False,
    }
    return EvidenceItemPayload.model_validate(strict_evidence).model_dump(mode="json")


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
    risk_confidence: float = 1.0,
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
    narrative_degraded: bool | None = None,
    narrative_failure_notice: str | None = None,
    top_risk_contributors_json: str = "[]",
    context_completeness_json: str = "{}",
    findings_payload: list[dict[str, Any]] | None = None,
    evidence_payload: list[dict[str, Any]] | None = None,
) -> AnalysisReport:
    severity = _normalize_report_severity(severity)
    risk_confidence = _normalize_risk_confidence(risk_confidence)
    evidence_payload = [
        _normalize_evidence_payload(evidence) for evidence in evidence_payload or []
    ]
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
        narrative_degraded=narrative_degraded,
        narrative_failure_notice=narrative_failure_notice,
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
        finding_payload = FindingPayload.model_validate(finding)
        persisted_finding = PersistedFinding(
            finding_id=finding_payload.finding_id,
            title=finding_payload.title,
            description=finding_payload.description,
            explanation=finding_payload.explanation,
            guidance_json=json.dumps(finding_payload.guidance),
            severity=finding_payload.severity,
            category=finding_payload.category,
            deterministic=finding_payload.deterministic,
            confidence=finding_payload.confidence,
            uncertainty_note=finding_payload.uncertainty_note,
            evidence_classification=finding_payload.evidence_classification,
            evidence_refs_json=json.dumps(finding_payload.evidence_refs),
            skill_id=finding_payload.skill_id,
        )
        finding_rows.append(
            (
                persisted_finding,
                finding_payload.evidence_refs,
            )
        )

    evidence_finding_by_id = _validate_finding_evidence_refs(
        finding_rows,
        evidence_payload,
        severity,
        risk_score,
        recommendation,
    )
    _validate_report_verdict_text(
        severity,
        recommendation,
        top_risk,
        narrative_opening,
        narrative_explanation,
    )
    _validate_top_risk_contributor_refs(
        top_risk_contributors_json,
        evidence_finding_by_id,
        severity,
    )

    report.risk_assessment = PersistedRiskAssessment(
        overall_severity=severity,
        recommendation=recommendation,
        score=risk_score,
        confidence=risk_confidence,
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
        for evidence in evidence_payload:
            owner_finding = evidence_finding_by_id.get(str(evidence["evidence_id"]))
            owner = (
                finding_by_id.get(owner_finding.finding_id)
                if owner_finding is not None
                else None
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
                    artifact=str(evidence.get("artifact") or ""),
                    location=str(evidence.get("location") or ""),
                    resource=str(evidence.get("resource") or ""),
                    operation=str(evidence.get("operation") or ""),
                    project_id=(
                        int(evidence["project_id"])
                        if evidence.get("project_id") is not None
                        else None
                    ),
                    project_key=(
                        str(evidence["project_key"])
                        if evidence.get("project_key") is not None
                        else None
                    ),
                    workspace_id=(
                        int(evidence["workspace_id"])
                        if evidence.get("workspace_id") is not None
                        else None
                    ),
                    workspace_key=(
                        str(evidence["workspace_key"])
                        if evidence.get("workspace_key") is not None
                        else None
                    ),
                    source_kind=str(evidence.get("source_kind") or "artifact"),
                    determinism_level=str(
                        evidence.get("determinism_level") or "deterministic"
                    ),
                    redaction_status=str(evidence.get("redaction_status") or "none"),
                    summary=str(evidence["summary"]),
                    severity_hint=str(evidence["severity_hint"]),
                    deterministic=evidence["deterministic"],
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
