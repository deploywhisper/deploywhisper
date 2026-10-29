"""Immutable decision values and durable compare-and-swap regressions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import unittest

from pydantic import ValidationError
from infra_automation.decisions import (
    DecisionBinding,
    binding_digest,
    freeze_report_snapshot,
    effective_deadline,
)

from importlib import import_module
from unittest.mock import patch
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError
from infra_automation.state import AuditActor
from infra_automation.lifecycle import LifecycleError
from models.repositories import infra_automation_decisions as repository
from models.repositories import infra_automation_runs as run_repository
from models.tables import AnalysisReport, InfraAutomationDecision
from alembic.operations import Operations
from alembic.migration import MigrationContext
from tests.test_infra_automation.lifecycle_support import LifecycleCase
from tests.test_infra_automation import test_workflow_snapshots as snapshot_tests


NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)
D = "sha256:" + "a" * 64


def binding_payload():
    return dict(
        version=1,
        authorization_kind="advisory_request",
        workflow_id="wf",
        revision_id="revision",
        workflow_revision_digest=D,
        input_digest=D,
        provenance=dict(
            version=1,
            authorization_kind="advisory_request",
            source=dict(kind="uploaded"),
        ),
        project_id=100,
        workspace_id=100,
        environment="test",
        canonical_target="target",
        receiver_id="receiver",
        pipeline_repository_id="pipeline",
        pipeline_workflow_id="workflow",
        pipeline_workflow_revision="a" * 40,
        report_id=1,
        report_schema_version="v2",
        report_bytes_digest=D,
        policy_version=1,
        policy_result="passed",
        policy_digest=D,
        unit_waves_digest=D,
        screened_artifact_digests=[D],
        redaction_version=1,
        payload_digest=D,
        evidence_deadline="2026-10-29T01:00:00Z",
        approval_deadline="2026-10-29T04:00:00Z",
        authorization_epoch=1,
        restore_epoch=1,
    )


class DecisionValuesTests(unittest.TestCase):
    def test_snapshot_preserves_fractional_fields_and_exact_bytes(self):
        raw, digest = freeze_report_snapshot(
            {"report_schema_version": "v2", "confidence": 0.123456789, "text": "é"}
        )
        self.assertEqual(json.loads(raw)["confidence"], 0.123456789)
        self.assertIn("é".encode(), raw)
        self.assertTrue(digest.startswith("sha256:"))
        with self.assertRaises(ValueError):
            freeze_report_snapshot(
                {"report_schema_version": "v2", "text": "a" * 8388608}
            )

    def test_frozen_tuple_every_field_is_bound(self):
        value = DecisionBinding.model_validate_json(json.dumps(binding_payload()))
        original = binding_digest(value)
        for key, item in binding_payload().items():
            if key in (
                "version",
                "report_schema_version",
                "policy_result",
                "authorization_kind",
                "provenance",
            ):
                continue
            changed = binding_payload()
            if key.endswith("deadline"):
                changed[key] = "2026-10-29T00:30:00Z"
            elif isinstance(item, int):
                changed[key] = item + 1
            elif isinstance(item, list):
                changed[key] = ["sha256:" + "b" * 64]
            elif item.startswith("sha256:"):
                changed[key] = "sha256:" + "b" * 64
            elif key == "pipeline_workflow_revision":
                changed[key] = "b" * 40
            else:
                changed[key] = item + "x"
            self.assertNotEqual(
                binding_digest(
                    DecisionBinding.model_validate_json(json.dumps(changed))
                ),
                original,
                key,
            )
        with self.assertRaises(ValidationError):
            value.policy_version = 2
        self.assertIsInstance(value.screened_artifact_digests, tuple)
        self.assertEqual(effective_deadline(value), NOW + timedelta(hours=1))


class DurableDecisionTests(LifecycleCase):
    enable = snapshot_tests.WorkflowSnapshotTests.enable
    export = snapshot_tests.WorkflowSnapshotTests.export
    publish_fixture = snapshot_tests.WorkflowSnapshotTests.publish_fixture

    def setUp(self):
        super().setUp()
        self.enable()
        snapshot = self.export(self.publish_fixture())
        with self.factory.begin() as db:
            self.run = run_repository.create_run(
                db,
                snapshot=snapshot,
                request_digest=D,
                key_digest=D,
                requested_by="human-a",
                deadline_at=self.now + timedelta(minutes=10),
                audit_actor=AuditActor("human-a", "human", "admin"),
                reason="synthetic",
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
        migration = import_module("migrations.versions.034_add_infra_decisions")
        with self.engine.begin() as db:
            InfraAutomationDecision.__table__.drop(db)
            with patch.object(
                migration, "op", Operations(MigrationContext.configure(db))
            ):
                migration.upgrade()
        self.raw, digest = freeze_report_snapshot(
            {"report_schema_version": "v2", "confidence": 0.4}
        )
        payload = binding_payload()
        payload["evidence_deadline"] = (self.now + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        payload["approval_deadline"] = (self.now + timedelta(hours=4)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        payload["report_bytes_digest"] = digest
        self.binding = DecisionBinding.model_validate_json(json.dumps(payload))
        self.enterContext(patch("services.project_service._require_operation"))

    def create(self):
        with self.factory.begin() as db:
            return repository.create_request(
                db,
                self.binding,
                run_id=self.run.id,
                step_id="decision",
                requested_by="human-a",
                report_bytes=self.raw,
                now=self.now,
            )

    def test_expired_initial_request_records_only_terminal_denial(self):
        now = self.now + timedelta(hours=4)
        with self.factory.begin() as db:
            denied = repository.create_denied_request(
                db,
                self.binding,
                run_id=self.run.id,
                step_id="decision",
                requested_by="human-a",
                report_bytes=self.raw,
                reason_codes=("stale_evidence", "approval_expired"),
                now=now,
            )
            self.assertEqual(denied.status, "expired")
            self.assertIsNone(denied.reviewer_id)
            self.assertEqual(
                json.loads(denied.reason), ["stale_evidence", "approval_expired"]
            )
        with self.factory() as db:
            self.assertEqual(repository.get_request(db, denied.id).status, "expired")
        with self.factory.begin() as db, self.assertRaises(LifecycleError):
            repository.decide(
                db,
                denied.id,
                expected_version=denied.version,
                binding_digest=denied.binding_digest,
                reviewer_id="reviewer",
                reviewer_authentication_version=1,
                reviewer_authorization_version=1,
                decision_kind="independent-approval",
                outcome="approve",
                reason="Cannot revive denied evidence",
                now=now,
            )

    def test_acknowledgement_retains_honest_decision_kind(self):
        row = self.create()
        with self.factory.begin() as db:
            decided = repository.decide(
                db,
                row.id,
                expected_version=1,
                binding_digest=row.binding_digest,
                reviewer_id="reviewer",
                reviewer_authentication_version=1,
                reviewer_authorization_version=1,
                decision_kind="acknowledgement",
                outcome="approve",
                reason="Acknowledged by the sole operator",
                now=self.now,
            )
            self.assertEqual(decided.decision_kind, "acknowledgement")
        with self.factory() as db:
            restored = repository.get_request(db, row.id)
            self.assertEqual(restored.decision_kind, "acknowledgement")
            self.assertEqual(restored.status, "approved")

    def test_restart_remains_pending_and_cas_rejects_replay(self):
        row = self.create()
        with self.factory() as db:
            restored = repository.get_request(db, row.id)
            self.assertEqual(restored.status, "pending")
            self.assertEqual(restored.report_bytes, self.raw)
        with self.factory.begin() as db:
            decided = repository.decide(
                db,
                row.id,
                expected_version=1,
                binding_digest=row.binding_digest,
                decision_kind="independent-approval",
                reviewer_authentication_version=1,
                reviewer_authorization_version=1,
                reviewer_id="reviewer",
                outcome="approve",
                reason="reviewed",
                now=self.now,
            )
            self.assertEqual((decided.status, decided.version), ("approved", 2))
        with self.factory.begin() as db, self.assertRaises(LifecycleError):
            repository.decide(
                db,
                row.id,
                expected_version=1,
                binding_digest=row.binding_digest,
                decision_kind="independent-approval",
                reviewer_authentication_version=1,
                reviewer_authorization_version=1,
                reviewer_id="reviewer",
                outcome="approve",
                reason="replayed",
                now=self.now,
            )

    def test_exact_expiry_and_new_generation(self):
        row = self.create()
        with self.factory.begin() as db, self.assertRaises(LifecycleError):
            repository.decide(
                db,
                row.id,
                expected_version=1,
                binding_digest=row.binding_digest,
                decision_kind="independent-approval",
                reviewer_authentication_version=1,
                reviewer_authorization_version=1,
                reviewer_id="reviewer",
                outcome="approve",
                reason="too late",
                now=self.now + timedelta(hours=1),
            )
        with self.factory.begin() as db:
            repository.invalidate(
                db,
                row.id,
                expected_version=1,
                status="superseded",
                reason="new evidence",
                now=self.now,
            )
        second = self.create()
        self.assertEqual(second.generation, 2)
        self.assertNotEqual(row.id, second.id)

    def test_immutable_sql_and_guard_validation(self):
        self.create()
        for statement in (
            "UPDATE infra_automation_decisions SET binding_bytes=x'01'",
            "DELETE FROM infra_automation_decisions",
            "INSERT OR REPLACE INTO infra_automation_decisions SELECT * FROM infra_automation_decisions",
            "UPDATE infra_automation_decisions SET status='approved',version=99",
        ):
            with (
                self.subTest(statement=statement),
                self.factory.begin() as db,
                self.assertRaises(IntegrityError),
            ):
                db.execute(text(statement))
        from models.database import _infra_automation_schema_complete

        with self.engine.begin() as db:
            tables = set(inspect(db).get_table_names())
            self.assertTrue(
                _infra_automation_schema_complete(db, tables, "034_add_infra_decisions")
            )
            db.exec_driver_sql("DROP TRIGGER infra_decision_immutable")
            with self.assertRaises(RuntimeError):
                _infra_automation_schema_complete(db, tables, "034_add_infra_decisions")

    def test_two_sessions_observe_same_generation_only_one_can_decide(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        row = self.create()
        barrier = Barrier(2)

        def contender(reviewer):
            with self.factory() as db:
                seen = repository.get_request(db, row.id)
                expected_version = seen.version
                db.rollback()
                barrier.wait(timeout=5)
                # Match the operation owner SQLite write reservation: independent
                # connections compete on the same immutable generation/version.
                db.execute(text("BEGIN IMMEDIATE"))
                try:
                    result = repository.decide(
                        db,
                        row.id,
                        expected_version=expected_version,
                        binding_digest=row.binding_digest,
                        decision_kind="independent-approval",
                        reviewer_authentication_version=1,
                        reviewer_authorization_version=1,
                        reviewer_id=reviewer,
                        outcome="approve",
                        reason="racing review",
                        now=self.now,
                    )
                    db.commit()
                    return result.status
                except LifecycleError:
                    db.rollback()
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(contender, ("reviewer-a", "reviewer-b")))
        self.assertCountEqual(results, ["approved", "conflict"])
        with self.factory() as db:
            current = repository.get_request(db, row.id)
            self.assertEqual(current.version, 2)

    def test_database_denies_another_active_generation(self):
        self.create()
        from sqlalchemy import insert, literal, select

        table = InfraAutomationDecision.__table__
        names = [column.name for column in table.columns if column.name != "sequence"]
        values = [
            literal("another-request")
            if name == "id"
            else table.c.generation + 1
            if name == "generation"
            else table.c[name]
            for name in names
        ]
        with self.factory.begin() as db, self.assertRaises(IntegrityError):
            db.execute(insert(table).from_select(names, select(*values)))
        with self.engine.connect() as db:
            indexes = {
                entry[1]: entry[2]
                for entry in db.exec_driver_sql(
                    "PRAGMA index_list(infra_automation_decisions)"
                )
            }
            self.assertEqual(indexes["uq_infra_decision_active"], 1)

    def test_replace_cannot_reuse_retained_sequence_with_fresh_public_identity(self):
        from sqlalchemy import insert, literal, select

        row = self.create()
        table = InfraAutomationDecision.__table__
        names = [column.name for column in table.columns]
        replacements = {
            "id": literal("replacement-request"),
            "step_id": literal("different-decision"),
            "generation": table.c.generation + 1,
        }
        values = [replacements.get(name, table.c[name]) for name in names]
        with self.factory.begin() as db, self.assertRaises(IntegrityError):
            self.assertEqual(db.execute(text("PRAGMA recursive_triggers")).scalar(), 0)
            db.execute(
                insert(table)
                .prefix_with("OR REPLACE")
                .from_select(names, select(*values).where(table.c.id == row.id))
            )
        with self.factory() as db:
            self.assertEqual(repository.get_request(db, row.id).sequence, row.sequence)
            self.assertIsNone(repository.get_request(db, "replacement-request"))

    def test_terminal_requires_reviewer_reason_and_live_deadline(self):
        self.create()
        for values in (
            "status='approved', version=2",
            "status='approved', version=2,reviewer_id='r',reason='ok',decided_at='2099-01-01'",
            "status='rejected', version=2,reviewer_id='',reason='ok',decided_at='2026-01-01'",
            "status='expired', version=2,reason='',decided_at='2026-01-01'",
        ):
            with (
                self.subTest(values=values),
                self.factory.begin() as db,
                self.assertRaises(IntegrityError),
            ):
                db.execute(text("UPDATE infra_automation_decisions SET " + values))
