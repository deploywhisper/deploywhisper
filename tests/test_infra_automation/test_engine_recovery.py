"""Finite safe retries, immutable output adoption, and local crash recovery."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


from infra_automation import claims
from infra_automation.contracts import STEP_CONTRACTS
from infra_automation.coordinator import Coordinator, deadline_outcome
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.local_workers import (
    HandlerRegistration,
    HandlerRegistry,
    SpawnProcessWorkers,
)
from infra_automation.state import WorkerResult, OutputReference
from models.repositories import infra_automation_runs as repository
from services import project_service as authorization
from services import infra_automation_support as support
from tests.test_infra_automation import test_engine_coordinator as coordinator_tests


def retryable_failure(value):
    return WorkerResult(outcome="retryable_local_failure")


def permanent_failure(value):
    return WorkerResult(outcome="permanent_local_failure")


def counted_permanent_failure(value):
    document = SnapshotDocument.model_validate_json(value.snapshot_bytes)
    with Path(document.inputs["note"]).open("a") as marker:
        marker.write("invoked\n")
    return WorkerResult(outcome="permanent_local_failure")


def counted_gate_stop(value):
    counted_permanent_failure(value)
    return WorkerResult(outcome="stopped_by_gate")


def counted_rejection(value):
    counted_permanent_failure(value)
    return WorkerResult(outcome="rejected")


def typed_local_success(value):
    document = SnapshotDocument.model_validate_json(value.snapshot_bytes)
    step = next(step for step in document.definition.steps if step.id == value.step_id)
    return WorkerResult(
        outcome="local_success",
        output=OutputReference(
            kind=STEP_CONTRACTS[step.kind].output,
            reference=step.id,
            digest=support.digest(step.id.encode()),
        ),
    )


def external_accept_and_drop(value):
    import os

    document = SnapshotDocument.model_validate_json(value.snapshot_bytes)
    with Path(document.inputs["marker"]).open("a") as marker:
        marker.write("accepted\n")
    os._exit(7)


def external_accept_and_block(value):
    document = SnapshotDocument.model_validate_json(value.snapshot_bytes)
    with Path(document.inputs["marker"]).open("a") as marker:
        marker.write("accepted\n")
    time.sleep(10)


class EngineRecoveryTests(coordinator_tests.EngineCoordinatorRuntimeTests):
    def operation(self, function, *args, **kwargs):
        with authorization.authorized_session(self.factory) as session:
            return function(session, *args, **kwargs)

    def assert_known_failure_survives_fault(
        self,
        boundary,
        failures,
        handler=counted_permanent_failure,
        terminal="failed",
        expire_attempt=False,
    ):
        marker = Path(self.temp.name) / "permanent-invocations.txt"
        document = self.snapshot.snapshot
        snapshot = self.export(
            (document.workflow_id, document.revision_id), inputs={"note": str(marker)}
        )
        self.request.update(snapshot=snapshot)
        run = self.admit()
        self.workers.close()
        self.workers = SpawnProcessWorkers(str(self.engine.url), max_workers=1)
        self.addCleanup(self.workers.close)
        coordinator = self.scheduler(handler)
        prepare = claims.prepare_attempt

        def finite_prepare(session, owner, **kwargs):
            kwargs["attempt_timeout_seconds"] = 5
            return prepare(session, owner, **kwargs)

        if expire_attempt:
            with patch.object(claims, "prepare_attempt", side_effect=finite_prepare):
                coordinator.tick()
        else:
            coordinator.tick()
        deadline = time.monotonic() + 8
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(marker.read_text(), "invoked\n")
        time.sleep(0.05)
        target, name = {
            "stop": (claims, "stop_run"),
            "finish": (claims, "finish_run"),
            "audit": (repository, "_audit"),
        }[boundary]
        real = getattr(target, name)
        remaining = failures

        def fail_then_recover(*args, **kwargs):
            nonlocal remaining
            if remaining and (
                boundary in ("stop", "finish") or args[4] == "engine.attempt_failed"
            ):
                remaining -= 1
                raise RuntimeError("Synthetic persistence fault")
            return real(*args, **kwargs)

        with patch.object(target, name, side_effect=fail_then_recover):
            for _ in range(failures):
                coordinator.tick()
                self.assertEqual(len(coordinator._pending_completions), 1)
                self.assertFalse(coordinator._can_submit)
                self.assertEqual(marker.read_text(), "invoked\n")
                with self.factory() as session:
                    self.assertEqual(
                        repository.get_run(session, run.id).state, "running"
                    )
                    rows = repository.list_attempts(session, run_id=run.id)
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0].state, "running")
            if expire_attempt:
                with self.factory() as session:
                    attempt = repository.list_attempts(session, run_id=run.id)[0]
                    until = repository.utc(attempt.deadline_at)
                while datetime.now(timezone.utc) <= until:
                    time.sleep(0.02)
            coordinator.tick()
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, run.id).state, terminal)
            self.assertEqual(len(repository.list_attempts(session, run_id=run.id)), 1)
        self.assertEqual(marker.read_text(), "invoked\n")
        self.assertEqual(coordinator._pending_completions, {})

    def test_known_permanent_result_survives_one_shot_stop_failure(self):
        self.assert_known_failure_survives_fault("stop", 1)

    def test_known_permanent_result_survives_attempt_audit_failure(self):
        self.assert_known_failure_survives_fault("audit", 1)

    def test_repeated_persistence_failures_keep_bounded_receipt_without_retry(self):
        self.assert_known_failure_survives_fault("stop", 4)

    def test_known_gate_stop_survives_persistence_failure(self):
        self.assert_known_failure_survives_fault(
            "finish", 1, counted_gate_stop, "stopped_by_gate"
        )

    def test_known_rejection_survives_persistence_failure(self):
        self.assert_known_failure_survives_fault(
            "finish", 1, counted_rejection, "rejected"
        )

    def test_known_permanent_result_never_retries_after_attempt_expiry(self):
        self.assert_known_failure_survives_fault("stop", 1, expire_attempt=True)

    def test_ten_active_runs_across_two_workflows_share_two_worker_slots(self):
        runs = []
        snapshots = [self.export(self.publish_fixture()) for _ in range(2)]
        for index in range(10):
            with self.factory.begin() as session:
                runs.append(
                    repository.create_run(
                        session,
                        **{
                            **self.request,
                            "snapshot": snapshots[index // 5],
                            "key_digest": support.digest(str(index).encode()),
                        },
                    )
                )
        with self.factory.begin() as session:
            queued = repository.create_run(
                session,
                **{
                    **self.request,
                    "snapshot": snapshots[0],
                    "key_digest": support.digest(b"over-active-cap"),
                },
            )
        coordinator = self.scheduler()
        coordinator.tick()
        self.assertEqual(len(self.workers.handles), 2)
        with self.factory() as session:
            self.assertTrue(
                all(
                    repository.get_run(session, run.id).state == "running"
                    for run in runs
                )
            )
            self.assertEqual(repository.get_run(session, queued.id).state, "queued")
            self.assertEqual(
                sum(
                    len(repository.list_attempts(session, run_id=run.id))
                    for run in runs
                ),
                2,
            )

    def await_run_terminal(self, coordinator, run_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            coordinator.tick()
            with self.factory() as session:
                row = repository.get_run(session, run_id)
                if row.state in (
                    "failed",
                    "succeeded",
                    "timed_out",
                    "expired",
                    "delivery_unknown",
                ):
                    return row
            time.sleep(0.03)
        self.fail("Recovery did not reach a bounded durable outcome")

    def test_retryable_failure_has_three_distinct_attempts_then_fails(self):
        run = self.admit()
        coordinator = self.scheduler(retryable_failure)
        self.assertEqual(self.await_run_terminal(coordinator, run.id).state, "failed")
        with self.factory() as session:
            attempts = repository.list_attempts(session, run_id=run.id)
        self.assertEqual([row.attempt_number for row in attempts], [1, 2, 3])
        self.assertEqual([row.fence for row in attempts], [1, 2, 3])
        self.assertTrue(all(row.state == "failed" for row in attempts))
        self.assertEqual(len({row.owner_hash for row in attempts}), 3)

    def test_permanent_failure_is_not_retried_even_for_safe_handler(self):
        run = self.admit()
        coordinator = self.scheduler(permanent_failure)
        self.assertEqual(self.await_run_terminal(coordinator, run.id).state, "failed")
        with self.factory() as session:
            self.assertEqual(len(repository.list_attempts(session, run_id=run.id)), 1)

    def test_restart_adopts_committed_output_without_invoking_handler(self):
        run = self.admit()
        owner = self.operation(
            claims.acquire_coordinator, project_id=100, workspace_id=100
        )
        self.operation(
            claims.start_run, owner, run_id=run.id, expected_version=run.version
        )
        pending = self.operation(
            claims.prepare_attempt,
            owner,
            run_id=run.id,
            step_id="upload",
            handler_id="synthetic",
            handler_version="1",
            retry_safe=True,
        )
        old_handle = self.operation(
            claims.claim_attempt,
            owner,
            attempt_id=pending.id,
            expected_version=pending.version,
        )
        attempt = self.operation(claims.start_attempt, old_handle, expected_version=2)
        output = OutputReference(
            kind="screened_artifacts",
            reference="prior-output",
            digest=support.digest(b"committed"),
        )
        attempt = self.operation(
            claims.register_upload,
            old_handle,
            expected_version=attempt.version,
            reference=output,
        )
        attempt = self.operation(
            claims.commit_output,
            old_handle,
            expected_version=attempt.version,
            output=output,
        )
        self.operation(
            claims.release_coordinator, owner, project_id=100, workspace_id=100
        )
        coordinator = self.scheduler(coordinator_tests.synthetic_handler)
        self.assertEqual(
            self.await_run_terminal(coordinator, run.id).state, "succeeded"
        )
        with self.factory() as session:
            attempts = repository.list_attempts(session, run_id=run.id)
        self.assertEqual([row.state for row in attempts], ["failed", "succeeded"])
        self.assertEqual(attempts[0].output_json, attempts[1].output_json)
        self.assertNotEqual(attempts[0].owner_hash, attempts[1].owner_hash)
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.complete_attempt,
                old_handle,
                expected_version=attempt.version,
                state="succeeded",
            )

    def test_elapsed_run_deadline_terminates_without_retry(self):
        self.request["deadline_at"] = self.now + timedelta(seconds=1)
        run = self.admit()
        coordinator = self.scheduler()
        coordinator.tick()
        time.sleep(1.05)
        self.assertEqual(
            self.await_run_terminal(coordinator, run.id).state, "timed_out"
        )
        with self.factory() as session:
            self.assertEqual(len(repository.list_attempts(session, run_id=run.id)), 1)

    def test_evidence_horizon_expires_durably_instead_of_total_timeout(self):
        document = self.snapshot.snapshot
        horizon = datetime.strptime(document.captured_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ) + timedelta(seconds=document.policy.evidence_ttl_seconds)
        self.request["deadline_at"] = horizon
        run = self.admit()
        coordinator = self.scheduler()
        coordinator.clock = lambda: horizon
        coordinator.tick()
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, run.id).state, "expired")
            self.assertEqual(repository.list_attempts(session, run_id=run.id), [])
        self.assertEqual(deadline_outcome(run.snapshot_bytes, horizon), "expired")
        self.assertEqual(
            deadline_outcome(run.snapshot_bytes, horizon - timedelta(seconds=1)),
            "timed_out",
        )

    def external_fixture(self, handler=external_accept_and_drop):
        definition = self.definition()
        definition["inputs"]["marker"] = {"type": "string", "max_length": 500}
        marker = Path(self.temp.name) / "accepted-double.txt"
        snapshot = self.export(
            self.publish_fixture(definition), inputs={"marker": str(marker)}
        )
        self.request.update(snapshot=snapshot, key_digest=support.digest(b"external"))
        run = self.admit()
        registry = HandlerRegistry(
            tuple(
                HandlerRegistration(
                    "typed-" + step.kind,
                    "1",
                    step.kind,
                    STEP_CONTRACTS[step.kind].output,
                    False,
                    handler
                    if step.kind == "registered_github_handoff"
                    else typed_local_success,
                )
                for step in snapshot.snapshot.definition.steps
            )
        )
        return run, registry, marker

    def test_committed_external_intent_and_dropped_response_never_resend(self):
        run, registry, marker = self.external_fixture()
        coordinator = Coordinator(self.factory, self.workers, registry=registry)
        self.addCleanup(coordinator.close)
        self.assertEqual(
            self.await_run_terminal(coordinator, run.id).state, "delivery_unknown"
        )
        self.assertEqual(marker.read_text(), "accepted\n")
        with self.factory() as session:
            attempts = repository.list_attempts(session, run_id=run.id)
        self.assertEqual(len(attempts), 5)
        coordinator.close()
        workers = SpawnProcessWorkers(str(self.engine.url))
        self.addCleanup(workers.close)
        successor = Coordinator(self.factory, workers, registry=registry)
        self.addCleanup(successor.close)
        for _ in range(3):
            successor.tick()
        self.assertEqual(marker.read_text(), "accepted\n")
        with self.factory() as session:
            self.assertEqual(len(repository.list_attempts(session, run_id=run.id)), 5)
            self.assertTrue(repository.get_run(session, run.id).external_possible)

    def test_restart_after_external_intent_recovers_unknown_without_invocation(self):
        run, registry, marker = self.external_fixture(external_accept_and_block)
        coordinator = Coordinator(self.factory, self.workers, registry=registry)
        self.addCleanup(coordinator.close)
        deadline = time.monotonic() + 12
        while not marker.exists() and time.monotonic() < deadline:
            coordinator.tick()
            time.sleep(0.03)
        self.assertEqual(marker.read_text(), "accepted\n")
        with self.factory() as session:
            self.assertEqual(repository.get_run(session, run.id).state, "handing_off")
        for handle in self.workers.handles:
            self.workers.cancel(handle.attempt_id)
        self.operation(
            claims.release_coordinator,
            coordinator._owner,
            project_id=100,
            workspace_id=100,
        )
        coordinator._owner = None
        workers = SpawnProcessWorkers(str(self.engine.url))
        self.addCleanup(workers.close)
        successor = Coordinator(self.factory, workers, registry=registry)
        self.addCleanup(successor.close)
        self.assertEqual(
            self.await_run_terminal(successor, run.id).state, "delivery_unknown"
        )
        self.assertEqual(marker.read_text(), "accepted\n")
        self.assertEqual(workers.handles, ())

    def test_expired_ownership_is_forgotten_then_reacquired_with_new_fence(self):
        run = self.admit()
        coordinator = self.scheduler(permanent_failure)
        with patch.object(claims, "LEASE_SECONDS", 1):
            coordinator.tick()
            owner, old = coordinator._owner, self.workers.handles[0]
            receipt_deadline = time.monotonic() + 8
            while (
                not coordinator._pending_completions
                and time.monotonic() < receipt_deadline
            ):
                for completion in self.workers.poll():
                    coordinator._pending_completions[completion.handle.attempt_id] = (
                        completion
                    )
                time.sleep(0.02)
            self.assertEqual(len(coordinator._pending_completions), 1)
            time.sleep(1.05)
            coordinator._heartbeat_at -= timedelta(seconds=10)
            coordinator.tick()
            self.assertIsNone(coordinator._owner)
            self.assertEqual(coordinator._pending_completions, {})
            coordinator.tick()
            self.assertGreater(coordinator._owner.generation, owner.generation)
            with self.factory() as session:
                attempts = repository.list_attempts(session, run_id=run.id)
            self.assertEqual([row.attempt_number for row in attempts], [1, 2])
            self.assertEqual(attempts[0].state, "failed")
            with self.assertRaises(LifecycleError):
                self.operation(
                    claims.heartbeat_attempt, old, expected_version=attempts[0].version
                )
