"""Apply existing uncertainty policy to independently collected live context."""

from __future__ import annotations

from datetime import datetime, timezone

from analysis.risk_scorer import (
    RiskAssessment,
    SEVERITY_ORDER,
    apply_context_uncertainty,
)
from cloud.collection import PlanGroundingOutcome

GROUNDING_WARNING = "Live environment grounding is incomplete; verify the affected resources before deployment."
GROUNDING_TODO = (
    "Review the grounding collection diagnostics and retry when context is available."
)


def apply_grounding_degradation(
    assessment: RiskAssessment,
    outcome: PlanGroundingOutcome | None,
    *,
    project_id: int | None,
    now: datetime | None = None,
) -> RiskAssessment:
    """Add source metadata without using missing context to improve a verdict.

    Collection authority stays in the cloud service. This hook consumes its
    typed outcome and cannot construct a connector or issue provider calls.
    """
    if outcome is None:
        return assessment
    try:
        observed = PlanGroundingOutcome.model_validate(outcome.model_dump())
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_grounding_outcome") from None
    if type(project_id) is not int or observed.project_id != project_id:
        raise ValueError("grounding_scope_mismatch")
    if observed.state == "disabled":
        return assessment

    # Reuse the existing freshness vocabulary and calculation, including stale
    # and future windows; a cached 'current' label cannot reset observation age.
    from services.cloud_context_service import snapshot_context

    source = snapshot_context(observed.snapshot, now=now or datetime.now(timezone.utc))
    if observed.context is not None:
        if observed.context.source_type != "live_state":
            raise ValueError("invalid_grounding_context")
        if (
            observed.context.source_id == source.source_id
            and observed.context.freshness_status != "current"
            and source.freshness_status == "current"
        ):
            source = observed.context.model_copy(deep=True)
    # This slice adds operational collection diagnostics, not admitted factual
    # report evidence. Do not persist a resolvable snapshot reference that lacks
    # an evidence-owned retention hold; factual admission belongs to its service.
    source = source.model_copy(
        update={
            "source_id": "live_state:collection",
            "source_ref": None,
            "limitations": list(
                dict.fromkeys([*source.limitations, "collection_metadata_only"])
            ),
        },
        deep=True,
    )
    degraded = (
        observed.state != "snapshot"
        or observed.snapshot is None
        or observed.snapshot.partial
        or source.freshness_status != "current"
        or observed.budget is None
        or observed.budget.cancelled
    )
    result = assessment.model_copy(deep=True)
    context = result.context_completeness
    context.context_sources = [
        item for item in context.context_sources if item.source_id != source.source_id
    ] + [source]
    if not degraded:
        return result
    context.insufficient_context = True
    if not context.uncertainty:
        context.uncertainty = "Live environment grounding is unavailable or incomplete; it cannot support a more confident verdict."
    if GROUNDING_TODO not in context.context_todos:
        context.context_todos.append(GROUNDING_TODO)
    result.partial_context = True
    if GROUNDING_WARNING not in result.warnings:
        result.warnings.append(GROUNDING_WARNING)
    result = apply_context_uncertainty(result)
    # The shared hook rounds confidence. Preserve the stronger explicit floor
    # even for a caller's non-rounded baseline such as 0.126.
    result.confidence = min(assessment.confidence, result.confidence)
    if SEVERITY_ORDER[result.severity] < SEVERITY_ORDER[assessment.severity]:
        result.severity = assessment.severity
    result.score = max(assessment.score, result.score)
    return result
