"""Receiver completion safety checks over the admitted synthetic target fixture."""

from __future__ import annotations
import hashlib
import hmac
import json
from tests.test_infra_automation import test_handoff_service as fixture
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from infra_automation.receiver_http_contracts import (
    CallbackEnvelope,
    callback_signing_bytes,
    source_identity_digest,
)
from infra_automation.receiver_protocol import validate_receiver_message
from infra_automation.lifecycle import LifecycleError


class ReceiverReconciliationTests(LifecycleCase):
    setUp = fixture.HandoffServiceTests.setUp
    enable = fixture.HandoffServiceTests.enable
    publish_fixture = fixture.HandoffServiceTests.publish_fixture
    deliver = fixture.HandoffServiceTests.deliver
    request = fixture.HandoffServiceTests.request
    prepare = fixture.HandoffServiceTests.prepare
    dispatch = fixture.HandoffServiceTests.dispatch

    def callback(self, operation, state="succeeded", sequence=1, nonce="nonce-1"):
        message = validate_receiver_message(
            json.loads(self.sent[0].message_bytes)
            | {
                "operation": "outcome"
                if state in {"succeeded", "failed", "delivery_unknown"}
                else "status",
                "state": state,
                "sequence": 2,
            }
        )
        values = dict(
            version=1,
            operation_id=operation["id"],
            run_id=operation["run_id"],
            binding_digest=operation["receiver_binding_digest"],
            source_identity_digest=source_identity_digest(message.binding),
            nonce=nonce,
            sequence=sequence,
            message=message.model_dump(mode="json"),
            signature="sha256:" + "0" * 64,
        )
        values["signature"] = (
            "sha256:"
            + hmac.new(
                self.receiver.secret.encode(),
                callback_signing_bytes(values),
                hashlib.sha256,
            ).hexdigest()
        )
        return CallbackEnvelope.model_validate(values)

    def test_bootstrap_is_exact_and_consumption_receipt_recovers_after_disable(self):
        operation = self.prepare()
        self.dispatch(operation)
        bootstrap = self.handoffs.bootstrap(
            operation["id"], operation["receiver_binding_digest"], self.receiver
        )
        self.assertEqual(bootstrap["message"], json.loads(self.sent[0].message_bytes))
        self.handoffs.consume(
            bootstrap["message"], bootstrap["grant_token"], self.receiver
        )
        from unittest.mock import patch

        with patch.object(self.handoffs, "_live", side_effect=LifecycleError(409)):
            recovered = self.handoffs.receiver_status(operation["id"], self.receiver)
            self.assertEqual(recovered["receipt"]["state"], "consumed")
            with self.assertRaises(LifecycleError):
                self.handoffs.authorize_action(operation["id"], self.receiver)

    def test_signed_callback_replay_is_fenced_and_terminal_is_retained(self):
        operation = self.prepare()
        self.dispatch(operation)
        self.handoffs.consume(
            self.sent[0].message_bytes, self.sent[0].grant_token, self.receiver
        )
        callback = self.callback(operation)
        result = self.handoffs.callback(callback, self.receiver)
        self.assertEqual(result["state"], "succeeded")
        with self.assertRaises(LifecycleError):
            self.handoffs.callback(callback, self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver)["state"],
            "succeeded",
        )

    def test_invalid_signature_and_source_cannot_change_state(self):
        operation = self.prepare()
        self.dispatch(operation)
        self.handoffs.consume(
            self.sent[0].message_bytes, self.sent[0].grant_token, self.receiver
        )
        callback = self.callback(operation)
        for altered in (
            callback.model_copy(update={"signature": "sha256:" + "f" * 64}),
            callback.model_copy(update={"run_id": "other-run"}),
        ):
            with self.assertRaises(Exception):
                self.handoffs.callback(altered, self.receiver)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver)["state"],
            "consumed",
        )

    def test_observation_never_confirms_receiver_success(self):
        from infra_automation.github_contracts import (
            DispatchAcceptance,
            GithubRunObservation,
        )
        from infra_automation.receiver_http_contracts import ReconcileRequest

        definition = self.snapshot.definition

        def delivery(envelope, credential):
            return DispatchAcceptance(
                operation_id=envelope.operation_id,
                binding_digest=json.loads(envelope.message_bytes)["binding_digest"],
                repository_id=definition.pipeline_repository_id,
                workflow_id=definition.pipeline_workflow_id,
                workflow_revision=definition.pipeline_workflow_revision,
                workflow_ref=definition.workflow_ref,
                run_id=1,
                run_url="https://api.github.com/repos/owner/repository/actions/runs/1",
                html_url="https://github.com/owner/repository/actions/runs/1",
            )

        self.handoffs.delivery_port = delivery
        self.handoffs.observation_port = lambda acceptance, snapshot: (
            GithubRunObservation(
                **acceptance.model_dump(
                    exclude={"state", "operation_id", "binding_digest"}
                ),
                status="completed",
                conclusion="success",
            )
        )
        operation = self.prepare()
        operation = self.dispatch(operation)
        with self.credentials():
            result = self.handoffs.reconcile(
                operation["id"],
                ReconcileRequest(
                    project_id=100,
                    workspace_id=100,
                    expected_version=operation["version"],
                    reason="Observe carrier facts",
                ),
            )
        self.assertEqual(result["acceptance"]["state"], "accepted")
        self.assertEqual(result["observation"]["conclusion"], "success")
        self.assertIsNone(result["verified_outcome"])
        self.assertEqual(result["lock_status"], "held")

    def test_signed_completion_cannot_release_lock_with_uncertain_sibling(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from models.repositories import infra_automation_targets as registry

        operation = self.prepare()
        self.dispatch(operation)
        self.handoffs.consume(
            self.sent[0].message_bytes, self.sent[0].grant_token, self.receiver
        )
        with self.factory() as session:
            capture = registry.list_run_targets(session, operation["run_id"])[0]
        sibling = SimpleNamespace(
            run_id=capture.run_id, handoff_step_id="sibling", lock_id=capture.lock_id
        )
        with patch.object(
            registry, "list_run_targets", return_value=[capture, sibling]
        ):
            self.handoffs.callback(self.callback(operation), self.receiver)
        with self.factory() as session:
            self.assertEqual(registry.get_lock(session, capture.lock_id).status, "held")
            from models.repositories import infra_automation_runs

            self.assertEqual(
                infra_automation_runs.get_run(session, operation["run_id"]).state,
                "external_running",
            )

    def test_callback_never_regresses_parent_clock_after_cancellation(self):
        from datetime import timedelta
        from sqlalchemy import update
        from models.tables import InfraAutomationRun
        from models.repositories import infra_automation_runs

        operation = self.prepare()
        self.dispatch(operation)
        self.handoffs.consume(
            self.sent[0].message_bytes, self.sent[0].grant_token, self.receiver
        )
        future = self.now + timedelta(seconds=20)
        with self.factory.begin() as session:
            session.execute(
                update(InfraAutomationRun)
                .where(InfraAutomationRun.id == operation["run_id"])
                .values(
                    cancel_requested=True,
                    cancellation_requested_at=future,
                    last_observed_at=future,
                    version=InfraAutomationRun.version + 1,
                )
            )
        self.now += timedelta(seconds=15)
        with self.assertRaises(LifecycleError):
            self.handoffs.callback(self.callback(operation), self.receiver)
        with self.factory() as session:
            parent = infra_automation_runs.get_run(session, operation["run_id"])
            self.assertEqual(infra_automation_runs.utc(parent.last_observed_at), future)
        self.assertEqual(
            self.handoffs.receiver_status(operation["id"], self.receiver)["state"],
            "consumed",
        )

    def test_signed_terminal_completes_real_handoff_attempt_and_guarded_parent(self):
        from infra_automation.contracts import STEP_CONTRACTS
        from infra_automation.state import OutputReference
        from models.tables import InfraAutomationAttempt
        from models.repositories import infra_automation_runs

        operation = self.prepare()
        self.dispatch(operation)
        self.handoffs.consume(
            self.sent[0].message_bytes, self.sent[0].grant_token, self.receiver
        )
        with self.factory.begin() as session:
            attempts = infra_automation_runs.list_attempts(
                session, run_id=operation["run_id"]
            )
            template = attempts[0]
            existing = {attempt.step_id: attempt for attempt in attempts}
            for step in self.document.definition.steps:
                attempt = existing.get(step.id)
                if attempt is None:
                    values = {
                        column.name: getattr(template, column.name)
                        for column in InfraAutomationAttempt.__table__.columns
                        if column.name != "sequence"
                    }
                    values.update(
                        id="completion-" + step.id,
                        step_id=step.id,
                        step_kind=step.kind,
                        output_json=None,
                        output_digest=None,
                    )
                    attempt = InfraAutomationAttempt(**values)
                    session.add(attempt)
                if step.kind == "registered_github_handoff":
                    attempt.state = "running"
                    attempt.output_json = attempt.output_digest = None
                else:
                    output = OutputReference(
                        kind=STEP_CONTRACTS[step.kind].output,
                        reference="completed-" + step.id,
                        digest="sha256:" + "a" * 64,
                    )
                    attempt.state = "succeeded"
                    attempt.output_json = output.model_dump_json()
                    attempt.output_digest = output.digest
        self.handoffs.callback(self.callback(operation), self.receiver)
        with self.factory() as session:
            parent = infra_automation_runs.get_run(session, operation["run_id"])
            self.assertEqual(parent.state, "succeeded")
            handoff = [
                a
                for a in infra_automation_runs.list_attempts(session, run_id=parent.id)
                if a.step_id == "handoff"
            ][0]
            self.assertEqual(handoff.state, "succeeded")
            self.assertIsNone(handoff.output_json)

    def test_uncertain_started_action_cannot_receive_new_action_admission(self):
        operation = self.prepare()
        self.dispatch(operation)
        self.handoffs.consume(
            self.sent[0].message_bytes, self.sent[0].grant_token, self.receiver
        )
        self.handoffs.callback(
            self.callback(operation, state="delivery_unknown"), self.receiver
        )
        with self.assertRaises(LifecycleError):
            self.handoffs.authorize_action(operation["id"], self.receiver)
        self.assertIsNotNone(
            self.handoffs.receiver_status(operation["id"], self.receiver)["receipt"]
        )

    def test_uncertainty_and_cancellation_history_never_reopens_action_authority(self):
        for first, regression in (
            ("delivery_unknown", "accepted"),
            ("cancel_requested", "running"),
            ("running", "accepted"),
        ):
            with self.subTest(first=first, regression=regression):
                case = ReceiverReconciliationTests(methodName="runTest")
                case.setUp()
                try:
                    operation = case.prepare()
                    case.dispatch(operation)
                    case.handoffs.consume(
                        case.sent[0].message_bytes,
                        case.sent[0].grant_token,
                        case.receiver,
                    )
                    case.handoffs.callback(
                        case.callback(operation, state=first), case.receiver
                    )
                    with case.assertRaises(LifecycleError) as rejected:
                        case.handoffs.callback(
                            case.callback(
                                operation, state=regression, sequence=2, nonce="nonce-2"
                            ),
                            case.receiver,
                        )
                    case.assertEqual(rejected.exception.status_code, 409)
                    with case.assertRaises(LifecycleError):
                        case.handoffs.authorize_action(operation["id"], case.receiver)
                    view = case.handoffs.callback(
                        case.callback(
                            operation, state="failed", sequence=2, nonce="terminal-2"
                        ),
                        case.receiver,
                    )
                    case.assertEqual(view["state"], "failed")
                finally:
                    case.tearDown()
                    case.doCleanups()

    def test_human_http_handoff_relation_uses_selected_scope(self):
        from unittest.mock import patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.infra_automation import router

        operation = self.prepare()
        app = FastAPI()
        app.include_router(router)
        with (
            patch("api.dependencies.identity_service", return_value=self.identity),
            patch("services.infra_automation_handoffs._default_service", self.handoffs),
            TestClient(app, base_url=self.origin) as client,
        ):
            headers = {
                "Cookie": "__Host-dw-session=" + self.tokens["human-a"][0],
                "Origin": self.origin,
            }
            response = client.get(
                f"/api/v1/infra-automation/runs/{operation['run_id']}/handoffs?project_id=100&workspace_id=100",
                headers=headers,
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["data"]["items"][0]["id"], operation["id"])
            response = client.get(
                f"/api/v1/infra-automation/runs/{operation['run_id']}/handoffs?project_id=200&workspace_id=200",
                headers=headers,
            )
            self.assertEqual(response.status_code, 403, response.text)


class ReceiverHttpRuntimeIntegrationTests(ReceiverReconciliationTests):
    """Actual HTTP adapter, durable receiver ledger and protected synthetic custody."""

    def setUp(self):
        from unittest.mock import patch

        self.synthetic_raw = b"deploywhisper-synthetic-v1\nhttp-integration\n"
        context = patch(
            "tests.test_infra_automation.test_decision_service.D",
            "sha256:" + hashlib.sha256(self.synthetic_raw).hexdigest(),
        )
        context.start()
        self.addCleanup(context.stop)
        context2 = patch(
            "tests.test_infra_automation.test_approval_eligibility.DIGEST",
            "sha256:" + hashlib.sha256(self.synthetic_raw).hexdigest(),
        )
        context2.start()
        self.addCleanup(context2.stop)
        super().setUp()

    def test_real_receiver_uses_authenticated_http_and_counts_one_action(self):
        import tempfile
        from pathlib import Path
        from dataclasses import replace
        from unittest.mock import patch
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.infra_automation_receiver import router
        from infra_automation.receiver_runtime import ReferenceReceiver
        from infra_automation.receiver_protocol import validate_receiver_message

        secret = "receiver-secret-" + "x" * 32
        self.receiver = replace(self.receiver, secret=secret)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(
            app,
            base_url="https://testserver",
            headers={
                "authorization": "Bearer " + secret,
                "x-receiver-id": self.receiver.receiver_id,
            },
        )

        class Port:
            def request(inner, operation_id, suffix, payload=None):
                url = f"/api/v1/infra-automation/handoffs/{operation_id}/{suffix}"
                result = (
                    client.get(url)
                    if payload is None
                    else client.post(url, json=payload)
                )
                if result.status_code != 200:
                    raise AssertionError(result.text)
                return result.json()["data"]

            def bootstrap(inner, operation_id, binding_digest):
                return inner.request(
                    operation_id,
                    "receipt",
                    {"version": 1, "binding_digest": binding_digest},
                )

            def consume(inner, message, grant_token):
                return inner.request(
                    message.operation_id,
                    "consume",
                    {
                        "version": 1,
                        "message": message.model_dump(mode="json"),
                        "grant_token": grant_token,
                    },
                )

            def status(inner, operation_id):
                return inner.request(operation_id, "status")

            def authorize_action(inner, operation_id):
                return inner.request(operation_id, "authorize-action", {"version": 1})

            lose_ack = True

            def callback(inner, envelope):
                result = inner.request(envelope["operation_id"], "outcome", envelope)
                if inner.lose_ack:
                    inner.lose_ack = False
                    raise ConnectionError("Lost committed callback response")
                return result

        with (
            patch(
                "config.handoff_credentials",
                return_value={"receiver": secret, "github": "dispatch-secret"},
            ),
            patch("services.infra_automation_handoffs._default_service", self.handoffs),
            tempfile.TemporaryDirectory() as directory,
        ):
            operation = self.prepare()
            self.dispatch(operation)
            message = validate_receiver_message(self.sent[0].message_bytes)
            receiver = ReferenceReceiver(
                Path(directory) / "receiver", Port(), secret.encode()
            )
            custody = message.binding.provenance.custody
            from datetime import datetime

            # The shared decision fixture deliberately advances its clock by one
            # second. Custody must use that same clock, not depend on test speed.
            with patch(
                "infra_automation.receiver_custody.datetime", wraps=datetime
            ) as clock:
                clock.now.return_value = self.now
                receiver.custody.publish(
                    custody.handle,
                    self.synthetic_raw,
                    message.binding.provenance.source.model_dump(mode="json"),
                    custody.expires_at,
                )
            result = receiver.run(operation["id"], operation["receiver_binding_digest"])
            self.assertEqual(result["counted_actions"], 1)
            self.assertTrue(result["callback_delivered"])
            replay = receiver.run(operation["id"], operation["receiver_binding_digest"])
            self.assertEqual(replay["counted_actions"], 1)
            view = Port().status(operation["id"])
            self.assertEqual(view["state"], "succeeded")
            self.assertEqual(view["receipt"], result["receipt"])
