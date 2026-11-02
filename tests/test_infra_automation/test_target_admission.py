"""Precollection canonical target admission; no collector or network is invoked."""

from __future__ import annotations

import copy
from datetime import timedelta
import json
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import object_session

from infra_automation import claims
from infra_automation.contracts import ProfileContract, RegistryContract
from infra_automation.lifecycle import AutomationSettings, LifecycleError
from infra_automation.state import CancelRunRequest, RunRequest
from infra_automation.targets import BreakLockRequest, RegisterTargetRequest
from infra_automation.workflow_schema import Workflow
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_targets as target_repository
from models.repositories import infra_automation_workflows as workflows
from models.tables import (
    InfraAutomationAudit,
    InfraAutomationRun,
    InfraAutomationRunRequest,
    InfraAutomationRunTarget,
    InfraAutomationTargetLock,
)
from services import infra_automation_engine_service as engine
from services import infra_automation_support as support
from services import infra_automation_targets as targets
from services import project_service as authorization
from tests.test_infra_automation import test_approval_eligibility as eligibility_tests
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation.test_target_contracts import definition_payload


class AdmissionHandlers:
    """Trusted availability double; calling a handler is an explicit test failure."""

    def get(self, kind):
        def forbidden(*args, **kwargs):
            raise AssertionError("Admission must not execute collection or handlers")

        return forbidden


class TargetAdmissionTests(LifecycleCase):
    enable = snapshot_tests.WorkflowSnapshotTests.enable

    def setUp(self):
        super().setUp()
        self.member("admin", project=200)
        self.enable()
        with self.factory.begin() as session:
            workflows.save_policy(
                session,
                project_id=200,
                expected_version=0,
                settings_json=AutomationSettings(enabled=True).model_dump_json(),
            )
        self.handlers = AdmissionHandlers()
        self.registry = RegistryContract(
            profiles=(
                ProfileContract(
                    digest=eligibility_tests.DIGEST,
                    tool="opentofu",
                    authorization_kinds=("exact_plan",),
                ),
            )
        )

    def register(
        self,
        target_id="target",
        *,
        scopes=(100, 200),
        expected_version=0,
        enabled=True,
        now=None,
    ):
        payload = {
            **definition_payload(),
            "canonical_target": target_id,
            "aliases": [target_id + "-one", target_id + "-two"],
            "allowed_scopes": [
                {"project_id": project, "workspace_id": project} for project in scopes
            ],
            "environment": "test",
            "enabled": enabled,
        }
        request = RegisterTargetRequest.model_validate_json(
            json.dumps(
                {
                    "project_id": scopes[0],
                    "workspace_id": scopes[0],
                    "expected_version": expected_version,
                    "definition": payload,
                    "reason": "Register owned synthetic admission destination",
                }
            )
        )
        with self.credentials():
            return targets.register_target(request, now=now or self.now)

    def request(self, *aliases, project=100, key="admit"):
        definition = eligibility_tests.ApprovalEligibilityTests().workflow()
        definition.update(project_id=str(project), workspace_id=str(project))
        branch = definition["steps"]
        definition["steps"] = []
        for index, alias in enumerate(aliases):
            steps = copy.deepcopy(branch)
            suffix = "" if index == 0 else f"_{index}"
            for step in steps:
                step["id"] += suffix
                step["depends_on"] = [item + suffix for item in step["depends_on"]]
                if "target_id" in step:
                    step["target_id"] = alias
                for value in step.values():
                    if isinstance(value, dict) and value.get("ref") == "step":
                        value["step_id"] += suffix
            definition["steps"].extend(steps)
        # Reuse the published snapshot fixture for its original scope; reproduce
        # that fixture's immutable publication for the second real project.
        if project == 100:
            ids = snapshot_tests.WorkflowSnapshotTests.publish_fixture(self, definition)
        else:
            raw = support.canonical(
                Workflow.model_validate(definition).model_dump(mode="json")
            )
            with self.factory.begin() as session:
                workflow = workflows.create_workflow(
                    session,
                    project_id=project,
                    workspace_id=project,
                    name="Target admission fixture",
                    canonical_definition=raw,
                    digest=support.digest(raw),
                    created_by="human-a",
                )
                revision = workflows.append_revision(
                    session,
                    workflow_id=workflow.id,
                    project_id=project,
                    workspace_id=project,
                    revision_number=1,
                    canonical_definition=raw,
                    digest=support.digest(raw),
                    published_by="human-a",
                    idempotency_key_digest=support.digest(workflow.id.encode()),
                    request_digest=support.digest(raw),
                )
                ids = workflow.id, revision.id
        return RunRequest(
            workflow_id=ids[0],
            revision_id=ids[1],
            workspace_id=project,
            inputs={},
            idempotency_key=key,
            reason="Admit synthetic registered handoff",
        )

    def admit(self, request, *, now=None):
        with self.credentials():
            return engine.request_run(
                request,
                registry=self.handlers,
                registry_contract=self.registry,
                now=now or self.now,
            )

    def counts(self):
        with self.factory() as session:
            return tuple(
                session.scalar(select(func.count()).select_from(model))
                for model in (
                    InfraAutomationRun,
                    InfraAutomationRunRequest,
                    InfraAutomationAudit,
                    InfraAutomationTargetLock,
                    InfraAutomationRunTarget,
                )
            )

    def capture(self, run_id, *, live=True):
        with self.credentials(), authorization.authorized_session() as session:
            return targets.captured_target(session, run_id, "handoff", live=live)

    def test_assigned_scopes_and_aliases_capture_one_lock_before_queued_visibility(
        self,
    ):
        for index, scopes in enumerate(((100,), (100, 200), (200,))):
            with self.subTest(scopes=scopes):
                target_id = f"target-{index}"
                self.register(target_id, scopes=scopes)
                request = self.request(
                    target_id + "-one",
                    target_id + "-two",
                    project=scopes[-1],
                    key=target_id,
                )
                original_view = engine._view

                def before_return(row):
                    session = object_session(row)
                    captures = target_repository.list_run_targets(session, row.id)
                    lock = target_repository.get_held_lock(session, target_id)
                    self.assertEqual(len(captures), 2)
                    self.assertIsNotNone(lock)
                    self.assertEqual(
                        {capture.lock_id for capture in captures}, {lock.id}
                    )
                    self.assertEqual(
                        {capture.target_id for capture in captures}, {target_id}
                    )
                    self.assertEqual(row.state, "queued")
                    with self.factory() as observer:
                        self.assertIsNone(runs.get_run(observer, row.id))
                    return original_view(row)

                with patch.object(engine, "_view", side_effect=before_return):
                    run = self.admit(request)
                with self.factory() as session:
                    captures = target_repository.list_run_targets(session, run["id"])
                    self.assertEqual(
                        {capture.requested_alias for capture in captures},
                        {target_id + "-one", target_id + "-two"},
                    )
                    document = engine._document(runs.get_run(session, run["id"]))
                    self.assertEqual(
                        {
                            step.target_id
                            for step in document.definition.steps
                            if step.kind == "registered_github_handoff"
                        },
                        {target_id + "-one", target_id + "-two"},
                    )

    def test_cross_project_alias_collision_rolls_back_run_request_snapshot_and_audit(
        self,
    ):
        self.register()
        first = self.admit(self.request("target-one", key="first"))
        second = self.request("target-two", project=200, key="second")
        before = self.counts()
        with self.assertRaises(LifecycleError) as caught:
            self.admit(second)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.counts(), before)
        with self.factory() as session:
            lock = target_repository.get_held_lock(session, "target")
            self.assertEqual((lock.run_id, lock.project_id), (first["id"], 100))

    def test_identical_request_reuses_capture_and_lock_without_recapturing(self):
        self.register()
        request = self.request("target-one")
        first = self.admit(request)
        capture, snapshot = self.capture(first["id"])
        before = self.counts()
        with patch.object(
            targets,
            "capture_run_targets",
            side_effect=AssertionError("Replay must retain its original lock"),
        ):
            replay = self.admit(request, now=self.now + timedelta(seconds=1))
        retained, retained_snapshot = self.capture(replay["id"])
        self.assertEqual(replay, first)
        self.assertEqual(
            (retained.lock_id, retained.snapshot_bytes),
            (capture.lock_id, capture.snapshot_bytes),
        )
        self.assertEqual(retained_snapshot, snapshot)
        self.assertEqual(self.counts(), before)

    def test_multiple_target_collision_rolls_back_new_locks_as_one_admission(self):
        self.register("a-free")
        self.register("z-held")
        self.admit(self.request("z-held-one", key="holder"))
        request = self.request("z-held-two", "a-free-one", key="multi")
        before = self.counts()
        with self.assertRaises(LifecycleError) as caught:
            self.admit(request)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.counts(), before)
        with self.factory() as session:
            self.assertIsNone(target_repository.get_held_lock(session, "a-free"))

    def test_target_epoch_change_disable_and_reenable_never_revive_capture_or_claim(
        self,
    ):
        for index, enabled in enumerate((True, False)):
            with self.subTest(enabled=enabled):
                target_id = f"changed-{index}"
                self.register(target_id)
                run = self.admit(self.request(target_id + "-one", key=target_id))
                capture, snapshot = self.capture(run["id"])
                changed = self.register(target_id, expected_version=1, enabled=enabled)
                self.assertGreater(changed["epoch"], snapshot.target_epoch)
                with self.assertRaises(LifecycleError) as caught:
                    self.capture(run["id"])
                self.assertEqual(caught.exception.status_code, 409)
                if not enabled:
                    self.register(target_id, expected_version=2, enabled=True)
                    with self.assertRaises(LifecycleError):
                        self.capture(run["id"])
                retained, _ = self.capture(run["id"], live=False)
                self.assertEqual(retained.snapshot_bytes, capture.snapshot_bytes)
                with self.credentials(), authorization.authorized_session() as session:
                    owner = claims.acquire_coordinator(
                        session, project_id=100, workspace_id=100, now=self.now
                    )
                with self.credentials(), self.assertRaises(LifecycleError):
                    with authorization.authorized_session() as session:
                        claims.start_run(
                            session,
                            owner,
                            run_id=run["id"],
                            expected_version=run["version"],
                            now=self.now,
                        )
                with self.credentials(), authorization.authorized_session() as session:
                    claims.release_coordinator(
                        session, owner, project_id=100, workspace_id=100, now=self.now
                    )

    def test_audited_break_retires_old_capture_even_after_new_run_acquires_lock(self):
        self.register()
        old = self.admit(self.request("target-one", key="old"))
        capture, _ = self.capture(old["id"])
        request = BreakLockRequest(
            project_id=100,
            workspace_id=100,
            expected_lock_id=capture.lock_id,
            expected_version=1,
            acknowledge_uncertainty=True,
            reason="Explicitly retire uncertain synthetic holder",
        )
        with self.credentials():
            result = targets.break_lock("target-two", request, now=self.now)
        self.assertEqual(result["status"], "broken")
        with self.assertRaises(LifecycleError):
            self.capture(old["id"])
        new = self.admit(self.request("target-two", project=200, key="new"))
        replacement, _ = self.capture(new["id"])
        self.assertNotEqual(replacement.lock_id, capture.lock_id)
        with self.assertRaises(LifecycleError):
            self.capture(old["id"])
        with self.factory() as session:
            events = list(
                session.scalars(
                    select(InfraAutomationAudit).where(
                        InfraAutomationAudit.event_type == "target_lock_broken"
                    )
                )
            )
            self.assertEqual(len(events), 1)
            self.assertEqual(
                (events[0].target_id, events[0].actor_principal_id),
                (capture.lock_id, "human-a"),
            )

    def test_local_lease_expiry_and_cancel_flag_keep_uncertain_canonical_lock(self):
        self.register()
        run = self.admit(self.request("target-one", key="uncertain"))
        capture, _ = self.capture(run["id"])
        # Retained possible-delivery fixture: no external operation is executed.
        with self.factory.begin() as session:
            row = runs.get_run(session, run["id"])
            row.state = "handing_off"
            row.external_possible = True
        with self.credentials(), authorization.authorized_session() as session:
            old_owner = claims.acquire_coordinator(
                session, project_id=100, workspace_id=100, now=self.now
            )
        with self.credentials():
            cancelled = engine.cancel_run(
                run["id"],
                CancelRunRequest(
                    expected_version=run["version"],
                    reason="Record local cancellation despite uncertain delivery",
                ),
                now=self.now + timedelta(seconds=1),
            )
        self.assertTrue(cancelled["cancel_requested"])
        self.assertEqual(cancelled["state"], "delivery_unknown")
        later = self.now + timedelta(seconds=claims.LEASE_SECONDS + 1)
        with self.credentials(), authorization.authorized_session() as session:
            owner = claims.acquire_coordinator(
                session, project_id=100, workspace_id=100, now=later
            )
            self.assertGreater(owner.generation, old_owner.generation)
            lock = target_repository.get_held_lock(session, "target")
            self.assertEqual(
                (lock.id, lock.status, lock.run_id),
                (capture.lock_id, "held", run["id"]),
            )
        before = self.counts()
        competing = self.request("target-two", project=200, key="after-expiry")
        with self.assertRaises(LifecycleError) as caught:
            self.admit(competing, now=later)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.counts(), before)
