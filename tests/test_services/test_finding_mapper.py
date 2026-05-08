"""Tests for finding generation and confidence mapping."""

from __future__ import annotations

import unittest

from analysis.interaction_risk import InteractionRisk
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.mappers import (
    INFERRED_CONFIDENCE_FLOOR,
    build_findings,
    classify_finding_evidence,
    resolve_finding_confidence,
)
from evidence.models import EvidenceItem


class FindingMapperTests(unittest.TestCase):
    def test_resolve_finding_confidence_defaults_deterministic_findings_to_one(
        self,
    ) -> None:
        self.assertEqual(
            resolve_finding_confidence(deterministic=True, source_confidence=0.22),
            1.0,
        )

    def test_resolve_finding_confidence_uses_stated_or_floor_for_inferred_findings(
        self,
    ) -> None:
        self.assertEqual(
            resolve_finding_confidence(deterministic=False, source_confidence=0.41),
            0.41,
        )
        self.assertEqual(
            resolve_finding_confidence(deterministic=False),
            INFERRED_CONFIDENCE_FLOOR,
        )

    def test_build_findings_creates_deterministic_and_inferred_confidence_values(
        self,
    ) -> None:
        evidence = EvidenceItem(
            evidence_id="ev-001",
            analysis_id=0,
            finding_id="pending:chg-001",
            source_type="artifact",
            source_ref="terraform://plan.json#aws_security_group.main?action=modify",
            summary="Security group exposure risk",
            severity_hint="high",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["chg-001"],
        )
        heuristic_evidence = EvidenceItem(
            evidence_id="ev-002",
            analysis_id=0,
            finding_id="pending:chg-002",
            source_type="heuristic",
            source_ref="kubernetes://deployment.yaml#apps/Deployment/payments?action=modify",
            summary="Deployment overlap risk",
            severity_hint="medium",
            deterministic=False,
            determinism_level="heuristic",
            confidence=0.64,
            related_change_ids=["chg-002"],
        )
        unrelated_prefix_evidence = EvidenceItem(
            evidence_id="ev-unrelated",
            analysis_id=0,
            finding_id="pending:chg-003",
            source_type="artifact",
            source_ref="terraform://plan-extra.json#aws_security_group.main-extra?action=modify",
            summary="Unrelated security group change.",
            severity_hint="medium",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["chg-003"],
        )
        unrelated_same_artifact_evidence = EvidenceItem(
            evidence_id="ev-unrelated-same-artifact",
            analysis_id=0,
            finding_id="pending:chg-004",
            source_type="artifact",
            source_ref="kubernetes://deployment.yaml#apps/Deployment/analytics?action=modify",
            summary="Unrelated deployment change.",
            severity_hint="medium",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["chg-004"],
        )
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Security group exposure risk",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    blast_radius="High blast radius",
                    downstream_scope=2,
                    security_flags=[],
                    environment="production",
                    severity="high",
                    reasoning="Security group changes can affect production ingress.",
                )
            ],
            interaction_risks=[
                InteractionRisk(
                    key="terraform-kubernetes",
                    summary="Terraform and Kubernetes changes overlap around payments.",
                    contributing_files=["plan.json", "deployment.yaml"],
                    contributing_resources=[
                        "aws_security_group.main",
                        "apps/Deployment/payments",
                    ],
                    contribution_bonus=12,
                )
            ],
            partial_context=False,
            warnings=[],
        )

        findings = build_findings(
            assessment=assessment,
            evidence_items=[
                evidence,
                heuristic_evidence,
                unrelated_prefix_evidence,
                unrelated_same_artifact_evidence,
            ],
        )

        self.assertEqual(findings[0].confidence, 1.0)
        self.assertTrue(findings[0].deterministic)
        self.assertEqual(findings[0].evidence_refs, ["ev-001"])
        self.assertEqual(
            findings[0].explanation,
            "Security group changes can affect production ingress.",
        )
        self.assertIn(
            "Review the linked evidence before deployment.",
            findings[0].guidance,
        )
        self.assertEqual(findings[0].evidence_classification, "deterministic")
        self.assertEqual(findings[1].confidence, INFERRED_CONFIDENCE_FLOOR)
        self.assertFalse(findings[1].deterministic)
        self.assertEqual(findings[1].evidence_refs, ["ev-001", "ev-002"])
        self.assertEqual(findings[1].evidence_classification, "deterministic")
        self.assertIn(
            "Review the linked resources together because the combined change may broaden blast radius.",
            findings[1].guidance,
        )

    def test_classify_finding_evidence_distinguishes_supported_evidence_types(
        self,
    ) -> None:
        def evidence_item(
            *,
            source_type: str = "artifact",
            deterministic: bool = True,
            determinism_level: str = "deterministic",
        ) -> EvidenceItem:
            return EvidenceItem(
                evidence_id=f"ev-{source_type}-{determinism_level}",
                analysis_id=0,
                finding_id="pending:chg-001",
                source_type=source_type,
                source_ref=f"{source_type}://input.json#resource?action=modify",
                summary="Evidence summary",
                severity_hint="medium",
                deterministic=deterministic,
                determinism_level=determinism_level,
                confidence=0.8,
                related_change_ids=["chg-001"],
            )

        self.assertEqual(
            classify_finding_evidence([evidence_item()]),
            "deterministic",
        )
        self.assertEqual(
            classify_finding_evidence(
                [
                    evidence_item(
                        deterministic=False,
                        determinism_level="heuristic",
                    )
                ]
            ),
            "derived",
        )
        self.assertEqual(
            classify_finding_evidence(
                [
                    evidence_item(
                        deterministic=False,
                        determinism_level="inferred",
                    )
                ]
            ),
            "model_inferred",
        )
        self.assertEqual(
            classify_finding_evidence([evidence_item(source_type="external_scanner")]),
            "external",
        )
        self.assertEqual(
            classify_finding_evidence([evidence_item(source_type="user_context")]),
            "user_provided",
        )
        self.assertEqual(
            classify_finding_evidence(
                [
                    evidence_item(
                        deterministic=False,
                        determinism_level="inferred",
                    ),
                    evidence_item(),
                ]
            ),
            "deterministic",
        )

    def test_build_findings_marks_missing_evidence_as_model_inferred(self) -> None:
        assessment = RiskAssessment(
            score=0,
            severity="low",
            recommendation="go",
            top_risk="Terraform plan has no resource changes.",
            contributors=[
                RiskContributor(
                    evidence_id=None,
                    source_file="empty-plan.json",
                    tool="terraform",
                    resource_id="terraform-plan",
                    action="no-op",
                    contribution=0,
                    summary="Terraform plan has no resource changes.",
                    normalized_action="no-op",
                    resource_category="generic infrastructure",
                    blast_radius="unknown",
                    downstream_scope=None,
                    security_flags=[],
                    environment="unknown",
                    severity="low",
                    reasoning="No planned changes were detected.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )

        findings = build_findings(assessment=assessment, evidence_items=[])

        self.assertEqual(findings[0].evidence_refs, [])
        self.assertFalse(findings[0].deterministic)
        self.assertEqual(findings[0].evidence_classification, "model_inferred")
        self.assertEqual(findings[0].confidence, INFERRED_CONFIDENCE_FLOOR)

    def test_build_findings_does_not_emit_unresolved_evidence_refs(self) -> None:
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            contributors=[
                RiskContributor(
                    evidence_id="ev-missing",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Security group exposure risk",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    blast_radius="High blast radius",
                    downstream_scope=2,
                    security_flags=[],
                    environment="production",
                    severity="high",
                    reasoning="Security group changes can affect production ingress.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )

        findings = build_findings(assessment=assessment, evidence_items=[])

        self.assertEqual(findings[0].evidence_refs, [])
        self.assertFalse(findings[0].deterministic)
        self.assertEqual(findings[0].evidence_classification, "model_inferred")


if __name__ == "__main__":
    unittest.main()
