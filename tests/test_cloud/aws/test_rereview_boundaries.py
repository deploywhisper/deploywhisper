"""Regressions for name scope, routing identity and true completion times."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cloud.aws.client as boundary
from cloud.aws.client import AwsReader, Call, Limits, dry_run
from cloud.aws.response_status import response_complete


class Clock:
    def __init__(self):
        self.value = 0.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.value

    def advance(self, amount):
        with self.lock:
            self.value += amount


class RereviewBoundaryTests(unittest.TestCase):
    def call(self):
        return Call(
            capability="instance", parameters={"InstanceIds": ["i-00000000000000001"]}
        )

    def response(self):
        return {
            "Reservations": [{"Instances": [{"InstanceId": "i-00000000000000001"}]}]
        }

    def test_bucket_capabilities_require_ordinary_exact_names(self):
        for capability in ("bucket_versioning", "bucket_tags"):
            for name in (
                "arn:aws:s3:us-west-2:000000000000:accesspoint/example",
                "https://example.com/bucket",
                "bucket/path",
                "UPPER",
                "a",
                "a..b",
                "192.0.2.1",
                "demo--usw2-az1--x-s3",
                "access-s3alias",
            ):
                with (
                    self.subTest(capability=capability, name=name),
                    self.assertRaises(ValueError),
                ):
                    Call(
                        capability=capability,
                        parameters={
                            "Bucket": name,
                            "ExpectedBucketOwner": "000000000000",
                        },
                    )
            for name in ("example-bucket", "example.bucket", "123-bucket"):
                call = Call(
                    capability=capability,
                    parameters={"Bucket": name, "ExpectedBucketOwner": "000000000000"},
                )
                self.assertEqual(dry_run([call])[0]["parameters"]["Bucket"], name)
        # A bucket-specific restriction must not alter other frozen name shapes.
        Call(capability="role", parameters={"RoleName": "example+role"})

    def test_route53_unselected_variants_and_malformed_names_are_incomplete(self):
        params = {
            "HostedZoneId": "Z123",
            "StartRecordName": "example.com.",
            "StartRecordType": "A",
            "MaxItems": "1",
        }
        row = {"Name": "example.com.", "Type": "A"}
        self.assertTrue(
            response_complete("record", params, {"ResourceRecordSets": [row]})
        )
        for extra in (
            {"SetIdentifier": "blue", "Weight": 100},
            {"SetIdentifier": None},
            {"Name": "example.com.."},
        ):
            with self.subTest(extra=extra):
                self.assertFalse(
                    response_complete(
                        "record",
                        params,
                        {
                            "ResourceRecordSets": [{**row, **extra}],
                            "IsTruncated": False,
                        },
                    )
                )

    def execute_clocked(
        self, *, duration, delay_after_wait=0, per_call=0.01, total=0.015
    ):
        clock = Clock()
        source = Mock()
        release = threading.Event()

        def read(*_args):
            if not release.wait(1):
                raise AssertionError("scheduler did not enter wait")
            clock.advance(duration)
            return self.response()

        source.create_client.return_value._make_api_call.side_effect = read
        original_wait = boundary.wait

        def delayed_wait(*args, **kwargs):
            release.set()
            # Complete the controlled worker before advancing observation time;
            # OS scheduling latency must not decide this fake-clock assertion.
            kwargs["timeout"] = 1
            result = original_wait(*args, **kwargs)
            self.assertTrue(result[0])
            clock.advance(delay_after_wait)
            return result

        with (
            patch.object(boundary, "time", SimpleNamespace(monotonic=clock)),
            patch.object(boundary, "wait", delayed_wait),
        ):
            return AwsReader(source).execute(
                [self.call()],
                limits=Limits(per_call_timeout=per_call, total_deadline=total),
            )

    def test_completed_future_after_individual_deadline_is_timeout(self):
        result = self.execute_clocked(duration=0.004, per_call=0.001, total=1)
        self.assertEqual(result.items[0].status, "timeout")
        self.assertTrue(result.partial)

    def test_completed_future_after_total_deadline_is_timeout(self):
        result = self.execute_clocked(duration=0.02, per_call=0.1, total=0.01)
        self.assertEqual(result.items[0].status, "timeout")
        self.assertTrue(result.partial)

    def test_timely_completion_survives_delayed_scheduler_observation(self):
        result = self.execute_clocked(duration=0.001, delay_after_wait=0.03)
        self.assertEqual(result.items[0].status, "recorded")
        self.assertFalse(result.partial)

    def test_done_after_wait_snapshot_keeps_its_true_completion_time(self):
        clock = Clock()
        source = Mock()
        releases = [threading.Event(), threading.Event()]
        ids = ["i-00000000000000001", "i-00000000000000002"]

        def read(_operation, parameters):
            identity = parameters["InstanceIds"][0]
            if not releases[ids.index(identity)].wait(1):
                raise AssertionError("controlled worker was not released")
            return {"Reservations": [{"Instances": [{"InstanceId": identity}]}]}

        source.create_client.return_value._make_api_call.side_effect = read
        original_wait = boundary.wait

        def snapshot_wait(futures, **_kwargs):
            first, second = list(futures)
            releases[0].set()
            done, _ = original_wait([first], timeout=1)
            self.assertEqual(done, {first})
            releases[1].set()
            self.assertEqual(original_wait([second], timeout=1)[0], {second})
            # Both completed at clock0; the controller sees a stale wait
            # snapshot after being delayed beyond the per-call limit.
            clock.advance(0.03)
            return {first}, {second}

        calls = [
            Call(capability="instance", parameters={"InstanceIds": [identity]})
            for identity in ids
        ]
        with (
            patch.object(boundary, "time", SimpleNamespace(monotonic=clock)),
            patch.object(boundary, "wait", snapshot_wait),
        ):
            result = AwsReader(source).execute(
                calls, limits=Limits(per_call_timeout=0.01, total_deadline=1)
            )
        self.assertEqual(
            [item.status for item in result.items], ["recorded", "recorded"]
        )
        self.assertFalse(result.partial)

    def test_timely_future_published_after_deadline_snapshot_is_preserved(self):
        clock = Clock()
        source = Mock()
        release = threading.Event()
        controller = threading.get_ident()
        original_wait = boundary.wait
        pending_future = None
        publish_on_observation = False

        def read(*_args):
            if not release.wait(1):
                raise AssertionError("controlled worker was not released")
            return self.response()

        source.create_client.return_value._make_api_call.side_effect = read

        def monotonic():
            nonlocal publish_on_observation
            if threading.get_ident() == controller and publish_on_observation:
                publish_on_observation = False
                release.set()
                self.assertEqual(
                    original_wait([pending_future], timeout=1)[0], {pending_future}
                )
                # The worker timestamp is0, but the controller observes the
                # global deadline after the preceding done-future snapshot.
                clock.advance(0.03)
            return clock()

        def snapshot_wait(futures, **_kwargs):
            nonlocal pending_future
            pending_future = next(iter(futures))
            original_done = pending_future.done
            observations = 0

            def done():
                nonlocal observations, publish_on_observation
                observations += 1
                if observations == 2:
                    publish_on_observation = True
                    return False
                return original_done()

            pending_future.done = done
            return set(), set(futures)

        with (
            patch.object(boundary, "time", SimpleNamespace(monotonic=monotonic)),
            patch.object(boundary, "wait", snapshot_wait),
        ):
            result = AwsReader(source).execute(
                [self.call()], limits=Limits(per_call_timeout=0.01, total_deadline=0.02)
            )
        self.assertEqual(result.items[0].status, "recorded")
        self.assertFalse(result.partial)

    def test_real_short_deadline_reproduction_returns_partial(self):
        source = Mock()

        def read(*_args):
            time.sleep(0.004)
            return self.response()

        source.create_client.return_value._make_api_call.side_effect = read
        result = AwsReader(source).execute(
            [self.call()], limits=Limits(per_call_timeout=0.001, total_deadline=1)
        )
        self.assertTrue(result.partial)
        self.assertEqual(result.items[0].status, "timeout")
