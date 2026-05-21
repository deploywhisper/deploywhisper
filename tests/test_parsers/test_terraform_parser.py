"""Tests for Terraform parser normalization behavior."""

from __future__ import annotations

import unittest

from parsers.base import UnifiedChange
from parsers.terraform_parser import parse_terraform


class TerraformParserTests(unittest.TestCase):
    def test_parse_terraform_returns_empty_list_when_content_missing(self) -> None:
        self.assertEqual(parse_terraform("plan.json", None), [])

    def test_parse_terraform_plan_json_joins_actions_and_uses_resource_specific_summary(
        self,
    ) -> None:
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
        self.assertEqual(changes[0].action, "replace")
        self.assertEqual(changes[0].metadata["actions"], ["create", "delete"])
        self.assertEqual(changes[0].resource_id, "aws_iam_policy.deploy")
        self.assertIn("changes access permissions", changes[0].summary)

    def test_parse_terraform_plan_json_preserves_module_and_plan_metadata(
        self,
    ) -> None:
        raw = b"""{
  "format_version": "1.2",
  "terraform_version": "1.8.5",
  "checks": [],
  "resource_drift": [],
  "resource_changes": [
    {
      "address": "module.network.aws_security_group.web",
      "module_address": "module.network",
      "mode": "managed",
      "type": "aws_security_group",
      "name": "web",
      "provider_name": "registry.terraform.io/hashicorp/aws",
      "change": {
        "actions": ["update"],
        "after_unknown": {"arn": true, "tags": {"DeploymentId": true}},
        "after_sensitive": {"ingress": [{"description": true}]},
        "replace_paths": [["ingress", 0, "cidr_blocks"]],
        "importing": {"id": "sg-123"}
      },
      "deposed": "unsupported-object-marker"
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(len(changes), 1)
        change = changes[0]
        self.assertEqual(change.resource_id, "module.network.aws_security_group.web")
        self.assertEqual(change.action, "modify")
        self.assertEqual(change.metadata["source_format"], "terraform_plan_json")
        self.assertEqual(change.metadata["plan_format_version"], "1.2")
        self.assertEqual(change.metadata["terraform_version"], "1.8.5")
        self.assertEqual(change.metadata["module_address"], "module.network")
        self.assertEqual(change.metadata["resource_type"], "aws_security_group")
        self.assertEqual(change.metadata["resource_name"], "web")
        self.assertEqual(
            change.metadata["provider_name"], "registry.terraform.io/hashicorp/aws"
        )
        self.assertEqual(change.metadata["replace_paths"], ["ingress.0.cidr_blocks"])
        self.assertEqual(
            change.metadata["unknown_after_apply"],
            ["arn", "tags.DeploymentId"],
        )
        self.assertEqual(
            change.metadata["redacted_fields"],
            ["ingress.0.description"],
        )
        self.assertEqual(
            change.metadata["unsupported_fields"],
            [
                "change.importing",
                "resource_change.deposed",
            ],
        )
        self.assertEqual(
            change.metadata["plan_unsupported_fields"],
            ["plan.checks", "plan.resource_drift"],
        )
        self.assertIn("changes network access rules", change.summary)
        self.assertNotIn("Plan metadata:", change.summary)

    def test_parse_terraform_plan_json_extracts_ingress_rule_facts(self) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_security_group.admin",
      "type": "aws_security_group",
      "change": {
        "actions": ["update"],
        "after": {
          "ingress": [
            {
              "protocol": "tcp",
              "from_port": 22,
              "to_port": 22,
              "cidr_blocks": ["0.0.0.0/0"],
              "ipv6_cidr_blocks": ["::/0"]
            }
          ]
        }
      }
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(
            changes[0].metadata["network_ingress_rules"],
            [
                {
                    "protocol": "tcp",
                    "from_port": 22,
                    "to_port": 22,
                    "cidr_blocks": ["0.0.0.0/0"],
                    "ipv6_cidr_blocks": ["::/0"],
                }
            ],
        )

    def test_parse_terraform_plan_json_extracts_standalone_ingress_rule_facts(
        self,
    ) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_security_group_rule.ssh",
      "type": "aws_security_group_rule",
      "change": {
        "actions": ["create"],
        "after": {
          "type": "ingress",
          "protocol": "tcp",
          "from_port": 22,
          "to_port": 22,
          "cidr_blocks": ["0.0.0.0/0"],
          "ipv6_cidr_blocks": ["::/0"]
        }
      }
    },
    {
      "address": "aws_vpc_security_group_ingress_rule.rdp",
      "type": "aws_vpc_security_group_ingress_rule",
      "change": {
        "actions": ["create"],
        "after": {
          "ip_protocol": "tcp",
          "from_port": 3389,
          "to_port": 3389,
          "cidr_ipv4": "0.0.0.0/0",
          "cidr_ipv6": "::/0"
        }
      }
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(
            changes[0].metadata["network_ingress_rules"],
            [
                {
                    "protocol": "tcp",
                    "from_port": 22,
                    "to_port": 22,
                    "cidr_blocks": ["0.0.0.0/0"],
                    "ipv6_cidr_blocks": ["::/0"],
                }
            ],
        )
        self.assertEqual(
            changes[1].metadata["network_ingress_rules"],
            [
                {
                    "protocol": "tcp",
                    "from_port": 3389,
                    "to_port": 3389,
                    "cidr_blocks": ["0.0.0.0/0"],
                    "ipv6_cidr_blocks": ["::/0"],
                }
            ],
        )

    def test_parse_terraform_plan_json_ignores_standalone_egress_rule_facts(
        self,
    ) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_security_group_rule.outbound",
      "type": "aws_security_group_rule",
      "change": {
        "actions": ["create"],
        "after": {
          "type": "egress",
          "protocol": "tcp",
          "from_port": 22,
          "to_port": 22,
          "cidr_blocks": ["0.0.0.0/0"]
        }
      }
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertNotIn("network_ingress_rules", changes[0].metadata)

    def test_parse_terraform_plan_json_trims_resource_addresses(self) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": " aws_instance.web ",
      "change": {"actions": ["update"]}
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(changes[0].resource_id, "aws_instance.web")
        self.assertEqual(
            changes[0].summary,
            "Terraform resource aws_instance.web marked for modify.",
        )

    def test_parse_terraform_plan_json_reports_root_unknown_and_sensitive_flags(
        self,
    ) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_instance.web",
      "change": {
        "actions": ["update"],
        "after_unknown": true,
        "after_sensitive": true
      }
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(changes[0].metadata["unknown_after_apply"], ["<root>"])
        self.assertEqual(changes[0].metadata["redacted_fields"], ["<root>"])

    def test_parse_terraform_plan_json_summarizes_module_scoped_generic_resource(
        self,
    ) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "module.compute.aws_instance.web",
      "module_address": "module.compute",
      "type": "aws_instance",
      "change": {"actions": ["update"]}
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(changes[0].action, "modify")
        self.assertIn(
            "Terraform resource module.compute.aws_instance.web marked for modify.",
            changes[0].summary,
        )
        self.assertNotIn("Terraform module", changes[0].summary)

    def test_parse_terraform_plan_json_preserves_noop_resources(self) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_security_group.unchanged",
      "change": {"actions": ["no-op"]}
    },
    {
      "address": "aws_security_group.updated",
      "change": {"actions": ["update"]}
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(
            [change.resource_id for change in changes],
            ["aws_security_group.unchanged", "aws_security_group.updated"],
        )
        self.assertEqual(changes[0].action, "no-op")
        self.assertEqual(changes[0].metadata["actions"], ["no-op"])
        self.assertIn("no planned changes", changes[0].summary)

    def test_parse_terraform_plan_json_attaches_plan_metadata_to_first_mutation(
        self,
    ) -> None:
        raw = b"""{
  "planned_values": {},
  "resource_changes": [
    {
      "address": "data.aws_ami.selected",
      "mode": "data",
      "change": {"actions": ["read"]}
    },
    {
      "address": "aws_security_group.updated",
      "type": "aws_security_group",
      "change": {"actions": ["update"]}
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(changes[0].action, "read")
        self.assertNotIn("plan_unsupported_fields", changes[0].metadata)
        self.assertEqual(changes[1].action, "modify")
        self.assertEqual(
            changes[1].metadata["plan_unsupported_fields"], ["plan.planned_values"]
        )

    def test_parse_terraform_plan_json_accepts_empty_plan_as_noop_entry(self) -> None:
        raw = b"""{
  "format_version": "1.2",
  "terraform_version": "1.8.5",
  "planned_values": {},
  "resource_changes": []
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].resource_id, "terraform-plan")
        self.assertEqual(changes[0].action, "no-op")
        self.assertIn("no planned resource changes", changes[0].summary)
        self.assertEqual(changes[0].metadata["actions"], ["no-op"])
        self.assertEqual(changes[0].metadata["resource_change_count"], 0)
        self.assertEqual(
            changes[0].metadata["plan_unsupported_fields"], ["plan.planned_values"]
        )

    def test_parse_terraform_plan_json_rejects_missing_resource_changes(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "missing required resource_changes"):
            parse_terraform(
                "tfplan.json",
                b'{"format_version": "1.2", "terraform_version": "1.8.5"}',
            )

    def test_parse_terraform_plan_json_rejects_non_object_root(
        self,
    ) -> None:
        for raw in (b"null", b"[]", b'"plan"'):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(
                    ValueError, "Terraform plan JSON must be an object"
                ):
                    parse_terraform("tfplan.json", raw)

    def test_parse_terraform_plan_json_rejects_non_native_plan_actions(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported Terraform action"):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["modify"]}}]}',
            )

        with self.assertRaisesRegex(ValueError, "Unsupported Terraform action"):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["destroy"]}}]}',
            )

    def test_parse_terraform_plan_json_rejects_unsupported_action_combinations(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError, "Unsupported Terraform action combination"
        ):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["read", "delete"]}}]}',
            )

        with self.assertRaisesRegex(
            ValueError, "Unsupported Terraform action combination"
        ):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["no-op", "update"]}}]}',
            )

    def test_parse_terraform_plan_json_rejects_duplicate_actions(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate Terraform action"):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["create", "create"]}}]}',
            )

        with self.assertRaisesRegex(ValueError, "Duplicate Terraform action"):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["delete", "create", "create"]}}]}',
            )

    def test_parse_terraform_plan_json_reports_plan_unsupported_fields_once(
        self,
    ) -> None:
        raw = b"""{
  "planned_values": {},
  "resource_changes": [
    {
      "address": "aws_instance.web",
      "change": {"actions": ["update"]}
    },
    {
      "address": "aws_instance.worker",
      "change": {"actions": ["update"]}
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(
            changes[0].metadata["plan_unsupported_fields"], ["plan.planned_values"]
        )
        self.assertNotIn("plan_unsupported_fields", changes[1].metadata)
        self.assertEqual(changes[0].metadata["unsupported_fields"], [])
        self.assertEqual(changes[1].metadata["unsupported_fields"], [])

    def test_parse_terraform_plan_json_rejects_missing_or_unknown_actions(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "missing required change.actions"):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {}}]}',
            )

        with self.assertRaisesRegex(ValueError, "Unsupported Terraform action"):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["future-op"]}}]}',
            )

    def test_parse_terraform_plan_json_rejects_missing_resource_address(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "missing required address"):
            parse_terraform(
                "tfplan.json",
                b'{"resource_changes": [{"change": {"actions": ["update"]}}]}',
            )

    def test_parse_terraform_plan_json_reports_invalid_metadata_shapes(
        self,
    ) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_instance.web",
      "change": {
        "actions": ["update"],
        "replace_paths": "ami",
        "after_unknown": "arn",
        "after_sensitive": "secret"
      }
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        unsupported = changes[0].metadata["unsupported_fields"]
        self.assertIn("change.after_sensitive.invalid", unsupported)
        self.assertIn("change.after_unknown.invalid", unsupported)
        self.assertIn("change.replace_paths.invalid", unsupported)
        self.assertEqual(changes[0].metadata["replace_paths"], [])
        self.assertEqual(changes[0].metadata["unknown_after_apply"], [])
        self.assertEqual(changes[0].metadata["redacted_fields"], [])

    def test_parse_terraform_plan_json_reports_generated_config_as_unsupported(
        self,
    ) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "aws_instance.imported",
      "change": {
        "actions": ["update"],
        "generated_config": "resource \\"aws_instance\\" \\"imported\\" {}"
      }
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertIn(
            "change.generated_config",
            changes[0].metadata["unsupported_fields"],
        )
        self.assertNotIn("generated_config", changes[0].metadata)

    def test_unified_change_metadata_is_json_safe(self) -> None:
        change = UnifiedChange(
            source_file="tfplan.json",
            tool="terraform",
            resource_id="aws_instance.web",
            action="modify",
            summary="Terraform resource aws_instance.web marked for modify.",
            metadata={
                "tuple_value": ("a", "b"),
                "set_value": {"x", "y"},
                "object_value": object(),
                10: "numeric key",
            },
        )

        self.assertEqual(change.metadata["tuple_value"], ["a", "b"])
        self.assertIsInstance(change.metadata["set_value"], list)
        self.assertIsInstance(change.metadata["object_value"], str)
        self.assertEqual(change.metadata["10"], "numeric key")

    def test_parse_terraform_plan_json_summarizes_typed_read_as_read_only(
        self,
    ) -> None:
        raw = b"""{
  "resource_changes": [
    {
      "address": "data.aws_security_group.selected",
      "mode": "data",
      "type": "aws_security_group",
      "change": {"actions": ["read"]}
    }
  ]
}"""

        changes = parse_terraform("tfplan.json", raw)

        self.assertEqual(changes[0].action, "read")
        self.assertIn("read-only", changes[0].summary)
        self.assertNotIn("changes network access rules", changes[0].summary)

    def test_parse_terraform_hcl_extracts_resource_and_module_changes(self) -> None:
        raw = b"""
resource "aws_vpc" "core" {
  cidr_block = "10.0.0.0/16"
}

module "cluster" {
  source = "./modules/cluster"
}
"""

        changes = parse_terraform("network.tf", raw)

        self.assertEqual(
            [change.resource_id for change in changes],
            ["aws_vpc.core", "module.cluster"],
        )
        self.assertIn("network boundaries", changes[0].summary)
        self.assertIn("multiple downstream resources", changes[1].summary)


if __name__ == "__main__":
    unittest.main()
