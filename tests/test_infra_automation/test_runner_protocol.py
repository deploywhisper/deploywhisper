"""Frozen runner protocol boundaries; no execution-isolation claim."""

from __future__ import annotations

import copy
import json
import unittest

from infra_automation.runner.protocol import Enrollment, RunnerMessage, parse_message


def message(operation="heartbeat"):
    return dict(
        version=1,
        operation=operation,
        scope=dict(
            version=1,
            runner_id="runner",
            project_id="1",
            workspace_id="2",
            run_id="run",
            step_id="collect",
            attempt=1,
            fence=1,
            coordinator_generation=1,
            authorization_epoch=1,
            restore_epoch=1,
            lease_deadline="2026-11-04T12:00:00Z",
            audience="runner-task-v1",
        ),
        capabilities=["screened-collection-v1"],
        profile_digest="sha256:" + "a" * 64,
        sequence=1,
    )


class RunnerProtocolTests(unittest.TestCase):
    def test_operations_require_exact_fields(self):
        fields = {
            "claim": {},
            "heartbeat": {},
            "log": {"log": "screened"},
            "upload": {
                "upload_digest": "sha256:" + "b" * 64,
                "atomic_upload_id": "upload",
            },
            "complete": {"atomic_upload_id": "upload", "state": "succeeded"},
        }
        for operation, extra in fields.items():
            with self.subTest(operation=operation):
                value = message(operation) | extra
                self.assertEqual(
                    RunnerMessage.model_validate(value).operation, operation
                )
                with self.assertRaises(ValueError):
                    RunnerMessage.model_validate(value | {"arbitrary_command": "no"})
                if extra:
                    value.pop(next(iter(extra)))
                    with self.assertRaises(ValueError):
                        RunnerMessage.model_validate(value)

    def test_strict_bound_fields(self):
        for path, bad in [
            ("version", True),
            ("sequence", "1"),
            ("capabilities", ["other"]),
            ("scope.attempt", False),
            ("scope.project_id", 1),
            ("scope.lease_deadline", "2026-02-30T12:00:00Z"),
            ("scope.audience", "human"),
        ]:
            value = copy.deepcopy(message())
            keys = path.split(".")
            (value[keys[0]] if len(keys) == 2 else value)[keys[-1]] = bad
            with self.subTest(path=path), self.assertRaises(ValueError):
                RunnerMessage.model_validate(value)

    def test_byte_duplicate_and_mutated_model_bounds(self):
        with self.assertRaises(ValueError):
            RunnerMessage.model_validate(message("log") | {"log": "é" * 8193})
        raw = json.dumps(message()).replace(
            '"version": 1', '"version": 1, "version": 1', 1
        )
        with self.assertRaises(ValueError):
            parse_message(raw)
        with self.assertRaises(ValueError):
            parse_message(b" " * 131073)
        model = RunnerMessage.model_validate(message())
        model.capabilities.append("other")
        with self.assertRaises(ValueError):
            RunnerMessage.model_validate(model)

    def test_enrollment_is_one_use_and_separate_audience(self):
        value = dict(
            audience="runner-enrollment-v1",
            enrollment_id="enroll",
            runner_id="runner",
            project_id="1",
            workspace_id="2",
            expires_at="2026-11-04T12:00:00Z",
            one_use=True,
        )
        self.assertEqual(Enrollment.model_validate(value).version, 1)
        for bad in (1, "true", False):
            with self.assertRaises(ValueError):
                Enrollment.model_validate(value | {"one_use": bad})
