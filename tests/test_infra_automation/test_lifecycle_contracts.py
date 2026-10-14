"""Frozen lifecycle defaults, strict mutation preconditions and policy floors."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import unittest

from pydantic import ValidationError

from infra_automation.lifecycle import (
    AutomationSettings,
    CreateWorkflowRequest,
    PublishWorkflowRequest,
    UpdateSettingsRequest,
    lifecycle_json_schema,
)


class LifecycleContractTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("jsonschema"), "optional schema validator unavailable"
    )
    def test_snapshot_input_schema_rejects_unmatched_keys_and_object_values(self):
        from jsonschema import Draft202012Validator

        schema = lifecycle_json_schema()["$defs"]["SnapshotDocument"]["properties"][
            "inputs"
        ]
        validator = Draft202012Validator(schema)
        self.assertTrue(
            validator.is_valid({"stage": "production", "limit": 1, "enabled": True})
        )
        for values in ({"bad/key": "value"}, {"stage": {"command": "forbidden"}}):
            with self.subTest(values=values):
                self.assertFalse(validator.is_valid(values))

    def test_typed_interface_matches_published_schema(self):
        schema = (
            Path(__file__).resolve().parents[2]
            / "schemas/infra-automation/workflow-lifecycle-v1.json"
        )
        self.assertEqual(json.loads(schema.read_text()), lifecycle_json_schema())

    def test_defaults_match_reviewed_interface_fixture(self):
        fixture = (
            Path(__file__).resolve().parents[1]
            / "fixtures/infra_automation/workflow_lifecycle_v1/contract.json"
        )
        expected = json.loads(fixture.read_text())["settings_defaults"]
        self.assertEqual(AutomationSettings().model_dump(), expected)

    def test_policy_floors_and_ttl_relationships_fail_closed(self):
        for values in (
            {"enabled": 1},
            {"max_active_runs": 11},
            {"max_workflows": 0},
            {"max_artifact_bytes": 8388609},
            {"retention_seconds": 86399},
            {"credential_ttl_seconds": 59},
            {"evidence_ttl_seconds": 3601},
            {"evidence_ttl_seconds": 600},
            {"command": "apply"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                AutomationSettings(**values)

    def test_preconditions_and_request_scope_are_strict(self):
        for version in (True, 0, -1, "1"):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                PublishWorkflowRequest(
                    expected_version=version, idempotency_key="k", reason="publish"
                )
        with self.assertRaises(ValidationError):
            CreateWorkflowRequest(
                project_id="1", name="example", definition="{}", reason="create"
            )
        self.assertEqual(
            UpdateSettingsRequest(
                project_id=1,
                expected_version=0,
                settings=AutomationSettings(),
                reason="enable",
            ).expected_version,
            0,
        )

    def test_settings_json_requires_a_complete_replacement(self):
        with self.assertRaises(ValidationError):
            UpdateSettingsRequest.model_validate(
                {
                    "project_id": 1,
                    "expected_version": 0,
                    "settings": {"enabled": True},
                    "reason": "enable",
                }
            )

    def test_text_bounds_reject_surrogates_controls_and_multibyte_expansion(self):
        for changes in (
            {"name": "bad\nname"},
            {"name": "bad\u0085name"},
            {"reason": "first\u2028second"},
            {"reason": "\ud800"},
            {"definition": "é" * 65537},
        ):
            raw = {
                "project_id": 1,
                "name": "example",
                "definition": "{}",
                "reason": "create",
                **changes,
            }
            with self.subTest(field=list(changes)), self.assertRaises(ValidationError):
                CreateWorkflowRequest(**raw)
