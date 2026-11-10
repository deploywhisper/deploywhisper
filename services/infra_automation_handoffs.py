"""Transaction-owned durable handoff intent with distinct online receiver authority.

The default ports are unavailable. Scoped doubles qualify this contract without
claiming a production collector, delivery carrier, or receiver implementation.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import hmac
import json
from uuid import uuid4

from sqlalchemy import func, select

import config
from infra_automation import claims
from infra_automation.decisions import (
    DecisionBinding,
    binding_bytes,
    binding_digest,
    effective_deadline,
    utc_now,
    instant,
)
from infra_automation.handoff import (
    DeliveryEnvelope,
    DispatchHandoffRequest,
    PrepareHandoffRequest,
    ReceiverCredential,
)
from infra_automation.lifecycle import LifecycleError
from infra_automation.state import AuditActor
from infra_automation.receiver_protocol import (
    ReceiverBinding,
    ReceiverMessage,
    receiver_binding_bytes,
    receiver_binding_digest,
    receiver_binding_from_decision,
    receiver_message_bytes,
    validate_receiver_message,
)
from infra_automation.targets import (
    TargetSnapshot,
    canonical,
    checked,
    semantic_payload,
    target_snapshot_bytes,
)
from models.repositories import infra_automation_decisions as decisions
from models.repositories import infra_automation_handoffs as repository
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_targets as target_repository
from models.repositories import project_memberships
from models.repositories import infra_automation_workflows as workflows
from models.tables import AnalysisReport, IdentityAccount
from services import infra_automation_support as support
from services import infra_automation_targets as targets
from services import project_service as authorization
from services.infra_automation_decisions import DecisionService
from services.infra_automation_engine_service import _document
from services.infra_automation_policy import check_live_policy


def _retained_size(*records):
    """Count every retained raw copy plus canonical nonsecret scalar bookkeeping.

    Callers may reserve bounded future scalar values before their first write.
    Timestamp/verifier placeholders retain their final fixed canonical widths.
    No bearer is included.
    """
    total = 0
    for record in records:
        metadata = {}
        for key, value in record.items():
            if type(value) is bytes:
                total += len(value)
            else:
                metadata[key] = (
                    support.utc(value) if isinstance(value, datetime) else value
                )
        total += len(canonical(metadata))
    return total


def _message(row, *, operation="consume", state="consumed", sequence=1):
    return ReceiverMessage(
        operation=operation,
        operation_id=row.id,
        audience="receiver-operation-v1",
        binding=ReceiverBinding.model_validate_json(row.receiver_binding_bytes),
        binding_digest=row.receiver_binding_digest,
        sequence=sequence,
        state=state,
    )


def _grant_token(row, key_ref):
    """Deterministic bearer; only its domain-separated verifier is retained."""
    try:
        key = config.handoff_grant_key(key_ref)
    except (ValueError, TypeError):
        raise LifecycleError(503) from None
    facts = canonical(
        {
            "domain": "handoff-grant-v1",
            "operation_id": row.id,
            "receiver_id": row.receiver_id,
            "decision_binding_digest": row.decision_binding_digest,
            "receiver_binding_digest": row.receiver_binding_digest,
            "payload_digest": row.payload_digest,
            "expires_at": support.utc(row.deadline_at),
            "target_epoch": row.target_epoch,
            "authorization_epoch": row.authorization_epoch,
            "restore_epoch": row.restore_epoch,
        }
    )
    return "handoff-v1." + hmac.new(key, facts, hashlib.sha256).hexdigest()


def _receipt(grant):
    if grant.receipt_bytes is None:
        return None
    try:
        message = validate_receiver_message(grant.receipt_bytes)
        if (
            receiver_message_bytes(message) != grant.receipt_bytes
            or support.digest(grant.receipt_bytes) != grant.receipt_digest
            or message.operation != "receipt"
            or message.sequence != 1
            or message.state != "consumed"
        ):
            raise ValueError
        return message.model_dump(mode="json")
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def _view(row, grant):
    binding = DecisionBinding.model_validate_json(row.decision_binding_bytes)
    return support.bounded_payload(
        {
            "protocol_version": 1,
            "id": row.id,
            "version": row.version,
            "state": "delivery_unknown" if row.state == "sending" else row.state,
            "project_id": row.project_id,
            "workspace_id": row.workspace_id,
            "run_id": row.run_id,
            "handoff_step_id": row.step_id,
            "approval_id": row.approval_id,
            "target_id": row.target_id,
            "receiver_id": row.receiver_id,
            "authorization_kind": binding.authorization_kind,
            "decision_binding_digest": row.decision_binding_digest,
            "receiver_binding_digest": row.receiver_binding_digest,
            "payload_digest": row.payload_digest,
            "deadline_at": support.utc(row.deadline_at),
            "created_at": support.utc(row.created_at),
            "broken": row.broken,
            "consumed_at": support.utc(grant.consumed_at)
            if grant.consumed_at
            else None,
            "receipt": _receipt(grant),
            "outcome": _message(
                row, operation="outcome", state=row.state, sequence=2
            ).model_dump(mode="json")
            if row.state in {"succeeded", "failed"}
            else None,
        }
    )


class HandoffService:
    def __init__(
        self,
        *,
        decision_service=None,
        delivery_port=None,
        ref_port=None,
        clock=None,
        session_factory=None,
        observation_port=None,
    ):
        self.decision_service = decision_service or DecisionService()
        self.delivery_port = delivery_port
        self.ref_port = ref_port
        self.observation_port = observation_port
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.session_factory = session_factory

    def _now(self, *floors):
        try:
            value = utc_now(self.clock())
            if any(
                value
                < utc_now(
                    floor.replace(tzinfo=timezone.utc)
                    if floor.tzinfo is None
                    else floor
                )
                for floor in floors
            ):
                raise ValueError
            return value
        except (ValueError, TypeError, AttributeError):
            raise LifecycleError(503) from None

    def _load(self, session, operation_id):
        authorization._require_operation(session)
        row = repository.get_operation(session, support.identifier(operation_id))
        if row is None:
            raise authorization.TrustedAuthorizationError()
        grant = repository.get_grant(session, row.id)
        try:
            binding = DecisionBinding.model_validate_json(row.decision_binding_bytes)
            snapshot = checked(
                TargetSnapshot.model_validate_json(row.target_snapshot_bytes),
                TargetSnapshot,
            )
            wire = receiver_binding_from_decision(binding)
            approval = decisions.get_request(session, row.approval_id)
            if (
                grant is None
                or approval is None
                or binding_bytes(binding) != row.decision_binding_bytes
                or binding_digest(binding) != row.decision_binding_digest
                or approval.binding_bytes != row.decision_binding_bytes
                or approval.binding_digest != row.decision_binding_digest
                or (binding.project_id, binding.workspace_id)
                != (row.project_id, row.workspace_id)
                or receiver_binding_bytes(wire) != row.receiver_binding_bytes
                or receiver_binding_digest(wire) != row.receiver_binding_digest
                or semantic_payload(binding, snapshot) != row.payload_bytes
                or support.digest(row.payload_bytes) != row.payload_digest
                or binding.payload_digest != row.payload_digest
                or target_snapshot_bytes(snapshot) != row.target_snapshot_bytes
                or support.digest(row.target_snapshot_bytes)
                != row.target_snapshot_digest
                or snapshot.definition.canonical_target != row.target_id
                or snapshot.definition.receiver_id != row.receiver_id
                or snapshot.receiver_principal_id != row.receiver_principal_id
                or snapshot.target_epoch != row.target_epoch
                or (binding.authorization_epoch, binding.restore_epoch)
                != (row.authorization_epoch, row.restore_epoch)
                or grant.receiver_id != row.receiver_id
                or support.utc(grant.deadline_at) != support.utc(row.deadline_at)
            ):
                raise ValueError
            if grant.receipt_bytes is not None:
                receipt = validate_receiver_message(grant.receipt_bytes)
                if (
                    receipt.operation_id != row.id
                    or receiver_binding_bytes(receipt.binding)
                    != row.receiver_binding_bytes
                ):
                    raise ValueError
                _receipt(grant)
        except (ValueError, TypeError, AttributeError):
            raise LifecycleError(503) from None
        return row, grant, binding, snapshot

    def _scope(self, session, row, project_id, workspace_id, *, mutation):
        grant = support.scope(
            session,
            project_id,
            workspace_id,
            "automation.request" if mutation else "automation.read",
            mutation=mutation,
        )
        if (
            (row.project_id, row.workspace_id) != (project_id, workspace_id)
            or grant.principal.principal_type != "human"
            or grant.principal.credential_audience != "human"
        ):
            raise authorization.TrustedAuthorizationError()
        return grant

    def _receiver(
        self, session, row, snapshot, credential, *, reconciliation_only=False
    ):
        authorization._require_operation(session)
        if (
            type(credential) is not ReceiverCredential
            or type(credential.secret) is not str
            or not 1 <= len(credential.secret) <= 4096
            or any(ord(char) < 33 or ord(char) > 126 for char in credential.secret)
            or credential.audience != "receiver-operation-v1"
            or credential.receiver_id != row.receiver_id
        ):
            raise authorization.TrustedAuthorizationError()
        from services import infra_automation_receiver_recovery as recovery

        if recovery.is_recovery(credential):
            if not reconciliation_only:
                raise authorization.TrustedAuthorizationError()
            return recovery.authenticate(
                session,
                row,
                repository.get_grant(session, row.id),
                credential.secret,
                operation="status",
            )
        try:
            expected = config.handoff_credentials("receiver").get(
                snapshot.definition.receiver_credential_ref
            )
        except (ValueError, TypeError):
            raise LifecycleError(503) from None
        actor = session.get(
            IdentityAccount, row.receiver_principal_id, populate_existing=True
        )
        if (
            type(expected) is not str
            or not hmac.compare_digest(expected.encode(), credential.secret.encode())
            or actor is None
            or actor.principal_type != "service"
            or actor.is_admin
            or not actor.enabled
            or actor.authentication_version != snapshot.receiver_authentication_version
        ):
            raise authorization.TrustedAuthorizationError()
        return actor

    def _required_receipts(self, session, run, approval, handoff_step_id):
        """Resolve only the selected handoff's immutable mandatory human DAG."""
        if run is None or approval is None:
            raise LifecycleError(503)
        document = _document(run)
        nodes = {step.id: step for step in document.definition.steps}
        handoff = nodes.get(handoff_step_id)
        if (
            handoff is None
            or handoff.kind != "registered_github_handoff"
            or handoff.decision.step_id != approval.step_id
        ):
            raise LifecycleError(409)
        required = set()
        pending = [handoff.id]
        visited = set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            node = nodes.get(name)
            if node is None:
                raise LifecycleError(503)
            if node.kind == "human_decision":
                required.add(name)
            pending.extend(node.depends_on)
        latest = {
            receipt.step_id: decisions.get_request(session, receipt.id)
            for receipt in decisions.list_latest_for_run(session, run.id)
        }
        if any(receipt is None for receipt in latest.values()):
            raise LifecycleError(503)
        if (
            approval.step_id not in required
            or any(
                name not in latest or latest[name].status != "approved"
                for name in required
            )
            or latest[approval.step_id].id != approval.id
        ):
            raise LifecycleError(409)
        receipts = tuple(latest[name] for name in sorted(required))
        if any(
            (receipt.run_id, receipt.project_id, receipt.workspace_id)
            != (run.id, run.project_id, run.workspace_id)
            for receipt in receipts
        ):
            raise LifecycleError(503)
        return receipts

    def _authority_tail(self, session, run, approval, *, handoff_step_id, now):
        """No material/ref callbacks after these final graph/time/authority floors."""
        document = _document(run)
        check_live_policy(session, document.authority, "consume")
        receipts = self._required_receipts(session, run, approval, handoff_step_id)
        deadlines = [runs.utc(run.deadline_at)]
        for receipt in receipts:
            binding = DecisionBinding.model_validate_json(receipt.binding_bytes)
            if (
                binding_bytes(binding) != receipt.binding_bytes
                or binding_digest(binding) != receipt.binding_digest
                or support.digest(receipt.report_bytes) != binding.report_bytes_digest
                or (binding.project_id, binding.workspace_id)
                != (run.project_id, run.workspace_id)
            ):
                raise LifecycleError(503)
            floors = [runs.utc(run.last_observed_at), runs.utc(receipt.created_at)]
            if receipt.decided_at is not None:
                floors.append(runs.utc(receipt.decided_at))
            if now < max(floors):
                raise LifecycleError(503)
            deadline = min(effective_deadline(binding), runs.utc(receipt.deadline_at))
            deadlines.append(deadline)
            if now >= min(deadline, runs.utc(run.deadline_at)):
                raise LifecycleError(409)
            if receipt.decision_kind == "independent-approval":
                if (
                    receipt.reviewer_id == run.requested_by
                    or config.settings.identity_decision_mode != "shared"
                ):
                    raise LifecycleError(409)
            elif receipt.decision_kind == "acknowledgement":
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
                    raise LifecycleError(409)
            else:
                raise LifecycleError(409)
            actor = session.get(
                IdentityAccount, receipt.reviewer_id, populate_existing=True
            )
            member = project_memberships.get_membership(
                session, principal_id=receipt.reviewer_id, project_id=run.project_id
            )
            if (
                actor is None
                or member is None
                or not actor.enabled
                or actor.principal_type != "human"
                or not member.enabled
                or actor.authentication_version
                != receipt.reviewer_authentication_version
                or member.authorization_version
                != receipt.reviewer_authorization_version
                or member.workspace_id not in (None, run.workspace_id)
                or "automation.decision"
                not in authorization.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
            ):
                raise LifecycleError(409)
        if run.cancel_requested or run.state not in {
            "ready_handoff",
            "handing_off",
            "external_running",
        }:
            raise LifecycleError(409)
        return min(deadlines)

    def _live(self, session, row, *, credential=None):
        if row.broken:
            raise LifecycleError(409)
        capture, snapshot = targets.captured_target(session, row.run_id, row.step_id)
        if (
            capture.snapshot_bytes != row.target_snapshot_bytes
            or capture.snapshot_digest != row.target_snapshot_digest
        ):
            raise LifecycleError(409)
        context = nullcontext()
        if credential is not None:
            from infra_automation.handoff_context import _bind_receiver_report

            def reader(request_session, report_id):
                if request_session is not session:
                    raise authorization.TrustedAuthorizationError()
                self._receiver(session, row, snapshot, credential)
                approval = decisions.get_request(session, row.approval_id)
                if approval is None:
                    raise authorization.TrustedAuthorizationError()
                run = runs.get_run(session, row.run_id)
                if run is None:
                    raise authorization.TrustedAuthorizationError()
                receipts = self._required_receipts(session, run, approval, row.step_id)
                if report_id not in {receipt.report_id for receipt in receipts}:
                    raise authorization.TrustedAuthorizationError()
                report = session.get(AnalysisReport, report_id, populate_existing=True)
                if report is None or (report.project_id, report.workspace_id) != (
                    row.project_id,
                    row.workspace_id,
                ):
                    raise authorization.TrustedAuthorizationError()
                return report

            context = _bind_receiver_report(session, reader)
        # Ref lookup can invalidate material/custody while it runs. Resolve it
        # before the final material check, retaining receiver-scoped report reads.
        if self.ref_port is None:
            raise LifecycleError(503)
        if self.ref_port(snapshot) != snapshot.definition.pipeline_workflow_revision:
            raise LifecycleError(409)
        with context:
            result = self.decision_service.recheck_approved(
                session,
                row.approval_id,
                phase="consume" if credential is not None else "dispatch",
            )
        if not result.eligible:
            raise LifecycleError(409)
        # Ports can consume time or modify live facts in this same transaction.
        capture, current = targets.captured_target(session, row.run_id, row.step_id)
        if capture.snapshot_bytes != row.target_snapshot_bytes or current != snapshot:
            raise LifecycleError(409)
        if credential is not None:
            self._receiver(session, row, snapshot, credential)
        run = runs.get_run(session, row.run_id)
        target = target_repository.get_target(session, row.target_id)
        lock = target_repository.get_lock(session, capture.lock_id)
        if run is None or target is None or lock is None:
            raise LifecycleError(503)
        now = self._now(
            row.created_at,
            row.last_observed_at,
            run.last_observed_at,
            target.last_observed_at,
            lock.updated_at,
            instant(snapshot.captured_at),
        )
        self._authority_tail(
            session,
            run,
            decisions.get_request(session, row.approval_id),
            handoff_step_id=row.step_id,
            now=now,
        )
        if now >= min(runs.utc(row.deadline_at), runs.utc(run.deadline_at)):
            raise LifecycleError(409)
        return now

    def _state_digest(self, session, row):
        """Nonsecret operation/grant/outbox/lock state, independent of wire IDs."""
        grant = repository.get_grant(session, row.id)
        outbox = repository.get_outbox(session, row.id)
        capture = target_repository.get_run_target(session, row.run_id, row.step_id)
        lock = target_repository.get_lock(session, capture.lock_id) if capture else None
        if grant is None or outbox is None or lock is None:
            raise LifecycleError(503)
        return support.digest(
            canonical(
                {
                    "version": 1,
                    "operation": _view(row, grant),
                    "operation_state": row.state,
                    "last_observed_at": support.utc(row.last_observed_at),
                    "grant": {"status": grant.status, "version": grant.version},
                    "outbox": {"state": outbox.state, "version": outbox.version},
                    "lock": {
                        "id": lock.id,
                        "status": lock.status,
                        "version": lock.version,
                    },
                }
            )
        )

    def _audit(self, session, row, *, event, reason, human=None, before_digest=None):
        if event != "handoff_prepared" and before_digest is None:
            raise LifecycleError(503)
        after_digest = self._state_digest(session, row)
        if human is not None:
            support.append_audit(
                session,
                human,
                workspace_id=row.workspace_id,
                event_type=event,
                target_id=row.id,
                reason=reason,
                before_digest=before_digest,
                after_digest=after_digest,
            )
        else:
            workflows.append_audit(
                session,
                project_id=row.project_id,
                workspace_id=row.workspace_id,
                actor_principal_id=row.receiver_principal_id,
                actor_type="service",
                actor_role="coordinator",
                event_type=event,
                target_id=row.id,
                reason=reason,
                before_digest=before_digest,
                after_digest=after_digest,
            )

    def prepare(self, request: PrepareHandoffRequest) -> dict:
        request = checked(request, PrepareHandoffRequest)
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            human = support.scope(
                session,
                request.project_id,
                request.workspace_id,
                "automation.request",
                mutation=True,
            )
            if (
                human.principal.principal_type != "human"
                or human.principal.credential_audience != "human"
            ):
                raise authorization.TrustedAuthorizationError()
            support.screened_label(request.reason)
            key_digest = support.digest(
                canonical(
                    {"operation": "prepare-handoff", "key": request.idempotency_key}
                )
            )
            request_digest = support.digest(canonical(request))
            existing = repository.by_key(
                session,
                request.project_id,
                request.workspace_id,
                human.principal.principal_id,
                key_digest,
            )
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise LifecycleError(409)
                row, grant, _, _ = self._load(session, existing.id)
                return _view(row, grant)
            approval = decisions.get_request(session, request.approval_id)
            if approval is None or (approval.project_id, approval.workspace_id) != (
                request.project_id,
                request.workspace_id,
            ):
                raise authorization.TrustedAuthorizationError()
            if repository.by_approval(session, approval.id) is not None:
                raise LifecycleError(409)
            if (
                repository.by_run_step(
                    session, approval.run_id, request.handoff_step_id
                )
                is not None
            ):
                raise LifecycleError(409)
            run = runs.get_run(session, approval.run_id)
            if run is None:
                raise LifecycleError(503)
            document = _document(run)
            step = next(
                (
                    step
                    for step in document.definition.steps
                    if step.id == request.handoff_step_id
                ),
                None,
            )
            if (
                step is None
                or step.kind != "registered_github_handoff"
                or step.decision.step_id != approval.step_id
            ):
                raise LifecycleError(409)
            capture, snapshot = targets.captured_target(session, run.id, step.id)
            binding = DecisionBinding.model_validate_json(approval.binding_bytes)
            payload = semantic_payload(binding, snapshot)
            if (
                binding_digest(binding) != approval.binding_digest
                or binding_bytes(binding) != approval.binding_bytes
                or support.digest(payload) != binding.payload_digest
            ):
                raise LifecycleError(409)
            if self.ref_port is None:
                raise LifecycleError(503)
            if (
                self.ref_port(snapshot)
                != snapshot.definition.pipeline_workflow_revision
            ):
                raise LifecycleError(409)
            run = runs.get_run(session, run.id)
            if run is None:
                raise LifecycleError(503)
            charge_now = self._now(run.last_observed_at)
            provisional_deadline = min(
                effective_deadline(binding), runs.utc(run.deadline_at)
            ).replace(microsecond=0)
            operation_id = uuid4().hex
            wire = receiver_binding_from_decision(binding)
            operation_values = dict(
                id=operation_id,
                run_id=run.id,
                step_id=step.id,
                approval_id=approval.id,
                project_id=run.project_id,
                workspace_id=run.workspace_id,
                target_id=capture.target_id,
                receiver_id=binding.receiver_id,
                receiver_principal_id=snapshot.receiver_principal_id,
                prepared_by=human.principal.principal_id,
                key_digest=key_digest,
                request_digest=request_digest,
                decision_binding_bytes=approval.binding_bytes,
                decision_binding_digest=approval.binding_digest,
                receiver_binding_bytes=receiver_binding_bytes(wire),
                receiver_binding_digest=receiver_binding_digest(wire),
                payload_bytes=payload,
                payload_digest=binding.payload_digest,
                target_snapshot_bytes=capture.snapshot_bytes,
                target_snapshot_digest=capture.snapshot_digest,
                target_epoch=snapshot.target_epoch,
                authorization_epoch=binding.authorization_epoch,
                restore_epoch=binding.restore_epoch,
                deadline_at=provisional_deadline,
                created_at=charge_now,
                last_observed_at=charge_now,
                version=1,
                state="prepared",
                broken=False,
            )
            outbox_values = dict(
                operation_id=operation_id,
                version=1,
                state="pending",
                attempted_at=None,
                updated_at=charge_now,
            )
            grant_values = dict(
                id=uuid4().hex,
                operation_id=operation_id,
                verifier_digest="sha256:" + "0" * 64,
                key_ref="handoff-v1",
                receiver_id=binding.receiver_id,
                deadline_at=provisional_deadline,
                created_at=charge_now,
                status="available",
                version=1,
                consumed_at=None,
                receipt_bytes=None,
                receipt_digest=None,
            )
            # Reserve all future scalar growth before authority exists. Keep
            # these bounds aligned with the state vocabulary and SQLite's signed
            # 64-bit counters. Only raw receipt bytes need charging at consume.
            maximum_version = 2**63 - 1
            claims._charge(
                session,
                run,
                _retained_size(
                    {
                        **operation_values,
                        "version": maximum_version,
                        "state": "delivery_unknown",
                    },
                    {
                        **outbox_values,
                        "version": maximum_version,
                        "state": "delivery_unknown",
                        "attempted_at": charge_now,
                    },
                    {
                        **grant_values,
                        "version": maximum_version,
                        "status": "invalidated",
                        "consumed_at": charge_now,
                        "receipt_digest": "sha256:" + "0" * 64,
                    },
                ),
                charge_now,
            )
            # Both ref lookup and the capacity probe can change live material.
            # Final target/human/clock floors must follow these material callbacks.
            if not self.decision_service.recheck_approved(
                session, approval.id, phase="dispatch"
            ).eligible:
                raise LifecycleError(409)
            current_capture, current_snapshot = targets.captured_target(
                session, run.id, step.id
            )
            if (
                current_capture.snapshot_bytes != capture.snapshot_bytes
                or current_snapshot != snapshot
            ):
                raise LifecycleError(409)
            # Ports may issue SQL with identity-map synchronization disabled.
            run = runs.get_run(session, run.id)
            approval = decisions.get_request(session, approval.id)
            target = target_repository.get_target(session, capture.target_id)
            lock = target_repository.get_lock(session, capture.lock_id)
            if run is None or approval is None or target is None or lock is None:
                raise LifecycleError(503)
            # Human/session/policy checks remain fresh after trusted callbacks.
            human = support.scope(
                session,
                request.project_id,
                request.workspace_id,
                "automation.request",
                mutation=True,
            )
            now = self._now(
                run.last_observed_at,
                approval.created_at,
                approval.decided_at,
                capture.created_at,
                target.last_observed_at,
                lock.updated_at,
                instant(snapshot.captured_at),
            )
            deadline = self._authority_tail(
                session, run, approval, handoff_step_id=step.id, now=now
            ).replace(microsecond=0)
            # Public expiry and HMAC facts use UTC seconds. Round the hard
            # minimum down before checking or retaining it, never extending it.
            if now >= deadline:
                raise LifecycleError(409)
            operation_values.update(
                deadline_at=deadline, created_at=now, last_observed_at=now
            )
            outbox_values.update(updated_at=now)
            grant_values.update(deadline_at=deadline, created_at=now)
            row = repository.create_operation(session, **operation_values)
            repository.create_outbox(session, **outbox_values)
            token = _grant_token(row, "handoff-v1")
            grant_values["verifier_digest"] = support.digest(token.encode())
            grant = repository.create_grant(session, **grant_values)
            self._audit(
                session,
                row,
                event="handoff_prepared",
                reason=request.reason,
                human=human,
            )
            return _view(row, grant)

    def get_operation(self, operation_id, project_id, workspace_id) -> dict:
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, _ = self._load(session, operation_id)
            self._scope(session, row, project_id, workspace_id, mutation=False)
            return _view(row, grant)

    def dispatch(self, operation_id, request: DispatchHandoffRequest) -> dict:
        request = checked(request, DispatchHandoffRequest)
        # A caller-owned transaction cannot release its lock for the port call.
        if authorization.has_authorized_session():
            raise LifecycleError(503)
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, operation_id)
            human = self._scope(
                session, row, request.project_id, request.workspace_id, mutation=True
            )
            support.screened_label(request.reason)
            if (
                row.state != "prepared"
                or row.version != request.expected_version
                or grant.status != "available"
            ):
                raise LifecycleError(409)
            if self.delivery_port is None:
                raise LifecycleError(503)
            now = self._live(session, row)
            token = _grant_token(row, grant.key_ref)
            if not hmac.compare_digest(
                support.digest(token.encode()), grant.verifier_digest
            ):
                raise LifecycleError(503)
            try:
                credential = config.handoff_credentials("dispatch").get(
                    snapshot.definition.credential_ref
                )
            except (ValueError, TypeError):
                raise LifecycleError(503) from None
            if type(credential) is not str or not credential:
                raise LifecycleError(503)
            envelope = DeliveryEnvelope(
                row.id, row.payload_bytes, receiver_message_bytes(_message(row)), token
            )
            human = self._scope(
                session, row, request.project_id, request.workspace_id, mutation=True
            )
            before_digest = self._state_digest(session, row)
            run = runs.get_run(session, row.run_id)
            if run is None:
                raise LifecycleError(503)
            if run.state == "ready_handoff":
                run = runs.transition_run(
                    session,
                    run_id=run.id,
                    expected_version=run.version,
                    state="handing_off",
                    audit_actor=AuditActor(
                        human.principal.principal_id, "human", human.role
                    ),
                    reason="Committed possible external handoff before delivery",
                    now=now,
                )
                if run is None:
                    raise LifecycleError(409)
            elif run.state not in {"handing_off", "external_running"}:
                raise LifecycleError(409)
            if not run.external_possible:
                raise LifecycleError(503)
            row = repository.transition(session, row, state="sending", now=now)
            outbox = repository.get_outbox(session, row.id)
            if outbox is None or outbox.state != "pending":
                raise LifecycleError(409)
            repository.transition_outbox(session, outbox, state="sending", now=now)
            self._audit(
                session,
                row,
                event="handoff_dispatch_claimed",
                reason=request.reason,
                human=human,
                before_digest=before_digest,
            )
        acceptance = None
        try:
            acceptance = self.delivery_port(envelope, credential)
        except Exception:
            # Even a purported definite failure cannot undo possible delivery.
            pass
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, operation_id)
            now = self._now(row.last_observed_at)
            if acceptance is not None:
                from infra_automation.github_contracts import DispatchAcceptance
                from infra_automation import reconciliation

                try:
                    accepted = checked(acceptance, DispatchAcceptance)
                    self._check_carrier(row, snapshot, accepted)
                except (ValueError, TypeError):
                    accepted = None
                if accepted is not None:
                    reconciliation.retain(
                        session,
                        row,
                        "acceptance",
                        accepted.model_dump(mode="json"),
                        now,
                    )
            before_digest = self._state_digest(session, row)
            changed = False
            if row.state == "sending" and not row.broken:
                row = repository.transition(
                    session, row, state="delivery_unknown", now=now
                )
                changed = True
            outbox = repository.get_outbox(session, row.id)
            if outbox.state == "sending":
                repository.transition_outbox(
                    session, outbox, state="delivery_unknown", now=now
                )
                changed = True
            if changed:
                self._audit(
                    session,
                    row,
                    event="handoff_delivery_observed",
                    reason="Delivery remains uncertain until receiver records consumption",
                    human=human,
                    before_digest=before_digest,
                )
        # Commit uncertainty before checking the caller's current read authority.
        # Revocation cannot roll back intent, and an old grant cannot expose the
        # protected result after the independent delivery transaction finishes.
        return self.get_operation(
            operation_id, request.project_id, request.workspace_id
        )

    def consume(self, message, grant_token, credential: ReceiverCredential) -> dict:
        try:
            message = validate_receiver_message(message)
        except (ValueError, TypeError):
            raise LifecycleError(422) from None
        if (
            message.operation != "consume"
            or message.state != "consumed"
            or message.sequence != 1
        ):
            raise LifecycleError(409)
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, message.operation_id)
            self._receiver(session, row, snapshot, credential)
            if (
                row.state not in {"sending", "delivery_unknown"}
                or grant.status != "available"
                or receiver_message_bytes(message)
                != receiver_message_bytes(_message(row))
            ):
                raise LifecycleError(409)
            if (
                type(grant_token) is not str
                or not 1 <= len(grant_token) <= 256
                or any(ord(char) < 33 or ord(char) > 126 for char in grant_token)
            ):
                raise authorization.TrustedAuthorizationError()
            token = _grant_token(row, grant.key_ref)
            if not hmac.compare_digest(
                support.digest(token.encode()), grant.verifier_digest
            ):
                raise LifecycleError(503)
            if not hmac.compare_digest(token.encode(), grant_token.encode()):
                raise authorization.TrustedAuthorizationError()
            raw = receiver_message_bytes(_message(row, operation="receipt"))
            run = runs.get_run(session, row.run_id)
            if run is None:
                raise LifecycleError(503)
            claims._charge(
                session,
                run,
                len(raw),
                self._now(row.last_observed_at, run.last_observed_at),
            )
            now = self._live(session, row, credential=credential)
            before_digest = self._state_digest(session, row)
            grant = repository.consume_grant(
                session,
                grant,
                receipt_bytes=raw,
                receipt_digest=support.digest(raw),
                now=now,
            )
            row = repository.transition(session, row, state="consumed", now=now)
            run = runs.get_run(session, row.run_id)
            if run is None:
                raise LifecycleError(503)
            if run.state == "handing_off":
                run = runs.transition_run(
                    session,
                    run_id=run.id,
                    expected_version=run.version,
                    state="external_running",
                    audit_actor=AuditActor(
                        row.receiver_principal_id, "service", "coordinator"
                    ),
                    reason="Receiver durably consumed approved external operation",
                    now=now,
                )
                if run is None:
                    raise LifecycleError(409)
            elif run.state != "external_running":
                raise LifecycleError(409)
            if not run.external_possible:
                raise LifecycleError(503)
            self._audit(
                session,
                row,
                event="handoff_consumed",
                reason="Receiver consumed approved operation",
                before_digest=before_digest,
            )
            return _view(row, grant)

    def receiver_status(
        self, operation_or_message, credential: ReceiverCredential
    ) -> dict:
        message = None
        if type(
            operation_or_message
        ) is str and not operation_or_message.lstrip().startswith("{"):
            operation_id = support.identifier(operation_or_message)
        else:
            try:
                message = validate_receiver_message(operation_or_message)
            except (ValueError, TypeError):
                raise LifecycleError(422) from None
            if message.operation != "status":
                raise LifecycleError(409)
            operation_id = message.operation_id
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, operation_id)
            self._receiver(session, row, snapshot, credential, reconciliation_only=True)
            if (
                message is not None
                and receiver_binding_bytes(message.binding)
                != row.receiver_binding_bytes
            ):
                raise LifecycleError(409)
            view = _view(row, grant)
            from infra_automation.reconciliation import facts

            callbacks = facts(session, row.id, "callback")
            if callbacks:
                latest = callbacks[-1]
                view["callback_ack"] = {
                    "sequence": latest.sequence,
                    "nonce": latest.nonce,
                    "envelope_digest": support.digest(latest.payload_bytes),
                }
            from services import infra_automation_receiver_recovery as recovery

            if recovery.is_recovery(credential):
                recovery.authenticate(
                    session, row, grant, credential.secret, operation="status"
                )
            return view

    def authorize_action(self, operation_id, credential: ReceiverCredential) -> dict:
        """Repeatable online deny check; receiver-owned durable action fencing is separate.

        The caller must fence its action with a durable operation/binding ledger.
        This method provides no exactly-once execution guarantee. Real receiver
        durability belongs to16.11.
        """
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, operation_id)
            self._receiver(session, row, snapshot, credential)
            from infra_automation.reconciliation import callback_states

            if callback_states(session, row.id) & {
                "running",
                "delivery_unknown",
                "cancel_requested",
                "succeeded",
                "failed",
            }:
                raise LifecycleError(409)
            if row.state not in {"consumed", "accepted"} or grant.status != "consumed":
                raise LifecycleError(409)
            now = self._live(session, row, credential=credential)
            if now > runs.utc(row.last_observed_at):
                before_digest = self._state_digest(session, row)
                row = repository.transition(session, row, state=row.state, now=now)
                self._audit(
                    session,
                    row,
                    event="handoff_action_checked",
                    reason="Retained current receiver action admission clock floor",
                    before_digest=before_digest,
                )
            return _view(row, grant)

    def resolve_terminal(self, message, credential: ReceiverCredential) -> dict:
        """Scoped receiver proof only; sequenced HTTP controller belongs to16.11."""
        try:
            message = validate_receiver_message(message)
        except (ValueError, TypeError):
            raise LifecycleError(422) from None
        if (
            message.operation != "outcome"
            or message.sequence != 2
            or message.state not in {"succeeded", "failed"}
        ):
            raise LifecycleError(409)
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, message.operation_id)
            self._receiver(session, row, snapshot, credential)
            return self._resolve_terminal_verified(session, row, grant, message)

    def _resolve_terminal_verified(
        self, session, row, grant, message, *, recovery_auth=None
    ):
        if (
            row.broken
            or grant.status != "consumed"
            or row.state not in {"consumed", "accepted", "running", "delivery_unknown"}
            or receiver_message_bytes(message)
            != receiver_message_bytes(
                _message(row, operation="outcome", state=message.state, sequence=2)
            )
        ):
            raise LifecycleError(409)
        capture, _ = targets.captured_target(
            session, row.run_id, row.step_id, live=False
        )
        lock = target_repository.get_lock(session, capture.lock_id)
        if lock is None or lock.status != "held" or lock.run_id != row.run_id:
            raise LifecycleError(409)
        parent = runs.get_run(session, row.run_id)
        if parent is None:
            raise LifecycleError(503)
        now = self._now(
            row.last_observed_at,
            grant.consumed_at,
            lock.updated_at,
            parent.last_observed_at,
        )
        before_digest = self._state_digest(session, row)
        row = repository.transition(session, row, state=message.state, now=now)
        outbox = repository.get_outbox(session, row.id)
        if outbox.state in {"sending", "delivery_unknown"}:
            repository.transition_outbox(session, outbox, state="delivered", now=now)
        operations = [
            repository.by_run_step(session, capture.run_id, capture.handoff_step_id)
            for capture in target_repository.list_run_targets(session, row.run_id)
            if capture.lock_id == lock.id
        ]
        if operations and all(
            operation is not None
            and operation.state in {"succeeded", "failed"}
            and not operation.broken
            for operation in operations
        ):
            if (
                target_repository.resolve_lock(
                    session,
                    lock_id=lock.id,
                    expected_version=lock.version,
                    status="resolved",
                    reason="Verified terminal receiver outcome",
                    now=now,
                )
                is None
            ):
                raise LifecycleError(409)
        from infra_automation.reconciliation import reconcile_parent

        reconcile_parent(session, row, now)
        self._audit(
            session,
            row,
            event="handoff_recovery_terminal_verified"
            if recovery_auth is not None
            else "handoff_terminal_verified",
            reason=(
                f"Recovery-authenticated terminal outcome; issuer {recovery_auth.issuer_id}; generation {recovery_auth.generation}"
                if recovery_auth is not None
                else "Verified sequenced receiver terminal outcome"
            ),
            before_digest=before_digest,
        )
        return _view(row, grant)

    @staticmethod
    def _check_carrier(row, snapshot, fact):
        definition = snapshot.definition
        if (
            fact.repository_id,
            fact.workflow_id,
            fact.workflow_revision,
            fact.workflow_ref,
        ) != (
            definition.pipeline_repository_id,
            definition.pipeline_workflow_id,
            definition.pipeline_workflow_revision,
            definition.workflow_ref,
        ):
            raise ValueError("Carrier identity mismatch")
        if hasattr(fact, "operation_id") and (
            fact.operation_id != row.id
            or fact.binding_digest != row.receiver_binding_digest
        ):
            raise ValueError("Carrier binding mismatch")

    def bootstrap(self, operation_id, binding_digest, credential):
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, operation_id)
            self._receiver(session, row, snapshot, credential)
            if (
                row.receiver_binding_digest != binding_digest
                or grant.status != "available"
                or row.state not in {"sending", "delivery_unknown"}
            ):
                raise LifecycleError(409)
            self._live(session, row, credential=credential)
            token = _grant_token(row, grant.key_ref)
            if not hmac.compare_digest(
                support.digest(token.encode()), grant.verifier_digest
            ):
                raise LifecycleError(503)
            return {
                "message": _message(row).model_dump(mode="json"),
                "payload": json.loads(row.payload_bytes),
                "grant_token": token,
                "run_id": row.run_id,
            }

    def callback(self, envelope, credential):
        from infra_automation.receiver_http_contracts import (
            CallbackEnvelope,
            callback_signing_bytes,
            source_identity_digest,
        )
        from infra_automation import reconciliation

        envelope = checked(envelope, CallbackEnvelope)
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, grant, _, snapshot = self._load(session, envelope.operation_id)
            from services import infra_automation_receiver_recovery as recovery

            recovery_auth = None
            if recovery.is_recovery(credential):
                if (
                    envelope.message.operation != "outcome"
                    or envelope.message.state not in {"succeeded", "failed"}
                ):
                    raise authorization.TrustedAuthorizationError()
                self._receiver(
                    session, row, snapshot, credential, reconciliation_only=True
                )
                recovery_auth = recovery.authenticate(
                    session, row, grant, credential.secret, operation="terminal"
                )
            else:
                self._receiver(session, row, snapshot, credential)
            expected = (
                "sha256:"
                + hmac.new(
                    credential.secret.encode(),
                    callback_signing_bytes(envelope),
                    hashlib.sha256,
                ).hexdigest()
            )
            message = envelope.message
            if not hmac.compare_digest(expected, envelope.signature):
                raise authorization.TrustedAuthorizationError()
            if (
                envelope.run_id != row.run_id
                or envelope.binding_digest != row.receiver_binding_digest
                or envelope.source_identity_digest
                != source_identity_digest(message.binding)
                or message.operation_id != row.id
                or receiver_binding_bytes(message.binding) != row.receiver_binding_bytes
                or grant.status != "consumed"
                or row.broken
            ):
                raise LifecycleError(409)
            if row.state in {"succeeded", "failed", "cancelled"}:
                raise LifecycleError(409)
            parent = runs.get_run(session, row.run_id)
            if parent is None:
                raise LifecycleError(503)
            now = self._now(
                row.last_observed_at, grant.consumed_at, parent.last_observed_at
            )
            prior_states = reconciliation.callback_states(session, row.id)
            if message.state in {"accepted", "running"} and prior_states & {
                "delivery_unknown",
                "cancel_requested",
            }:
                raise LifecycleError(409)
            if message.state == "accepted" and "running" in prior_states:
                raise LifecycleError(409)
            if recovery_auth is not None:
                current_auth = recovery.authenticate(
                    session, row, grant, credential.secret, operation="terminal"
                )
                if current_auth != recovery_auth:
                    raise LifecycleError(409)
            reconciliation.retain(
                session,
                row,
                "callback",
                envelope.model_dump(mode="json"),
                now,
                sequence=envelope.sequence,
                nonce=envelope.nonce,
            )
            if message.state in {"succeeded", "failed"}:
                if message.operation != "outcome" or message.sequence != 2:
                    raise LifecycleError(409)
                if recovery_auth is not None:
                    current_auth = recovery.authenticate(
                        session, row, grant, credential.secret, operation="terminal"
                    )
                    if current_auth != recovery_auth:
                        raise LifecycleError(409)
                    result = self._resolve_terminal_verified(
                        session, row, grant, message, recovery_auth=recovery_auth
                    )
                    final_auth = recovery.authenticate(
                        session, row, grant, credential.secret, operation="status"
                    )
                    if final_auth != recovery_auth:
                        raise LifecycleError(409)
                    return result
                return self.resolve_terminal(message, credential)
            if message.operation not in {"status", "outcome"} or message.state not in {
                "accepted",
                "running",
                "delivery_unknown",
                "cancel_requested",
            }:
                raise LifecycleError(409)
            if message.state == "accepted" and row.state not in {
                "consumed",
                "accepted",
                "delivery_unknown",
            }:
                raise LifecycleError(409)
            state = (
                message.state if message.state in {"accepted", "running"} else row.state
            )
            before = self._state_digest(session, row)
            row = repository.transition(session, row, state=state, now=now)
            self._audit(
                session,
                row,
                event="handoff_receiver_observed",
                reason="Verified receiver progress; external outcome remains unconfirmed",
                before_digest=before,
            )
            return _view(row, grant)

    def _projection(self, session, row):
        from infra_automation import reconciliation

        capture, _ = targets.captured_target(
            session, row.run_id, row.step_id, live=False
        )
        lock = target_repository.get_lock(session, capture.lock_id)
        callback = reconciliation.latest(session, row.id, "callback")
        run = runs.get_run(session, row.run_id)
        return {
            "id": row.id,
            "version": row.version,
            "state": "delivery_unknown" if row.state == "sending" else row.state,
            "acceptance": reconciliation.latest(session, row.id, "acceptance"),
            "observation": reconciliation.latest(session, row.id, "observation"),
            "receiver_state": callback["message"]["state"] if callback else None,
            "lock_status": lock.status,
            "cancel_requested": run.cancel_requested,
            "verified_outcome": row.state
            if row.state in {"succeeded", "failed"}
            and callback is not None
            and callback["message"]["state"] == row.state
            else None,
            "reconciliation_available": self.observation_port is not None
            and reconciliation.latest(session, row.id, "acceptance") is not None,
        }

    def list_for_run(self, run_id, project_id, workspace_id):
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            run = runs.get_run(session, support.identifier(run_id))
            support.scope(
                session, project_id, workspace_id, "automation.read", mutation=False
            )
            if run is None or (run.project_id, run.workspace_id) != (
                project_id,
                workspace_id,
            ):
                raise authorization.TrustedAuthorizationError()
            items = []
            for capture in target_repository.list_run_targets(session, run_id):
                row = repository.by_run_step(session, run_id, capture.handoff_step_id)
                if row is not None:
                    self._scope(session, row, project_id, workspace_id, mutation=False)
                    items.append(self._projection(session, row))
            if len(items) > 50:
                raise LifecycleError(503)
            return dict(
                version=1,
                run_id=run_id,
                project_id=project_id,
                workspace_id=workspace_id,
                items=items,
            )

    def reconcile(self, operation_id, request):
        from infra_automation.receiver_http_contracts import ReconcileRequest
        from infra_automation.github_contracts import (
            GithubRunObservation,
            DispatchAcceptance,
        )
        from infra_automation import reconciliation

        request = checked(request, ReconcileRequest)
        if authorization.has_authorized_session():
            raise LifecycleError(503)
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, _, _, snapshot = self._load(session, operation_id)
            self._scope(
                session, row, request.project_id, request.workspace_id, mutation=True
            )
            support.screened_label(request.reason)
            if row.version != request.expected_version:
                raise LifecycleError(409)
            acceptance = reconciliation.latest(session, row.id, "acceptance")
            if self.observation_port is None or acceptance is None:
                raise LifecycleError(503)
            acceptance = DispatchAcceptance.model_validate(acceptance)
        try:
            observation = checked(
                self.observation_port(acceptance, snapshot), GithubRunObservation
            )
            self._check_carrier(row, snapshot, observation)
            if observation.run_id != acceptance.run_id:
                raise ValueError
        except Exception:
            raise LifecycleError(503) from None
        with authorization.authorized_session(
            session_factory=self.session_factory
        ) as session:
            row, _, _, _ = self._load(session, operation_id)
            human = self._scope(
                session, row, request.project_id, request.workspace_id, mutation=True
            )
            if row.version != request.expected_version:
                raise LifecycleError(409)
            now = self._now(row.last_observed_at)
            before = self._state_digest(session, row)
            reconciliation.retain(
                session, row, "observation", observation.model_dump(mode="json"), now
            )
            row = repository.transition(session, row, state=row.state, now=now)
            self._audit(
                session,
                row,
                event="handoff_carrier_observed",
                reason=request.reason,
                human=human,
                before_digest=before,
            )
            return self._projection(session, row)


_default_service = HandoffService()


def prepare(request):
    return _default_service.prepare(request)


def get_operation(operation_id, project_id, workspace_id):
    return _default_service.get_operation(operation_id, project_id, workspace_id)


def dispatch(operation_id, request):
    return _default_service.dispatch(operation_id, request)
