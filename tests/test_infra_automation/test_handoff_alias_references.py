"""Real decision and handoff services resolve aliases without changing identity."""

from __future__ import annotations

import json
from unittest.mock import patch

from sqlalchemy import select

from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_targets as targets
from models.repositories import infra_automation_workflows as workflows
from models.tables import InfraAutomationGrant, InfraAutomationHandoff
from services import infra_automation_support as support
from services import project_service as authorization
from tests.test_infra_automation import test_approval_eligibility as definitions
from tests.test_infra_automation import test_handoff_service as fixture
from tests.test_infra_automation.lifecycle_support import LifecycleCase


class _AliasHandoffFixture(LifecycleCase):
    """Reuse setup and ports explicitly, without inheriting fixture test methods."""

    target_aliases = ("production",)
    use_input = False
    enable = fixture.HandoffServiceTests.enable
    publish_fixture = fixture.HandoffServiceTests.publish_fixture
    deliver = fixture.HandoffServiceTests.deliver
    request = fixture.HandoffServiceTests.request
    prepare = fixture.HandoffServiceTests.prepare
    dispatch = fixture.HandoffServiceTests.dispatch

    def setUp(self):
        original = definitions.ApprovalEligibilityTests.workflow

        def aliased(case):
            definition = original(case)
            target = "PRODUCTION"
            if self.use_input:
                definition["inputs"] = {
                    "target_alias": {
                        "type": "identifier",
                        "required": False,
                        "default": "PRODUCTION",
                    },
                    "environment_name": {
                        "type": "identifier",
                        "required": False,
                        "default": "test",
                    },
                }
                target = {"ref": "input", "name": "target_alias"}
                definition["environment"] = {
                    "ref": "input",
                    "name": "environment_name",
                }
            for step in definition["steps"]:
                if "target_id" in step:
                    step["target_id"] = target
                    step["environment"] = {"ref": "run", "field": "environment"}
            return definition

        with patch.object(definitions.ApprovalEligibilityTests, "workflow", aliased):
            fixture.HandoffServiceTests.setUp(self)

    def exercise_round_trip(self):
        original_snapshot = self.run.snapshot_bytes
        original_snapshot_digest = self.run.snapshot_digest
        original_definition_digest = self.run.definition_digest
        original_definition = self.document.definition.model_dump(mode="json")
        with self.factory() as session:
            revision = workflows.get_revision(session, self.run.revision_id)
            original_publication = revision.canonical_definition
            self.assertEqual(revision.digest, original_definition_digest)
            capture = targets.get_run_target(session, self.run.id, "handoff")
            self.assertEqual(
                (capture.requested_alias, capture.target_id), ("PRODUCTION", "target")
            )
            self.assertEqual(targets.resolve_alias(session, "production").id, "target")

        self.assertEqual(self.approval["status"], "approved")
        self.assertEqual(self.material.binding.canonical_target, "target")
        self.assertEqual(self.material.binding.environment, "test")
        with self.credentials(), authorization.authorized_session() as session:
            self.assertTrue(
                self.service.recheck_approved(
                    session, self.approval["id"], phase="dispatch"
                ).eligible
            )

        operation = self.prepare()
        self.assertEqual(operation["target_id"], "target")
        dispatched = self.dispatch(operation)
        self.assertEqual(dispatched["state"], "delivery_unknown")
        self.assertEqual(len(self.sent), 1)
        envelope = self.sent[0]
        receipt = self.handoffs.consume(
            envelope.message_bytes, envelope.grant_token, self.receiver
        )
        self.assertEqual(receipt["receipt"]["sequence"], 1)
        self.assertEqual(
            self.handoffs.authorize_action(operation["id"], self.receiver)["state"],
            "consumed",
        )

        with self.factory() as session:
            current = runs.get_run(session, self.run.id)
            self.assertEqual(current.snapshot_bytes, original_snapshot)
            self.assertEqual(current.snapshot_digest, original_snapshot_digest)
            self.assertEqual(current.definition_digest, original_definition_digest)
            self.assertEqual(
                support.digest(current.snapshot_bytes), current.snapshot_digest
            )
            retained_document = json.loads(current.snapshot_bytes)
            self.assertEqual(retained_document["definition"], original_definition)
            retained_revision = workflows.get_revision(session, self.run.revision_id)
            self.assertEqual(
                retained_revision.canonical_definition, original_publication
            )
            self.assertEqual(
                support.digest(original_publication), retained_revision.digest
            )
            captured = targets.get_run_target(session, self.run.id, "handoff")
            self.assertEqual(
                (captured.requested_alias, captured.target_id), ("PRODUCTION", "target")
            )
            retained = session.get(InfraAutomationHandoff, operation["id"])
            grant = session.scalar(select(InfraAutomationGrant))
            self.assertEqual(retained.target_id, "target")
            self.assertEqual(grant.status, "consumed")
            self.assertEqual(targets.get_lock(session, captured.lock_id).status, "held")


class LiteralAliasHandoffTests(_AliasHandoffFixture):
    def test_uppercase_literal_alias_and_run_environment_complete_handoff(self):
        self.exercise_round_trip()
        self.assertEqual(self.document.definition.steps[-1].target_id, "PRODUCTION")
        self.assertEqual(self.document.definition.steps[-1].environment.ref, "run")


class InputAliasHandoffTests(_AliasHandoffFixture):
    use_input = True

    def test_default_input_alias_and_run_environment_complete_handoff(self):
        self.exercise_round_trip()
        self.assertEqual(self.document.inputs["target_alias"], "PRODUCTION")
        self.assertEqual(self.document.definition.steps[-1].target_id.ref, "input")
        self.assertEqual(self.document.definition.steps[-1].environment.ref, "run")
        self.assertEqual(self.document.definition.environment.ref, "input")
