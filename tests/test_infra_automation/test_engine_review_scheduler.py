"""Regression coverage for terminal worker cleanup and bounded scheduler fairness."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import time
import os
from types import SimpleNamespace
from unittest.mock import patch

from infra_automation import claims
from infra_automation.coordinator import Coordinator
from infra_automation.lifecycle import SnapshotDocument
from infra_automation.local_workers import (
    HandlerRegistration,
    HandlerRegistry,
    WorkerCompletion,
    WorkerTerminationError,
)
from infra_automation.state import EngineBounds, WorkerResult
from models.repositories import infra_automation_runs as repository
from services import project_service as authorization
from services.infra_automation_support import digest
from tests.test_infra_automation import test_engine_coordinator as coordinator_tests
from tests.test_infra_automation.test_engine_cancellation import alive


def sibling_handler(value):
    note = SnapshotDocument.model_validate_json(value.snapshot_bytes).inputs["note"]
    marker = Path(note) if note != "original" else None
    if value.step_id == "failure":
        if marker is not None:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
        time.sleep(1)
        return WorkerResult(outcome="permanent_local_failure")
    if marker is not None:
        marker.write_text(str(os.getpid()))
    time.sleep(60)
    return WorkerResult(outcome="permanent_local_failure")


class ControlledWorkers:
    """Use real claims while keeping process termination explicitly observable."""

    max_workers = 2

    def __init__(self, case):
        self.case = case
        self.owned = {}
        self.receipts = []
        self.cancel_calls = []
        self.refuse_cancel = False

    @property
    def handles(self):
        return tuple(self.owned.values())

    @property
    def can_submit(self):
        return len(self.owned) < self.max_workers

    def submit(self, handle, registration, value):
        with authorization.authorized_session(self.case.factory) as session:
            row = repository.get_attempt(session, handle.attempt_id)
            claims.start_attempt(
                session, handle, expected_version=row.version, now=self.case.now
            )
        self.owned[handle.attempt_id] = handle

    def poll(self):
        values, self.receipts = self.receipts, []
        return tuple(values)

    def cancel(self, attempt_id):
        self.cancel_calls.append(attempt_id)
        if self.refuse_cancel:
            raise WorkerTerminationError()
        self.owned.pop(attempt_id, None)

    def close(self):
        self.refuse_cancel = False
        for attempt_id in tuple(self.owned):
            self.cancel(attempt_id)


class EngineReviewSchedulerTests(coordinator_tests.EngineCoordinatorRuntimeTests):
    def sibling_run(self, marker=None):
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {"note": {"type": "string", "max_length": 100}},
            "steps": [
                {
                    "id": name,
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "source": {"kind": "uploaded"},
                }
                for name in ("failure", "blocker")
            ],
        }
        self.request["snapshot"] = self.export(
            self.publish_fixture(definition),
            inputs={"note": str(marker)} if marker is not None else None,
        )
        return self.admit()

    def controlled_scheduler(self):
        workers = ControlledWorkers(self)
        registry = HandlerRegistry(
            (
                HandlerRegistration(
                    "synthetic",
                    "1",
                    "uploaded_intake",
                    "screened_artifacts",
                    True,
                    coordinator_tests.slow_success,
                ),
            )
        )
        coordinator = Coordinator(
            self.factory, workers, registry=registry, clock=lambda: self.now
        )
        self.addCleanup(coordinator.close)
        return coordinator, workers

    def fail_first_sibling(self, coordinator, workers):
        coordinator.tick()
        coordinator.tick()
        self.assertEqual(len(workers.handles), 2)
        failed = next(
            handle for handle in workers.handles if handle.step_id == "failure"
        )
        workers.owned.pop(failed.attempt_id)
        workers.receipts.append(
            WorkerCompletion(failed, WorkerResult(outcome="permanent_local_failure"))
        )
        coordinator.tick()

    def test_terminal_sibling_is_cancelled_and_slot_reusable(self):
        run = self.sibling_run()
        coordinator, workers = self.controlled_scheduler()
        self.fail_first_sibling(coordinator, workers)
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, run.id).state, "failed")
        self.assertEqual(workers.handles, ())
        self.assertEqual(len(workers.cancel_calls), 1)
        self.request["key_digest"] = digest(b"replacement")
        replacement = self.admit()
        coordinator.tick()
        self.assertEqual(workers.handles[0].run_id, replacement.id)

    def test_terminal_sibling_retains_slot_until_stop_confirmed_past_deadline(self):
        self.sibling_run()
        coordinator, workers = self.controlled_scheduler()
        workers.refuse_cancel = True
        self.fail_first_sibling(coordinator, workers)
        self.assertEqual(len(workers.handles), 1)
        with patch("infra_automation.coordinator.logger.warning"):
            for _ in range(65):
                self.now += timedelta(seconds=10)
                coordinator.tick()
        self.assertGreaterEqual(len(workers.cancel_calls), 2)
        self.assertEqual(len(workers.handles), 1)
        workers.refuse_cancel = False
        coordinator.tick()
        self.assertEqual(workers.handles, ())

    def test_real_spawn_terminal_sibling_is_stopped(self):
        marker = Path(self.temp.name) / "blocker.pid"
        self.sibling_run(marker)
        coordinator = self.scheduler(sibling_handler)
        coordinator.tick()
        coordinator.tick()
        self.assertEqual(len(self.workers.handles), 2)
        pids = tuple(item.process.pid for item in self.workers._owned.values())
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            coordinator.tick()
            if not self.workers.handles:
                break
            time.sleep(0.03)
        self.assertEqual(self.workers.handles, ())
        self.assertTrue(marker.exists(), "Blocking handler must actually execute")
        self.assertFalse(alive(int(marker.read_text())))
        for pid in pids:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)
        self.request["key_digest"] = digest(b"spawn-replacement")
        replacement = self.admit()
        coordinator.tick()
        self.assertEqual(self.workers.handles[0].run_id, replacement.id)

    def test_candidates_advance_past_blocked_oldest_hundred_and_expire_later_run(self):
        runs = []
        for group in range(5):
            snapshot = self.export(self.publish_fixture())
            for index in range(25 if group < 4 else 2):
                with self.factory.begin() as session:
                    row = repository.create_run(
                        session,
                        **{
                            **self.request,
                            "snapshot": snapshot,
                            "key_digest": digest(f"{group}/{index}".encode()),
                            "deadline_at": self.now
                            + timedelta(
                                seconds=1 if group == 4 and index == 1 else 600
                            ),
                        },
                    )
                    if group < 4 and index == 0:
                        repository.transition_run(
                            session,
                            run_id=row.id,
                            expected_version=row.version,
                            state="running",
                            audit_actor=self.actor,
                            reason="synthetic quota",
                            now=self.now,
                        )
                    runs.append(row.id)
        workers = SimpleNamespace(
            handles=(),
            can_submit=False,
            max_workers=2,
            poll=lambda: (),
            close=lambda: None,
        )
        coordinator = Coordinator(
            self.factory,
            workers,
            registry=HandlerRegistry(
                (
                    HandlerRegistration(
                        "synthetic",
                        "1",
                        "uploaded_intake",
                        "screened_artifacts",
                        True,
                        coordinator_tests.slow_success,
                    ),
                )
            ),
            bounds=EngineBounds(workflow_active_runs=1),
            clock=lambda: self.now,
        )
        self.addCleanup(coordinator.close)
        self.now += timedelta(seconds=2)
        for _ in range(3):
            coordinator.tick()
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, runs[-2]).state, "running")
            self.assertEqual(repository.get_run(session, runs[-1]).state, "timed_out")

    def test_project_quota_does_not_block_later_project(self):
        from infra_automation.lifecycle import AutomationSettings
        from infra_automation.workflow_schema import Workflow
        from models.repositories import infra_automation_workflows as workflows
        from services.infra_automation_snapshots import export_run_snapshot
        from services.infra_automation_support import canonical

        # Project one is independently capped even though its workflow quota
        # and all worker slots would allow another run.
        with self.factory.begin() as session:
            policy = workflows.get_policy(session, project_id=100)
            workflows.save_policy(
                session,
                project_id=100,
                expected_version=policy.version,
                settings_json=AutomationSettings(
                    enabled=True, max_active_runs=1
                ).model_dump_json(),
            )
            workflows.save_policy(
                session,
                project_id=200,
                expected_version=0,
                settings_json=AutomationSettings(enabled=True).model_dump_json(),
            )
        self.member(project=200)
        snapshot = self.export(self.publish_fixture())
        for index in range(3):
            with self.factory.begin() as session:
                repository.create_run(
                    session,
                    **{
                        **self.request,
                        "snapshot": snapshot,
                        "key_digest": digest(f"project-one/{index}".encode()),
                    },
                )
        definition = Workflow.model_validate(
            {
                "workflow_version": 2,
                "project_id": "200",
                "workspace_id": "200",
                "environment": "dev",
                "inputs": {},
                "steps": [
                    {
                        "id": "upload",
                        "kind": "uploaded_intake",
                        "depends_on": [],
                        "source": {"kind": "uploaded"},
                    }
                ],
            }
        )
        raw = canonical(definition.model_dump(mode="json"))
        with self.factory.begin() as session:
            workflow = workflows.create_workflow(
                session,
                project_id=200,
                workspace_id=200,
                name="Other project",
                canonical_definition=raw,
                digest=digest(raw),
                created_by="human-a",
            )
            revision = workflows.append_revision(
                session,
                workflow_id=workflow.id,
                project_id=200,
                workspace_id=200,
                revision_number=1,
                canonical_definition=raw,
                digest=digest(raw),
                published_by="human-a",
                idempotency_key_digest=digest(workflow.id.encode()),
                request_digest=digest(raw),
            )
        with self.credentials():
            other_snapshot = export_run_snapshot(workflow.id, revision.id, {}, 200)
        with self.factory.begin() as session:
            other = repository.create_run(
                session,
                **{
                    **self.request,
                    "snapshot": other_snapshot,
                    "key_digest": digest(b"project-two"),
                },
            )
        coordinator, workers = self.controlled_scheduler()
        coordinator.tick()
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, other.id).state, "running")
        self.assertEqual({handle.project_id for handle in workers.handles}, {100, 200})

    def test_ready_workflows_share_worker_slots_before_same_workflow_siblings(self):
        first = self.admit()
        with self.factory.begin() as session:
            second = repository.create_run(
                session,
                **{**self.request, "key_digest": digest(b"same-workflow")},
            )
        snapshot = self.export(self.publish_fixture())
        with self.factory.begin() as session:
            other = repository.create_run(
                session,
                **{
                    **self.request,
                    "snapshot": snapshot,
                    "key_digest": digest(b"different-workflow"),
                },
            )
        coordinator, workers = self.controlled_scheduler()
        coordinator.tick()
        self.assertEqual(
            {handle.run_id for handle in workers.handles}, {first.id, other.id}
        )
        with self.factory() as session:
            self.assertEqual(repository.list_attempts(session, run_id=second.id), [])

    def test_full_pages_of_new_arrivals_cannot_extend_current_sweep(self):
        from infra_automation.lifecycle import AutomationSettings
        from models.repositories import infra_automation_workflows as workflows

        with self.factory.begin() as session:
            policy = workflows.get_policy(session, project_id=100)
            workflows.save_policy(
                session,
                project_id=100,
                expected_version=policy.version,
                settings_json=AutomationSettings(
                    enabled=True, max_active_runs=8, max_queued_runs=1000
                ).model_dump_json(),
            )
        target = None

        def append_page(page, *, active=False):
            nonlocal target
            for group in range(4):
                snapshot = self.export(self.publish_fixture())
                with self.factory.begin() as session:
                    for index in range(25):
                        short_deadline = page == 0 and group == 0 and index == 1
                        row = repository.create_run(
                            session,
                            **{
                                **self.request,
                                "snapshot": snapshot,
                                "key_digest": digest(
                                    f"arrival/{page}/{group}/{index}".encode()
                                ),
                                "deadline_at": self.now
                                + timedelta(seconds=1 if short_deadline else 600),
                            },
                        )
                        if short_deadline:
                            target = row.id
                        if active and index == 0:
                            repository.transition_run(
                                session,
                                run_id=row.id,
                                expected_version=row.version,
                                state="running",
                                audit_actor=self.actor,
                                reason="synthetic active quota",
                                now=self.now,
                            )

        append_page(0, active=True)
        append_page(1, active=True)
        workers = SimpleNamespace(
            handles=(),
            can_submit=False,
            max_workers=2,
            poll=lambda: (),
            close=lambda: None,
        )
        coordinator = Coordinator(
            self.factory,
            workers,
            registry=HandlerRegistry(
                (
                    HandlerRegistration(
                        "synthetic",
                        "1",
                        "uploaded_intake",
                        "screened_artifacts",
                        True,
                        coordinator_tests.slow_success,
                    ),
                )
            ),
            bounds=EngineBounds(workflow_active_runs=1),
            clock=lambda: self.now,
        )
        self.addCleanup(coordinator.close)
        # The initial sweep has exactly two full pages. Keep adding another
        # full page before every tick so a moving tail would never be reached.
        coordinator.tick()
        append_page(2)
        self.now += timedelta(seconds=2)
        coordinator.tick()
        append_page(3)
        coordinator.tick()
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, target).state, "timed_out")
