"""Cloud orchestration uses server-owned authorization and no provider SDK."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, delete, event, select, inspect
from sqlalchemy.orm import sessionmaker

from cloud.base import (
    ResourceIdentity,
    ResourceRead,
    SnapshotFact,
    ReadStatus,
    build_snapshot,
)
from cloud.redaction import redact_snapshot
from models.database import Base
from models.cloud_snapshots import CloudContextSnapshot
from models.tables import (
    Project,
    ProjectWorkspace,
    AppSetting,
    RiskAssessment,
    AnalysisReport,
    Finding as StoredFinding,
    EvidenceItem as StoredEvidence,
)
from services.cloud_context_service import (
    CloudContextService,
    CloudContextError,
    snapshot_context,
)

NOW = datetime.now(timezone.utc) - timedelta(seconds=1)
IDENTITY = ResourceIdentity(
    address="example.instance", resource_type="example", physical_id="synthetic"
)


class TestPort:
    __test__ = False

    def __init__(self, factory):
        self.factory = factory
        self.allowed = {1, 2}
        self.checks = 0

    @contextmanager
    def session(self, project_id, operation):
        with self.factory() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield session
                self.check(session, project_id, operation)
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def check(self, session, project_id, operation):
        self.checks += 1
        if project_id not in self.allowed:
            raise PermissionError("synthetic authority denied")


class Stub:
    def __init__(self, mutate=None):
        self.mutate = mutate

    def collect(self, identities, *, project_id, scope_id):
        fields = dict(
            provider="reference",
            project_id=project_id,
            scope_id=scope_id,
            scope="123456789012",
            regions=("test",),
            read_window_start=NOW,
            read_window_end=NOW,
            resources=tuple(
                ResourceRead(
                    identity=i,
                    status=ReadStatus.READ,
                    facts=(SnapshotFact(name="state", value="running"),),
                )
                for i in identities
            ),
            issued_actions=("reference:DescribeResource",),
        )
        if self.mutate:
            self.mutate(fields)
        return build_snapshot(**fields)


class CloudServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + str(Path(self.temp.name) / "cloud.db")
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(
            self.engine,
            tables=[
                item.__table__
                for item in (
                    Project,
                    ProjectWorkspace,
                    AppSetting,
                    AnalysisReport,
                    StoredFinding,
                    StoredEvidence,
                    RiskAssessment,
                )
            ],
        )
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.factory() as db:
            db.add_all(
                [
                    Project(id=1, project_key="one", display_name="One"),
                    Project(id=2, project_key="two", display_name="Two"),
                ]
            )
            db.commit()
        self.port = TestPort(self.factory)
        self.connector = Stub()
        self.factory_mock = Mock(side_effect=lambda provider: self.connector)
        self.service = CloudContextService(
            unit_of_work=self.port,
            connector_factory=self.factory_mock,
            clock=lambda: NOW,
        )

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def configure(self):
        return self.service.configure(1, enabled=True, provider="reference")

    def test_no_port_denies_without_provider_construction(self):
        service = CloudContextService(connector_factory=self.factory_mock)
        with self.assertRaises(CloudContextError) as caught:
            service.collect(1, (IDENTITY,))
        self.assertEqual(caught.exception.code, "authorization_unavailable")
        self.factory_mock.assert_not_called()

    def test_boolean_permission_helper_is_not_an_authorization_port(self):
        for result in (False, True):
            self.port.check = lambda *args, value=result: value
            with (
                self.subTest(result=result),
                self.assertRaises(CloudContextError) as caught,
            ):
                self.configure()
            self.assertEqual(caught.exception.code, "authorization_unavailable")
            with self.factory() as db:
                self.assertIsNone(db.get(AppSetting, "cloud_context:1"))
        self.factory_mock.assert_not_called()

    def test_disabled_operations_do_not_initialize_or_create_cloud_schema(self):
        before = set(inspect(self.engine).get_table_names())
        with patch(
            "cloud.schema.initialize_snapshot_schema",
            side_effect=AssertionError("unexpected schema DDL"),
        ):
            self.assertEqual(self.service.collect(1, (IDENTITY,)).state, "disabled")
            self.service.configure(1, enabled=False)
            self.assertEqual(self.service.collect(1, (IDENTITY,)).state, "disabled")
            self.assertIsNone(self.service.get_snapshot(1, "f" * 64))
            self.assertEqual(self.service.purge_expired(1), 0)
        self.assertEqual(set(inspect(self.engine).get_table_names()), before)
        self.assertNotIn("cloud_context_snapshots", before)
        with self.factory() as db:
            self.assertIsNone(db.get(AppSetting, "cloud_context:schema"))
        self.factory_mock.assert_not_called()

    def test_enabled_config_initializes_owned_schema_idempotently(self):
        self.configure()
        tables = set(inspect(self.engine).get_table_names())
        self.assertIn("cloud_context_snapshots", tables)
        with self.factory() as db:
            version = db.get(AppSetting, "cloud_context:schema").value
        self.configure()
        self.assertEqual(set(inspect(self.engine).get_table_names()), tables)
        with self.factory() as db:
            self.assertEqual(db.get(AppSetting, "cloud_context:schema").value, version)
        self.factory_mock.assert_not_called()

    def test_schema_initialization_and_configuration_roll_back_on_revocation(self):
        from cloud.schema import initialize_snapshot_schema

        def revoke_after_initialize(session):
            initialize_snapshot_schema(session)
            self.port.allowed.remove(1)

        with patch("cloud.schema.initialize_snapshot_schema", revoke_after_initialize):
            with self.assertRaises(CloudContextError) as caught:
                self.configure()
        self.assertEqual(caught.exception.code, "authorization_denied")
        self.assertNotIn(
            "cloud_context_snapshots", inspect(self.engine).get_table_names()
        )
        with self.factory() as db:
            self.assertIsNone(db.get(AppSetting, "cloud_context:schema"))
            self.assertIsNone(db.get(AppSetting, "cloud_context:1"))

    def test_enabled_configuration_without_schema_fails_before_factory(self):
        with self.factory() as db:
            db.add(
                AppSetting(
                    key="cloud_context:1",
                    value=json.dumps(
                        {
                            "project_id": 1,
                            "enabled": True,
                            "provider": "reference",
                            "scope_id": "1" * 32,
                            "mask_accounts": True,
                        }
                    ),
                )
            )
            db.commit()
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (IDENTITY,))
        self.assertEqual(caught.exception.code, "snapshot_storage_unavailable")
        self.factory_mock.assert_not_called()
        self.assertNotIn(
            "cloud_context_snapshots", inspect(self.engine).get_table_names()
        )

    def test_partial_schema_fails_enabled_collection_before_factory(self):
        self.configure()
        with self.factory() as db:
            db.delete(db.get(AppSetting, "cloud_context:schema"))
            db.commit()
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (IDENTITY,))
        self.assertEqual(caught.exception.code, "snapshot_storage_unavailable")
        self.factory_mock.assert_not_called()

    def test_default_off_and_configure_do_not_instantiate(self):
        self.assertEqual(self.service.collect(1, (IDENTITY,)).state, "disabled")
        self.configure()
        self.factory_mock.assert_not_called()
        self.assertEqual(self.service.collect(2, (IDENTITY,)).state, "disabled")
        self.factory_mock.assert_not_called()

    def test_collect_persists_masked_snapshot_and_deduplicates(self):
        self.configure()
        one = self.service.collect(1, (IDENTITY,))
        two = self.service.collect(1, (IDENTITY,))
        self.assertEqual(one.snapshot.digest, two.snapshot.digest)
        self.assertNotIn("123456789012", one.snapshot.model_dump_json())
        self.assertEqual(
            self.service.get_snapshot(1, one.snapshot.digest), one.snapshot
        )
        self.assertIsNone(self.service.get_snapshot(2, one.snapshot.digest))

    def test_float_account_identifier_is_masked_in_persisted_payload(self):
        def float_account(fields):
            fields["resources"] = (
                ResourceRead(
                    identity=IDENTITY,
                    status=ReadStatus.READ,
                    facts=(SnapshotFact(name="account_id", value=123456789012.0),),
                ),
            )

        self.connector = Stub(float_account)
        self.configure()
        snapshot = self.service.collect(1, (IDENTITY,)).snapshot
        with self.factory() as db:
            row = db.get(CloudContextSnapshot, (1, snapshot.digest))
            self.assertNotIn("123456789012", row.payload_json)
            self.assertEqual(
                json.loads(row.payload_json)["resources"][0]["facts"][0]["value"],
                "[MASKED_ACCOUNT]",
            )
        self.assertEqual(self.service.get_snapshot(1, snapshot.digest), snapshot)

    def test_account_masking_is_explicit_configuration(self):
        self.service.configure(
            1, enabled=True, provider="reference", mask_accounts=False
        )
        snapshot = self.service.collect(1, (IDENTITY,)).snapshot
        self.assertEqual(snapshot.scope, "123456789012")
        self.assertEqual(self.service.get_snapshot(1, snapshot.digest), snapshot)

    def test_partial_outcome_preserves_exact_failure_cause(self):
        def unreadable(fields):
            fields["resources"] = (
                ResourceRead(
                    identity=IDENTITY,
                    status=ReadStatus.UNREADABLE,
                    cause="access_denied",
                    missing_permission="reference:DescribeResource",
                ),
            )

        self.connector = Stub(unreadable)
        self.configure()
        result = self.service.collect(1, (IDENTITY,))
        self.assertTrue(result.snapshot.partial)
        self.assertEqual(result.snapshot.resources[0].cause, "access_denied")
        self.assertEqual(
            result.snapshot.resources[0].missing_permission,
            "reference:DescribeResource",
        )
        self.assertEqual(result.context.freshness_status, "incomplete")
        self.assertEqual(result.context.confidence, 0)

    def test_expired_unreferenced_collection_cannot_claim_retained_snapshot(self):
        def old(fields):
            fields["read_window_start"] -= timedelta(days=8)
            fields["read_window_end"] -= timedelta(days=8)

        self.connector = Stub(old)
        self.configure()
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (IDENTITY,))
        self.assertEqual(caught.exception.code, "snapshot_unavailable")
        from sqlalchemy import func

        with self.factory() as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(CloudContextSnapshot)), 0
            )

    def test_collection_duplicate_cannot_resurrect_or_return_purged_observation(self):
        from models.repositories.cloud_snapshots import (
            put_snapshot,
            purge_expired_snapshots,
        )

        def old(fields):
            fields["read_window_start"] -= timedelta(days=8)
            fields["read_window_end"] -= timedelta(days=8)

        self.connector = Stub(old)
        config = self.configure()
        raw = self.connector.collect(
            (IDENTITY,), project_id=1, scope_id=config.scope_id
        )
        snapshot = redact_snapshot(
            raw, mask_accounts=True, account_identifiers=(raw.scope,)
        )
        with self.factory() as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            row = put_snapshot(db, snapshot, mask_accounts=True)
            self.assertEqual(purge_expired_snapshots(db, project_id=1), 1)
            db.commit()
            original_expiry, original_purge = row.expires_at, row.purged_at
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (IDENTITY,))
        self.assertEqual(caught.exception.code, "snapshot_unavailable")
        with self.factory() as db:
            row = db.get(CloudContextSnapshot, (1, snapshot.digest))
            self.assertIsNone(row.payload_json)
            self.assertEqual(
                row.expires_at.replace(tzinfo=timezone.utc),
                original_expiry.replace(tzinfo=timezone.utc),
            )
            self.assertEqual(
                row.purged_at.replace(tzinfo=timezone.utc),
                original_purge.replace(tzinfo=timezone.utc),
            )

    def test_disable_and_rotate_keep_historical_snapshot(self):
        self.configure()
        saved = self.service.collect(1, (IDENTITY,)).snapshot
        self.service.configure(1, enabled=False)
        self.assertEqual(self.service.get_snapshot(1, saved.digest), saved)
        self.configure()
        self.assertEqual(self.service.get_snapshot(1, saved.digest), saved)
        with self.assertRaises(CloudContextError):
            with self.service.admit_evidence(1, saved.digest):
                pass

    def test_wrong_result_scope_provider_or_identity_is_rejected(self):
        self.configure()
        for change in (
            {"project_id": 2},
            {"provider": "other"},
            {"scope_id": "other"},
            {"resources": ()},
        ):
            self.connector = Stub(lambda fields, value=change: fields.update(value))
            with (
                self.subTest(change=change),
                self.assertRaises(CloudContextError) as caught,
            ):
                self.service.collect(1, (IDENTITY,))
            self.assertEqual(caught.exception.code, "invalid_observation")

    def test_revocation_after_collection_rolls_back(self):
        self.configure()

        def revoke(fields):
            self.port.allowed.remove(1)

        self.connector = Stub(revoke)
        with self.assertRaises(CloudContextError):
            self.service.collect(1, (IDENTITY,))
        self.port.allowed.add(1)

        with self.factory() as db:
            self.assertEqual(
                db.scalar(
                    select(__import__("sqlalchemy").func.count()).select_from(
                        CloudContextSnapshot
                    )
                ),
                0,
            )

    def test_provider_errors_do_not_echo_sensitive_exception(self):
        self.configure()
        self.factory_mock.side_effect = ValueError("SYNTHETIC-sensitive-error-canary")
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (IDENTITY,))
        self.assertNotIn("canary", str(caught.exception))

    def test_provider_cannot_smuggle_a_service_error_with_sensitive_text(self):
        self.configure()
        self.factory_mock.side_effect = CloudContextError(
            "SYNTHETIC-private-cause-canary"
        )
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (IDENTITY,))
        self.assertEqual(caught.exception.code, "invalid_observation")
        self.assertNotIn("canary", str(caught.exception))

    def test_corrupt_configuration_rejected_before_factory(self):
        self.configure()
        with self.factory() as db:
            record = db.get(AppSetting, "cloud_context:1")
            payload = json.loads(record.value)
            payload["scope_id"] = " "
            record.value = json.dumps(payload)
            db.commit()
        with self.assertRaises(CloudContextError) as caught:
            self.service.collect(1, (IDENTITY,))
        self.assertEqual(caught.exception.code, "invalid_configuration")
        self.factory_mock.assert_not_called()

    def test_evidence_admission_requires_publication(self):
        self.configure()
        snapshot = self.service.collect(1, (IDENTITY,)).snapshot
        with self.assertRaises(CloudContextError) as caught:
            with self.service.admit_evidence(1, snapshot.digest) as admission:
                admission.evidence_for(IDENTITY.address, "state", "finding-1")
        self.assertEqual(caught.exception.code, "evidence_not_published")

    def test_evidence_publication_is_bound_to_report_project_and_fact(self):
        self.configure()
        snapshot = self.service.collect(1, (IDENTITY,)).snapshot
        with self.service.admit_evidence(1, snapshot.digest) as admission:
            evidence = admission.evidence_for(IDENTITY.address, "state", "finding-1")
            self.assertIn(snapshot.digest, evidence.source_ref)
            self.assertIn("running", evidence.summary)
            report = AnalysisReport(
                project_id=1,
                risk_score=0,
                severity="low",
                recommendation="go",
                top_risk="Synthetic",
                parse_summary="Synthetic",
                narrative_opening="Synthetic",
                narrative_explanation="Synthetic",
            )
            admission.session.add(report)
            admission.session.flush()
            admission.session.add(
                StoredFinding(
                    finding_id="finding-1",
                    analysis_id=report.id,
                    title="Synthetic",
                    description="Observed state",
                    severity="low",
                    category="compute",
                    evidence_refs_json=json.dumps([evidence.evidence_id]),
                )
            )
            admission.session.flush()
            payload = evidence.model_dump(
                exclude={"context_source", "related_change_ids"}
            )
            payload["analysis_id"] = report.id
            admission.session.add(
                StoredEvidence(
                    **payload,
                    context_source_json=evidence.context_source.model_dump_json(),
                    related_change_ids_json=json.dumps(evidence.related_change_ids),
                )
            )
        with self.factory() as db:
            self.assertIsNotNone(db.get(StoredEvidence, evidence.evidence_id))
        with self.assertRaises(CloudContextError):
            admission.evidence_for(IDENTITY.address, "state", "late")

    def test_deleted_project_cannot_transfer_optin_to_reused_identifier(self):
        self.configure()
        with self.factory() as db:
            db.execute(delete(Project).where(Project.id == 1))
            db.commit()
            db.add(Project(id=1, project_key="replacement", display_name="Replacement"))
            db.commit()
        self.factory_mock.reset_mock()
        self.assertEqual(self.service.collect(1, (IDENTITY,)).state, "disabled")
        self.factory_mock.assert_not_called()

    def test_unknown_and_unimplemented_providers_fail_explicitly(self):
        service = CloudContextService(unit_of_work=self.port, clock=lambda: NOW)
        for provider, cause in (
            ("aws", "unimplemented_provider"),
            ("missing_provider", "unknown_provider"),
        ):
            service.configure(1, enabled=True, provider=provider)
            with (
                self.subTest(provider=provider),
                self.assertRaises(CloudContextError) as caught,
            ):
                service.collect(1, (IDENTITY,))
            self.assertEqual(caught.exception.code, cause)

    def test_freshness_uses_existing_vocabulary(self):
        self.configure()
        snap = self.service.collect(1, (IDENTITY,)).snapshot
        self.assertEqual(snapshot_context(None, now=NOW).freshness_status, "missing")
        self.assertEqual(snapshot_context(snap, now=NOW).freshness_status, "current")
        self.assertEqual(
            snapshot_context(snap, now=NOW + timedelta(days=2)).freshness_status,
            "stale",
        )
        self.assertEqual(
            snapshot_context(snap, now=NOW - timedelta(seconds=1)).freshness_status,
            "unknown",
        )
        self.assertEqual(
            snapshot_context(snap, now=NOW, conflicting=True).freshness_status,
            "conflicting",
        )
