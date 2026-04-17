"""Tests for Terraform parser normalization behavior."""

from __future__ import annotations

import unittest

from parsers.terraform_parser import parse_terraform


class TerraformParserTests(unittest.TestCase):
    def test_parse_terraform_returns_empty_list_when_content_missing(self) -> None:
        self.assertEqual(parse_terraform("plan.json", None), [])

    def test_parse_terraform_plan_json_joins_actions_and_uses_resource_specific_summary(self) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_iam_policy.deploy",
      "change": {"actions": ["create", "delete"]}
    }
  ]
}"""

        changes = parse_terraform("plan.json", raw)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].action, "create+delete")
        self.assertEqual(changes[0].resource_id, "aws_iam_policy.deploy")
        self.assertIn("changes access permissions", changes[0].summary)

    def test_parse_terraform_hcl_extracts_resource_and_module_changes(self) -> None:
        raw = b'''
resource "aws_vpc" "core" {
  cidr_block = "10.0.0.0/16"
}

module "cluster" {
  source = "./modules/cluster"
}
'''

        changes = parse_terraform("network.tf", raw)

        self.assertEqual([change.resource_id for change in changes], ["aws_vpc.core", "module.cluster"])
        self.assertIn("network boundaries", changes[0].summary)
        self.assertIn("multiple downstream resources", changes[1].summary)


if __name__ == "__main__":
    unittest.main()
