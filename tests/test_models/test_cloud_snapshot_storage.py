"""Project-scoped immutable screened cloud snapshot persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import (
    create_engine,
    create_mock_engine,
    delete,
    event,
    insert,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from cloud.base import (
    ResourceIdentity,
    ResourceRead,
    SnapshotFact,
    build_snapshot,
    canonical_snapshot_json,
)
from cloud.redaction import redact_snapshot
from models.database import Base
from models.cloud_snapshots import CloudContextSnapshot
from cloud.schema import initialize_snapshot_schema
from models.repositories.cloud_snapshots import (
    CloudSnapshotIntegrityError,
    get_snapshot,
    purge_expired_snapshots,
    put_snapshot,
    source_ref,
)
from models.tables import (
    AnalysisReport,
    AppSetting,
    EvidenceItem,
    Finding,
    Project,
    ProjectWorkspace,
)


class CloudSnapshotStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")

        @event.listens_for(self.engine, "connect")
        def enable_fk(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(
            self.engine,
            tables=[
                item.__table__
                for item in (
                    Project,
                    ProjectWorkspace,
                    AnalysisReport,
                    Finding,
                    EvidenceItem,
                    AppSetting,
                )
            ],
        )
        self.session = Session(self.engine)
        self.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        initialize_snapshot_schema(self.session)
        self.project = Project(project_key="cloud-test", display_name="Cloud test")
        self.session.add(self.project)
        self.session.flush()
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.session.rollback()
        self.session.close()
        self.engine.dispose()

    def snapshot(self, *, old=False, secret=False, scope="account-display"):
        end = self.now - timedelta(days=8) if old else self.now - timedelta(seconds=1)
        resources = ()
        if secret:
            resources = (
                ResourceRead(
                    identity=ResourceIdentity(
                        address="aws_instance.test", resource_type="aws_instance"
                    ),
                    status="read",
                    facts=(
                        SnapshotFact(
                            name="password", value="SYNTHETIC-cloud-storage-canary"
                        ),
                    ),
                ),
            )
        return build_snapshot(
            provider="reference",
            project_id=self.project.id,
            scope_id="opaque-scope",
            scope=scope,
            regions=("test",),
            read_window_start=end - timedelta(seconds=1),
            read_window_end=end,
            resources=resources,
        )

    def put(self, snapshot):
        return put_snapshot(self.session, snapshot, mask_accounts=True)

    def test_supported_profile_requires_transaction_and_foreign_keys(self):
        with Session(self.engine) as missing:
            with self.assertRaises(CloudSnapshotIntegrityError):
                put_snapshot(missing, self.snapshot(), mask_accounts=True)
        disabled_engine = create_engine("sqlite://")
        try:
            with Session(disabled_engine) as disabled, disabled.begin():
                with self.assertRaises(CloudSnapshotIntegrityError):
                    put_snapshot(disabled, self.snapshot(), mask_accounts=True)
        finally:
            disabled_engine.dispose()
        other_engine = create_mock_engine("postgresql://", lambda *a, **k: None)
        with Session(other_engine) as other, other.begin():
            with self.assertRaises(CloudSnapshotIntegrityError):
                put_snapshot(other, self.snapshot(), mask_accounts=True)

    def test_initial_raw_tombstone_insert_is_forbidden(self):
        record = self.put(self.snapshot(old=True))
        values = {
            column.name: getattr(record, column.name)
            for column in CloudContextSnapshot.__table__.columns
        }
        values.update(digest="c" * 64, payload_json=None, purged_at=self.now)
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.execute(insert(CloudContextSnapshot).values(**values))

    def test_roundtrip_dedup_does_not_refresh_expiry_or_commit(self):
        snapshot = self.snapshot()
        first = self.put(snapshot)
        expiry = first.expires_at.replace(tzinfo=None)
        again = self.put(snapshot)
        self.assertIs(first, again)
        self.assertEqual(again.expires_at.replace(tzinfo=None), expiry)
        self.assertTrue(self.session.in_transaction())
        self.assertEqual(
            get_snapshot(
                self.session, project_id=self.project.id, digest=snapshot.digest
            ),
            snapshot,
        )

    def test_direct_repository_rejects_unscreened_sensitive_material(self):
        with self.assertRaises(CloudSnapshotIntegrityError) as failure:
            self.put(self.snapshot(secret=True))
        self.assertNotIn("SYNTHETIC", str(failure.exception))
        self.assertIsNone(failure.exception.__cause__)
        self.assertEqual(self.session.scalar(select(CloudContextSnapshot)), None)
        screened = redact_snapshot(self.snapshot(secret=True))
        record = self.put(screened)
        self.assertNotIn("SYNTHETIC", record.payload_json)

    def test_account_mask_policy_is_explicit_and_enforced(self):
        raw = self.snapshot(scope="123456789012")
        with self.assertRaises(CloudSnapshotIntegrityError):
            self.put(raw)
        record = put_snapshot(self.session, raw, mask_accounts=False)
        self.assertIn("123456789012", record.payload_json)
        masked = redact_snapshot(raw, mask_accounts=True)
        self.assertIn("MASKED_ACCOUNT", self.put(masked).payload_json)
        with self.assertRaises(CloudSnapshotIntegrityError):
            put_snapshot(self.session, masked, mask_accounts=1)

    def test_tampered_constructor_and_metadata_fail_closed(self):
        snapshot = self.snapshot()
        bad = snapshot.model_copy(update={"scope": "forged-secret-canary"})
        with self.assertRaises(CloudSnapshotIntegrityError) as failure:
            self.put(bad)
        self.assertNotIn("forged", str(failure.exception))
        self.put(snapshot)
        self.session.execute(text("DROP TRIGGER cloud_snapshots_immutable_update"))
        self.session.execute(
            text("UPDATE cloud_context_snapshots SET scope_id='tampered'")
        )
        self.session.expire_all()
        with self.assertRaises(CloudSnapshotIntegrityError):
            get_snapshot(
                self.session, project_id=self.project.id, digest=snapshot.digest
            )

    def test_expired_unreferenced_payload_cannot_be_read_even_with_backdated_clock(
        self,
    ):
        old = self.snapshot(old=True)
        self.put(old)
        self.assertIsNone(
            get_snapshot(self.session, project_id=self.project.id, digest=old.digest)
        )
        self.assertIsNone(
            get_snapshot(
                self.session,
                project_id=self.project.id,
                digest=old.digest,
                now=old.read_window_end,
            )
        )

    def test_purge_is_one_way_and_duplicate_cannot_resurrect(self):
        old = self.snapshot(old=True)
        self.put(old)
        self.assertEqual(
            purge_expired_snapshots(self.session, project_id=self.project.id), 1
        )
        record = self.put(old)
        self.assertIsNone(record.payload_json)
        self.assertIsNotNone(record.purged_at)
        self.assertIsNone(
            get_snapshot(self.session, project_id=self.project.id, digest=old.digest)
        )
        self.assertEqual(
            purge_expired_snapshots(self.session, project_id=self.project.id), 0
        )

    def test_future_clock_cannot_purge_unexpired_data(self):
        self.put(self.snapshot())
        self.assertEqual(
            purge_expired_snapshots(
                self.session,
                project_id=self.project.id,
                now=self.now + timedelta(days=90),
            ),
            0,
        )

    def test_retained_same_project_report_prevents_purge_after_ttl(self):
        old = self.snapshot(old=True)
        self.put(old)
        report = AnalysisReport(
            project_id=self.project.id,
            risk_score=10,
            severity="low",
            recommendation="safe",
            top_risk="test",
            parse_summary="test",
            narrative_opening="test",
            narrative_explanation="test",
        )
        self.session.add(report)
        self.session.flush()
        finding = Finding(
            finding_id="cloud-finding",
            analysis_id=report.id,
            title="test",
            description="test",
            severity="low",
            category="test",
        )
        self.session.add(finding)
        self.session.flush()
        evidence = EvidenceItem(
            evidence_id="cloud-evidence",
            analysis_id=report.id,
            finding_id=finding.finding_id,
            source_type="live_state",
            source_ref=source_ref(self.project.id, old.digest, "a" * 64),
            project_id=None,
            summary="test",
            severity_hint="low",
        )
        self.session.add(evidence)
        self.session.flush()
        self.assertEqual(
            purge_expired_snapshots(self.session, project_id=self.project.id), 0
        )
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.execute(
                    text(
                        "UPDATE cloud_context_snapshots SET payload_json=NULL,purged_at=CURRENT_TIMESTAMP"
                    )
                )
        self.assertEqual(
            get_snapshot(self.session, project_id=self.project.id, digest=old.digest),
            old,
        )
        self.session.execute(
            delete(AnalysisReport).where(AnalysisReport.id == report.id)
        )
        self.session.flush()
        self.assertEqual(
            purge_expired_snapshots(self.session, project_id=self.project.id), 1
        )

    def test_cross_project_reads_and_refs_do_not_grant_access(self):
        snapshot = self.snapshot()
        self.put(snapshot)
        self.assertIsNone(
            get_snapshot(
                self.session, project_id=self.project.id + 1, digest=snapshot.digest
            )
        )
        with self.assertRaises(CloudSnapshotIntegrityError):
            source_ref(self.project.id, snapshot.digest, "raw-secret-address")

    def test_database_blocks_mutation_resurrection_and_direct_delete_but_allows_parent_cascade(
        self,
    ):
        snapshot = self.snapshot(old=True)
        self.put(snapshot)
        for sql in [
            "UPDATE cloud_context_snapshots SET provider='other'",
            "UPDATE cloud_context_snapshots SET payload_json=NULL,purged_at=CURRENT_TIMESTAMP,provider='other'",
            "UPDATE cloud_context_snapshots SET purged_at=CURRENT_TIMESTAMP",
            "DELETE FROM cloud_context_snapshots",
        ]:
            with self.subTest(sql=sql), self.assertRaises(IntegrityError):
                with self.session.begin_nested():
                    self.session.execute(text(sql))
        purge_expired_snapshots(self.session, project_id=self.project.id)
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.execute(
                    text(
                        "UPDATE cloud_context_snapshots SET payload_json='{}',purged_at=NULL"
                    )
                )
        self.session.execute(delete(Project).where(Project.id == self.project.id))
        self.assertIsNone(self.session.scalar(select(CloudContextSnapshot)))

    def test_project_delete_clears_only_its_cloud_optin_before_id_reuse(self):
        old_id = self.project.id
        key = f"cloud_context:{old_id}"
        self.session.add_all(
            [
                AppSetting(key=key, value='{"enabled":true}'),
                AppSetting(key="cloud_context:999", value='{"enabled":true}'),
                AppSetting(key="unrelated", value="preserve"),
            ]
        )
        self.put(self.snapshot())
        self.session.execute(delete(Project).where(Project.id == old_id))
        self.session.expire_all()
        self.assertIsNone(self.session.get(AppSetting, key))
        self.assertIsNotNone(self.session.get(AppSetting, "cloud_context:999"))
        self.assertEqual(self.session.get(AppSetting, "unrelated").value, "preserve")
        replacement = Project(project_key="replacement", display_name="Replacement")
        self.session.add(replacement)
        self.session.flush()
        self.assertEqual(replacement.id, old_id)
        self.assertIsNone(
            self.session.get(AppSetting, f"cloud_context:{replacement.id}")
        )

    def _assert_replace_rejected(self, *, purged):
        for recursive in (0, 1):
            with self.subTest(recursive_triggers=recursive, purged=purged):
                self.session.connection().exec_driver_sql(
                    f"PRAGMA recursive_triggers={recursive}"
                )
                record = self.put(
                    self.snapshot(old=True, scope=f"replace-{purged}-{recursive}")
                )
                original = {
                    column.name: getattr(record, column.name)
                    for column in CloudContextSnapshot.__table__.columns
                }
                if purged:
                    purge_expired_snapshots(self.session, project_id=self.project.id)
                with self.assertRaises(IntegrityError):
                    with self.session.begin_nested():
                        self.session.execute(
                            insert(CloudContextSnapshot)
                            .prefix_with("OR REPLACE")
                            .values(**original)
                        )
                self.session.expire_all()
                stored = self.session.get(
                    CloudContextSnapshot, (record.project_id, record.digest)
                )
                self.assertEqual(stored.payload_json is None, purged)

    def test_replace_cannot_overwrite_live_observation_with_recursive_triggers_off_or_on(
        self,
    ):
        self._assert_replace_rejected(purged=False)

    def test_replace_cannot_resurrect_purged_payload_with_recursive_triggers_off_or_on(
        self,
    ):
        self._assert_replace_rejected(purged=True)

    def test_replace_cannot_evict_via_any_implicit_rowid_alias(self):
        record = self.put(self.snapshot(old=True, scope="original-rowid-observation"))
        original = {
            column.name: getattr(record, column.name)
            for column in CloudContextSnapshot.__table__.columns
        }
        self.session.connection().exec_driver_sql("PRAGMA recursive_triggers=0")
        for alias in ("rowid", "oid", "_rowid_"):
            with self.subTest(alias=alias):
                replacement = self.snapshot(old=True, scope=f"replacement-{alias}")
                values = dict(
                    original,
                    digest=replacement.digest,
                    payload_json=canonical_snapshot_json(replacement),
                )
                columns = (alias, *values)
                sql = (
                    "INSERT OR REPLACE INTO cloud_context_snapshots ("
                    + ",".join(columns)
                    + ") VALUES ("
                    + ",".join("?" for _ in columns)
                    + ")"
                )
                bound = (
                    1,
                    *(
                        value.isoformat(" ") if isinstance(value, datetime) else value
                        for value in values.values()
                    ),
                )
                with self.assertRaises(OperationalError):
                    with self.session.begin_nested():
                        self.session.connection().exec_driver_sql(sql, bound)
                self.session.expire_all()
                self.assertIsNotNone(
                    self.session.get(
                        CloudContextSnapshot, (record.project_id, record.digest)
                    )
                )

    def test_project_replace_clears_only_new_identity_optin_without_recursive_delete_triggers(
        self,
    ):
        key = f"cloud_context:{self.project.id}"
        self.session.add(AppSetting(key="unrelated", value="preserve"))
        self.session.flush()
        for recursive in (0, 1):
            with self.subTest(recursive_triggers=recursive):
                self.session.connection().exec_driver_sql(
                    f"PRAGMA recursive_triggers={recursive}"
                )
                self.session.add(AppSetting(key=key, value='{"enabled":true}'))
                snapshot = self.snapshot()
                self.put(snapshot)
                values = {
                    column.name: getattr(self.project, column.name)
                    for column in Project.__table__.columns
                }
                values.update(
                    project_key=f"replacement-{recursive}", display_name="Replacement"
                )
                self.session.execute(
                    insert(Project).prefix_with("OR REPLACE").values(**values)
                )
                self.session.expire_all()
                self.assertIsNone(self.session.get(AppSetting, key))
                self.assertIsNone(
                    self.session.get(
                        CloudContextSnapshot, (self.project.id, snapshot.digest)
                    )
                )
                self.assertEqual(
                    self.session.get(AppSetting, "unrelated").value, "preserve"
                )

    def test_ignored_insert_and_conflict_update_do_not_disable_existing_project(self):
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        key = f"cloud_context:{self.project.id}"
        self.session.add(AppSetting(key=key, value='{"enabled":true}'))
        self.session.flush()
        values = {
            column.name: getattr(self.project, column.name)
            for column in Project.__table__.columns
        }
        self.session.execute(insert(Project).prefix_with("OR IGNORE").values(**values))
        self.session.expire_all()
        self.assertEqual(self.session.get(AppSetting, key).value, '{"enabled":true}')
        self.session.execute(
            sqlite_insert(Project)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["id"], set_={"display_name": "Updated"}
            )
        )
        self.session.expire_all()
        self.assertEqual(self.session.get(AppSetting, key).value, '{"enabled":true}')

    def test_raw_future_receipt_cannot_bypass_database_expiry(self):
        self.put(self.snapshot())
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                self.session.execute(
                    text(
                        "UPDATE cloud_context_snapshots SET payload_json=NULL,purged_at='2099-01-01 00:00:00'"
                    )
                )
