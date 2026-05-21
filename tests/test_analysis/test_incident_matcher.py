"""Tests for incident similarity matching."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module
import analysis.incident_matcher as incident_matcher_module
from parsers.base import UnifiedChange
from parsers.terraform_parser import parse_terraform


class IncidentMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "incidents.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(incident_service_module)
        reload(incident_matcher_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_find_incident_matches_returns_ranked_match(self) -> None:
        incident_service_module.ingest_incident_document(
            "incident.md",
            "# Database exposure\nDate: 2026-04-16\nSeverity: P1\nTerraform security group database exposure during deployment restart.",
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform security group database exposure during deployment restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].title, "Database exposure")
        self.assertGreater(matches[0].similarity, 0.2)
        self.assertEqual(matches[0].incident_date, "2026-04-16")

    def test_find_incident_matches_returns_empty_when_no_candidates(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform security group database exposure during deployment restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )
        self.assertEqual(matches, [])

    def test_find_incident_matches_returns_public_pattern_without_incidents(
        self,
    ) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.ssh",
                action="modify",
                summary="Terraform opened SSH ingress from 0.0.0.0/0 on port 22.",
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].match_type, "public_risk_pattern")
        self.assertEqual(matches[0].public_pattern_id, "public-ingress-wide-open")
        self.assertIn("Public risk pattern", matches[0].summary)
        self.assertIn("0.0.0.0/0", " ".join(matches[0].evidence))
        self.assertGreaterEqual(matches[0].confidence, 0.8)
        self.assertTrue(matches[0].verification_guidance)

    def test_find_incident_matches_detects_structured_terraform_ingress(
        self,
    ) -> None:
        changes = parse_terraform(
            "plan.json",
            b"""{
  "resource_changes": [
    {
      "address": "aws_security_group.ssh",
      "type": "aws_security_group",
      "change": {
        "actions": ["update"],
        "after": {
          "ingress": [
            {
              "protocol": "tcp",
              "from_port": 22,
              "to_port": 22,
              "cidr_blocks": ["0.0.0.0/0"]
            }
          ]
        }
      }
    }
  ]
}""",
        )

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].public_pattern_id, "public-ingress-wide-open")
        self.assertIn("aws_security_group.ssh", " ".join(matches[0].evidence))

    def test_find_incident_matches_detects_standalone_terraform_ingress_rule(
        self,
    ) -> None:
        changes = parse_terraform(
            "plan.json",
            b"""{
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
          "cidr_blocks": ["0.0.0.0/0"]
        }
      }
    }
  ]
}""",
        )

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].public_pattern_id, "public-ingress-wide-open")
        self.assertIn("aws_security_group_rule.ssh", " ".join(matches[0].evidence))

    def test_find_incident_matches_trusts_structured_non_admin_ingress(
        self,
    ) -> None:
        changes = parse_terraform(
            "plan.json",
            b"""{
  "resource_changes": [
    {
      "address": "aws_security_group.ssh_docs",
      "type": "aws_security_group",
      "change": {
        "actions": ["update"],
        "after": {
          "ingress": [
            {
              "protocol": "tcp",
              "from_port": 80,
              "to_port": 80,
              "cidr_blocks": ["0.0.0.0/0"]
            }
          ]
        }
      }
    }
  ]
}""",
        )

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(matches, [])

    def test_find_incident_matches_returns_stateful_destroy_public_pattern(
        self,
    ) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_db_instance.primary",
                action="destroy",
                summary="Terraform will destroy database aws_db_instance.primary.",
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].match_type, "public_risk_pattern")
        self.assertEqual(
            matches[0].public_pattern_id, "public-stateful-resource-destroy"
        )
        self.assertIn("stateful resource", matches[0].reason)
        self.assertIn("aws_db_instance.primary", " ".join(matches[0].evidence))
        self.assertGreaterEqual(matches[0].confidence, 0.8)
        self.assertTrue(matches[0].verification_guidance)

    def test_find_incident_matches_ignores_stateful_helper_destroy(
        self,
    ) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_s3_bucket_policy.logs",
                action="destroy",
                summary="Terraform will destroy bucket policy aws_s3_bucket_policy.logs.",
                metadata={"resource_type": "aws_s3_bucket_policy"},
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(matches, [])

    def test_find_incident_matches_avoids_generic_token_false_positive(self) -> None:
        incident_service_module.ingest_incident_document(
            "generic.md",
            "# Generic deployment note\nSeverity: low\nA deployment changed a resource and included a service update.",
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a resource.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(
            changes, min_similarity=0.15, project_id=self.project.id
        )
        self.assertEqual(matches, [])

    def test_find_incident_matches_ranks_more_specific_incident_higher(self) -> None:
        incident_service_module.ingest_incident_document(
            "generic.md",
            "# Generic deployment note\nSeverity: low\nSecurity group update.",
            project_id=self.project.id,
        )
        incident_service_module.ingest_incident_document(
            "specific.md",
            "# Database exposure\nSeverity: P1\nTerraform security group database exposure during deployment restart.",
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform security group database exposure during deployment restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(
            changes, min_similarity=0.1, project_id=self.project.id
        )
        self.assertGreaterEqual(len(matches), 1)
        self.assertEqual(matches[0].title, "Database exposure")

    def test_find_incident_matches_prefers_higher_severity_and_recent_context(
        self,
    ) -> None:
        incident_service_module.ingest_incident_document(
            "older.md",
            "# Similar deploy\nDate: 2024-01-01\nSeverity: low\nDatabase exposure during deploy restart.",
            project_id=self.project.id,
        )
        incident_service_module.ingest_incident_document(
            "recent.md",
            "# Similar deploy\nDate: 2026-04-16\nSeverity: P1\nDatabase exposure during deploy restart.",
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Database exposure during deploy restart.",
            )
        ]
        matches = incident_matcher_module.find_incident_matches(
            changes, min_similarity=0.1, project_id=self.project.id
        )
        self.assertGreaterEqual(len(matches), 2)
        self.assertEqual(matches[0].source_file, "recent.md")
