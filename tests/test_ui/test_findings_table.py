"""Tests for findings table evidence inspector helpers."""

from __future__ import annotations

import unittest

from ui.components.findings_table import describe_evidence_item


class FindingsTableEvidenceInspectorTests(unittest.TestCase):
    def test_describe_evidence_item_builds_uploaded_artifact_link(self) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://deployments/prod/plan.json#L42?action=modify",
                "summary": "Terraform changed the production security group.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            },
            artifact_names={"deployments/prod/plan.json"},
            report_id=17,
        )

        self.assertEqual(descriptor["source_icon"], "description")
        self.assertEqual(descriptor["source_label"], "Artifact")
        self.assertEqual(
            descriptor["display_source_ref"],
            "deployments/prod/plan.json · line 42",
        )
        self.assertEqual(
            descriptor["artifact_href"],
            "/reports/17/artifacts?name=deployments%2Fprod%2Fplan.json&line=42#L42",
        )
        self.assertIsNone(descriptor["source_system"])

    def test_describe_evidence_item_matches_uploaded_artifact_by_basename(self) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://deployments/prod/plan.json#L7",
                "summary": "Terraform changed the production security group.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            },
            artifact_names={"plan.json"},
            report_id=9,
        )

        self.assertEqual(
            descriptor["artifact_href"],
            "/reports/9/artifacts?name=plan.json&line=7#L7",
        )

    def test_describe_evidence_item_preserves_current_artifact_reference_format(
        self,
    ) -> None:
        descriptor = describe_evidence_item(
            {
                "source_type": "artifact",
                "source_ref": "terraform://plan.json#aws_security_group.main?action=modify",
                "summary": "Terraform changed the production security group.",
                "severity_hint": "high",
                "deterministic": True,
                "confidence": 1.0,
            }
        )

        self.assertEqual(
            descriptor["display_source_ref"],
            "plan.json · aws_security_group.main",
        )
        self.assertIsNone(descriptor["artifact_href"])

    def test_describe_evidence_item_extracts_source_system_badges(self) -> None:
        topology_descriptor = describe_evidence_item(
            {
                "source_type": "topology",
                "source_ref": "topology://payments/api-gateway#line=18",
                "summary": "Topology maps the gateway to the payments service.",
                "severity_hint": "medium",
                "deterministic": True,
                "confidence": 0.9,
            }
        )
        incident_descriptor = describe_evidence_item(
            {
                "source_type": "incident",
                "source_ref": "incident://checkout/inc-442#database failover",
                "summary": "Past incident touched the checkout database failover path.",
                "severity_hint": "high",
                "deterministic": False,
                "confidence": 0.72,
            }
        )

        self.assertEqual(topology_descriptor["source_icon"], "hub")
        self.assertEqual(topology_descriptor["source_system"], "payments")
        self.assertEqual(incident_descriptor["source_icon"], "history")
        self.assertEqual(incident_descriptor["source_system"], "checkout")


if __name__ == "__main__":
    unittest.main()
