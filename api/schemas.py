"""Shared API schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

from config import settings


class MetaPayload(BaseModel):
    app: str = Field(..., description="Application identifier")
    version: str = Field(..., description="Application version")


def build_meta(**extra: Any) -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        **extra,
    }


class HealthData(BaseModel):
    status: str = Field(..., description="Service health status")
    mode: str = Field(..., description="Current application mode")


class HealthResponse(BaseModel):
    data: HealthData
    meta: MetaPayload


ToolType = Literal["terraform", "kubernetes", "ansible", "jenkins", "cloudformation", "unsupported"]
IntakeStatus = Literal["ready", "unsupported", "sensitive"]
ParseStatus = Literal["parsed", "failed", "skipped"]
RiskSeverity = Literal["low", "medium", "high", "critical"]
DeployRecommendation = Literal["go", "caution", "no-go"]
RollbackComplexity = Literal["low", "medium", "high"]


class IntakeItem(BaseModel):
    name: str
    tool: ToolType
    status: IntakeStatus
    message: str


class PendingAnalysis(BaseModel):
    items: list[IntakeItem]

    @computed_field(return_type=int)
    @property
    def ready_count(self) -> int:
        return sum(1 for item in self.items if item.status == "ready")


class CountMetaPayload(MetaPayload):
    count: int = Field(..., description="Count of returned items")


class ResourceMetaPayload(MetaPayload):
    id: int = Field(..., description="Stable resource identifier")


class AnalysisRunMetaPayload(MetaPayload):
    api_version: str = Field(..., description="Versioned API contract identifier")
    advisory_only: bool = Field(..., description="Whether the analysis is advisory rather than deployment-blocking")
    submitted_artifact_count: int = Field(..., description="Number of uploaded artifacts received")
    accepted_artifact_count: int = Field(..., description="Number of artifacts accepted for analysis")


class ErrorPayload(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable error summary")
    details: dict[str, Any] = Field(default_factory=dict, description="Optional machine-readable error details")


class ErrorResponse(BaseModel):
    error: ErrorPayload


class AuditMetadataData(BaseModel):
    files_analyzed: list[str] = Field(default_factory=list, description="Artifacts included in the persisted analysis")
    llm_provider: str | None = Field(default=None, description="Narrative provider used for this analysis")
    llm_model: str | None = Field(default=None, description="Narrative model used for this analysis")
    llm_local_mode: bool | None = Field(default=None, description="Whether narrative generation used local-only mode")
    source_interface: str | None = Field(default=None, description="Boundary surface that triggered the analysis")
    trigger_type: str | None = Field(default=None, description="Trigger category when available")
    trigger_id: str | None = Field(default=None, description="Trigger identifier when available")


class PersistedReportData(BaseModel):
    id: int
    risk_score: int
    severity: str
    recommendation: str
    top_risk: str
    parse_summary: str
    narrative_opening: str
    created_at: str
    warnings: list[str] = Field(default_factory=list)
    contributors: list["RiskContributorData"] = Field(default_factory=list)
    dashboard_display_duration_seconds: int | None = Field(default=None)
    dashboard_remaining_seconds: int | None = Field(default=None)
    audit: AuditMetadataData


class AnalysisReportData(PersistedReportData):
    pass


class ChangeData(BaseModel):
    source_file: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Source tool name")
    resource_id: str = Field(..., description="Resource identifier")
    action: str = Field(..., description="Change action")
    summary: str = Field(..., description="Human-readable summary")


class ParseIssueData(BaseModel):
    file_name: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Detected or expected tool")
    message: str = Field(..., description="Why parsing failed or was partial")


class ParsedArtifactData(BaseModel):
    file_name: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Detected tool")
    status: ParseStatus = Field(..., description="Parse outcome for this file")
    changes: list[ChangeData] = Field(default_factory=list, description="Normalized changes")
    issue: ParseIssueData | None = Field(default=None, description="Failure context if parsing failed")


class ParseBatchData(BaseModel):
    files: list[ParsedArtifactData] = Field(default_factory=list, description="Per-file parse results")


class InteractionRiskData(BaseModel):
    key: str = Field(..., description="Stable identifier for the interaction pattern")
    summary: str = Field(..., description="User-facing explanation of the interaction")
    contributing_files: list[str] = Field(default_factory=list, description="Files involved")
    contributing_resources: list[str] = Field(default_factory=list, description="Resources involved")
    contribution_bonus: int = Field(..., description="Additional score contribution")


class RiskContributorData(BaseModel):
    source_file: str = Field(..., description="Source file for the contributing change")
    tool: str = Field(..., description="Tool that produced the change")
    resource_id: str = Field(..., description="Resource affected by the change")
    action: str = Field(..., description="Change action")
    contribution: int = Field(..., description="Contribution to the final score")
    summary: str = Field(..., description="Human-readable explanation")
    normalized_action: str = Field(default="modify", description="Normalized lifecycle action")
    resource_category: str = Field(default="generic infrastructure", description="Resource blast-radius category")
    blast_radius: str = Field(default="unknown", description="Blast-radius explanation")
    downstream_scope: int | None = Field(default=None, description="Approximate downstream scope count")
    security_flags: list[str] = Field(default_factory=list, description="Detected security-sensitive findings")
    environment: str = Field(default="unknown", description="Inferred target environment")
    severity: RiskSeverity = Field(..., description="Per-resource severity")
    reasoning: str = Field(default="", description="Per-resource scoring explanation")


class AssessmentData(BaseModel):
    score: int = Field(..., description="Overall bounded risk score")
    severity: RiskSeverity = Field(..., description="Severity classification")
    recommendation: DeployRecommendation = Field(..., description="Advisory recommendation")
    top_risk: str = Field(..., description="Most important risk summary")
    contributors: list[RiskContributorData] = Field(default_factory=list, description="Score contributors")
    interaction_risks: list[InteractionRiskData] = Field(default_factory=list, description="Cross-tool interaction findings")
    partial_context: bool = Field(..., description="Whether some files failed to parse")
    warnings: list[str] = Field(default_factory=list, description="Assessment warnings")


class ImpactNodeData(BaseModel):
    service_id: str = Field(..., description="Stable service identifier")
    label: str = Field(..., description="Human-readable service label")
    depth: int = Field(..., description="0 for direct impact, 1+ for transitive impact")


class BlastRadiusData(BaseModel):
    affected: list[ImpactNodeData] = Field(default_factory=list, description="Affected services")
    direct_count: int = Field(..., description="Count of directly affected services")
    transitive_count: int = Field(..., description="Count of transitively affected services")
    warning: str | None = Field(default=None, description="Warning when impact may be incomplete")
    unmatched_resources: list[str] = Field(default_factory=list, description="Resources not found in topology context")


class RollbackStepData(BaseModel):
    order: int = Field(..., description="Execution order")
    title: str = Field(..., description="Short rollback step title")
    detail: str = Field(..., description="Operational rollback instruction")
    critical: bool = Field(..., description="Whether this step is critical to safe recovery")


class RollbackPlanData(BaseModel):
    steps: list[RollbackStepData] = Field(default_factory=list, description="Ordered rollback steps")
    complexity: RollbackComplexity = Field(..., description="Rollback complexity classification")
    warning: str | None = Field(default=None, description="Warning if context is incomplete")


class IncidentMatchData(BaseModel):
    incident_id: int = Field(..., description="Matched incident identifier")
    title: str = Field(..., description="Incident title")
    severity: str = Field(..., description="Incident severity")
    source_file: str = Field(..., description="Incident source file")
    incident_date: str | None = Field(default=None, description="Incident date if available")
    similarity: float = Field(..., description="Similarity score between 0 and 1")
    summary: str = Field(..., description="Short operational explanation")


class NarrativeData(BaseModel):
    opening_sentence: str = Field(..., description="First-scan deploy briefing sentence")
    explanation: str = Field(..., description="Extended plain-English explanation")
    guidance: list[str] = Field(default_factory=list, description="Actionable guidance")
    degraded: bool = Field(..., description="Whether fallback mode was used")
    warnings: list[str] = Field(default_factory=list, description="Narrative warnings")


class AdvisorySummaryData(BaseModel):
    advisory_only: bool = Field(..., description="Whether the output is advisory rather than blocking")
    should_block: bool = Field(..., description="Whether DeployWhisper itself should block deployment")
    requires_attention: bool = Field(..., description="Whether humans should provide additional review")
    severity: RiskSeverity = Field(..., description="Shared risk severity")
    recommendation: DeployRecommendation = Field(..., description="Shared deploy recommendation")
    top_risk: str = Field(..., description="Most important shared risk summary")
    partial_context: bool = Field(..., description="Whether parser coverage was partial")
    narrative_degraded: bool = Field(..., description="Whether narrative generation degraded to fallback output")
    uncertainty_flags: list[str] = Field(default_factory=list, description="Machine-readable uncertainty indicators")


class ShareSummaryData(BaseModel):
    advisory_only: bool = Field(..., description="Whether the shared summary is advisory rather than blocking")
    should_block: bool = Field(..., description="Whether DeployWhisper itself should block deployment")
    severity: RiskSeverity = Field(..., description="Risk severity for PR or approval-thread sharing")
    recommendation: DeployRecommendation = Field(..., description="Recommendation for PR or approval-thread sharing")
    headline: str = Field(..., description="Top narrative line for sharing")
    blast_radius_summary: str = Field(..., description="Concise blast-radius summary")
    rollback_summary: str = Field(..., description="Concise rollback summary")
    uncertainty_summary: str = Field(..., description="Concise review and uncertainty summary")
    markdown: str = Field(..., description="Markdown-ready advisory summary")
    plain_text: str = Field(..., description="Plain-text advisory summary")


class AnalysisRunData(BaseModel):
    intake: PendingAnalysis
    parse_batch: ParseBatchData
    assessment: AssessmentData
    blast_radius: BlastRadiusData
    rollback_plan: RollbackPlanData
    incident_matches: list[IncidentMatchData] = Field(default_factory=list)
    narrative: NarrativeData
    advisory: AdvisorySummaryData
    share_summary: ShareSummaryData
    persisted_report: PersistedReportData


class AnalysisListResponse(BaseModel):
    data: list[AnalysisReportData]
    meta: CountMetaPayload


class AnalysisDetailResponse(BaseModel):
    data: AnalysisReportData
    meta: ResourceMetaPayload


class AnalysisRunResponse(BaseModel):
    data: AnalysisRunData
    meta: AnalysisRunMetaPayload


PersistedReportData.model_rebuild()


def _copy_model(model: BaseModel, schema_type: type[BaseModel]) -> BaseModel:
    return schema_type.model_validate(model.model_dump())


def build_analysis_run_data(
    *,
    intake: PendingAnalysis,
    result: BaseModel,
    advisory: BaseModel,
    share_summary: BaseModel,
) -> AnalysisRunData:
    parse_batch = result.parse_batch
    assessment = result.assessment
    blast_radius = result.blast_radius
    rollback_plan = result.rollback_plan
    incident_matches = result.incident_matches
    narrative = result.narrative
    persisted_report = result.persisted_report

    return AnalysisRunData(
        intake=PendingAnalysis.model_validate(intake.model_dump()),
        parse_batch=ParseBatchData(
            files=[
                ParsedArtifactData(
                    file_name=file_result.file_name,
                    tool=file_result.tool,
                    status=file_result.status,
                    changes=[_copy_model(change, ChangeData) for change in file_result.changes],
                    issue=_copy_model(file_result.issue, ParseIssueData) if file_result.issue is not None else None,
                )
                for file_result in parse_batch.files
            ]
        ),
        assessment=AssessmentData(
            score=assessment.score,
            severity=assessment.severity,
            recommendation=assessment.recommendation,
            top_risk=assessment.top_risk,
            contributors=[_copy_model(contributor, RiskContributorData) for contributor in assessment.contributors],
            interaction_risks=[_copy_model(interaction_risk, InteractionRiskData) for interaction_risk in assessment.interaction_risks],
            partial_context=assessment.partial_context,
            warnings=list(assessment.warnings),
        ),
        blast_radius=BlastRadiusData(
            affected=[_copy_model(node, ImpactNodeData) for node in blast_radius.affected],
            direct_count=blast_radius.direct_count,
            transitive_count=blast_radius.transitive_count,
            warning=blast_radius.warning,
            unmatched_resources=list(blast_radius.unmatched_resources),
        ),
        rollback_plan=RollbackPlanData(
            steps=[_copy_model(step, RollbackStepData) for step in rollback_plan.steps],
            complexity=rollback_plan.complexity,
            warning=rollback_plan.warning,
        ),
        incident_matches=[_copy_model(match, IncidentMatchData) for match in incident_matches],
        narrative=_copy_model(narrative, NarrativeData),
        advisory=_copy_model(advisory, AdvisorySummaryData),
        share_summary=_copy_model(share_summary, ShareSummaryData),
        persisted_report=PersistedReportData.model_validate(persisted_report),
    )
