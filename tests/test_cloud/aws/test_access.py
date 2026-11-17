"""Offline deny-by-default access regression tests."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from cloud.aws.allowlist import ALLOWLIST, PERMISSIONS, assert_read_only, authorize


class AllowlistTests(unittest.TestCase):
    def test_catalog_read_only(self):
        assert_read_only(ALLOWLIST)
        self.assertEqual(len(ALLOWLIST), 33)
        self.assertEqual(set().union(*PERMISSIONS.values()), set(ALLOWLIST))

    def test_mutation_rejected(self):
        with self.assertRaises(ValueError):
            assert_read_only((*ALLOWLIST, "ec2:TerminateInstances"))

    def test_denial_before_construction_and_safe_audit(self):
        construct = Mock()
        with self.assertLogs("cloud.aws", level="WARNING") as logs:
            with self.assertRaises(PermissionError):
                authorize("ec2:TerminateInstances secret-canary", construct)
        construct.assert_not_called()
        self.assertNotIn("secret-canary", str(logs.output))
        self.assertIn("action_refused", str(logs.output))

    def test_policy_exact(self):
        policy = json.loads(
            Path(
                "docs/live-environment-grounding/aws-read-only-policy.json"
            ).read_text()
        )
        self.assertEqual(
            {a for row in policy["Statement"] for a in row["Action"]}, set(ALLOWLIST)
        )
        self.assertTrue(all(row["Effect"] == "Allow" for row in policy["Statement"]))

    def test_frozen_qualification_catalog(self):
        from cloud.aws.allowlist import _CATALOG

        qualified = json.loads(
            Path(
                "docs/verification/live-environment-grounding/17-0/coverage/coverage.json"
            ).read_text()
        )
        self.assertEqual(_CATALOG, qualified)
        expected = json.loads(
            Path(
                "docs/verification/live-environment-grounding/17-0/coverage/policy.json"
            ).read_text()
        )
        actual = json.loads(
            Path(
                "docs/live-environment-grounding/aws-read-only-policy.json"
            ).read_text()
        )
        self.assertEqual(actual, expected)

    def test_each_capability_denial_has_required_permission(self):
        from cloud.aws.allowlist import _CATALOG

        for family, actions in PERMISSIONS.items():
            self.assertEqual(
                actions,
                {
                    _CATALOG["operations"][c]["iam_action"]
                    for c in _CATALOG["families"][family]["operations"]
                },
            )
