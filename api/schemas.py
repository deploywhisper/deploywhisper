"""Shared API schemas."""

from __future__ import annotations

import math
from typing import Any, Literal

from config import settings
from evidence.models import FindingEvidenceClassification
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

from services.confidence_ledger import (
    EvidenceLawStatus,
    normalize_confidence_ledger_payload,
)


class MetaPayload(BaseModel):
    app: str = Field(..., description="Application identifier")
    version: str = Field(..., description="Application version")


def build_meta(**extra: Any) -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        **extra,
    }


def build_report_meta(*, report_schema_version: str, **extra: Any) -> dict[str, Any]:
    """Build metadata for report-bearing API responses."""
    extra.setdefault("api_version", "v1")
    return build_meta(report_schema_version=report_schema_version, **extra)


class HealthData(BaseModel):
    status: str = Field(..., description="Service health status")
    mode: str = Field(..., description="Current application mode")
    core_status: str = Field(..., description="Core system health status")
    llm: "LlmHealthData" = Field(
        ..., description="Narrative provider readiness reported separately from core"
    )


class HealthResponse(BaseModel):
    data: HealthData
    meta: MetaPayload


class LlmHealthData(BaseModel):
    status: Literal["ok", "degraded"] = Field(..., description="LLM readiness status")
    ready: bool = Field(..., description="Whether the LLM provider is ready")
    provider: str = Field(..., description="Configured LLM provider")
    model: str = Field(..., description="Configured LLM model")
    local_mode: bool = Field(..., description="Whether local-only mode is active")
    requires_api_key: bool = Field(
        ..., description="Whether the selected provider requires an API key"
    )
    has_api_key: bool = Field(
        ..., description="Whether an API key is currently available"
    )
    message: str = Field(..., description="Human-readable readiness summary")
    source: str = Field(
        ..., description="Where the provider settings were resolved from"
    )
    capabilities: "ProviderCapabilityData" = Field(
        ..., description="Explicit capability metadata for the selected provider"
    )


class ProviderCapabilityData(BaseModel):
    supports_structured_output: bool = Field(
        ..., description="Whether the provider supports structured JSON responses"
    )
    supports_remote_mcp: bool = Field(
        ..., description="Whether the provider supports future remote MCP execution"
    )
    supports_local_mcp: bool = Field(
        ..., description="Whether the provider supports future local MCP execution"
    )
    supports_tool_approval: bool = Field(
        ..., description="Whether the provider supports explicit tool approval flows"
    )
    supports_local_only_mode: bool = Field(
        ..., description="Whether the provider supports fully local-only operation"
    )


class ProviderOptionData(BaseModel):
    provider: str = Field(..., description="Provider identifier")
    label: str = Field(..., description="Display label")
    model: str = Field(..., description="Default model")
    api_base: str = Field(..., description="Default API base URL")
    local_mode: bool = Field(..., description="Default local-only mode")
    requires_api_key: bool = Field(
        ..., description="Whether this provider requires an API key"
    )
    capabilities: ProviderCapabilityData = Field(
        ..., description="Provider capability metadata"
    )


class ProviderSettingsData(BaseModel):
    provider: str = Field(..., description="Configured provider identifier")
    model: str = Field(..., description="Configured model")
    api_base: str = Field(..., description="Configured API base URL")
    local_mode: bool = Field(..., description="Whether local-only mode is active")
    request_timeout_seconds: float = Field(
        ..., description="Provider request timeout in seconds"
    )
    source: str = Field(..., description="Where settings were resolved from")
    api_key_present: bool = Field(
        ..., description="Whether an API key is available from the runtime"
    )
    api_key_preview: str | None = Field(
        default=None, description="Masked API key presence hint"
    )
    capabilities: ProviderCapabilityData = Field(
        ..., description="Provider capability metadata"
    )


class ProviderSettingsRequest(BaseModel):
    provider: str = Field(..., min_length=1, description="Provider identifier")
    model: str = Field(..., min_length=1, description="Model identifier")
    api_base: str = Field(..., min_length=1, description="Provider API base URL")
    request_timeout_seconds: float | None = Field(
        default=None,
        gt=0,
        le=600,
        description="Provider request timeout in seconds",
    )
    api_key: str | None = Field(
        default=None, description="Optional API key used for immediate validation"
    )
    local_mode: bool = Field(
        default=False, description="Whether to activate local-only mode"
    )


class ProviderValidationData(BaseModel):
    valid: bool = Field(..., description="Whether settings validated")
    message: str = Field(..., description="Validation message")


class ProviderSettingsSaveData(BaseModel):
    settings: ProviderSettingsData
    validation: ProviderValidationData


class ProviderSettingsResponse(BaseModel):
    data: ProviderSettingsSaveData
    meta: MetaPayload


ToolType = Literal[
    "terraform", "kubernetes", "ansible", "jenkins", "cloudformation", "unsupported"
]
IntakeStatus = Literal["ready", "unsupported", "sensitive"]
ParseStatus = Literal["parsed", "failed", "skipped"]
RiskSeverity = Literal["low", "medium", "high", "critical"]
DeployRecommendation = Literal["go", "caution", "no-go"]
RollbackComplexity = Literal["low", "medium", "high"]
DeploymentOutcomeLabel = Literal["success", "failure", "rolled_back"]
DeploymentOutcomeInputLabel = Literal["success", "failure", "rolled_back", "rollback"]
OwnerSignalScope = Literal["file", "service"]


def _validate_non_empty_strings(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            raise ValueError("List values must be non-empty strings.")
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


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
    api_version: str = Field(
        default="v1", description="Versioned API contract identifier"
    )
    report_schema_version: str = Field(
        ...,
        description=(
            "Report schema version used by returned report payloads when uniform; "
            "inspect report_schema_versions when multiple versions are present"
        ),
    )
    report_schema_versions: list[str] = Field(
        default_factory=list,
        description="Distinct report schema versions present in returned items",
    )
    count: int = Field(..., description="Count of returned items")
    total_count: int | None = Field(
        default=None, description="Total number of matching items"
    )
    page: int | None = Field(default=None, description="Current results page")
    page_size: int | None = Field(default=None, description="Current results page size")


class ResourceMetaPayload(MetaPayload):
    api_version: str = Field(
        default="v1", description="Versioned API contract identifier"
    )
    report_schema_version: str = Field(
        ..., description="Report schema version used by the returned payload"
    )
    id: int = Field(..., description="Stable resource identifier")


class ListMetaPayload(MetaPayload):
    count: int = Field(..., description="Count of returned items")


class ResourceOnlyMetaPayload(MetaPayload):
    id: int = Field(..., description="Stable resource identifier")


class AnalysisRunMetaPayload(MetaPayload):
    api_version: str = Field(..., description="Versioned API contract identifier")
    report_schema_version: str = Field(
        ..., description="Report schema version used by the response payload"
    )
    advisory_only: bool = Field(
        ...,
        description="Whether the analysis is advisory rather than deployment-blocking",
    )
    submitted_artifact_count: int = Field(
        ..., description="Number of uploaded artifacts received"
    )
    accepted_artifact_count: int = Field(
        ..., description="Number of artifacts accepted for analysis"
    )


class ErrorPayload(BaseModel):
    code: str = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Human-readable error summary")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Optional machine-readable error details"
    )


class ErrorResponse(BaseModel):
    error: ErrorPayload


class AuditMetadataData(BaseModel):
    files_analyzed: list[str] = Field(
        default_factory=list, description="Artifacts included in the persisted analysis"
    )
    llm_provider: str | None = Field(
        default=None, description="Narrative provider used for this analysis"
    )
    llm_model: str | None = Field(
        default=None, description="Narrative model used for this analysis"
    )
    llm_local_mode: bool | None = Field(
        default=None, description="Whether narrative generation used local-only mode"
    )
    source_interface: str | None = Field(
        default=None, description="Boundary surface that triggered the analysis"
    )
    trigger_type: str | None = Field(
        default=None, description="Trigger category when available"
    )
    trigger_id: str | None = Field(
        default=None, description="Trigger identifier when available"
    )
    actor: str = Field(
        default="service_actor",
        description="Actor or automation identity that submitted the analysis",
    )
    persisted_at: str | None = Field(
        default=None,
        description=(
            "Persisted report row creation timestamp; emitted only after final "
            "artifact persistence succeeds"
        ),
    )
    redaction_status: str = Field(
        default="unknown", description="Overall redaction state for persisted evidence"
    )
    redaction: dict[str, Any] = Field(
        default_factory=dict, description="Detailed redaction metadata"
    )
    delivery: dict[str, Any] = Field(
        default_factory=dict, description="Delivery metadata for the successful result"
    )


class SubmissionManifestItemData(BaseModel):
    name: str = Field(..., description="Normalized artifact name")
    tool: str = Field(..., description="Detected tool family")
    status: Literal["accepted", "excluded", "failed", "sensitive"] = Field(
        ..., description="Final manifest outcome"
    )
    intake_status: str = Field(..., description="Upload classification outcome")
    parse_status: str | None = Field(
        default=None, description="Parser outcome when parsing was attempted"
    )
    message: str = Field(..., description="Human-readable outcome summary")
    partial: bool = Field(
        default=False, description="Whether this artifact reduced analysis coverage"
    )
    redaction_status: str = Field(
        default="none", description="Filename/content redaction outcome"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Submission source metadata"
    )


class SubmissionManifestData(BaseModel):
    submitted_artifact_count: int = Field(
        default=0, description="Number of artifacts submitted"
    )
    accepted_artifact_count: int = Field(
        default=0, description="Artifacts accepted for parser analysis"
    )
    analyzed_artifact_count: int = Field(
        default=0, description="Accepted artifacts parsed into normalized changes"
    )
    excluded_artifact_count: int = Field(
        default=0, description="Artifacts excluded from parser analysis"
    )
    sensitive_artifact_count: int = Field(
        default=0, description="Sensitive artifacts excluded from unsafe handling"
    )
    failed_artifact_count: int = Field(
        default=0, description="Accepted artifacts that failed parser analysis"
    )
    partial_artifact_count: int = Field(
        default=0, description="Artifacts that made the analysis partial"
    )
    partial_analysis: bool = Field(
        default=False, description="Whether the analysis used partial coverage"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Submission-level source metadata"
    )
    redaction: dict[str, Any] = Field(
        default_factory=dict, description="Submission-level redaction metadata"
    )
    items: list[SubmissionManifestItemData] = Field(default_factory=list)


class SubmissionManifestFallbackItemData(BaseModel):
    name: str = Field(..., description="Artifact name retained outside manifest JSON")
    tool: str = Field(..., description="Detected or inferred tool family")
    status: str = Field(..., description="Fallback artifact outcome")
    intake_status: str = Field(..., description="Upload classification outcome")
    parse_status: str | None = Field(
        default=None, description="Parser outcome when parsing was attempted"
    )
    partial: bool = Field(
        default=False, description="Whether this artifact reduced analysis coverage"
    )
    redaction_status: str = Field(
        default="none", description="Filename/content redaction outcome"
    )
    actor: str | None = Field(
        default=None,
        description="Fallback submitter identity retained outside manifest JSON",
    )


class ProjectData(BaseModel):
    id: int = Field(..., description="Stable project/workspace identifier")
    project_key: str = Field(..., description="Stable project/workspace key")
    display_name: str = Field(..., description="Human-readable project name")
    description: str | None = Field(default=None, description="Optional description")
    repository_url: str | None = Field(
        default=None, description="Optional repository URL"
    )
    default_branch: str | None = Field(
        default=None, description="Optional default branch"
    )
    is_default: bool = Field(
        default=False, description="Whether this is the legacy default workspace"
    )
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")

    @computed_field(return_type=str)
    @property
    def name(self) -> str:
        """Dashboard-friendly alias for display_name."""
        return self.display_name

    @computed_field(return_type=str)
    @property
    def env_label(self) -> str:
        """Short label for project switcher secondary text."""
        if self.default_branch:
            return self.default_branch
        if self.is_default:
            return "default"
        return self.project_key


class ConfidenceLedgerData(BaseModel):
    contributors: list[str] = Field(
        default_factory=list,
        description="Reviewer-facing contributor lines backing the verdict",
    )
    confidence_factors: list[str] = Field(
        default_factory=list,
        description="Confidence signals used to interpret the verdict",
    )
    why_not_lower: list[str] = Field(
        default_factory=list,
        description="Evidence-backed reasons the verdict is not lower",
    )
    why_not_higher: list[str] = Field(
        default_factory=list,
        description="Evidence-backed reasons the verdict is not higher",
    )
    uncertainty_drivers: list[str] = Field(
        default_factory=list,
        description="Context and evidence limitations affecting certainty",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, data: Any) -> dict[str, list[str]]:
        return normalize_confidence_ledger_payload(data)


class PersistedReportData(BaseModel):
    id: int
    project: ProjectData = Field(..., description="Owning project/workspace")
    workspace: "WorkspaceData | None" = Field(
        default=None, description="Optional project-local workspace/environment scope"
    )
    risk_score: int
    severity: str
    recommendation: str
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Overall verdict confidence"
    )
    top_risk: str
    report_schema_version: str = Field(
        ..., description="Persisted report schema version"
    )
    tool_mix: list[str] = Field(
        default_factory=list,
        description="Supported toolchains represented in this persisted report",
    )
    analysis_status: Literal["complete", "degraded", "fallback"] = Field(
        default="complete",
        description="High-level persisted analysis completion/degradation status",
    )
    top_risk_contributors: list[str] = Field(default_factory=list)
    context_completeness: "ContextCompletenessData" = Field(
        default_factory=lambda: ContextCompletenessData()
    )
    blast_radius: "BlastRadiusData" = Field(
        default_factory=lambda: BlastRadiusData(direct_count=0, transitive_count=0)
    )
    rollback_plan: "RollbackPlanData" = Field(
        default_factory=lambda: RollbackPlanData(complexity="low")
    )
    parse_summary: str
    narrative_opening: str
    narrative_available: bool = Field(
        default=True, description="Whether narrative text is available"
    )
    narrative_degraded: bool = Field(
        ...,
        description=(
            "Whether narrative output used fallback mode or is inferred unavailable"
        ),
    )
    narrative_failure_notice: str | None = Field(
        default=None,
        description="Visible explanation when narrative generation was unavailable",
    )
    assessment_source: Literal["heuristic-only", "heuristic+llm"] | None = Field(
        default=None
    )
    narrative_source: Literal["llm", "fallback"] | None = Field(default=None)
    narrative_provider: str | None = Field(default=None)
    narrative_model: str | None = Field(default=None)
    narrative_local_mode: bool | None = Field(default=None)
    advisory: "AdvisorySummaryData" = Field(
        ..., description="Stable advisory recommendation contract for automation"
    )
    skills_applied: list[str] = Field(default_factory=list)
    created_at: str
    warnings: list[str] = Field(default_factory=list)
    findings: list["FindingData"] = Field(default_factory=list)
    evidence_items: list["EvidenceItemData"] = Field(default_factory=list)
    incident_matches: list["IncidentMatchData"] = Field(default_factory=list)
    contributors: list["RiskContributorData"] = Field(default_factory=list)
    confidence_ledger: ConfidenceLedgerData = Field(
        default_factory=ConfidenceLedgerData,
        description="Shared confidence ledger and why-not boundary explanations",
    )
    dashboard_display_duration_seconds: int | None = Field(default=None)
    dashboard_remaining_seconds: int | None = Field(default=None)
    analysis_duration_seconds: int | None = Field(default=None)
    submission_manifest: SubmissionManifestData | None = Field(
        default=None,
        description="Submission manifest metadata, or null when persisted manifest data is unavailable",
    )
    submission_manifest_fallback: list[SubmissionManifestFallbackItemData] = Field(
        default_factory=list,
        description="Durable artifact identity/status fallback retained outside manifest JSON",
    )
    audit: AuditMetadataData

    @computed_field(return_type=int)
    @property
    def score(self) -> int:
        """Dashboard-friendly alias for risk_score."""
        return self.risk_score

    @computed_field(return_type=str)
    @property
    def verdict(self) -> str:
        """Dashboard-friendly alias for recommendation."""
        return self.recommendation

    @computed_field(return_type=list[str])
    @property
    def filenames(self) -> list[str]:
        """Dashboard-friendly alias for analyzed artifact names."""
        return list(self.audit.files_analyzed)

    @computed_field(return_type=str)
    @property
    def workspace_label(self) -> str:
        """Human-friendly workspace label for compact dashboard rows."""
        if self.workspace is not None:
            return self.workspace.display_name
        return self.project.display_name

    @computed_field(return_type=str)
    @property
    def env_label(self) -> str:
        """Environment label for compact dashboard rows."""
        if self.workspace is not None:
            return self.workspace.environment or self.workspace.workspace_key
        return self.project.env_label

    @computed_field(return_type=str | None)
    @property
    def trigger_ref(self) -> str | None:
        """Dashboard-friendly alias for audit trigger identifiers."""
        return self.audit.trigger_id

    @computed_field(return_type=str | None)
    @property
    def pr_ref(self) -> str | None:
        """Pull-request reference when the trigger metadata identifies one."""
        trigger_type = str(self.audit.trigger_type or "").strip().lower()
        if trigger_type in {"pr", "pull_request", "pull-request", "github_pr"}:
            return self.audit.trigger_id
        return None

    @model_validator(mode="before")
    @classmethod
    def normalize_context_completeness_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        context_payload = normalized.get("context_completeness")
        normalized["context_completeness"] = _known_context_fields_payload(
            context_payload,
            ContextCompletenessData,
        )
        return normalized


class PreviousScanDiffData(BaseModel):
    previous_report_id: int = Field(..., description="Prior scan report id")
    previous_created_at: str = Field(..., description="Prior scan timestamp")
    score_delta: int = Field(..., description="Risk score delta from prior scan")
    score_direction: Literal["up", "down", "flat"] = Field(
        ..., description="Risk score movement direction"
    )
    previous_severity: str = Field(..., description="Prior scan severity")
    current_severity: str = Field(..., description="Current scan severity")
    previous_recommendation: str = Field(..., description="Prior recommendation")
    current_recommendation: str = Field(..., description="Current recommendation")


class AnalysisReportData(PersistedReportData):
    previous_scan_diff: PreviousScanDiffData | None = Field(
        default=None,
        description="Compact rescan delta against the previous scan of matching artifacts.",
    )


class AnalysisBulkDeleteRequest(BaseModel):
    ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Analysis report ids to delete.",
    )


class AnalysisBulkDeleteData(BaseModel):
    requested_count: int = Field(..., description="Number of requested report ids")
    deleted_count: int = Field(..., description="Number of deleted reports")
    deleted_ids: list[int] = Field(
        default_factory=list, description="Report ids requested for deletion"
    )


class AnalysisBulkDeleteResponse(BaseModel):
    data: AnalysisBulkDeleteData
    meta: MetaPayload


class ProjectCreateRequest(BaseModel):
    project_key: str = Field(..., description="Stable project/workspace key")
    display_name: str = Field(..., description="Human-readable project name")
    description: str | None = Field(default=None, description="Optional description")
    repository_url: str | None = Field(
        default=None, description="Optional repository URL"
    )
    default_branch: str | None = Field(
        default=None, description="Optional default branch"
    )


class WorkspaceCreateRequest(BaseModel):
    workspace_key: str = Field(..., description="Stable workspace/environment key")
    display_name: str = Field(..., description="Human-readable workspace name")
    description: str | None = Field(default=None, description="Optional description")
    environment: str | None = Field(
        default=None, description="Optional environment label such as prod or staging"
    )


class WorkspaceData(BaseModel):
    id: int = Field(..., description="Stable workspace identifier")
    project_id: int = Field(..., description="Owning project identifier")
    project_key: str = Field(..., description="Owning stable project key")
    workspace_key: str = Field(..., description="Stable workspace/environment key")
    display_name: str = Field(..., description="Human-readable workspace name")
    description: str | None = Field(default=None, description="Optional description")
    environment: str | None = Field(
        default=None, description="Optional environment label"
    )
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class ProjectRoleData(BaseModel):
    role: str = Field(..., description="Stable project role identifier")
    display_name: str = Field(..., description="Human-readable role name")
    description: str = Field(..., description="Role capability summary")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Stable project capability identifiers granted to this role",
    )


class ProjectListResponse(BaseModel):
    data: list[ProjectData]
    meta: ListMetaPayload


class ProjectRoleListResponse(BaseModel):
    data: list[ProjectRoleData]
    meta: ListMetaPayload


class ProjectResponse(BaseModel):
    data: ProjectData
    meta: ResourceOnlyMetaPayload


class WorkspaceListResponse(BaseModel):
    data: list[WorkspaceData]
    meta: ListMetaPayload


class WorkspaceResponse(BaseModel):
    data: WorkspaceData
    meta: ResourceOnlyMetaPayload


class DeploymentOutcomeCreateRequest(BaseModel):
    analysis_id: int = Field(..., description="Analysis identifier for the deployment.")
    outcome: DeploymentOutcomeInputLabel = Field(
        ..., description="Final deployment result for the analyzed change."
    )
    deployed_at: str = Field(..., description="Deployment completion timestamp.")
    linked_incident_id: int | None = Field(
        default=None,
        description="Optional linked incident identifier when the deployment failed.",
    )
    environment: str | None = Field(
        default=None,
        description="Optional environment label such as prod or staging.",
    )
    summary: str | None = Field(
        default=None,
        description="Optional operator summary for the deployment outcome.",
    )
    notes: str | None = Field(
        default=None,
        description="Optional operator notes for the deployment outcome.",
    )
    project_id: int | None = Field(
        default=None, description="Optional numeric project identifier."
    )
    project_key: str | None = Field(
        default=None, description="Optional stable project key."
    )
    workspace_id: int | None = Field(
        default=None, description="Optional numeric workspace identifier."
    )
    workspace_key: str | None = Field(
        default=None, description="Optional stable workspace key."
    )


class DeploymentOutcomeData(BaseModel):
    id: int = Field(..., description="Stable deployment outcome identifier.")
    project: ProjectData = Field(..., description="Owning project/workspace.")
    workspace: WorkspaceData | None = Field(
        default=None, description="Optional workspace/environment scope."
    )
    analysis_id: int | None = Field(
        default=None,
        description="Analysis report identifier tied to this deployment.",
    )
    outcome: DeploymentOutcomeLabel = Field(
        ..., description="Normalized deployment outcome label."
    )
    deployed_at: str = Field(..., description="Deployment completion timestamp.")
    linked_incident_id: int | None = Field(
        default=None,
        description="Linked incident identifier when available.",
    )
    environment: str | None = Field(
        default=None, description="Optional environment label."
    )
    summary: str | None = Field(default=None, description="Optional operator summary.")
    notes: str | None = Field(default=None, description="Optional operator notes.")
    created_at: str = Field(..., description="Outcome record creation timestamp.")


class DeploymentOutcomeListResponse(BaseModel):
    data: list[DeploymentOutcomeData]
    meta: ListMetaPayload


class DeploymentOutcomeResponse(BaseModel):
    data: DeploymentOutcomeData
    meta: ResourceOnlyMetaPayload


class StatsBucketData(BaseModel):
    date: str = Field(..., description="UTC calendar date for the bucket")
    value: float = Field(..., description="Metric value for the bucket")


class StatsSummaryTotalsData(BaseModel):
    analyses: int = Field(..., description="Total persisted analyses")
    clean_verdict_rate: float = Field(
        ..., description="Percentage of low-severity analyses"
    )
    open_high_critical_count: int = Field(
        ..., description="Count of high or critical analyses"
    )
    avg_time_to_verdict_seconds: float | None = Field(
        default=None,
        description="Average positive analysis_duration_seconds across reports",
    )


class StatsSummarySeriesData(BaseModel):
    analyses: list[StatsBucketData] = Field(
        default_factory=list, description="Seven daily analysis-count buckets"
    )
    clean_verdict_rate: list[StatsBucketData] = Field(
        default_factory=list, description="Seven daily clean-rate buckets"
    )
    open_high_critical_count: list[StatsBucketData] = Field(
        default_factory=list, description="Seven daily high/critical-count buckets"
    )
    avg_time_to_verdict_seconds: list[StatsBucketData] = Field(
        default_factory=list, description="Seven daily average-duration buckets"
    )


class StatsSummaryData(BaseModel):
    totals: StatsSummaryTotalsData
    total_analyses: int = Field(..., description="Total persisted analyses")
    clean_verdict_rate: float = Field(
        ..., description="Percentage of low-severity analyses"
    )
    open_high_critical_count: int = Field(
        ..., description="Count of high or critical analyses"
    )
    avg_time_to_verdict_seconds: float | None = Field(
        default=None, description="Average positive analysis duration in seconds"
    )
    series: StatsSummarySeriesData


class StatsSummaryResponse(BaseModel):
    data: StatsSummaryData
    meta: MetaPayload


class VerdictDistributionData(BaseModel):
    days: int = Field(..., description="Lookback window in days")
    window_start: str = Field(..., description="Inclusive UTC window start")
    window_end: str = Field(..., description="Inclusive UTC window end")
    counts: dict[str, int] = Field(
        default_factory=dict, description="Counts keyed by advisory recommendation"
    )
    total: int = Field(..., description="Total reports included in the window")


class VerdictDistributionResponse(BaseModel):
    data: VerdictDistributionData
    meta: MetaPayload


class TopologyStatusData(BaseModel):
    path: str = Field(..., description="Logical or file path for the topology source")
    exists: bool = Field(..., description="Whether an active topology exists")
    updated_at: str | None = Field(
        default=None, description="Last update timestamp when available"
    )
    service_count: int = Field(default=0, description="Number of services")
    dependency_count: int = Field(default=0, description="Number of dependencies")
    resource_key_count: int = Field(
        default=0, description="Number of resource mappings"
    )
    preview_services: list[str] = Field(
        default_factory=list, description="Preview of service labels"
    )
    warnings: list[str] = Field(default_factory=list, description="Topology warnings")
    blocking_errors: list[str] = Field(
        default_factory=list, description="Blocking validation errors"
    )
    drift: "TopologyDriftStatusData | None" = Field(
        default=None, description="Latest drift check summary when available"
    )


class TopologyDriftStatusData(BaseModel):
    status: str = Field(..., description="Current topology drift state")
    checked_at: str | None = Field(
        default=None, description="ISO timestamp for the latest drift check"
    )
    next_check_at: str | None = Field(
        default=None, description="ISO timestamp for the next scheduled drift check"
    )
    interval_hours: int = Field(
        default=24, description="Configured drift check cadence in hours"
    )
    source_type: str | None = Field(
        default=None, description="Imported topology source identifier when available"
    )
    source_ref: str | None = Field(
        default=None, description="Imported topology source reference when available"
    )
    total_resource_count: int = Field(
        default=0, description="Total resources considered during the drift check"
    )
    changed_resource_count: int = Field(
        default=0, description="Number of changed resources in the latest drift check"
    )
    change_percent: float = Field(
        default=0.0, description="Percentage of changed resources"
    )
    alert: bool = Field(
        default=False,
        description="Whether the drift report exceeds the alert threshold",
    )
    added_resources: list[str] = Field(default_factory=list)
    removed_resources: list[str] = Field(default_factory=list)
    modified_resources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TopologyContextRequest(BaseModel):
    topology: dict[str, Any] = Field(..., description="Topology JSON payload")
    project_id: int | None = Field(
        default=None, description="Optional numeric project identifier"
    )
    project_key: str | None = Field(
        default=None, description="Optional stable project key"
    )
    workspace_id: int | None = Field(
        default=None, description="Optional numeric workspace identifier"
    )
    workspace_key: str | None = Field(
        default=None, description="Optional stable workspace key"
    )


class TopologyContextData(BaseModel):
    project: ProjectData = Field(..., description="Owning project/workspace")
    topology: TopologyStatusData = Field(..., description="Topology status payload")


class TopologyContextResponse(BaseModel):
    data: TopologyContextData
    meta: MetaPayload


class TopologyUploadRequest(BaseModel):
    topology: dict[str, Any] = Field(..., description="Topology JSON payload")
    project_id: int | None = Field(
        default=None, description="Optional numeric project identifier"
    )
    project_key: str | None = Field(
        default=None, description="Optional stable project key"
    )
    workspace_id: int | None = Field(
        default=None, description="Optional numeric workspace identifier"
    )
    workspace_key: str | None = Field(
        default=None, description="Optional stable workspace key"
    )


class TopologyValidationData(BaseModel):
    topology: TopologyStatusData
    success_message: str | None = Field(
        default=None, description="Human-readable success message"
    )
    error_message: str | None = Field(
        default=None, description="Human-readable validation error"
    )


class TopologyValidationResponse(BaseModel):
    data: TopologyValidationData
    meta: MetaPayload


class TopologyDriftCadenceData(BaseModel):
    interval_hours: int = Field(..., description="Active drift check cadence")
    options: list[int] = Field(
        default_factory=list, description="Supported cadence options in hours"
    )


class TopologyDriftCadenceRequest(BaseModel):
    interval_hours: int = Field(..., description="Desired drift check cadence")


class TopologyDriftCadenceResponse(BaseModel):
    data: TopologyDriftCadenceData
    meta: MetaPayload


class FeedbackCurrentStateData(BaseModel):
    useful_count: int = Field(default=0)
    noisy_count: int = Field(default=0)
    not_useful_count: int = Field(default=0)
    false_positive_count: int = Field(default=0)
    missed_finding_count: int = Field(default=0)


class FeedbackTotalsData(BaseModel):
    events_recorded: int = Field(default=0)


class FeedbackRecentNoteData(BaseModel):
    type: str = Field(..., description="Feedback note type")
    text: str = Field(..., description="Reviewer note")
    analysis_id: int | None = Field(default=None)
    finding_id: str | None = Field(default=None)
    created_at: str = Field(..., description="UTC timestamp")


class FeedbackSummaryData(BaseModel):
    project: ProjectData
    current_state: FeedbackCurrentStateData
    totals: FeedbackTotalsData
    recent_notes: list[FeedbackRecentNoteData] = Field(default_factory=list)


class CustomSkillStatusData(BaseModel):
    name: str = Field(..., description="Stable skill name")
    mode: Literal["override", "new"] = Field(
        ..., description="Whether the skill overrides a built-in skill"
    )
    active: bool = Field(..., description="Whether the skill is active")
    path: str = Field(..., description="Filesystem path")
    warning: str | None = Field(default=None, description="Ignored-state warning")


class CustomSkillUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, description="Markdown skill filename")
    content: str = Field(..., min_length=1, description="Markdown skill content")


class CustomSkillUploadData(BaseModel):
    statuses: list[CustomSkillStatusData] = Field(default_factory=list)
    saved: CustomSkillStatusData | None = Field(default=None)
    success_message: str | None = Field(default=None)
    error_message: str | None = Field(default=None)


class CustomSkillUploadResponse(BaseModel):
    data: CustomSkillUploadData
    meta: MetaPayload


class CustomSkillListResponse(BaseModel):
    data: list[CustomSkillStatusData]
    meta: MetaPayload


class SettingsSummaryData(BaseModel):
    provider: ProviderSettingsData
    provider_options: list[ProviderOptionData]
    topology: TopologyStatusData
    drift_cadence: TopologyDriftCadenceData
    feedback: FeedbackSummaryData
    custom_skills: list[CustomSkillStatusData] = Field(default_factory=list)


class SettingsSummaryResponse(BaseModel):
    data: SettingsSummaryData
    meta: MetaPayload


class ChangeData(BaseModel):
    source_file: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Source tool name")
    resource_id: str = Field(..., description="Resource identifier")
    action: str = Field(..., description="Change action")
    summary: str = Field(..., description="Human-readable summary")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional parser-specific normalized metadata",
    )


class ParseIssueData(BaseModel):
    file_name: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Detected or expected tool")
    message: str = Field(..., description="Why parsing failed or was partial")


class ParsedArtifactData(BaseModel):
    file_name: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Detected tool")
    status: ParseStatus = Field(..., description="Parse outcome for this file")
    changes: list[ChangeData] = Field(
        default_factory=list, description="Normalized changes"
    )
    issue: ParseIssueData | None = Field(
        default=None, description="Failure context if parsing failed"
    )


class ParseBatchData(BaseModel):
    files: list[ParsedArtifactData] = Field(
        default_factory=list, description="Per-file parse results"
    )


class InteractionRiskData(BaseModel):
    key: str = Field(..., description="Stable identifier for the interaction pattern")
    summary: str = Field(..., description="User-facing explanation of the interaction")
    contributing_files: list[str] = Field(
        default_factory=list, description="Files involved"
    )
    contributing_resources: list[str] = Field(
        default_factory=list, description="Resources involved"
    )
    contribution_bonus: int = Field(..., description="Additional score contribution")


class RiskContributorData(BaseModel):
    evidence_id: str | None = Field(
        default=None, description="Evidence item that produced this contributor"
    )
    source_file: str = Field(..., description="Source file for the contributing change")
    tool: str = Field(..., description="Tool that produced the change")
    resource_id: str = Field(..., description="Resource affected by the change")
    action: str = Field(..., description="Change action")
    contribution: int = Field(..., description="Contribution to the final score")
    summary: str = Field(..., description="Human-readable explanation")
    normalized_action: str = Field(
        default="modify", description="Normalized lifecycle action"
    )
    resource_category: str = Field(
        default="generic infrastructure", description="Resource blast-radius category"
    )
    blast_radius: str = Field(default="unknown", description="Blast-radius explanation")
    downstream_scope: int | None = Field(
        default=None, description="Approximate downstream scope count"
    )
    security_flags: list[str] = Field(
        default_factory=list, description="Detected security-sensitive findings"
    )
    environment: str = Field(
        default="unknown", description="Inferred target environment"
    )
    severity: RiskSeverity = Field(..., description="Per-resource severity")
    reasoning: str = Field(default="", description="Per-resource scoring explanation")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Parser-specific normalized metadata carried into reports",
    )


class FindingData(BaseModel):
    finding_id: str = Field(..., description="Stable finding identifier")
    analysis_id: int = Field(..., description="Analysis identifier")
    title: str = Field(..., description="Reviewer-facing finding title")
    description: str = Field(..., description="Detailed finding description")
    explanation: str = Field(default="", description="Why the finding matters")
    guidance: list[str] = Field(
        default_factory=list,
        description="Reviewer verification or remediation guidance",
    )
    severity: RiskSeverity = Field(..., description="Finding severity")
    category: str = Field(..., description="Finding category")
    deterministic: bool = Field(
        ..., description="Whether the finding came from deterministic logic"
    )
    confidence: float = Field(..., description="Confidence score between 0 and 1")
    uncertainty_note: str | None = Field(
        default=None,
        description="Explanation when confidence reflects inferred reasoning",
    )
    evidence_classification: FindingEvidenceClassification = Field(
        default="deterministic",
        description="Dominant evidence support type for this finding",
    )
    evidence_refs: list[str] = Field(
        default_factory=list, description="Evidence IDs linked to the finding"
    )
    skill_id: str | None = Field(
        default=None,
        description="Skill identifier when a skill contributed the finding",
    )


class EvidenceItemData(BaseModel):
    evidence_id: str = Field(..., description="Stable evidence identifier")
    analysis_id: int = Field(..., description="Analysis identifier")
    finding_id: str = Field(..., description="Owning finding identifier")
    source_type: str = Field(..., description="Evidence source category")
    source_ref: str = Field(..., description="Stable source reference")
    artifact: str = Field(default="", description="Submitted artifact identifier")
    location: str = Field(default="", description="Inspectable artifact location")
    resource: str = Field(default="", description="Changed resource identifier")
    operation: str = Field(default="", description="Normalized change operation")
    project_id: int | None = Field(
        default=None, description="Project identifier for this evidence context"
    )
    project_key: str | None = Field(
        default=None, description="Project key for this evidence context"
    )
    workspace_id: int | None = Field(
        default=None, description="Workspace identifier for this evidence context"
    )
    workspace_key: str | None = Field(
        default=None, description="Workspace key for this evidence context"
    )
    source_kind: str = Field(default="artifact", description="Evidence source kind")
    determinism_level: str = Field(
        default="deterministic",
        description="Whether evidence was deterministic, heuristic, or inferred",
    )
    redaction_status: str = Field(
        default="none", description="Evidence redaction status"
    )
    summary: str = Field(..., description="Evidence summary")
    severity_hint: RiskSeverity = Field(
        ..., description="Severity hint for the evidence"
    )
    deterministic: bool = Field(
        ..., description="Whether the evidence came from deterministic logic"
    )
    confidence: float = Field(..., description="Confidence score between 0 and 1")
    related_change_ids: list[str] = Field(
        default_factory=list, description="Traceable normalized change identifiers"
    )


class OwnerSignalData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: OwnerSignalScope = Field(..., description="Ownership signal scope")
    subject: str = Field(
        ..., min_length=1, description="Owned file, service, or resource subject"
    )
    owners: list[str] = Field(
        default_factory=list, description="Owners identified for this subject"
    )
    source: str = Field(..., min_length=1, description="Ownership source type")
    source_ref: str | None = Field(
        default=None, min_length=1, description="Source file or topology reference"
    )
    matched_pattern: str | None = Field(
        default=None,
        min_length=1,
        description="CODEOWNERS pattern that matched the subject",
    )
    resource_id: str | None = Field(
        default=None,
        min_length=1,
        description="Changed resource linked to the signal",
    )
    service_id: str | None = Field(
        default=None,
        min_length=1,
        description="Topology service identifier linked to the signal",
    )
    escalation_hint: str = Field(
        ..., min_length=1, description="Reviewer-facing escalation guidance"
    )

    @field_validator("owners")
    @classmethod
    def _validate_owners(cls, value: list[str]) -> list[str]:
        return _validate_non_empty_strings(value)


class ContextCompletenessData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topology_freshness_days: int | None = Field(
        default=None,
        ge=0,
        description="Age in days of the topology snapshot when available",
    )
    topology_last_imported_at: str | None = Field(
        default=None,
        description="ISO timestamp for the last imported topology snapshot when available",
    )
    incident_index_size: int = Field(
        default=0,
        ge=0,
        description="Number of incidents available for similarity matching",
    )
    incident_index_version: str | None = Field(
        default=None,
        min_length=1,
        description="Incident index version used for context",
    )
    incident_index_last_indexed_at: str | None = Field(
        default=None,
        min_length=1,
        description="ISO timestamp for the incident index snapshot when available",
    )
    incident_index_freshness_status: str | None = Field(
        default=None,
        min_length=1,
        description="Freshness status for the incident index snapshot",
    )
    evidence_success_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
        description="Fraction of material changes represented by evidence items",
    )
    parser_success_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
        description="Fraction of analyzed files parsed successfully",
    )
    parser_success_by_tool: dict[str, float] = Field(
        default_factory=dict,
        description="Per-tool parser success rates between 0 and 1",
    )
    context_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
        description="Aggregate context completeness score between 0 and 1",
    )
    confidence_level: Literal["high", "medium", "low"] = Field(
        default="high",
        description="Human-readable confidence level derived from context completeness",
    )
    uncertainty: str | None = Field(
        default=None, description="Reviewer-facing uncertainty explanation"
    )
    context_todos: list[str] = Field(
        default_factory=list,
        description="Actionable context improvements for future reports",
    )
    insufficient_context: bool = Field(
        default=False,
        description="Whether context is too weak for a confident low-risk verdict",
    )
    partial_context: bool = Field(
        default=False,
        description="Whether analysis context was explicitly marked partial upstream",
    )
    owner_signals: list[OwnerSignalData] = Field(
        default_factory=list,
        description="File and service ownership signals for analyzed changes",
    )
    escalation_hints: list[str] = Field(
        default_factory=list,
        description="Reviewer-facing ownership escalation hints",
    )
    ownership_unmapped_subjects: list[str] = Field(
        default_factory=list,
        description="Analyzed files, resources, or services missing ownership data",
    )

    @field_validator("escalation_hints", "ownership_unmapped_subjects")
    @classmethod
    def _validate_ownership_strings(cls, value: list[str]) -> list[str]:
        return _validate_non_empty_strings(value)

    @field_validator("evidence_success_rate", "parser_success_rate", "context_score")
    @classmethod
    def _validate_unit_float(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("value must be a finite number between 0 and 1")
        return value

    @field_validator("parser_success_by_tool")
    @classmethod
    def _validate_parser_success_by_tool(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        normalized: dict[str, float] = {}
        for tool, rate in value.items():
            tool_name = str(tool).strip()
            if not tool_name:
                raise ValueError("parser success tool names must be non-empty")
            try:
                numeric_rate = float(rate)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "parser success rates must be finite numbers between 0 and 1"
                ) from exc
            if not math.isfinite(numeric_rate) or not 0.0 <= numeric_rate <= 1.0:
                raise ValueError(
                    "parser success rates must be finite numbers between 0 and 1"
                )
            normalized[tool_name] = numeric_rate
        return normalized


class AssessmentData(BaseModel):
    score: int = Field(..., description="Overall bounded risk score")
    severity: RiskSeverity = Field(..., description="Severity classification")
    recommendation: DeployRecommendation = Field(
        ..., description="Advisory recommendation"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Overall verdict confidence"
    )
    top_risk: str = Field(..., description="Most important risk summary")
    top_risk_contributors: list[str] = Field(
        default_factory=list,
        description="Evidence IDs that most influenced the final verdict",
    )
    context_completeness: ContextCompletenessData = Field(
        default_factory=ContextCompletenessData,
        description="Structured signal describing how complete the supporting context was",
    )
    contributors: list[RiskContributorData] = Field(
        default_factory=list, description="Score contributors"
    )
    confidence_ledger: ConfidenceLedgerData = Field(
        default_factory=ConfidenceLedgerData,
        description="Shared confidence ledger and why-not boundary explanations",
    )
    interaction_risks: list[InteractionRiskData] = Field(
        default_factory=list, description="Cross-tool interaction findings"
    )
    partial_context: bool = Field(..., description="Whether some files failed to parse")
    warnings: list[str] = Field(default_factory=list, description="Assessment warnings")
    source: Literal["heuristic-only", "heuristic+llm"] = Field(
        ...,
        description="Whether structured risk scoring was heuristic-only or LLM-assisted",
    )


class ImpactNodeData(BaseModel):
    service_id: str = Field(..., description="Stable service identifier")
    label: str = Field(..., description="Human-readable service label")
    depth: int = Field(..., description="0 for direct impact, 1+ for transitive impact")
    dependencies: list[str] = Field(
        default_factory=list,
        description="Upstream service ids this service depends on in topology context",
    )
    owners: list[str] = Field(
        default_factory=list,
        description="Owner labels declared for this topology service",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["dependencies"] = _text_list(normalized.get("dependencies"))
        normalized["owners"] = _text_list(normalized.get("owners"))
        return normalized


class BlastRadiusData(BaseModel):
    affected: list[ImpactNodeData] = Field(
        default_factory=list, description="Affected services"
    )
    direct_count: int = Field(..., description="Count of directly affected services")
    transitive_count: int = Field(
        ..., description="Count of transitively affected services"
    )
    warning: str | None = Field(
        default=None, description="Warning when impact may be incomplete"
    )
    unmatched_resources: list[str] = Field(
        default_factory=list, description="Resources not found in topology context"
    )
    context_source: dict[str, str | None] = Field(
        default_factory=lambda: {"type": None, "ref": None},
        description="Topology source metadata used for this blast-radius result",
    )
    freshness: dict[str, int | str | None] = Field(
        default_factory=lambda: {"updated_at": None, "age_days": None},
        description="Topology freshness metadata used for this blast-radius result",
    )
    context_state: str | None = Field(
        default="unknown",
        description="Topology context state: current, stale, missing, incomplete, conflicting, or unknown",
    )
    context_limitations: list[str] = Field(
        default_factory=list,
        description="Machine-readable topology context limitation labels",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_context(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if not isinstance(normalized.get("affected"), list):
            normalized["affected"] = []
        if not isinstance(normalized.get("context_source"), dict):
            normalized["context_source"] = {"type": None, "ref": None}
        if not isinstance(normalized.get("freshness"), dict):
            normalized["freshness"] = {"updated_at": None, "age_days": None}
        else:
            freshness = normalized["freshness"]
            updated_at = freshness.get("updated_at")
            age_days = freshness.get("age_days")
            normalized["freshness"] = {
                "updated_at": updated_at if isinstance(updated_at, str) else None,
                "age_days": age_days if isinstance(age_days, int | str) else None,
            }
        context_source = normalized.get("context_source")
        if isinstance(context_source, dict):
            normalized["context_source"] = {
                "type": _scalar_text_or_none(context_source.get("type")),
                "ref": _scalar_text_or_none(context_source.get("ref")),
            }
        context_state = normalized.get("context_state")
        if context_state is None or not isinstance(context_state, str):
            normalized["context_state"] = "unknown"
        normalized["context_limitations"] = _text_list(
            normalized.get("context_limitations")
        )
        return normalized

    @model_validator(mode="after")
    def normalize_context_defaults(self) -> "BlastRadiusData":
        context_source = dict(self.context_source or {})
        self.context_source = {
            "type": context_source.get("type"),
            "ref": context_source.get("ref"),
        }
        freshness = dict(self.freshness or {})
        self.freshness = {
            "updated_at": freshness.get("updated_at"),
            "age_days": freshness.get("age_days"),
        }
        return self


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _scalar_text_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int | float | bool):
        return str(value)
    return None


class RollbackStepData(BaseModel):
    order: int = Field(..., description="Execution order")
    title: str = Field(..., description="Short rollback step title")
    detail: str = Field(..., description="Operational rollback instruction")
    estimated_minutes: int = Field(
        default=5, description="Estimated time in minutes for this rollback step"
    )
    critical: bool = Field(
        ..., description="Whether this step is critical to safe recovery"
    )


class RollbackPlanData(BaseModel):
    steps: list[RollbackStepData] = Field(
        default_factory=list, description="Ordered rollback steps"
    )
    complexity: RollbackComplexity = Field(
        ..., description="Rollback complexity classification"
    )
    complexity_score: int = Field(
        default=1, description="Rollback complexity score on a 1-5 scale"
    )
    complexity_explanation: str = Field(
        default="Minimal rollback effort based on the available change set.",
        description="Human-readable explanation for the complexity score",
    )
    warning: str | None = Field(
        default=None, description="Warning if context is incomplete"
    )


class IncidentMatchData(BaseModel):
    incident_id: int = Field(..., description="Matched incident identifier")
    match_type: Literal["organization_incident", "public_risk_pattern"] = Field(
        default="organization_incident",
        description="Whether the match came from org incident memory or public patterns.",
    )
    public_pattern_id: str | None = Field(
        default=None, description="Built-in public risk pattern identifier."
    )
    title: str = Field(..., description="Incident title")
    severity: str = Field(..., description="Incident severity")
    source_file: str = Field(..., description="Incident source file")
    incident_date: str | None = Field(
        default=None, description="Incident date if available"
    )
    similarity: float = Field(..., description="Similarity score between 0 and 1")
    confidence: float = Field(
        default=0.0, description="Confidence that this memory signal applies."
    )
    confidence_label: Literal["high", "medium", "low"] = Field(
        default="low", description="Human-readable confidence bucket."
    )
    reason: str = Field(
        default="", description="Why the incident or public pattern matched."
    )
    evidence: list[str] = Field(
        default_factory=list, description="Concrete evidence supporting the match."
    )
    matched_signals: list[str] = Field(
        default_factory=list,
        description="Specific tokens, services, or risk signals that matched.",
    )
    affected_services: list[str] = Field(
        default_factory=list,
        description="Services affected in the matched incident or pattern.",
    )
    prevention_notes: list[str] = Field(
        default_factory=list,
        description="Prevention guidance from the incident or public pattern.",
    )
    verification_guidance: list[str] = Field(
        default_factory=list,
        description="Human verification steps before acting on the match.",
    )
    summary: str = Field(..., description="Short operational explanation")

    @model_validator(mode="before")
    @classmethod
    def _derive_confidence_label(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("confidence_label"):
            return value
        confidence = float(value.get("confidence") or 0.0)
        if confidence >= 0.5:
            label: Literal["high", "medium", "low"] = "high"
        elif confidence >= 0.35:
            label = "medium"
        else:
            label = "low"
        return {**value, "confidence_label": label}


class NarrativeData(BaseModel):
    available: bool = Field(
        default=True, description="Whether narrative text is available"
    )
    opening_sentence: str = Field(
        default="", description="First-scan deploy briefing sentence"
    )
    explanation: str = Field(
        default="", description="Extended plain-English explanation"
    )
    guidance: list[str] = Field(default_factory=list, description="Actionable guidance")
    degraded: bool = Field(..., description="Whether fallback mode was used")
    warnings: list[str] = Field(default_factory=list, description="Narrative warnings")
    failure_notice: str | None = Field(
        default=None,
        description="Visible explanation when narrative generation was unavailable",
    )
    source: Literal["llm", "fallback"] = Field(
        ...,
        description="Whether the narrative was produced by the LLM or local fallback logic",
    )
    provider: str | None = Field(
        default=None, description="Provider used for narrative generation"
    )
    model: str | None = Field(
        default=None, description="Model used for narrative generation"
    )
    local_mode: bool | None = Field(
        default=None, description="Whether local-only mode was active for the narrative"
    )
    skills_applied: list[str] = Field(
        default_factory=list,
        description="Resolved skill names included in the narrative prompt",
    )


class AdvisorySummaryData(BaseModel):
    advisory_only: bool = Field(
        ..., description="Whether the output is advisory rather than blocking"
    )
    should_block: bool = Field(
        ..., description="Whether DeployWhisper itself should block deployment"
    )
    requires_attention: bool = Field(
        ..., description="Whether humans should provide additional review"
    )
    severity: RiskSeverity = Field(..., description="Shared risk severity")
    recommendation: DeployRecommendation = Field(
        ..., description="Shared deploy recommendation"
    )
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


class ShareSummaryData(BaseModel):
    advisory_only: bool = Field(
        ..., description="Whether the shared summary is advisory rather than blocking"
    )
    should_block: bool = Field(
        ..., description="Whether DeployWhisper itself should block deployment"
    )
    severity: RiskSeverity = Field(
        ..., description="Risk severity for PR or approval-thread sharing"
    )
    recommendation: DeployRecommendation = Field(
        ..., description="Recommendation for PR or approval-thread sharing"
    )
    headline: str = Field(..., description="Top narrative line for sharing")
    blast_radius_summary: str = Field(..., description="Concise blast-radius summary")
    rollback_summary: str = Field(..., description="Concise rollback summary")
    uncertainty_summary: str = Field(
        ..., description="Concise review and uncertainty summary"
    )
    markdown: str = Field(..., description="Markdown-ready advisory summary")
    plain_text: str = Field(..., description="Plain-text advisory summary")
    json_payload: "ShareSummaryJsonPayloadData" = Field(
        ..., description="Machine-friendly share-summary payload"
    )


class ShareSummaryFindingData(BaseModel):
    title: str = Field(..., description="Short finding title for sharing")
    severity: RiskSeverity = Field(..., description="Finding severity")
    evidence_count: int = Field(..., description="Evidence count for the finding")
    confidence: float = Field(..., description="Finding confidence score")


class ShareSummaryContextData(BaseModel):
    score: float = Field(..., description="Context completeness score")
    label: str = Field(..., description="Context completeness label")
    summary: str = Field(..., description="Short context completeness summary")


class ShareSummaryJsonPayloadData(BaseModel):
    version: str = Field(..., description="Share-summary payload version")
    report_schema_version: str = Field(
        ...,
        description="Report schema version used by the source persisted report",
    )
    report_id: int | None = Field(default=None, description="Persisted report ID")
    report_link: str | None = Field(default=None, description="Deep link to the report")
    rollback_link: str | None = Field(
        default=None, description="Deep link to the rollback view"
    )
    verdict_banner: str = Field(..., description="Verdict banner")
    evidence_law_status: EvidenceLawStatus = Field(
        ..., description="Evidence Law verification status for severe claims"
    )
    evidence_law_detail: str = Field(
        ..., description="Human-readable Evidence Law verification detail"
    )
    headline: str = Field(..., description="Top summary line")
    top_findings: list[ShareSummaryFindingData] = Field(
        default_factory=list, description="Top findings to surface"
    )
    evidence_count: int = Field(..., description="Total evidence-item count")
    blast_radius_summary: str = Field(..., description="Concise blast-radius summary")
    rollback_summary: str = Field(..., description="Concise rollback summary")
    context_completeness: ShareSummaryContextData = Field(
        ..., description="Context completeness summary"
    )
    advisory_summary: str = Field(..., description="Advisory-only review summary")


class AnalysisRunData(BaseModel):
    intake: PendingAnalysis
    parse_batch: ParseBatchData
    assessment: AssessmentData
    findings: list[FindingData] = Field(default_factory=list)
    evidence_items: list[EvidenceItemData] = Field(default_factory=list)
    blast_radius: BlastRadiusData
    rollback_plan: RollbackPlanData
    incident_matches: list[IncidentMatchData] = Field(default_factory=list)
    narrative: NarrativeData
    advisory: AdvisorySummaryData
    share_summary: ShareSummaryData
    persisted_report: PersistedReportData


class FeedbackEventData(BaseModel):
    id: int = Field(..., description="Stable feedback event identifier")
    project_id: int = Field(..., description="Owning project identifier")
    workspace_id: int | None = Field(
        default=None, description="Optional workspace identifier"
    )
    analysis_id: int = Field(..., description="Analysis report identifier")
    finding_id: str | None = Field(
        default=None, description="Finding identifier when feedback is finding-scoped"
    )
    reviewer_role: str | None = Field(default=None, description="Reviewer role label")
    useful: bool | None = Field(
        default=None, description="Whether the finding was useful"
    )
    correctness_rating: int | None = Field(
        default=None, description="Legacy correctness rating"
    )
    false_positive_flag: bool = Field(
        default=False, description="Whether the finding was marked false positive"
    )
    false_positive_reason: str | None = Field(
        default=None, description="Optional false-positive reason"
    )
    false_negative_note: str | None = Field(
        default=None, description="Optional missed-finding note"
    )
    outcome_label: str | None = Field(
        default=None, description="Normalized feedback outcome label"
    )
    created_at: str = Field(..., description="Feedback creation timestamp")


class FeedbackStateData(BaseModel):
    finding_feedback: dict[str, FeedbackEventData] = Field(
        default_factory=dict,
        description="Latest persisted feedback event for each finding",
    )
    false_negative_by_finding: dict[str, FeedbackEventData] = Field(
        default_factory=dict,
        description="Latest missed-finding note keyed by finding id",
    )
    false_negative_notes: list[FeedbackEventData] = Field(
        default_factory=list, description="Latest missed-finding feedback notes"
    )


class AnalysisShareConfigData(BaseModel):
    share_url: str = Field(..., description="Public share URL for the report.")
    password_protected: bool = Field(
        ..., description="Whether the shared report currently requires a password."
    )
    redact_filenames: bool = Field(
        ..., description="Whether file names are redacted in the shared view."
    )


class AnalysisDetailData(AnalysisReportData):
    share_summary: ShareSummaryData = Field(
        ..., description="Existing share-summary markdown and machine payload"
    )
    share: AnalysisShareConfigData | None = Field(
        default=None, description="Public share configuration when available"
    )
    feedback_state: FeedbackStateData = Field(
        default_factory=FeedbackStateData,
        description="Latest reviewer feedback state for report findings",
    )
    comparison: dict[str, Any] | None = Field(
        default=None,
        description="Optional previous-report comparison for shared report views",
    )


class AnalysisListResponse(BaseModel):
    data: list[AnalysisReportData]
    meta: CountMetaPayload


class AnalysisDetailResponse(BaseModel):
    data: AnalysisDetailData
    meta: ResourceMetaPayload


class AnalysisRunResponse(BaseModel):
    data: AnalysisRunData
    meta: AnalysisRunMetaPayload


class AnalysisShareConfigRequest(BaseModel):
    password: str | None = Field(
        default=None,
        description="Optional password required before the shared report can be viewed.",
    )
    redact_filenames: bool = Field(
        default=False,
        description="Whether shared rendering should replace file names with generic labels.",
    )


class AnalysisShareConfigResponse(BaseModel):
    data: AnalysisShareConfigData
    meta: ResourceMetaPayload


class FindingFeedbackRequest(BaseModel):
    outcome: Literal["useful", "noisy", "false_positive"] = Field(
        ..., description="Reviewer feedback outcome for the finding"
    )
    false_positive_reason: str | None = Field(
        default=None,
        description="Optional reason when outcome is false_positive",
    )
    reviewer_role: str = Field(default="reviewer", description="Reviewer role label")


class FindingFeedbackResponse(BaseModel):
    data: FeedbackEventData
    meta: ResourceMetaPayload


class SharedReportUnlockRequest(BaseModel):
    password: str = Field(..., description="Password for a protected shared report")


class SharedReportAccessResponse(BaseModel):
    data: AnalysisDetailData
    meta: ResourceMetaPayload


SkillRegistrySource = Literal["built-in", "custom-override", "custom-new"]
SkillHarnessStatus = Literal["passing", "failing", "missing"]


class SkillTestResultsSummaryData(BaseModel):
    total_scenarios: int = Field(..., description="Total number of harness scenarios.")
    passed_scenarios: int = Field(..., description="Number of passing scenarios.")
    failed_scenarios: int = Field(..., description="Number of failing scenarios.")
    pass_rate: float = Field(..., description="Fraction of scenarios that passed.")
    status: SkillHarnessStatus = Field(
        ..., description="High-level harness status for the skill."
    )
    display_text: str = Field(..., description="Human-readable pass/fail summary.")
    generated_at: str = Field(..., description="UTC timestamp for this harness run.")


class SkillTestScenarioResultData(BaseModel):
    name: str = Field(..., description="Stable scenario name.")
    description: str | None = Field(
        default=None, description="Human-readable description of the scenario."
    )
    passed: bool = Field(..., description="Whether the scenario passed.")
    failures: list[str] = Field(
        default_factory=list,
        description="Failure reasons when the scenario did not pass.",
    )


class SkillTestResultsData(BaseModel):
    skill_id: str = Field(..., description="Stable skill identifier.")
    version: str = Field(..., description="Skill version under test.")
    summary: SkillTestResultsSummaryData
    scenarios: list[SkillTestScenarioResultData] = Field(default_factory=list)


class SkillRegistryData(BaseModel):
    id: str = Field(..., description="Stable skill identifier")
    name: str = Field(..., description="Human-readable skill name")
    version: str = Field(..., description="Current effective version")
    source: SkillRegistrySource = Field(
        ..., description="Where the skill definition currently resolves from"
    )
    author: str = Field(..., description="Skill author or owner label")
    maintainer: str = Field(..., description="Current maintainer label")
    is_official: bool = Field(
        default=False,
        description="Whether the skill is officially maintained by DeployWhisper.",
    )
    is_featured: bool = Field(
        default=False,
        description="Whether the skill is a curated featured community entry.",
    )
    license: str | None = Field(default=None, description="Declared skill license")
    description: str = Field(..., description="Skill summary")
    tool: str = Field(..., description="Primary tool family for the skill")
    tags: list[str] = Field(default_factory=list, description="Searchable skill tags")
    token_budget: int | None = Field(
        default=None, description="Suggested token budget for the skill"
    )
    test_suite_path: str | None = Field(
        default=None,
        description="Repository path to the skill validation suite, when declared.",
    )
    test_results: SkillTestResultsSummaryData | None = Field(
        default=None,
        description="Latest deterministic harness summary for the skill.",
    )
    triggers: list[str] = Field(
        default_factory=list, description="Filename or extension triggers"
    )
    trigger_content_patterns: list[str] = Field(
        default_factory=list, description="Content markers used for matching"
    )
    install_count: int = Field(
        default=0, description="Current install count from the analytics snapshot"
    )
    active_issue_count: int = Field(
        default=0, description="Current open issue count from the analytics snapshot"
    )
    analytics_updated_at: str = Field(
        ..., description="When the analytics snapshot was last refreshed"
    )
    download_count: int = Field(
        default=0,
        description="Compatibility popularity metric derived from install counts.",
    )
    star_count: int = Field(
        default=0, description="Current star count from the analytics snapshot"
    )
    updated_at: str = Field(..., description="Last local update timestamp")
    available_versions: int = Field(
        ..., description="Number of versions discoverable for this skill id"
    )
    install_command: str = Field(
        ..., description="CLI command for installing this skill"
    )


class SkillRegistryVersionData(SkillRegistryData):
    is_current: bool = Field(
        ..., description="Whether this version is the current effective version"
    )


class SkillRegistryContentData(BaseModel):
    id: str = Field(..., description="Stable skill identifier")
    version: str = Field(..., description="Registry version for the returned skill")
    content: str = Field(
        ...,
        description="Raw markdown payload including frontmatter for installation.",
    )
    sha256: str = Field(..., description="SHA-256 checksum for the payload")


class SkillRegistryListMetaPayload(MetaPayload):
    count: int = Field(..., description="Count of returned items")
    total_count: int = Field(..., description="Total number of matching skills")
    page: int = Field(..., description="Current results page")
    page_size: int = Field(..., description="Current results page size")
    filters: dict[str, str] = Field(
        default_factory=dict,
        description="Filters applied to the current registry query",
    )


class SkillRegistryResourceMetaPayload(MetaPayload):
    id: str = Field(..., description="Stable skill identifier")


class SkillRegistryListResponse(BaseModel):
    data: list[SkillRegistryData]
    meta: SkillRegistryListMetaPayload


class SkillRegistryDetailResponse(BaseModel):
    data: SkillRegistryData
    meta: SkillRegistryResourceMetaPayload


class SkillRegistryVersionsResponse(BaseModel):
    data: list[SkillRegistryVersionData]
    meta: SkillRegistryResourceMetaPayload


class SkillRegistryContentResponse(BaseModel):
    data: SkillRegistryContentData
    meta: SkillRegistryResourceMetaPayload


class SkillRegistryTestResultsResponse(BaseModel):
    data: SkillTestResultsData
    meta: SkillRegistryResourceMetaPayload


PersistedReportData.model_rebuild()


def _copy_model(model: BaseModel, schema_type: type[BaseModel]) -> BaseModel:
    return schema_type.model_validate(model.model_dump())


def _copy_payload(payload: Any, schema_type: type[BaseModel]) -> BaseModel:
    return schema_type.model_validate(payload)


def _copy_payload_list(items: Any, schema_type: type[BaseModel]) -> list[BaseModel]:
    if not isinstance(items, list):
        return []
    return [_copy_payload(item, schema_type) for item in items]


def _known_model_fields_payload(payload: Any, schema_type: type[BaseModel]) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {
        key: value for key, value in payload.items() if key in schema_type.model_fields
    }


def _degraded_context_payload() -> dict[str, Any]:
    return {
        "context_score": 0.0,
        "confidence_level": "low",
        "insufficient_context": True,
        "uncertainty": "Context completeness payload was unavailable or unreadable.",
        "context_todos": [
            "Regenerate this report to restore context completeness metadata."
        ],
    }


def _context_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    try:
        return _validate_non_empty_strings(value)
    except ValueError:
        return []


def _salvaged_context_string_list(value: Any) -> tuple[list[str], bool]:
    if not isinstance(value, list):
        return [], value is not None
    cleaned: list[str] = []
    seen: set[str] = set()
    dropped = False
    for item in value:
        if not isinstance(item, str):
            dropped = True
            continue
        text = item.strip()
        if not text:
            dropped = True
            continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned, dropped


def _mark_context_ownership_payload_partial(payload: dict[str, Any]) -> dict[str, Any]:
    marked = dict(payload)
    try:
        marked["context_score"] = min(float(marked.get("context_score", 1.0)), 0.69)
    except (TypeError, ValueError):
        marked["context_score"] = 0.69
    marked["confidence_level"] = "low"
    marked["insufficient_context"] = True
    marked["partial_context"] = True
    warning = "Ownership context payload was partially unreadable."
    uncertainty = str(marked.get("uncertainty") or "").strip()
    marked["uncertainty"] = f"{uncertainty} {warning}".strip()
    todos, _ = _salvaged_context_string_list(marked.get("context_todos"))
    ownership_todo = "Regenerate this report to restore ownership context metadata."
    if ownership_todo not in todos:
        todos.append(ownership_todo)
    marked["context_todos"] = todos
    return marked


def _owner_signal_escalation_hint(payload: dict[str, Any]) -> str | None:
    scope = str(payload.get("scope") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    owners = _context_string_list(payload.get("owners"))
    if scope not in {"file", "service"} or not subject or not owners:
        return None
    owner_text = ", ".join(owners)
    if scope == "service":
        return f"Escalate service review for {subject} to {owner_text}."
    return f"Escalate file review for {subject} to {owner_text}."


def _salvaged_ownership_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    salvaged = dict(payload)
    dropped_ownership_data = False
    raw_owner_signals = salvaged.get("owner_signals")
    if isinstance(raw_owner_signals, list):
        owner_signals: list[dict[str, Any]] = []
        for item in raw_owner_signals:
            filtered = _known_model_fields_payload(item, OwnerSignalData)
            if not filtered:
                continue
            if "owners" in filtered:
                cleaned_owners, dropped_owners = _salvaged_context_string_list(
                    filtered.get("owners")
                )
                if dropped_owners:
                    dropped_ownership_data = True
                if cleaned_owners:
                    filtered["owners"] = cleaned_owners
            if not filtered.get("escalation_hint"):
                hint = _owner_signal_escalation_hint(filtered)
                if hint is not None:
                    filtered["escalation_hint"] = hint
            try:
                owner_signals.append(
                    OwnerSignalData.model_validate(filtered).model_dump(mode="json")
                )
            except ValidationError:
                continue
        dropped_ownership_data = dropped_ownership_data or len(owner_signals) != len(
            raw_owner_signals
        )
        salvaged["owner_signals"] = owner_signals
    else:
        dropped_ownership_data = "owner_signals" in salvaged
        salvaged.pop("owner_signals", None)
    for field_name in ("escalation_hints", "ownership_unmapped_subjects"):
        if field_name in salvaged:
            values = salvaged[field_name]
            salvaged_values, dropped_values = _salvaged_context_string_list(values)
            if dropped_values:
                dropped_ownership_data = True
            salvaged[field_name] = salvaged_values
    if dropped_ownership_data:
        return _mark_context_ownership_payload_partial(salvaged)
    return salvaged


def _coerce_optional_context_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_context_float(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric_value):
        return default
    return numeric_value


def _coerce_context_int(value: Any, default: int) -> int:
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return default
    if numeric_value < 0:
        return default
    return numeric_value


def _coerce_optional_context_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return None
    if numeric_value < 0:
        return None
    return numeric_value


def _coerce_context_unit_float(
    value: Any,
    *,
    default: float,
    invalid_default: float = 0.0,
) -> float:
    if value is None:
        return default
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return invalid_default
    if not math.isfinite(numeric_value):
        return invalid_default
    return min(max(numeric_value, 0.0), 1.0)


def _salvaged_context_completeness_payload(payload: dict[str, Any]) -> dict[str, Any]:
    salvaged = _salvaged_ownership_context_payload(payload)
    normalized = dict(salvaged)
    normalized["topology_freshness_days"] = _coerce_optional_context_int(
        normalized.get("topology_freshness_days")
    )
    for field_name in (
        "topology_last_imported_at",
        "incident_index_version",
        "incident_index_last_indexed_at",
        "incident_index_freshness_status",
        "uncertainty",
    ):
        normalized[field_name] = _coerce_optional_context_string(
            normalized.get(field_name)
        )
    normalized["incident_index_size"] = _coerce_context_int(
        normalized.get("incident_index_size"),
        0,
    )
    normalized["evidence_success_rate"] = _coerce_context_unit_float(
        normalized.get("evidence_success_rate"),
        default=1.0,
    )
    normalized["parser_success_rate"] = _coerce_context_unit_float(
        normalized.get("parser_success_rate"),
        default=1.0,
    )
    parser_success_by_tool = normalized.get("parser_success_by_tool")
    normalized["parser_success_by_tool"] = (
        {
            str(tool).strip(): _coerce_context_unit_float(rate, default=1.0)
            for tool, rate in parser_success_by_tool.items()
            if str(tool).strip()
        }
        if isinstance(parser_success_by_tool, dict)
        else {}
    )
    normalized["context_score"] = _coerce_context_unit_float(
        normalized.get("context_score"),
        default=1.0,
        invalid_default=1.0,
    )
    if normalized.get("confidence_level") not in {"high", "medium", "low"}:
        normalized["confidence_level"] = "low"
    normalized["context_todos"] = _context_string_list(normalized.get("context_todos"))
    if not isinstance(normalized.get("insufficient_context"), bool):
        normalized["insufficient_context"] = True
    if not isinstance(normalized.get("partial_context"), bool):
        normalized["partial_context"] = False
    return _mark_context_ownership_payload_partial(normalized)


def _known_context_fields_payload(
    payload: Any,
    schema_type: type[BaseModel],
) -> dict:
    if not isinstance(payload, dict):
        return _degraded_context_payload()
    known_payload = _known_model_fields_payload(payload, schema_type)
    if not known_payload:
        return _degraded_context_payload()
    try:
        return schema_type.model_validate(known_payload).model_dump(mode="json")
    except ValidationError:
        if schema_type is ContextCompletenessData:
            ownership_fields = {
                "owner_signals",
                "escalation_hints",
                "ownership_unmapped_subjects",
            }
            if ownership_fields.intersection(known_payload):
                try:
                    return schema_type.model_validate(
                        _salvaged_context_completeness_payload(known_payload)
                    ).model_dump(mode="json")
                except ValidationError:
                    pass
        return _degraded_context_payload()


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
    narrative = result.narrative
    persisted_report = result.persisted_report
    raw_context_payload = persisted_report.get("context_completeness")
    persisted_context = ContextCompletenessData.model_validate(
        _known_context_fields_payload(
            raw_context_payload,
            ContextCompletenessData,
        )
    )
    persisted_report_payload = dict(persisted_report)
    persisted_report_payload["context_completeness"] = persisted_context.model_dump(
        mode="json"
    )

    return AnalysisRunData(
        intake=PendingAnalysis.model_validate(intake.model_dump()),
        parse_batch=ParseBatchData(
            files=[
                ParsedArtifactData(
                    file_name=file_result.file_name,
                    tool=file_result.tool,
                    status=file_result.status,
                    changes=[
                        _copy_model(change, ChangeData)
                        for change in file_result.changes
                    ],
                    issue=_copy_model(file_result.issue, ParseIssueData)
                    if file_result.issue is not None
                    else None,
                )
                for file_result in parse_batch.files
            ]
        ),
        assessment=AssessmentData(
            score=int(persisted_report.get("risk_score", assessment.score)),
            severity=persisted_report.get("severity", assessment.severity),
            recommendation=persisted_report.get(
                "recommendation", assessment.recommendation
            ),
            confidence=float(persisted_report.get("confidence", assessment.confidence)),
            top_risk=str(persisted_report.get("top_risk", assessment.top_risk)),
            top_risk_contributors=list(
                persisted_report.get(
                    "top_risk_contributors", assessment.top_risk_contributors
                )
                or []
            ),
            context_completeness=persisted_context,
            contributors=_copy_payload_list(
                persisted_report.get("contributors"), RiskContributorData
            ),
            confidence_ledger=ConfidenceLedgerData.model_validate(
                persisted_report.get("confidence_ledger", {})
            ),
            interaction_risks=[
                _copy_model(interaction_risk, InteractionRiskData)
                for interaction_risk in assessment.interaction_risks
            ],
            partial_context=persisted_context.partial_context,
            warnings=list(persisted_report.get("warnings") or []),
            source=persisted_report.get("assessment_source") or assessment.source,
        ),
        findings=_copy_payload_list(persisted_report.get("findings"), FindingData),
        evidence_items=_copy_payload_list(
            persisted_report.get("evidence_items"), EvidenceItemData
        ),
        blast_radius=BlastRadiusData.model_validate(
            persisted_report.get("blast_radius")
            or {
                "affected": [
                    _copy_model(node, ImpactNodeData).model_dump()
                    for node in blast_radius.affected
                ],
                "direct_count": blast_radius.direct_count,
                "transitive_count": blast_radius.transitive_count,
                "warning": blast_radius.warning,
                "unmatched_resources": list(blast_radius.unmatched_resources),
                "context_source": dict(blast_radius.context_source),
                "freshness": dict(blast_radius.freshness),
                "context_state": blast_radius.context_state,
                "context_limitations": list(blast_radius.context_limitations),
            }
        ),
        rollback_plan=RollbackPlanData.model_validate(
            persisted_report.get("rollback_plan")
            or {
                "steps": [
                    _copy_model(step, RollbackStepData).model_dump()
                    for step in rollback_plan.steps
                ],
                "complexity": rollback_plan.complexity,
                "complexity_score": rollback_plan.complexity_score,
                "complexity_explanation": rollback_plan.complexity_explanation,
                "warning": rollback_plan.warning,
            }
        ),
        incident_matches=_copy_payload_list(
            persisted_report.get("incident_matches"), IncidentMatchData
        ),
        narrative=_copy_model(narrative, NarrativeData),
        advisory=_copy_model(advisory, AdvisorySummaryData),
        share_summary=_copy_model(share_summary, ShareSummaryData),
        persisted_report=PersistedReportData.model_validate(persisted_report_payload),
    )
