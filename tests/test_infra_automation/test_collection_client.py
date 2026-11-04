"""Trusted handler must bind assignments and never upload failed private output."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from infra_automation.runner.collection_client import CollectionHandler
from infra_automation.runner.client import TaskAssignment, RunnerClientError
from infra_automation.runner.protocol import RunnerMessage, TaskScope


def scope():
    return TaskScope(
        runner_id="runner",
        project_id="project-1",
        workspace_id="workspace-1",
        run_id="run",
        step_id="collect",
        attempt=1,
        fence=1,
        coordinator_generation=1,
        authorization_epoch=1,
        restore_epoch=1,
        lease_deadline="2099-01-01T00:00:00Z",
        audience="runner-task-v1",
    )


class CollectionClientTests(unittest.TestCase):
    def handler(self):
        runner = Mock()
        runner.profile_digest = "sha256:" + "a" * 64
        snapshot = Mock(commit="b" * 40)
        return CollectionHandler(
            scope=scope(),
            repository_id="repository",
            snapshot=snapshot,
            runner=runner,
            custody=Mock(),
            tool="opentofu",
            credential_resolver=Mock(),
            evidence_ttl_seconds=300,
            execution_timeout_seconds=60,
        )

    def assignment(self, handler, **changes):
        value = dict(
            operation="heartbeat",
            scope=scope(),
            capabilities=["screened-collection-v1"],
            profile_digest=handler.runner.profile_digest,
            sequence=2,
        )
        value.update(changes)
        return TaskAssignment(RunnerMessage(**value), "private-task-token")

    def test_foreign_assignment_never_executes_or_sends(self):
        handler = self.handler()
        client = Mock()
        other = scope().model_copy(update={"fence": 2})
        with self.assertRaises(RunnerClientError):
            handler(client, self.assignment(handler, scope=other))
        handler.runner.execute.assert_not_called()
        client.send.assert_not_called()

    def test_failure_never_uploads_private_output(self):
        handler = self.handler()
        handler.runner.execute.return_value = SimpleNamespace(
            finalizable=False, output="private-plan-secret", collection=None
        )
        client = Mock()
        client.send.return_value = {
            "scope": scope().model_dump(),
            "state": "failed",
            "sequence": 2,
        }
        handler(client, self.assignment(handler))
        sent = client.send.call_args.args[0]
        self.assertEqual(sent.operation, "complete")
        self.assertEqual(sent.state, "failed")
        self.assertNotIn("private-plan-secret", str(client.send.call_args))

    def test_success_sends_only_screened_envelope_and_same_upload_id(self):
        import json
        from infra_automation.receiver_protocol import Custody
        from infra_automation.receiver_custody import digest

        handler = self.handler()
        raw = b"synthetic-private-plan"
        screened = b'{"format_version":"1.2","resource_changes":[]}'
        handler.custody.publish.side_effect = lambda handle, content, source, expiry: (
            Custody(handle=handle, raw_local_digest=digest(content), expires_at=expiry)
        )

        def execute(*args, **kwargs):
            self.assertTrue(kwargs["authority_check"]())
            custody = kwargs["custody_finalizer"](
                raw, screened, 0, "sha256:" + "c" * 64
            )
            return SimpleNamespace(
                finalizable=True,
                output=screened.decode(),
                collection={
                    "tool": "opentofu",
                    "tool_version": "1.13.1",
                    "exit_code": 0,
                    "command_digest": "sha256:" + "d" * 64,
                    "argv_digest": "sha256:" + "c" * 64,
                    "custody": custody,
                },
            )

        handler.runner.execute.side_effect = execute
        client = Mock()
        client.send.side_effect = lambda message, token, **kwargs: {
            "scope": message.scope.model_dump(),
            "sequence": message.sequence,
            "state": "running",
        }
        handler(client, self.assignment(handler))
        calls = client.send.call_args_list
        self.assertEqual(
            [call.args[0].operation for call in calls],
            ["heartbeat", "upload", "complete"],
        )
        self.assertEqual([call.args[0].sequence for call in calls], [2, 3, 4])
        self.assertEqual(
            calls[1].args[0].atomic_upload_id, calls[2].args[0].atomic_upload_id
        )
        transported = calls[1].kwargs["upload_bytes"]
        from datetime import datetime

        evidence = json.loads(transported)["provenance"]
        self.assertEqual(
            (
                datetime.fromisoformat(evidence["source_deadline"])
                - datetime.fromisoformat(evidence["collected_at"])
            ).total_seconds(),
            300,
        )
        self.assertNotIn(raw, transported)
        self.assertEqual(
            json.loads(transported)["artifacts"][0]["content"], screened.decode()
        )
        self.assertEqual(
            json.loads(transported)["provenance"]["raw_local_digest"], digest(raw)
        )

    def test_ambiguous_upload_is_never_retried(self):
        from infra_automation.receiver_protocol import Custody
        from infra_automation.receiver_custody import digest

        handler = self.handler()
        handler.custody.publish.side_effect = lambda handle, content, source, expiry: (
            Custody(handle=handle, raw_local_digest=digest(content), expires_at=expiry)
        )

        def execute(*args, **kwargs):
            custody = kwargs["custody_finalizer"](
                b"private", b'{"format_version":"1.2"}', 0, "sha256:" + "c" * 64
            )
            return SimpleNamespace(
                finalizable=True,
                output='{"format_version":"1.2"}',
                collection={
                    "tool": "opentofu",
                    "tool_version": "1.13.1",
                    "exit_code": 0,
                    "command_digest": "sha256:" + "d" * 64,
                    "argv_digest": "sha256:" + "c" * 64,
                    "custody": custody,
                },
            )

        handler.runner.execute.side_effect = execute
        client = Mock()
        client.send.side_effect = RunnerClientError()
        with self.assertRaises(RunnerClientError):
            handler(client, self.assignment(handler))
        self.assertEqual(client.send.call_count, 1)

    def test_stalled_heartbeat_does_not_block_failure_or_send_late_completion(self):
        import threading
        import time

        handler = self.handler()
        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        calls, errors, callbacks = [], [], []
        client = Mock()

        def transport(message, token, **kwargs):
            calls.append(message.operation)
            entered.set()
            release.wait(5)
            return {
                "scope": message.scope.model_dump(),
                "sequence": message.sequence,
                "state": "running",
            }

        client.send.side_effect = transport

        def execute(*args, **kwargs):
            def callback():
                try:
                    kwargs["authority_check"]()
                except RunnerClientError:
                    pass

            thread = threading.Thread(target=callback)
            callbacks.append(thread)
            thread.start()
            self.assertTrue(entered.wait(1))
            return SimpleNamespace(finalizable=False, collection=None)

        handler.runner.execute.side_effect = execute

        def run():
            try:
                handler(client, self.assignment(handler))
            except RunnerClientError:
                errors.append(True)
            finally:
                finished.set()

        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(
                finished.wait(1), "Handler waited behind an ambiguous heartbeat"
            )
            self.assertEqual(calls, ["heartbeat"])
        finally:
            release.set()
            thread.join(2)
            for callback in callbacks:
                callback.join(2)
        time.sleep(0.02)
        self.assertEqual(calls, ["heartbeat"])
        self.assertTrue(errors)

    def test_failure_completion_honors_original_task_deadline(self):
        import threading
        from datetime import datetime, timedelta, timezone

        handler = self.handler()
        near = scope().model_copy(
            update={
                "lease_deadline": (
                    datetime.now(timezone.utc) + timedelta(seconds=2)
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            }
        )
        handler.scope = near
        handler.runner.execute.return_value = SimpleNamespace(
            finalizable=False, collection=None
        )
        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        errors = []
        client = Mock()

        def transport(message, token, **kwargs):
            entered.set()
            release.wait(5)
            return {
                "scope": message.scope.model_dump(),
                "sequence": message.sequence,
                "state": "failed",
            }

        client.send.side_effect = transport

        def run():
            try:
                handler(client, self.assignment(handler, scope=near))
            except RunnerClientError:
                errors.append(True)
            finally:
                finished.set()

        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertTrue(finished.wait(2.2), "Completion exceeded original lease")
        finally:
            release.set()
            thread.join(2)
        self.assertTrue(errors)
        self.assertEqual(client.send.call_count, 1)

    def test_expired_assignment_sends_nothing(self):
        handler = self.handler()
        expired = scope().model_copy(update={"lease_deadline": "2000-01-01T00:00:00Z"})
        client = Mock()
        with self.assertRaises(RunnerClientError):
            handler(client, self.assignment(handler, scope=expired))
        handler.runner.execute.assert_not_called()
        client.send.assert_not_called()

    def test_stalled_upload_cannot_send_late_success(self):
        import threading
        from infra_automation.receiver_protocol import Custody
        from infra_automation.receiver_custody import digest

        handler = self.handler()
        handler.execution_timeout_seconds = 1
        handler.custody.publish.side_effect = lambda handle, content, source, expiry: (
            Custody(handle=handle, raw_local_digest=digest(content), expires_at=expiry)
        )

        def execute(*args, **kwargs):
            custody = kwargs["custody_finalizer"](
                b"private", b'{"format_version":"1.2"}', 0, "sha256:" + "c" * 64
            )
            return SimpleNamespace(
                finalizable=True,
                output='{"format_version":"1.2"}',
                collection={
                    "tool": "opentofu",
                    "tool_version": "1.13.1",
                    "exit_code": 0,
                    "command_digest": "sha256:" + "d" * 64,
                    "argv_digest": "sha256:" + "c" * 64,
                    "custody": custody,
                },
            )

        handler.runner.execute.side_effect = execute
        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        errors = []
        calls = []
        client = Mock()

        def transport(message, token, **kwargs):
            calls.append(message.operation)
            entered.set()
            release.wait(5)
            return {
                "scope": message.scope.model_dump(),
                "sequence": message.sequence,
                "state": "running",
            }

        client.send.side_effect = transport

        def run():
            try:
                handler(client, self.assignment(handler))
            except RunnerClientError:
                errors.append(True)
            finally:
                finished.set()

        thread = threading.Thread(target=run)
        thread.start()
        try:
            self.assertTrue(entered.wait(0.5))
            self.assertTrue(finished.wait(1.3))
            self.assertEqual(calls, ["upload"])
        finally:
            release.set()
            thread.join(2)
        self.assertTrue(errors)
        self.assertEqual(calls, ["upload"])

    def test_execution_budget_is_explicit_and_bounded(self):
        handler = self.handler()
        for duration in (True, 0, 601, 1.5):
            with self.subTest(duration=duration), self.assertRaises(RunnerClientError):
                CollectionHandler(
                    scope=scope(),
                    repository_id="repository",
                    snapshot=handler.snapshot,
                    runner=handler.runner,
                    custody=handler.custody,
                    tool="opentofu",
                    credential_resolver=Mock(),
                    evidence_ttl_seconds=300,
                    execution_timeout_seconds=duration,
                )

    def test_evidence_ttl_is_explicit_and_bounded(self):
        handler = self.handler()
        self.assertEqual(handler.evidence_ttl_seconds, 300)
        for ttl in (True, 59, 3601):
            with self.subTest(ttl=ttl), self.assertRaises(RunnerClientError):
                CollectionHandler(
                    scope=scope(),
                    repository_id="repository",
                    snapshot=handler.snapshot,
                    runner=handler.runner,
                    custody=handler.custody,
                    tool="opentofu",
                    credential_resolver=Mock(),
                    evidence_ttl_seconds=ttl,
                    execution_timeout_seconds=60,
                )


class CollectorCleanupRaceTests(unittest.TestCase):
    def test_process_group_permission_race_accepts_only_observed_exit(self):
        from unittest.mock import patch
        from infra_automation.runner.sandbox import kill_process

        for running in (True, False):
            process = Mock()
            process.poll.return_value = None if running else 0
            process.poll.side_effect = [None, None if running else 0]
            with (
                self.subTest(running=running),
                patch(
                    "infra_automation.runner.sandbox.os.killpg",
                    side_effect=PermissionError,
                ),
            ):
                self.assertEqual(kill_process(process), not running)
