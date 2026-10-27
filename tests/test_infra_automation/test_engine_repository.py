"""Atomic engine evidence, CAS and bounded cancellation regressions."""

from __future__ import annotations
from datetime import timedelta
from importlib import import_module
from unittest.mock import patch
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from infra_automation.state import AuditActor, OutputReference
from models.repositories import infra_automation_runs as repo
from models.tables import InfraAutomationAudit
from services.infra_automation_support import digest
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests


class EngineRepositoryTests(LifecycleCase):
    publish_fixture = snapshot_tests.WorkflowSnapshotTests.publish_fixture
    enable = snapshot_tests.WorkflowSnapshotTests.enable
    export = snapshot_tests.WorkflowSnapshotTests.export

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
            request_digest=digest(b"request"),
            key_digest=digest(b"key"),
            requested_by="human-a",
            deadline_at=self.now + timedelta(minutes=10),
            audit_actor=self.actor,
            reason="synthetic",
            now=self.now,
        )

    def admit(self):
        with self.factory.begin() as db:
            return repo.create_run(db, **self.request)

    def attempt(self, run):
        with self.factory.begin() as db:
            return repo.create_attempt(
                db,
                run_id=run.id,
                step_id="upload",
                handler_id="synthetic",
                handler_version="1",
                retry_safe=True,
                deadline_at=self.now + timedelta(minutes=5),
                audit_actor=self.actor,
                reason="synthetic",
                now=self.now,
            )

    def count_audit(self):
        with self.factory() as db:
            return db.scalar(select(func.count()).select_from(InfraAutomationAudit))

    def test_admission_replay_changed_binding_and_immutable_sql(self):
        run = self.admit()
        count = self.count_audit()
        self.assertEqual(self.admit().id, run.id)
        self.assertEqual(self.count_audit(), count)
        with self.factory.begin() as db, self.assertRaises(ValueError):
            repo.create_run(
                db, **{**self.request, "request_digest": digest(b"changed")}
            )
        for statement in (
            "UPDATE infra_automation_runs SET snapshot_bytes=x'01',version=version+1",
            "DELETE FROM infra_automation_runs",
            "INSERT OR REPLACE INTO infra_automation_runs SELECT * FROM infra_automation_runs",
        ):
            with (
                self.subTest(statement=statement),
                self.factory.begin() as db,
                self.assertRaises(IntegrityError),
            ):
                db.execute(text(statement))

    def test_cas_audit_and_transaction_failure_are_atomic(self):
        run = self.admit()
        count = self.count_audit()
        with self.factory.begin() as db:
            self.assertIsNone(
                repo.transition_run(
                    db,
                    run_id=run.id,
                    expected_version=9,
                    state="running",
                    audit_actor=self.actor,
                    reason="stale",
                    now=self.now,
                )
            )
        self.assertEqual(self.count_audit(), count)
        with (
            self.assertRaises(RuntimeError),
            self.factory.begin() as db,
            patch.object(
                repo, "append_audit", side_effect=RuntimeError("synthetic disk fault")
            ),
        ):
            repo.transition_run(
                db,
                run_id=run.id,
                expected_version=1,
                state="running",
                audit_actor=self.actor,
                reason="start",
                now=self.now,
            )
        with self.factory() as db:
            self.assertEqual(repo.get_run(db, run.id).state, "queued")
        self.assertEqual(self.count_audit(), count)
        with self.factory.begin() as db:
            repo.transition_run(
                db,
                run_id=run.id,
                expected_version=1,
                state="running",
                audit_actor=self.actor,
                reason="start",
                now=self.now,
            )
        with self.factory() as db:
            self.assertEqual(repo.get_run(db, run.id).state, "running")
        self.assertEqual(self.count_audit(), count + 1)

    def test_queued_cancel_and_timeout_stop_pending_descendants(self):
        for target in ("cancelled", "timed_out"):
            self.request["key_digest"] = digest(target.encode())
            run = self.admit()
            attempt = self.attempt(run)
            with self.factory.begin() as db:
                repo.transition_run(
                    db,
                    run_id=run.id,
                    expected_version=1,
                    state=target,
                    audit_actor=self.actor,
                    reason="stop",
                    now=self.now,
                )
            with self.factory() as db:
                self.assertEqual(repo.get_attempt(db, attempt.id).state, target)
                with self.assertRaises(ValueError):
                    repo.transition_run(
                        db,
                        run_id=run.id,
                        expected_version=2,
                        state="running",
                        audit_actor=self.actor,
                        reason="reopen",
                        now=self.now,
                    )

    def test_success_requires_committed_typed_output_and_output_never_rewrites(self):
        run = self.admit()
        attempt = self.attempt(run)
        with self.factory.begin() as db:
            repo.transition_run(
                db,
                run_id=run.id,
                expected_version=1,
                state="running",
                audit_actor=self.actor,
                reason="start",
                now=self.now,
            )
            with self.assertRaises(ValueError):
                repo.transition_run(
                    db,
                    run_id=run.id,
                    expected_version=2,
                    state="succeeded",
                    audit_actor=self.actor,
                    reason="finish",
                    now=self.now,
                )
            for version, state in ((1, "claimed"), (2, "running")):
                repo.transition_attempt(
                    db,
                    attempt_id=attempt.id,
                    expected_version=version,
                    state=state,
                    audit_actor=self.actor,
                    reason="start",
                    now=self.now,
                )
            output = OutputReference(
                kind="screened_artifacts",
                reference="synthetic",
                digest=digest(b"output"),
            )
            row = repo.commit_output(
                db,
                attempt_id=attempt.id,
                expected_version=3,
                output=output,
                audit_actor=self.actor,
                reason="output",
                now=self.now,
            )
            self.assertEqual(row.version, 4)
            self.assertEqual(
                repo.commit_output(
                    db,
                    attempt_id=attempt.id,
                    expected_version=3,
                    output=output,
                    audit_actor=self.actor,
                    reason="replay",
                    now=self.now,
                ).version,
                4,
            )
            repo.transition_attempt(
                db,
                attempt_id=attempt.id,
                expected_version=4,
                state="succeeded",
                audit_actor=self.actor,
                reason="finish",
                now=self.now,
            )
            repo.transition_run(
                db,
                run_id=run.id,
                expected_version=2,
                state="succeeded",
                audit_actor=self.actor,
                reason="finish",
                now=self.now,
            )
        with self.factory.begin() as db, self.assertRaises(IntegrityError):
            db.execute(
                text(
                    "UPDATE infra_automation_attempts SET output_json='{}',version=version+1"
                )
            )

    def test_scope_foreign_keys_and_clock_rollback(self):
        run = self.admit()
        attempt = self.attempt(run)
        with self.factory.begin() as db, self.assertRaises(IntegrityError):
            db.execute(
                text(
                    "UPDATE infra_automation_attempts SET workspace_id=200,version=version+1"
                )
            )
        with self.factory.begin() as db, self.assertRaises(ValueError):
            repo.transition_attempt(
                db,
                attempt_id=attempt.id,
                expected_version=1,
                state="claimed",
                audit_actor=self.actor,
                reason="rollback",
                now=self.now - timedelta(seconds=1),
            )

    def test_every_run_edge_recovers_exact_state_and_audit_around_commit(self):
        from infra_automation.state import RUN_TRANSITIONS
        from models.tables import InfraAutomationRun

        for old, targets in RUN_TRANSITIONS.items():
            for target in targets:
                if target == "succeeded":
                    # Full typed-output success path is covered separately above.
                    continue
                with self.subTest(old=old, target=target):
                    self.request["key_digest"] = digest((old + target).encode())
                    run = self.admit()
                    with self.factory.begin() as db:
                        row = db.get(InfraAutomationRun, run.sequence)
                        row.state = old
                        row.version = 2
                    before = self.count_audit()
                    for committed in (False, True):
                        with self.factory() as db:
                            repo.transition_run(
                                db,
                                run_id=run.id,
                                expected_version=2,
                                state=target,
                                audit_actor=self.actor,
                                reason="commit boundary",
                                now=self.now,
                            )
                            if committed:
                                db.commit()
                            else:
                                db.rollback()
                        with self.factory() as db:
                            recovered = repo.get_run(db, run.id)
                            self.assertEqual(
                                recovered.state, target if committed else old
                            )
                            self.assertEqual(recovered.version, 3 if committed else 2)
                        self.assertEqual(self.count_audit(), before + int(committed))

    def test_every_attempt_edge_recovers_exact_state_and_audit_around_commit(self):
        import json
        from infra_automation.state import ATTEMPT_TRANSITIONS
        from models.tables import InfraAutomationAttempt

        for old, targets in ATTEMPT_TRANSITIONS.items():
            for target in targets:
                with self.subTest(old=old, target=target):
                    self.request["key_digest"] = digest(
                        ("attempt" + old + target).encode()
                    )
                    run = self.admit()
                    attempt = self.attempt(run)
                    with self.factory.begin() as db:
                        row = db.get(InfraAutomationAttempt, attempt.sequence)
                        row.state = old
                        row.version = 2
                        if target == "succeeded":
                            output = OutputReference(
                                kind="screened_artifacts",
                                reference="synthetic",
                                digest=digest(b"output"),
                            )
                            row.output_json = json.dumps(output.model_dump())
                            row.output_digest = output.digest
                    before = self.count_audit()
                    for committed in (False, True):
                        with self.factory() as db:
                            repo.transition_attempt(
                                db,
                                attempt_id=attempt.id,
                                expected_version=2,
                                state=target,
                                audit_actor=self.actor,
                                reason="commit boundary",
                                now=self.now,
                            )
                            if committed:
                                db.commit()
                            else:
                                db.rollback()
                        with self.factory() as db:
                            recovered = repo.get_attempt(db, attempt.id)
                            self.assertEqual(
                                recovered.state, target if committed else old
                            )
                            self.assertEqual(recovered.version, 3 if committed else 2)
                        self.assertEqual(self.count_audit(), before + int(committed))

    def test_audit_records_before_and_after_digests(self):
        run = self.admit()
        with self.factory.begin() as db:
            repo.transition_run(
                db,
                run_id=run.id,
                expected_version=1,
                state="running",
                audit_actor=self.actor,
                reason="start",
                now=self.now,
            )
        with self.factory() as db:
            audit = db.scalars(
                select(InfraAutomationAudit)
                .where(InfraAutomationAudit.target_id == run.id)
                .order_by(InfraAutomationAudit.sequence)
            ).all()
            self.assertIsNone(audit[0].before_digest)
            self.assertTrue(audit[0].after_digest.startswith("sha256:"))
            self.assertEqual(audit[1].before_digest, audit[0].after_digest)
            self.assertNotEqual(audit[1].before_digest, audit[1].after_digest)
