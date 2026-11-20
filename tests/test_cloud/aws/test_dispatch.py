"""Offline cancellation tests for native AWS operation and send boundaries."""

from __future__ import annotations

import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cloud.aws.client as boundary
from cloud.aws.client import AwsReader, Limits
from cloud.aws.session import _fence_client
from cloud.reflection import ReflectionTarget, build_manifest, extract_resources


class _OfflineClient:
    def __init__(self, pause, finished):
        self.handlers = {}
        self.meta = SimpleNamespace(
            events=self,
            service_model=SimpleNamespace(
                service_id=SimpleNamespace(hyphenize=lambda: "ec2"),
                operation_names=("DescribeInstances",),
            ),
        )
        self.pause = pause
        self.finished = finished
        self.send = Mock()

    def register_first(self, name, handler, *, unique_id):
        self.handlers.setdefault(name, []).insert(0, handler)

    def _make_api_call(self, operation, parameters):
        try:
            for step in ("before-parameter-build", "before-call", "before-send"):
                self.pause(step)
                for handler in self.handlers.get(f"{step}.ec2.{operation}", ()):
                    handler(model=SimpleNamespace(name=operation))
            self.send()
            return {
                "Reservations": [
                    {"Instances": [{"InstanceId": parameters["InstanceIds"][0]}]}
                ]
            }
        finally:
            self.finished.set()

    def fenced(self):
        with patch.dict(
            sys.modules,
            {"botocore.exceptions": SimpleNamespace(ClientError=RuntimeError)},
        ):
            return _fence_client(self, "ec2")


class AwsDispatchTests(unittest.TestCase):
    def selected(self, count):
        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))
        resources = extract_resources(
            {
                "format_version": "1.2",
                "resource_changes": [
                    {
                        "address": f"aws_instance.example{index}",
                        "type": "aws_instance",
                        "change": {
                            "actions": ["update"],
                            "before": {"id": f"i-{index:017x}"},
                        },
                    }
                    for index in range(1, count + 1)
                ],
            },
            target=target,
        )
        manifest = build_manifest(resources, target=target)
        return dict(
            manifest=manifest,
            indices=tuple(
                i
                for i, entry in enumerate(manifest.entries)
                if entry.capability == "instance"
            ),
            target=target,
            resources=resources,
        )

    def test_cancellation_fences_sdk_operation_and_transport_admission(self):
        for step, expected_calls in (
            ("before-parameter-build", 0),
            ("before-call", 1),
            ("before-send", 1),
        ):
            with self.subTest(step=step):
                cancel, release, finished = (threading.Event() for _ in range(3))

                def pause(event):
                    if event == step:
                        cancel.set()
                        release.wait(2)

                fake = _OfflineClient(pause, finished)
                native = fake.fenced()
                session = SimpleNamespace(create_client=lambda *a, **kw: native)
                try:
                    result = AwsReader(session).execute_selected(
                        cancel=cancel,
                        **self.selected(1),
                    )
                    self.assertEqual(result.attempts, 1)
                    self.assertEqual(result.actual_call_count, expected_calls)
                    self.assertEqual(
                        result.issued_indices, (0,) if expected_calls else ()
                    )
                    self.assertEqual(result.items[0].status, "cancelled")
                finally:
                    release.set()
                    self.assertTrue(finished.wait(2))
                    fake.send.assert_not_called()

    def test_earlier_worker_expiry_fences_sibling_before_scheduler_poll(self):
        admitted_first, release_first, finished_first = (
            threading.Event() for _ in range(3)
        )
        entered_second, release_second, finished_second = (
            threading.Event() for _ in range(3)
        )

        def pause_first(event):
            if event == "before-send":
                admitted_first.set()
                release_first.wait(2)

        def pause_second(event):
            if event == "before-parameter-build":
                entered_second.set()
                release_second.wait(2)

        first = _OfflineClient(pause_first, finished_first).fenced()
        second = _OfflineClient(pause_second, finished_second).fenced()
        session = Mock()
        session.create_client.side_effect = (first, second)
        reader = AwsReader(session)
        reader._slots = Mock()
        now = 0.0

        def acquire(**_):
            nonlocal now
            if reader._slots.acquire.call_count == 2:
                self.assertTrue(admitted_first.wait(2))
                now = 0.005
            return True

        def wait(*args, **kwargs):
            nonlocal now
            self.assertTrue(entered_second.wait(2))
            # The first worker's deadline has passed. The second worker's
            # own deadline is still in the future.
            now = 0.012
            release_second.set()
            self.assertTrue(finished_second.wait(2))
            return original_wait(*args, **kwargs)

        reader._slots.acquire.side_effect = acquire
        original_wait = boundary.wait
        with (
            patch.object(boundary, "time", SimpleNamespace(monotonic=lambda: now)),
            patch.object(boundary, "wait", wait),
        ):
            try:
                result = reader.execute_selected(
                    limits=Limits(
                        per_call_timeout=0.01, total_deadline=1, concurrency=2
                    ),
                    **self.selected(2),
                )
                self.assertEqual(result.attempts, 2)
                self.assertEqual(result.actual_call_count, 1)
                self.assertEqual(result.issued_indices, (0,))
            finally:
                release_first.set()
                release_second.set()
                self.assertTrue(finished_first.wait(2))
                self.assertTrue(finished_second.wait(2))
                first.send.assert_not_called()
                second.send.assert_not_called()
