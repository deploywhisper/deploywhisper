"""Captured typed target/environment references resolve without rewriting identity."""

from __future__ import annotations

from unittest.mock import patch

from infra_automation.run_resolution import runtime_workflow, resolve_target_value
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_targets as targets
from services import infra_automation_support as support
from tests.test_infra_automation import test_target_admission as fixture
from tests.test_infra_automation import test_approval_eligibility as definitions


class TargetReferenceTests(fixture.TargetAdmissionTests):
    def test_bound_input_and_run_references_acquire_canonical_lock_before_collection(
        self,
    ):
        self.register()
        original = definitions.ApprovalEligibilityTests.workflow

        def referenced(case):
            value = original(case)
            value.setdefault("inputs", {}).update(
                {
                    "target_alias": {
                        "type": "identifier",
                        "required": False,
                        "default": "TARGET-ONE",
                    },
                    "environment_name": {
                        "type": "identifier",
                        "required": False,
                        "default": "test",
                    },
                }
            )
            value["environment"] = {"ref": "input", "name": "environment_name"}
            for step in value["steps"]:
                if "environment" in step:
                    step["environment"] = {"ref": "run", "field": "environment"}
            return value

        with patch.object(definitions.ApprovalEligibilityTests, "workflow", referenced):
            request = self.request({"ref": "input", "name": "target_alias"})
        result = self.admit(request)
        from infra_automation.lifecycle import SnapshotDocument

        with self.factory() as session:
            row = runs.get_run(session, result["id"])
            raw = row.snapshot_bytes
            doc = SnapshotDocument.model_validate_json(raw)
            capture = targets.get_run_target(session, row.id, "handoff")
            self.assertEqual(capture.requested_alias, "TARGET-ONE")
            self.assertEqual(capture.target_id, "target")
            self.assertEqual(targets.get_held_lock(session, "target").run_id, row.id)
            resolved = runtime_workflow(doc)
            self.assertEqual(
                resolve_target_value(doc, doc.definition.steps[-1].target_id),
                "TARGET-ONE",
            )
            self.assertEqual(resolved.steps[-1].target_id, "TARGET-ONE")
            self.assertEqual(resolved.steps[-1].environment, "test")
            self.assertEqual(doc.definition.steps[-1].target_id.ref, "input")
            self.assertEqual(row.snapshot_bytes, raw)
            self.assertEqual(support.digest(raw), row.snapshot_digest)
