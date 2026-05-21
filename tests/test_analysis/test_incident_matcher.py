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

    def test_organization_match_explains_signals_services_and_prevention(
        self,
    ) -> None:
        incident_service_module.ingest_incident_document(
            "checkout-ingress.md",
            "\n".join(
                [
                    "# Checkout ingress exposure",
                    "Date: 2026-04-20",
                    "Severity: high",
                    "The checkout-api and edge-router exposed administrative ingress.",
                    "## Affected services",
                    "- checkout-api",
                    "- edge-router",
                    "## Prevention notes",
                    "- Require expiry checks before public ingress changes.",
                    "- Restrict administrative access to trusted CIDRs.",
                ]
            ),
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.checkout_admin",
                action="modify",
                summary=(
                    "Terraform opens checkout-api administrative ingress on "
                    "edge-router from 0.0.0.0/0 on port 22."
                ),
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        organization_match = next(
            match for match in matches if match.match_type == "organization_incident"
        )
        self.assertEqual(organization_match.title, "Checkout ingress exposure")
        self.assertIn("checkout-api", organization_match.matched_signals)
        self.assertEqual(
            organization_match.affected_services, ["checkout-api", "edge-router"]
        )
        self.assertIn(
            "Require expiry checks before public ingress changes.",
            organization_match.prevention_notes,
        )
        self.assertEqual(organization_match.confidence_label, "high")
        self.assertIn("organization-specific", organization_match.reason)
        self.assertTrue(
            any(match.match_type == "public_risk_pattern" for match in matches)
        )

    def test_weak_organization_signal_is_labeled_low_confidence(self) -> None:
        incident_service_module.ingest_incident_document(
            "checkout-cache.md",
            "\n".join(
                [
                    "# Checkout cache warmup",
                    "Severity: low",
                    "Checkout cache warmup created latency during a deploy.",
                    "## Affected services",
                    "- checkout-api",
                    "## Prevention notes",
                    "- Warm caches before checkout deploys.",
                ]
            ),
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="module.checkout.aws_appautoscaling_target.api",
                action="modify",
                summary="Checkout service capacity tuning for the next deploy.",
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].match_type, "organization_incident")
        self.assertEqual(matches[0].confidence_label, "low")
        self.assertIn("Low-confidence", matches[0].summary)
        self.assertIn("checkout", matches[0].matched_signals)

    def test_incident_match_derives_legacy_confidence_label_from_numeric_string(
        self,
    ) -> None:
        match = incident_matcher_module.IncidentMatch.model_validate(
            {
                "incident_id": 17,
                "match_type": "organization_incident",
                "title": "Checkout ingress exposure",
                "severity": "high",
                "source_file": "checkout-ingress.md",
                "incident_date": None,
                "similarity": 0.86,
                "confidence": "0.86",
                "reason": "Legacy persisted payload.",
                "evidence": ["matched signals: checkout-api"],
                "verification_guidance": ["Compare against prior incident."],
                "summary": "Legacy organization incident match.",
            }
        )

        self.assertEqual(match.confidence, 0.86)
        self.assertEqual(match.confidence_label, "high")

    def test_recent_high_severity_incident_without_signals_does_not_match(
        self,
    ) -> None:
        incident_service_module.ingest_incident_document(
            "database-outage.md",
            "\n".join(
                [
                    "# Database outage",
                    "Date: 2026-05-20",
                    "Severity: high",
                    "Postgres failover caused write loss during recovery.",
                ]
            ),
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.docs",
                action="modify",
                summary="Open web documentation port for public preview.",
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(matches, [])

    def test_short_service_name_does_not_substring_match_resource_identifier(
        self,
    ) -> None:
        incident_service_module.ingest_incident_document(
            "api-incident.md",
            "\n".join(
                [
                    "# API outage",
                    "Severity: high",
                    "A generic API failed during deployment.",
                    "## Affected services",
                    "- api",
                    "## Prevention notes",
                    "- Stage generic API rollouts.",
                ]
            ),
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="module.payments.aws_lambda_function.graphql_api",
                action="modify",
                summary="Tune GraphQL function memory for payments.",
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(matches, [])

    def test_organization_match_accepts_common_explanation_heading_variants(
        self,
    ) -> None:
        incident_service_module.ingest_incident_document(
            "checkout-variant.md",
            "\n".join(
                [
                    "# Checkout deploy incident",
                    "Severity: medium",
                    "Checkout rollout missed canary checks.",
                    "## Affected service:",
                    "- checkout-api",
                    "## Prevention notes:",
                    "- Run canary checks before checkout rollout.",
                ]
            ),
            project_id=self.project.id,
        )
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="module.checkout.aws_ecs_service.api",
                action="modify",
                summary="Checkout service rollout capacity change.",
            )
        ]

        matches = incident_matcher_module.find_incident_matches(
            changes,
            project_id=self.project.id,
        )

        self.assertEqual(matches[0].affected_services, ["checkout-api"])
        self.assertEqual(
            matches[0].prevention_notes,
            ["Run canary checks before checkout rollout."],
        )

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
