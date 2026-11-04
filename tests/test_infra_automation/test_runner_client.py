"""Outbound client transport and credential custody boundaries."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import json
from unittest.mock import patch

from infra_automation.runner.client import RunnerClient, RunnerClientError
from tests.test_infra_automation.test_runner_protocol import message


class RunnerClientTests(unittest.TestCase):
    def test_https_origin_and_identity_validation(self):
        for url in (
            "http://host",
            "https://user:secret@host",
            "https://host?secret=x",
            "https://host/#x",
            "https://host/base",
        ):
            with self.subTest(url=url), self.assertRaises(RunnerClientError):
                RunnerClient(url, "runner", "token")
        with self.assertRaises(RunnerClientError):
            RunnerClient("https://host", "../runner", "token")

    def test_bounded_poll_and_backoff(self):
        calls, delays = [], []

        def transport(method, url, headers, body, timeout):
            calls.append((method, url, body))
            return 200, b'{"data":null}'

        client = RunnerClient(
            "https://host", "runner", "secret", transport=transport, sleep=delays.append
        )
        self.assertIsNone(client.poll(max_polls=4))
        self.assertEqual(delays, [0.25, 0.5, 1.0])
        self.assertEqual(len(calls), 4)
        self.assertNotIn("secret", repr(client))

    def test_post_is_never_replayed_or_error_echoed(self):
        calls = []

        def transport(*args):
            calls.append(args)
            raise RuntimeError("secret material")

        client = RunnerClient("https://host", "runner", "secret", transport=transport)
        with self.assertRaises(RunnerClientError) as raised:
            client.send(message(), "task-secret")
        self.assertNotIn("secret", str(raised.exception))
        self.assertEqual(len(calls), 1)

    def test_response_limits_and_scope_binding(self):
        for result in (
            (200, b" " * 131073),
            (302, b"{}"),
            (200, b'{"data":{"command":"bad"}}'),
        ):
            client = RunnerClient(
                "https://host", "runner", "secret", transport=lambda *args: result
            )
            with self.subTest(result=result[0]), self.assertRaises(RunnerClientError):
                client.poll(max_polls=1)
        client = RunnerClient(
            "https://host",
            "other",
            "secret",
            transport=lambda *args: (200, b'{"data":null}'),
        )
        with self.assertRaises(RunnerClientError):
            client.send(message(), "task-token")

    def test_cli_denies_public_credential_file(self):
        from cli.runner import main

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential"
            path.write_text("secret")
            path.chmod(0o644)
            with patch("sys.stderr") as error:
                self.assertEqual(
                    main(
                        [
                            "run",
                            "--url",
                            "https://host",
                            "--runner-id",
                            "runner",
                            "--credential-file",
                            str(path),
                        ]
                    ),
                    1,
                )
            self.assertNotIn("secret", str(error.mock_calls))

    def test_run_claims_before_local_handler(self):
        events = []
        claim = message("claim")

        def transport(method, url, headers, body, timeout):
            if method == "GET":
                events.append("poll")
                value = {
                    key: claim[key]
                    for key in ("scope", "profile_digest", "capabilities")
                }
                value["task_token"] = "task-secret"
            else:
                events.append("claim")
                self.assertEqual(json.loads(body)["operation"], "claim")
                value = {"scope": claim["scope"], "sequence": 1, "state": "claimed"}
            return 200, json.dumps({"data": value}).encode()

        def handler(client, assignment):
            events.append("handler")
            self.assertEqual(assignment.message.sequence, 2)
            self.assertEqual(assignment.message.operation, "heartbeat")

        client = RunnerClient("https://host", "runner", "secret", transport=transport)
        self.assertTrue(client.run(handler=handler, max_polls=1))
        self.assertEqual(events, ["poll", "claim", "handler"])
        with self.assertRaises(RunnerClientError):
            client.run()

    def test_enrollment_cli_writes_private_file_without_echo(self):
        from cli.runner import main

        enrollment = dict(
            audience="runner-enrollment-v1",
            enrollment_id="enrollment",
            runner_id="runner",
            project_id="1",
            workspace_id="2",
            expires_at="2026-11-04T12:00:00Z",
            one_use=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "enrollment-token"
            token.write_text("enrollment-secret")
            token.chmod(0o600)
            metadata = root / "enrollment.json"
            metadata.write_text(json.dumps(enrollment))
            metadata.chmod(0o600)
            output = root / "runner-token"
            with (
                patch(
                    "infra_automation.runner.client._transport",
                    return_value=(
                        200,
                        b'{"data":{"runner_id":"runner","audience":"runner-task-v1","token":"runner-secret"}}',
                    ),
                ),
                patch("sys.stdout") as stream,
            ):
                self.assertEqual(
                    main(
                        [
                            "enroll",
                            "--url",
                            "https://host",
                            "--enrollment-file",
                            str(metadata),
                            "--credential-file",
                            str(token),
                            "--output",
                            str(output),
                        ]
                    ),
                    0,
                )
            self.assertEqual(output.read_text(), "runner-secret\n")
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("runner-secret", str(stream.mock_calls))

    def test_cli_run_does_not_consume_assignment_without_handler(self):
        from cli.runner import main

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credential"
            path.write_text("secret")
            path.chmod(0o600)
            with (
                patch("infra_automation.runner.client._transport") as transport,
                patch("sys.stderr"),
            ):
                self.assertEqual(
                    main(
                        [
                            "run",
                            "--url",
                            "https://host",
                            "--runner-id",
                            "runner",
                            "--credential-file",
                            str(path),
                        ]
                    ),
                    1,
                )
                transport.assert_not_called()
