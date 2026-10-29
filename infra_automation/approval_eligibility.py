"""Pure runtime evidence and exact-lineage gates over already authenticated facts.

These values are scoped service ports, never credentials or collector admission.
Callers derive current facts transactionally and repeat the check before every
side effect. Canonical advisory report fields are observed without mutation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import StrictBool, StrictStr, field_validator

from infra_automation.contracts import (
    AuthorizationKind,
    ClosedModel,
    Digest,
    Identifier,
    RegistryContract,
)
from infra_automation.workflow_schema import (
    AdmittedCollectionStep,
    HumanDecisionStep,
    PolicyEvaluationStep,
    RegisteredGithubHandoffStep,
    SharedAnalysisStep,
    UploadedIntakeStep,
)
from infra_automation.workflow_validation import validate_workflow

Phase = Literal["decision", "dispatch", "consume"]
EligibilityReason = Literal[
    "invalid_evidence",
    "invalid_clock",
    "invalid_phase",
    "invalid_freshness",
    "stale_evidence",
    "incomplete_evidence",
    "missing_report",
    "unverified_source",
    "insufficient_context",
    "unsupported_recommendation",
    "unsupported_policy",
    "canonical_contract_changed",
    "policy_denied",
    "binding_changed",
    "membership_revoked",
    "target_unavailable",
    "custody_unavailable",
    "missing_approval",
    "approval_expired",
    "custody_expired",
    "source_expired",
    "invalid_workflow",
    "missing_handoff",
    "prerequisite_unsuccessful",
    "decision_missing",
    "decision_mismatch",
    "lineage_mismatch",
    "scope_unresolved",
]

_RECOVERY: dict[EligibilityReason, tuple[str, str]] = {
    "invalid_evidence": (
        "Evidence or live authority facts violate their closed contract.",
        "Resolve current typed evidence and authority before retrying.",
    ),
    "invalid_clock": (
        "Current UTC time cannot be verified.",
        "Restore a trustworthy UTC clock and recheck eligibility.",
    ),
    "invalid_phase": (
        "The eligibility phase is unsupported.",
        "Use a supported decision, dispatch or consumption check.",
    ),
    "invalid_freshness": (
        "Evidence collection times or freshness policy are invalid.",
        "Recollect evidence using the captured policy of at most 60 minutes.",
    ),
    "stale_evidence": (
        "Mandatory evidence freshness has expired.",
        "Recollect, reanalyze and obtain a new decision.",
    ),
    "incomplete_evidence": (
        "Mandatory evidence collection is incomplete.",
        "Collect all mandatory evidence and reanalyze.",
    ),
    "missing_report": (
        "The immutable mandatory report is unavailable.",
        "Submit a new analysis and capture its immutable report.",
    ),
    "unverified_source": (
        "Evidence source identity is unverified; uploaded evidence remains advisory.",
        "Collect evidence through an admitted source before requesting approval.",
    ),
    "insufficient_context": (
        "Mandatory analysis context is insufficient.",
        "Resolve the report's context TODOs and reanalyze.",
    ),
    "unsupported_recommendation": (
        "The report recommendation vocabulary is unsupported.",
        "Analyze with a supported canonical report contract.",
    ),
    "unsupported_policy": (
        "The workflow policy result is unsupported.",
        "Evaluate a supported policy version again.",
    ),
    "canonical_contract_changed": (
        "The canonical report is no longer advisory.",
        "Reanalyze without changing canonical advisory semantics.",
    ),
    "policy_denied": (
        "The mandatory workflow policy gate did not pass.",
        "Resolve policy findings and evaluate current evidence again.",
    ),
    "binding_changed": (
        "The immutable action binding no longer matches current authority.",
        "Recapture evidence, policy and action and request a new decision.",
    ),
    "membership_revoked": (
        "Current reviewer membership is unavailable.",
        "Restore authorized membership and obtain a new decision.",
    ),
    "target_unavailable": (
        "The exact target is unavailable or ineligible.",
        "Select an authorized registered target and request a new decision.",
    ),
    "custody_unavailable": (
        "Required exact-plan custody is unavailable.",
        "Recollect into qualified custody and obtain a new decision.",
    ),
    "missing_approval": (
        "No finite current approval deadline is available.",
        "Obtain a new finite durable human decision.",
    ),
    "approval_expired": (
        "The approval deadline has expired.",
        "Obtain a new decision against current evidence.",
    ),
    "custody_expired": (
        "The custody deadline has expired.",
        "Recollect into current custody and obtain a new decision.",
    ),
    "source_expired": (
        "The source evidence deadline has expired.",
        "Recollect current source evidence and obtain a new decision.",
    ),
    "invalid_workflow": (
        "The closed workflow failed static validation.",
        "Correct and publish a valid workflow revision.",
    ),
    "missing_handoff": (
        "The requested executable handoff is unavailable.",
        "Use a matching handoff from the immutable run definition.",
    ),
    "prerequisite_unsuccessful": (
        "A mandatory executable prerequisite has not succeeded.",
        "Complete this handoff's own mandatory evidence, analysis and policy path.",
    ),
    "decision_missing": (
        "A matching approved human decision is unavailable.",
        "Obtain a current human decision for this exact action.",
    ),
    "decision_mismatch": (
        "The decision belongs to a different immutable action binding.",
        "Obtain a new decision for the exact current packet.",
    ),
    "lineage_mismatch": (
        "Evidence or target belongs to another workflow path.",
        "Analyze and approve the exact artifact, target and handoff path.",
    ),
    "scope_unresolved": (
        "The workflow scope or target remains unresolved.",
        "Resolve authorized concrete scope and typed inputs before approval.",
    ),
}


class EligibilityResult(ClosedModel):
    eligible: StrictBool
    reasons: tuple[EligibilityReason, ...] = ()
    limitations: tuple[StrictStr, ...] = ()
    context_todos: tuple[StrictStr, ...] = ()


class EvidenceFacts(ClosedModel):
    source_kind: Literal["uploaded", "collected"]
    source_verified: StrictBool = False
    collected_at: datetime
    evidence_deadline: datetime
    complete: StrictBool
    report_available: StrictBool
    recommendation: StrictStr
    should_block: StrictBool = False
    insufficient_context: StrictBool = False
    policy_status: StrictStr
    policy_passed: StrictBool = False
    artifact_step_id: Identifier | None = None
    report_step_id: Identifier | None = None
    evidence_ttl_seconds: int = 3600

    @field_validator("evidence_ttl_seconds")
    @classmethod
    def bounded_ttl(cls, value: int) -> int:
        if type(value) is not int or not 1 <= value <= 3600:
            raise ValueError(
                "Evidence policy must be stricter than or equal to 60 minutes."
            )
        return value


class LiveBinding(ClosedModel):
    expected_tuple_digest: Digest
    current_tuple_digest: Digest
    membership_active: StrictBool
    target_available: StrictBool
    custody_available: StrictBool = False
    approval_deadline: datetime | None = None
    custody_deadline: datetime | None = None
    source_deadline: datetime | None = None
    target_id: Identifier
    environment: Identifier
    authorization_kind: AuthorizationKind = "advisory_request"


def _result(reasons: Sequence[EligibilityReason]) -> EligibilityResult:
    ordered = tuple(dict.fromkeys(reasons))
    return EligibilityResult(
        eligible=not ordered,
        reasons=ordered,
        limitations=tuple(_RECOVERY[reason][0] for reason in ordered),
        context_todos=tuple(_RECOVERY[reason][1] for reason in ordered),
    )


def eligibility_from_reasons(codes: Sequence[EligibilityReason]) -> EligibilityResult:
    """Project retained typed invalidation codes without treating prose as authority."""
    if (
        not isinstance(codes, (tuple, list))
        or len(codes) > 50
        or any(type(code) is not str or code not in _RECOVERY for code in codes)
    ):
        return _result(["invalid_evidence"])
    return _result(codes)


def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware clock is required.")
    return value.astimezone(timezone.utc)


def evaluate_evidence(
    evidence: EvidenceFacts,
    live: LiveBinding,
    *,
    now: datetime,
    phase: Phase = "decision",
) -> EligibilityResult:
    """Check current immutable evidence without granting or extending authority."""
    try:
        if type(evidence) is not EvidenceFacts or type(live) is not LiveBinding:
            raise ValueError
        evidence = EvidenceFacts.model_validate_json(
            evidence.model_dump_json(warnings="error")
        )
        live = LiveBinding.model_validate_json(live.model_dump_json(warnings="error"))
    except (ValueError, TypeError, AttributeError):
        return _result(["invalid_evidence"])
    reasons: list[EligibilityReason] = []
    if phase not in ("decision", "dispatch", "consume"):
        reasons.append("invalid_phase")
    try:
        timestamp = _utc(now)
        collected = _utc(evidence.collected_at)
        deadline = _utc(evidence.evidence_deadline)
        if (
            collected > timestamp
            or deadline <= collected
            or deadline > collected + timedelta(seconds=evidence.evidence_ttl_seconds)
        ):
            reasons.append("invalid_freshness")
        if timestamp >= deadline:
            reasons.append("stale_evidence")
        if live.approval_deadline is None:
            if phase in ("dispatch", "consume"):
                reasons.append("missing_approval")
        elif timestamp >= _utc(live.approval_deadline):
            reasons.append("approval_expired")
        if live.source_deadline is not None:
            source_deadline = _utc(live.source_deadline)
            if source_deadline > collected + timedelta(
                seconds=evidence.evidence_ttl_seconds
            ):
                reasons.append("invalid_freshness")
            if timestamp >= source_deadline:
                reasons.append("source_expired")
        if live.authorization_kind == "exact_plan":
            if not live.custody_available or live.custody_deadline is None:
                reasons.append("custody_unavailable")
            elif timestamp >= _utc(live.custody_deadline):
                reasons.append("custody_expired")
    except (TypeError, ValueError, AttributeError, OverflowError):
        reasons.append("invalid_clock")
    if not evidence.complete:
        reasons.append("incomplete_evidence")
    if not evidence.report_available:
        reasons.append("missing_report")
    if evidence.source_kind != "collected" or not evidence.source_verified:
        reasons.append("unverified_source")
    if evidence.insufficient_context:
        reasons.append("insufficient_context")
    if evidence.recommendation not in ("go", "caution", "no-go"):
        reasons.append("unsupported_recommendation")
    if evidence.should_block:
        reasons.append("canonical_contract_changed")
    if evidence.policy_status not in ("advisory", "warn", "soft-block", "hard-block"):
        reasons.append("unsupported_policy")
    elif (
        evidence.policy_status in ("soft-block", "hard-block")
        or not evidence.policy_passed
    ):
        reasons.append("policy_denied")
    if live.current_tuple_digest != live.expected_tuple_digest:
        reasons.append("binding_changed")
    if not live.membership_active:
        reasons.append("membership_revoked")
    if not live.target_available:
        reasons.append("target_unavailable")
    return _result(reasons)


def _evaluate_action_path(
    *,
    definition_bytes: bytes,
    registry_contract: RegistryContract,
    handoff_step_id: str | None = None,
    decision_step_id: str | None = None,
    step_states: tuple[tuple[str, str], ...],
    evidence: EvidenceFacts,
    live: LiveBinding,
    now: datetime,
    decision_binding_digest: str | None = None,
    decision_approved: bool = False,
    phase: Phase = "dispatch",
) -> EligibilityResult:
    """Require this exact validated handoff's complete successful AND ancestry.

    A decision waits for its own mandatory ancestry, allowing independent human
    requests before their shared downstream handoff becomes executable. Dispatch
    and consumption require the full handoff ancestry and matching receipt.
    Unknown runtime states, missing branches and unrelated successes never count.
    """
    reasons = list(evaluate_evidence(evidence, live, now=now, phase=phase).reasons)
    if "invalid_evidence" in reasons:
        return _result(reasons)
    validated = validate_workflow(definition_bytes, registry_contract=registry_contract)
    if not validated.valid:
        return _result(reasons + ["invalid_workflow"])
    workflow = validated.definition
    if workflow is None:
        return _result(reasons + ["invalid_workflow"])
    nodes = {step.id: step for step in workflow.steps}
    handoff = None
    if handoff_step_id is not None:
        candidate = nodes.get(handoff_step_id)
        if not isinstance(candidate, RegisteredGithubHandoffStep):
            return _result(reasons + ["missing_handoff"])
        handoff = candidate
        decision = nodes.get(handoff.decision.step_id)
    else:
        decision = nodes.get(decision_step_id or "")
    if not isinstance(decision, HumanDecisionStep):
        return _result(reasons + ["decision_missing"])
    gate = nodes[decision.binding.step_id]
    if not isinstance(gate, PolicyEvaluationStep):
        return _result(reasons + ["invalid_workflow"])
    analysis = nodes[gate.report.step_id]
    if not isinstance(analysis, SharedAnalysisStep):
        return _result(reasons + ["invalid_workflow"])
    source = nodes[analysis.artifact.step_id]
    if not isinstance(source, (AdmittedCollectionStep, UploadedIntakeStep)):
        return _result(reasons + ["invalid_workflow"])
    if (
        type(workflow.environment) is not str
        or workflow.workspace_id is None
        or type(gate.target_id) is not str
        or type(gate.environment) is not str
    ):
        reasons.append("scope_unresolved")
    if (
        evidence.report_step_id != analysis.id
        or evidence.artifact_step_id != source.id
        or live.target_id != gate.target_id
        or live.environment != gate.environment
        or live.authorization_kind != gate.authorization_kind
        or (source.kind == "admitted_collection")
        != (evidence.source_kind == "collected")
    ):
        reasons.append("lineage_mismatch")
    try:
        if (
            type(step_states) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or any(type(part) is not str for part in item)
                for item in step_states
            )
            or len(dict(step_states)) != len(step_states)
            or len(step_states) > 50
        ):
            raise ValueError
        states = dict(step_states)
        allowed = (
            ("pending", "waiting_approval") if phase == "decision" else ("succeeded",)
        )
        if states.get(decision.id) not in allowed:
            reasons.append("prerequisite_unsuccessful")
        pending = list(
            decision.depends_on
            if phase == "decision" or handoff is None
            else handoff.depends_on
        )
        visited: set[str] = set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            if states.get(name) != "succeeded":
                reasons.append("prerequisite_unsuccessful")
            pending.extend(nodes[name].depends_on)
    except (ValueError, TypeError):
        reasons.append("prerequisite_unsuccessful")
    if phase != "decision":
        if decision_approved is not True:
            reasons.append("decision_missing")
        if decision_binding_digest != live.current_tuple_digest:
            reasons.append("decision_mismatch")
    return _result(reasons)


def evaluate_decision(
    *,
    definition_bytes: bytes,
    registry_contract: RegistryContract,
    decision_step_id: str,
    step_states: tuple[tuple[str, str], ...],
    evidence: EvidenceFacts,
    live: LiveBinding,
    now: datetime,
    decision_binding_digest: str | None = None,
    decision_approved: bool = False,
    phase: Phase = "decision",
) -> EligibilityResult:
    """Check a human decision's own exact gate and mandatory prerequisite path.

    A human step may be another action's mandatory prerequisite without a direct
    handoff receipt consumer. Its own finite evidence and live authority checks
    remain identical; approving it does not qualify the downstream handoff.
    """
    return _evaluate_action_path(
        definition_bytes=definition_bytes,
        registry_contract=registry_contract,
        decision_step_id=decision_step_id,
        step_states=step_states,
        evidence=evidence,
        live=live,
        now=now,
        decision_binding_digest=decision_binding_digest,
        decision_approved=decision_approved,
        phase=phase,
    )


def evaluate_handoff(
    *,
    definition_bytes: bytes,
    registry_contract: RegistryContract,
    handoff_step_id: str,
    step_states: tuple[tuple[str, str], ...],
    evidence: EvidenceFacts,
    live: LiveBinding,
    now: datetime,
    decision_binding_digest: str | None = None,
    decision_approved: bool = False,
    phase: Phase = "dispatch",
) -> EligibilityResult:
    """Check the exact human binding and, before effects, full handoff ancestry."""
    return _evaluate_action_path(
        definition_bytes=definition_bytes,
        registry_contract=registry_contract,
        handoff_step_id=handoff_step_id,
        step_states=step_states,
        evidence=evidence,
        live=live,
        now=now,
        decision_binding_digest=decision_binding_digest,
        decision_approved=decision_approved,
        phase=phase,
    )
