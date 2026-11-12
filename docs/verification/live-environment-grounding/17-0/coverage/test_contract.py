"""Abuse checks for the frozen, offline qualification manifest."""

from __future__ import annotations

import json
from pathlib import Path
import socket

import botocore.session
import unittest
from unittest.mock import patch

from validate_contract import BASE, validate_contract


class CoverageContractTests(unittest.TestCase):
    def assert_contract_rejected(self, mutate):
        original = Path.read_text
        contract = json.loads(original(BASE / "coverage.json"))
        mutate(contract)

        def read_text(path, *args, **kwargs):
            if path == BASE / "coverage.json":
                return json.dumps(contract)
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", read_text), self.assertRaises(ValueError):
            validate_contract()

    def test_renamed_family_does_not_preserve_the_freeze(self):
        def rename(contract):
            contract["families"]["aws_unapproved_family"] = contract["families"].pop(
                "aws_security_group"
            )

        self.assert_contract_rejected(rename)

    def test_empty_unknown_duplicate_or_malformed_operation_references_fail(self):
        for references in (
            [],
            ["missing_template"],
            ["instance", "instance"],
            "instance",
            [None],
        ):
            with self.subTest(references=references):
                self.assert_contract_rejected(
                    lambda contract: contract["families"]["aws_instance"].update(
                        operations=references
                    )
                )

    def test_missing_operation_references_fail(self):
        self.assert_contract_rejected(
            lambda contract: contract["families"]["aws_instance"].pop("operations")
        )

    def test_unreferenced_allowed_operation_fails(self):
        self.assert_contract_rejected(
            lambda contract: contract["families"]["aws_instance"]["operations"].remove(
                "termination_protection"
            )
        )

    def test_contract_version_is_exact_integer_one(self):
        for version in (None, True, "1", 2):
            with self.subTest(version=version):
                self.assert_contract_rejected(
                    lambda contract: contract.update(contract_version=version)
                )

    def test_sdk_models_without_network_or_credentials(self):
        with (
            patch.object(
                socket, "socket", side_effect=AssertionError("network denied")
            ),
            patch.object(
                botocore.session.Session,
                "get_credentials",
                side_effect=AssertionError("credential resolution denied"),
            ),
            patch.dict("os.environ", {"AWS_DATA_PATH": "/untrusted-models"}),
        ):
            result = validate_contract()
        self.assertEqual(result["families"], 25)
        self.assertEqual(result["provider_calls"], 0)
        self.assertFalse(result["credential_resolution"])

    def test_templates_have_plan_identity_selectors_and_no_endpoint_fields(self):
        contract = json.loads((BASE / "coverage.json").read_text())
        for key, item in contract["operations"].items():
            with self.subTest(operation=key):
                self.assertEqual(item["operation"], item["iam_action"].split(":")[1])
                self.assertRegex(
                    json.dumps(item["params"]),
                    r"\$\{(?:id|name|arn|function_arn|zone_id|canonical_queue_url)\}",
                )
                self.assertNotRegex(
                    json.dumps(item["params"]),
                    r"endpoint|role_arn|UserData|Environment",
                )

    def test_policy_wildcard_only_for_unscopable_actions(self):
        contract = json.loads((BASE / "coverage.json").read_text())
        unscopable = {"ec2", "elbv2", "autoscaling"}
        for item in contract["operations"].values():
            if "*" in item["iam_resources"]:
                self.assertTrue(
                    item["service"] in unscopable
                    or item["operation"] == "ListEventSourceMappings"
                )

    def test_sensitive_payload_actions_excluded(self):
        contract = json.loads((BASE / "coverage.json").read_text())
        actions = {item["operation"] for item in contract["operations"].values()}
        self.assertTrue(
            actions.isdisjoint(
                {
                    "GetFunction",
                    "GetFunctionConfiguration",
                    "GetSecretValue",
                    "GetParameter",
                    "GetObject",
                    "ReceiveMessage",
                    "GetEventSourceMapping",
                }
            )
        )

    def test_deliberate_mutations_fail_validation(self):
        original = Path.read_text
        contract = json.loads(original(BASE / "coverage.json"))
        policy = json.loads(original(BASE / "policy.json"))
        mutations = []
        mutated = json.loads(json.dumps(contract))
        mutated["operations"]["instance"]["iam_action"] = "ec2:TerminateInstances"
        mutations.append((mutated, policy))
        mutated = json.loads(json.dumps(contract))
        mutated["operations"]["instance"]["params"] = {}
        mutations.append((mutated, policy))
        mutated_policy = json.loads(json.dumps(policy))
        mutated_policy["Statement"][0]["Resource"] = ["arn:aws:example:*:*:unrelated"]
        mutations.append((contract, mutated_policy))
        for bad_contract, bad_policy in mutations:

            def read_text(path, *args, **kwargs):
                if path == BASE / "coverage.json":
                    return json.dumps(bad_contract)
                if path == BASE / "policy.json":
                    return json.dumps(bad_policy)
                return original(path, *args, **kwargs)

            with (
                patch.object(Path, "read_text", read_text),
                self.assertRaises(ValueError),
            ):
                validate_contract()

    def test_published_policy_matches_frozen_manifest(self):
        self.assertEqual(validate_contract()["iam_actions"], 33)


if __name__ == "__main__":
    unittest.main()
