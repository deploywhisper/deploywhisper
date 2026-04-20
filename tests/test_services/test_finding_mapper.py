"""Tests for finding generation and confidence mapping."""

from __future__ import annotations

import unittest

from analysis.interaction_risk import InteractionRisk
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.mappers import (
    INFERRED_CONFIDENCE_FLOOR,
    build_findings,
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
                    contributing_resources=["aws_security_group.main"],
                    contribution_bonus=12,
                )
            ],
            partial_context=False,
            warnings=[],
        )

        findings = build_findings(
            assessment=assessment,
            evidence_items=[evidence],
        )

        self.assertEqual(findings[0].confidence, 1.0)
        self.assertTrue(findings[0].deterministic)
        self.assertEqual(findings[0].evidence_refs, ["ev-001"])
        self.assertEqual(findings[1].confidence, INFERRED_CONFIDENCE_FLOOR)
        self.assertFalse(findings[1].deterministic)


if __name__ == "__main__":
    unittest.main()
