"""Stable advisory output contracts for AI-agent interfaces."""

from __future__ import annotations

from typing import Literal

from api.schemas import (
    AnalysisRunData,
    DeployRecommendation,
    RiskSeverity,
)
from evidence.models import (
    ContextSourceFreshness,
    ContextSourceType,
    FindingEvidenceClassification,
)
from pydantic import BaseModel, ConfigDict, Field
from services.confidence_ledger import EvidenceLawStatus


AGENT_OUTPUT_SCHEMA_VERSION = "v1"
AGENT_APPROVAL_STATEMENT = (
    "This output is advisory and is not deployment approval. "
    "A human must review the evidence before any deployment decision."
)
_HUMAN_REVIEW_GUIDANCE = (
    "Have a human reviewer inspect the evidence and findings before deployment."
)


class _AgentContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentScopeData(_AgentContractModel):
    project_id: int
    project_key: str
    workspace_id: int | None = None
    workspace_key: str | None = None


class AgentVerdictData(_AgentContractModel):
    risk_score: int
    severity: RiskSeverity
    recommendation: DeployRecommendation
    top_risk: str


class AgentEvidenceLawData(_AgentContractModel):
    status: EvidenceLawStatus
    detail: str


class AgentContextSourceData(_AgentContractModel):
    source_id: str
    source_type: ContextSourceType
    source_ref: str | None = None
    scope: str
    freshness_status: ContextSourceFreshness = "unknown"
    last_observed_at: str | None = None
    age_days: int | None = Field(default=None, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, allow_inf_nan=False)
    conflicts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AgentEvidenceData(_AgentContractModel):
    evidence_id: str
    analysis_id: int
    finding_id: str
    source_type: str
    source_ref: str
    artifact: str = ""
    location: str = ""
    resource: str = ""
    operation: str = ""
    project_id: int | None = None
    project_key: str | None = None
    workspace_id: int | None = None
    workspace_key: str | None = None
    source_kind: str = "artifact"
    determinism_level: str = "deterministic"
    redaction_status: str = "none"
    summary: str
    severity_hint: RiskSeverity
    deterministic: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_label: str | None = None
    related_change_ids: list[str] = Field(default_factory=list)
    context_source: AgentContextSourceData | None = None


class AgentFindingData(_AgentContractModel):
    finding_id: str
    analysis_id: int
    title: str
    description: str
    explanation: str = ""
    guidance: list[str] = Field(default_factory=list)
    severity: RiskSeverity
    category: str
    deterministic: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    uncertainty_note: str | None = None
    evidence_classification: FindingEvidenceClassification = "deterministic"
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_label: str | None = None
    skill_id: str | None = None


class AgentConfidenceLedgerData(_AgentContractModel):
    contributors: list[str] = Field(default_factory=list)
    confidence_factors: list[str] = Field(default_factory=list)
    why_not_lower: list[str] = Field(default_factory=list)
    why_not_higher: list[str] = Field(default_factory=list)
    uncertainty_drivers: list[str] = Field(default_factory=list)


class AgentConfidenceData(_AgentContractModel):
    overall: float = Field(..., ge=0.0, le=1.0)
    ledger: AgentConfidenceLedgerData


class AgentUncertaintyData(_AgentContractModel):
    flags: list[str] = Field(default_factory=list)
    summary: str | None = None
    partial_context: bool
    insufficient_context: bool
    warnings: list[str] = Field(default_factory=list)


class AgentAnalysisData(_AgentContractModel):
    schema_version: Literal["v1"] = AGENT_OUTPUT_SCHEMA_VERSION
    report_schema_version: str
    report_id: int
    scope: AgentScopeData
    verdict: AgentVerdictData
    advisory_only: Literal[True] = True
    deployment_approval: Literal[False] = False
    human_decision_required: Literal[True] = True
    approval_statement: Literal[
        "This output is advisory and is not deployment approval. "
        "A human must review the evidence before any deployment decision."
    ] = AGENT_APPROVAL_STATEMENT
    evidence_law: AgentEvidenceLawData
    evidence: list[AgentEvidenceData] = Field(default_factory=list)
    findings: list[AgentFindingData] = Field(default_factory=list)
    confidence: AgentConfidenceData
    uncertainty: AgentUncertaintyData
    context_todos: list[str] = Field(default_factory=list)
    verification_guidance: list[str] = Field(default_factory=list)


def _append_unique(values: list[str], candidate: object) -> None:
    text = str(candidate).strip()
    normalized = " ".join(text.split()).casefold()
    if normalized and all(
        " ".join(existing.split()).casefold() != normalized for existing in values
    ):
        values.append(text)


def collect_agent_verification_guidance(analysis: AnalysisRunData) -> list[str]:
    """Collect deterministic human-review steps without changing report semantics."""
    guidance: list[str] = []
    for finding in analysis.findings:
        for item in finding.guidance:
            _append_unique(guidance, item)
    for incident_match in analysis.incident_matches:
        for item in incident_match.verification_guidance:
            _append_unique(guidance, item)
    for conflict in analysis.share_summary.json_payload.scanner_conflicts:
        _append_unique(guidance, conflict.recommended_verification)
    for item in analysis.narrative.guidance:
        _append_unique(guidance, item)
    _append_unique(guidance, _HUMAN_REVIEW_GUIDANCE)
    return guidance


def build_agent_analysis_data(analysis: AnalysisRunData) -> AgentAnalysisData:
    """Adapt one canonical analysis result into the stable agent JSON contract."""
    context = analysis.assessment.context_completeness
    report = analysis.persisted_report
    share_payload = analysis.share_summary.json_payload
    workspace = report.workspace
    warnings: list[str] = []
    for item in [*analysis.assessment.warnings, *analysis.narrative.warnings]:
        _append_unique(warnings, item)

    return AgentAnalysisData(
        report_schema_version=report.report_schema_version,
        report_id=report.id,
        scope=AgentScopeData(
            project_id=report.project.id,
            project_key=report.project.project_key,
            workspace_id=workspace.id if workspace is not None else None,
            workspace_key=workspace.workspace_key if workspace is not None else None,
        ),
        verdict=AgentVerdictData(
            risk_score=analysis.assessment.score,
            severity=analysis.assessment.severity,
            recommendation=analysis.assessment.recommendation,
            top_risk=analysis.assessment.top_risk,
        ),
        evidence_law=AgentEvidenceLawData(
            status=share_payload.evidence_law_status,
            detail=share_payload.evidence_law_detail,
        ),
        evidence=[
            AgentEvidenceData(
                evidence_id=item.evidence_id,
                analysis_id=item.analysis_id,
                finding_id=item.finding_id,
                source_type=item.source_type,
                source_ref=item.source_ref,
                artifact=item.artifact,
                location=item.location,
                resource=item.resource,
                operation=item.operation,
                project_id=item.project_id,
                project_key=item.project_key,
                workspace_id=item.workspace_id,
                workspace_key=item.workspace_key,
                source_kind=item.source_kind,
                determinism_level=item.determinism_level,
                redaction_status=item.redaction_status,
                summary=item.summary,
                severity_hint=item.severity_hint,
                deterministic=item.deterministic,
                confidence=item.confidence,
                evidence_label=item.evidence_label,
                related_change_ids=item.related_change_ids,
                context_source=(
                    AgentContextSourceData(
                        source_id=item.context_source.source_id,
                        source_type=item.context_source.source_type,
                        source_ref=item.context_source.source_ref,
                        scope=item.context_source.scope,
                        freshness_status=item.context_source.freshness_status,
                        last_observed_at=item.context_source.last_observed_at,
                        age_days=item.context_source.age_days,
                        confidence=item.context_source.confidence,
                        conflicts=item.context_source.conflicts,
                        limitations=item.context_source.limitations,
                    )
                    if item.context_source is not None
                    else None
                ),
            )
            for item in analysis.evidence_items
        ],
        findings=[
            AgentFindingData(
                finding_id=item.finding_id,
                analysis_id=item.analysis_id,
                title=item.title,
                description=item.description,
                explanation=item.explanation,
                guidance=item.guidance,
                severity=item.severity,
                category=item.category,
                deterministic=item.deterministic,
                confidence=item.confidence,
                uncertainty_note=item.uncertainty_note,
                evidence_classification=item.evidence_classification,
                evidence_refs=item.evidence_refs,
                evidence_label=item.evidence_label,
                skill_id=item.skill_id,
            )
            for item in analysis.findings
        ],
        confidence=AgentConfidenceData(
            overall=analysis.assessment.confidence,
            ledger=AgentConfidenceLedgerData(
                contributors=analysis.assessment.confidence_ledger.contributors,
                confidence_factors=(
                    analysis.assessment.confidence_ledger.confidence_factors
                ),
                why_not_lower=analysis.assessment.confidence_ledger.why_not_lower,
                why_not_higher=analysis.assessment.confidence_ledger.why_not_higher,
                uncertainty_drivers=(
                    analysis.assessment.confidence_ledger.uncertainty_drivers
                ),
            ),
        ),
        uncertainty=AgentUncertaintyData(
            flags=analysis.advisory.uncertainty_flags,
            summary=context.uncertainty,
            partial_context=context.partial_context,
            insufficient_context=context.insufficient_context,
            warnings=warnings,
        ),
        context_todos=context.context_todos,
        verification_guidance=collect_agent_verification_guidance(analysis),
    )
