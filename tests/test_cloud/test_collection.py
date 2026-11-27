"""Plan-bound collection returns screened facts and truthful execution metrics."""

from __future__ import annotations

import copy
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from cloud.collection import AwsPlanCollector
from cloud.aws.client import ExecutionProgress, Limits
from cloud.reflection import (
    ReflectionTarget,
    build_manifest,
    extract_resources,
    ReflectionError,
)
from tests.test_cloud.test_reflection import plan


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.target = ReflectionTarget(
            account_id="000000000000", regions=("us-east-1",)
        )
        self.session = Mock()

        def response(operation, parameters):
            if operation == "DescribeInstances":
                return {
                    "Reservations": [
                        {
                            "Instances": [
                                {
                                    "InstanceId": parameters["InstanceIds"][0],
                                    "State": {"Name": "running"},
                                    "UserData": "unselected-private",
                                }
                            ]
                        }
                    ]
                }
            if operation == "DescribeInstanceAttribute":
                return {
                    "InstanceId": parameters["InstanceId"],
                    "DisableApiTermination": {"Value": True},
                }
            return {}

        self.session.create_client.return_value._make_api_call.side_effect = response
        self.collector = AwsPlanCollector(target=self.target, session=self.session)

    def collect(self, source=None, **kwargs):
        resources = extract_resources(source or plan(), target=self.target)
        manifest = build_manifest(resources, target=self.target)
        return self.collector.collect_manifest(
            manifest, resources=resources, project_id=1, scope_id="test-scope", **kwargs
        )

    def test_selected_facts_and_actual_count(self):
        result = self.collect()
        self.assertEqual(result.budget.actual_call_count, 2)
        self.assertEqual(result.budget.attempted_calls, 2)
        self.assertFalse(result.snapshot.partial)
        text = result.snapshot.model_dump_json()
        self.assertIn("running", text)
        self.assertNotIn("unselected-private", text)
        self.assertEqual(len(result.snapshot.resources), 1)

    def test_ec2_attachment_projection_marks_an_unreported_trailing_group_incomplete(
        self,
    ):
        client = self.session.create_client.return_value
        original_response = client._make_api_call.side_effect

        def response(operation, parameters):
            result = original_response(operation, parameters)
            if operation == "DescribeInstances":
                instance = result["Reservations"][0]["Instances"][0]
                instance["SecurityGroups"] = [
                    {"GroupId": "sg-0123456789abcdef0"},
                    {"GroupName": "missing-id"},
                ]
            return result

        client._make_api_call.side_effect = response
        (resource,) = self.collect().snapshot.resources
        self.assertEqual(resource.status.value, "partial")
        facts = {fact.name: fact.value for fact in resource.facts}
        self.assertEqual(
            facts["instance.Reservations.0.Instances.0.SecurityGroups.0.GroupId"],
            "sg-0123456789abcdef0",
        )
        self.assertEqual(
            facts["instance.Reservations.0.Instances.0.State.Name"], "running"
        )

    def test_create_needs_no_sdk(self):
        source = plan(actions=["create"])
        source["resource_changes"][0]["change"]["before"] = None
        result = self.collect(source)
        self.session.create_client.assert_not_called()
        self.assertEqual(result.budget.actual_call_count, 0)
        self.assertEqual(
            result.snapshot.resources[0].status.value, "no_live_counterpart"
        )
        self.assertFalse(result.snapshot.partial)

    def test_reservations_are_not_calls(self):
        self.session.create_client.side_effect = PermissionError("private credential")
        result = self.collect()
        self.assertEqual(result.budget.actual_call_count, 0)
        self.assertEqual(result.budget.attempted_calls, 2)
        self.assertTrue(result.snapshot.partial)
        self.assertNotIn("private credential", result.model_dump_json())
        self.assertIsNone(result.snapshot.resources[0].missing_permission)

    def test_budget_cancellation_and_late_results(self):
        result = self.collect(limits=Limits(call_budget=1))
        self.assertEqual(result.budget.actual_call_count, 1)
        self.assertEqual(result.budget.budget_consumed, 1)
        self.assertTrue(result.snapshot.partial)
        event = threading.Event()
        event.set()
        result = self.collect(cancel=event)
        self.assertTrue(result.budget.cancelled)
        self.assertEqual(result.budget.actual_call_count, 0)
        self.session.create_client.return_value._make_api_call.side_effect = lambda *a: (
            time.sleep(0.08)
        )
        result = self.collect(limits=Limits(per_call_timeout=0.01, total_deadline=0.02))
        before = result.model_dump_json()
        time.sleep(0.1)
        self.assertEqual(before, result.model_dump_json())
        self.assertTrue(result.snapshot.partial)
        self.assertFalse(result.snapshot.resources[0].facts)

    def test_scope_tamper_before_client(self):
        resources = extract_resources(plan(), target=self.target)
        manifest = build_manifest(resources, target=self.target)
        other = ReflectionTarget(account_id="111111111111", regions=("us-east-1",))
        with self.assertRaises(ReflectionError):
            self.collector.collect_manifest(
                manifest.model_copy(update={"target": other}),
                resources=resources,
                project_id=1,
                scope_id="test-scope",
            )
        self.session.create_client.assert_not_called()

    def test_secret_tag_and_raw_credentials_echo_never_return(self):
        source = plan("aws_s3_bucket", {"id": "synthetic-bucket"})

        def response(operation, parameters):
            if operation == "GetBucketVersioning":
                return {"ResponseMetadata": {"HTTPStatusCode": 200}}
            return {
                "TagSet": [
                    {"Key": "password", "Value": "synthetic-private-canary"},
                    {"Key": "owner", "Value": "synthetic-private-canary"},
                ],
                "Credentials": {"SecretAccessKey": "synthetic-private-canary"},
            }

        self.session.create_client.return_value._make_api_call.side_effect = response
        result = self.collect(source)
        self.assertNotIn("synthetic-private-canary", result.model_dump_json())
        self.assertTrue(result.snapshot.partial)

    def test_global_output_bound_and_unreachable_or_expired_diagnostics(self):
        with patch("cloud.collection._MAX_FACTS", 1):
            result = self.collect()
        self.assertTrue(result.snapshot.partial)
        self.assertEqual(result.snapshot.resources[0].cause, "output_bound")
        self.assertLessEqual(len(result.snapshot.resources[0].facts), 1)

        class ProviderFailure(Exception):
            response = {"Error": {"Code": "ExpiredToken", "Message": "private-canary"}}

        self.session.create_client.return_value._make_api_call.side_effect = (
            ProviderFailure()
        )
        result = self.collect()
        self.assertEqual(result.snapshot.resources[0].cause, "credentials_expired")
        self.assertIsNone(result.snapshot.resources[0].missing_permission)
        self.assertNotIn("private-canary", result.model_dump_json())

    def test_denial_uses_the_snapshot_screened_address(self):
        class Denied(Exception):
            response = {"Error": {"Code": "AccessDenied"}}

        source = plan()
        source["resource_changes"][0]["address"] = "aws_instance.example9182736"
        self.session.create_client.return_value._make_api_call.side_effect = Denied()
        result = self.collect(source, sensitive_values=("9182736.0",))
        screened = result.snapshot.resources[0].identity.address
        self.assertEqual(screened, "aws_instance.example[REDACTED]")
        self.assertEqual(
            {item.address for item in result.permission_denials}, {screened}
        )
        self.assertNotIn("9182736", result.model_dump_json())

    def test_actual_denial_is_exact_but_transport_does_not_invent_permissions(self):
        class Denied(Exception):
            response = {"Error": {"Code": "AccessDenied"}}

        self.session.create_client.return_value._make_api_call.side_effect = Denied()
        result = self.collect()
        self.assertEqual(result.budget.actual_call_count, 2)
        self.assertEqual(
            result.snapshot.resources[0].missing_permission,
            "ec2:DescribeInstanceAttribute",
        )
        self.assertEqual(
            {
                (item.address, item.capability, item.action)
                for item in result.permission_denials
            },
            {
                ("aws_instance.example", "instance", "ec2:DescribeInstances"),
                (
                    "aws_instance.example",
                    "termination_protection",
                    "ec2:DescribeInstanceAttribute",
                ),
            },
        )
        self.session.create_client.return_value._make_api_call.side_effect = (
            ConnectionError("private-transport")
        )
        result = self.collect()
        self.assertIsNone(result.snapshot.resources[0].missing_permission)
        self.assertEqual(result.snapshot.resources[0].cause, "transport_error")
        self.assertEqual(result.permission_denials, ())

        self.session.create_client.side_effect = Denied()
        result = self.collect()
        self.assertEqual(result.budget.actual_call_count, 0)
        self.assertEqual(result.snapshot.resources[0].cause, "credentials_unavailable")
        self.assertEqual(result.permission_denials, ())

    def collect_multiple_regions(self, **kwargs):
        target = ReflectionTarget(
            account_id="000000000000", regions=("us-east-1", "us-west-2")
        )
        collector = AwsPlanCollector(target=target, session=self.session)
        source = plan(values={"id": "i-00000000000000001", "region": "us-east-1"})
        second = copy.deepcopy(source["resource_changes"][0])
        second["address"] = "aws_instance.second"
        second["change"]["before"]["region"] = "us-west-2"
        source["resource_changes"].append(second)
        rows = extract_resources(source, target=target)
        manifest = build_manifest(rows, target=target)
        return collector.collect_manifest(
            manifest,
            resources=rows,
            project_id=1,
            scope_id="test-scope",
            **kwargs,
        )

    def test_multiple_regions_share_one_budget_and_deadline(self):
        result = self.collect_multiple_regions(limits=Limits(call_budget=1))
        self.assertEqual(result.budget.actual_call_count, 1)
        self.assertEqual(result.budget.attempted_calls, 1)
        self.assertTrue(result.snapshot.partial)
        self.assertEqual(self.session.create_client.call_count, 1)
        self.assertEqual(result.budget.planned_calls, 4)

    def test_timed_out_worker_does_not_allow_more_dispatch_in_another_region(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def read(*args):
            started.set()
            try:
                release.wait(1)
                return {}
            finally:
                finished.set()

        self.session.create_client.return_value._make_api_call.side_effect = read
        try:
            result = self.collect_multiple_regions(
                limits=Limits(concurrency=1, per_call_timeout=0.08, total_deadline=0.8)
            )
            self.assertTrue(started.is_set())
            self.assertFalse(finished.is_set())
            self.assertEqual(result.budget.actual_call_count, 1)
            self.assertEqual(self.session.create_client.call_count, 1)
            self.assertTrue(result.snapshot.partial)
        finally:
            release.set()
            self.assertTrue(finished.wait(1))

    def test_backoff_applies_after_denial_at_region_boundary(self):
        class Denied(Exception):
            response = {"Error": {"Code": "AccessDenied"}}

        timestamps = {}
        response = self.session.create_client.return_value._make_api_call.side_effect

        def create(service, config, *, timeout):
            region = config["region"]
            timestamps.setdefault(region, time.monotonic())

            def read(operation, parameters):
                if region == "us-east-1" and operation == "DescribeInstanceAttribute":
                    timestamps["denial"] = time.monotonic()
                    raise Denied()
                return response(operation, parameters)

            return Mock(_make_api_call=Mock(side_effect=read))

        self.session.create_client.side_effect = create
        result = self.collect_multiple_regions(
            limits=Limits(concurrency=1, backoff=0.15)
        )
        self.assertEqual(result.budget.actual_call_count, 4)
        self.assertGreaterEqual(timestamps["us-west-2"] - timestamps["denial"], 0.15)

    def test_cancel_during_client_creation_consumes_reservation_not_call(self):
        event = threading.Event()

        def create(*a, **kw):
            event.set()
            return Mock()

        self.session.create_client.side_effect = create
        result = self.collect(cancel=event, limits=Limits(concurrency=1))
        self.assertEqual(result.budget.attempted_calls, 1)
        self.assertEqual(result.budget.actual_call_count, 0)
        self.assertEqual(result.snapshot.issued_actions, ())
        self.assertTrue(result.budget.cancelled)

    def test_cancel_during_sdk_method_resolution_never_counts_or_invokes_call(self):
        event = threading.Event()
        invoke = Mock(return_value={})

        class Client:
            @property
            def _make_api_call(self):
                event.set()
                return invoke

        self.session.create_client.return_value = Client()
        result = self.collect(cancel=event, limits=Limits(concurrency=1))
        invoke.assert_not_called()
        self.assertEqual(result.budget.attempted_calls, 1)
        self.assertEqual(result.budget.actual_call_count, 0)
        self.assertTrue(result.budget.cancelled)

    def test_closing_progress_freezes_accounting_during_client_setup(self):
        started = threading.Event()
        release = threading.Event()
        progress = ExecutionProgress()
        results = []
        client = Mock()
        slots = threading.BoundedSemaphore(1)

        def create(*args, **kwargs):
            started.set()
            release.wait(2)
            return client

        def collect():
            results.append(
                self.collect(progress=progress, limits=Limits(concurrency=1))
            )

        self.session.create_client.side_effect = create
        thread = threading.Thread(target=collect, daemon=True)
        with patch("cloud.aws.client._SLOTS", slots):
            thread.start()
            try:
                self.assertTrue(started.wait(1))
                progress.close()
                self.assertEqual(progress.counts(), (1, 0))
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(results[0].budget.actual_call_count, 0)
                self.assertTrue(results[0].snapshot.partial)
            finally:
                release.set()
                thread.join(1)
                self.assertTrue(slots.acquire(timeout=1))
                slots.release()
        client._make_api_call.assert_not_called()
        self.assertEqual(progress.counts(), (1, 0))

    def test_missing_identity_is_unknown_before_any_provider_read(self):
        source = plan()
        source["resource_changes"][0]["change"]["before"] = None
        result = self.collect(source)
        self.session.create_client.assert_not_called()
        self.assertEqual(result.snapshot.resources[0].status.value, "unknown")
        self.assertEqual(
            result.snapshot.resources[0].cause, "recorded_identity_missing"
        )
        self.assertEqual(result.permission_denials, ())

    def test_reverse_expansion_is_recorded_without_followup_requests(self):
        source = plan("aws_security_group", {"id": "sg-00000000000000001"})

        def response(operation, parameters):
            if operation == "DescribeNetworkInterfaces":
                return {
                    "NetworkInterfaces": [
                        {"NetworkInterfaceId": "eni-00000000000000002"}
                    ]
                }
            group = (
                "sg-00000000000000001"
                if "GroupIds" in parameters
                else "sg-00000000000000002"
            )
            return {"SecurityGroups": [{"GroupId": group}]}

        self.session.create_client.return_value._make_api_call.side_effect = response
        result = self.collect(source)
        self.assertEqual(result.budget.actual_call_count, 4)
        facts = {f.name: f.value for f in result.snapshot.resources[0].facts}
        self.assertEqual(facts["sg_eni_reverse.expansion.hop"], 1)
        self.assertEqual(facts["sg_eni_reverse.expansion.bound"], 100)
        self.assertTrue(facts["sg_eni_reverse.expansion.reason"])
        self.assertEqual(len(result.snapshot.resources), 1)
        params = [
            call.args[1]
            for call in self.session.create_client.return_value._make_api_call.call_args_list
        ]
        self.assertFalse(any("NetworkInterfaceIds" in p for p in params))

    def test_collector_guard_time_consumes_original_deadline(self):
        from cloud.reflection import guard_manifest

        clock = [0.0]
        timer = SimpleNamespace(monotonic=lambda: clock[0])

        def guard(*args, **kwargs):
            result = guard_manifest(*args, **kwargs)
            clock[0] = 0.02
            return result

        with (
            patch("cloud.collection.time", timer),
            patch("cloud.collection.guard_manifest", side_effect=guard),
        ):
            result = self.collect(limits=Limits(total_deadline=0.01))
        self.session.create_client.assert_not_called()
        self.assertEqual(result.budget.elapsed_seconds, 0.02)
        self.assertTrue(result.snapshot.partial)

    def test_reader_scope_revalidation_cannot_restart_deadline(self):
        from cloud.reflection import guard_manifest

        clock = [0.0]
        timer = SimpleNamespace(monotonic=lambda: clock[0])

        def guard(*args, **kwargs):
            result = guard_manifest(*args, **kwargs)
            clock[0] = 0.02
            return result

        with (
            patch("cloud.collection.time", timer),
            patch("cloud.aws.client.time", timer),
            patch("cloud.reflection.guard_manifest", side_effect=guard),
        ):
            result = self.collect(limits=Limits(total_deadline=0.01))
        self.session.create_client.assert_not_called()
        self.assertEqual(result.budget.actual_call_count, 0)
        self.assertTrue(result.snapshot.partial)

    def test_lowercase_provider_tags_cannot_escape_raw_collector_snapshot(self):
        secret = "synthetic-ecs-password-canary"
        arn = "arn:aws:ecs:us-east-1:000000000000:cluster/example"
        source = plan("aws_ecs_cluster", {"id": arn})
        self.session.create_client.return_value._make_api_call.return_value = {
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
        self.session.create_client.return_value._make_api_call.side_effect = None
        result = self.collect(source)
        self.assertNotIn(secret, result.model_dump_json())
        self.assertTrue(result.snapshot.partial)
