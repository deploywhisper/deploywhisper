"""Scoped doubles prove durable handoff admission, not a production receiver."""

from __future__ import annotations

from dataclasses import replace
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module
import json
from unittest.mock import patch

from sqlalchemy import select

import config
from infra_automation.decisions import binding_digest
from infra_automation.lifecycle import LifecycleError
from infra_automation.run_resolution import resolve_target_value
from infra_automation.targets import (
    TargetDefinition,
    TargetSnapshot,
    semantic_payload,
    target_definition_bytes,
    target_snapshot_bytes,
)
from models.repositories import infra_automation_targets as registry
from models.tables import (
    InfraAutomationGrant,
    InfraAutomationHandoff,
    InfraAutomationOutbox,
)
from services import infra_automation_support as support
from services import project_service as auth
from services.infra_automation_decisions import DecisionRequest
from tests.test_infra_automation import test_decision_service as fixture
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class HandoffServiceTests(LifecycleCase):
    enable = fixture.DecisionServiceTests.enable
    publish_fixture = fixture.DecisionServiceTests.publish_fixture

    def setUp(self):
        fixture.DecisionServiceTests.setUp(self)
        self.member("admin", project=200)
        self.principal(
            "receiver-actor", principal_type="service", audience="receiver-operation-v1"
        )
        self.sent = []
        for name, value in (
            ("handoff_grant_key", b"g" * 32),
            (
                "handoff_credentials",
                {"receiver": "receiver-secret", "github": "dispatch-secret"},
            ),
        ):
            context = patch("config." + name, return_value=value)
            context.start()
            self.addCleanup(context.stop)
        binding = self.material.binding
        definition = TargetDefinition.model_validate_json(
            json.dumps(
                dict(
                    canonical_target=binding.canonical_target,
                    aliases=getattr(self, "target_aliases", ()),
                    allowed_scopes=[dict(project_id=100, workspace_id=100)],
                    environment=binding.environment,
                    receiver_id=binding.receiver_id,
                    pipeline_repository_id=binding.pipeline_repository_id,
                    pipeline_workflow_id=binding.pipeline_workflow_id,
                    pipeline_workflow_revision=binding.pipeline_workflow_revision,
                    github_owner="owner",
                    github_repository="repository",
                    github_workflow="deploy.yml",
                    workflow_ref="main",
                    credential_ref="github",
                    receiver_credential_ref="receiver",
                )
            )
        )
        self.snapshot = TargetSnapshot(
            definition=definition,
            target_version=1,
            target_epoch=1,
            receiver_principal_id="receiver-actor",
            receiver_authentication_version=1,
            captured_at=support.utc(self.now),
        )
        raw = target_snapshot_bytes(self.snapshot)
        with self.factory.begin() as db:
            registry.create_target(
                db,
                target_id=definition.canonical_target,
                definition_bytes=target_definition_bytes(definition),
                definition_digest=support.digest(target_definition_bytes(definition)),
                enabled=True,
                receiver_principal_id="receiver-actor",
                created_by="human-a",
                aliases=definition.aliases,
                scopes=[(100, 100)],
                now=self.now,
            )
            registry.acquire_lock(
                db,
                lock_id="held-lock",
                target_id=definition.canonical_target,
                run_id=self.run.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
            registry.capture_run_target(
                db,
                run_id=self.run.id,
                handoff_step_id="handoff",
                project_id=100,
                workspace_id=100,
                target_id=definition.canonical_target,
                target_epoch=1,
                requested_alias=resolve_target_value(
                    self.document,
                    next(
                        step.target_id
                        for step in self.document.definition.steps
                        if step.id == "handoff"
                    ),
                ),
                lock_id="held-lock",
                snapshot_bytes=raw,
                snapshot_digest=support.digest(raw),
                now=self.now,
            )
            from infra_automation.run_resolution import runtime_workflow
            from infra_automation.state import OutputReference
            from models.repositories import infra_automation_runs as run_repository
            from models.tables import InfraAutomationReportLink
            from services.infra_automation_policy_worker import policy_output_digest

            gate = next(
                step
                for step in runtime_workflow(self.document).steps
                if step.id == "gate"
            )
            link = db.get(InfraAutomationReportLink, "link")
            policy, settings = support.policy_state(db, 100)
            output = OutputReference(
                kind="action_binding",
                reference=link.id,
                digest=policy_output_digest(
                    self.run,
                    self.document,
                    gate,
                    link,
                    policy,
                    settings,
                    self.snapshot,
                ),
            ).model_dump(mode="json")
            attempt = next(
                item
                for item in run_repository.list_attempts(db, run_id=self.run.id)
                if item.step_id == "gate"
            )
            attempt.output_json = support.canonical(output).decode()
            attempt.output_digest = support.digest(attempt.output_json.encode())
        binding = binding.model_copy(
            update={
                "payload_digest": support.digest(
                    semantic_payload(binding, self.snapshot)
                )
            }
        )
        digest = binding_digest(binding)
        self.material = replace(
            self.material,
            binding=binding,
            live=self.material.live.model_copy(
                update={"expected_tuple_digest": digest, "current_tuple_digest": digest}
            ),
        )
        reviewer_id = "reviewer"
        if getattr(self, "acknowledgement", False):
            context = patch(
                "config.settings",
                replace(config.settings, identity_decision_mode="single-operator"),
            )
            context.start()
            self.addCleanup(context.stop)
            from models.tables import IdentityAccount

            with self.factory.begin() as db:
                db.get(IdentityAccount, "reviewer").enabled = False
            reviewer_id = "human-a"
        if getattr(self, "serial_decisions", False):
            ancestor_deadline = self.now + timedelta(minutes=2)
            ancestor_binding = binding.model_copy(
                update={"approval_deadline": support.utc(ancestor_deadline)}
            )
            ancestor_evidence = self.material.evidence
            if hasattr(self, "seed_ancestor_report"):
                ancestor_binding, ancestor_evidence = self.seed_ancestor_report(
                    ancestor_binding
                )
            ancestor_digest = binding_digest(ancestor_binding)
            self.ancestor_material = replace(
                self.material,
                binding=ancestor_binding,
                evidence=ancestor_evidence,
                live=self.material.live.model_copy(
                    update={
                        "approval_deadline": ancestor_deadline,
                        "expected_tuple_digest": ancestor_digest,
                        "current_tuple_digest": ancestor_digest,
                    }
                ),
            )
            self.service.material_port = lambda session, run, step, previous: (
                self.ancestor_material if step == "decision-a" else self.material
            )
            with self.credentials():
                ancestor = self.service.request_decision(self.run.id, "decision-a")
            with self.credentials(reviewer_id):
                self.ancestor_approval = self.service.decide(
                    ancestor["id"],
                    DecisionRequest(
                        expected_version=ancestor["version"],
                        binding_digest=ancestor["binding_digest"],
                        outcome="approve",
                        reason="Review mandatory predecessor",
                    ),
                )
        with self.credentials():
            pending = self.service.request_decision(self.run.id, "decision")
        with self.credentials(reviewer_id):
            self.approval = self.service.decide(
                pending["id"],
                DecisionRequest(
                    expected_version=pending["version"],
                    binding_digest=pending["binding_digest"],
                    outcome="approve",
                    reason="Review synthetic target",
                ),
            )
        from services.infra_automation_handoffs import HandoffService
        from infra_automation.handoff import ReceiverCredential

        self.receiver = ReceiverCredential(binding.receiver_id, "receiver-secret")
        self.handoffs = HandoffService(
            decision_service=self.service,
            delivery_port=self.deliver,
            ref_port=lambda snapshot: snapshot.definition.pipeline_workflow_revision,
            clock=lambda: self.now,
            session_factory=self.factory,
        )
        with self.engine.begin() as db:
            for name, body in import_module(
                "migrations.versions.035_add_infra_handoffs"
            ).GUARDS.items():
                db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")

    def deliver(self, envelope, dispatch_credential):
        self.assertFalse(auth.has_authorized_session())
        self.assertEqual(dispatch_credential, "dispatch-secret")
        self.sent.append(envelope)

    def request(self, **changes):
        from infra_automation.handoff import PrepareHandoffRequest

        return PrepareHandoffRequest(
            project_id=100,
            workspace_id=100,
            approval_id=self.approval["id"],
            handoff_step_id="handoff",
            idempotency_key="unique-key",
            reason="Prepare approved work",
            **changes,
        )

    def prepare(self):
        with self.credentials():
            return self.handoffs.prepare(self.request())

    def dispatch(self, operation):
        from infra_automation.handoff import DispatchHandoffRequest

        with self.credentials():
            return self.handoffs.dispatch(
                operation["id"],
                DispatchHandoffRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_version=operation["version"],
                    reason="Send approved work",
                ),
            )

    def test_prepare_is_atomic_replay_stable_and_only_verifier_persists(self):
        first = self.prepare()
        self.assertEqual(self.prepare(), first)
        with self.credentials(), self.assertRaises(LifecycleError):
            self.handoffs.prepare(
                self.request().model_copy(update={"reason": "Changed request"})
            )
        with self.credentials(), self.assertRaises(LifecycleError):
            self.handoffs.prepare(
                self.request().model_copy(update={"idempotency_key": "another-key"})
            )
        self.assertNotEqual(
            first["decision_binding_digest"], first["receiver_binding_digest"]
        )
        with self.factory() as db:
            grant = db.scalar(select(InfraAutomationGrant))
            self.assertEqual(grant.status, "available")
            self.assertIsNone(grant.receipt_bytes)
            self.assertEqual(len(list(db.scalars(select(InfraAutomationOutbox)))), 1)
            self.assertNotIn("grant", json.dumps(first))

    def test_dispatch_unknown_never_retries_and_consumption_precedes_action(self):
        operation = self.prepare()
        dispatched = self.dispatch(operation)
        self.assertEqual(dispatched["state"], "delivery_unknown")
        with self.assertRaises(LifecycleError):
            self.dispatch(dispatched)
        envelope = self.sent[0]
        receipt = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.assertEqual(receipt["receipt"]["sequence"], 1)
        self.assertEqual(
            receipt, self.handoffs.receiver_status(operation["id"], self.receiver)
        )
        self.assertEqual(
            self.handoffs.authorize_action(operation["id"], self.receiver)["state"],
            "consumed",
        )
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(len(self.sent), 1)
        with self.factory() as db:
            self.assertEqual(registry.get_lock(db, "held-lock").status, "held")

    def test_prepare_failure_rolls_back_all_rows_and_ref_and_payload_fail_closed(self):
        with patch(
            "models.repositories.infra_automation_handoffs.create_grant",
            side_effect=RuntimeError("fault"),
        ):
            with self.assertRaises(RuntimeError):
                self.prepare()
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(InfraAutomationHandoff)))), 0)
            self.assertEqual(len(list(db.scalars(select(InfraAutomationOutbox)))), 0)
        self.handoffs.ref_port = lambda snapshot: "b" * 40
        with self.assertRaises(LifecycleError):
            self.prepare()

    def test_wrong_receiver_token_wire_and_rotated_key_deny_without_consumption(self):
        from infra_automation.handoff import ReceiverCredential

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        for credential, token, wire in (
            (
                ReceiverCredential("other", "receiver-secret"),
                envelope.grant_token,
                envelope.message_bytes,
            ),
            (self.receiver, "wrong", envelope.message_bytes),
            (
                self.receiver,
                envelope.grant_token,
                json.loads(envelope.message_bytes) | {"operation_id": "other"},
            ),
        ):
            with (
                self.subTest(credential=type(credential)),
                self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)),
            ):
                self.handoffs.consume(wire, token, credential)
        with (
            patch("config.handoff_grant_key", return_value=b"r" * 32),
            self.assertRaises(LifecycleError),
        ):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "available"
            )

    def test_expiry_and_disable_deny_action_but_receipt_remains_readable(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        consumed = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.now += timedelta(minutes=20)
        with self.assertRaises(LifecycleError):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), consumed
        )

    def test_possible_delivery_claim_is_committed_before_fault_and_never_resends(self):
        operation = self.prepare()

        class LostProcess(BaseException):
            pass

        def crash(envelope, credential):
            self.assertFalse(auth.has_authorized_session())
            with self.factory() as db:
                self.assertEqual(
                    db.get(InfraAutomationHandoff, operation["id"]).state, "sending"
                )
                self.assertEqual(
                    db.get(InfraAutomationOutbox, operation["id"]).state, "sending"
                )
                self.assertEqual(registry.get_lock(db, "held-lock").status, "held")
            self.sent.append(envelope)
            raise LostProcess()

        self.handoffs.delivery_port = crash
        with self.assertRaises(LostProcess):
            self.dispatch(operation)
        with self.credentials():
            recorded = self.handoffs.get_operation(operation["id"], 100, 100)
        self.assertEqual(recorded["state"], "delivery_unknown")
        with self.assertRaises(LifecycleError):
            self.dispatch(recorded)
        self.assertEqual(len(self.sent), 1)
        self.handoffs.consume(
            self.sent[0].message_bytes, self.sent[0].grant_token, self.receiver
        )

    def test_receipt_rollback_and_lost_response_recover_before_one_counted_action(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        with patch(
            "models.repositories.infra_automation_handoffs.transition",
            side_effect=RuntimeError("fault after grant CAS"),
        ):
            with self.assertRaises(RuntimeError):
                self.handoffs.consume(
                    envelope.message_bytes, envelope.grant_token, self.receiver
                )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "available"
            )
        # This local double loses the first successful response, then recovers
        # its committed receipt via status before checking action admission.
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        recovered = self.handoffs.receiver_status(operation["id"], self.receiver)
        self.assertEqual(recovered["receipt"]["state"], "consumed")
        count = 0
        self.handoffs.authorize_action(operation["id"], self.receiver)
        count += 1
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(count, 1)
        self.assertNotIn(envelope.grant_token, repr(envelope))
        self.assertNotIn(self.receiver.secret, repr(self.receiver))
        with self.engine.connect() as connection:
            dump = "\n".join(connection.connection.driver_connection.iterdump())
        self.assertNotIn(envelope.grant_token, dump)
        self.assertNotIn(self.receiver.secret, dump)

    def test_disable_after_consume_blocks_counted_action_while_status_is_retained(self):
        from infra_automation.lifecycle import AutomationSettings
        from models.repositories import infra_automation_workflows as policies

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        consumed = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        with self.factory.begin() as db:
            policy = policies.get_policy(db, project_id=100)
            policies.save_policy(
                db,
                project_id=100,
                expected_version=policy.version,
                settings_json=AutomationSettings(enabled=False).model_dump_json(),
            )
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), consumed
        )
        with self.credentials():
            self.assertEqual(
                self.handoffs.get_operation(operation["id"], 100, 100), consumed
            )

    def test_custody_and_reviewer_revocation_and_target_retirement_deny_consume(self):
        from models.tables import IdentityAccount

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        old = self.material
        self.material = replace(
            old, live=old.live.model_copy(update={"custody_available": False})
        )
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.material = old
        with self.factory.begin() as db:
            reviewer = db.get(IdentityAccount, "reviewer")
            reviewer.authentication_version += 1
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "available"
            )
            self.assertEqual(registry.get_lock(db, "held-lock").status, "held")

    def test_break_retires_available_authority(self):
        from infra_automation.targets import BreakLockRequest
        from services.infra_automation_targets import break_lock

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        with self.credentials():
            broken = break_lock(
                "target",
                BreakLockRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_lock_id="held-lock",
                    expected_version=1,
                    acknowledge_uncertainty=True,
                    reason="Operator acknowledges external uncertainty",
                ),
                now=self.now,
            )
        self.assertEqual(broken["status"], "broken")
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        status = self.handoffs.receiver_status(operation["id"], self.receiver)
        self.assertTrue(status["broken"])
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "invalidated"
            )

    def test_only_exact_sequenced_terminal_after_consumption_resolves_held_lock(self):
        from infra_automation.receiver_protocol import validate_receiver_message

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        terminal = validate_receiver_message(
            json.loads(envelope.message_bytes)
            | {"operation": "outcome", "sequence": 2, "state": "succeeded"}
        )
        with self.assertRaises(LifecycleError):
            self.handoffs.resolve_terminal(terminal, self.receiver)
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        resolved = self.handoffs.resolve_terminal(terminal, self.receiver)
        self.assertEqual(resolved["state"], "succeeded")
        self.assertEqual(resolved["outcome"]["sequence"], 2)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), resolved
        )
        with self.factory() as db:
            self.assertEqual(registry.get_lock(db, "held-lock").status, "resolved")
        with self.assertRaises(LifecycleError):
            self.handoffs.authorize_action(operation["id"], self.receiver)

    def test_concurrent_consume_has_one_cas_winner(self):
        from concurrent.futures import ThreadPoolExecutor

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]

        def contender(_):
            try:
                return self.handoffs.consume(
                    envelope.message_bytes, envelope.grant_token, self.receiver
                )["state"]
            except LifecycleError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(
                list(pool.map(contender, range(2))), ["consumed", "conflict"]
            )

    def test_clock_change_inside_ref_callback_cannot_authorize_prepare(
        self,
    ):
        original = self.handoffs.ref_port

        def late(snapshot):
            self.now += timedelta(minutes=20)
            return original(snapshot)

        self.handoffs.ref_port = late
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.prepare()
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(InfraAutomationHandoff)))), 0)

    def test_unavailable_ports_fail_before_any_possible_delivery(self):
        original = self.handoffs.ref_port
        self.handoffs.ref_port = None
        with self.assertRaises(LifecycleError) as error:
            self.prepare()
        self.assertEqual(error.exception.status_code, 503)
        self.handoffs.ref_port = original
        operation = self.prepare()
        self.handoffs.delivery_port = None
        with self.assertRaises(LifecycleError) as error:
            self.dispatch(operation)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(self.sent, [])
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationHandoff, operation["id"]).state, "prepared"
            )
            self.assertEqual(
                db.get(InfraAutomationOutbox, operation["id"]).state, "pending"
            )

    def test_scoped_human_reads_and_csrf_and_receiver_audience_remain_independent(self):
        from infra_automation.handoff import ReceiverCredential

        operation = self.prepare()
        with (
            self.credentials(csrf="wrong"),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            self.handoffs.prepare(self.request())
        with self.credentials(), self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.get_operation(operation["id"], 200, 200)
        self.dispatch(operation)
        envelope = self.sent[0]
        with self.credentials(), self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, "receiver-secret"
            )
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.consume(
                envelope.message_bytes,
                envelope.grant_token,
                ReceiverCredential(
                    self.receiver.receiver_id, self.receiver.secret, audience="human"
                ),
            )
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.handoffs.receiver_status(
                operation["id"],
                ReceiverCredential(self.receiver.receiver_id, "wrong-secret"),
            )

    def test_restoration_and_target_disable_then_reenable_cannot_revive_grant(self):
        from models.repositories import infra_automation_workflows as policies

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        with self.factory.begin() as db:
            target = registry.get_target(db, "target")
            registry.update_target(
                db,
                target_id=target.id,
                expected_version=target.version,
                definition_bytes=target.definition_bytes,
                definition_digest=target.definition_digest,
                enabled=False,
                receiver_principal_id=target.receiver_principal_id,
                aliases=(),
                scopes=[(100, 100)],
                now=self.now,
            )
            target = registry.get_target(db, "target")
            registry.update_target(
                db,
                target_id=target.id,
                expected_version=target.version,
                definition_bytes=target.definition_bytes,
                definition_digest=target.definition_digest,
                enabled=True,
                receiver_principal_id=target.receiver_principal_id,
                aliases=(),
                scopes=[(100, 100)],
                now=self.now,
            )
            policy = policies.get_policy(db, project_id=100)
            policies.save_policy(
                db,
                project_id=100,
                expected_version=policy.version,
                settings_json=policy.settings_json,
                restore=True,
            )
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver)["state"],
            "delivery_unknown",
        )
        with self.factory() as db:
            self.assertEqual(registry.get_lock(db, "held-lock").status, "held")

    def test_cancel_and_earliest_expiry_retain_lock_and_receipt_authority_is_not_replayed(
        self,
    ):
        from models.repositories import infra_automation_runs as run_repository

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        with self.factory.begin() as db:
            run_repository.get_run(db, self.run.id).cancel_requested = True
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory.begin() as db:
            run_repository.get_run(db, self.run.id).cancel_requested = False
        self.now += timedelta(minutes=5)
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "available"
            )
            self.assertEqual(registry.get_lock(db, "held-lock").status, "held")

    def test_frozen_wire_mutation_even_with_recomputed_digest_does_not_match_operation(
        self,
    ):
        from infra_automation.receiver_protocol import receiver_binding_digest

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        mutated = json.loads(envelope.message_bytes)
        mutated["binding"]["project_id"] = "200"
        mutated["binding_digest"] = receiver_binding_digest(mutated["binding"])
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(mutated, envelope.grant_token, self.receiver)
        original = json.loads(envelope.message_bytes)
        # Duplicate keys are rejected by the actual frozen parser before auth.
        duplicate = envelope.message_bytes.replace(
            b'"operation":"consume"', b'"operation":"consume","operation":"consume"'
        )
        self.assertNotEqual(duplicate, envelope.message_bytes)
        with self.assertRaises(LifecycleError) as error:
            self.handoffs.consume(duplicate, envelope.grant_token, self.receiver)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(
            original["binding_digest"], operation["receiver_binding_digest"]
        )

    def test_feature_or_reviewer_revocation_inside_ref_callback_rolls_back_prepare(
        self,
    ):
        from models.tables import IdentityAccount

        def revoke(snapshot):
            with auth.authorized_session() as db:
                db.get(IdentityAccount, "reviewer").authentication_version += 1
                db.flush()
            return snapshot.definition.pipeline_workflow_revision

        self.handoffs.ref_port = revoke
        with self.assertRaises(LifecycleError):
            self.prepare()
        with self.factory() as db:
            self.assertEqual(
                db.get(IdentityAccount, "reviewer").authentication_version, 1
            )
            self.assertEqual(len(list(db.scalars(select(InfraAutomationHandoff)))), 0)

    def test_clock_regression_and_ref_change_after_prepare_leave_intent_unsent(self):
        operation = self.prepare()
        self.handoffs.clock = lambda: self.now - timedelta(seconds=1)
        with self.assertRaises(LifecycleError) as error:
            self.dispatch(operation)
        self.assertEqual(error.exception.status_code, 503)
        self.handoffs.clock = lambda: self.now
        self.handoffs.ref_port = lambda snapshot: "b" * 40
        with self.assertRaises(LifecycleError):
            self.dispatch(operation)
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationHandoff, operation["id"]).state, "prepared"
            )
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "available"
            )
        self.assertEqual(self.sent, [])

    def test_receiver_report_bridge_never_supplies_human_or_project_authority(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        old_port = self.service.material_port
        observed = []

        def material(session, *args):
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_project(
                    session, 100, 100, "automation.request", mutation=True
                )
            # The same private context permits only the bound report read.
            self.assertEqual(auth.guard_report(session, 1, "report.read").id, 1)
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_report(session, 1, "report.read", mutation=True)
            with self.assertRaises(auth.TrustedAuthorizationError):
                auth.guard_report(session, 2, "report.read")
            observed.append(True)
            return old_port(session, *args)

        self.service.material_port = material
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.assertTrue(observed)

    def test_feature_disable_inside_ref_callback_cannot_cross_consume_boundary(self):
        from infra_automation.lifecycle import AutomationSettings
        from models.repositories import infra_automation_workflows as policies

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]

        def disable(snapshot):
            with auth.authorized_session() as db:
                policy = policies.get_policy(db, project_id=100)
                policies.save_policy(
                    db,
                    project_id=100,
                    expected_version=policy.version,
                    settings_json=AutomationSettings(enabled=False).model_dump_json(),
                )
            return snapshot.definition.pipeline_workflow_revision

        self.handoffs.ref_port = disable
        with self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "available"
            )
            _, settings = support.policy_state(db, 100)
            self.assertTrue(settings.enabled)

    def test_handoff_mutation_audits_bind_before_and_after_state_without_read_events(
        self,
    ):
        from models.tables import InfraAutomationAudit
        from infra_automation.receiver_protocol import validate_receiver_message

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        with self.factory() as session:
            before_reads = list(
                session.scalars(
                    select(InfraAutomationAudit).where(
                        InfraAutomationAudit.target_id == operation["id"]
                    )
                )
            )
        self.handoffs.receiver_status(operation["id"], self.receiver)
        self.handoffs.authorize_action(operation["id"], self.receiver)
        with self.credentials():
            self.handoffs.get_operation(operation["id"], 100, 100)
        with self.factory() as session:
            self.assertEqual(
                len(
                    list(
                        session.scalars(
                            select(InfraAutomationAudit).where(
                                InfraAutomationAudit.target_id == operation["id"]
                            )
                        )
                    )
                ),
                len(before_reads),
            )
        terminal = validate_receiver_message(
            json.loads(envelope.message_bytes)
            | {"operation": "outcome", "sequence": 2, "state": "succeeded"}
        )
        self.handoffs.resolve_terminal(terminal, self.receiver)
        with self.factory() as session:
            events = list(
                session.scalars(
                    select(InfraAutomationAudit)
                    .where(InfraAutomationAudit.target_id == operation["id"])
                    .order_by(InfraAutomationAudit.sequence)
                )
            )
        self.assertEqual(
            [event.event_type for event in events],
            [
                "handoff_prepared",
                "handoff_dispatch_claimed",
                "handoff_delivery_observed",
                "handoff_consumed",
                "handoff_terminal_verified",
            ],
        )
        self.assertIsNone(events[0].before_digest)
        for prior, event in zip(events, events[1:]):
            self.assertIsNotNone(event.before_digest)
            self.assertIsNotNone(event.after_digest)
            self.assertNotEqual(event.before_digest, event.after_digest)
            self.assertEqual(event.before_digest, prior.after_digest)

    def test_audit_fault_rolls_back_consumption_state_and_receipt_together(self):
        from models.tables import InfraAutomationAudit

        operation = self.prepare()
        dispatched = self.dispatch(operation)
        envelope = self.sent[0]
        with self.factory() as session:
            events_before = list(
                session.scalars(
                    select(InfraAutomationAudit).where(
                        InfraAutomationAudit.target_id == operation["id"]
                    )
                )
            )
        with patch.object(
            self.handoffs, "_audit", side_effect=RuntimeError("audit fault")
        ):
            with self.assertRaises(RuntimeError):
                self.handoffs.consume(
                    envelope.message_bytes, envelope.grant_token, self.receiver
                )
        with self.factory() as session:
            self.assertEqual(
                session.scalar(select(InfraAutomationGrant)).status, "available"
            )
            self.assertEqual(
                session.get(InfraAutomationHandoff, operation["id"]).version,
                dispatched["version"],
            )
            self.assertEqual(
                len(
                    list(
                        session.scalars(
                            select(InfraAutomationAudit).where(
                                InfraAutomationAudit.target_id == operation["id"]
                            )
                        )
                    )
                ),
                len(events_before),
            )
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )

    def test_prepare_refreshes_run_after_ref_callback_raw_sql_mutations(self):
        from sqlalchemy import update
        from models.tables import InfraAutomationRun
        from models.repositories import infra_automation_runs as run_repository

        for changes in (
            {"cancel_requested": True},
            {"state": "cancelled"},
            {"last_observed_at": self.now + timedelta(seconds=1)},
        ):
            with self.subTest(changes=tuple(changes)):

                def mutate(snapshot):
                    with auth.authorized_session() as session:
                        session.execute(
                            update(InfraAutomationRun)
                            .where(InfraAutomationRun.id == self.run.id)
                            .values(**changes)
                            .execution_options(synchronize_session=False)
                        )
                    return snapshot.definition.pipeline_workflow_revision

                self.handoffs.ref_port = mutate
                with self.assertRaises(LifecycleError):
                    self.prepare()
                with self.factory() as session:
                    self.assertEqual(
                        run_repository.get_run(session, self.run.id).state,
                        "ready_handoff",
                    )
                    self.assertEqual(
                        len(list(session.scalars(select(InfraAutomationHandoff)))), 0
                    )

    def test_possible_dispatch_marks_parent_run_before_port_and_cancel_retains_unknown(
        self,
    ):
        from infra_automation.state import CancelRunRequest
        from models.repositories import infra_automation_runs as run_repository
        from services.infra_automation_engine_service import cancel_run

        operation = self.prepare()

        def deliver(envelope, credential):
            self.assertFalse(auth.has_authorized_session())
            with self.factory() as session:
                run = run_repository.get_run(session, self.run.id)
                self.assertEqual(run.state, "handing_off")
                self.assertTrue(run.external_possible)
            self.sent.append(envelope)

        self.handoffs.delivery_port = deliver
        self.dispatch(operation)
        self.assertEqual(len(self.sent), 1)
        with self.factory() as session:
            run_version = run_repository.get_run(session, self.run.id).version
        with self.credentials():
            cancelled = cancel_run(
                self.run.id,
                CancelRunRequest(
                    expected_version=run_version, reason="Stop uncertain external work"
                ),
                now=self.now,
            )
        self.assertEqual(cancelled["state"], "delivery_unknown")
        with self.factory() as session:
            run = run_repository.get_run(session, self.run.id)
            self.assertTrue(run.cancel_requested)
            self.assertTrue(run.external_possible)
            self.assertEqual(registry.get_lock(session, "held-lock").status, "held")
        envelope = self.sent[0]
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.assertRaises(LifecycleError):
            self.handoffs.authorize_action(operation["id"], self.receiver)

    def test_revoked_human_after_port_cannot_read_result_but_unknown_intent_commits(
        self,
    ):
        from models.tables import IdentityAccount

        operation = self.prepare()

        def revoke(envelope, credential):
            self.assertFalse(auth.has_authorized_session())
            self.sent.append(envelope)
            # A distinct committed transaction models concurrent revocation at
            # the delivery boundary, after the first human transaction ended.
            with self.factory.begin() as session:
                session.get(IdentityAccount, "human-a").enabled = False

        self.handoffs.delivery_port = revoke
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.dispatch(operation)
        self.assertEqual(len(self.sent), 1)
        with self.factory() as session:
            self.assertEqual(
                session.get(InfraAutomationHandoff, operation["id"]).state,
                "delivery_unknown",
            )
            self.assertEqual(
                session.get(InfraAutomationOutbox, operation["id"]).state,
                "delivery_unknown",
            )
            self.assertEqual(registry.get_lock(session, "held-lock").status, "held")
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver)["state"],
            "delivery_unknown",
        )

    def test_consumption_records_external_running_without_inventing_run_terminal(self):
        from infra_automation.receiver_protocol import validate_receiver_message
        from models.repositories import infra_automation_runs as run_repository

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        with self.factory() as session:
            run = run_repository.get_run(session, self.run.id)
            self.assertEqual(run.state, "external_running")
            self.assertTrue(run.external_possible)
        terminal = validate_receiver_message(
            json.loads(envelope.message_bytes)
            | {"operation": "outcome", "sequence": 2, "state": "succeeded"}
        )
        self.handoffs.resolve_terminal(terminal, self.receiver)
        with self.factory() as session:
            self.assertEqual(
                run_repository.get_run(session, self.run.id).state, "external_running"
            )


class AncestorDeadlineHandoffTests(LifecycleCase):
    """Ref callbacks cannot outlive a required earlier receipt's authority."""

    serial_decisions = True
    indirect_decisions = True
    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def expire_ancestor(self, snapshot):
        # Selected approval remains live until minute5; its predecessor expires
        # at minute2. Material callbacks have already checked the old clock.
        self.now += timedelta(minutes=3)
        return snapshot.definition.pipeline_workflow_revision

    def test_prepared_grant_deadline_includes_required_ancestor(self):
        operation = self.prepare()
        self.assertEqual(
            operation["deadline_at"], self.ancestor_approval["deadline_at"]
        )
        self.assertLess(operation["deadline_at"], self.approval["deadline_at"])

    def test_prepare_rechecks_ancestor_deadline_after_ref_callback(self):
        self.handoffs.ref_port = self.expire_ancestor
        with self.assertRaises(LifecycleError):
            self.prepare()
        with self.factory() as db:
            self.assertEqual(len(list(db.scalars(select(InfraAutomationHandoff)))), 0)
            self.assertEqual(len(list(db.scalars(select(InfraAutomationGrant)))), 0)

    def test_dispatch_rechecks_ancestor_deadline_before_sending(self):
        operation = self.prepare()
        self.handoffs.ref_port = self.expire_ancestor
        with self.assertRaises(LifecycleError):
            self.dispatch(operation)
        self.assertEqual(self.sent, [])
        with self.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationHandoff, operation["id"]).state, "prepared"
            )

    def test_consume_rechecks_ancestor_deadline_before_grant_cas(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.ref_port = self.expire_ancestor
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(InfraAutomationGrant)).status, "available"
            )
            self.assertEqual(registry.get_lock(db, "held-lock").status, "held")

    def test_action_rechecks_ancestor_deadline_but_preserves_consumed_receipt(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        receipt = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.handoffs.ref_port = self.expire_ancestor
        with self.assertRaises(LifecycleError):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), receipt
        )


class _ReceiverDoubleCrash(Exception):
    pass


class _DurableReceiverDouble:
    """Synthetic local SQL effect+ledger only; no production delivery proof.

    The service's repeatable live deny check does not fence receiver actions.
    This double owns a separate durable operation/binding ledger and performs
    its synthetic counted effect atomically with the terminal ledger write.
    An actual external receiver must supply its own qualified durability in16.11.
    """

    def __init__(self, path, service, credential):
        self.path = path
        self.service = service
        self.credential = credential
        with self.connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ledger (operation_id TEXT PRIMARY KEY, binding_digest TEXT NOT NULL, state TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS effects (operation_id TEXT PRIMARY KEY, count INTEGER NOT NULL CHECK(count=1))"
            )

    @contextmanager
    def connection(self):
        import sqlite3

        connection = sqlite3.connect(self.path)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def count(self):
        with self.connection() as connection:
            return connection.execute(
                "SELECT coalesce(sum(count),0) FROM effects"
            ).fetchone()[0]

    def authorize_and_count(self, operation_id, *, crash_at=None):
        view = self.service.authorize_action(operation_id, self.credential)
        digest = view["receiver_binding_digest"]
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT binding_digest,state FROM ledger WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if previous is not None:
                if previous[0] != digest:
                    raise LifecycleError(409)
                if previous[1] == "done":
                    return False
            else:
                if crash_at == "before_insert":
                    raise _ReceiverDoubleCrash()
                connection.execute(
                    "INSERT INTO ledger VALUES (?,?,?)",
                    (operation_id, digest, "claimed"),
                )
                if crash_at == "during_insert":
                    raise _ReceiverDoubleCrash()
        if crash_at == "after_insert":
            raise _ReceiverDoubleCrash()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT binding_digest,state FROM ledger WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if previous != (digest, "claimed"):
                return False
            # Recheck live admission after recovering a claimed ledger row and
            # immediately before this local double's transactional effect.
            self.service.authorize_action(operation_id, self.credential)
            if crash_at == "before_count":
                raise _ReceiverDoubleCrash()
            connection.execute("INSERT INTO effects VALUES (?,1)", (operation_id,))
            connection.execute(
                "UPDATE ledger SET state='done' WHERE operation_id=?", (operation_id,)
            )
            if crash_at == "after_count":
                raise _ReceiverDoubleCrash()
        if crash_at == "after_commit":
            raise _ReceiverDoubleCrash()
        return True


class DurableReceiverDoubleTests(LifecycleCase):
    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def consumed(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        # Treat the successful consume response as lost. Only durable status is
        # used to recover the existing receipt; consume is never replayed.
        recovered = self.handoffs.receiver_status(operation["id"], self.receiver)
        self.assertEqual(recovered["receipt"]["sequence"], 1)
        return operation

    def test_recovered_and_concurrent_repeatable_checks_count_once_via_receiver_ledger(
        self,
    ):
        from concurrent.futures import ThreadPoolExecutor

        operation = self.consumed()
        path = self.temp.name + "/durable-double.db"
        double = _DurableReceiverDouble(path, self.handoffs, self.receiver)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: double.authorize_and_count(operation["id"]), range(2)
                )
            )
        self.assertCountEqual(results, [True, False])
        restarted = _DurableReceiverDouble(path, self.handoffs, self.receiver)
        self.assertFalse(restarted.authorize_and_count(operation["id"]))
        self.assertEqual(restarted.count(), 1)

    def test_crashes_around_durable_claim_and_count_recover_without_duplicate_effect(
        self,
    ):
        operation = self.consumed()
        for stage in (
            "before_insert",
            "during_insert",
            "after_insert",
            "before_count",
            "after_count",
            "after_commit",
        ):
            with self.subTest(stage=stage):
                path = self.temp.name + "/double-" + stage + ".db"
                double = _DurableReceiverDouble(path, self.handoffs, self.receiver)
                with self.assertRaises(_ReceiverDoubleCrash):
                    double.authorize_and_count(operation["id"], crash_at=stage)
                restarted = _DurableReceiverDouble(path, self.handoffs, self.receiver)
                restarted.authorize_and_count(operation["id"])
                self.assertFalse(restarted.authorize_and_count(operation["id"]))
                self.assertEqual(restarted.count(), 1)


class CallbackDecisionModeTests(LifecycleCase):
    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def change_mode(self, snapshot):
        context = patch(
            "config.settings",
            replace(config.settings, identity_decision_mode="single-operator"),
        )
        context.start()
        self.addCleanup(context.stop)
        return snapshot.definition.pipeline_workflow_revision

    def test_prepare_rechecks_current_decision_mode_after_ref_callback(self):
        self.handoffs.ref_port = self.change_mode
        with self.assertRaises(LifecycleError):
            self.prepare()

    def test_consume_rechecks_current_decision_mode_after_ref_callback(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.ref_port = self.change_mode
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )

    def test_action_rechecks_current_decision_mode_after_ref_callback(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        receipt = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.handoffs.ref_port = self.change_mode
        with self.assertRaises(LifecycleError):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), receipt
        )


class CallbackAcknowledgementHumanCountTests(LifecycleCase):
    acknowledgement = True
    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def add_human(self, snapshot):
        from models.tables import IdentityAccount

        with auth.authorized_session() as session:
            session.add(
                IdentityAccount(
                    id="new-human",
                    username="new-human",
                    principal_type="human",
                    password_verifier="synthetic-unused",
                    is_admin=False,
                    enabled=True,
                    authentication_version=1,
                    created_at=self.now,
                )
            )
            session.flush()
        return snapshot.definition.pipeline_workflow_revision

    def test_prepare_rechecks_exactly_one_enabled_human_after_ref_callback(self):
        self.assertEqual(self.approval["decision_kind"], "acknowledgement")
        self.handoffs.ref_port = self.add_human
        with self.assertRaises(LifecycleError):
            self.prepare()

    def test_consume_rechecks_exactly_one_enabled_human_after_ref_callback(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.ref_port = self.add_human
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )

    def test_action_rechecks_exactly_one_enabled_human_after_ref_callback(self):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        receipt = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.handoffs.ref_port = self.add_human
        with self.assertRaises(LifecycleError):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), receipt
        )


class IndependentReceiptDeadlineTests(LifecycleCase):
    serial_decisions = True
    indirect_decisions = True
    enable = HandoffServiceTests.enable
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch
    expire_ancestor = AncestorDeadlineHandoffTests.expire_ancestor

    def publish_fixture(self, definition=None, **kwargs):
        import copy

        definition = copy.deepcopy(definition)
        selected = next(
            step for step in definition["steps"] if step["id"] == "decision"
        )
        selected["depends_on"].remove("decision-a")
        return HandoffServiceTests.publish_fixture(self, definition, **kwargs)

    def test_unrelated_receipt_expiring_during_ref_does_not_block_selected_consume(
        self,
    ):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.handoffs.ref_port = self.expire_ancestor
        consumed = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.assertEqual(consumed["state"], "consumed")
        self.handoffs.ref_port = lambda snapshot: (
            snapshot.definition.pipeline_workflow_revision
        )
        self.assertEqual(
            self.handoffs.authorize_action(operation["id"], self.receiver)["state"],
            "consumed",
        )


class DistinctAncestorReportTests(LifecycleCase):
    """A required sibling analysis report is readable only within this exact DAG."""

    serial_decisions = True
    indirect_decisions = True
    enable = HandoffServiceTests.enable
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def publish_fixture(self, definition=None, **kwargs):
        import copy

        definition = copy.deepcopy(definition)
        nodes = {step["id"]: step for step in definition["steps"]}
        analysis = copy.deepcopy(nodes["analyze"])
        analysis["id"] = "analyze-a"
        gate = copy.deepcopy(nodes["gate"])
        gate.update(id="gate-a", depends_on=["analyze-a"])
        gate["report"]["step_id"] = "analyze-a"
        nodes["decision-a"]["depends_on"] = ["gate-a"]
        nodes["decision-a"]["binding"]["step_id"] = "gate-a"
        definition["steps"][3:3] = [analysis, gate]
        return HandoffServiceTests.publish_fixture(self, definition, **kwargs)

    def seed_ancestor_report(self, binding):
        from infra_automation.decisions import freeze_report_snapshot
        from models.tables import (
            AnalysisReport,
            RiskAssessment,
            InfraAutomationAttempt,
            InfraAutomationReportLink,
        )
        from services.report_service import _serialize_report

        def values(row, *excluded):
            return {
                column.key: getattr(row, column.key)
                for column in row.__table__.columns
                if column.key not in excluded
            }

        with self.factory.begin() as session:
            first = session.get(AnalysisReport, 1)
            report = AnalysisReport(id=2, **values(first, "id"))
            report.risk_assessment = RiskAssessment(
                **values(first.risk_assessment, "analysis_id")
            )
            session.add(report)
            # A real row outside the required report allowlist stays denied.
            session.add(AnalysisReport(id=3, **values(first, "id")))
            session.flush()
            raw_report, report_digest = freeze_report_snapshot(
                _serialize_report(report)
            )
            for original_step in ("analyze", "gate"):
                original = session.scalar(
                    select(InfraAutomationAttempt).where(
                        InfraAutomationAttempt.id == "attempt-" + original_step
                    )
                )
                clone = InfraAutomationAttempt(
                    **values(original, "sequence", "id", "step_id"),
                    id="attempt-" + original_step + "-a",
                    step_id=original_step + "-a",
                )
                if original_step == "analyze":
                    output = {
                        "kind": "report",
                        "reference": "link-a",
                        "digest": support.digest(
                            support.canonical(
                                {"version": 1, "kind": "synthetic-collected-proof"}
                            )
                        ),
                    }
                    clone.output_json = support.canonical(output).decode()
                    clone.output_digest = support.digest(clone.output_json.encode())
                session.add(clone)
            session.flush()
            original_link = session.get(InfraAutomationReportLink, "link")
            session.add(
                InfraAutomationReportLink(
                    **values(original_link, "id", "attempt_id", "report_id"),
                    id="link-a",
                    attempt_id="attempt-analyze-a",
                    report_id=2,
                )
            )
        return binding.model_copy(
            update={"report_id": 2, "report_bytes_digest": report_digest}
        ), self.material.evidence.model_copy(update={"report_step_id": "analyze-a"})

    def test_consume_and_action_read_both_required_reports_but_no_unrelated_report(
        self,
    ):
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        original = self.service.material_port
        observed = set()

        def material(session, run, step, previous):
            from infra_automation.handoff_context import has_receiver_report_read

            if has_receiver_report_read():
                for report_id in (1, 2):
                    self.assertEqual(
                        auth.guard_report(session, report_id).id, report_id
                    )
                    observed.add(report_id)
                with self.assertRaises(auth.TrustedAuthorizationError):
                    auth.guard_report(session, 3)
            return original(session, run, step, previous)

        self.service.material_port = material
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(observed, {1, 2})


class FractionalRunDeadlineTests(LifecycleCase):
    """Published/HMAC second precision must never extend a fractional hard floor."""

    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def setUp(self):
        original = fixture.runs.create_run

        def create_run(session, **values):
            values["deadline_at"] = values["now"] + timedelta(
                seconds=180, microseconds=500000
            )
            return original(session, **values)

        # Seed the fractional immutable deadline at real repository insertion;
        # never mutate retained run identity or bypass its deadline guard.
        with patch.object(fixture.runs, "create_run", side_effect=create_run):
            HandoffServiceTests.setUp(self)

    def test_persisted_operation_and_grant_deadlines_equal_published_whole_second(self):
        from infra_automation.decisions import instant
        from models.repositories import infra_automation_runs as run_repository

        operation = self.prepare()
        published = instant(operation["deadline_at"])
        with self.factory() as session:
            run = run_repository.get_run(session, self.run.id)
            retained = session.get(InfraAutomationHandoff, operation["id"])
            grant = session.scalar(select(InfraAutomationGrant))
            self.assertEqual(
                run_repository.utc(run.deadline_at),
                published + timedelta(microseconds=500000),
            )
            self.assertEqual(run_repository.utc(retained.deadline_at), published)
            self.assertEqual(run_repository.utc(grant.deadline_at), published)

    def test_consume_at_published_expiry_rejects_inside_fractional_run_window(self):
        from infra_automation.decisions import instant

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        self.now = instant(operation["deadline_at"])
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        with self.factory() as session:
            self.assertEqual(
                session.scalar(select(InfraAutomationGrant)).status, "available"
            )
            self.assertEqual(registry.get_lock(session, "held-lock").status, "held")

    def test_prepare_denies_published_expiry_floor_before_fractional_run_deadline(self):
        self.now += timedelta(seconds=180, microseconds=250000)
        with self.assertRaises(LifecycleError):
            self.prepare()
        with self.factory() as session:
            self.assertEqual(
                len(list(session.scalars(select(InfraAutomationHandoff)))), 0
            )
            self.assertEqual(
                len(list(session.scalars(select(InfraAutomationGrant)))), 0
            )


class HandoffStorageCapacityTests(LifecycleCase):
    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def retained(self):
        from models.repositories import infra_automation_runs as run_repository

        with self.factory() as session:
            run = run_repository.get_run(session, self.run.id)
            return run.retained_bytes, run.version

    def test_new_operation_and_first_receipt_charge_once_replays_and_reads_never_charge(
        self,
    ):
        before, _ = self.retained()
        operation = self.prepare()
        prepared, _ = self.retained()
        with self.factory() as session:
            row = session.get(InfraAutomationHandoff, operation["id"])
            raw_copies = sum(
                len(value)
                for value in (
                    row.decision_binding_bytes,
                    row.receiver_binding_bytes,
                    row.payload_bytes,
                    row.target_snapshot_bytes,
                )
            )
        self.assertGreater(prepared, before + raw_copies)
        self.assertEqual(self.prepare(), operation)
        self.assertEqual(self.retained()[0], prepared)
        self.dispatch(operation)
        self.assertEqual(self.retained()[0], prepared)
        envelope = self.sent[0]
        consumed = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        with self.factory() as session:
            receipt_size = len(
                session.scalar(select(InfraAutomationGrant)).receipt_bytes
            )
        self.assertEqual(self.retained()[0], prepared + receipt_size)
        with self.assertRaises(LifecycleError):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), consumed
        )
        with self.credentials():
            self.handoffs.get_operation(operation["id"], 100, 100)
        self.assertEqual(self.retained()[0], prepared + receipt_size)

    def test_prepare_project_global_and_disk_capacity_failure_roll_back_every_intent_row(
        self,
    ):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from infra_automation.state import EngineBounds

        before, version = self.retained()
        for name in ("project", "global", "disk"):
            with self.subTest(limit=name):
                bounds = EngineBounds(
                    **({name + "_bytes": before} if name != "disk" else {})
                )
                disk = (
                    patch(
                        "infra_automation.storage.shutil.disk_usage",
                        return_value=SimpleNamespace(free=0),
                    )
                    if name == "disk"
                    else nullcontext()
                )
                with (
                    patch("config.engine_bounds", return_value=bounds),
                    disk,
                    self.assertRaises(LifecycleError) as error,
                ):
                    self.prepare()
                self.assertEqual(error.exception.status_code, 429)
                self.assertEqual(self.retained(), (before, version))
                with self.factory() as session:
                    for table in (
                        InfraAutomationHandoff,
                        InfraAutomationOutbox,
                        InfraAutomationGrant,
                    ):
                        self.assertEqual(len(list(session.scalars(select(table)))), 0)
                self.assertEqual(self.sent, [])

    def test_receipt_capacity_failure_preserves_available_grant_unknown_intent_and_reads(
        self,
    ):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from infra_automation.state import EngineBounds

        operation = self.prepare()
        recorded = self.dispatch(operation)
        envelope = self.sent[0]
        before = self.retained()
        for name in ("project", "global", "disk"):
            with self.subTest(limit=name):
                bounds = EngineBounds(
                    **({name + "_bytes": before[0]} if name != "disk" else {})
                )
                disk = (
                    patch(
                        "infra_automation.storage.shutil.disk_usage",
                        return_value=SimpleNamespace(free=0),
                    )
                    if name == "disk"
                    else nullcontext()
                )
                with patch("config.engine_bounds", return_value=bounds), disk:
                    with self.assertRaises(LifecycleError) as error:
                        self.handoffs.consume(
                            envelope.message_bytes, envelope.grant_token, self.receiver
                        )
                    self.assertEqual(error.exception.status_code, 429)
                    self.assertEqual(
                        self.handoffs.receiver_status(operation["id"], self.receiver),
                        recorded,
                    )
                    with self.credentials():
                        self.assertEqual(
                            self.handoffs.get_operation(operation["id"], 100, 100),
                            recorded,
                        )
                self.assertEqual(self.retained(), before)
                with self.factory() as session:
                    grant = session.scalar(select(InfraAutomationGrant))
                    self.assertEqual(grant.status, "available")
                    self.assertIsNone(grant.receipt_bytes)
                    self.assertEqual(
                        session.get(InfraAutomationOutbox, operation["id"]).state,
                        "delivery_unknown",
                    )
                    self.assertEqual(
                        registry.get_lock(session, "held-lock").status, "held"
                    )

    def test_slow_prepare_disk_probe_cannot_extend_approval_or_leave_charged_bytes(
        self,
    ):
        from types import SimpleNamespace

        before = self.retained()

        def slow_probe(path):
            self.now += timedelta(minutes=6)
            return SimpleNamespace(free=1024**3)

        with (
            patch("infra_automation.storage.shutil.disk_usage", side_effect=slow_probe),
            self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)),
        ):
            self.prepare()
        self.assertEqual(self.retained(), before)
        self.assertEqual(self.sent, [])

    def test_slow_receipt_disk_probe_cannot_renew_consumption_authority(self):
        from types import SimpleNamespace

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        before = self.retained()

        def slow_probe(path):
            self.now += timedelta(minutes=6)
            return SimpleNamespace(free=1024**3)

        with (
            patch("infra_automation.storage.shutil.disk_usage", side_effect=slow_probe),
            self.assertRaises((LifecycleError, auth.TrustedAuthorizationError)),
        ):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(self.retained(), before)
        with self.factory() as session:
            self.assertEqual(
                session.scalar(select(InfraAutomationGrant)).status, "available"
            )

    def test_later_audit_fault_rolls_back_operation_and_receipt_storage_charges(self):
        before = self.retained()
        with (
            patch.object(
                self.handoffs, "_audit", side_effect=RuntimeError("audit fault")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.prepare()
        self.assertEqual(self.retained(), before)
        with self.factory() as session:
            self.assertEqual(
                len(list(session.scalars(select(InfraAutomationHandoff)))), 0
            )
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        before = self.retained()
        with (
            patch.object(
                self.handoffs, "_audit", side_effect=RuntimeError("audit fault")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(self.retained(), before)
        with self.factory() as session:
            self.assertEqual(
                session.scalar(select(InfraAutomationGrant)).status, "available"
            )
            self.assertIsNone(
                session.scalar(select(InfraAutomationGrant)).receipt_bytes
            )


class ReviewBoundaryRegressionTests(LifecycleCase):
    """Live material and durable observation floors survive the final callbacks."""

    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def assert_ref_mutation_denied(self, phase):
        operation = self.prepare() if phase != "prepare" else None
        if phase in {"consume", "action"}:
            self.dispatch(operation)
            envelope = self.sent[0]
        if phase == "action":
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        original = self.material
        mutations = {
            "custody": replace(
                original,
                live=original.live.model_copy(update={"custody_available": False}),
            ),
            "evidence": replace(
                original,
                evidence=original.evidence.model_copy(update={"complete": False}),
            ),
            "binding": replace(
                original,
                live=original.live.model_copy(
                    update={"current_tuple_digest": "sha256:" + "f" * 64}
                ),
            ),
        }
        before = HandoffStorageCapacityTests.retained(self)
        recorded = (
            self.handoffs.receiver_status(operation["id"], self.receiver)
            if operation
            else None
        )
        sent = len(self.sent)
        for name, material in mutations.items():
            with self.subTest(phase=phase, mutation=name):
                self.material = original

                def mutate(snapshot):
                    self.material = material
                    return snapshot.definition.pipeline_workflow_revision

                self.handoffs.ref_port = mutate
                with self.assertRaises(LifecycleError) as error:
                    if phase == "prepare":
                        self.prepare()
                    elif phase == "dispatch":
                        self.dispatch(operation)
                    elif phase == "consume":
                        self.handoffs.consume(
                            envelope.message_bytes, envelope.grant_token, self.receiver
                        )
                    else:
                        self.handoffs.authorize_action(operation["id"], self.receiver)
                self.assertEqual(error.exception.status_code, 409)
                self.assertEqual(HandoffStorageCapacityTests.retained(self), before)
                self.assertEqual(len(self.sent), sent)
                if operation:
                    self.assertEqual(
                        self.handoffs.receiver_status(operation["id"], self.receiver),
                        recorded,
                    )
                else:
                    with self.factory() as session:
                        self.assertEqual(
                            list(session.scalars(select(InfraAutomationHandoff))), []
                        )
                        self.assertEqual(
                            list(session.scalars(select(InfraAutomationGrant))), []
                        )
                        self.assertEqual(
                            list(session.scalars(select(InfraAutomationOutbox))), []
                        )

    def test_prepare_denies_material_changes_during_ref_lookup(self):
        self.assert_ref_mutation_denied("prepare")

    def test_dispatch_denies_material_changes_during_ref_lookup(self):
        self.assert_ref_mutation_denied("dispatch")

    def test_consume_denies_material_changes_during_ref_lookup(self):
        self.assert_ref_mutation_denied("consume")

    def test_action_denies_material_changes_during_ref_lookup(self):
        self.assert_ref_mutation_denied("action")

    def test_prepare_denies_custody_loss_during_disk_probe(self):
        from types import SimpleNamespace

        before = HandoffStorageCapacityTests.retained(self)

        def lose_custody(path):
            self.material = replace(
                self.material,
                live=self.material.live.model_copy(update={"custody_available": False}),
            )
            return SimpleNamespace(free=1024**3)

        with (
            patch(
                "infra_automation.storage.shutil.disk_usage", side_effect=lose_custody
            ),
            self.assertRaises(LifecycleError) as error,
        ):
            self.prepare()
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(HandoffStorageCapacityTests.retained(self), before)
        with self.factory() as session:
            self.assertEqual(list(session.scalars(select(InfraAutomationHandoff))), [])

    def test_action_clock_floor_survives_service_restart_without_new_grant(self):
        from models.repositories import infra_automation_runs as run_repository
        from services.infra_automation_handoffs import HandoffService

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        consumed = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        initial = self.now
        before = HandoffStorageCapacityTests.retained(self)
        self.now = initial + timedelta(seconds=60)
        admitted = self.handoffs.authorize_action(operation["id"], self.receiver)
        with self.factory() as session:
            row = session.get(InfraAutomationHandoff, operation["id"])
            self.assertEqual(run_repository.utc(row.last_observed_at), self.now)
            grants = list(session.scalars(select(InfraAutomationGrant)))
            self.assertEqual(len(grants), 1)
            self.assertEqual(grants[0].status, "consumed")
            self.assertEqual(grants[0].version, 2)
        self.assertEqual(admitted["receipt"], consumed["receipt"])
        self.assertEqual(HandoffStorageCapacityTests.retained(self), before)
        restarted = HandoffService(
            decision_service=self.service,
            ref_port=self.handoffs.ref_port,
            clock=lambda: self.now,
            session_factory=self.factory,
        )
        self.now = initial + timedelta(seconds=30)
        with self.assertRaises(LifecycleError) as error:
            restarted.authorize_action(operation["id"], self.receiver)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(
            restarted.receiver_status(operation["id"], self.receiver), admitted
        )
        self.now = initial + timedelta(seconds=61)
        self.assertEqual(
            restarted.authorize_action(operation["id"], self.receiver)["state"],
            "consumed",
        )

    def test_consume_denies_custody_loss_during_disk_probe_without_receipt(self):
        from types import SimpleNamespace

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        before = HandoffStorageCapacityTests.retained(self)
        recorded = self.handoffs.receiver_status(operation["id"], self.receiver)

        def lose_custody(path):
            self.material = replace(
                self.material,
                live=self.material.live.model_copy(update={"custody_available": False}),
            )
            return SimpleNamespace(free=1024**3)

        with (
            patch(
                "infra_automation.storage.shutil.disk_usage", side_effect=lose_custody
            ),
            self.assertRaises(LifecycleError) as error,
        ):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(HandoffStorageCapacityTests.retained(self), before)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), recorded
        )
        with self.factory() as session:
            grant = session.scalar(select(InfraAutomationGrant))
            self.assertEqual(grant.status, "available")
            self.assertIsNone(grant.receipt_bytes)

    def test_action_floor_update_is_audited_and_audit_failure_rolls_it_back(self):
        from models.tables import InfraAutomationAudit
        from infra_automation.receiver_protocol import validate_receiver_message

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        consumed = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.now += timedelta(seconds=60)
        with (
            patch.object(
                self.handoffs, "_audit", side_effect=RuntimeError("audit fault")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver), consumed
        )
        admitted = self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertEqual(admitted["version"], consumed["version"] + 1)
        self.assertEqual(
            self.handoffs.authorize_action(operation["id"], self.receiver), admitted
        )
        self.handoffs.resolve_terminal(
            validate_receiver_message(
                json.loads(envelope.message_bytes)
                | {
                    "operation": "outcome",
                    "sequence": 2,
                    "state": "succeeded",
                }
            ),
            self.receiver,
        )
        with self.factory() as session:
            events = list(
                session.scalars(
                    select(InfraAutomationAudit)
                    .where(InfraAutomationAudit.target_id == operation["id"])
                    .order_by(InfraAutomationAudit.sequence)
                )
            )
        self.assertEqual(
            [event.event_type for event in events].count("handoff_action_checked"), 1
        )
        for previous, current in zip(events, events[1:]):
            self.assertEqual(current.before_digest, previous.after_digest)


class GraphMaterialRaceTests(LifecycleCase):
    """A later receipt callback cannot invalidate an earlier authority snapshot."""

    serial_decisions = True
    indirect_decisions = True
    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch

    def phase_call(self, phase):
        operation = self.prepare() if phase != "prepare" else None
        if phase in {"consume", "action"}:
            self.dispatch(operation)
            envelope = self.sent[0]
        if phase == "action":
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )

        def call():
            if phase == "prepare":
                return self.prepare()
            if phase == "dispatch":
                return self.dispatch(operation)
            if phase == "consume":
                return self.handoffs.consume(
                    envelope.message_bytes, envelope.grant_token, self.receiver
                )
            return self.handoffs.authorize_action(operation["id"], self.receiver)

        return operation, call

    def record_state(self, operation):
        return (
            HandoffStorageCapacityTests.retained(self),
            len(self.sent),
            self.handoffs.receiver_status(operation["id"], self.receiver)
            if operation
            else None,
        )

    def assert_unchanged(self, operation, before):
        self.assertEqual(self.record_state(operation), before)
        if operation is None:
            with self.factory() as session:
                for model in (
                    InfraAutomationHandoff,
                    InfraAutomationGrant,
                    InfraAutomationOutbox,
                ):
                    self.assertEqual(list(session.scalars(select(model))), [])

    def assert_graph_change_denied(self, phase):
        from models.repositories import infra_automation_decisions as decisions

        operation, call = self.phase_call(phase)
        before = self.record_state(operation)
        selected, ancestor = self.material, self.ancestor_material
        original = self.service.material_port
        latest = decisions.list_latest_for_run
        for victim, attribute in (
            ("decision", "material"),
            ("decision-a", "ancestor_material"),
        ):
            for fact in ("custody", "evidence", "binding"):
                for aba in (False, True):
                    with self.subTest(phase=phase, victim=victim, fact=fact, aba=aba):
                        self.material, self.ancestor_material = selected, ancestor
                        value = getattr(self, attribute)
                        if fact == "evidence":
                            changed = replace(
                                value,
                                evidence=value.evidence.model_copy(
                                    update={"complete": False}
                                ),
                            )
                        else:
                            update = (
                                {"custody_available": False}
                                if fact == "custody"
                                else {"current_tuple_digest": "sha256:" + "f" * 64}
                            )
                            changed = replace(
                                value, live=value.live.model_copy(update=update)
                            )
                        seen = set()

                        def mutate(session, run, step, previous):
                            if step != victim and victim in seen:
                                setattr(self, attribute, changed)
                                if aba:
                                    setattr(self, attribute, value)
                            seen.add(step)
                            return original(session, run, step, previous)

                        self.service.material_port = mutate

                        def ordered(*args, **kwargs):
                            rows = latest(*args, **kwargs)
                            return (
                                list(reversed(rows)) if victim == "decision-a" else rows
                            )

                        with patch.object(
                            decisions, "list_latest_for_run", side_effect=ordered
                        ):
                            with self.assertRaises(LifecycleError) as error:
                                call()
                        self.assertEqual(error.exception.status_code, 409)
                        self.assertEqual(seen, {"decision", "decision-a"})
                        self.assert_unchanged(operation, before)

    def test_prepare_denies_selected_custody_revoked_by_ancestor(self):
        self.assert_graph_change_denied("prepare")

    def test_dispatch_denies_selected_custody_revoked_by_ancestor(self):
        self.assert_graph_change_denied("dispatch")

    def test_consume_denies_selected_custody_revoked_by_ancestor(self):
        self.assert_graph_change_denied("consume")

    def test_action_denies_selected_custody_revoked_by_ancestor(self):
        self.assert_graph_change_denied("action")

    def assert_invalid_witness_denied(self, phase):
        operation, call = self.phase_call(phase)
        before = self.record_state(operation)
        original = self.service.material_witness_port

        def unavailable(*args):
            raise RuntimeError("Synthetic private provider failure")

        invalid = {
            "missing": None,
            "exception": unavailable,
            "untyped": lambda *args: {},
            "scope": lambda session, scope: original(session, scope).model_copy(
                update={"scope_digest": "sha256:" + "f" * 64}
            ),
            "domain": lambda session, scope: original(session, scope).model_copy(
                update={"source_id": ""}
            ),
            "count": lambda session, scope: original(session, scope).model_copy(
                update={"generations": (1,)}
            ),
            "bool": lambda session, scope: original(session, scope).model_copy(
                update={"generations": (True, True)}
            ),
            "zero": lambda session, scope: original(session, scope).model_copy(
                update={"generations": (0, 1)}
            ),
        }
        for name, port in invalid.items():
            with self.subTest(phase=phase, witness=name):
                self.service.material_witness_port = port
                with self.assertRaises(LifecycleError) as error:
                    call()
                self.assertEqual(error.exception.status_code, 503)
                self.assert_unchanged(operation, before)

    def test_prepare_requires_qualified_exact_witness(self):
        self.assert_invalid_witness_denied("prepare")

    def test_dispatch_requires_qualified_exact_witness(self):
        self.assert_invalid_witness_denied("dispatch")

    def test_consume_requires_qualified_exact_witness(self):
        self.assert_invalid_witness_denied("consume")

    def test_action_requires_qualified_exact_witness(self):
        self.assert_invalid_witness_denied("action")

    def test_changed_or_reset_witness_domain_denies_all_phases(self):
        for phase in ("prepare", "dispatch", "consume", "action"):
            case = GraphMaterialRaceTests(methodName="runTest")
            case.setUp()
            try:
                operation, call = case.phase_call(phase)
                before = case.record_state(operation)
                original = case.service.material_witness_port
                for kind in ("advance", "regress", "domain-reset"):
                    with self.subTest(phase=phase, change=kind):
                        samples = []

                        def witness(session, scope):
                            value = original(session, scope)
                            samples.append(value)
                            if kind == "advance" and len(samples) == 2:
                                return value.model_copy(
                                    update={
                                        "generations": tuple(
                                            v + 1 for v in value.generations
                                        )
                                    }
                                )
                            if (
                                kind in {"regress", "domain-reset"}
                                and len(samples) == 1
                            ):
                                return value.model_copy(
                                    update={
                                        "generations": tuple(
                                            v + 10 for v in value.generations
                                        )
                                    }
                                )
                            if kind == "domain-reset":
                                return value.model_copy(
                                    update={"source_id": "replacement-material-domain"}
                                )
                            return value

                        case.service.material_witness_port = witness
                        with case.assertRaises(LifecycleError) as error:
                            call()
                        self.assertEqual(error.exception.status_code, 409)
                        self.assertEqual(len(samples), 2)
                        case.assert_unchanged(operation, before)
            finally:
                case.doCleanups()

    def test_end_witness_read_cannot_outlive_ancestor_deadline(self):
        operation, call = self.phase_call("consume")
        before = self.record_state(operation)
        original = self.service.material_witness_port
        calls = []

        def witness(session, scope):
            calls.append(scope)
            if len(calls) == 2:
                self.now += timedelta(minutes=3)
            return original(session, scope)

        self.service.material_witness_port = witness
        with self.assertRaises(LifecycleError) as error:
            call()
        self.assertEqual(error.exception.status_code, 409)
        self.assert_unchanged(operation, before)

    def test_end_witness_read_cannot_bypass_final_reviewer_guard(self):
        from models.tables import IdentityAccount

        operation, call = self.phase_call("action")
        before = self.record_state(operation)
        original = self.service.material_witness_port
        calls = []

        def witness(session, scope):
            calls.append(scope)
            if len(calls) == 2:
                session.get(
                    IdentityAccount, "reviewer", populate_existing=True
                ).authentication_version += 1
                session.flush()
            return original(session, scope)

        self.service.material_witness_port = witness
        with self.assertRaises(LifecycleError) as error:
            call()
        self.assertEqual(error.exception.status_code, 409)
        self.assert_unchanged(operation, before)
        with self.factory() as session:
            self.assertEqual(
                session.get(IdentityAccount, "reviewer").authentication_version, 1
            )

    def test_end_witness_cannot_supersede_a_required_receipt_without_detection(self):
        from models.repositories import infra_automation_decisions as decisions

        operation, call = self.phase_call("prepare")
        before = self.record_state(operation)
        original = self.service.material_witness_port
        samples = []

        def witness(session, scope):
            samples.append(scope)
            if len(samples) == 2:
                old = decisions.get_request(session, self.approval["id"])
                decisions.create_request(
                    session,
                    self.material.binding,
                    run_id=self.run.id,
                    step_id="decision",
                    requested_by="human-a",
                    report_bytes=old.report_bytes,
                    now=self.now,
                )
            return original(session, scope)

        self.service.material_witness_port = witness
        with self.assertRaises(LifecycleError) as error:
            call()
        self.assertEqual(error.exception.status_code, 409)
        self.assert_unchanged(operation, before)
        with self.factory() as session:
            latest = decisions.list_latest_for_run(session, self.run.id)
            self.assertIn(self.approval["id"], {row.id for row in latest})


class HandoffMetadataCapacityTests(LifecycleCase):
    """Retained-copy quotas reserve bounded scalar growth before authority exists."""

    enable = HandoffServiceTests.enable
    publish_fixture = HandoffServiceTests.publish_fixture
    setUp = HandoffServiceTests.setUp
    deliver = HandoffServiceTests.deliver
    request = HandoffServiceTests.request
    prepare = HandoffServiceTests.prepare
    dispatch = HandoffServiceTests.dispatch
    retained = HandoffStorageCapacityTests.retained

    def retained_records_size(self, operation_id):
        from services.infra_automation_handoffs import _retained_size

        with self.factory() as session:
            records = [
                session.get(InfraAutomationHandoff, operation_id),
                session.get(InfraAutomationOutbox, operation_id),
                session.scalar(select(InfraAutomationGrant)),
            ]
            return _retained_size(
                *[
                    {
                        column.name: getattr(row, column.name)
                        for column in row.__table__.columns
                    }
                    for row in records
                ]
            )

    def test_prepared_reservation_covers_all_later_metadata_growth(self):
        initial, _ = self.retained()
        operation = self.prepare()
        self.assertGreaterEqual(
            self.retained()[0] - initial, self.retained_records_size(operation["id"])
        )
        self.dispatch(operation)
        self.assertGreaterEqual(
            self.retained()[0] - initial, self.retained_records_size(operation["id"])
        )
        envelope = self.sent[0]
        self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        for _ in range(10):
            self.now += timedelta(seconds=1)
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertGreaterEqual(
            self.retained()[0] - initial, self.retained_records_size(operation["id"])
        )

    def test_exact_receipt_quota_never_undercounts_retained_metadata(self):
        from infra_automation.receiver_protocol import receiver_message_bytes
        from infra_automation.state import EngineBounds
        from services.infra_automation_handoffs import _message

        initial, _ = self.retained()
        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        with self.factory() as session:
            raw = receiver_message_bytes(
                _message(
                    session.get(InfraAutomationHandoff, operation["id"]),
                    operation="receipt",
                )
            )
        ceiling = self.retained()[0] + len(raw)
        with patch(
            "config.engine_bounds",
            return_value=EngineBounds(project_bytes=ceiling, global_bytes=ceiling),
        ):
            self.handoffs.consume(
                envelope.message_bytes, envelope.grant_token, self.receiver
            )
        self.assertEqual(self.retained()[0], ceiling)
        self.assertLessEqual(
            self.retained_records_size(operation["id"]), ceiling - initial
        )

    def test_one_byte_missing_receipt_capacity_rolls_back_consumption(self):
        from infra_automation.receiver_protocol import receiver_message_bytes
        from infra_automation.state import EngineBounds
        from services.infra_automation_handoffs import _message

        operation = self.prepare()
        self.dispatch(operation)
        envelope = self.sent[0]
        before = self.retained()
        recorded = self.handoffs.receiver_status(operation["id"], self.receiver)
        with self.factory() as session:
            raw = receiver_message_bytes(
                _message(
                    session.get(InfraAutomationHandoff, operation["id"]),
                    operation="receipt",
                )
            )
        for bound in ("project_bytes", "global_bytes"):
            with self.subTest(bound=bound):
                with patch(
                    "config.engine_bounds",
                    return_value=EngineBounds(**{bound: before[0] + len(raw) - 1}),
                ):
                    with self.assertRaises(LifecycleError) as error:
                        self.handoffs.consume(
                            envelope.message_bytes, envelope.grant_token, self.receiver
                        )
                self.assertEqual(error.exception.status_code, 429)
                self.assertEqual(self.retained(), before)
                self.assertEqual(
                    self.handoffs.receiver_status(operation["id"], self.receiver),
                    recorded,
                )
