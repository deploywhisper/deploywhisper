"""Analysis workflow orchestration."""

from __future__ import annotations

from pydantic import BaseModel, Field

from analysis.blast_radius import BlastRadiusResult, compute_blast_radius
from analysis.incident_matcher import IncidentMatch, find_incident_matches
from analysis.rollback_planner import RollbackPlan, generate_rollback_plan
from analysis.risk_scorer import RiskAssessment, score_parse_batch
from llm.narrator import NarrativeResult, generate_narrative
from parsers.base import ParseBatchResult, UnifiedChange
from services.intake_service import build_parse_batch
from services.report_service import persist_analysis_report
from services.topology_service import load_topology


def evaluate_parse_batch(
    batch: ParseBatchResult,
    *,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    completion_client=None,
) -> RiskAssessment:
    """Return a reusable unified risk assessment from parsed inputs."""
    return score_parse_batch(
        batch,
        topology=topology,
        raw_files=raw_files,
        completion_client=completion_client,
    )


class AnalysisArtifacts(BaseModel):
    parse_batch: ParseBatchResult = Field(..., description="Per-file parse results")
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


def build_advisory_summary(
    assessment: RiskAssessment, narrative: NarrativeResult
) -> AdvisorySummary:
    uncertainty_flags: list[str] = []
    if assessment.partial_context:
        uncertainty_flags.append("partial_context")
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

    markdown = "\n".join(
        [
            f"### DeployWhisper {advisory.severity.upper()} · {advisory.recommendation.upper()}",
            f"- Summary: {narrative.opening_sentence}",
            f"- Blast radius: {blast_radius_summary}",
            f"- Rollback: {rollback_summary}",
            "- Advisory only: DeployWhisper does not make the final release decision or block deployment.",
            f"- Review signal: {uncertainty_summary}",
        ]
    )
    plain_text = " ".join(
        [
            f"DeployWhisper {advisory.severity.upper()} / {advisory.recommendation.upper()}.",
            f"Summary: {narrative.opening_sentence}",
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
        headline=narrative.opening_sentence,
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
    changes = _collect_changes(parse_batch)
    topology, topology_warning = load_topology()
    assessment = evaluate_parse_batch(
        parse_batch,
        topology=topology,
        raw_files={name: raw_content for name, raw_content in files},
        completion_client=completion_client,
    )
    blast_radius = compute_blast_radius(changes, topology, topology_warning)
    rollback_plan = generate_rollback_plan(
        changes, partial_context=parse_batch.has_partial_context
    )
    incident_matches = find_incident_matches(changes)
    narrative = generate_narrative(
        assessment,
        completion_client=completion_client,
        raw_files={name: raw_content for name, raw_content in files},
    )
    return AnalysisArtifacts(
        parse_batch=parse_batch,
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
        audit_context=audit_context,
    )
    return AnalysisRunResult(
        **artifacts.model_dump(), persisted_report=persisted_report
    )
