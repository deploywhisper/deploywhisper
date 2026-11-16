"""Reference-provider behavior and actual absent-provider import graph proof."""

from __future__ import annotations

from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import inspect, select
from models.database import Base
from models.tables import AppSetting

from cloud.base import (
    CloudConnector,
    ResourceIdentity,
    ResourceRead,
    SnapshotFact,
    ReadStatus,
)
from cloud.reference import ReferenceCloudConnector
from cloud.registry import (
    CONNECTORS,
    create_connector,
    UnknownProviderError,
    UnimplementedProviderError,
)
from services.cloud_context_service import CloudContextService
from tests.test_cloud.conformance.helpers import ReferenceFixture


IDENTITY = ResourceIdentity(
    address="example.resource", resource_type="example", physical_id="synthetic"
)


class ReferenceConformanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ReferenceFixture()
        self.provider = ReferenceCloudConnector(
            observations=(
                ResourceRead(
                    identity=IDENTITY,
                    status=ReadStatus.READ,
                    facts=(SnapshotFact(name="state", value="running"),),
                ),
            ),
            read_window_start=self.fixture.now,
            read_window_end=self.fixture.now,
            scope="123456789012",
            regions=("test",),
        )
        self.factory = Mock(return_value=self.provider)
        self.service = CloudContextService(
            unit_of_work=self.fixture,
            connector_factory=self.factory,
            clock=lambda: self.fixture.now,
        )

    def tearDown(self):
        self.fixture.close()

    def test_default_off_leaves_core_metadata_and_database_schema_unchanged(self):
        self.assertFalse(
            "cloud_context_snapshots" in Base.metadata.tables,
            "cloud snapshot registration pollutes shared metadata",
        )
        with self.fixture.engine.connect() as connection:
            before = set(inspect(connection).get_table_names())
        self.assertNotIn("cloud_context_snapshots", before)
        self.assertEqual(self.service.collect(1, (IDENTITY,)).state, "disabled")
        self.factory.assert_not_called()
        with self.fixture.engine.connect() as connection:
            self.assertEqual(set(inspect(connection).get_table_names()), before)
        with self.fixture.factory() as session:
            self.assertEqual(session.scalars(select(AppSetting)).all(), [])
        self.service.configure(1, enabled=False)
        self.assertEqual(self.service.collect(1, (IDENTITY,)).state, "disabled")
        with self.fixture.engine.connect() as connection:
            self.assertEqual(set(inspect(connection).get_table_names()), before)
        self.factory.assert_not_called()

    def test_reference_is_structural_and_not_globally_registered(self):
        self.assertIsInstance(self.provider, CloudConnector)
        self.assertNotIn("reference", CONNECTORS)
        with self.assertRaises(UnknownProviderError):
            create_connector("reference")
        for provider in ("aws", "azure", "gcp"):
            with (
                self.subTest(provider=provider),
                self.assertRaises(UnimplementedProviderError),
            ):
                create_connector(provider)

    def test_disabled_skips_factory_then_collect_persists_exact_observation(self):
        self.assertEqual(self.service.collect(1, (IDENTITY,)).state, "disabled")
        self.factory.assert_not_called()
        self.service.configure(1, enabled=True, provider="reference")
        self.assertFalse("cloud_context_snapshots" in Base.metadata.tables)
        with self.fixture.engine.connect() as connection:
            self.assertTrue(inspect(connection).has_table("cloud_context_snapshots"))
        with patch.object(
            socket.socket, "connect", side_effect=AssertionError("network denied")
        ):
            first = self.service.collect(1, (IDENTITY,)).snapshot
            second = self.service.collect(1, (IDENTITY,)).snapshot
            saved = self.service.get_snapshot(1, first.digest)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(saved, first)
        self.assertEqual(first.issued_actions, ())
        self.assertEqual(first.scope, "[MASKED_ACCOUNT]")
        self.assertEqual(first.resources[0].identity, IDENTITY)

    def test_only_requested_observations_are_returned(self):
        unrelated = ResourceIdentity(
            address="unrelated.resource", resource_type="example", physical_id="other"
        )
        provider = ReferenceCloudConnector(
            observations=self.provider.observations
            + (
                ResourceRead(
                    identity=unrelated,
                    status="read",
                    facts=(SnapshotFact(name="state", value="private-unrelated"),),
                ),
            ),
            read_window_start=self.fixture.now,
            read_window_end=self.fixture.now,
        )
        result = provider.collect((IDENTITY,), project_id=1, scope_id="opaque")
        self.assertEqual(tuple(row.identity for row in result.resources), (IDENTITY,))
        self.assertNotIn("private-unrelated", result.model_dump_json())
        self.assertEqual(
            provider.collect((), project_id=1, scope_id="opaque").resources, ()
        )
        with self.assertRaises(ValueError):
            provider.collect((IDENTITY, IDENTITY), project_id=1, scope_id="opaque")

    def test_missing_observation_is_explicit_unknown_not_successful_empty(self):
        missing = ResourceIdentity(address="missing", resource_type="example")
        result = self.provider.collect((missing,), project_id=1, scope_id="opaque")
        self.assertTrue(result.partial)
        self.assertEqual(len(result.resources), 1)
        self.assertEqual(result.resources[0].status, ReadStatus.UNKNOWN)
        self.assertEqual(result.resources[0].cause, "reference_observation_missing")

    def test_partial_unreadable_and_no_counterpart_are_preserved(self):
        denied = ResourceIdentity(
            address="denied", resource_type="example", physical_id="denied"
        )
        create = ResourceIdentity(address="create", resource_type="example")
        provider = ReferenceCloudConnector(
            observations=(
                ResourceRead(
                    identity=denied,
                    status=ReadStatus.UNREADABLE,
                    cause="access_denied",
                    missing_permission="reference:ReadResource",
                ),
                ResourceRead(identity=create, status=ReadStatus.NO_LIVE_COUNTERPART),
            ),
            read_window_start=self.fixture.now,
            read_window_end=self.fixture.now,
        )
        result = provider.collect((denied, create), project_id=1, scope_id="opaque")
        self.assertTrue(result.partial)
        rows = {row.identity.address: row for row in result.resources}
        self.assertEqual(rows["denied"].missing_permission, "reference:ReadResource")
        self.assertEqual(rows["create"].status, ReadStatus.NO_LIVE_COUNTERPART)
        self.assertEqual(rows["create"].facts, ())

    def test_fixture_identity_mismatch_fails_instead_of_reading_another_resource(self):
        different = IDENTITY.model_copy(update={"physical_id": "other"})
        with self.assertRaises(ValueError):
            self.provider.collect((different,), project_id=1, scope_id="opaque")

    def test_sensitive_observations_are_redacted_by_service_before_storage(self):
        self.provider = ReferenceCloudConnector(
            observations=(
                ResourceRead(
                    identity=IDENTITY,
                    status="read",
                    facts=(
                        SnapshotFact(
                            name="password", value="synthetic-reference-canary"
                        ),
                        SnapshotFact(name="echo", value="synthetic-reference-canary"),
                        SnapshotFact(name="custom_data", value="opaque-bootstrap-body"),
                    ),
                ),
            ),
            read_window_start=self.fixture.now,
            read_window_end=self.fixture.now,
        )
        self.factory.side_effect = lambda provider: self.provider
        self.service.configure(1, enabled=True, provider="reference")
        snapshot = self.service.collect(1, (IDENTITY,)).snapshot
        self.assertTrue(snapshot.partial)
        rendered = self.service.get_snapshot(1, snapshot.digest).model_dump_json()
        self.assertNotIn("synthetic-reference-canary", rendered)
        self.assertNotIn("opaque-bootstrap-body", rendered)

    def test_retained_fact_is_published_atomically_with_digest_reference(self):
        from tests.test_evidence.test_live_state_admission import publish

        self.service.configure(1, enabled=True, provider="reference")
        saved = self.service.collect(1, (IDENTITY,)).snapshot
        with self.service.admit_evidence(1, saved.digest) as admission:
            evidence = admission.evidence_for(
                IDENTITY.address, "state", "reference-fact", severity_hint="high"
            )
            report = publish(admission, evidence)
        self.assertGreater(report.id, 0)
        self.assertIn(saved.digest, evidence.source_ref)
        self.assertEqual(evidence.source_type, "live_state")

    def test_service_roundtrip_and_claim_work_without_cloud_sdks_or_other_epic_modules(
        self,
    ):
        script = textwrap.dedent("""
            import importlib.abc,sys,socket
            blocked=('infra_automation','services.infra_automation','boto3','botocore','google.cloud','azure')
            def denied(name):
                return any(name==prefix or name.startswith(prefix+'.') for prefix in blocked)
            class BlockImports(importlib.abc.MetaPathFinder):
                def find_spec(self,fullname,path=None,target=None):
                    if denied(fullname): raise AssertionError('forbidden component import: '+fullname)
            sys.meta_path.insert(0,BlockImports())
            def no_network(*args,**kwargs): raise AssertionError('network denied')
            socket.socket.connect=no_network
            socket.create_connection=no_network
            from tests.test_cloud.conformance.helpers import ReferenceFixture
            from tests.test_evidence.test_live_state_admission import publish
            from cloud.reference import ReferenceCloudConnector
            from cloud.base import ResourceIdentity,ResourceRead,SnapshotFact
            from services.cloud_context_service import CloudContextService
            fixture=ReferenceFixture()
            try:
                identity=ResourceIdentity(address='isolated',resource_type='example',physical_id='synthetic')
                provider=ReferenceCloudConnector(observations=(ResourceRead(identity=identity,status='read',facts=(SnapshotFact(name='state',value='running'),)),),read_window_start=fixture.now,read_window_end=fixture.now)
                service=CloudContextService(unit_of_work=fixture,connector_factory=lambda name:provider,clock=lambda:fixture.now)
                from sqlalchemy import inspect
                from models.database import Base
                assert 'cloud_context_snapshots' not in Base.metadata.tables
                with fixture.engine.connect() as connection:
                    assert not inspect(connection).has_table('cloud_context_snapshots')
                assert service.collect(1,(identity,)).state=='disabled'
                with fixture.engine.connect() as connection:
                    assert not inspect(connection).has_table('cloud_context_snapshots')
                service.configure(1,enabled=True,provider='reference')
                snapshot=service.collect(1,(identity,)).snapshot
                assert service.get_snapshot(1,snapshot.digest)==snapshot
                with service.admit_evidence(1,snapshot.digest) as admission:
                    evidence=admission.evidence_for(identity.address,'state','isolated-fact',severity_hint='high')
                    publish(admission,evidence)
                assert not any(denied(name) for name in sys.modules)
                print('isolated reference collection, retained claim and history passed')
            finally:
                fixture.close()
        """)
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).parents[3],
                env={"HOME": home, "PYTHON_DOTENV_DISABLED": "1"},
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("isolated reference collection", result.stdout)
