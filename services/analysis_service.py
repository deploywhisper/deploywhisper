"""Analysis workflow orchestration."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from pydantic import BaseModel, Field

from analysis.blast_radius import BlastRadiusResult, compute_blast_radius
from analysis.incident_matcher import (
    IncidentMatch,
    find_incident_matches,
)
from analysis.risk_engine import score_evidence
from analysis.risk_scorer import (
    RiskAssessment,
    apply_context_uncertainty,
    score_changes,
)
from analysis.rollback_planner import RollbackPlan, generate_rollback_plan
from evidence.extractor import extract_batch_evidence
from evidence.mappers import build_findings
from evidence.models import ContextCompleteness, EvidenceItem, Finding
from llm.narrator import NarrativeResult, generate_narrative
from llm.providers import generate_completion_with_settings
from parsers.base import ParseBatchResult, UnifiedChange, is_non_mutating_action
from services.intake_service import build_parse_batch
from services.project_service import (
    ProjectResolutionError,
    resolve_project_reference,
    resolve_workspace_reference,
)
from services.report_service import (
    REPORT_SCHEMA_VERSION,
    build_share_report_link,
    persist_analysis_report,
    readable_report_schema_version,
)
from services.settings_service import resolve_provider_runtime
from services.submission_manifest import SubmissionManifest, build_submission_manifest
from services.incident_service import get_incident_index_snapshot
from services.confidence_ledger import EvidenceLawStatus, evidence_law_status
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
    change_metadata_by_id: dict[str, dict[str, Any]] | None = None,
    supplemental_changes: list[UnifiedChange] | None = None,
    completion_client=None,
    allow_llm_assistance: bool = True,
) -> RiskAssessment:
    """Return a reusable unified risk assessment from evidence inputs."""
    return score_evidence(
        evidence_items,
        partial_context=partial_context,
        topology=topology,
        raw_files=raw_files,
        change_metadata_by_id=change_metadata_by_id,
        supplemental_changes=supplemental_changes,
        completion_client=completion_client,
        allow_llm_assistance=allow_llm_assistance,
    )


def _change_metadata_by_id(batch: ParseBatchResult) -> dict[str, dict[str, Any]]:
    metadata_by_id: dict[str, dict[str, Any]] = {}
    for file_result in batch.files:
        if file_result.status != "parsed":
            continue
        for change in file_result.changes:
            if change.metadata:
                metadata_by_id[change.change_id] = dict(change.metadata)
    return metadata_by_id


def _all_changes_are_non_mutating_terraform(changes: list[UnifiedChange]) -> bool:
    return bool(changes) and all(
        change.tool == "terraform" and is_non_mutating_action(change.action)
        for change in changes
    )


def _supplemental_non_mutating_terraform_changes(
    changes: list[UnifiedChange], evidence_items: list[EvidenceItem]
) -> list[UnifiedChange]:
    evidence_change_ids = {
        change_id
        for item in evidence_items
        for change_id in item.related_change_ids
        if change_id
    }
    return [
        change
        for change in changes
        if change.tool == "terraform"
        and is_non_mutating_action(change.action)
        and change.change_id not in evidence_change_ids
    ]


def evaluate_parse_batch(
    batch: ParseBatchResult,
    *,
    partial_context: bool | None = None,
    evidence_items: list[EvidenceItem] | None = None,
    topology: dict | None = None,
    raw_files: dict[str, bytes | None] | None = None,
    completion_client=None,
    allow_llm_assistance: bool = True,
) -> RiskAssessment:
    """Compatibility wrapper that scores extracted evidence for a parse batch."""
    scored_evidence_items = (
        list(evidence_items)
        if evidence_items is not None
        else extract_batch_evidence(batch)
    )
    changes = _collect_changes(batch)
    partial_context_value = (
        batch.has_partial_context if partial_context is None else partial_context
    )
    if not scored_evidence_items and _all_changes_are_non_mutating_terraform(changes):
        return score_changes(
            changes,
            partial_context=partial_context_value,
            topology=topology,
            raw_files=raw_files,
            completion_client=completion_client,
            allow_llm_assistance=allow_llm_assistance,
        )
    if not scored_evidence_items:
        scored_evidence_items = extract_batch_evidence(batch)
    return evaluate_evidence(
        scored_evidence_items,
        partial_context=partial_context_value,
        topology=topology,
        raw_files=raw_files,
        change_metadata_by_id=_change_metadata_by_id(batch),
        supplemental_changes=_supplemental_non_mutating_terraform_changes(
            changes, scored_evidence_items
        ),
        completion_client=completion_client,
        allow_llm_assistance=allow_llm_assistance,
    )


class AnalysisArtifacts(BaseModel):
    parse_batch: ParseBatchResult = Field(..., description="Per-file parse results")
    submission_manifest: SubmissionManifest = Field(
        default_factory=SubmissionManifest,
        description="Submission coverage and artifact outcome manifest",
    )
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


class AnalysisPersistenceError(RuntimeError):
    """Raised when report persistence fails after deterministic analysis completed."""

    code = "report_persistence_failed"
    public_reason = (
        "Report persistence did not complete. Retry the analysis; if it repeats, "
        "review local application logs and persistence configuration."
    )

    def __init__(self, reason: str) -> None:
        super().__init__(
            "Report persistence failed; final analysis success was not returned."
        )
        self.reason = reason


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
    json_payload: "ShareSummaryJsonPayload" = Field(
        ..., description="Machine-friendly share-summary payload"
    )


class ShareSummaryFinding(BaseModel):
    title: str = Field(..., description="Short finding title for sharing")
    severity: str = Field(..., description="Finding severity")
    evidence_count: int = Field(..., description="Evidence items linked to the finding")
    confidence: float = Field(..., description="Finding confidence score")


class ShareSummaryContext(BaseModel):
    score: float = Field(..., description="Context completeness score")
    label: str = Field(..., description="Context completeness badge label")
    summary: str = Field(..., description="Short context completeness summary")


class ShareSummaryJsonPayload(BaseModel):
    version: str = Field(default="v1", description="Share-summary payload version")
    report_schema_version: str = Field(
        default=REPORT_SCHEMA_VERSION,
        description="Report schema version used by the source persisted report",
    )
    report_id: int | None = Field(default=None, description="Persisted report ID")
    report_link: str | None = Field(default=None, description="Deep link to the report")
    rollback_link: str | None = Field(
        default=None, description="Deep link to the report rollback view"
    )
    verdict_banner: str = Field(..., description="Verdict banner for PR comments")
    evidence_law_status: EvidenceLawStatus = Field(
        ..., description="Evidence Law verification status for severe claims"
    )
    evidence_law_detail: str = Field(
        ..., description="Human-readable Evidence Law verification detail"
    )
    headline: str = Field(..., description="Top summary line")
    top_findings: list[ShareSummaryFinding] = Field(
        default_factory=list, description="Top findings to surface"
    )
    evidence_count: int = Field(..., description="Total evidence-item count")
    blast_radius_summary: str = Field(..., description="Concise blast-radius summary")
    rollback_summary: str = Field(..., description="Concise rollback summary")
    context_completeness: ShareSummaryContext = Field(
        ..., description="Context completeness summary"
    )
    advisory_summary: str = Field(..., description="Advisory-only review summary")


def _collect_changes(parse_batch: ParseBatchResult) -> list[UnifiedChange]:
    changes: list[UnifiedChange] = []
    for file_result in parse_batch.files:
        if file_result.status == "parsed":
            changes.extend(file_result.changes)
    return changes


def _normalize_incident_matches(matches: list[IncidentMatch]) -> list[IncidentMatch]:
    return [
        IncidentMatch.model_validate(match.model_dump())
        if isinstance(match, BaseModel)
        else IncidentMatch.model_validate(match)
        for match in matches
    ]


def _raw_files_for_parse_batch(
    files: list[tuple[str, bytes | None]],
    parse_batch: ParseBatchResult,
) -> dict[str, bytes | None]:
    parsed_names = {
        file_result.file_name
        for file_result in parse_batch.files
        if file_result.status == "parsed"
    }
    return {name: raw_content for name, raw_content in files if name in parsed_names}


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


def _unique_texts(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _context_confidence_level(context_score: float) -> str:
    if context_score >= 0.85:
        return "high"
    if context_score >= 0.7:
        return "medium"
    return "low"


def _context_todos(
    *,
    evidence_success_rate: float,
    topology_freshness_days: int | None,
    topology_warnings: list[str] | None = None,
    incident_index_size: int,
    parser_success_rate: float,
    include_topology_context: bool = True,
    include_incident_context: bool = True,
) -> list[str]:
    todos: list[str] = []
    if include_topology_context:
        if topology_freshness_days is None:
            todos.append(
                "Import or refresh topology context for this project/workspace."
            )
        elif topology_freshness_days > STALE_AFTER_DAYS:
            todos.append("Refresh stale topology context for this project/workspace.")
        if _has_kubernetes_live_state_todo(topology_warnings):
            todos.append(
                "Resolve Kubernetes live-state context TODOs before relying on topology context."
            )
    if include_incident_context and incident_index_size == 0:
        todos.append("Import relevant incident history for this project/workspace.")
    if parser_success_rate < 1.0:
        todos.append("Review parser errors and resubmit supported artifacts.")
    if evidence_success_rate < 1.0:
        todos.append("Review evidence extraction gaps for supported artifacts.")
    return todos


def _context_uncertainty(
    *,
    context_score: float,
    evidence_success_rate: float,
    topology_freshness_days: int | None,
    topology_warnings: list[str] | None = None,
    incident_index_size: int,
    parser_success_rate: float,
    include_topology_context: bool = True,
    include_incident_context: bool = True,
) -> str | None:
    weak_signals: list[str] = []
    if include_topology_context:
        if topology_freshness_days is None:
            weak_signals.append("topology context is unavailable")
        elif topology_freshness_days > STALE_AFTER_DAYS:
            weak_signals.append("topology context is stale")
        if _has_kubernetes_live_state_todo(topology_warnings):
            weak_signals.append("Kubernetes live-state context has unresolved TODOs")
        elif _has_kubernetes_live_state_degradation(topology_warnings):
            weak_signals.append("Kubernetes live-state context is degraded")
    if include_incident_context and incident_index_size == 0:
        weak_signals.append("incident history is unavailable")
    if parser_success_rate < 1.0:
        weak_signals.append("parser coverage is partial")
    if evidence_success_rate < 1.0:
        weak_signals.append("evidence coverage is partial")
    if context_score < 0.7:
        message = (
            "Insufficient context: missing parser coverage, evidence coverage, "
            "or enabled project context prevents a confident low-risk verdict."
        )
        if weak_signals:
            message += " Weak signals: " + "; ".join(weak_signals) + "."
        return message
    if not weak_signals:
        return None
    return "Uncertainty: " + "; ".join(weak_signals) + "."


def _has_kubernetes_live_state_todo(warnings: list[str] | None) -> bool:
    return any(
        "kubernetes live-state context todo" in str(warning).lower()
        for warning in warnings or []
    )


def _has_kubernetes_live_state_degradation(warnings: list[str] | None) -> bool:
    degradation_markers = (
        "kubernetes live-state context todo",
        "kubernetes live-state import partially parsed",
        "kubernetes live-state import did not produce any supported resources",
        "kubernetes live-state import did not produce any non-namespace resources",
    )
    return any(
        any(marker in str(warning).lower() for marker in degradation_markers)
        for warning in warnings or []
    )


def _is_kubernetes_topology_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    import_metadata = metadata.get("import", {})
    if not isinstance(import_metadata, dict):
        return False
    return str(import_metadata.get("source_type") or "").strip() == "kubernetes"


def _has_usable_topology_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    services = payload.get("services", [])
    if not isinstance(services, list):
        return False
    for service in services:
        if not isinstance(service, dict):
            continue
        service_id = str(service.get("id") or "").strip()
        resource_keys = service.get("resource_keys", [])
        resource_key_texts = (
            [
                str(resource_key).strip()
                for resource_key in resource_keys
                if str(resource_key).strip()
            ]
            if isinstance(resource_keys, list)
            else []
        )
        if service_id and not service_id.startswith("Namespace/"):
            return True
        if any(
            resource_key and not resource_key.startswith("Namespace/")
            for resource_key in resource_key_texts
        ):
            return True
    return False


def _evidence_success_rate(
    changes: list[UnifiedChange], evidence_items: list[EvidenceItem]
) -> float:
    material_change_ids = {
        change.change_id
        for change in changes
        if change.change_id and not is_non_mutating_action(change.action)
    }
    if not material_change_ids:
        return 1.0
    covered_change_ids = {
        change_id
        for item in evidence_items
        for change_id in item.related_change_ids
        if change_id in material_change_ids
    }
    return len(covered_change_ids) / len(material_change_ids)


def _parser_success_by_tool(parse_batch: ParseBatchResult) -> dict[str, float]:
    tool_totals: dict[str, int] = {}
    tool_successes: dict[str, int] = {}
    for file_result in parse_batch.files:
        tool_name = file_result.tool.strip() or "unknown"
        tool_totals[tool_name] = tool_totals.get(tool_name, 0) + 1
        if file_result.status == "parsed":
            tool_successes[tool_name] = tool_successes.get(tool_name, 0) + 1
    return {
        tool_name: round(tool_successes.get(tool_name, 0) / total, 2)
        for tool_name, total in sorted(tool_totals.items())
        if total > 0
    }


def _build_context_completeness(
    parse_batch: ParseBatchResult,
    *,
    evidence_items: list[EvidenceItem] | None = None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    include_topology_context: bool = True,
    include_incident_context: bool = True,
) -> ContextCompleteness:
    topology_last_imported_at = None
    topology_warnings: list[str] = []
    topology_payload_is_usable = False
    topology_payload_is_kubernetes = False
    if include_topology_context:
        topology_status = get_topology_status(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
        topology_payload = getattr(topology_status, "payload", None)
        topology_last_imported_at = topology_status.updated_at
        topology_warnings = list(getattr(topology_status, "warnings", []) or [])
        topology_payload_is_usable = _has_usable_topology_payload(topology_payload)
        topology_payload_is_kubernetes = _is_kubernetes_topology_payload(
            topology_payload
        )
        topology_drift = getattr(topology_status, "drift", None)
        topology_drift_warnings = list(getattr(topology_drift, "warnings", []) or [])
        if getattr(
            topology_drift, "status", None
        ) == "unavailable" and _has_kubernetes_live_state_degradation(
            topology_drift_warnings
        ):
            topology_warnings = _unique_texts(
                topology_warnings + topology_drift_warnings
            )
    topology_freshness_days = _topology_freshness_days(topology_last_imported_at)
    if not include_incident_context or (project_id is None and project_key is None):
        incident_index_size = 0
        incident_index_snapshot = {
            "incident_index_version": "incidents:unscoped",
            "incident_index_last_indexed_at": None,
            "incident_index_freshness_status": "empty",
        }
    else:
        try:
            incident_index_snapshot = get_incident_index_snapshot(
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )
        except Exception:
            incident_index_snapshot = {
                "incident_index_size": 0,
                "incident_index_version": "incidents:unknown",
                "incident_index_last_indexed_at": None,
                "incident_index_freshness_status": "stale",
            }
        incident_index_size = int(
            incident_index_snapshot.get("incident_index_size") or 0
        )
    raw_parser_success_rate = parse_batch.parsed_count / max(len(parse_batch.files), 1)
    parser_success_rate = round(raw_parser_success_rate, 2)
    evidence_success_rate = _evidence_success_rate(
        _collect_changes(parse_batch), list(evidence_items or [])
    )
    weighted_scores = [
        (raw_parser_success_rate, 0.35),
        (evidence_success_rate, 0.20),
    ]
    if include_topology_context:
        topology_score = _freshness_score(topology_freshness_days)
        if topology_payload_is_kubernetes and not topology_payload_is_usable:
            topology_score = 0.0
        if _has_kubernetes_live_state_degradation(topology_warnings):
            topology_score = (
                0.0 if not topology_payload_is_usable else min(topology_score, 0.5)
            )
        weighted_scores.append((topology_score, 0.25))
    if include_incident_context:
        weighted_scores.append((_incident_score(incident_index_size), 0.20))
    total_weight = sum(weight for _, weight in weighted_scores) or 1.0
    raw_context_score = min(
        1.0,
        sum(score * weight for score, weight in weighted_scores) / total_weight,
    )
    context_score = round(raw_context_score, 2)
    context_todos = _context_todos(
        evidence_success_rate=evidence_success_rate,
        topology_freshness_days=topology_freshness_days,
        topology_warnings=topology_warnings,
        incident_index_size=incident_index_size,
        parser_success_rate=raw_parser_success_rate,
        include_topology_context=include_topology_context,
        include_incident_context=include_incident_context,
    )
    return ContextCompleteness(
        topology_freshness_days=topology_freshness_days,
        topology_last_imported_at=topology_last_imported_at,
        incident_index_size=incident_index_size,
        incident_index_version=str(
            incident_index_snapshot.get("incident_index_version") or "incidents:empty"
        ),
        incident_index_last_indexed_at=incident_index_snapshot.get(
            "incident_index_last_indexed_at"
        ),
        incident_index_freshness_status=str(
            incident_index_snapshot.get("incident_index_freshness_status") or "empty"
        ),
        parser_success_rate=parser_success_rate,
        evidence_success_rate=round(evidence_success_rate, 2),
        parser_success_by_tool=_parser_success_by_tool(parse_batch),
        context_score=context_score,
        confidence_level=_context_confidence_level(raw_context_score),
        uncertainty=_context_uncertainty(
            context_score=raw_context_score,
            evidence_success_rate=evidence_success_rate,
            topology_freshness_days=topology_freshness_days,
            topology_warnings=topology_warnings,
            incident_index_size=incident_index_size,
            parser_success_rate=raw_parser_success_rate,
            include_topology_context=include_topology_context,
            include_incident_context=include_incident_context,
        ),
        context_todos=context_todos,
        insufficient_context=raw_context_score < 0.7,
    )


def build_context_completeness(
    parse_batch: ParseBatchResult,
    *,
    evidence_items: list[EvidenceItem] | None = None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    include_topology_context: bool = True,
    include_incident_context: bool = True,
) -> ContextCompleteness:
    """Build the shared context-completeness signal for analysis callers."""

    return _build_context_completeness(
        parse_batch,
        evidence_items=evidence_items,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
        include_topology_context=include_topology_context,
        include_incident_context=include_incident_context,
    )


def _skipped_narrative(reason: str, assessment: RiskAssessment) -> NarrativeResult:
    return NarrativeResult(
        available=False,
        opening_sentence="",
        explanation="",
        guidance=[],
        degraded=True,
        warnings=list(assessment.warnings) + [reason],
        failure_notice=reason,
        source="fallback",
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
    context_uncertainty = bool(assessment.context_completeness.uncertainty)
    context_todos = bool(assessment.context_completeness.context_todos)
    if assessment.partial_context:
        uncertainty_flags.append("partial_context")
    if assessment.context_completeness.context_score < 0.7:
        uncertainty_flags.append("low_context_completeness")
    if assessment.context_completeness.insufficient_context:
        uncertainty_flags.append("insufficient_context")
    if context_uncertainty:
        uncertainty_flags.append("context_uncertainty")
    if context_todos:
        uncertainty_flags.append("context_todos")
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
            or assessment.context_completeness.insufficient_context
            or context_uncertainty
            or context_todos
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


def _shorten(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(limit - 1, 0)].rstrip() + "…"


def _report_link(report_id: int | None) -> str | None:
    return build_share_report_link(report_id)


def _truthy_bool_signal(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int | float):
        if not math.isfinite(float(value)):
            return False
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return False


def _mapping_or_empty(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _manifest_item_has_partial_context_signal(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    if _truthy_bool_signal(item.get("partial")):
        return True
    status = str(item.get("status") or "").strip().lower()
    if status in {"failed", "excluded", "sensitive"}:
        return True
    parse_status = str(item.get("parse_status") or "").strip().lower()
    return bool(parse_status and parse_status != "parsed")


def _has_partial_context_signal(report: dict) -> bool:
    if _truthy_bool_signal(report.get("partial_context")):
        return True
    advisory = report.get("advisory")
    if isinstance(advisory, dict) and _truthy_bool_signal(
        advisory.get("partial_context")
    ):
        return True
    manifest = report.get("submission_manifest")
    if isinstance(manifest, dict):
        if _truthy_bool_signal(manifest.get("partial_analysis")):
            return True
        for item in manifest.get("items") or []:
            if _manifest_item_has_partial_context_signal(item):
                return True
    for item in report.get("submission_manifest_fallback") or []:
        if _manifest_item_has_partial_context_signal(item):
            return True
    context = _mapping_or_empty(report.get("context_completeness"))
    if _truthy_bool_signal(context.get("partial_context")):
        return True
    if _truthy_bool_signal(context.get("insufficient_context")):
        return True
    if str(context.get("uncertainty") or "").strip():
        return True
    if _context_todo_items(context.get("context_todos")):
        return True
    try:
        if float(context.get("parser_success_rate", 1.0)) < 1.0:
            return True
    except (TypeError, ValueError):
        pass
    warnings = [str(warning).lower() for warning in (report.get("warnings") or [])]
    return any(
        "partial context" in warning or "failed to parse" in warning
        for warning in warnings
    )


def _has_context_attention_signal(report: dict) -> bool:
    if _has_partial_context_signal(report):
        return True
    context = _mapping_or_empty(report.get("context_completeness"))
    try:
        return float(context.get("evidence_success_rate", 1.0)) < 1.0
    except (TypeError, ValueError):
        return False


def _advisory_requires_attention_signal(report: dict) -> bool | None:
    advisory = report.get("advisory")
    if not isinstance(advisory, dict) or "requires_attention" not in advisory:
        return None
    return _truthy_bool_signal(advisory.get("requires_attention"))


def _warning_requires_attention_signal(warning: object) -> bool:
    normalized = str(warning or "").strip().lower()
    return bool(normalized and not normalized.startswith("narrative"))


def _has_warning_attention_signal(report: dict) -> bool:
    return any(
        _warning_requires_attention_signal(warning)
        for warning in (report.get("warnings") or [])
    )


def _context_summary_from_report(report: dict) -> ShareSummaryContext:
    context = _mapping_or_empty(report.get("context_completeness"))
    context_summary = _context_summary(context)
    if (
        not _has_partial_context_signal(report)
        or context_summary.label == "LIMITED CONTEXT"
    ):
        return context_summary
    uncertainty = str(context.get("uncertainty") or "").strip()
    return ShareSummaryContext(
        score=context_summary.score,
        label="LIMITED CONTEXT",
        summary=(
            f"LIMITED CONTEXT ({context_summary.score:.2f}) - "
            + (uncertainty or "one or more submitted artifacts were not analyzed.")
        ),
    )


def _finding_severity_rank(severity: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(severity, 0)


def _finding_evidence_count(
    finding: dict, evidence_items: list[dict[str, object]]
) -> int:
    finding_id = finding.get("finding_id")
    count = sum(1 for item in evidence_items if item.get("finding_id") == finding_id)
    if count:
        return count
    return len(finding.get("evidence_refs") or [])


def _mapping_items(value: object) -> list[dict]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, dict)]


def _share_finding_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(confidence):
        return 0.0
    return max(0.0, min(confidence, 1.0))


def _context_number(
    context: dict,
    key: str,
    *,
    missing_default: float,
    invalid_default: float = 0.0,
) -> float:
    if key not in context:
        return missing_default
    try:
        value = float(context.get(key))
    except (TypeError, ValueError):
        return invalid_default
    if not math.isfinite(value):
        return invalid_default
    return max(0.0, min(value, 1.0))


def _context_todo_items(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _context_summary(context: dict) -> ShareSummaryContext:
    score = round(_context_number(context, "context_score", missing_default=1.0), 2)
    partial_context = (
        _context_number(context, "parser_success_rate", missing_default=1.0) < 1.0
    )
    partial_evidence = (
        _context_number(context, "evidence_success_rate", missing_default=1.0) < 1.0
    )
    insufficient_context = _truthy_bool_signal(context.get("insufficient_context"))
    uncertainty = str(context.get("uncertainty") or "").strip()
    context_todos = bool(_context_todo_items(context.get("context_todos")))
    label = (
        "LIMITED CONTEXT"
        if (
            score < 0.7
            or partial_context
            or partial_evidence
            or insufficient_context
            or uncertainty
            or context_todos
        )
        else "STRONG CONTEXT"
    )
    if uncertainty:
        summary = f"{label} ({score:.2f}) - {uncertainty}"
    else:
        summary = f"{label} ({score:.2f})" + (
            " - one or more artifacts failed to parse cleanly."
            if partial_context
            else (
                " - evidence coverage is partial."
                if partial_evidence
                else (
                    " - supporting topology or incident history may be stale."
                    if score < 0.7 or insufficient_context
                    else " - supporting topology, evidence, parser, and incident context look healthy."
                )
            )
        )
    return ShareSummaryContext(score=score, label=label, summary=summary)


def _blast_radius_summary(report: dict) -> str:
    blast_radius = dict(report.get("blast_radius") or {})
    affected = list(blast_radius.get("affected") or [])
    affected_labels = ", ".join(
        _shorten(str(node.get("label", "")), 32) for node in affected[:3]
    )
    if not affected_labels:
        affected_labels = "No mapped downstream services"
    if len(affected) > 3:
        affected_labels += ", …"
    summary = (
        f"{int(blast_radius.get('direct_count', 0))} direct / "
        f"{int(blast_radius.get('transitive_count', 0))} transitive"
        f" ({affected_labels})"
    )
    warning = blast_radius.get("warning")
    if warning:
        summary += f" Warning: {_shorten(str(warning), 80)}"
    return summary


def _rollback_summary(report: dict) -> str:
    rollback_plan = dict(report.get("rollback_plan") or {})
    steps = list(rollback_plan.get("steps") or [])
    first_step_title = (
        _shorten(str(steps[0].get("title", "No rollback steps available")), 64)
        if steps
        else "No rollback steps available"
    )
    summary = (
        f"{int(rollback_plan.get('complexity_score', 1))}/5 "
        f"{str(rollback_plan.get('complexity', 'low')).upper()} · "
        f"First step: {first_step_title}"
    )
    warning = rollback_plan.get("warning")
    if warning:
        summary += f" Warning: {_shorten(str(warning), 72)}"
    return summary


def _share_findings(report: dict) -> list[ShareSummaryFinding]:
    evidence_items = _mapping_items(report.get("evidence_items"))
    findings = _mapping_items(report.get("findings"))
    sorted_findings = sorted(
        findings,
        key=lambda item: (
            -_finding_severity_rank(str(item.get("severity", ""))),
            -_share_finding_confidence(item.get("confidence")),
            str(item.get("title", "")),
        ),
    )
    return [
        ShareSummaryFinding(
            title=_shorten(str(finding.get("title", "")), 72),
            severity=str(finding.get("severity", "medium")),
            evidence_count=_finding_evidence_count(finding, evidence_items),
            confidence=round(_share_finding_confidence(finding.get("confidence")), 2),
        )
        for finding in sorted_findings[:3]
    ]


def build_share_summary(
    report: dict, *, evidence_detail_available: bool = True
) -> ShareSummary:
    """Build a markdown + JSON share summary from the persisted report object."""
    severity = str(report.get("severity", "medium"))
    recommendation = str(report.get("recommendation", "caution"))
    narrative_opening = str(report.get("narrative_opening") or "").strip()
    top_risk = str(report.get("top_risk") or "")
    headline = _shorten(
        narrative_opening or f"{recommendation.upper()}: {top_risk}",
        160,
    )
    verdict_banner = f"DeployWhisper {severity.upper()} · {recommendation.upper()}"
    top_findings = _share_findings(report)
    evidence_count = len(_mapping_items(report.get("evidence_items")))
    evidence_status, evidence_detail = evidence_law_status(
        report, evidence_detail_available=evidence_detail_available
    )
    blast_radius_summary = _blast_radius_summary(report)
    rollback_summary = _rollback_summary(report)
    context_summary = _context_summary_from_report(report)
    report_id = int(report["id"]) if report.get("id") is not None else None
    report_link = _report_link(report_id)
    rollback_link = report_link
    partial_context = _has_context_attention_signal(report)
    narrative_available = _truthy_bool_signal(report.get("narrative_available", True))
    narrative_degraded = _truthy_bool_signal(report.get("narrative_degraded"))
    advisory_requires_attention = _advisory_requires_attention_signal(report)
    baseline_requires_attention = (
        advisory_requires_attention
        if advisory_requires_attention is not None
        else (
            recommendation != "go"
            or context_summary.score < 0.7
            or partial_context
            or context_summary.label == "LIMITED CONTEXT"
            or not narrative_available
            or narrative_degraded
            or _has_warning_attention_signal(report)
        )
    )
    requires_attention = baseline_requires_attention or evidence_status in {
        "Needs review",
        "Reconciled",
    }
    uncertainty_summary = (
        "This result requires additional human review before release."
        if requires_attention
        else "Standard approval flow is sufficient."
    )
    json_payload = ShareSummaryJsonPayload(
        report_schema_version=readable_report_schema_version(
            report.get("report_schema_version")
        ),
        report_id=report_id,
        report_link=report_link,
        rollback_link=rollback_link,
        verdict_banner=verdict_banner,
        evidence_law_status=evidence_status,
        evidence_law_detail=evidence_detail,
        headline=headline,
        top_findings=top_findings,
        evidence_count=evidence_count,
        blast_radius_summary=blast_radius_summary,
        rollback_summary=rollback_summary,
        context_completeness=context_summary,
        advisory_summary=uncertainty_summary,
    )

    markdown_lines = [
        f"### {verdict_banner}",
        f"**Summary:** {headline}",
        f"- Findings: {len(top_findings)} shown / {len(report.get('findings') or [])} total · {evidence_count} evidence items",
    ]
    markdown_lines.extend(
        f"  - {finding.severity.upper()}: {finding.title} ({finding.evidence_count} evidence)"
        for finding in json_payload.top_findings
    )
    markdown_lines.extend(
        [
            f"- Blast radius: {blast_radius_summary}",
            (
                f"- Rollback: [View rollback plan]({rollback_link}) · {rollback_summary}"
                if rollback_link
                else f"- Rollback: {rollback_summary}"
            ),
            f"- Evidence Law: {evidence_status} - {evidence_detail}",
            f"- Context: {context_summary.summary}",
            f"- Advisory only: {uncertainty_summary}",
        ]
    )
    markdown = "\n".join(markdown_lines)
    if len(markdown) > 1500:
        finding_lines = [
            f"  - {finding.severity.upper()}: {finding.title} ({finding.evidence_count} evidence)"
            for finding in json_payload.top_findings[:2]
        ]
        markdown = "\n".join(
            [
                f"### {verdict_banner}",
                f"**Summary:** {_shorten(headline, 120)}",
                f"- Findings: {len(report.get('findings') or [])} total · {evidence_count} evidence items",
                *finding_lines,
                f"- Blast radius: {_shorten(blast_radius_summary, 120)}",
                (
                    f"- Rollback: [View rollback plan]({rollback_link})"
                    if rollback_link
                    else f"- Rollback: {_shorten(rollback_summary, 120)}"
                ),
                f"- Evidence Law: {evidence_status} - {_shorten(evidence_detail, 100)}",
                f"- Context: {context_summary.label} ({context_summary.score:.2f})",
                f"- Advisory only: {uncertainty_summary}",
            ]
        )
    plain_text = " ".join(
        [
            verdict_banner + ".",
            f"Summary: {headline}",
            f"Findings: {len(top_findings)} shown / {len(report.get('findings') or [])} total and {evidence_count} evidence items.",
            f"Blast radius: {blast_radius_summary}.",
            f"Rollback: {rollback_summary}.",
            f"Evidence Law: {evidence_status} - {evidence_detail}.",
            (
                f"Rollback link: {rollback_link}."
                if rollback_link
                else "Rollback link unavailable."
            ),
            f"Context: {context_summary.summary}.",
            f"Advisory only: {uncertainty_summary}",
        ]
    )

    return ShareSummary(
        advisory_only=True,
        should_block=False,
        severity=severity,
        recommendation=recommendation,
        headline=headline,
        blast_radius_summary=blast_radius_summary,
        rollback_summary=rollback_summary,
        uncertainty_summary=uncertainty_summary,
        markdown=markdown,
        plain_text=plain_text,
        json_payload=json_payload,
    )


def build_analysis_artifacts(
    files: list[tuple[str, bytes | None]],
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    completion_client=None,
    include_topology_context: bool = True,
    include_incident_context: bool = True,
    include_narrative: bool = True,
    allow_llm_assistance: bool = True,
) -> AnalysisArtifacts:
    """Build all analysis artifacts up to, but not including, persistence."""
    parse_batch = build_parse_batch(files)
    submission_manifest = build_submission_manifest(files, parse_batch=parse_batch)
    partial_context = parse_batch.has_partial_context or (
        submission_manifest.partial_analysis
    )
    analysis_raw_files = _raw_files_for_parse_batch(files, parse_batch)
    evidence_items = extract_batch_evidence(
        parse_batch,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    changes = _collect_changes(parse_batch)
    if include_topology_context:
        topology, topology_warning = load_topology(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    else:
        topology, topology_warning = None, None
    assessment = evaluate_parse_batch(
        parse_batch,
        partial_context=partial_context,
        evidence_items=evidence_items,
        topology=topology,
        raw_files=analysis_raw_files,
        completion_client=completion_client,
        allow_llm_assistance=allow_llm_assistance,
    )
    assessment.context_completeness = _build_context_completeness(
        parse_batch,
        evidence_items=evidence_items,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
        include_topology_context=include_topology_context,
        include_incident_context=include_incident_context,
    )
    assessment = apply_context_uncertainty(assessment)
    findings = build_findings(
        assessment=assessment,
        evidence_items=evidence_items,
        interaction_confidence_overrides=_interaction_confidence_overrides(
            assessment, completion_client=completion_client
        ),
    )
    blast_radius = compute_blast_radius(changes, topology, topology_warning)
    rollback_plan = generate_rollback_plan(changes, partial_context=partial_context)
    incident_matches = _normalize_incident_matches(
        []
        if not include_incident_context or (project_id is None and project_key is None)
        else find_incident_matches(
            changes,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    )
    if include_narrative:
        narrative = generate_narrative(
            assessment.model_copy(deep=True),
            [finding.model_copy(deep=True) for finding in findings],
            completion_client=completion_client,
            raw_files=analysis_raw_files,
        )
    else:
        narrative = _skipped_narrative(
            "Narrative skipped for deterministic benchmark profile.",
            assessment,
        )
    return AnalysisArtifacts(
        parse_batch=parse_batch,
        submission_manifest=submission_manifest,
        evidence_items=evidence_items,
        findings=findings,
        assessment=assessment,
        blast_radius=blast_radius,
        rollback_plan=rollback_plan,
        incident_matches=incident_matches,
        narrative=narrative,
    )


def resolve_analysis_project_scope(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
):
    """Resolve the required analysis project before artifact parsing."""
    raw_project_key = str(project_key) if project_key is not None else None
    cleaned_project_key = (
        raw_project_key.strip() if raw_project_key is not None else None
    )
    if project_id is None and raw_project_key is not None and not cleaned_project_key:
        raise ProjectResolutionError(
            "invalid_project_reference",
            "Project key must contain at least one letter or number.",
        )
    if project_id is None and not cleaned_project_key:
        raise ProjectResolutionError(
            "missing_project_scope",
            (
                "Project scope is required for analysis submission. "
                "Provide a project_key or project_id, select a project in the UI, "
                "or use a workflow integration that derives one."
            ),
        )
    resolved_project = resolve_project_reference(
        project_id=project_id,
        project_key=cleaned_project_key or None,
    )
    resolve_workspace_reference(
        project_id=resolved_project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    return resolved_project


def analyze_uploaded_files(
    files: list[tuple[str, bytes | None]],
    completion_client=None,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    audit_context: dict | None = None,
) -> AnalysisRunResult:
    """Run the shared parse -> assess -> persist pipeline."""
    started_at = perf_counter()
    resolved_project = resolve_analysis_project_scope(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    artifacts = build_analysis_artifacts(
        files,
        project_id=resolved_project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
        completion_client=completion_client,
    )
    analysis_duration_seconds = max(1, round(perf_counter() - started_at))
    try:
        persisted_report = persist_analysis_report(
            artifacts.parse_batch,
            artifacts.assessment,
            artifacts.narrative,
            blast_radius=artifacts.blast_radius,
            rollback_plan=artifacts.rollback_plan,
            incident_matches=artifacts.incident_matches,
            findings=artifacts.findings,
            evidence_items=artifacts.evidence_items,
            artifact_snapshots={name: raw_content for name, raw_content in files},
            submitted_artifacts=list(files),
            project_id=resolved_project.id,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
            audit_context=audit_context,
            analysis_duration_seconds=analysis_duration_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        raise AnalysisPersistenceError(str(exc)) from exc
    return AnalysisRunResult(
        **artifacts.model_dump(), persisted_report=persisted_report
    )
