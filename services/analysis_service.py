"""Analysis workflow orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from analysis.blast_radius import BlastRadiusResult, compute_blast_radius
from analysis.incident_matcher import (
    IncidentMatch,
    find_incident_matches,
    load_incident_candidates,
)
from analysis.risk_engine import score_evidence
from analysis.rollback_planner import RollbackPlan, generate_rollback_plan
from evidence.mappers import build_findings
from analysis.risk_scorer import RiskAssessment
from evidence.models import ContextCompleteness, EvidenceItem, Finding
from evidence.extractor import extract_batch_evidence
from llm.narrator import NarrativeResult, generate_narrative
from llm.providers import generate_completion_with_settings
from parsers.base import ParseBatchResult, UnifiedChange
from services.intake_service import build_parse_batch
from services.report_service import persist_analysis_report
from services.settings_service import resolve_provider_runtime
from services.topology_service import (
    STALE_AFTER_DAYS,
    get_topology_status,
    load_topology,
)


def evaluate_evidence(
    evidence_items: list[EvidenceItem],
    *,
    partial_context: bool = False,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    completion_client=None,
) -> RiskAssessment:
    """Return a reusable unified risk assessment from evidence inputs."""
    return score_evidence(
        evidence_items,
        partial_context=partial_context,
        topology=topology,
        raw_files=raw_files,
        completion_client=completion_client,
    )


def evaluate_parse_batch(
    batch: ParseBatchResult,
    *,
    evidence_items: list[EvidenceItem] | None = None,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    completion_client=None,
) -> RiskAssessment:
    """Compatibility wrapper that scores extracted evidence for a parse batch."""
    return evaluate_evidence(
        evidence_items or extract_batch_evidence(batch),
        partial_context=batch.has_partial_context,
        topology=topology,
        raw_files=raw_files,
        completion_client=completion_client,
    )


class AnalysisArtifacts(BaseModel):
    parse_batch: ParseBatchResult = Field(..., description="Per-file parse results")
    evidence_items: list[EvidenceItem] = Field(
        default_factory=list,
        description="Traceable evidence extracted from parsed changes",
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="Reviewer-facing findings with explicit confidence",
    )
    assessment: RiskAssessment = Field(..., description="Unified risk assessment")
    blast_radius: BlastRadiusResult = Field(..., description="Blast radius result")
    rollback_plan: RollbackPlan = Field(..., description="Rollback planning result")
    incident_matches: list[IncidentMatch] = Field(
        default_factory=list, description="Incident similarity matches"
    )
    narrative: NarrativeResult = Field(..., description="Narrative briefing result")


class AnalysisRunResult(AnalysisArtifacts):
    persisted_report: dict = Field(..., description="Persisted report metadata")


class AdvisorySummary(BaseModel):
    advisory_only: bool = Field(
        ..., description="Whether the output is advisory rather than blocking"
    )
    should_block: bool = Field(
        ..., description="Whether DeployWhisper itself should block deployment"
    )
    requires_attention: bool = Field(
        ..., description="Whether humans should provide additional review"
    )
    severity: str = Field(..., description="Shared risk severity")
    recommendation: str = Field(..., description="Shared deploy recommendation")
    top_risk: str = Field(..., description="Most important shared risk summary")
    partial_context: bool = Field(
        ..., description="Whether parser coverage was partial"
    )
    narrative_degraded: bool = Field(
        ..., description="Whether narrative generation degraded to fallback output"
    )
    uncertainty_flags: list[str] = Field(
        default_factory=list, description="Machine-readable uncertainty indicators"
    )


class ShareSummary(BaseModel):
    advisory_only: bool = Field(
        ..., description="Whether the shared summary is advisory rather than blocking"
    )
    should_block: bool = Field(
        ..., description="Whether DeployWhisper itself should block deployment"
    )
    severity: str = Field(..., description="Risk severity for the shared summary")
    recommendation: str = Field(
        ..., description="Deploy recommendation for the shared summary"
    )
    headline: str = Field(
        ..., description="Top narrative line for PR or approval-thread use"
    )
    blast_radius_summary: str = Field(..., description="Concise blast-radius summary")
    rollback_summary: str = Field(..., description="Concise rollback summary")
    uncertainty_summary: str = Field(
        ..., description="Concise uncertainty and review note"
    )
    markdown: str = Field(..., description="Markdown-ready advisory summary")
    plain_text: str = Field(..., description="Plain-text advisory summary")


def _collect_changes(parse_batch: ParseBatchResult) -> list[UnifiedChange]:
    changes: list[UnifiedChange] = []
    for file_result in parse_batch.files:
        if file_result.status == "parsed":
            changes.extend(file_result.changes)
    return changes


def _topology_freshness_days(updated_at: str | None) -> int | None:
    if not updated_at:
        return None
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max((datetime.now(UTC) - parsed).days, 0)


def _freshness_score(topology_freshness_days: int | None) -> float:
    if topology_freshness_days is None:
        return 0.0
    if topology_freshness_days <= STALE_AFTER_DAYS:
        return 1.0
    return max(0.0, 1.0 - ((topology_freshness_days - STALE_AFTER_DAYS) / 60))


def _incident_score(incident_index_size: int) -> float:
    return min(incident_index_size / 10, 1.0)


def _build_context_completeness(parse_batch: ParseBatchResult) -> ContextCompleteness:
    topology_status = get_topology_status()
    topology_freshness_days = _topology_freshness_days(topology_status.updated_at)
    incident_index_size = len(load_incident_candidates())
    parser_success_rate = round(
        parse_batch.parsed_count / max(len(parse_batch.files), 1),
        2,
    )
    context_score = round(
        min(
            1.0,
            (
                parser_success_rate * 0.45
                + _freshness_score(topology_freshness_days) * 0.35
                + _incident_score(incident_index_size) * 0.20
            ),
        ),
        2,
    )
    return ContextCompleteness(
        topology_freshness_days=topology_freshness_days,
        incident_index_size=incident_index_size,
        parser_success_rate=parser_success_rate,
        context_score=context_score,
    )


def _interaction_confidence_prompt_payload(assessment: RiskAssessment) -> str:
    payload = {
        "instructions": {
            "format": "Return JSON with key 'confidences' containing objects with keys 'key' and 'confidence'.",
            "constraints": [
                "Only use interaction keys present in the payload.",
                "Confidence must be a number between 0 and 1.",
                "Do not invent extra interactions.",
            ],
        },
        "interactions": [
            {
                "key": interaction.key,
                "summary": interaction.summary,
                "contributing_files": interaction.contributing_files,
                "contributing_resources": interaction.contributing_resources,
            }
            for interaction in assessment.interaction_risks
        ],
        "top_risk": assessment.top_risk,
        "contributors": [
            {
                "resource_id": contributor.resource_id,
                "severity": contributor.severity,
                "reasoning": contributor.reasoning,
            }
            for contributor in assessment.contributors[:5]
        ],
    }
    return json.dumps(payload, indent=2)


def _interaction_confidence_overrides(
    assessment: RiskAssessment, *, completion_client=None
) -> dict[str, float]:
    if assessment.source != "heuristic+llm" or not assessment.interaction_risks:
        return {}

    runtime = resolve_provider_runtime()
    try:
        raw_response = generate_completion_with_settings(
            [
                {
                    "role": "system",
                    "content": (
                        "You assign confidence scores to inferred deployment findings. "
                        "Return only JSON with key 'confidences'."
                    ),
                },
                {
                    "role": "user",
                    "content": _interaction_confidence_prompt_payload(assessment),
                },
            ],
            provider=runtime["provider"],
            model=runtime["model"],
            api_base=runtime["api_base"],
            api_key=runtime["api_key"],
            local_mode=runtime["local_mode"],
            completion_client=completion_client,
        )
        payload = json.loads(raw_response)
    except Exception:  # noqa: BLE001
        return {}

    overrides: dict[str, float] = {}
    allowed_keys = {interaction.key for interaction in assessment.interaction_risks}
    for item in payload.get("confidences", []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        confidence = item.get("confidence")
        if key not in allowed_keys or not isinstance(confidence, (int, float)):
            continue
        overrides[key] = max(0.0, min(1.0, round(float(confidence), 2)))
    return overrides


def build_advisory_summary(
    assessment: RiskAssessment, narrative: NarrativeResult
) -> AdvisorySummary:
    uncertainty_flags: list[str] = []
    if assessment.partial_context:
        uncertainty_flags.append("partial_context")
    if assessment.context_completeness.context_score < 0.7:
        uncertainty_flags.append("low_context_completeness")
    if assessment.warnings:
        uncertainty_flags.append("assessment_warnings")
    if narrative.degraded:
        uncertainty_flags.append("narrative_degraded")
    if narrative.warnings:
        uncertainty_flags.append("narrative_warnings")

    return AdvisorySummary(
        advisory_only=True,
        should_block=False,
        requires_attention=(
            assessment.recommendation != "go"
            or assessment.partial_context
            or assessment.context_completeness.context_score < 0.7
            or bool(assessment.warnings)
            or narrative.degraded
        ),
        severity=assessment.severity,
        recommendation=assessment.recommendation,
        top_risk=assessment.top_risk,
        partial_context=assessment.partial_context,
        narrative_degraded=narrative.degraded,
        uncertainty_flags=uncertainty_flags,
    )


def build_share_summary(
    *,
    advisory: AdvisorySummary,
    narrative: NarrativeResult,
    blast_radius: BlastRadiusResult,
    rollback_plan: RollbackPlan,
) -> ShareSummary:
    affected_labels = (
        ", ".join(node.label for node in blast_radius.affected[:3])
        or "No mapped downstream services"
    )
    if len(blast_radius.affected) > 3:
        affected_labels += ", ..."
    blast_radius_summary = (
        f"{blast_radius.direct_count} direct / {blast_radius.transitive_count} transitive affected"
        f" ({affected_labels})"
    )
    if blast_radius.warning:
        blast_radius_summary += f". Warning: {blast_radius.warning}"

    first_step = (
        rollback_plan.steps[0].title
        if rollback_plan.steps
        else "No rollback steps available"
    )
    rollback_summary = (
        f"{rollback_plan.complexity.title()} complexity. First step: {first_step}."
    )
    if rollback_plan.warning:
        rollback_summary += f" Warning: {rollback_plan.warning}"

    if advisory.requires_attention:
        uncertainty_summary = (
            "This result requires additional human review before release."
        )
    else:
        uncertainty_summary = (
            "No additional human review is required beyond the normal approval flow."
        )
    if advisory.uncertainty_flags:
        uncertainty_summary += (
            " Uncertainty: " + ", ".join(advisory.uncertainty_flags) + "."
        )
    headline = narrative.opening_sentence or (
        f"{advisory.recommendation.upper()}: {advisory.top_risk}"
    )

    markdown = "\n".join(
        [
            f"### DeployWhisper {advisory.severity.upper()} · {advisory.recommendation.upper()}",
            f"- Summary: {headline}",
            f"- Blast radius: {blast_radius_summary}",
            f"- Rollback: {rollback_summary}",
            "- Advisory only: DeployWhisper does not make the final release decision or block deployment.",
            f"- Review signal: {uncertainty_summary}",
        ]
    )
    plain_text = " ".join(
        [
            f"DeployWhisper {advisory.severity.upper()} / {advisory.recommendation.upper()}.",
            f"Summary: {headline}",
            f"Blast radius: {blast_radius_summary}",
            f"Rollback: {rollback_summary}",
            "Advisory only: DeployWhisper does not make the final release decision or block deployment.",
            f"Review signal: {uncertainty_summary}",
        ]
    )

    return ShareSummary(
        advisory_only=True,
        should_block=False,
        severity=advisory.severity,
        recommendation=advisory.recommendation,
        headline=headline,
        blast_radius_summary=blast_radius_summary,
        rollback_summary=rollback_summary,
        uncertainty_summary=uncertainty_summary,
        markdown=markdown,
        plain_text=plain_text,
    )


def build_analysis_artifacts(
    files: list[tuple[str, bytes | None]],
    completion_client=None,
) -> AnalysisArtifacts:
    """Build all analysis artifacts up to, but not including, persistence."""
    parse_batch = build_parse_batch(files)
    evidence_items = extract_batch_evidence(parse_batch)
    changes = _collect_changes(parse_batch)
    topology, topology_warning = load_topology()
    assessment = evaluate_parse_batch(
        parse_batch,
        evidence_items=evidence_items,
        topology=topology,
        raw_files={name: raw_content for name, raw_content in files},
        completion_client=completion_client,
    )
    assessment.context_completeness = _build_context_completeness(parse_batch)
    findings = build_findings(
        assessment=assessment,
        evidence_items=evidence_items,
        interaction_confidence_overrides=_interaction_confidence_overrides(
            assessment, completion_client=completion_client
        ),
    )
    blast_radius = compute_blast_radius(changes, topology, topology_warning)
    rollback_plan = generate_rollback_plan(
        changes, partial_context=parse_batch.has_partial_context
    )
    incident_matches = find_incident_matches(changes)
    narrative = generate_narrative(
        assessment.model_copy(deep=True),
        [finding.model_copy(deep=True) for finding in findings],
        completion_client=completion_client,
        raw_files={name: raw_content for name, raw_content in files},
    )
    return AnalysisArtifacts(
        parse_batch=parse_batch,
        evidence_items=evidence_items,
        findings=findings,
        assessment=assessment,
        blast_radius=blast_radius,
        rollback_plan=rollback_plan,
        incident_matches=incident_matches,
        narrative=narrative,
    )


def analyze_uploaded_files(
    files: list[tuple[str, bytes | None]],
    completion_client=None,
    audit_context: dict | None = None,
) -> AnalysisRunResult:
    """Run the shared parse -> assess -> persist pipeline."""
    artifacts = build_analysis_artifacts(files, completion_client=completion_client)
    persisted_report = persist_analysis_report(
        artifacts.parse_batch,
        artifacts.assessment,
        artifacts.narrative,
        findings=artifacts.findings,
        evidence_items=artifacts.evidence_items,
        artifact_snapshots={name: raw_content for name, raw_content in files},
        audit_context=audit_context,
    )
    return AnalysisRunResult(
        **artifacts.model_dump(), persisted_report=persisted_report
    )
