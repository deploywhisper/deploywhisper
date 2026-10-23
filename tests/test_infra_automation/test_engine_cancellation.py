"""Durable cancellation precedes signals to owned local process groups."""

from __future__ import annotations

from unittest.mock import patch
import os
from pathlib import Path
import subprocess
import sys
import time

from infra_automation import claims
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.state import CancelRunRequest, LogChunk, OutputReference
from infra_automation.coordinator import Coordinator
from services import infra_automation_engine_service as engine_service
from services import project_service as authorization
from services import infra_automation_support as support

from infra_automation.local_workers import WorkerTerminationError
from models.repositories import infra_automation_runs as repository
from tests.test_infra_automation import test_engine_coordinator as coordinator_tests
from tests.test_infra_automation import test_engine_recovery as recovery_tests


_IGNORE_TERM_CHILD = (
    "import os, signal, sys, time; "
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
)


def owned_process_tree(value):
    document = SnapshotDocument.model_validate_json(value.snapshot_bytes)
    marker = Path(document.inputs["note"])
    Path(str(marker) + ".parent").write_text(str(os.getpid()))
    _descendant = subprocess.Popen(
        [sys.executable, "-c", _IGNORE_TERM_CHILD, str(marker)]
    )
    time.sleep(60)


def alive(pid):
    if sys.platform == "linux":
        try:
            if (
                Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                == "Z"
            ):
                return False
        except FileNotFoundError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class EngineCancellationTests(coordinator_tests.EngineCoordinatorRuntimeTests):
    external_fixture = recovery_tests.EngineRecoveryTests.external_fixture

    def marker_run(self):
        marker = Path(self.temp.name) / "owned-child.pid"
        document = self.snapshot.snapshot
        self.request["snapshot"] = self.export(
            (document.workflow_id, document.revision_id), inputs={"note": str(marker)}
        )
        return self.admit(), marker

    def commit_cancel(self, run_id):
        with self.factory.begin() as session:
            run = repository.get_run(session, run_id)
            return repository.transition_run(
                session,
                run_id=run.id,
                expected_version=run.version,
                state="cancelled",
                audit_actor=self.actor,
                reason="Synthetic cancellation",
            )

    def test_private_cancel_refuses_to_signal_without_committed_request(self):
        run = self.admit()
        coordinator = self.scheduler()
        coordinator.tick()
        handles = self.workers.handles
        self.assertFalse(coordinator.cancel_run(run.id))
        self.assertEqual(self.workers.handles, handles)
        self.commit_cancel(run.id)
        self.assertTrue(coordinator.cancel_run(run.id))
        self.assertEqual(self.workers.handles, ())

    def test_tick_observes_committed_cancel_when_callback_was_lost(self):
        run = self.admit()
        coordinator = self.scheduler()
        coordinator.tick()
        self.commit_cancel(run.id)
        coordinator.tick()
        self.assertEqual(self.workers.handles, ())

    def test_failed_kill_keeps_owned_slot_until_confirmed_stop(self):
        self.two_runs()
        coordinator = self.scheduler()
        coordinator.tick()
        handle = self.workers.handles[0]
        with patch.object(
            self.workers, "_signal", side_effect=PermissionError("synthetic")
        ):
            with self.assertRaises(WorkerTerminationError):
                self.workers.cancel(handle.attempt_id)
        self.assertIn(handle, self.workers.handles)
        self.assertFalse(self.workers.can_submit)
        self.workers.cancel(handle.attempt_id)
        self.assertEqual(len(self.workers.handles), 1)

    def test_cancel_terminates_sigterm_ignoring_descendant_within_five_seconds(self):
        if os.name != "posix":
            self.skipTest("Owned process-group contract is POSIX scoped")
        run, marker = self.marker_run()
        coordinator = self.scheduler(owned_process_tree)
        coordinator.tick()
        deadline = time.monotonic() + 8
        while not marker.exists() and time.monotonic() < deadline:
            coordinator.tick()
            time.sleep(0.02)
        child = int(marker.read_text())
        parent = int(Path(str(marker) + ".parent").read_text())
        self.assertTrue(alive(parent) and alive(child))
        handle = self.workers.handles[0]
        started = time.monotonic()
        self.commit_cancel(run.id)
        coordinator.cancel_run(run.id)
        self.assertLess(time.monotonic() - started, 5)
        self.assertFalse(alive(parent) or alive(child))
        self.assertEqual(self.workers.handles, ())
        output = OutputReference(
            kind="screened_artifacts", reference="late", digest=support.digest(b"late")
        )
        for function, payload in (
            (claims.heartbeat_attempt, {}),
            (claims.append_log, {"chunk": LogChunk(sequence=1, text="late")}),
            (claims.register_upload, {"reference": output}),
            (claims.commit_output, {"output": output}),
            (claims.complete_attempt, {"state": "succeeded"}),
        ):
            with (
                self.subTest(operation=function.__name__),
                self.assertRaises(LifecycleError),
            ):
                with authorization.authorized_session(self.factory) as session:
                    row = repository.get_attempt(session, handle.attempt_id)
                    function(session, handle, expected_version=row.version, **payload)

    def test_cancel_before_start_never_creates_attempt(self):
        run = self.admit()
        self.commit_cancel(run.id)
        coordinator = self.scheduler()
        coordinator.tick()
        self.assertEqual(self.workers.handles, ())
        with self.factory() as session:
            self.assertEqual(repository.list_attempts(session, run_id=run.id), [])

    def test_uncommitted_cancel_cannot_signal_private_port(self):
        run = self.admit()
        coordinator = self.scheduler()
        coordinator.tick()
        handles = self.workers.handles
        with self.assertRaises(RuntimeError):
            with authorization.authorized_session(self.factory) as session:
                row = repository.get_run(session, run.id)
                repository.transition_run(
                    session,
                    run_id=run.id,
                    expected_version=row.version,
                    state="cancelled",
                    audit_actor=self.actor,
                    reason="Synthetic rollback",
                )
                with self.assertRaises(LifecycleError):
                    coordinator.cancel_run(run.id)
                raise RuntimeError("Crash before cancellation commit")
        self.assertEqual(self.workers.handles, handles)
        with self.factory() as session:
            self.assertFalse(repository.get_run(session, run.id).cancel_requested)

    def test_committed_cancel_discards_pending_success_completion(self):
        run = self.admit()
        coordinator = self.scheduler()
        coordinator.tick()
        deadline = time.monotonic() + 8
        while not coordinator._pending_completions and time.monotonic() < deadline:
            for completion in self.workers.poll():
                coordinator._pending_completions[completion.handle.attempt_id] = (
                    completion
                )
            time.sleep(0.02)
        self.assertEqual(len(coordinator._pending_completions), 1)
        self.commit_cancel(run.id)
        coordinator.cancel_run(run.id)
        coordinator.tick()
        self.assertEqual(coordinator._pending_completions, {})
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, run.id).state, "cancelled")
            row = repository.list_attempts(session, run_id=run.id)[0]
            self.assertEqual(row.state, "cancelled")
            self.assertIsNotNone(row.output_json)

    def test_restarted_coordinator_observes_cancel_before_lease_acquisition(self):
        run = self.admit()
        coordinator = self.scheduler()
        coordinator.tick()
        self.commit_cancel(run.id)
        coordinator._owner = None
        coordinator.tick()
        self.assertEqual(self.workers.handles, ())

    def test_external_accepted_work_remains_unknown_after_public_cancel(self):
        run, registry, marker = self.external_fixture(
            recovery_tests.external_accept_and_block
        )
        coordinator = Coordinator(self.factory, self.workers, registry=registry)
        self.addCleanup(coordinator.close)
        deadline = time.monotonic() + 30
        while not marker.exists() and time.monotonic() < deadline:
            coordinator.tick()
            time.sleep(0.02)
        self.assertEqual(marker.read_text(), "accepted\n")
        with self.factory() as session:
            current = repository.get_run(session, run.id)
        with self.credentials():
            result = engine_service.cancel_run(
                run.id,
                CancelRunRequest(
                    expected_version=current.version,
                    reason="Synthetic external cancellation",
                ),
                cancel_port=coordinator.cancel_run,
            )
        self.assertEqual(result["state"], "delivery_unknown")
        self.assertTrue(result["cancel_requested"])
        self.assertEqual(self.workers.handles, ())
        coordinator.tick()
        self.assertEqual(marker.read_text(), "accepted\n")
        with self.factory() as session:
            self.assertEqual(
                repository.get_run(session, run.id).state, "delivery_unknown"
            )

    def test_cancel_signals_only_matching_owned_run(self):
        first, second = self.two_runs()
        coordinator = self.scheduler()
        coordinator.tick()
        self.commit_cancel(first.id)
        coordinator.cancel_run(first.id)
        self.assertEqual(
            [handle.run_id for handle in self.workers.handles], [second.id]
        )

    def test_alive_group_after_kill_budget_retains_record_and_backpressure(self):
        self.two_runs()
        coordinator = self.scheduler()
        coordinator.tick()
        handle = self.workers.handles[0]
        started = time.monotonic()
        with (
            patch.object(self.workers, "_signal"),
            patch.object(self.workers, "_group_alive", return_value=True),
        ):
            with self.assertRaises(WorkerTerminationError):
                self.workers.cancel(handle.attempt_id)
        self.assertLess(time.monotonic() - started, 5)
        self.assertIn(handle, self.workers.handles)
        self.assertFalse(self.workers.can_submit)
        self.workers.cancel(handle.attempt_id)

    def test_failed_post_result_cleanup_preserves_original_result(self):
        self.admit()
        coordinator = self.scheduler(recovery_tests.permanent_failure)
        coordinator.tick()
        handle = self.workers.handles[0]
        item = self.workers._owned[handle.attempt_id]
        deadline = time.monotonic() + 8
        while item.process.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        with (
            patch.object(
                self.workers, "_signal", side_effect=PermissionError("synthetic")
            ),
            patch.object(self.workers, "_group_alive", return_value=True),
        ):
            with self.assertRaises(WorkerTerminationError):
                self.workers.poll()
        self.assertEqual(item.result.outcome, "permanent_local_failure")
        completion = self.workers.poll()[0]
        self.assertEqual(completion.result.outcome, "permanent_local_failure")
        self.assertFalse(completion.crashed)
