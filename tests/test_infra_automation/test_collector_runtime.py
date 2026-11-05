"""Closed collector invocation and private frame boundaries."""

from __future__ import annotations

import base64
import json
import unittest

from infra_automation.runner.collector import (
    command_argv,
    command_digests,
    classify_exit,
)
from infra_automation.runner.collection_output import parse_collection_output


class CollectorRuntimeTests(unittest.TestCase):
    def frame(self, document=None, **changes):
        return json.dumps(
            {
                "version": 1,
                "tool": "opentofu",
                "tool_version": "1.13.1",
                "exit_code": 2,
                "plan": base64.b64encode(b"synthetic-plan").decode(),
                "json": json.dumps(
                    document or {"format_version": "1.2", "resource_changes": []}
                ),
                **changes,
            }
        ).encode()

    def test_fixed_argv_and_exit_classification(self):
        for tool, executable in (("opentofu", "tofu"), ("terraform", "terraform")):
            argv = command_argv(tool)
            self.assertEqual(
                argv[0], ("/usr/local/bin/" + executable, "version", "-json")
            )
            self.assertIn("-detailed-exitcode", argv[2])
            self.assertEqual(argv[3][-1], "/work/original.plan")
            self.assertEqual(len(command_digests(tool)), 2)
        for invalid in ("sh", "--help", "opentofu;id"):
            with self.assertRaises(ValueError):
                command_argv(invalid)
        self.assertEqual(
            [classify_exit(v) for v in (0, 2, 1, -9)],
            ["no_change", "change", "failure", "failure"],
        )

    def test_private_plan_never_enters_repr_or_screened_output(self):
        value = parse_collection_output(self.frame(), tool="opentofu", version="1.13.1")
        self.assertEqual(value.raw_plan, b"synthetic-plan")
        self.assertNotIn("synthetic-plan", repr(value))
        self.assertNotIn(b"synthetic-plan", value.screened_json)
        self.assertEqual(value.exit_code, 2)

    def test_real_no_change_optional_array_normalization(self):
        document = {
            "format_version": "1.2",
            "terraform_version": "1.13.1",
            "planned_values": {},
        }
        result = parse_collection_output(
            self.frame(document, exit_code=0), tool="opentofu", version="1.13.1"
        )
        self.assertEqual(
            json.loads(result.screened_json), {**document, "resource_changes": []}
        )
        self.assertEqual(result.exit_code, 0)

    def test_json_escaped_known_credential_rejected(self):
        secret = "ordinary-private-value"
        escaped = "".join("\\u%04x" % ord(char) for char in secret)
        text = '{"format_version":"1.2","resource_changes":[],"x":"' + escaped + '"}'
        with self.assertRaises(ValueError):
            parse_collection_output(
                self.frame(json=text),
                tool="opentofu",
                version="1.13.1",
                sensitive_values=(secret,),
            )

    def test_json_escaped_credential_punctuation_rejected(self):
        for secret in ('ordinary"private', "ordinary\\private", "ordinary\nprivate"):
            with self.subTest(secret=secret), self.assertRaises(ValueError):
                parse_collection_output(
                    self.frame(
                        {"format_version": "1.2", "resource_changes": [], "x": secret}
                    ),
                    tool="opentofu",
                    version="1.13.1",
                    sensitive_values=(secret,),
                )

    def test_known_credentials_in_decoded_keys_are_rejected(self):
        for secret in (
            'private"collector',
            "private\\collector",
            "private\ncollector",
            "private\u2603collector",
        ):
            with self.subTest(kind="escaped-key"), self.assertRaises(ValueError):
                parse_collection_output(
                    self.frame(
                        {
                            "format_version": "1.2",
                            "resource_changes": [],
                            "planned_values": {
                                "outputs": {
                                    "value": {
                                        "sensitive": False,
                                        "value": {secret: "innocent"},
                                    }
                                }
                            },
                        }
                    ),
                    tool="opentofu",
                    version="1.13.1",
                    sensitive_values=(secret,),
                )
        secret = "ordinary-private-value"
        escaped = "".join("\\u%04x" % ord(char) for char in secret)
        text = (
            '{"format_version":"1.2","resource_changes":[],"nested":{"'
            + escaped
            + '":"innocent"}}'
        )
        with self.assertRaises(ValueError):
            parse_collection_output(
                self.frame(json=text),
                tool="opentofu",
                version="1.13.1",
                sensitive_values=(secret,),
            )

    def test_sensitive_masks_credentials_errors_and_versions_reject(self):
        for raw in (
            self.frame(
                {"resource_changes": [{"change": {"after_sensitive": {"value": True}}}]}
            ),
            self.frame(
                {
                    "planned_values": {
                        "outputs": {"x": {"sensitive": True, "value": "private"}}
                    }
                }
            ),
            self.frame({"resource_changes": [], "x": "known-credential"}),
            self.frame(
                {"format_version": "1.2", "resource_changes": [], "errored": True}
            ),
            self.frame(
                {"format_version": "1.2", "resource_changes": [], "complete": False}
            ),
            self.frame(
                {"format_version": "1.2", "resource_changes": [], "incomplete": True}
            ),
            self.frame(
                {"format_version": "1.2", "resource_changes": [], "value": float("nan")}
            ),
            self.frame(exit_code=1),
            self.frame(tool_version="1.0.0"),
            self.frame(plan="invalid"),
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_collection_output(
                    raw,
                    tool="opentofu",
                    version="1.13.1",
                    sensitive_values=("known-credential",),
                )


class CollectorCatalogTests(unittest.TestCase):
    def catalog(self, **changes):
        from infra_automation.runner.catalog import CatalogDocument

        return CatalogDocument.model_validate(
            {
                "image_id": "sha256:" + "a" * 64,
                "tool_versions": [{"tool": "opentofu", "version": "1.13.1"}],
                "files": [
                    {
                        "path": path,
                        "sha256": "sha256:" + "b" * 64,
                        "kind": "lock" if path.endswith(".lock.hcl") else "tool",
                    }
                    for path in (
                        "/usr/local/bin/python",
                        "/usr/local/bin/tofu",
                        "/opt/deploywhisper/bootstrap.py",
                        "/opt/deploywhisper/collector.py",
                        "/opt/deploywhisper/tofurc",
                        "/opt/deploywhisper/.terraform.lock.hcl",
                    )
                ],
                **changes,
            }
        )

    def test_collection_requires_pinned_manifest_and_closed_tool(self):
        from infra_automation.runner.catalog import CommandRequest, build_argv
        from pydantic import ValidationError

        request = CommandRequest(command="collect_plan", tool="opentofu")
        self.assertEqual(
            build_argv(self.catalog(), request),
            (
                "/usr/local/bin/python",
                "-I",
                "/opt/deploywhisper/collector.py",
                "opentofu",
                "1.13.1",
            ),
        )
        with self.assertRaises(ValueError):
            build_argv(self.catalog(tool_versions=[]), request)
        with self.assertRaises(ValueError):
            build_argv(
                self.catalog(), CommandRequest(command="collect_plan", tool="terraform")
            )
        for value in (
            {"command": "collect_plan"},
            {"command": "collect_plan", "tool": "--help"},
            {"command": "collect_plan", "tool": "opentofu", "version": "1.0.0"},
            {"command": "tool_version", "tool": "opentofu"},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CommandRequest.model_validate(value)


class CollectorFinalizationTests(unittest.TestCase):
    def test_private_frame_success_and_failure_never_retain_raw_bytes(self):
        from datetime import datetime, timedelta, timezone
        import hashlib
        from pathlib import Path
        import subprocess
        import sys
        import tempfile
        from unittest.mock import patch
        from infra_automation.runner.execution import ExecutionRunner
        from infra_automation.runner.source import SourceSnapshot
        from tests.test_infra_automation.test_runner_execution import task_scope
        from tests.test_infra_automation.test_runner_execution_boundaries import (
            _PipeSandbox,
        )

        for scenario in (
            "success",
            "cancel",
            "custody_failure",
            "custody_tamper",
            "custody_hang",
            "sensitive",
            "partial",
            "cap",
        ):
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary).resolve()
                from threading import Event
                import time

                release = Event()
                completed = Event()
                calls = []
                frame = CollectorRuntimeTests().frame()
                if scenario == "sensitive":
                    frame = CollectorRuntimeTests().frame(
                        {
                            "format_version": "1.2",
                            "planned_values": {
                                "outputs": {"x": {"sensitive": True, "value": "hidden"}}
                            },
                        }
                    )
                if scenario == "partial":
                    frame = frame[:-3]
                if scenario == "cap":
                    frame = b"x" * 70000

                class FrameSandbox(_PipeSandbox):
                    def start(self, name):
                        return subprocess.Popen(
                            [
                                sys.executable,
                                "-u",
                                "-c",
                                "import sys; sys.stdin.readline(); print('DW_RUNNER_READY_V1',flush=True); sys.stdin.readline(); sys.stdout.buffer.write("
                                + repr(frame)
                                + "); sys.stdout.buffer.flush()",
                            ],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            start_new_session=True,
                        )

                sandbox = FrameSandbox(lambda _: None)
                catalog = CollectorCatalogTests().catalog()
                path = root / "catalog.json"
                raw = catalog.model_dump_json().encode()
                path.write_bytes(raw)
                path.chmod(0o600)
                runner = ExecutionRunner(
                    sandbox,
                    path,
                    "sha256:" + hashlib.sha256(raw).hexdigest(),
                    root / "journal",
                )
                snapshot = SourceSnapshot(
                    root, "0" * 40, "sha256:" + "b" * 64, (), 0, 0, None, "unit-only"
                )
                scope = task_scope()

                def finalize(raw_plan, screened, code, argv_digest):
                    calls.append(code)
                    self.assertFalse(
                        sandbox.created, "Container cleanup precedes publication."
                    )
                    self.assertEqual(raw_plan, b"synthetic-plan")
                    self.assertNotIn(b"synthetic-plan", screened)
                    if scenario == "custody_hang":
                        release.wait(5)
                        completed.set()
                    if scenario == "custody_failure":
                        raise OSError("private failure")
                    if scenario == "cancel":
                        runner.cancel(scope)
                    return {
                        "handle": "opaque-handle",
                        "raw_local_digest": "sha256:"
                        + hashlib.sha256(
                            raw_plan if scenario != "custody_tamper" else b"other"
                        ).hexdigest(),
                        "expires_at": (
                            datetime.now(timezone.utc) + timedelta(seconds=60)
                        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }

                started = time.monotonic()
                with patch.object(SourceSnapshot, "verify", lambda self: None):
                    result = runner.execute(
                        scope,
                        "collect_plan",
                        {"tool": "opentofu"},
                        snapshot,
                        expected_profile_digest=runner.profile_digest,
                        authority_check=lambda: True,
                        custody_finalizer=finalize,
                    )
                if scenario == "custody_hang":
                    self.assertLess(time.monotonic() - started, 2)
                    release.set()
                    self.assertTrue(completed.wait(1))
                self.assertEqual(result.finalizable, scenario == "success")
                self.assertNotIn("synthetic-plan", repr(result))
                if scenario == "success":
                    self.assertEqual(result.collection["exit_code"], 2)
                    self.assertEqual(
                        result.collection["custody"]["handle"], "opaque-handle"
                    )
                else:
                    self.assertEqual(result.output, "")
                    self.assertIsNone(result.collection)
                    self.assertIsNone(result.output_digest)
                if scenario in ("sensitive", "partial", "cap"):
                    self.assertEqual(calls, [])
                for stored in runner.journal.root.iterdir():
                    if stored.is_file():
                        self.assertNotIn(b"synthetic-plan", stored.read_bytes())
