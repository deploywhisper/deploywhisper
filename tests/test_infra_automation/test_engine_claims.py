"""Private capability fencing and live-authority engine regression tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from models.tables import InfraAutomationAudit
from models.repositories import infra_automation_workflows as workflows


from infra_automation import claims
from infra_automation.lifecycle import LifecycleError
from infra_automation.state import (
    AuditActor,
    CoordinatorHandle,
    EngineBounds,
    LogChunk,
    OutputReference,
)
from models.repositories import infra_automation_runs as repo
from services import project_service as auth
from services import infra_automation_engine_support as engine_support
from services import infra_automation_support as support
from tests.test_infra_automation import test_engine_repository as repository_tests
from tests.test_infra_automation.lifecycle_support import LifecycleCase


def _process_race(database_url, now, queue, gate, owner=None, attempt_id=None):
    engine = create_engine(database_url, connect_args={"timeout": 10})
    factory = sessionmaker(engine, expire_on_commit=False)
    gate.wait(10)
    try:
        with auth.authorized_session(factory) as db:
            if owner is None:
                result = claims.acquire_coordinator(
                    db, project_id=100, workspace_id=100, now=now
                )
            else:
                result = claims.claim_attempt(
                    db, owner, attempt_id=attempt_id, expected_version=1, now=now
                )
            won = result is not None
        queue.put(won)
    finally:
        engine.dispose()


class EngineClaimsTests(LifecycleCase):
    publish_fixture = repository_tests.EngineRepositoryTests.publish_fixture
    enable = repository_tests.EngineRepositoryTests.enable
    export = repository_tests.EngineRepositoryTests.export
    admit = repository_tests.EngineRepositoryTests.admit
    attempt = repository_tests.EngineRepositoryTests.attempt

    def setUp(self):
        super().setUp()
        with self.engine.begin() as db:
            for name, body in import_module(
                "migrations.versions.032_add_infra_automation_engine"
            ).GUARDS.items():
                db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")
        self.enable()
        self.snapshot = self.export(self.publish_fixture())
        self.actor = AuditActor("human-a", "human", "admin")
        self.request = dict(
            snapshot=self.snapshot,
            request_digest=support.digest(b"request"),
            key_digest=support.digest(b"key"),
            requested_by="human-a",
            deadline_at=self.now + timedelta(minutes=10),
            audit_actor=self.actor,
            reason="synthetic",
            now=self.now,
        )
        with self.credentials(), auth.authorized_session() as db:
            grant = support.scope(db, 100, 100, "automation.request", mutation=True)
            engine_support.ensure_engine_actor(db, grant)
        self.run = self.admit()
        self.pending = self.attempt(self.run)

    def operation(self, function, *args, **kwargs):
        with auth.authorized_session(self.factory) as db:
            return function(db, *args, now=kwargs.pop("now", self.now), **kwargs)

    def acquire(self):
        return self.operation(
            claims.acquire_coordinator, project_id=100, workspace_id=100
        )

    def owned(self):
        owner = self.acquire()
        self.operation(claims.start_run, owner, run_id=self.run.id, expected_version=1)
        handle = self.operation(
            claims.claim_attempt, owner, attempt_id=self.pending.id, expected_version=1
        )
        row = self.operation(claims.start_attempt, handle, expected_version=2)
        return owner, handle, row

    def test_private_secret_and_singleton_race(self):
        def acquire(_):
            return self.acquire()

        with ThreadPoolExecutor(max_workers=2) as pool:
            handles = list(pool.map(acquire, range(2)))
        self.assertEqual(sum(handle is not None for handle in handles), 1)
        owner = next(handle for handle in handles if handle)
        self.assertEqual(len(owner.owner_secret), 64)
        self.assertNotIn(owner.owner_secret, repr(owner))
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.renew_coordinator,
                replace(owner, owner_secret="a" * 64),
                project_id=100,
                workspace_id=100,
            )

    def test_claim_race_and_full_stale_binding_matrix(self):
        owner, handle, row = self.owned()
        self.assertIsNone(
            self.operation(
                claims.claim_attempt,
                owner,
                attempt_id=self.pending.id,
                expected_version=1,
            )
        )
        mutations = dict(
            project_id=200,
            workspace_id=101,
            principal_id="other",
            run_id="other",
            step_id="other",
            attempt_id="other",
            attempt_number=2,
            fence=2,
            generation=2,
            owner_id="other",
            owner_secret="a" * 64,
            authorization_epoch=2,
            restore_epoch=2,
        )
        output = OutputReference(
            kind="screened_artifacts",
            reference="safe",
            digest=support.digest(b"output"),
        )
        for key, value in mutations.items():
            stale = replace(handle, **{key: value})
            for function, payload in (
                (claims.heartbeat_attempt, {}),
                (claims.append_log, {"chunk": LogChunk(sequence=1, text="safe")}),
                (claims.register_upload, {"reference": output}),
                (claims.commit_output, {"output": output}),
                (claims.complete_attempt, {"state": "failed"}),
            ):
                with (
                    self.subTest(field=key, operation=function.__name__),
                    self.assertRaises(LifecycleError),
                ):
                    self.operation(
                        function, stale, expected_version=row.version, **payload
                    )

    def test_upload_output_replay_and_strict_log_bounds(self):
        _, handle, row = self.owned()
        output = OutputReference(
            kind="screened_artifacts",
            reference="safe",
            digest=support.digest(b"output"),
        )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.commit_output,
                handle,
                expected_version=row.version,
                output=output,
            )
        row = self.operation(
            claims.append_log,
            handle,
            expected_version=row.version,
            chunk=LogChunk(sequence=1, text="safe"),
        )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.append_log,
                handle,
                expected_version=row.version,
                chunk=LogChunk(sequence=3, text="gap"),
            )
        row = self.operation(
            claims.register_upload,
            handle,
            expected_version=row.version,
            reference=output,
        )
        version = row.version
        row = self.operation(
            claims.commit_output, handle, expected_version=version, output=output
        )
        self.assertEqual(
            self.operation(
                claims.commit_output, handle, expected_version=version, output=output
            ).version,
            row.version,
        )
        version = row.version
        row = self.operation(
            claims.complete_attempt, handle, expected_version=version, state="succeeded"
        )
        self.assertEqual(
            self.operation(
                claims.complete_attempt,
                handle,
                expected_version=version,
                state="succeeded",
            ).version,
            row.version,
        )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.commit_output,
                handle,
                expected_version=version,
                output=output,
                now=self.now + timedelta(seconds=30),
            )

    def test_restart_takeover_epoch_and_clock_rollback(self):
        owner, handle, row = self.owned()
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.heartbeat_attempt,
                handle,
                expected_version=row.version,
                now=self.now - timedelta(seconds=1),
            )
        successor = self.operation(
            claims.acquire_coordinator,
            project_id=100,
            workspace_id=100,
            now=self.now + timedelta(seconds=30),
        )
        self.assertGreater(successor.generation, owner.generation)
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.heartbeat_attempt,
                handle,
                expected_version=row.version,
                now=self.now + timedelta(seconds=30),
            )
        stopped = self.operation(
            claims.safety_cleanup,
            successor,
            attempt_id=handle.attempt_id,
            expected_version=row.version,
            state="failed",
            now=self.now + timedelta(seconds=30),
        )
        self.assertEqual(stopped.state, "failed")

    def test_live_revocation_rejects_writes_but_cleanup_survives(self):
        owner, handle, row = self.owned()
        self.member("read-only")
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.operation(
                claims.heartbeat_attempt, handle, expected_version=row.version
            )
        self.assertEqual(
            self.operation(
                claims.safety_cleanup,
                owner,
                attempt_id=handle.attempt_id,
                expected_version=row.version,
                state="cancelled",
            ).state,
            "cancelled",
        )

    def test_audit_failure_rolls_back_owned_mutation(self):
        from unittest.mock import patch

        _, handle, row = self.owned()
        with (
            patch.object(
                repo, "append_audit", side_effect=RuntimeError("disk failure")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.operation(
                claims.heartbeat_attempt, handle, expected_version=row.version
            )
        with self.factory() as db:
            self.assertEqual(
                repo.get_attempt(db, handle.attempt_id).version, row.version
            )

    def process_race(self, owner=None):
        context = multiprocessing.get_context("spawn")
        queue, gate = context.Queue(), context.Event()
        processes = [
            context.Process(
                target=_process_race,
                args=(
                    str(self.engine.url),
                    self.now,
                    queue,
                    gate,
                    owner,
                    self.pending.id,
                ),
            )
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        gate.set()
        results = [queue.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(timeout=20)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum(results), 1)
        queue.close()

    def test_independent_process_coordinator_and_attempt_races(self):
        self.process_race()
        with auth.authorized_session(self.factory) as db:
            lease = claims._lease(db)
            lease.owner_id = None
            lease.owner_hash = None
            lease.lease_until = None
            lease.version += 1
        owner = self.acquire()
        self.operation(claims.start_run, owner, run_id=self.run.id, expected_version=1)
        self.process_race(owner)

    def test_real_restart_epoch_invalidation_and_audit_digests(self):
        owner, handle, row = self.owned()
        original_engine = self.engine
        self.engine.dispose()
        self.engine = create_engine(
            str(original_engine.url), connect_args={"timeout": 10}
        )
        self.addCleanup(self.engine.dispose)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.assertIsNone(self.acquire())
        row = self.operation(
            claims.heartbeat_attempt, handle, expected_version=row.version
        )
        with self.factory.begin() as db:
            settings = workflows.get_policy(db, project_id=100)
            workflows.save_policy(
                db,
                project_id=100,
                expected_version=settings.version,
                settings_json=settings.settings_json,
                restore=True,
            )
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.operation(
                claims.heartbeat_attempt, handle, expected_version=row.version
            )
        self.operation(
            claims.safety_cleanup,
            owner,
            attempt_id=handle.attempt_id,
            expected_version=row.version,
            state="cancelled",
        )
        with self.factory() as db:
            audits = db.scalars(
                select(InfraAutomationAudit).where(
                    InfraAutomationAudit.target_id == handle.attempt_id
                )
            ).all()
            self.assertTrue(all(a.before_digest != a.after_digest for a in audits))

    def test_log_utf8_json_overhead_and_full_scope_counter_types(self):
        _, handle, row = self.owned()
        with self.assertRaises(ValueError):
            LogChunk(sequence=1, text="é" * 8193)
        for sequence in range(1, 64):
            row = self.operation(
                claims.append_log,
                handle,
                expected_version=row.version,
                chunk=LogChunk(sequence=sequence, text="x" * 16384),
            )
        self.assertLess(row.log_bytes, 1048576)
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.append_log,
                handle,
                expected_version=row.version,
                chunk=LogChunk(sequence=64, text="x" * 16384),
            )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.heartbeat_attempt,
                replace(handle, fence=True),
                expected_version=row.version,
            )

    def test_queued_start_archive_and_dependency_and_deadline_denials(self):
        owner = self.acquire()
        with self.factory.begin() as db:
            workflow = workflows.get_workflow(db, self.run.workflow_id)
            workflow.archived = True
            workflow.draft_version += 1
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.operation(
                claims.start_run, owner, run_id=self.run.id, expected_version=1
            )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.start_run,
                owner,
                run_id=self.run.id,
                expected_version=1,
                now=self.now + timedelta(minutes=10),
            )

    def test_prepare_initial_attempt_uses_finite_deadline_and_no_duplicates(self):
        owner = self.acquire()
        self.operation(claims.start_run, owner, run_id=self.run.id, expected_version=1)
        self.assertIsNone(
            self.operation(
                claims.prepare_attempt,
                owner,
                run_id=self.run.id,
                step_id="upload",
                handler_id="test",
                handler_version="1",
                retry_safe=True,
            )
        )
        self.request["key_digest"] = support.digest(b"another")
        run = self.admit()
        self.operation(claims.start_run, owner, run_id=run.id, expected_version=1)
        row = self.operation(
            claims.prepare_attempt,
            owner,
            run_id=run.id,
            step_id="upload",
            handler_id="test",
            handler_version="1",
            retry_safe=True,
        )
        self.assertEqual(repo.utc(row.deadline_at), self.now + timedelta(seconds=300))

    def test_attempt_secret_cannot_forge_sibling_or_coordinator(self):
        owner, handle, _ = self.owned()
        self.assertNotEqual(owner.owner_secret, handle.owner_secret)
        forged_coordinator = CoordinatorHandle(
            handle.owner_id, handle.owner_secret, handle.generation
        )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.renew_coordinator,
                forged_coordinator,
                project_id=100,
                workspace_id=100,
            )

        with self.assertRaises(LifecycleError):
            self.operation(
                claims.renew_coordinator, handle, project_id=100, workspace_id=100
            )
        self.request["key_digest"] = support.digest(b"sibling")
        run = self.admit()
        pending = self.attempt(run)
        self.operation(claims.start_run, owner, run_id=run.id, expected_version=1)
        sibling = self.operation(
            claims.claim_attempt, owner, attempt_id=pending.id, expected_version=1
        )
        sibling_row = self.operation(claims.start_attempt, sibling, expected_version=2)
        forged = replace(sibling, owner_secret=handle.owner_secret)
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.complete_attempt,
                forged,
                expected_version=sibling_row.version,
                state="failed",
            )

    def test_and_dependencies_require_every_typed_committed_success(self):
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {},
            "steps": [
                {
                    "id": "one",
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "source": {"kind": "uploaded"},
                },
                {
                    "id": "two",
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "source": {"kind": "uploaded"},
                },
                {
                    "id": "analysis",
                    "kind": "shared_analysis",
                    "depends_on": ["one", "two"],
                    "artifact": {
                        "ref": "step",
                        "step_id": "one",
                        "output": "screened_artifacts",
                    },
                },
            ],
        }
        snapshot = self.export(self.publish_fixture(definition), inputs={})
        self.request.update(snapshot=snapshot, key_digest=support.digest(b"dag"))
        run = self.admit()
        owner = self.acquire()
        self.operation(claims.start_run, owner, run_id=run.id, expected_version=1)

        def prepare(step):
            return self.operation(
                claims.prepare_attempt,
                owner,
                run_id=run.id,
                step_id=step,
                handler_id="test",
                handler_version="1",
                retry_safe=True,
            )

        self.assertIsNone(prepare("analysis"))
        for step in ("one", "two"):
            attempt = prepare(step)
            handle = self.operation(
                claims.claim_attempt, owner, attempt_id=attempt.id, expected_version=1
            )
            row = self.operation(claims.start_attempt, handle, expected_version=2)
            output = OutputReference(
                kind="screened_artifacts",
                reference=step,
                digest=support.digest(step.encode()),
            )
            row = self.operation(
                claims.register_upload,
                handle,
                expected_version=row.version,
                reference=output,
            )
            row = self.operation(
                claims.commit_output,
                handle,
                expected_version=row.version,
                output=output,
            )
            self.assertIsNone(prepare("analysis"))
            self.operation(
                claims.complete_attempt,
                handle,
                expected_version=row.version,
                state="succeeded",
            )
            if step == "one":
                self.assertIsNone(prepare("analysis"))
        self.assertIsNotNone(prepare("analysis"))

    def test_coordinator_release_and_all_stop_mutations_are_atomic(self):
        owner = self.acquire()
        self.operation(
            claims.stop_run,
            owner,
            run_id=self.run.id,
            expected_version=1,
            state="cancelled",
        )
        with self.factory() as db:
            self.assertEqual(repo.get_attempt(db, self.pending.id).state, "cancelled")
        self.assertTrue(
            self.operation(
                claims.release_coordinator, owner, project_id=100, workspace_id=100
            )
        )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.renew_coordinator, owner, project_id=100, workspace_id=100
            )
        successor = self.acquire()
        self.assertGreater(successor.generation, owner.generation)

    def test_every_owned_boundary_rollback_and_reopen_commit(self):
        def evidence():
            with self.factory() as db:
                return tuple(
                    tuple(
                        tuple(row)
                        for row in db.execute(
                            text("SELECT * FROM " + table + " ORDER BY 1")
                        )
                    )
                    for table in (
                        "infra_automation_runs",
                        "infra_automation_attempts",
                        "infra_automation_coordinator_lease",
                        "infra_automation_audit",
                    )
                )

        def boundary(function, *args, **kwargs):
            before = evidence()
            with self.assertRaises(RuntimeError):
                with auth.authorized_session(self.factory) as db:
                    function(db, *args, **kwargs, now=self.now)
                    raise RuntimeError("crash before outer commit")
            self.engine.dispose()
            self.assertEqual(evidence(), before)
            result = self.operation(function, *args, **kwargs)
            self.engine.dispose()
            self.assertNotEqual(evidence(), before)
            return result

        owner = boundary(claims.acquire_coordinator, project_id=100, workspace_id=100)
        boundary(claims.renew_coordinator, owner, project_id=100, workspace_id=100)
        boundary(claims.start_run, owner, run_id=self.run.id, expected_version=1)
        handle = boundary(
            claims.claim_attempt, owner, attempt_id=self.pending.id, expected_version=1
        )
        row = boundary(claims.start_attempt, handle, expected_version=2)
        row = boundary(claims.heartbeat_attempt, handle, expected_version=row.version)
        row = boundary(
            claims.append_log,
            handle,
            expected_version=row.version,
            chunk=LogChunk(sequence=1, text="safe"),
        )
        output = OutputReference(
            kind="screened_artifacts", reference="safe", digest=support.digest(b"safe")
        )
        row = boundary(
            claims.register_upload,
            handle,
            expected_version=row.version,
            reference=output,
        )
        row = boundary(
            claims.commit_output, handle, expected_version=row.version, output=output
        )
        boundary(
            claims.complete_attempt,
            handle,
            expected_version=row.version,
            state="succeeded",
        )
        with self.factory() as db:
            version = repo.get_run(db, self.run.id).version
        boundary(
            claims.stop_run,
            owner,
            run_id=self.run.id,
            expected_version=version,
            state="failed",
        )
        self.request["key_digest"] = support.digest(b"boundary-prepare")
        run = self.admit()
        boundary(claims.start_run, owner, run_id=run.id, expected_version=1)
        row = boundary(
            claims.prepare_attempt,
            owner,
            run_id=run.id,
            step_id="upload",
            handler_id="test",
            handler_version="1",
            retry_safe=True,
        )
        boundary(
            claims.safety_cleanup,
            owner,
            attempt_id=row.id,
            expected_version=1,
            state="cancelled",
        )
        boundary(claims.release_coordinator, owner, project_id=100, workspace_id=100)

    def test_storage_exact_bound_one_over_global_and_terminal_evidence(self):
        _, handle, row = self.owned()
        self.request["key_digest"] = support.digest(b"retained-terminal")
        terminal = self.admit()
        with self.factory.begin() as db:
            repo.transition_run(
                db,
                run_id=terminal.id,
                expected_version=1,
                state="cancelled",
                audit_actor=self.actor,
                reason="synthetic",
                now=self.now,
            )
        with self.factory() as db:
            used = sum(r.retained_bytes for r in repo.list_runs(db, project_id=100))
        chunk = LogChunk(sequence=1, text="safe")
        delta = len(support.canonical([chunk.model_dump()])) - 2
        for bounds in (
            EngineBounds(project_bytes=used + delta - 1),
            EngineBounds(global_bytes=used + delta - 1),
        ):
            with self.assertRaises(LifecycleError):
                self.operation(
                    claims.append_log,
                    handle,
                    expected_version=row.version,
                    chunk=chunk,
                    bounds=bounds,
                )
            with self.factory() as db:
                self.assertEqual(
                    repo.get_attempt(db, handle.attempt_id).version, row.version
                )
                self.assertEqual(
                    sum(r.retained_bytes for r in repo.list_runs(db, project_id=100)),
                    used,
                )
        row = self.operation(
            claims.append_log,
            handle,
            expected_version=row.version,
            chunk=chunk,
            bounds=EngineBounds(project_bytes=used + delta, global_bytes=used + delta),
        )
        used += delta
        output = OutputReference(
            kind="screened_artifacts", reference="safe", digest=support.digest(b"safe")
        )
        delta = len(support.canonical([output.model_dump()])) - 2
        row = self.operation(
            claims.register_upload,
            handle,
            expected_version=row.version,
            reference=output,
            bounds=EngineBounds(project_bytes=used + delta, global_bytes=used + delta),
        )
        used += delta
        replay = self.operation(
            claims.register_upload,
            handle,
            expected_version=row.version - 1,
            reference=output,
            bounds=EngineBounds(project_bytes=used, global_bytes=used),
        )
        self.assertEqual(replay.version, row.version)
        delta = len(support.canonical(output.model_dump()))
        version = row.version
        row = self.operation(
            claims.commit_output,
            handle,
            expected_version=version,
            output=output,
            bounds=EngineBounds(project_bytes=used + delta, global_bytes=used + delta),
        )
        used += delta
        self.operation(
            claims.commit_output,
            handle,
            expected_version=version,
            output=output,
            bounds=EngineBounds(project_bytes=used, global_bytes=used),
        )
        with self.factory() as db:
            self.assertEqual(
                sum(r.retained_bytes for r in repo.list_runs(db, project_id=100)), used
            )

    def test_initial_attempt_empty_json_quota_failure_rolls_back_creation(self):
        owner = self.acquire()
        self.request["key_digest"] = support.digest(b"initial-json")
        run = self.admit()
        self.operation(claims.start_run, owner, run_id=run.id, expected_version=1)
        with self.factory() as db:
            used = sum(r.retained_bytes for r in repo.list_runs(db, project_id=100))
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.prepare_attempt,
                owner,
                run_id=run.id,
                step_id="upload",
                handler_id="test",
                handler_version="1",
                retry_safe=True,
                bounds=EngineBounds(project_bytes=used + 3),
            )
        with self.factory() as db:
            self.assertEqual(repo.list_attempts(db, run_id=run.id), [])
            before = repo.get_run(db, run.id).retained_bytes
        self.operation(
            claims.prepare_attempt,
            owner,
            run_id=run.id,
            step_id="upload",
            handler_id="test",
            handler_version="1",
            retry_safe=True,
            bounds=EngineBounds(project_bytes=used + 4),
        )
        with self.factory() as db:
            self.assertEqual(repo.get_run(db, run.id).retained_bytes, before + 4)

    def test_expired_attempt_lease_and_live_denial_reject_every_write_class(self):
        owner, handle, row = self.owned()
        self.operation(
            claims.renew_coordinator,
            owner,
            project_id=100,
            workspace_id=100,
            now=self.now + timedelta(seconds=10),
        )
        output = OutputReference(
            kind="screened_artifacts", reference="safe", digest=support.digest(b"safe")
        )
        operations = (
            (claims.heartbeat_attempt, {}),
            (claims.append_log, {"chunk": LogChunk(sequence=1, text="safe")}),
            (claims.register_upload, {"reference": output}),
            (claims.commit_output, {"output": output}),
            (claims.complete_attempt, {"state": "failed"}),
        )
        for function, payload in operations:
            with (
                self.subTest(operation=function.__name__),
                self.assertRaises(LifecycleError),
            ):
                self.operation(
                    function,
                    handle,
                    expected_version=row.version,
                    now=self.now + timedelta(seconds=30),
                    **payload,
                )
        self.member("read-only")
        for function, payload in operations:
            with (
                self.subTest(operation=function.__name__),
                self.assertRaises(auth.TrustedAuthorizationError),
            ):
                self.operation(
                    function,
                    handle,
                    expected_version=row.version,
                    now=self.now + timedelta(seconds=10),
                    **payload,
                )

    def test_corrupt_other_run_retained_counter_denies_global_growth(self):
        _, handle, row = self.owned()
        self.request["key_digest"] = support.digest(b"corrupt-other")
        other = self.admit()
        with self.factory.begin() as db:
            db.execute(
                text(
                    "UPDATE infra_automation_runs SET retained_bytes='corrupt',version=version+1 WHERE id=:id"
                ),
                {"id": other.id},
            )
        with self.factory() as db:
            before_audits = len(db.scalars(select(InfraAutomationAudit)).all())
            run_version = repo.get_run(db, self.run.id).version
        with self.assertRaises(LifecycleError) as denied:
            self.operation(
                claims.append_log,
                handle,
                expected_version=row.version,
                chunk=LogChunk(sequence=1, text="safe"),
            )
        self.assertEqual(denied.exception.status_code, 503)
        with self.factory() as db:
            self.assertEqual(
                repo.get_attempt(db, handle.attempt_id).version, row.version
            )
            self.assertEqual(repo.get_run(db, self.run.id).version, run_version)
            self.assertEqual(
                len(db.scalars(select(InfraAutomationAudit)).all()), before_audits
            )

    def test_finish_run_requires_live_authority_and_all_committed_outputs(self):
        owner, handle, row = self.owned()
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.finish_run,
                owner,
                run_id=self.run.id,
                expected_version=2,
                state="succeeded",
            )
        output = OutputReference(
            kind="screened_artifacts", reference="safe", digest=support.digest(b"safe")
        )
        row = self.operation(
            claims.register_upload,
            handle,
            expected_version=row.version,
            reference=output,
        )
        row = self.operation(
            claims.commit_output, handle, expected_version=row.version, output=output
        )
        self.operation(
            claims.complete_attempt,
            handle,
            expected_version=row.version,
            state="succeeded",
        )
        with self.factory() as db:
            version = repo.get_run(db, self.run.id).version
        with self.assertRaises(RuntimeError):
            with auth.authorized_session(self.factory) as db:
                claims.finish_run(
                    db,
                    owner,
                    run_id=self.run.id,
                    expected_version=version,
                    state="succeeded",
                    now=self.now,
                )
                raise RuntimeError("crash before commit")
        self.engine.dispose()
        with self.factory() as db:
            self.assertEqual(repo.get_run(db, self.run.id).state, "running")
        result = self.operation(
            claims.finish_run,
            owner,
            run_id=self.run.id,
            expected_version=version,
            state="succeeded",
        )
        self.engine.dispose()
        with self.factory() as db:
            self.assertEqual(repo.get_run(db, self.run.id).state, "succeeded")
        self.assertEqual(result.state, "succeeded")
