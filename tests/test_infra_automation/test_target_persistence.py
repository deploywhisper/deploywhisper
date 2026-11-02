"""Canonical target reservations, transactional scope and durable history guards."""

from __future__ import annotations

from importlib import import_module
from datetime import timedelta
import json
import hashlib

from sqlalchemy import inspect
from models import database
from models.tables import (
    AnalysisReport,
    InfraAutomationDecision,
    InfraAutomationHandoff,
    InfraAutomationOutbox,
    InfraAutomationGrant,
)
from infra_automation.state import AuditActor
from models.repositories import infra_automation_runs as run_repository
from tests.test_infra_automation import test_workflow_snapshots as snapshots
import unittest
from unittest.mock import patch
from alembic.operations import Operations
from alembic.migration import MigrationContext

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models.repositories import infra_automation_targets as repository
from tests.test_infra_automation.lifecycle_support import LifecycleCase

D = "sha256:" + "a" * 64


class TargetPersistenceTests(LifecycleCase):
    enable = snapshots.WorkflowSnapshotTests.enable
    export = snapshots.WorkflowSnapshotTests.export
    publish_fixture = snapshots.WorkflowSnapshotTests.publish_fixture

    def snapshot(self):
        return json.dumps(
            dict(
                version=1,
                definition={},
                target_version=1,
                target_epoch=1,
                receiver_principal_id="receiver",
                receiver_authentication_version=1,
                captured_at=self.now.isoformat(),
            ),
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    def snapshot_digest(self):
        return "sha256:" + hashlib.sha256(self.snapshot()).hexdigest()

    def make_run(self, key="a"):
        self.enable()
        snapshot = self.export(self.publish_fixture())
        with self.factory.begin() as db:
            return run_repository.create_run(
                db,
                snapshot=snapshot,
                request_digest="sha256:" + key * 64,
                key_digest="sha256:" + key * 64,
                requested_by="human-a",
                deadline_at=self.now + timedelta(minutes=10),
                audit_actor=AuditActor("human-a", "human", "admin"),
                reason="synthetic",
                now=self.now,
            )

    def setUp(self):
        super().setUp()
        self.principal("receiver", principal_type="service", audience="receiver")
        migration = import_module("migrations.versions.035_add_infra_handoffs")
        with self.engine.begin() as connection:
            for name, body in migration.GUARDS.items():
                connection.exec_driver_sql(f"CREATE TRIGGER {name} {body}")

    def create(self, db, target_id="prod", aliases=("production",)):
        return repository.create_target(
            db,
            target_id=target_id,
            definition_bytes=b"{}",
            definition_digest=D,
            enabled=True,
            receiver_principal_id="receiver",
            created_by="human-a",
            aliases=aliases,
            scopes=((100, 100),),
            now=self.now,
        )

    def test_alias_retirement_reserves_global_identity(self):
        with self.factory.begin() as db:
            self.create(db)
            repository.update_target(
                db,
                target_id="prod",
                expected_version=1,
                definition_bytes=b"{ }",
                definition_digest=D,
                enabled=True,
                receiver_principal_id="receiver",
                aliases=(),
                scopes=((100, 100),),
                now=self.now,
            )
            self.assertIsNone(repository.resolve_alias(db, "production"))
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            self.create(db, "other", ("production",))
        with self.factory() as db:
            self.assertEqual(repository.get_target(db, "prod").epoch, 2)

    def test_target_sequence_is_monotonic_and_cannot_replace_reserved_identity(self):
        with self.factory.begin() as db:
            first = self.create(db)
            second = self.create(db, "second", ())
            self.assertGreater(second.sequence, first.sequence)
        for sql in (
            "UPDATE infra_automation_targets SET sequence=sequence+10, version=2, epoch=2 WHERE id='prod'",
            "INSERT OR REPLACE INTO infra_automation_targets SELECT sequence, 'replacement', definition_bytes, definition_digest, version, epoch, enabled, receiver_principal_id, created_by, created_at, updated_at, last_observed_at FROM infra_automation_targets WHERE id='prod'",
        ):
            with (
                self.subTest(sql=sql),
                self.assertRaises(IntegrityError),
                self.factory.begin() as db,
            ):
                db.execute(text(sql))

    def test_compare_and_swap_and_transaction_rollback(self):
        with self.factory.begin() as db:
            self.create(db)
        with self.factory.begin() as db:
            self.assertIsNone(
                repository.update_target(
                    db,
                    target_id="prod",
                    expected_version=2,
                    definition_bytes=b"{}",
                    definition_digest=D,
                    enabled=False,
                    receiver_principal_id="receiver",
                    aliases=(),
                    scopes=((200, 200),),
                    now=self.now,
                )
            )
        with self.assertRaises(RuntimeError), self.factory.begin() as db:
            self.create(db, "rollback", ())
            raise RuntimeError("roll back caller-owned transaction")
        with self.factory() as db:
            self.assertIsNone(repository.get_target(db, "rollback"))
            self.assertEqual(repository.list_scopes(db, "prod"), [(100, 100)])

    def test_alias_and_target_identity_cannot_be_replaced_or_deleted(self):
        with self.factory.begin() as db:
            self.create(db)
        for sql in (
            "DELETE FROM infra_automation_target_aliases WHERE alias='production'",
            "UPDATE infra_automation_target_aliases SET target_id='other' WHERE alias='production'",
            "DELETE FROM infra_automation_targets WHERE id='prod'",
            "UPDATE infra_automation_targets SET id='other', version=2, epoch=2 WHERE id='prod'",
            "UPDATE infra_automation_targets SET enabled=0 WHERE id='prod'",
        ):
            with (
                self.subTest(sql=sql),
                self.assertRaises(IntegrityError),
                self.factory.begin() as db,
            ):
                db.execute(text(sql))

    def test_concrete_scope_cannot_cross_project(self):
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            repository.create_target(
                db,
                target_id="bad",
                definition_bytes=b"{}",
                definition_digest=D,
                enabled=True,
                receiver_principal_id="receiver",
                created_by="human-a",
                aliases=(),
                scopes=((100, 200),),
                now=self.now,
            )

    def test_held_lock_collisions_and_broken_claim_cannot_reacquire(self):
        run_one, run_two = self.make_run("a"), self.make_run("b")
        with self.factory.begin() as db:
            self.create(db)
            repository.acquire_lock(
                db,
                lock_id="lock-one",
                target_id="prod",
                run_id=run_one.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
            repository.capture_run_target(
                db,
                run_id=run_one.id,
                handoff_step_id="handoff",
                project_id=100,
                workspace_id=100,
                target_id="prod",
                target_epoch=1,
                requested_alias="production",
                lock_id="lock-one",
                snapshot_bytes=self.snapshot(),
                snapshot_digest=self.snapshot_digest(),
                now=self.now,
            )
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            repository.acquire_lock(
                db,
                lock_id="lock-two",
                target_id="prod",
                run_id=run_two.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
        with self.factory.begin() as db:
            self.assertIsNone(
                repository.resolve_lock(
                    db,
                    lock_id="lock-one",
                    expected_version=2,
                    status="broken",
                    reason="uncertain",
                    now=self.now,
                )
            )
            repository.resolve_lock(
                db,
                lock_id="lock-one",
                expected_version=1,
                status="broken",
                reason="uncertain",
                now=self.now,
            )
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            repository.acquire_lock(
                db,
                lock_id="replacement",
                target_id="prod",
                run_id=run_one.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
        with self.factory.begin() as db:
            repository.acquire_lock(
                db,
                lock_id="lock-two",
                target_id="prod",
                run_id=run_two.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
        for sql in (
            "DELETE FROM infra_automation_target_locks WHERE id='lock-one'",
            "UPDATE infra_automation_target_locks SET status='held', version=3 WHERE id='lock-one'",
            "UPDATE infra_automation_run_targets SET target_epoch=2",
            "DELETE FROM infra_automation_run_targets",
            "INSERT OR REPLACE INTO infra_automation_run_targets SELECT * FROM infra_automation_run_targets",
        ):
            with (
                self.subTest(sql=sql),
                self.assertRaises(IntegrityError),
                self.factory.begin() as db,
            ):
                db.execute(text(sql))

    def test_multi_target_collision_rolls_back_every_prior_lock_and_sidecar(self):
        run_one, run_two = self.make_run("a"), self.make_run("b")
        with self.factory.begin() as db:
            self.create(db)
            self.create(db, "other", ())
            repository.acquire_lock(
                db,
                lock_id="other-lock",
                target_id="other",
                run_id=run_two.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            repository.acquire_lock(
                db,
                lock_id="prod-lock",
                target_id="prod",
                run_id=run_one.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
            repository.capture_run_target(
                db,
                run_id=run_one.id,
                handoff_step_id="handoff",
                project_id=100,
                workspace_id=100,
                target_id="prod",
                target_epoch=1,
                requested_alias="production",
                lock_id="prod-lock",
                snapshot_bytes=self.snapshot(),
                snapshot_digest=self.snapshot_digest(),
                now=self.now,
            )
            repository.acquire_lock(
                db,
                lock_id="collision",
                target_id="other",
                run_id=run_one.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
        with self.factory() as db:
            self.assertIsNone(repository.get_held_lock(db, "prod"))
            self.assertEqual(repository.list_run_targets(db, run_one.id), [])
            self.assertEqual(repository.get_held_lock(db, "other").id, "other-lock")

    def test_alias_collision_cannot_be_hidden_in_another_project(self):
        with self.factory.begin() as db:
            self.create(db)
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            repository.create_target(
                db,
                target_id="other-project",
                definition_bytes=b"{}",
                definition_digest=D,
                enabled=True,
                receiver_principal_id="receiver",
                created_by="human-a",
                aliases=("production",),
                scopes=((200, 200),),
                now=self.now,
            )
        with self.factory() as db:
            self.assertEqual(
                repository.list_targets(db, project_id=200, workspace_id=200), []
            )
            self.assertEqual(repository.resolve_alias(db, "production").id, "prod")

    def test_sidecar_retains_original_case_while_resolving_normalized_alias(self):
        run = self.make_run()
        with self.factory.begin() as db:
            self.create(db)
            repository.acquire_lock(
                db,
                lock_id="lock",
                target_id="prod",
                run_id=run.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
            sidecar = repository.capture_run_target(
                db,
                run_id=run.id,
                handoff_step_id="handoff",
                project_id=100,
                workspace_id=100,
                target_id="prod",
                target_epoch=1,
                requested_alias="PRODUCTION",
                lock_id="lock",
                snapshot_bytes=self.snapshot(),
                snapshot_digest=self.snapshot_digest(),
                now=self.now,
            )
            self.assertEqual(sidecar.requested_alias, "PRODUCTION")
        with self.factory() as db:
            self.assertEqual(
                repository.get_run_target(db, run.id, "handoff").requested_alias,
                "PRODUCTION",
            )

    def test_sidecar_requires_exact_snapshot_and_concrete_run_scope(self):
        run = self.make_run()
        with self.factory.begin() as db:
            self.create(db)
            repository.acquire_lock(
                db,
                lock_id="lock",
                target_id="prod",
                run_id=run.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
        for values in (
            {"snapshot_bytes": b"changed"},
            {"snapshot_bytes": b'{"definition":'},
            {"snapshot_bytes": b"\xff"},
            {"target_epoch": 2},
            {"project_id": 200, "workspace_id": 200},
            {"requested_alias": "missing"},
        ):
            kwargs = dict(
                run_id=run.id,
                handoff_step_id="handoff",
                project_id=100,
                workspace_id=100,
                target_id="prod",
                target_epoch=1,
                requested_alias="production",
                lock_id="lock",
                snapshot_bytes=self.snapshot(),
                snapshot_digest=self.snapshot_digest(),
                now=self.now,
            )
            kwargs.update(values)
            with (
                self.subTest(values=values),
                self.assertRaisesRegex(IntegrityError, "Run target scope mismatch"),
                self.factory.begin() as db,
            ):
                repository.capture_run_target(db, **kwargs)

    def prepare_operation(self):
        run = self.make_run()
        with self.factory.begin() as db:
            self.create(db)
            repository.acquire_lock(
                db,
                lock_id="lock",
                target_id="prod",
                run_id=run.id,
                project_id=100,
                workspace_id=100,
                now=self.now,
            )
            repository.capture_run_target(
                db,
                run_id=run.id,
                handoff_step_id="handoff",
                project_id=100,
                workspace_id=100,
                target_id="prod",
                target_epoch=1,
                requested_alias="production",
                lock_id="lock",
                snapshot_bytes=self.snapshot(),
                snapshot_digest=self.snapshot_digest(),
                now=self.now,
            )
            db.add(
                AnalysisReport(
                    id=1,
                    project_id=100,
                    workspace_id=100,
                    risk_score=1,
                    severity="low",
                    recommendation="go",
                    top_risk="",
                    parse_summary="",
                    narrative_opening="",
                    narrative_explanation="",
                )
            )
            db.flush()
            db.add(
                InfraAutomationDecision(
                    id="approval",
                    run_id=run.id,
                    step_id="decision",
                    project_id=100,
                    workspace_id=100,
                    requested_by="human-a",
                    report_id=1,
                    generation=1,
                    version=2,
                    status="approved",
                    binding_bytes=b"{}",
                    binding_digest=D,
                    report_bytes=b"{}",
                    report_digest=D,
                    decision_kind="acknowledgement",
                    reviewer_id="human-a",
                    reviewer_authentication_version=1,
                    reviewer_authorization_version=1,
                    reason="synthetic",
                    created_at=self.now,
                    deadline_at=self.now + timedelta(minutes=5),
                    decided_at=self.now,
                )
            )
            db.flush()
            db.add(
                InfraAutomationHandoff(
                    id="operation",
                    run_id=run.id,
                    step_id="handoff",
                    approval_id="approval",
                    project_id=100,
                    workspace_id=100,
                    target_id="prod",
                    receiver_id="receiver",
                    receiver_principal_id="receiver",
                    prepared_by="human-a",
                    key_digest=D,
                    request_digest=D,
                    decision_binding_bytes=b"{}",
                    decision_binding_digest=D,
                    receiver_binding_bytes=b"{}",
                    receiver_binding_digest=D,
                    payload_bytes=b"{}",
                    payload_digest=D,
                    target_snapshot_bytes=self.snapshot(),
                    target_snapshot_digest=self.snapshot_digest(),
                    target_epoch=1,
                    authorization_epoch=1,
                    restore_epoch=1,
                    deadline_at=self.now + timedelta(minutes=5),
                    created_at=self.now,
                    last_observed_at=self.now,
                    version=1,
                    state="prepared",
                    broken=False,
                )
            )
            db.flush()
            db.add(
                InfraAutomationOutbox(
                    operation_id="operation",
                    version=1,
                    state="pending",
                    attempted_at=None,
                    updated_at=self.now,
                )
            )
            db.add(
                InfraAutomationGrant(
                    id="grant",
                    operation_id="operation",
                    verifier_digest=D,
                    key_ref="synthetic-key-reference",
                    receiver_id="receiver",
                    deadline_at=self.now + timedelta(minutes=5),
                    created_at=self.now,
                    status="available",
                    version=1,
                    consumed_at=None,
                    receipt_bytes=None,
                    receipt_digest=None,
                )
            )

    def test_one_approval_cannot_mint_another_operation_for_a_different_step(self):
        self.prepare_operation()
        with self.factory.begin() as db:
            original = db.get(InfraAutomationHandoff, "operation")
            repository.capture_run_target(
                db,
                run_id=original.run_id,
                handoff_step_id="another-handoff",
                project_id=100,
                workspace_id=100,
                target_id="prod",
                target_epoch=1,
                requested_alias="production",
                lock_id="lock",
                snapshot_bytes=self.snapshot(),
                snapshot_digest=self.snapshot_digest(),
                now=self.now,
            )
            duplicate = {
                column.name: getattr(original, column.name)
                for column in InfraAutomationHandoff.__table__.columns
            }
            duplicate.update(
                id="second-operation",
                step_id="another-handoff",
                key_digest="sha256:" + "b" * 64,
            )
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            db.add(InfraAutomationHandoff(**duplicate))
            db.flush()

    def test_later_approval_generation_cannot_replace_same_run_handoff(self):
        self.prepare_operation()
        with self.factory.begin() as db:
            decision = db.query(InfraAutomationDecision).filter_by(id="approval").one()
            next_decision = {
                column.name: getattr(decision, column.name)
                for column in InfraAutomationDecision.__table__.columns
                if column.name != "sequence"
            }
            next_decision.update(id="later-approval", generation=2)
            db.add(InfraAutomationDecision(**next_decision))
            original = db.get(InfraAutomationHandoff, "operation")
            replacement = {
                column.name: getattr(original, column.name)
                for column in InfraAutomationHandoff.__table__.columns
            }
            replacement.update(
                id="replacement-operation",
                approval_id="later-approval",
                key_digest="sha256:" + "b" * 64,
            )
        with self.assertRaises(IntegrityError), self.factory.begin() as db:
            db.add(InfraAutomationHandoff(**replacement))
            db.flush()

    def test_operation_intent_grant_and_outbox_identity_retained(self):
        self.prepare_operation()
        for sql in (
            "UPDATE infra_automation_handoffs SET payload_bytes=X'61', version=2",
            "UPDATE infra_automation_handoffs SET project_id=200, version=2",
            "UPDATE infra_automation_handoffs SET state='succeeded', version=2",
            "DELETE FROM infra_automation_handoffs",
            "INSERT OR REPLACE INTO infra_automation_handoffs SELECT * FROM infra_automation_handoffs",
            "UPDATE infra_automation_grants SET verifier_digest='changed', version=2",
            "DELETE FROM infra_automation_grants",
            "INSERT OR REPLACE INTO infra_automation_grants SELECT * FROM infra_automation_grants",
            "DELETE FROM infra_automation_outbox",
            "INSERT OR REPLACE INTO infra_automation_outbox SELECT * FROM infra_automation_outbox",
        ):
            with (
                self.subTest(sql=sql),
                self.assertRaises(IntegrityError),
                self.factory.begin() as db,
            ):
                db.execute(text(sql))

    def test_one_use_grant_and_unknown_outbox_never_reissued_or_resent(self):
        self.prepare_operation()
        with self.factory.begin() as db:
            db.execute(
                text(
                    "UPDATE infra_automation_grants SET status='consumed', version=2, consumed_at=:now, receipt_bytes=:receipt, receipt_digest=:digest"
                ),
                dict(now=self.now, receipt=b'{"receipt":1}', digest=D),
            )
            db.execute(
                text(
                    "UPDATE infra_automation_outbox SET state='sending', version=2, attempted_at=:now"
                ),
                dict(now=self.now),
            )
            db.execute(
                text(
                    "UPDATE infra_automation_outbox SET state='delivery_unknown', version=3"
                )
            )
        for sql in (
            "UPDATE infra_automation_grants SET status='available', version=3, consumed_at=NULL, receipt_bytes=NULL, receipt_digest=NULL",
            "UPDATE infra_automation_grants SET receipt_bytes=X'61', version=3",
            "UPDATE infra_automation_outbox SET state='sending', version=4",
            "UPDATE infra_automation_outbox SET state='delivered', version=3",
        ):
            with (
                self.subTest(sql=sql),
                self.assertRaises(IntegrityError),
                self.factory.begin() as db,
            ):
                db.execute(text(sql))

    def test_empty_migration_roundtrip_and_retained_authority_downgrade_refusal(self):
        migration = import_module("migrations.versions.035_add_infra_handoffs")
        with self.engine.begin() as connection:
            with patch.object(
                migration, "op", Operations(MigrationContext.configure(connection))
            ):
                migration.downgrade()
                self.assertFalse(
                    set(migration.TABLES) & set(inspect(connection).get_table_names())
                )
                migration.upgrade()
                self.assertTrue(
                    database._infra_automation_schema_complete(
                        connection,
                        set(inspect(connection).get_table_names()),
                        "035_add_infra_handoffs",
                    )
                )
        with self.factory.begin() as db:
            self.create(db)
        with self.engine.begin() as connection:
            with patch.object(
                migration, "op", Operations(MigrationContext.configure(connection))
            ):
                with self.assertRaisesRegex(RuntimeError, "retained target authority"):
                    migration.downgrade()
                self.assertTrue(
                    database._infra_automation_schema_complete(
                        connection,
                        set(inspect(connection).get_table_names()),
                        "035_add_infra_handoffs",
                    )
                )

    def test_startup_rejects_missing_guards_and_held_unique_index(self):
        tables = set(inspect(self.engine).get_table_names())
        with self.engine.begin() as connection:
            self.assertTrue(
                database._infra_automation_schema_complete(
                    connection, tables, "035_add_infra_handoffs"
                )
            )
            connection.exec_driver_sql("DROP INDEX uq_infra_target_held")
            with self.assertRaisesRegex(RuntimeError, "partial infra automation"):
                database._infra_automation_schema_complete(
                    connection, tables, "035_add_infra_handoffs"
                )
        with self.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX uq_infra_target_held ON infra_automation_target_locks(target_id) WHERE status='held'"
            )
            connection.exec_driver_sql("DROP TRIGGER infra_grant_transition")
            with self.assertRaisesRegex(RuntimeError, "partial infra automation"):
                database._infra_automation_schema_complete(
                    connection, tables, "035_add_infra_handoffs"
                )


if __name__ == "__main__":
    unittest.main()
