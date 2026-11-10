"""Retention removes screened bytes without reviving evidence or losing identity."""

from __future__ import annotations

from datetime import timedelta
from importlib import import_module
from unittest.mock import patch
import unittest

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from infra_automation.lifecycle import LifecycleError
from models.repositories import infra_automation_reports as reports
from models.tables import InfraAutomationArtifactManifest, InfraAutomationRun
from services import project_service as auth
from tests.test_infra_automation import test_preflight_repository as fixtures


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PreflightRepositoryTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.row = self.fixture.create(
            [
                (
                    "main.tf",
                    b"# synthetic padding\n" * 200
                    + b'resource "aws_s3_bucket" "test" {}',
                )
            ]
        )
        with self.fixture.engine.begin() as db:
            migration = import_module("migrations.versions.040_add_manifest_retention")
            for name, body in {**migration.GUARDS, **migration.OVERRIDES}.items():
                db.exec_driver_sql(f"DROP TRIGGER IF EXISTS {name}")
                db.exec_driver_sql(f"CREATE TRIGGER {name} {body}")
        self.future = self.fixture.now + timedelta(days=8)
        with self.fixture.factory.begin() as db:
            db.execute(
                update(InfraAutomationRun)
                .where(InfraAutomationRun.id == self.row.run_id)
                .values(state="failed", version=InfraAutomationRun.version + 1)
            )
        self.request = self.request_for()

    def request_for(self):
        from infra_automation.retention import PurgeManifestRequest

        with self.fixture.factory() as db:
            run = db.scalar(
                select(InfraAutomationRun).where(
                    InfraAutomationRun.id == self.row.run_id
                )
            )
            return PurgeManifestRequest(
                manifest_id=self.row.id,
                expected_run_version=run.version,
                reason="Expired synthetic screened content",
            )

    def purge(self, request=None):
        from services import infra_automation_retention as retention

        with (
            self.fixture.credentials(),
            patch.object(retention, "_now", return_value=self.future),
        ):
            return retention.purge_manifest(request or self.request)

    def test_purge_preserves_identity_reclaims_bytes_and_replays_exactly(self):
        from models.tables import InfraAutomationRetentionTombstone

        with self.fixture.factory() as db:
            before = db.scalar(
                select(InfraAutomationRun).where(
                    InfraAutomationRun.id == self.row.run_id
                )
            ).retained_bytes
        result = self.purge()
        self.assertEqual(result, self.purge())
        with self.fixture.factory() as db:
            row = db.get(InfraAutomationArtifactManifest, self.row.id)
            tombstone = db.get(InfraAutomationRetentionTombstone, self.row.id)
            self.assertEqual(row.artifacts_bytes, b"[]")
            self.assertEqual(row.digest, self.row.digest)
            self.assertEqual(tombstone.original_size, len(self.row.artifacts_bytes))
            self.assertLess(
                db.scalar(
                    select(InfraAutomationRun).where(
                        InfraAutomationRun.id == row.run_id
                    )
                ).retained_bytes,
                before,
            )
            with self.assertRaises(LifecycleError) as caught:
                reports.manifest_files(row)
            self.assertEqual(caught.exception.status_code, 409)

    def test_nonterminal_stale_version_and_unexpired_content_deny(self):
        from services import infra_automation_retention as retention

        for state, when, version in (
            ("running", self.future, self.request.expected_run_version),
            ("failed", self.fixture.now, self.request.expected_run_version),
            ("failed", self.future, self.request.expected_run_version + 1),
        ):
            with self.subTest(state=state, when=when, version=version):
                with self.fixture.factory.begin() as db:
                    db.execute(
                        update(InfraAutomationRun)
                        .where(InfraAutomationRun.id == self.row.run_id)
                        .values(state=state, version=InfraAutomationRun.version + 1)
                    )
                request = self.request_for()
                if version != self.request.expected_run_version:
                    request = request.model_copy(
                        update={
                            "expected_run_version": request.expected_run_version + 1
                        }
                    )
                with (
                    self.fixture.credentials(),
                    patch.object(retention, "_now", return_value=when),
                    self.assertRaises(LifecycleError),
                ):
                    retention.purge_manifest(request)
        with self.fixture.factory() as db:
            self.assertEqual(
                db.get(InfraAutomationArtifactManifest, self.row.id).artifacts_bytes,
                self.row.artifacts_bytes,
            )

    def test_nonadmin_and_read_only_credentials_deny(self):
        self.fixture.member("read-only")
        with self.assertRaises(auth.TrustedAuthorizationError):
            self.purge()
        self.fixture.member("admin")
        from services import infra_automation_retention as retention

        with (
            self.fixture.credentials(mutation=False),
            self.assertRaises(auth.TrustedAuthorizationError),
        ):
            retention.purge_manifest(self.request)

    def test_failure_rolls_back_marker_tombstone_and_counter(self):
        from services import infra_automation_retention as retention
        from models.tables import InfraAutomationRetentionTombstone

        with (
            patch.object(
                retention.support,
                "append_audit",
                side_effect=RuntimeError("synthetic failure"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.purge()
        with self.fixture.factory() as db:
            self.assertIsNone(db.get(InfraAutomationRetentionTombstone, self.row.id))
            self.assertEqual(
                db.get(InfraAutomationArtifactManifest, self.row.id).artifacts_bytes,
                self.row.artifacts_bytes,
            )

    def test_tombstone_and_marker_are_irreversible(self):
        from sqlalchemy import text

        self.purge()
        for sql in (
            "DELETE FROM infra_automation_retention_tombstones",
            "UPDATE infra_automation_retention_tombstones SET reason='changed'",
            "UPDATE infra_automation_artifact_manifests SET artifacts_bytes=X'61'",
            "UPDATE infra_automation_artifact_manifests SET digest='changed'",
        ):
            with (
                self.subTest(sql=sql),
                self.assertRaises(IntegrityError),
                self.fixture.engine.begin() as db,
            ):
                db.execute(text(sql))

    def test_cleanup_does_not_require_admission_capacity_and_long_reason_is_counted(
        self,
    ):
        from infra_automation import storage

        request = self.request.model_copy(update={"reason": "界" * 256})
        with self.fixture.factory() as db:
            before = db.scalar(
                select(InfraAutomationRun).where(
                    InfraAutomationRun.id == self.row.run_id
                )
            ).retained_bytes
        with patch.object(
            storage,
            "ensure_capacity",
            side_effect=AssertionError("new admission must not gate cleanup"),
        ):
            self.purge(request)
        with self.fixture.factory() as db:
            after = db.scalar(
                select(InfraAutomationRun).where(
                    InfraAutomationRun.id == self.row.run_id
                )
            ).retained_bytes
        self.assertLess(
            before - after,
            len(self.row.artifacts_bytes) - 3 * len(request.reason.encode("utf-8")),
        )

    def test_concurrent_exact_retries_commit_one_receipt_and_one_audit(self):
        from concurrent.futures import ThreadPoolExecutor
        from models.tables import (
            InfraAutomationAudit,
            InfraAutomationRetentionTombstone,
        )
        from sqlalchemy import func

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.purge(), range(2)))
        self.assertEqual(results[0], results[1])
        with self.fixture.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(func.count()).select_from(InfraAutomationRetentionTombstone)
                ),
                1,
            )
            self.assertEqual(
                db.scalar(
                    select(func.count())
                    .select_from(InfraAutomationAudit)
                    .where(
                        InfraAutomationAudit.event_type
                        == "automation_manifest_content_removed"
                    )
                ),
                1,
            )

    def test_backward_clock_and_corrupt_counter_deny_without_tombstone(self):
        from services import infra_automation_retention as retention
        from models.tables import InfraAutomationRetentionTombstone

        with (
            self.fixture.credentials(),
            patch.object(
                retention, "_now", return_value=self.fixture.now - timedelta(seconds=1)
            ),
            self.assertRaises(LifecycleError),
        ):
            retention.purge_manifest(self.request)
        with self.assertRaises(IntegrityError), self.fixture.factory.begin() as db:
            db.execute(
                update(InfraAutomationRun)
                .where(InfraAutomationRun.id == self.row.run_id)
                .values(
                    retained_bytes=len(self.fixture.snapshot.canonical_bytes),
                    version=InfraAutomationRun.version + 1,
                )
            )
        with self.fixture.factory() as db:
            self.assertIsNone(db.get(InfraAutomationRetentionTombstone, self.row.id))

    def test_real_pending_and_approved_decisions_protect_terminal_content(self):
        from tests.test_infra_automation import test_decision_service as decisions
        from infra_automation.retention import PurgeManifestRequest
        from services import infra_automation_retention as retention

        for status in ("pending", "approved"):
            with self.subTest(status=status):
                fixture = decisions.DecisionServiceTests()
                self.addCleanup(fixture.doCleanups)
                fixture.setUp()
                if status == "approved":
                    fixture.approve()
                else:
                    fixture.pending()
                with fixture.factory.begin() as db:
                    db.execute(
                        update(InfraAutomationRun)
                        .where(InfraAutomationRun.id == fixture.run.id)
                        .values(state="failed", version=InfraAutomationRun.version + 1)
                    )
                    run = db.scalar(
                        select(InfraAutomationRun).where(
                            InfraAutomationRun.id == fixture.run.id
                        )
                    )
                    request = PurgeManifestRequest(
                        manifest_id="manifest",
                        expected_run_version=run.version,
                        reason="Expired synthetic content",
                    )
                with (
                    fixture.credentials(),
                    patch.object(
                        retention, "_now", return_value=fixture.now + timedelta(days=8)
                    ),
                    self.assertRaises(LifecycleError) as caught,
                ):
                    retention.purge_manifest(request)
                self.assertEqual(caught.exception.status_code, 409)
                fixture.doCleanups()

    def test_held_and_broken_locks_protect_terminal_content(self):
        from tests.test_infra_automation import test_handoff_service as handoffs
        from infra_automation.retention import PurgeManifestRequest
        from models.tables import InfraAutomationTargetLock
        from services import infra_automation_retention as retention

        fixture = handoffs.HandoffServiceTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        for status in ("held", "broken"):
            with self.subTest(status=status), fixture.factory.begin() as db:
                db.execute(
                    update(InfraAutomationRun)
                    .where(InfraAutomationRun.id == fixture.run.id)
                    .values(state="failed", version=InfraAutomationRun.version + 1)
                )
                run = db.scalar(
                    select(InfraAutomationRun).where(
                        InfraAutomationRun.id == fixture.run.id
                    )
                )
                # Existing real fixture has an approval and lock. The protection
                # query must retain both regardless of the terminal run label.
                locks = list(
                    db.scalars(
                        select(InfraAutomationTargetLock).where(
                            InfraAutomationTargetLock.run_id == run.id
                        )
                    )
                )
                self.assertTrue(locks)
                for lock in locks:
                    if status != lock.status:
                        lock.status = status
                        lock.version += 1
                request = PurgeManifestRequest(
                    manifest_id="manifest",
                    expected_run_version=run.version,
                    reason="Unknown synthetic external work",
                )
            with (
                fixture.credentials(),
                patch.object(
                    retention, "_now", return_value=fixture.now + timedelta(days=8)
                ),
                self.assertRaises(LifecycleError) as caught,
            ):
                retention.purge_manifest(request)
            self.assertEqual(caught.exception.status_code, 409)

    def test_external_possible_terminal_run_retains_content_without_operation_projection(
        self,
    ):
        with self.fixture.factory.begin() as db:
            db.execute(
                update(InfraAutomationRun)
                .where(InfraAutomationRun.id == self.row.run_id)
                .values(external_possible=True, version=InfraAutomationRun.version + 1)
            )
        with self.assertRaises(LifecycleError) as caught:
            self.purge()
        self.assertEqual(caught.exception.status_code, 409)
