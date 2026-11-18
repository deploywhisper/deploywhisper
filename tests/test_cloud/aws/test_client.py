"""Recorded calls and bounded failure behaviour."""

from __future__ import annotations
import time
import unittest
from unittest.mock import Mock
from cloud.aws.client import AwsReader, Call, Limits, dry_run


class ClientTests(unittest.TestCase):
    def call(self):
        return Call(
            capability="instance", parameters={"InstanceIds": ["i-00000000000000001"]}
        )

    def test_dryrun_no_credentials(self):
        source = Mock()
        reader = AwsReader(source)
        self.assertEqual(dry_run([self.call()])[0]["action"], "ec2:DescribeInstances")
        self.assertEqual(reader.dry_run([self.call()]), dry_run([self.call()]))
        source.create_client.assert_not_called()

    def test_unbounded_parameters_denied(self):
        for params in (
            {},
            {"InstanceIds": []},
            {"InstanceIds": ["https://evil"]},
            {"Filters": []},
        ):
            with self.subTest(params=params), self.assertRaises(ValueError):
                Call(capability="instance", parameters=params)

    def test_budget_and_denial_no_provider_echo(self):
        source = Mock()
        source.create_client.return_value._make_api_call.side_effect = RuntimeError(
            "secret-canary"
        )
        result = AwsReader(source).execute(
            [self.call(), self.call()], limits=Limits(call_budget=1)
        )
        self.assertEqual(result.attempts, 1)
        self.assertNotIn("secret-canary", repr(result))
        self.assertTrue(result.partial)

    def test_timeout_and_cancellation(self):
        source = Mock()
        source.create_client.return_value._make_api_call.side_effect = lambda *a: (
            time.sleep(0.3)
        )
        start = time.monotonic()
        result = AwsReader(source).execute(
            [self.call()], limits=Limits(per_call_timeout=0.02, total_deadline=0.04)
        )
        self.assertLess(time.monotonic() - start, 0.2)
        self.assertEqual(result.items[0].status, "timeout")
        source.reset_mock()
        import threading

        event = threading.Event()
        event.set()
        result = AwsReader(source).execute([self.call()], cancel=event)
        self.assertEqual(result.attempts, 0)
        source.create_client.assert_not_called()

    def test_mutated_copy_cannot_expand_request(self):
        call = self.call()
        call.parameters.clear()
        with self.assertRaises(ValueError):
            dry_run([call])

    def test_secret_environment_rejected_without_echo(self):
        import os
        from unittest.mock import patch

        for name in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "AWS_SECRET_KEY",
            "AWS_SECURITY_TOKEN",
        ):
            with (
                self.subTest(name=name),
                patch.dict(os.environ, {name: "synthetic-credential-canary"}),
            ):
                with self.assertRaises(ValueError) as error:
                    Call(
                        capability="role",
                        parameters={"RoleName": "synthetic-credential-canary"},
                    )
                self.assertNotIn("synthetic-credential-canary", str(error.exception))

    def test_concurrency_cap_and_budget(self):
        import threading

        lock = threading.Lock()
        active = 0
        peak = 0

        def issue(*args):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return {}

        source = Mock()
        source.create_client.return_value._make_api_call.side_effect = issue
        result = AwsReader(source).execute(
            [self.call() for _ in range(12)],
            limits=Limits(concurrency=2, call_budget=7),
        )
        self.assertLessEqual(peak, 2)
        self.assertLessEqual(result.attempts, 7)
        self.assertTrue(result.partial)

    def test_every_capability_permission_denial(self):
        from cloud.aws.allowlist import _CATALOG

        def render(value):
            if isinstance(value, dict):
                return {k: render(v) for k, v in value.items()}
            if isinstance(value, list):
                return [render(v) for v in value]
            return {
                "${id}": "i-00000000000000001",
                "${arn}": "arn:aws:lambda:us-east-1:000000000000:function:synthetic",
                "${cluster_arn}": "arn:aws:ecs:us-east-1:000000000000:cluster/synthetic",
                "${function_arn}": "arn:aws:lambda:us-east-1:000000000000:function:synthetic",
                "${event_source_arn}": "arn:aws:sqs:us-east-1:000000000000:synthetic",
                "${canonical_queue_url}": "https://sqs.us-east-1.amazonaws.com/000000000000/synthetic",
                "${account}": "000000000000",
                "${name}": "synthetic",
                "${zone_id}": "ZSYNTHETIC",
                "${record_type}": "A",
            }.get(value, value)

        for capability, row in _CATALOG["operations"].items():
            with self.subTest(capability=capability):
                source = Mock()
                source.create_client.return_value._make_api_call.side_effect = type(
                    "ClientError",
                    (Exception,),
                    {"response": {"Error": {"Code": "AccessDenied"}}},
                )("secret-canary")
                call = Call(capability=capability, parameters=render(row["params"]))
                result = AwsReader(source).execute([call])
                self.assertEqual(result.items[0].missing_permission, row["iam_action"])
                self.assertEqual(result.items[0].status, "unreadable")
                self.assertNotIn("secret-canary", repr(result))
