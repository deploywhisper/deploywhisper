"""Safe retry, immutable output adoption and external uncertainty boundaries."""

from __future__ import annotations

from datetime import timedelta
from importlib import import_module
from infra_automation.state import AuditActor
from services import infra_automation_engine_support as engine_support


from infra_automation import claims
from infra_automation.lifecycle import LifecycleError
from infra_automation.state import OutputReference, EngineBounds
from models.repositories import infra_automation_runs as repo
from services import project_service as auth
from services import infra_automation_support as support
from tests.test_infra_automation import test_engine_claims as base


class EngineRecoveryClaimsTests(base.LifecycleCase):
    publish_fixture = base.EngineClaimsTests.publish_fixture
    enable = base.EngineClaimsTests.enable
    export = base.EngineClaimsTests.export
    admit = base.EngineClaimsTests.admit
    attempt = base.EngineClaimsTests.attempt

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

    operation = base.EngineClaimsTests.operation
    acquire = base.EngineClaimsTests.acquire
    owned = base.EngineClaimsTests.owned

    def failed_attempt(self, state="failed", output=False):
        owner, handle, row = self.owned()
        if output:
            reference = OutputReference(
                kind="screened_artifacts",
                reference="safe",
                digest=support.digest(b"safe"),
            )
            row = self.operation(
                claims.register_upload,
                handle,
                expected_version=row.version,
                reference=reference,
            )
            row = self.operation(
                claims.commit_output,
                handle,
                expected_version=row.version,
                output=reference,
            )
        row = self.operation(
            claims.complete_attempt, handle, expected_version=row.version, state=state
        )
        return owner, handle, row

    def test_retry_creates_new_bound_attempt_and_distinct_secret_max_three(self):
        owner, old, previous = self.failed_attempt()
        for expected in (2, 3):
            row = self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=previous.id,
                expected_version=previous.version,
            )
            self.assertEqual(row.attempt_number, expected)
            self.assertEqual(row.fence, expected)
            self.assertEqual(
                (row.input_digest, row.handler_id, row.handler_version),
                (previous.input_digest, previous.handler_id, previous.handler_version),
            )
            handle = self.operation(
                claims.claim_attempt,
                owner,
                attempt_id=row.id,
                expected_version=row.version,
            )
            self.assertNotEqual(handle.owner_secret, old.owner_secret)
            row = self.operation(claims.start_attempt, handle, expected_version=2)
            previous = self.operation(
                claims.complete_attempt,
                handle,
                expected_version=row.version,
                state="failed",
            )
        self.assertIsNone(
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=previous.id,
                expected_version=previous.version,
            )
        )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.heartbeat_attempt, old, expected_version=previous.version
            )

    def test_adopt_committed_output_preserves_old_attempt_and_replay(self):
        owner, old, previous = self.failed_attempt(output=True)
        with self.factory() as db:
            old_output = repo.get_attempt(db, old.attempt_id).output_json
        pending = self.operation(
            claims.prepare_retry,
            owner,
            previous_attempt_id=previous.id,
            expected_version=previous.version,
        )
        current = self.operation(
            claims.claim_attempt, owner, attempt_id=pending.id, expected_version=1
        )
        row = self.operation(claims.start_attempt, current, expected_version=2)
        version = row.version
        adopted = self.operation(
            claims.adopt_committed_output, current, expected_version=version
        )
        self.assertEqual(adopted.output_json, old_output)
        self.assertEqual(
            self.operation(
                claims.adopt_committed_output, current, expected_version=version
            ).version,
            adopted.version,
        )
        with self.factory() as db:
            self.assertEqual(
                repo.get_attempt(db, old.attempt_id).output_json, old_output
            )
            self.assertEqual(
                repo.get_attempt(db, old.attempt_id).version, previous.version
            )
        self.operation(
            claims.complete_attempt,
            current,
            expected_version=adopted.version,
            state="succeeded",
        )

    def test_retry_epoch_deadline_unsafe_and_quota_fail_closed(self):
        owner, _, previous = self.failed_attempt()
        with self.factory() as db:
            used = sum(row.retained_bytes for row in repo.list_runs(db, project_id=100))
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=previous.id,
                expected_version=previous.version,
                bounds=EngineBounds(project_bytes=used + 3),
            )
        with self.factory() as db:
            self.assertEqual(len(repo.list_attempts(db, run_id=self.run.id)), 1)
        self.member("read-only")
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=previous.id,
                expected_version=previous.version,
            )

    def test_retry_and_adoption_crash_before_commit_leave_no_new_evidence(self):
        owner, _, previous = self.failed_attempt(output=True)
        with self.assertRaises(RuntimeError):
            with auth.authorized_session(self.factory) as db:
                claims.prepare_retry(
                    db,
                    owner,
                    previous_attempt_id=previous.id,
                    expected_version=previous.version,
                    now=self.now,
                )
                raise RuntimeError("crash")
        self.engine.dispose()
        with self.factory() as db:
            self.assertEqual(len(repo.list_attempts(db, run_id=self.run.id)), 1)
        pending = self.operation(
            claims.prepare_retry,
            owner,
            previous_attempt_id=previous.id,
            expected_version=previous.version,
        )
        handle = self.operation(
            claims.claim_attempt, owner, attempt_id=pending.id, expected_version=1
        )
        row = self.operation(claims.start_attempt, handle, expected_version=2)
        with self.assertRaises(RuntimeError):
            with auth.authorized_session(self.factory) as db:
                claims.adopt_committed_output(
                    db, handle, expected_version=row.version, now=self.now
                )
                raise RuntimeError("crash")
        self.engine.dispose()
        with self.factory() as db:
            recovered = repo.get_attempt(db, row.id)
            self.assertIsNone(recovered.output_json)
            self.assertEqual(recovered.uploads_json, "[]")
        self.assertIsNotNone(
            self.operation(
                claims.adopt_committed_output, handle, expected_version=row.version
            ).output_json
        )

    def external_ready(self):
        from infra_automation.contracts import STEP_CONTRACTS

        definition = self.definition()
        snapshot = self.export(self.publish_fixture(definition), inputs={})
        self.request.update(snapshot=snapshot, key_digest=support.digest(b"external"))
        run = self.admit()
        owner = self.acquire()
        self.operation(claims.start_run, owner, run_id=run.id, expected_version=1)
        for step in snapshot.snapshot.definition.steps:
            pending = self.operation(
                claims.prepare_attempt,
                owner,
                run_id=run.id,
                step_id=step.id,
                handler_id="test-" + step.id,
                handler_version="1",
                retry_safe=False,
            )
            handle = self.operation(
                claims.claim_attempt, owner, attempt_id=pending.id, expected_version=1
            )
            row = self.operation(claims.start_attempt, handle, expected_version=2)
            if step.kind == "registered_github_handoff":
                return owner, handle, row
            output = OutputReference(
                kind=STEP_CONTRACTS[step.kind].output,
                reference=step.id,
                digest=support.digest(step.id.encode()),
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
            self.operation(
                claims.complete_attempt,
                handle,
                expected_version=row.version,
                state="succeeded",
            )
        self.fail("Missing external fixture step")

    def test_external_intent_precedes_double_and_dropped_response_never_resends(self):
        owner, handle, row = self.external_ready()
        with self.assertRaises(RuntimeError):
            with auth.authorized_session(self.factory) as db:
                claims.begin_external(
                    db, handle, expected_version=row.version, now=self.now
                )
                raise RuntimeError("crash before invocation commit")
        self.engine.dispose()
        with self.factory() as db:
            self.assertEqual(repo.get_run(db, handle.run_id).state, "running")
            self.assertFalse(repo.get_run(db, handle.run_id).external_possible)
        run = self.operation(
            claims.begin_external, handle, expected_version=row.version
        )
        self.engine.dispose()
        calls = []

        def trusted_double():
            with self.factory() as db:
                committed = repo.get_run(db, handle.run_id)
                self.assertEqual(committed.state, "handing_off")
                self.assertTrue(committed.external_possible)
            calls.append("accepted")
            raise RuntimeError("dropped response")

        with self.assertRaises(RuntimeError):
            trusted_double()
        with self.assertRaises(LifecycleError):
            self.operation(claims.begin_external, handle, expected_version=row.version)
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.complete_attempt,
                handle,
                expected_version=row.version,
                state="failed",
            )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=row.id,
                expected_version=row.version,
            )
        unknown = self.operation(
            claims.stop_run,
            owner,
            run_id=run.id,
            expected_version=run.version,
            state="delivery_unknown",
        )
        self.assertEqual(unknown.state, "delivery_unknown")
        self.assertEqual(calls, ["accepted"])
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.stop_run,
                owner,
                run_id=run.id,
                expected_version=unknown.version,
                state="cancelled",
            )

    def test_external_wrong_kind_and_revocation_deny_before_intent(self):
        _, handle, row = self.owned()
        with self.assertRaises(LifecycleError):
            self.operation(claims.begin_external, handle, expected_version=row.version)
        self.member("read-only")
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.operation(claims.begin_external, handle, expected_version=row.version)

    def test_adoption_partial_quota_failure_is_atomic_and_epoch_checked(self):
        owner, _, previous = self.failed_attempt(output=True)
        pending = self.operation(
            claims.prepare_retry,
            owner,
            previous_attempt_id=previous.id,
            expected_version=previous.version,
        )
        handle = self.operation(
            claims.claim_attempt, owner, attempt_id=pending.id, expected_version=1
        )
        row = self.operation(claims.start_attempt, handle, expected_version=2)
        with self.factory() as db:
            used = sum(run.retained_bytes for run in repo.list_runs(db, project_id=100))
            output = OutputReference.model_validate_json(previous.output_json)
        upload_delta = len(support.canonical([output.model_dump()])) - 2
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.adopt_committed_output,
                handle,
                expected_version=row.version,
                bounds=EngineBounds(project_bytes=used + upload_delta),
            )
        with self.factory() as db:
            current = repo.get_attempt(db, row.id)
            self.assertEqual(current.uploads_json, "[]")
            self.assertIsNone(current.output_json)
            self.assertEqual(current.version, row.version)
            self.assertEqual(
                sum(run.retained_bytes for run in repo.list_runs(db, project_id=100)),
                used,
            )
        from models.repositories import infra_automation_workflows as workflows

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
                claims.adopt_committed_output, handle, expected_version=row.version
            )

    def test_finite_retry_deadlines_unsafe_failure_and_changed_replay(self):
        owner, _, previous = self.failed_attempt()
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=previous.id,
                expected_version=previous.version,
                attempt_timeout_seconds=601,
            )
        successor = self.operation(
            claims.prepare_retry,
            owner,
            previous_attempt_id=previous.id,
            expected_version=previous.version,
            attempt_timeout_seconds=600,
        )
        self.assertEqual(
            repo.utc(successor.deadline_at), repo.utc(self.run.deadline_at)
        )
        self.assertIsNone(
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=previous.id,
                expected_version=previous.version,
            )
        )
        self.request["key_digest"] = support.digest(b"unsafe")
        run = self.admit()
        self.operation(claims.start_run, owner, run_id=run.id, expected_version=1)
        unsafe = self.operation(
            claims.prepare_attempt,
            owner,
            run_id=run.id,
            step_id="upload",
            handler_id="unsafe",
            handler_version="1",
            retry_safe=False,
        )
        unsafe = self.operation(
            claims.safety_cleanup,
            owner,
            attempt_id=unsafe.id,
            expected_version=unsafe.version,
            state="failed",
        )
        self.assertIsNone(
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=unsafe.id,
                expected_version=unsafe.version,
            )
        )
        later = self.now + timedelta(minutes=10)
        successor_owner = self.operation(
            claims.acquire_coordinator, project_id=100, workspace_id=100, now=later
        )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.prepare_retry,
                successor_owner,
                previous_attempt_id=unsafe.id,
                expected_version=unsafe.version,
                now=later,
            )

    def test_missing_adoption_has_no_mutation_and_permanent_outcome_forbids_retry(self):
        owner, _, previous = self.failed_attempt()
        pending = self.operation(
            claims.prepare_retry,
            owner,
            previous_attempt_id=previous.id,
            expected_version=previous.version,
        )
        handle = self.operation(
            claims.claim_attempt, owner, attempt_id=pending.id, expected_version=1
        )
        row = self.operation(claims.start_attempt, handle, expected_version=2)
        self.assertIsNone(
            self.operation(
                claims.adopt_committed_output, handle, expected_version=row.version
            )
        )
        with auth.authorized_session(self.factory) as db:
            failed = claims.complete_attempt(
                db, handle, expected_version=row.version, state="failed", now=self.now
            )
            run = repo.get_run(db, handle.run_id)
            claims.stop_run(
                db,
                owner,
                run_id=run.id,
                expected_version=run.version,
                state="failed",
                now=self.now,
            )
        with self.assertRaises(LifecycleError):
            self.operation(
                claims.prepare_retry,
                owner,
                previous_attempt_id=failed.id,
                expected_version=failed.version,
            )
