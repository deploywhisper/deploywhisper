"""Saved-plan digest receipts reuse receiver fences without executing a plan."""

from __future__ import annotations

import json
import sqlite3
import unittest

from infra_automation.receiver_custody import canonical, digest
from infra_automation.receiver_protocol import ReceiverMessage, receiver_binding_digest
from infra_automation.receiver_runtime import ReferenceReceiver, ReceiverConflict
from tests.test_infra_automation import test_receiver_runtime as fixture_runtime

SECRET = fixture_runtime.SECRET


class CollectionReceiverTests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_runtime.RuntimeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.raw = b"PK\x03\x04opaque-synthetic-saved-plan-fixture\x00"
        source = fixture.message.binding.provenance.source.model_dump(mode="json")
        record = fixture.receiver.custody.publish(
            "saved-plan", self.raw, source, fixture.message.binding.evidence_deadline
        )
        value = fixture.message.binding.model_dump(mode="json")
        value["provenance"]["custody"] = record.model_dump(mode="json")
        payload = {"version": 1, "receiver_action": "saved_plan_receipt"}
        value["payload_digest"] = digest(canonical(payload))
        self.message = ReceiverMessage.model_validate(
            {
                **fixture.message.model_dump(mode="json"),
                "binding": value,
                "binding_digest": receiver_binding_digest(value),
            }
        )
        spec = {
            "message": self.message.model_dump(mode="json"),
            "payload": payload,
            "grant_token": "never-store-grant",
            "run_id": "synthetic-run",
        }
        (fixture.directory / "bootstrap.json").write_text(json.dumps(spec))
        self.server = fixture_runtime.Server(fixture.directory)

    def receiver(self, **kwargs):
        return ReferenceReceiver(self.fixture.root, self.server, SECRET, **kwargs)

    def run_receiver(self, receiver):
        return receiver.run(self.message.operation_id, self.message.binding_digest)

    def test_default_denies_saved_bytes_before_consume(self):
        with self.assertRaises(ValueError):
            self.run_receiver(self.receiver())
        self.assertEqual(self.fixture.calls("consume"), 0)

    def test_saved_plan_receipt_is_harmless_durable_and_explicit(self):
        first = self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        second = self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        self.assertEqual(first, second)
        self.assertEqual(first["counted_actions"], 0)
        self.assertEqual(first["verified_plan_receipts"], 1)
        self.assertEqual(first["verified_plan_digest"], digest(self.raw))
        self.assertFalse(first["deployment_performed"])
        self.assertEqual(self.fixture.calls("consume"), 1)
        with self.assertRaises(ReceiverConflict):
            self.run_receiver(self.receiver())

    def test_mode_requires_approved_payload_selection(self):
        self.server.spec["payload"] = {"version": 1, "synthetic": True}
        with self.assertRaises(ReceiverConflict):
            self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        self.assertEqual(self.fixture.calls("consume"), 0)

    def test_restart_rechecks_tampered_custody_before_receipt(self):
        def checkpoint(name):
            if name == "local_receipt":
                raise RuntimeError("synthetic restart")

        with self.assertRaises(RuntimeError):
            self.run_receiver(
                self.receiver(action_mode="saved_plan_receipt", checkpoint=checkpoint)
            )
        artifact = self.fixture.root / "custody/saved-plan/artifact"
        artifact.chmod(0o600)
        artifact.write_bytes(b"changed")
        artifact.chmod(0o400)
        with self.assertRaises(ValueError):
            self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        self.assertEqual(self.fixture.calls("consume"), 1)
        with sqlite3.connect(self.fixture.root / "receiver.sqlite3") as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM saved_plan_receipts").fetchone()[0], 0
            )

    def test_unknown_action_mode_is_rejected(self):
        for mode in ("apply", "destroy", None, 1):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.receiver(action_mode=mode)

    def test_receipt_fence_restart_reconciles_without_repeat(self):
        def checkpoint(name):
            if name == "effect":
                raise RuntimeError("synthetic crash after digest receipt")

        with self.assertRaises(RuntimeError):
            self.run_receiver(
                self.receiver(action_mode="saved_plan_receipt", checkpoint=checkpoint)
            )
        result = self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        self.assertEqual(result["phase"], "reconcile")
        self.assertEqual(result["verified_plan_receipts"], 1)
        self.assertEqual(result["counted_actions"], 0)
        self.assertFalse(result["deployment_performed"])
        self.assertEqual(self.fixture.calls("consume"), 1)
        self.assertEqual(self.fixture.calls("authorize"), 1)

    def production_payload(self):
        from infra_automation.decisions import DecisionBinding
        from infra_automation.receiver_protocol import receiver_binding_from_decision
        from infra_automation.targets import semantic_payload
        from tests.test_infra_automation.test_github_adapter import envelope_fixture

        snapshot, _ = envelope_fixture()
        target = snapshot.definition
        value = self.message.binding.model_dump(mode="json")
        value.update(
            project_id=100,
            workspace_id=200,
            revision_id="revision-1",
            pipeline_repository_id=target.pipeline_repository_id,
            pipeline_workflow_id=target.pipeline_workflow_id,
            pipeline_workflow_revision=target.pipeline_workflow_revision,
        )
        decision = DecisionBinding.model_validate_json(json.dumps(value))
        payload = json.loads(semantic_payload(decision, snapshot))
        decision = decision.model_copy(
            update={"payload_digest": digest(canonical(payload))}
        )
        binding = receiver_binding_from_decision(decision)
        self.message = ReceiverMessage.model_validate(
            {
                **self.message.model_dump(mode="json"),
                "binding": binding.model_dump(mode="json"),
                "binding_digest": receiver_binding_digest(binding),
            }
        )
        self.server.spec["message"] = self.message.model_dump(mode="json")
        self.server.spec["payload"] = payload
        return payload

    def test_production_canonical_payload_verifies_exact_plan_on_restart(self):
        payload = self.production_payload()
        self.assertNotIn("receiver_action", payload)
        result = self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        again = self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        self.assertEqual(result, again)
        self.assertEqual(result["verified_plan_digest"], digest(self.raw))
        self.assertEqual(result["verified_plan_receipts"], 1)
        self.assertFalse(result["deployment_performed"])
        self.assertEqual(self.fixture.calls("consume"), 1)

    def test_production_payload_embedded_decision_must_match_outer_binding(self):
        payload = self.production_payload()
        payload["decision"]["receiver_id"] = "different-receiver"
        value = self.message.binding.model_dump(mode="json")
        value["payload_digest"] = digest(canonical(payload))
        self.message = ReceiverMessage.model_validate(
            {
                **self.message.model_dump(mode="json"),
                "binding": value,
                "binding_digest": receiver_binding_digest(value),
            }
        )
        self.server.spec["message"] = self.message.model_dump(mode="json")
        with self.assertRaises(ReceiverConflict):
            self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        self.assertEqual(self.fixture.calls("consume"), 0)

    def test_malformed_registered_receipt_payload_denies_before_consume(self):
        for field, invalid in (
            ("version", True),
            ("kind", "apply"),
            ("decision", None),
            ("destination", []),
        ):
            with self.subTest(field=field):
                payload = self.production_payload()
                payload[field] = invalid
                value = self.message.binding.model_dump(mode="json")
                value["payload_digest"] = digest(canonical(payload))
                self.message = ReceiverMessage.model_validate(
                    {
                        **self.message.model_dump(mode="json"),
                        "binding": value,
                        "binding_digest": receiver_binding_digest(value),
                    }
                )
                self.server.spec["message"] = self.message.model_dump(mode="json")
                with self.assertRaises(ReceiverConflict):
                    self.run_receiver(self.receiver(action_mode="saved_plan_receipt"))
        self.assertEqual(self.fixture.calls("consume"), 0)
