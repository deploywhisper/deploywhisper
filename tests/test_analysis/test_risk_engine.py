"""Tests for evidence-first risk scoring."""

from __future__ import annotations

import unittest

from analysis.risk_engine import score_evidence
from evidence.models import EvidenceItem


class RiskEngineTests(unittest.TestCase):
    def _item(
        self,
        *,
        evidence_id: str,
        source_ref: str,
        summary: str,
        severity_hint: str,
        confidence: float = 1.0,
        related_change_ids: list[str] | None = None,
    ) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=evidence_id,
            analysis_id=0,
            finding_id=f"pending:{evidence_id}",
            source_type="artifact",
            source_ref=source_ref,
            summary=summary,
            severity_hint=severity_hint,
            deterministic=True,
            confidence=confidence,
            related_change_ids=related_change_ids or [f"chg-{evidence_id}"],
        )

    def test_score_evidence_returns_traceable_top_risk_contributors(self) -> None:
        assessment = score_evidence(
            [
                self._item(
                    evidence_id="ev-high",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.payments?action=destroy"
                    ),
                    summary="Terraform resource aws_security_group.payments marked for destroy.",
                    severity_hint="high",
                ),
                self._item(
                    evidence_id="ev-medium",
                    source_ref=(
                        "kubernetes://deployment.yaml#Deployment/payments?action=modify"
                    ),
                    summary="Kubernetes Deployment payments included in analysis set.",
                    severity_hint="medium",
                ),
            ]
        )

        self.assertEqual(assessment.top_risk_contributors[0], "ev-high")
        self.assertEqual(assessment.contributors[0].evidence_id, "ev-high")
        self.assertEqual(
            assessment.contributors[0].resource_id, "aws_security_group.payments"
        )
        self.assertIn(assessment.recommendation, {"caution", "no-go"})

    def test_disabling_any_single_evidence_item_changes_the_score(self) -> None:
        evidence_items = [
            self._item(
                evidence_id="ev-critical",
                source_ref="terraform://plan.json#aws_db_instance.primary?action=destroy",
                summary="Terraform resource aws_db_instance.primary marked for destroy.",
                severity_hint="critical",
                confidence=1.0,
            ),
            self._item(
                evidence_id="ev-high",
                source_ref=(
                    "cloudformation://stack.yaml#resource/PrimaryDatabase?action=destroy"
                ),
                summary="CloudFormation resource PrimaryDatabase included in analysis set.",
                severity_hint="high",
                confidence=0.9,
            ),
            self._item(
                evidence_id="ev-medium",
                source_ref="jenkins://Jenkinsfile#stage/Deploy?action=modify",
                summary="Jenkins stage Deploy included in analysis set.",
                severity_hint="medium",
                confidence=0.8,
            ),
        ]

        baseline_score = score_evidence(evidence_items).score
        rescored = {
            item.evidence_id: score_evidence(
                [
                    candidate
                    for candidate in evidence_items
                    if candidate.evidence_id != item.evidence_id
                ]
            ).score
            for item in evidence_items
        }

        self.assertTrue(all(score != baseline_score for score in rescored.values()))


if __name__ == "__main__":
    unittest.main()
