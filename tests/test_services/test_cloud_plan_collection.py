"""Plan collection preserves the installed UOW and immutable storage contract."""

from __future__ import annotations
from contextlib import contextmanager
import threading
import time
import unittest
from unittest.mock import Mock, patch
from sqlalchemy import select
from cloud.aws.client import Limits
from cloud.collection import AwsPlanCollector
from cloud.reflection import ReflectionTarget
from models.cloud_snapshots import CloudContextSnapshot
from services.cloud_context_service import CloudContextService, CloudContextError
from tests.test_cloud.conformance.helpers import ReferenceFixture
from tests.test_cloud.test_reflection import plan


class CloudPlanServiceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ReferenceFixture()
        self.sdk = Mock()
        self.sdk.create_client.return_value._make_api_call.side_effect = (
            lambda operation, params: (
                {
                    "Reservations": [
                        {"Instances": [{"InstanceId": params["InstanceIds"][0]}]}
                    ]
                }
                if operation == "DescribeInstances"
                else {
                    "InstanceId": params["InstanceId"],
                    "DisableApiTermination": {"Value": True},
                }
            )
        )
        self.collector = AwsPlanCollector(
            target=ReflectionTarget(account_id="000000000000", regions=("us-east-1",)),
            session=self.sdk,
            clock=lambda: self.fixture.now,
        )
        self.factory = Mock(return_value=self.collector)
        self.service = CloudContextService(
            unit_of_work=self.fixture,
            plan_collector_factory=self.factory,
            clock=lambda: self.fixture.now,
        )

    def tearDown(self):
        self.fixture.close()

    def test_default_off_does_not_construct_provider(self):
        self.assertEqual(self.service.collect_plan(1, plan()).state, "disabled")
        self.factory.assert_not_called()

    def test_no_authority_denies_before_factory(self):
        with self.assertRaises(CloudContextError):
            CloudContextService(plan_collector_factory=self.factory).collect_plan(
                1, plan()
            )
        self.factory.assert_not_called()

    def test_retained_masked_result_and_budget(self):
        self.service.configure(1, enabled=True, provider="aws")
        result = self.service.collect_plan(1, plan())
        self.assertEqual(result.state, "snapshot")
        self.assertEqual(result.budget.actual_call_count, 2)
        self.assertNotIn("000000000000", result.model_dump_json())
        self.assertEqual(
            self.service.get_snapshot(1, result.snapshot.digest), result.snapshot
        )

    def test_post_collection_revoke_rolls_back(self):
        self.service.configure(1, enabled=True, provider="aws")
        original = self.collector.collect_manifest
        check = self.fixture.check

        def collect(*args, **kwargs):
            result = original(*args, **kwargs)

            def deny(*args):
                raise PermissionError("revoked-private")

            self.fixture.check = deny
            return result

        self.collector.collect_manifest = collect
        with self.assertRaises(CloudContextError):
            self.service.collect_plan(1, plan())
        self.fixture.check = check
        with self.fixture.factory() as session:
            self.assertEqual(list(session.scalars(select(CloudContextSnapshot))), [])

    def test_uninstalled_collector_fails_closed(self):
        service = CloudContextService(
            unit_of_work=self.fixture, clock=lambda: self.fixture.now
        )
        service.configure(1, enabled=True, provider="aws")
        result = service.collect_plan(1, plan())
        self.assertEqual(result.state, "unavailable")
        self.assertEqual(result.budget.actual_call_count, 0)
        self.sdk.create_client.assert_not_called()

    def test_blocked_preparation_returns_at_service_deadline(self):
        self.service.configure(1, enabled=True, provider="aws")
        from cloud.reflection import build_manifest

        entered, release, exited = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def prepare(*args, **kwargs):
            entered.set()
            release.wait(1)
            try:
                return build_manifest(*args, **kwargs)
            finally:
                exited.set()

        with patch("cloud.reflection.build_manifest", side_effect=prepare):
            started = time.monotonic()
            try:
                result = self.service.collect_plan(
                    1, plan(), limits=Limits(total_deadline=0.08)
                )
                self.assertLess(time.monotonic() - started, 0.45)
                self.assertTrue(entered.is_set())
                self.assertFalse(exited.is_set())
                self.assertEqual(result.state, "unavailable")
                self.assertEqual(result.budget.actual_call_count, 0)
                self.assertIn("collection_deadline", result.context.limitations)
            finally:
                release.set()
                self.assertTrue(exited.wait(1))
        self.sdk.create_client.assert_not_called()

    def test_blocked_readback_returns_budget_and_rolls_back(self):
        from models.repositories.cloud_snapshots import get_snapshot

        self.service.configure(1, enabled=True, provider="aws", mask_accounts=False)
        entered, release = threading.Event(), threading.Event()

        def readback(*args, **kwargs):
            entered.set()
            release.wait(2)
            return get_snapshot(*args, **kwargs)

        with patch(
            "models.repositories.cloud_snapshots.get_snapshot", side_effect=readback
        ):
            started = time.monotonic()
            try:
                result = self.service.collect_plan(
                    1, plan(), limits=Limits(total_deadline=0.25)
                )
                self.assertLess(time.monotonic() - started, 0.7)
                self.assertTrue(entered.is_set())
                self.assertEqual(result.state, "unavailable")
                self.assertEqual(result.budget.actual_call_count, 2)
            finally:
                release.set()
            with self.fixture.session(1, "read") as session:
                self.assertEqual(
                    list(session.scalars(select(CloudContextSnapshot))), []
                )

    def test_provider_cutoff_leaves_time_to_retain_timely_partial_facts(self):
        self.service.configure(1, enabled=True, provider="aws")
        entered, release = threading.Event(), threading.Event()
        reader = self.sdk.create_client.return_value._make_api_call
        recorded = reader.side_effect

        def read(operation, parameters):
            if operation == "DescribeInstanceAttribute":
                entered.set()
                release.wait(3)
            return recorded(operation, parameters)

        reader.side_effect = read
        try:
            result = self.service.collect_plan(
                1,
                plan(),
                limits=Limits(total_deadline=1, per_call_timeout=2, concurrency=1),
            )
            self.assertTrue(entered.is_set())
            self.assertEqual(result.state, "snapshot")
            self.assertTrue(result.snapshot.partial)
            self.assertTrue(result.snapshot.resources[0].facts)
            self.assertEqual(result.budget.actual_call_count, 2)
            self.assertLess(result.budget.elapsed_seconds, 1)
        finally:
            release.set()

    def test_cancellation_during_uow_exit_is_reported_and_fences_commit(self):
        self.service.configure(1, enabled=True, provider="aws", mask_accounts=False)
        event, release, exited = threading.Event(), threading.Event(), threading.Event()
        original = self.fixture.session

        @contextmanager
        def finalization(*args, **kwargs):
            try:
                with original(*args, **kwargs) as session:
                    yield session
                    event.set()
                    release.wait(2)
            finally:
                exited.set()

        self.fixture.session = finalization
        try:
            result = self.service.collect_plan(1, plan(), cancel=event)
            self.assertFalse(exited.is_set())
            self.assertEqual(result.state, "unavailable")
            self.assertTrue(result.budget.cancelled)
            self.assertEqual(result.budget.actual_call_count, 2)
        finally:
            release.set()
            self.assertTrue(exited.wait(2))
            self.fixture.session = original
        with self.fixture.session(1, "read") as session:
            self.assertEqual(list(session.scalars(select(CloudContextSnapshot))), [])

    def test_lowercase_ecs_tag_secret_absent_from_retained_snapshot(self):
        secret = "synthetic-ecs-password-canary"
        arn = "arn:aws:ecs:us-east-1:000000000000:cluster/example"
        self.service.configure(1, enabled=True, provider="aws")
        self.sdk.create_client.return_value._make_api_call.side_effect = None
        self.sdk.create_client.return_value._make_api_call.return_value = {
            "clusters": [
                {
                    "clusterArn": arn,
                    "tags": [
                        {"key": "password", "value": secret},
                        {"key": "owner", "value": secret},
                    ],
                }
            ]
        }
        result = self.service.collect_plan(1, plan("aws_ecs_cluster", {"id": arn}))
        self.assertNotIn(secret, result.model_dump_json())
        self.assertNotIn(
            secret,
            self.service.get_snapshot(1, result.snapshot.digest).model_dump_json(),
        )
        self.assertTrue(result.snapshot.partial)

    def test_plan_private_metadata_is_screened_before_retention(self):
        marker = "synthetic-private-test-marker"
        arn = "arn:aws:lambda:us-east-1:000000000000:function:example"
        source = plan(
            "aws_lambda_function", {"id": "example", "arn": arn, "password": marker}
        )
        self.service.configure(1, enabled=True, provider="aws")

        def response(operation, _parameters):
            if operation == "ListTags":
                return {"Tags": {"owner": marker, "team": "operations"}}
            if operation == "ListEventSourceMappings":
                return {"EventSourceMappings": []}
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

        self.sdk.create_client.return_value._make_api_call.side_effect = response
        result = self.service.collect_plan(1, source)
        stored = self.service.get_snapshot(1, result.snapshot.digest)
        self.assertTrue(stored.partial)
        self.assertIn("operations", stored.model_dump_json())
        self.assertNotIn(marker, result.model_dump_json())
        self.assertNotIn(marker, stored.model_dump_json())

    def test_retained_outcome_preserves_all_confirmed_iam_denials(self):
        class Denied(Exception):
            response = {"Error": {"Code": "AccessDenied"}}

        self.service.configure(1, enabled=True, provider="aws")
        self.sdk.create_client.return_value._make_api_call.side_effect = Denied()
        source = plan()
        source["resource_changes"][0]["address"] += '["000000000000"]'
        result = self.service.collect_plan(1, source)
        self.assertEqual(
            {denial.action for denial in result.permission_denials},
            {"ec2:DescribeInstances", "ec2:DescribeInstanceAttribute"},
        )
        self.assertEqual(
            {denial.address for denial in result.permission_denials},
            {result.snapshot.resources[0].identity.address},
        )
        self.assertNotIn("000000000000", result.model_dump_json())

    def test_private_denial_addresses_match_the_retained_resources(self):
        class Denied(Exception):
            response = {"Error": {"Code": "AccessDenied"}}

        source = plan(values={"id": "i-00000000000000001", "password": "9182736.0"})
        row = source["resource_changes"][0]
        row["address"] = 'aws_instance.example9182736["000000000000"]'
        self.service.configure(1, enabled=True, provider="aws")
        self.sdk.create_client.return_value._make_api_call.side_effect = Denied()

        result = self.service.collect_plan(1, source)
        retained = self.service.get_snapshot(1, result.snapshot.digest)
        screened = retained.resources[0].identity.address
        self.assertIn("[REDACTED]", screened)
        self.assertIn("[MASKED_ACCOUNT]", screened)
        self.assertEqual(
            {item.address for item in result.permission_denials}, {screened}
        )
        self.assertEqual(len(result.permission_denials), 2)
        self.assertNotIn("9182736", result.model_dump_json())

    def test_dynamic_fact_key_secret_absent_from_collector_and_retention(self):
        from cloud.reflection import extract_resources, build_manifest

        secret = "offline-private-canary"
        arn = "arn:aws:lambda:us-east-1:000000000000:function:example"
        source = plan("aws_lambda_function", {"id": "example", "arn": arn})
        self.service.configure(1, enabled=True, provider="aws")

        def response(operation, params):
            if operation == "ListTags":
                return {"Tags": {"password": secret, secret: "public"}}
            if operation == "ListEventSourceMappings":
                return {"EventSourceMappings": []}
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

        self.sdk.create_client.return_value._make_api_call.side_effect = response
        rows = extract_resources(source, target=self.collector.target)
        manifest = build_manifest(rows, target=self.collector.target)
        raw = self.collector.collect_manifest(
            manifest, resources=rows, project_id=1, scope_id="test-scope"
        )
        self.assertNotIn(secret, raw.model_dump_json())
        result = self.service.collect_plan(1, source)
        self.assertNotIn(secret, result.model_dump_json())
        self.assertNotIn(
            secret,
            self.service.get_snapshot(1, result.snapshot.digest).model_dump_json(),
        )
        self.assertTrue(result.snapshot.partial)
