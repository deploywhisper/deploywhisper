"""Recorded plan scope extraction never consults a cloud provider."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from cloud.reflection import ReflectionError, ReflectionTarget, extract_resources


def plan(family="aws_instance", values=None, actions=None):
    values = {"id": "i-00000000000000001"} if values is None else values
    return {
        "format_version": "1.2",
        "resource_changes": [
            {
                "address": family + ".example",
                "type": family,
                "mode": "managed",
                "change": {
                    "actions": actions or ["update"],
                    "before": values,
                    "after": {"id": "i-fffffffffffffffff"},
                },
            }
        ],
    }


class ReflectionExtractionTests(unittest.TestCase):
    def setUp(self):
        self.target = ReflectionTarget(
            account_id="000000000000", regions=("us-east-1",)
        )

    def test_recorded_prior_precedence_nested_and_before_fallback(self):
        source = plan()
        source["prior_state"] = {
            "format_version": "1.0",
            "values": {
                "root_module": {
                    "child_modules": [
                        {
                            "resources": [
                                {
                                    "address": "aws_instance.example",
                                    "values": {"id": "i-00000000000000002"},
                                }
                            ]
                        }
                    ]
                }
            },
        }
        with patch(
            "builtins.__import__", side_effect=AssertionError("no provider imports")
        ):
            rows = extract_resources(source, target=self.target)
        self.assertEqual(rows[0].identity.physical_id, "i-00000000000000002")
        self.assertEqual(rows[0].source, "prior_state")
        source["prior_state"]["values"]["root_module"]["child_modules"][0]["resources"][
            0
        ]["values"] = None
        self.assertEqual(
            extract_resources(source, target=self.target)[0].source, "change.before"
        )

    def test_pure_create_and_replacement_are_distinct(self):
        source = plan(actions=["create"])
        source["resource_changes"][0]["change"]["before"] = None
        self.assertEqual(
            extract_resources(source, target=self.target)[0].state,
            "no_live_counterpart",
        )
        source["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        self.assertEqual(
            extract_resources(source, target=self.target)[0].state, "unknown"
        )
        self.assertIsNone(
            extract_resources(source, target=self.target)[0].identity.physical_id
        )

    def test_real_qualified_producer_exports(self):
        root = Path("docs/verification/live-environment-grounding/17-0/producer")
        for name in (
            "terraform-1.16.7.json",
            "terraform-1.17.2.json",
            "tofu-1.12.12.json",
            "tofu-1.13.9.json",
        ):
            with self.subTest(name=name):
                source = json.loads((root / name).read_text())
                rows = extract_resources(source, target=self.target)
                self.assertEqual(len(rows), len(source["resource_changes"]))
                self.assertTrue(any(row.source == "prior_state" for row in rows))
                self.assertTrue(any(row.state == "no_live_counterpart" for row in rows))

    def test_unsupported_formats_duplicate_and_oversized_plans_fail_closed(self):
        for version in ("1.0", "1.1", "2.0"):
            with self.subTest(version=version), self.assertRaises(ReflectionError):
                extract_resources(
                    dict(plan(), format_version=version), target=self.target
                )
        source = plan()
        source["resource_changes"] *= 2
        with self.assertRaises(ReflectionError):
            extract_resources(source, target=self.target)
        source["resource_changes"] = [
            dict(source["resource_changes"][0], address=f"aws_instance.r{i}")
            for i in range(1001)
        ]
        with self.assertRaises(ReflectionError):
            extract_resources(source, target=self.target)

    def test_only_selected_values_survive_and_after_is_not_used(self):
        source = plan(
            values={
                "id": "i-00000000000000001",
                "password": "synthetic-private-canary",
                "user_data": "raw-script",
                "unrelated": {"raw_state": "secret"},
            }
        )
        rendered = extract_resources(source, target=self.target)[0].model_dump_json()
        self.assertNotIn("synthetic-private-canary", rendered)
        self.assertNotIn("raw-script", rendered)
        self.assertNotIn("raw_state", rendered)
        self.assertNotIn("ffffffff", rendered)
        original = copy.deepcopy(source)
        extract_resources(source, target=self.target)
        self.assertEqual(source, original)


class ReflectionSensitiveSelectorTests(unittest.TestCase):
    def test_selected_sensitive_values_are_never_exported(self):
        target = ReflectionTarget(account_id="000000000000", regions=("us-east-1",))
        source = plan(
            "aws_autoscaling_group",
            {
                "id": "synthetic-private-canary",
                "name": "synthetic-private-canary",
                "password": "synthetic-private-canary",
            },
        )
        with self.assertRaises(ReflectionError) as result:
            extract_resources(source, target=target)
        self.assertNotIn("synthetic-private-canary", str(result.exception))
        source = plan(
            "aws_autoscaling_group",
            {"id": "synthetic-private-canary", "name": "synthetic-private-canary"},
        )
        source["resource_changes"][0]["change"]["before_sensitive"] = {"name": True}
        with self.assertRaises(ReflectionError):
            extract_resources(source, target=target)
