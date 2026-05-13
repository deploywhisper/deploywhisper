"""Tests for findings table evidence inspector helpers."""

from __future__ import annotations

import unittest

from ui.components.findings_table import (
    describe_evidence_item,
    finding_row_signals,
)


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
            "/history/17/artifacts?name=deployments%2Fprod%2Fplan.json&line=42#L42",
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
            "/history/9/artifacts?name=plan.json&line=7#L7",
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

    def test_finding_row_signals_include_category_evidence_badges_and_law_status(
        self,
    ) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-001",
                "severity": "critical",
                "category": "networking/ingress",
                "deterministic": True,
                "evidence_refs": ["ev-001", "ev-002"],
            },
            [
                {
                    "evidence_id": "ev-001",
                    "source_type": "artifact",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
                {
                    "evidence_id": "ev-002",
                    "source_type": "topology",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                },
            ],
        )

        self.assertEqual(signals["category"], "networking/ingress")
        self.assertEqual(signals["evidence_count_label"], "2 evidence items")
        self.assertEqual(signals["evidence_law_label"], "Evidence Law satisfied")
        self.assertIn("Deterministic", signals["evidence_badges"])
        self.assertIn("External", signals["evidence_badges"])

    def test_finding_row_signals_flag_severe_findings_without_deterministic_evidence(
        self,
    ) -> None:
        signals = finding_row_signals(
            {
                "finding_id": "finding-002",
                "severity": "high",
                "category": "",
                "deterministic": False,
                "evidence_refs": ["ev-heuristic"],
            },
            [
                {
                    "evidence_id": "ev-heuristic",
                    "source_type": "heuristic",
                    "deterministic": False,
                    "determinism_level": "heuristic",
                },
            ],
        )

        self.assertEqual(signals["category"], "uncategorized")
        self.assertEqual(signals["evidence_count_label"], "1 evidence item")
        self.assertEqual(signals["evidence_law_label"], "Evidence Law needs evidence")
        self.assertIn("Derived", signals["evidence_badges"])


if __name__ == "__main__":
    unittest.main()
