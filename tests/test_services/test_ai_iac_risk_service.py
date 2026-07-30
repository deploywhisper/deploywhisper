"""Tests for AI-assisted IaC provenance and risk labels."""

from __future__ import annotations

import unittest

from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import EvidenceItem, Finding
from services.ai_iac_risk_service import (
    assess_iac_provenance,
    label_ai_iac_risk_findings,
)


class AiIacRiskServiceTests(unittest.TestCase):
    def test_assess_iac_provenance_treats_content_marker_as_suggestion(self) -> None:
        provenance = assess_iac_provenance(
            {
                "main.tf": (
                    b"# AI-generated draft; verify before apply\n"
                    b'resource "aws_security_group" "web" {}\n'
                )
            }
        )

        self.assertEqual(provenance["authorship"], "ai-assisted")
        self.assertEqual(provenance["authorship_certainty"], "suggested")
        self.assertIn("content-marker:main.tf", provenance["authorship_signals"])
        self.assertIn("does not establish authorship", provenance["authorship_note"])

    def test_assess_iac_provenance_preserves_declared_human_authorship(self) -> None:
        provenance = assess_iac_provenance(
            {"main.tf": b'resource "aws_s3_bucket" "logs" {}\n'},
            audit_context={"iac_authorship": "human-authored"},
        )

        self.assertEqual(provenance["authorship"], "human-authored")
        self.assertEqual(provenance["authorship_certainty"], "declared")
        self.assertEqual(
            provenance["authorship_signals"],
            ["declared:human-authored"],
        )

    def test_assess_iac_provenance_does_not_treat_transport_as_authorship(
        self,
    ) -> None:
        provenance = assess_iac_provenance(
            {"main.tf": b'resource "aws_s3_bucket" "logs" {}\n'},
            audit_context={
                "source_interface": "agent-api",
                "trigger_type": "agent_request",
            },
        )

        self.assertEqual(provenance["authorship"], "unknown")
        self.assertEqual(provenance["authorship_certainty"], "unknown")
        self.assertEqual(provenance["authorship_signals"], [])

    def test_label_ai_iac_risk_findings_names_deterministic_patterns(self) -> None:
        evidence = EvidenceItem(
            evidence_id="ev-public-ingress",
            analysis_id=0,
            finding_id="pending:chg-public-ingress",
            source_type="artifact",
            source_ref=("terraform://main.tf#aws_security_group.web?action=modify"),
            summary="Security group permits public ingress.",
            severity_hint="high",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["chg-public-ingress"],
        )
        finding = Finding(
            finding_id="finding-public-ingress",
            analysis_id=0,
            title="HIGH: aws_security_group.web",
            description="Security group permits public ingress.",
            severity="high",
            category="networking/ingress",
            deterministic=True,
            confidence=1.0,
            evidence_refs=[evidence.evidence_id],
        )
        contributor = RiskContributor(
            evidence_id=evidence.evidence_id,
            source_file="main.tf",
            tool="terraform",
            resource_id="aws_security_group.web",
            action="modify",
            contribution=72,
            summary="Security group permits public ingress.",
            normalized_action="modify",
            resource_category="networking/ingress",
            blast_radius="Unknown downstream impact.",
            downstream_scope=None,
            security_flags=[
                "Open security group rule detected (protocol -1 / 0.0.0.0/0)."
            ],
            environment="unknown",
            severity="high",
            reasoning="Public ingress requires review.",
        )
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Public ingress requires review.",
            contributors=[contributor],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )

        labeled = label_ai_iac_risk_findings(
            [finding],
            assessment=assessment,
            evidence_items=[evidence],
            provenance_by_artifact={
                "main.tf": {
                    "authorship": "ai-assisted",
                    "authorship_certainty": "suggested",
                    "authorship_signals": ["content-marker:main.tf"],
                    "authorship_note": (
                        "Available signals suggest AI assistance; this does not "
                        "establish authorship."
                    ),
                }
            },
        )

        self.assertEqual(labeled[0].category, "networking/ingress")
        self.assertTrue(labeled[0].title.startswith("AI-assisted IaC risk:"))
        self.assertEqual(labeled[0].severity, "high")
        self.assertTrue(labeled[0].deterministic)
        self.assertEqual(labeled[0].evidence_refs, [evidence.evidence_id])
        self.assertIn("public ingress", labeled[0].description.lower())
        self.assertIn("missing environment scoping", labeled[0].description.lower())
        self.assertIn("does not establish authorship", labeled[0].uncertainty_note)
        self.assertIn(
            "Treat AI-assisted IaC as untrusted input",
            labeled[0].guidance,
        )
        self.assertEqual(
            label_ai_iac_risk_findings(
                labeled,
                assessment=assessment,
                evidence_items=[evidence],
                provenance_by_artifact={
                    "main.tf": {
                        "authorship": "ai-assisted",
                        "authorship_signals": ["content-marker:main.tf"],
                    }
                },
            ),
            labeled,
        )

        conflicting = label_ai_iac_risk_findings(
            [finding],
            assessment=assessment,
            evidence_items=[evidence],
            provenance_by_artifact={
                "main.tf": {
                    "authorship": "unknown",
                    "authorship_certainty": "conflicting",
                    "authorship_signals": [
                        "declared:human-authored",
                        "content-marker:main.tf",
                    ],
                    "authorship_note": "Authorship signals conflict.",
                }
            },
        )
        self.assertTrue(conflicting[0].title.startswith("AI-assisted IaC risk:"))

        fallback_contributor = contributor.model_copy(update={"evidence_id": None})
        fallback_assessment = assessment.model_copy(
            update={"contributors": [fallback_contributor]}
        )
        fallback_labeled = label_ai_iac_risk_findings(
            [finding],
            assessment=fallback_assessment,
            evidence_items=[evidence],
            provenance_by_artifact={
                "main.tf": {
                    "authorship": "ai-assisted",
                    "authorship_signals": ["content-marker:main.tf"],
                }
            },
        )
        self.assertTrue(fallback_labeled[0].title.startswith("AI-assisted IaC risk:"))

        derived_finding = finding.model_copy(
            update={
                "deterministic": False,
                "evidence_classification": "derived",
            }
        )
        derived = label_ai_iac_risk_findings(
            [derived_finding],
            assessment=assessment,
            evidence_items=[evidence],
            provenance_by_artifact={
                "main.tf": {
                    "authorship": "ai-assisted",
                    "authorship_signals": ["content-marker:main.tf"],
                }
            },
        )
        self.assertEqual(derived, [derived_finding])

        unrelated_flag_contributor = contributor.model_copy(
            update={
                "security_flags": ["Feature disabled by policy."],
                "environment": "production",
            }
        )
        unrelated_flag_assessment = assessment.model_copy(
            update={"contributors": [unrelated_flag_contributor]}
        )
        unrelated_flag = label_ai_iac_risk_findings(
            [finding],
            assessment=unrelated_flag_assessment,
            evidence_items=[evidence],
            provenance_by_artifact={
                "main.tf": {
                    "authorship": "ai-assisted",
                    "authorship_signals": ["content-marker:main.tf"],
                }
            },
        )
        self.assertEqual(unrelated_flag, [finding])

    def test_label_ai_iac_risk_findings_requires_deterministic_evidence(self) -> None:
        finding = Finding(
            finding_id="finding-inferred",
            analysis_id=0,
            title="HIGH: inferred risk",
            description="Model-inferred risk.",
            severity="high",
            category="generic infrastructure",
            deterministic=False,
            confidence=0.6,
            evidence_refs=[],
        )
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Inferred risk.",
            contributors=[
                RiskContributor(
                    evidence_id=None,
                    source_file="main.tf",
                    tool="terraform",
                    resource_id="aws_instance.web",
                    action="modify",
                    contribution=72,
                    summary="Inferred risk.",
                    normalized_action="modify",
                    resource_category="generic infrastructure",
                    blast_radius="Unknown downstream impact.",
                    downstream_scope=None,
                    security_flags=[],
                    environment="unknown",
                    severity="high",
                    reasoning="Inferred risk.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )

        labeled = label_ai_iac_risk_findings(
            [finding],
            assessment=assessment,
            evidence_items=[],
            provenance_by_artifact={
                "main.tf": {
                    "authorship": "ai-assisted",
                    "authorship_certainty": "suggested",
                    "authorship_signals": ["content-marker:main.tf"],
                    "authorship_note": (
                        "Available signals suggest AI assistance; this does not "
                        "establish authorship."
                    ),
                }
            },
        )

        self.assertEqual(labeled, [finding])


if __name__ == "__main__":
    unittest.main()
