"""Plan collection preserves the installed UOW and immutable storage contract."""

from __future__ import annotations
import unittest
from unittest.mock import Mock
from sqlalchemy import select
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

    def test_preparation_uses_original_service_deadline_and_total_elapsed(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from cloud.aws.client import Limits
        from cloud.reflection import extract_resources

        self.service.configure(1, enabled=True, provider="aws")
        clock = [0.0]
        timer = SimpleNamespace(monotonic=lambda: clock[0])

        def prepare(*args, **kwargs):
            result = extract_resources(*args, **kwargs)
            clock[0] = 20.0
            return result

        with (
            patch("services.cloud_context_service.time", timer, create=True),
            patch("cloud.collection.time", timer),
            patch("cloud.aws.client.time", timer),
            patch("cloud.reflection.extract_resources", side_effect=prepare),
        ):
            result = self.service.collect_plan(
                1, plan(), limits=Limits(total_deadline=15)
            )
        self.sdk.create_client.assert_not_called()
        self.assertEqual(result.budget.actual_call_count, 0)
        self.assertEqual(result.budget.elapsed_seconds, 20)
        self.assertTrue(result.snapshot.partial)

    def test_retention_time_is_included_without_discarding_timely_facts(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from models.repositories.cloud_snapshots import get_snapshot

        self.service.configure(1, enabled=True, provider="aws", mask_accounts=False)
        clock = [0.0]
        timer = SimpleNamespace(monotonic=lambda: clock[0])

        def readback(*args, **kwargs):
            result = get_snapshot(*args, **kwargs)
            clock[0] = 20.0
            return result

        with (
            patch("services.cloud_context_service.time", timer, create=True),
            patch("cloud.collection.time", timer),
            patch("cloud.aws.client.time", timer),
            patch(
                "models.repositories.cloud_snapshots.get_snapshot", side_effect=readback
            ),
        ):
            result = self.service.collect_plan(1, plan())
        self.assertEqual(result.budget.actual_call_count, 2)
        self.assertEqual(result.budget.elapsed_seconds, 20)
        self.assertFalse(result.snapshot.partial)
        self.assertTrue(result.snapshot.resources[0].facts)

    def test_final_authorization_and_commit_time_is_in_elapsed(self):
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest.mock import patch

        self.service.configure(1, enabled=True, provider="aws", mask_accounts=False)
        clock = [0.0]
        timer = SimpleNamespace(monotonic=lambda: clock[0])
        original = self.fixture.session

        @contextmanager
        def finalization(*args, **kwargs):
            with original(*args, **kwargs) as session:
                yield session
                clock[0] = 20.0

        self.fixture.session = finalization
        with (
            patch("services.cloud_context_service.time", timer),
            patch("cloud.collection.time", timer),
            patch("cloud.aws.client.time", timer),
        ):
            result = self.service.collect_plan(1, plan())
        self.assertEqual(result.budget.elapsed_seconds, 20.0)
        self.assertEqual(result.budget.actual_call_count, 2)
        self.assertFalse(result.snapshot.partial)

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
