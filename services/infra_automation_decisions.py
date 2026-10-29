"""Durable human decisions over server-resolved evidence, with deny-only ports.

The material port is installed by server composition, never by an HTTP caller.
The default has no admitted target/custody/collector and cannot create authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
import json
from typing import Annotated, Callable, Literal

from pydantic import Field, StrictInt, StrictStr, field_validator

from sqlalchemy import select

from infra_automation.approval_eligibility import (
    EvidenceFacts,
    LiveBinding,
    eligibility_from_reasons,
    evaluate_handoff,
    evaluate_decision,
)
from infra_automation.contracts import ClosedModel, Digest, Identifier, RegistryContract
from infra_automation.decisions import (
    DecisionBinding,
    binding_bytes,
    binding_digest,
    freeze_report_snapshot,
    instant,
)
from infra_automation.lifecycle import LifecycleError, MutationRequest, Positive
from infra_automation.state import AuditActor, UTCText
from infra_automation.review_contracts import ConfirmationRequirements
from models.repositories import infra_automation_decisions as repository
from models.repositories import infra_automation_runs as runs
from models.tables import (
    InfraAutomationReportLink,
    InfraAutomationArtifactManifest,
    InfraAutomationAttempt,
)
from services import infra_automation_support as support
from services import project_service as authorization
from services.infra_automation_engine_service import _document
from services.infra_automation_policy import check_live_policy


class DecisionRequest(MutationRequest):
    expected_version: Positive
    binding_digest: Digest
    outcome: Literal["approve", "reject"]
    confirmation: Annotated[StrictStr, Field(max_length=256)] | None = None

    @field_validator("confirmation")
    @classmethod
    def printable_confirmation(cls, value):
        if value is not None:
            if any(
                ord(char) < 32 or 127 <= ord(char) <= 159 or char in "\u2028\u2029"
                for char in value
            ):
                raise ValueError("Confirmation must be a bounded single line.")
            value.encode("utf-8", errors="strict")
        return value


def confirmation_requirements(binding, report_payload, decision_kind):
    """Derive nonsecret typed phrases from immutable severity and server mode."""
    severity = report_payload.get("severity") if type(report_payload) is dict else None
    if (
        type(severity) is not str
        or severity not in {"low", "medium", "high", "critical"}
        or type(decision_kind) is not str
        or decision_kind not in {"independent-approval", "acknowledgement"}
    ):
        raise LifecycleError(503)
    binding = support.revalidate(binding, DecisionBinding)
    required = report_payload["severity"] in {"high", "critical"}
    approval = "ACKNOWLEDGE" if decision_kind == "acknowledgement" else "APPROVE"
    return ConfirmationRequirements(
        required=required,
        approve_phrase=f"{approval} {binding.canonical_target}" if required else None,
        reject_phrase=f"REJECT {binding.canonical_target}" if required else None,
    )


class DecisionAuditState(ClosedModel):
    """Versioned screened receipt state; independent of binding/report identity."""

    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    id: Identifier
    run_id: Identifier
    step_id: Identifier
    project_id: Positive
    workspace_id: Positive
    generation: Positive
    transition_version: Positive
    status: Literal[
        "pending", "approved", "rejected", "expired", "invalidated", "superseded"
    ]
    binding_digest: Digest
    requested_by: Identifier
    reviewer_id: Identifier | None
    reviewer_authentication_version: Positive | None
    reviewer_authorization_version: Positive | None
    decision_kind: Literal["independent-approval", "acknowledgement"] | None
    reason: Annotated[StrictStr, Field(max_length=2048)] | None
    created_at: UTCText
    deadline_at: UTCText
    decided_at: UTCText | None
    actor_principal_id: Identifier | None
    actor_type: Literal["human", "service"] | None
    actor_role: (
        Literal[
            "admin", "maintainer", "reviewer", "contributor", "read-only", "coordinator"
        ]
        | None
    )


def decision_audit_snapshot(row, *, actor=None):
    """Capture actual immutable receipt facts, never current membership guesses."""
    from infra_automation.artifact_intake import screen_metadata

    try:
        binding = DecisionBinding.model_validate_json(row.binding_bytes)
        if (
            binding_digest(binding) != row.binding_digest
            or support.digest(row.report_bytes) != binding.report_bytes_digest
        ):
            raise ValueError
        value = DecisionAuditState(
            id=row.id,
            run_id=row.run_id,
            step_id=row.step_id,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            generation=row.generation,
            transition_version=row.version,
            status=row.status,
            binding_digest=row.binding_digest,
            requested_by=row.requested_by,
            reviewer_id=row.reviewer_id,
            reviewer_authentication_version=row.reviewer_authentication_version,
            reviewer_authorization_version=row.reviewer_authorization_version,
            decision_kind=row.decision_kind,
            reason=row.reason,
            created_at=support.utc(row.created_at),
            deadline_at=support.utc(row.deadline_at),
            decided_at=support.utc(row.decided_at) if row.decided_at else None,
            actor_principal_id=actor.principal_id if actor else None,
            actor_type=actor.principal_type if actor else None,
            actor_role=actor.role if actor else None,
        )
        screen_metadata(value.model_dump(mode="json"))
        return value
    except (ValueError, TypeError, AttributeError):
        raise LifecycleError(503) from None


def decision_audit_digest(row, *, actor=None):
    return support.digest(
        support.canonical(
            decision_audit_snapshot(row, actor=actor).model_dump(mode="json")
        )
    )


@dataclass(frozen=True)
class DecisionMaterial:
    """Trusted scoped target/custody facts; seeded ports do not admit collectors."""

    binding: DecisionBinding
    evidence: EvidenceFacts
    live: LiveBinding
    registry_contract: RegistryContract


def _run_time_reasons(run, now, receipt=None):
    floors = [runs.utc(run.last_observed_at)]
    if receipt is not None:
        floors.append(runs.utc(receipt.created_at))
        if receipt.decided_at is not None:
            floors.append(runs.utc(receipt.decided_at))
    if now < max(floors):
        return ("invalid_clock",)
    return ("run_timed_out",) if now >= runs.utc(run.deadline_at) else ()


def _expiry_reasons(binding, now):
    deadlines = [
        ("stale_evidence", binding.evidence_deadline),
        ("approval_expired", binding.approval_deadline),
    ]
    if binding.provenance.source.kind == "collected":
        deadlines.append(("source_expired", binding.provenance.source.source_deadline))
    if binding.provenance.custody:
        deadlines.append(("custody_expired", binding.provenance.custody.expires_at))
    return tuple(reason for reason, deadline in deadlines if now >= instant(deadline))


def _denied_run_state(reasons):
    if "run_timed_out" in reasons:
        return "timed_out"
    if any(
        reason in reasons
        for reason in (
            "stale_evidence",
            "approval_expired",
            "source_expired",
            "custody_expired",
        )
    ):
        return "expired"
    return "stopped_by_gate"


class DecisionService:
    def __init__(
        self, *, material_port=None, clock: Callable[[], datetime] | None = None
    ):
        self.material_port = material_port
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        value = self.clock()
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise LifecycleError(503)
        return value.astimezone(timezone.utc)

    def _run(self, session, run_id, capability, *, mutation):
        run = runs.get_run(session, support.identifier(run_id))
        if run is None:
            raise authorization.TrustedAuthorizationError()
        grant = support.scope(
            session, run.project_id, run.workspace_id, capability, mutation=mutation
        )
        return run, grant, _document(run)

    def _material(
        self, session, run, document, step_id, previous=None, report_bytes=None
    ):
        if self.material_port is None:
            raise LifecycleError(503)
        material = self.material_port(session, run, step_id, previous)
        if type(material) is not DecisionMaterial:
            raise LifecycleError(503)
        binding = support.revalidate(material.binding, DecisionBinding)
        step = next(
            (step for step in document.definition.steps if step.id == step_id), None
        )
        if step is None or step.kind != "human_decision":
            raise LifecycleError(409)
        gate = next(
            (
                item
                for item in document.definition.steps
                if item.id == step.binding.step_id
            ),
            None,
        )
        if gate is None or gate.kind != "policy_evaluation":
            raise LifecycleError(409)
        if (
            binding.project_id,
            binding.workspace_id,
            binding.workflow_id,
            binding.revision_id,
            binding.workflow_revision_digest,
            binding.input_digest,
            binding.environment,
            binding.authorization_epoch,
            binding.restore_epoch,
            binding.canonical_target,
            binding.authorization_kind,
        ) != (
            run.project_id,
            run.workspace_id,
            run.workflow_id,
            run.revision_id,
            run.definition_digest,
            run.input_digest,
            document.environment,
            document.authority.authorization_epoch,
            document.authority.restore_epoch,
            gate.target_id,
            gate.authorization_kind,
        ):
            raise LifecycleError(409)
        # Resolve the source of this gate's exact report, not another branch.
        analysis = next(
            (
                item
                for item in document.definition.steps
                if item.id == gate.report.step_id
            ),
            None,
        )
        if analysis is None or analysis.kind != "shared_analysis":
            raise LifecycleError(409)
        sources = [
            source
            for source in document.sources
            if source.kind == "collected"
            and source.step_id == analysis.artifact.step_id
        ]
        if not sources or binding.provenance.source.kind != "collected":
            raise LifecycleError(409)
        if not any(
            source.repository_id == binding.provenance.source.repository_id
            and source.commit_sha == binding.provenance.source.commit_sha
            and source.profile_digest == binding.provenance.source.profile_digest
            for source in sources
        ):
            raise LifecycleError(409)
        link = session.scalar(
            select(InfraAutomationReportLink).where(
                InfraAutomationReportLink.run_id == run.id,
                InfraAutomationReportLink.report_id == binding.report_id,
                InfraAutomationReportLink.project_id == run.project_id,
                InfraAutomationReportLink.workspace_id == run.workspace_id,
            )
        )
        if link is None:
            raise LifecycleError(409)
        manifest = session.get(InfraAutomationArtifactManifest, link.manifest_id)
        attempt = session.scalar(
            select(InfraAutomationAttempt).where(
                InfraAutomationAttempt.id == link.attempt_id
            )
        )
        if (
            manifest is None
            or attempt is None
            or (
                manifest.run_id != run.id
                or manifest.step_id != analysis.artifact.step_id
                or attempt.run_id != run.id
                or attempt.step_id != analysis.id
                or attempt.state != "succeeded"
                or support.digest(manifest.artifacts_bytes) != manifest.digest
                or support.digest(link.provenance_bytes) != link.digest
                or json.loads(attempt.output_json or "null")
                != {"kind": "report", "reference": link.id, "digest": link.digest}
                or manifest.digest not in binding.screened_artifact_digests
            )
        ):
            raise LifecycleError(409)
        if (
            manifest.collection_bytes is None
            or support.digest(manifest.collection_bytes) != manifest.collection_digest
        ):
            raise LifecycleError(409)
        from infra_automation.preflight_contracts import SyntheticCollectionEnvelope

        collection = SyntheticCollectionEnvelope.model_validate_json(
            manifest.collection_bytes
        )
        if (
            collection.run_id,
            collection.step_id,
            collection.repository_id,
            collection.commit_sha,
            collection.collector_id,
            collection.profile_digest,
            collection.sanitized_digest,
            collection.collected_at,
            collection.source_deadline,
            collection.redaction_version,
        ) != (
            run.id,
            analysis.artifact.step_id,
            binding.provenance.source.repository_id,
            binding.provenance.source.commit_sha,
            binding.provenance.source.collector_id,
            binding.provenance.source.profile_digest,
            binding.provenance.source.screened_transport_digest,
            binding.provenance.source.collected_at,
            binding.provenance.source.source_deadline,
            binding.redaction_version,
        ):
            raise LifecycleError(409)
        source_attempts = [
            item
            for item in runs.list_attempts(session, run_id=run.id)
            if item.step_id == analysis.artifact.step_id
        ]
        latest_source = source_attempts[-1] if source_attempts else None
        if (
            latest_source is None
            or latest_source.state != "succeeded"
            or (
                collection.attempt_id != latest_source.id
                or collection.fence != latest_source.fence
                or json.loads(latest_source.output_json or "null")
                != {
                    "kind": "screened_artifacts",
                    "reference": manifest.id,
                    "digest": manifest.digest,
                }
            )
        ):
            raise LifecycleError(409)
        if (
            binding.provenance.custody
            and collection.raw_local_digest
            != binding.provenance.custody.raw_local_digest
        ):
            raise LifecycleError(409)
        policy_row, _ = support.policy_state(session, run.project_id)
        policy_digest = support.digest(
            support.canonical(
                {
                    "automation": document.policy.model_dump(mode="json"),
                    "advisory": document.advisory_policy.model_dump(mode="json"),
                }
            )
        )
        if (
            policy_row is None
            or binding.policy_version != policy_row.version
            or binding.policy_digest != policy_digest
        ):
            raise LifecycleError(409)
        actual_digest = binding_digest(binding)
        if (
            material.live.expected_tuple_digest != actual_digest
            or material.live.current_tuple_digest != actual_digest
        ):
            raise LifecycleError(409)
        source = binding.provenance.source
        collected_at = instant(source.collected_at)
        if instant(binding.evidence_deadline) > collected_at + timedelta(
            seconds=document.policy.evidence_ttl_seconds
        ):
            raise LifecycleError(409)
        if material.evidence.evidence_deadline != instant(binding.evidence_deadline):
            raise LifecycleError(409)
        from services.report_service import (
            _serialize_report,
            build_report_advisory_payload,
        )

        report = authorization.guard_report(session, binding.report_id, "report.read")
        if report is None or (report.project_id, report.workspace_id) != (
            run.project_id,
            run.workspace_id,
        ):
            raise authorization.TrustedAuthorizationError()
        if report.recommendation not in {
            "go",
            "caution",
            "no-go",
        } or report.severity not in {"low", "medium", "high", "critical"}:
            raise LifecycleError(409)
        if report_bytes is None:
            report_bytes, report_digest = freeze_report_snapshot(
                _serialize_report(report)
            )
        else:
            report_digest = support.digest(report_bytes)
        if report_digest != binding.report_bytes_digest:
            raise LifecycleError(409)
        payload = json.loads(report_bytes)
        if (
            material.evidence.source_kind != "collected"
            or not material.evidence.source_verified
        ):
            raise LifecycleError(409)
        advisory = build_report_advisory_payload(payload)
        from services.analysis_service import build_share_summary
        from services.adapter_output_contract import build_adapter_output_contract
        from services.policy_adapter_output_contract import (
            build_policy_adapter_output_from_settings,
        )

        adapter = build_adapter_output_contract(
            build_share_summary(payload),
            {
                "adapter": "infra-automation",
                "format": "decision-v1",
                "project_id": run.project_id,
            },
        )
        policy = build_policy_adapter_output_from_settings(
            adapter,
            document.advisory_policy,
            resolved_project_key=document.advisory_policy.project_key,
        )
        context = payload.get("context_completeness") or {}
        evidence = EvidenceFacts.model_validate(
            {
                **material.evidence.model_dump(),
                "collected_at": collected_at,
                "recommendation": report.recommendation,
                "should_block": advisory["should_block"],
                "insufficient_context": context.get("insufficient_context", False),
                "complete": material.evidence.complete
                and collection.exit_code in {0, 2}
                and not advisory["partial_context"]
                and context.get("evidence_success_rate", 1) == 1,
                "report_available": True,
                "policy_status": policy.status.value,
                "policy_passed": policy.status.value in {"advisory", "warn"},
                "artifact_step_id": analysis.artifact.step_id,
                "report_step_id": analysis.id,
                "evidence_ttl_seconds": document.policy.evidence_ttl_seconds,
            }
        )
        live = LiveBinding.model_validate(
            {
                **material.live.model_dump(),
                "approval_deadline": instant(binding.approval_deadline),
                "source_deadline": instant(source.source_deadline),
                "custody_deadline": instant(binding.provenance.custody.expires_at)
                if binding.provenance.custody
                else None,
            }
        )
        return replace(material, evidence=evidence, live=live), report_bytes

    def _eligibility(
        self,
        session,
        run,
        document,
        step_id,
        material,
        *,
        phase="decision",
        approval=None,
    ):
        matching = [
            step
            for step in document.definition.steps
            if step.kind == "registered_github_handoff"
            and step.decision.step_id == step_id
        ]
        states = {}
        for attempt in runs.list_attempts(session, run_id=run.id):
            states[attempt.step_id] = attempt.state
        states.setdefault(step_id, "pending")
        # Human steps have durable receipts rather than manufactured attempts.
        # Verify each latest receipt without traversing its graph before projecting
        # it; the full selected DAG traversal below enforces prerequisite order.
        receipts = repository.list_latest_for_run(session, run.id)
        for receipt in receipts:
            if (
                receipt.status == "approved"
                and self._receipt_evidence(
                    session, receipt.id, phase="dispatch"
                ).eligible
            ):
                states[receipt.step_id] = "succeeded"
        # Material resolution may outlive an earlier receipt's check. Project all
        # human facts against the same final clock before traversing the graph.
        now = self._now()
        for receipt in receipts:
            if states.get(receipt.step_id) == "succeeded" and (
                _run_time_reasons(run, now, receipt)
                or _expiry_reasons(
                    DecisionBinding.model_validate_json(receipt.binding_bytes), now
                )
            ):
                states.pop(receipt.step_id)
        time_reasons = _run_time_reasons(run, now, approval)
        # Requests and mandatory prerequisite receipts bind the human step's own
        # gate/ancestry. They do not need to own a handoff receipt reference.
        if phase == "decision" or not matching:
            results = [
                evaluate_decision(
                    definition_bytes=support.canonical(
                        document.definition.model_dump(mode="json")
                    ),
                    registry_contract=material.registry_contract,
                    decision_step_id=step_id,
                    step_states=tuple(states.items()),
                    evidence=material.evidence,
                    live=material.live,
                    now=now,
                    phase=phase,
                    decision_binding_digest=approval.binding_digest
                    if approval is not None
                    else None,
                    decision_approved=approval is not None
                    and approval.status == "approved",
                )
            ]
        else:
            results = [
                evaluate_handoff(
                    definition_bytes=support.canonical(
                        document.definition.model_dump(mode="json")
                    ),
                    registry_contract=material.registry_contract,
                    handoff_step_id=handoff.id,
                    step_states=tuple(states.items()),
                    evidence=material.evidence,
                    live=material.live,
                    now=now,
                    phase=phase,
                    decision_binding_digest=approval.binding_digest
                    if approval is not None
                    else None,
                    decision_approved=approval is not None
                    and approval.status == "approved",
                )
                for handoff in matching
            ]
        return [
            eligibility_from_reasons((*time_reasons, *result.reasons))
            for result in results
        ], now

    def _waiting_for_human(self, session, run, document, step_id):
        """Only an unfinished human ancestor defers otherwise valid evidence."""
        nodes = {step.id: step for step in document.definition.steps}
        states = {
            attempt.step_id: attempt.state
            for attempt in runs.list_attempts(session, run_id=run.id)
        }
        receipts = {
            receipt.step_id: receipt
            for receipt in repository.list_latest_for_run(session, run.id)
        }
        pending = list(nodes[step_id].depends_on)
        visited = set()
        waiting = False
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            node = nodes[name]
            if node.kind == "human_decision":
                receipt = receipts.get(name)
                if receipt is None or receipt.status == "pending":
                    if states.get(name) not in (None, "pending", "waiting_approval"):
                        return False
                    waiting = True
                elif (
                    receipt.status != "approved"
                    or not self._receipt_evidence(session, receipt.id).eligible
                ):
                    return False
            elif states.get(name) != "succeeded":
                return False
            pending.extend(node.depends_on)
        return waiting

    def request_decision(self, run_id: str, step_id: str) -> dict:
        """Persist a pending request from a fully analyzed admitted server context."""
        with authorization.authorized_session() as session:
            now = self._now()
            run, grant, document = self._run(
                session, run_id, "automation.request", mutation=True
            )
            time_reasons = _run_time_reasons(run, now)
            if time_reasons:
                raise LifecycleError(503 if "invalid_clock" in time_reasons else 409)
            check_live_policy(session, document.authority, "dispatch")
            if run.state not in {"running", "waiting_approval"} or run.cancel_requested:
                raise LifecycleError(409)
            material, report_bytes = self._material(
                session, run, document, support.identifier(step_id)
            )
            now = self._now()
            binding = material.binding
            if instant(binding.approval_deadline) > now + timedelta(
                seconds=document.policy.approval_ttl_seconds
            ):
                raise LifecycleError(409)
            authorization.guard_report(session, binding.report_id, "report.read")
            link = session.scalar(
                select(InfraAutomationReportLink).where(
                    InfraAutomationReportLink.run_id == run.id,
                    InfraAutomationReportLink.report_id == binding.report_id,
                    InfraAutomationReportLink.project_id == run.project_id,
                    InfraAutomationReportLink.workspace_id == run.workspace_id,
                )
            )
            if link is None:
                raise LifecycleError(409)
            results, now = self._eligibility(session, run, document, step_id, material)
            denied = tuple(
                dict.fromkeys(reason for result in results for reason in result.reasons)
            )
            if "invalid_clock" in denied:
                raise LifecycleError(503)
            if "run_timed_out" in denied:
                raise LifecycleError(409)
            if denied == ("prerequisite_unsuccessful",) and self._waiting_for_human(
                session, run, document, step_id
            ):
                raise LifecycleError(409)
            from infra_automation import claims
            from models.tables import InfraAutomationDecision

            existing = session.scalar(
                select(InfraAutomationDecision).where(
                    InfraAutomationDecision.run_id == run.id,
                    InfraAutomationDecision.step_id == step_id,
                    InfraAutomationDecision.status == "pending",
                )
            )
            request_actor = AuditActor(
                grant.principal.principal_id,
                grant.principal.principal_type,
                grant.role,
            )
            request_before_digest = (
                decision_audit_digest(existing, actor=request_actor)
                if existing is not None
                else None
            )
            if existing is None:
                from services.infra_automation_engine_support import ensure_engine_actor

                ensure_engine_actor(session, grant)
                claims._charge(
                    session,
                    run,
                    len(binding_bytes(binding)) + len(report_bytes),
                    now,
                    None,
                )
                run = runs.get_run(session, run.id)
            values = dict(
                run_id=run.id,
                step_id=step_id,
                requested_by=run.requested_by,
                report_bytes=report_bytes,
                now=now,
            )
            if denied:
                row = repository.create_denied_request(
                    session, binding, reason_codes=denied, **values
                )
                self._transition(
                    session,
                    run,
                    grant,
                    _denied_run_state(denied),
                    now,
                )
            else:
                row = repository.create_request(session, binding, **values)
                if run.state == "running":
                    self._transition(session, run, grant, "waiting_approval", now)
            support.append_audit(
                session,
                grant,
                workspace_id=run.workspace_id,
                event_type="decision_gate_denied" if denied else "decision_requested",
                target_id=row.id,
                reason="Evidence-bound decision request",
                before_digest=request_before_digest,
                after_digest=decision_audit_digest(row, actor=request_actor),
            )
            response = _view(row)
        if denied:
            raise LifecycleError(409)
        return response

    def _transition(self, session, run, grant, state, now):
        actor = AuditActor(
            grant.principal.principal_id, grant.principal.principal_type, grant.role
        )
        changed = runs.transition_run(
            session,
            run_id=run.id,
            expected_version=run.version,
            state=state,
            audit_actor=actor,
            reason="Evidence-bound human decision",
            now=now,
        )
        if changed is None:
            raise LifecycleError(409)
        return changed

    def decide(self, approval_id: str, request: DecisionRequest) -> dict:
        request = support.revalidate(request, DecisionRequest)
        invalid = False
        with authorization.authorized_session() as session:
            now = self._now()
            row = repository.get_request(session, support.identifier(approval_id))
            if row is None:
                raise authorization.TrustedAuthorizationError()
            run, grant, document = self._run(
                session, row.run_id, "automation.decision", mutation=True
            )
            # Context derives entirely from the retained request and run, never body claims.
            result = authorization.authorize_automation_decision(
                authorization.DecisionContext(
                    project_id=row.project_id,
                    workspace_id=row.workspace_id,
                    report_id=DecisionBinding.model_validate_json(
                        row.binding_bytes
                    ).report_id,
                    requester_principal_id=run.requested_by,
                    object_id=row.id,
                )
            )
            if (
                row.version != request.expected_version
                or row.binding_digest != request.binding_digest
                or row.status != "pending"
            ):
                raise LifecycleError(409)
            support.screened_label(request.reason)
            binding = DecisionBinding.model_validate_json(row.binding_bytes)
            if (
                support.digest(row.report_bytes) != binding.report_bytes_digest
                or row.report_digest != binding.report_bytes_digest
            ):
                raise LifecycleError(503)
            phrases = confirmation_requirements(
                binding, json.loads(row.report_bytes), result["decision_kind"]
            )
            expected_phrase = (
                phrases.approve_phrase
                if request.outcome == "approve"
                else phrases.reject_phrase
            )
            if phrases.required and request.confirmation != expected_phrase:
                raise LifecycleError(422)
            before_digest = decision_audit_digest(row)
            reasons = (
                *_run_time_reasons(run, now, row),
                *_expiry_reasons(binding, now),
            )
            if "invalid_clock" in reasons:
                raise LifecycleError(503)
            valid = (
                not reasons
                and run.state == "waiting_approval"
                and not run.cancel_requested
            )
            if not valid and not reasons:
                reasons = ("binding_changed",)
            if valid:
                try:
                    check_live_policy(session, document.authority, "dispatch")
                    material, _ = self._material(
                        session, run, document, row.step_id, binding, row.report_bytes
                    )
                    valid = binding_digest(material.binding) == row.binding_digest
                    if valid:
                        eligibility, now = self._eligibility(
                            session, run, document, row.step_id, material
                        )
                        reasons = tuple(
                            dict.fromkeys(
                                code for item in eligibility for code in item.reasons
                            )
                        )
                        reasons = tuple(
                            dict.fromkeys(
                                (
                                    *reasons,
                                    *_run_time_reasons(run, now, row),
                                    *_expiry_reasons(binding, now),
                                )
                            )
                        )
                        if "invalid_clock" in reasons:
                            raise LifecycleError(503)
                        valid = not reasons
                    else:
                        reasons = ("binding_changed",)
                except LifecycleError as error:
                    if error.status_code == 503:
                        raise
                    valid = False
                    reasons = ("binding_changed",)
                except (
                    authorization.TrustedAuthorizationError,
                    ValueError,
                    TypeError,
                ):
                    valid = False
                    reasons = ("binding_changed",)
            if not valid:
                state = _denied_run_state(reasons)
                row = repository.invalidate(
                    session,
                    row.id,
                    expected_version=row.version,
                    status="expired"
                    if state in {"expired", "timed_out"}
                    else "invalidated",
                    reason=json.dumps(reasons),
                    now=now,
                )
                if run.state == "waiting_approval":
                    self._transition(
                        session,
                        run,
                        grant,
                        state,
                        now,
                    )
                invalid = True
            else:
                row = repository.decide(
                    session,
                    row.id,
                    expected_version=request.expected_version,
                    binding_digest=request.binding_digest,
                    reviewer_id=result["actor_principal_id"],
                    decision_kind=result["decision_kind"],
                    reviewer_authentication_version=grant.principal.authentication_version,
                    reviewer_authorization_version=grant.authorization_version,
                    outcome=request.outcome,
                    reason=request.reason,
                    now=now,
                )
                if request.outcome == "reject":
                    self._transition(session, run, grant, "rejected", now)
                else:
                    required = {
                        step.id
                        for step in document.definition.steps
                        if step.kind == "human_decision"
                    }
                    approved = {
                        item.step_id: item
                        for item in repository.list_latest_for_run(session, run.id)
                        if item.status == "approved"
                    }
                    if required <= approved.keys() and all(
                        self._recheck_graph(
                            session, approved[name].id, phase="dispatch"
                        ).eligible
                        for name in required
                    ):
                        self._transition(session, run, grant, "ready_handoff", now)
            support.append_audit(
                session,
                grant,
                workspace_id=run.workspace_id,
                event_type="decision_invalidated"
                if invalid
                else "decision_" + request.outcome,
                target_id=row.id,
                reason=request.reason,
                before_digest=before_digest,
                after_digest=decision_audit_digest(
                    row,
                    actor=AuditActor(
                        grant.principal.principal_id,
                        grant.principal.principal_type,
                        grant.role,
                    ),
                ),
            )
            response = _view(row)
        # Invalidations commit before conflict is returned; no retry can revive them.
        if invalid:
            raise LifecycleError(409)
        return response

    def _receipt_evidence(self, session, approval_id, *, phase="dispatch"):
        """Additional deny check inside the consumer's authenticated transaction.

        This is not a receiver credential issuer; callers authenticate their own
        audience/operation before invoking it and keep this transaction open
        through dispatch/consume. Retained decisions are never replay authority.
        """
        from infra_automation.approval_eligibility import eligibility_from_reasons
        from models.tables import IdentityAccount
        from models.repositories import project_memberships

        authorization._require_operation(session)
        if phase not in {"dispatch", "consume"}:
            return eligibility_from_reasons(("invalid_phase",))
        row = repository.get_request(session, support.identifier(approval_id))
        if row is None or row.status != "approved":
            return eligibility_from_reasons(("missing_approval",))
        latest = next(
            (
                item
                for item in repository.list_latest_for_run(session, row.run_id)
                if item.step_id == row.step_id
            ),
            None,
        )
        if latest is None or latest.id != row.id:
            return eligibility_from_reasons(("binding_changed",))
        try:
            _view(row)
            run = runs.get_run(session, row.run_id)
            if (
                run is None
                or run.state
                not in {
                    "waiting_approval",
                    "ready_handoff",
                    "handing_off",
                    "external_running",
                }
                or run.cancel_requested
            ):
                return eligibility_from_reasons(("binding_changed",))
            document = _document(run)
            check_live_policy(session, document.authority, phase)
            account = session.get(
                IdentityAccount, row.reviewer_id, populate_existing=True
            )
            member = project_memberships.get_membership(
                session, principal_id=row.reviewer_id, project_id=row.project_id
            )
            if (
                account is None
                or member is None
                or not account.enabled
                or not member.enabled
                or account.principal_type != "human"
                or account.authentication_version != row.reviewer_authentication_version
                or member.authorization_version != row.reviewer_authorization_version
                or member.workspace_id not in (None, row.workspace_id)
                or "automation.decision"
                not in authorization.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
            ):
                return eligibility_from_reasons(("membership_revoked",))
            import config

            if row.decision_kind == "independent-approval":
                if (
                    row.reviewer_id == run.requested_by
                    or config.settings.identity_decision_mode != "shared"
                ):
                    return eligibility_from_reasons(("membership_revoked",))
            elif row.decision_kind == "acknowledgement":
                from sqlalchemy import func

                humans = session.scalar(
                    select(func.count())
                    .select_from(IdentityAccount)
                    .where(
                        IdentityAccount.enabled.is_(True),
                        IdentityAccount.principal_type == "human",
                    )
                )
                if (
                    config.settings.identity_decision_mode != "single-operator"
                    or humans != 1
                ):
                    return eligibility_from_reasons(("membership_revoked",))
            else:
                return eligibility_from_reasons(("missing_approval",))
            binding = DecisionBinding.model_validate_json(row.binding_bytes)
            material, _ = self._material(
                session, run, document, row.step_id, binding, row.report_bytes
            )
            if binding_digest(material.binding) != row.binding_digest:
                return eligibility_from_reasons(("binding_changed",))
            from infra_automation.approval_eligibility import evaluate_evidence

            now = self._now()
            result = evaluate_evidence(
                material.evidence, material.live, now=now, phase=phase
            )
            return eligibility_from_reasons(
                (*_run_time_reasons(run, now, row), *result.reasons)
            )
        except authorization.TrustedAuthorizationError:
            return eligibility_from_reasons(("membership_revoked",))
        except LifecycleError as error:
            if error.status_code == 503:
                raise
            return eligibility_from_reasons(("binding_changed",))
        except (ValueError, TypeError):
            return eligibility_from_reasons(("binding_changed",))

    def _recheck_graph(self, session, approval_id, *, phase="dispatch"):
        """Check a receipt graph during atomic run-readiness evaluation."""
        from infra_automation.approval_eligibility import eligibility_from_reasons

        result = self._receipt_evidence(session, approval_id, phase=phase)
        if not result.eligible:
            return result
        try:
            row = repository.get_request(session, approval_id)
            run = runs.get_run(session, row.run_id)
            document = _document(run)
            binding = DecisionBinding.model_validate_json(row.binding_bytes)
            material, _ = self._material(
                session, run, document, row.step_id, binding, row.report_bytes
            )
            results, _ = self._eligibility(
                session,
                run,
                document,
                row.step_id,
                material,
                phase=phase,
                approval=row,
            )
            return eligibility_from_reasons(
                tuple(
                    dict.fromkeys(code for value in results for code in value.reasons)
                )
            )
        except authorization.TrustedAuthorizationError:
            return eligibility_from_reasons(("membership_revoked",))
        except LifecycleError as error:
            if error.status_code == 503:
                raise
            return eligibility_from_reasons(("binding_changed",))
        except (ValueError, TypeError):
            return eligibility_from_reasons(("binding_changed",))

    def recheck_approved(self, session, approval_id, *, phase="dispatch"):
        """Require a ready run before a consumer rechecks its approved receipt."""
        from infra_automation.approval_eligibility import eligibility_from_reasons

        authorization._require_operation(session)
        row = repository.get_request(session, support.identifier(approval_id))
        if row is None:
            return eligibility_from_reasons(("missing_approval",))
        run = runs.get_run(session, row.run_id)
        if run is None or run.state not in {
            "ready_handoff",
            "handing_off",
            "external_running",
        }:
            return eligibility_from_reasons(("prerequisite_unsuccessful",))
        return self._recheck_graph(session, approval_id, phase=phase)


def _view(row):
    from infra_automation.approval_eligibility import eligibility_from_reasons

    codes = ("missing_approval",)
    if row.status == "approved":
        codes = ("binding_changed",)
    if row.status in {"invalidated", "expired", "superseded"}:
        try:
            codes = tuple(json.loads(row.reason))
        except (ValueError, TypeError):
            codes = ("binding_changed",)
    elif row.status == "rejected":
        codes = ("policy_denied",)
    projection = eligibility_from_reasons(codes)
    binding = DecisionBinding.model_validate_json(row.binding_bytes)
    if (
        binding_digest(binding) != row.binding_digest
        or support.digest(row.report_bytes) != row.report_digest
        or binding.report_bytes_digest != row.report_digest
    ):
        raise LifecycleError(503)
    return support.bounded_payload(
        {
            "id": row.id,
            "run_id": row.run_id,
            "step_id": row.step_id,
            "project_id": row.project_id,
            "workspace_id": row.workspace_id,
            "requested_by": row.requested_by,
            "reviewer_id": row.reviewer_id,
            "decision_kind": row.decision_kind,
            "generation": row.generation,
            "version": row.version,
            "status": row.status,
            "reason": row.reason,
            "eligibility": projection.model_dump(mode="json"),
            "binding": binding.model_dump(mode="json"),
            "binding_digest": row.binding_digest,
            "deadline_at": support.utc(row.deadline_at),
            "created_at": support.utc(row.created_at),
            "decided_at": support.utc(row.decided_at) if row.decided_at else None,
        }
    )


def list_approvals(project_id, workspace_id=None, limit=25, cursor=None):
    from services.infra_automation_service import _binding, _page

    with authorization.authorized_session() as session:
        grant = support.scope(
            session, project_id, workspace_id, "automation.decision", mutation=False
        )
        return _page(
            binding=_binding(grant, workspace_id=workspace_id, family="approvals"),
            limit=limit,
            cursor=cursor,
            maximum=repository.max_sequence(session, project_id, workspace_id),
            fetch=lambda **values: repository.list_requests(
                session, project_id, workspace_id, **values
            ),
            render=_view,
        )


_default_service = DecisionService()


def request_decision(run_id, step_id):
    return _default_service.request_decision(run_id, step_id)


def decide(approval_id, request):
    return _default_service.decide(approval_id, request)
