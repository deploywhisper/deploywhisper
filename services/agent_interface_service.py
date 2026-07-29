"""Stable advisory output contracts for AI-agent interfaces."""

from __future__ import annotations

from typing import Any, Literal

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
AGENT_INTERFACE_SCHEMA_VERSION = "v1"
AGENT_MAX_STRING_CHARACTERS = 2048
AGENT_MAX_COLLECTION_ITEMS = 50
AGENT_MAX_FINDINGS = 50
AGENT_MAX_EVIDENCE = 100
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


class AgentOutputLimitsData(_AgentContractModel):
    max_string_characters: int = AGENT_MAX_STRING_CHARACTERS
    max_collection_items: int = AGENT_MAX_COLLECTION_ITEMS
    max_findings: int = AGENT_MAX_FINDINGS
    max_evidence: int = AGENT_MAX_EVIDENCE


class AgentInterfaceMeta(_AgentContractModel):
    interface_schema_version: Literal["v1"] = AGENT_INTERFACE_SCHEMA_VERSION
    operation: Literal["analysis.submit", "report.read"]
    advisory_only: Literal[True] = True
    output_limits: AgentOutputLimitsData = Field(default_factory=AgentOutputLimitsData)
    truncated: bool = False
    truncated_fields: list[str] = Field(default_factory=list)


class AgentInterfaceResponse(_AgentContractModel):
    data: AgentAnalysisData
    meta: AgentInterfaceMeta


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


def _mapping_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_items(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value if str(item).strip()]


def collect_agent_report_verification_guidance(report: dict[str, Any]) -> list[str]:
    """Collect human-review steps from one canonical persisted report."""
    guidance: list[str] = []
    for finding in _mapping_items(report.get("findings")):
        for item in _string_items(finding.get("guidance")):
            _append_unique(guidance, item)
    for incident_match in _mapping_items(report.get("incident_matches")):
        for item in _string_items(incident_match.get("verification_guidance")):
            _append_unique(guidance, item)
    share_summary = report.get("share_summary")
    if share_summary is not None:
        for conflict in share_summary.json_payload.scanner_conflicts:
            _append_unique(guidance, conflict.recommended_verification)
    for item in _string_items(report.get("narrative_guidance")):
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


def build_agent_report_data(report: dict[str, Any]) -> AgentAnalysisData:
    """Adapt a canonical persisted report into the stable agent contract."""
    from services.analysis_service import build_share_summary

    share_summary = build_share_summary(report)
    context = dict(report.get("context_completeness") or {})
    project = dict(report.get("project") or {})
    workspace = (
        dict(report["workspace"]) if isinstance(report.get("workspace"), dict) else None
    )
    advisory = dict(report.get("advisory") or {})
    ledger = AgentConfidenceLedgerData.model_validate(
        report.get("confidence_ledger") or {}
    )
    report_with_summary = {**report, "share_summary": share_summary}
    if project.get("id") is None or not str(project.get("project_key") or "").strip():
        raise ValueError("Persisted agent report project scope is incomplete.")
    if workspace is not None and (
        workspace.get("id") is None
        or not str(workspace.get("workspace_key") or "").strip()
    ):
        raise ValueError("Persisted agent report workspace scope is incomplete.")

    return AgentAnalysisData(
        report_schema_version=str(report.get("report_schema_version") or ""),
        report_id=int(report["id"]),
        scope=AgentScopeData(
            project_id=int(project["id"]),
            project_key=str(project["project_key"]),
            workspace_id=int(workspace["id"]) if workspace is not None else None,
            workspace_key=(
                str(workspace["workspace_key"]) if workspace is not None else None
            ),
        ),
        verdict=AgentVerdictData(
            risk_score=int(report.get("risk_score") or 0),
            severity=report.get("severity", "low"),
            recommendation=report.get("recommendation", "caution"),
            top_risk=str(report.get("top_risk") or ""),
        ),
        evidence_law=AgentEvidenceLawData(
            status=share_summary.json_payload.evidence_law_status,
            detail=share_summary.json_payload.evidence_law_detail,
        ),
        evidence=[
            AgentEvidenceData.model_validate(item)
            for item in _mapping_items(report.get("evidence_items"))
        ],
        findings=[
            AgentFindingData.model_validate(item)
            for item in _mapping_items(report.get("findings"))
        ],
        confidence=AgentConfidenceData(
            overall=float(report.get("confidence") or 0.0),
            ledger=ledger,
        ),
        uncertainty=AgentUncertaintyData(
            flags=list(advisory.get("uncertainty_flags") or []),
            summary=str(context["uncertainty"])
            if context.get("uncertainty") is not None
            else None,
            partial_context=bool(context.get("partial_context")),
            insufficient_context=bool(context.get("insufficient_context")),
            warnings=[str(item) for item in report.get("warnings") or []],
        ),
        context_todos=[str(item) for item in context.get("context_todos") or []],
        verification_guidance=collect_agent_report_verification_guidance(
            report_with_summary
        ),
    )


def _bounded_agent_value(
    value: Any,
    *,
    path: str,
    truncated_fields: list[str],
) -> Any:
    if isinstance(value, str):
        if len(value) <= AGENT_MAX_STRING_CHARACTERS:
            return value
        truncated_fields.append(path)
        return value[:AGENT_MAX_STRING_CHARACTERS]
    if isinstance(value, list):
        limit = (
            AGENT_MAX_EVIDENCE
            if path == "evidence"
            else AGENT_MAX_FINDINGS
            if path == "findings"
            else AGENT_MAX_COLLECTION_ITEMS
        )
        if len(value) > limit:
            truncated_fields.append(path)
        return [
            _bounded_agent_value(
                item,
                path=f"{path}.{index}",
                truncated_fields=truncated_fields,
            )
            for index, item in enumerate(value[:limit])
        ]
    if isinstance(value, dict):
        return {
            key: _bounded_agent_value(
                item,
                path=f"{path}.{key}" if path else key,
                truncated_fields=truncated_fields,
            )
            for key, item in value.items()
        }
    return value


def _bound_linked_agent_graph(
    payload: dict[str, Any],
    *,
    truncated_fields: list[str],
) -> None:
    """Bound findings and evidence while preserving their references."""
    findings = list(payload.get("findings") or [])
    evidence = list(payload.get("evidence") or [])
    selected_findings = findings[:AGENT_MAX_FINDINGS]
    if len(findings) > len(selected_findings):
        truncated_fields.append("findings")

    finding_ids = {
        str(finding.get("finding_id") or "")
        for finding in selected_findings
        if isinstance(finding, dict)
    }
    linked_evidence = [
        item
        for item in evidence
        if isinstance(item, dict) and str(item.get("finding_id") or "") in finding_ids
    ]
    evidence_by_id = {
        str(item.get("evidence_id") or ""): item
        for item in linked_evidence
        if str(item.get("evidence_id") or "")
    }

    ordered_evidence: list[dict[str, Any]] = []
    selected_evidence_ids: set[str] = set()

    def append_evidence(item: dict[str, Any]) -> None:
        evidence_id = str(item.get("evidence_id") or "")
        if evidence_id and evidence_id not in selected_evidence_ids:
            selected_evidence_ids.add(evidence_id)
            ordered_evidence.append(item)

    for finding in selected_findings:
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("finding_id") or "")
        for evidence_ref in finding.get("evidence_refs") or []:
            item = evidence_by_id.get(str(evidence_ref))
            if item is not None and str(item.get("finding_id") or "") == finding_id:
                append_evidence(item)
    for item in linked_evidence:
        append_evidence(item)

    selected_evidence = ordered_evidence[:AGENT_MAX_EVIDENCE]
    returned_evidence_ids = {
        str(item.get("evidence_id") or "") for item in selected_evidence
    }
    if len(evidence) > len(selected_evidence):
        truncated_fields.append("evidence")

    for finding in selected_findings:
        if isinstance(finding, dict):
            finding["evidence_refs"] = [
                str(evidence_ref)
                for evidence_ref in finding.get("evidence_refs") or []
                if str(evidence_ref) in returned_evidence_ids
            ]

    payload["findings"] = selected_findings
    payload["evidence"] = selected_evidence


def build_agent_interface_response(
    data: AgentAnalysisData,
    *,
    operation: Literal["analysis.submit", "report.read"],
) -> AgentInterfaceResponse:
    """Apply deterministic output bounds and wrap the agent API response."""
    truncated_fields: list[str] = []
    payload = data.model_dump(mode="json")
    _bound_linked_agent_graph(payload, truncated_fields=truncated_fields)
    bounded_payload = _bounded_agent_value(
        payload,
        path="",
        truncated_fields=truncated_fields,
    )
    bounded_data = AgentAnalysisData.model_validate(bounded_payload)
    return AgentInterfaceResponse(
        data=bounded_data,
        meta=AgentInterfaceMeta(
            operation=operation,
            truncated=bool(truncated_fields),
            truncated_fields=list(dict.fromkeys(truncated_fields)),
        ),
    )
