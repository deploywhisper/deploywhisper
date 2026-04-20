"""Tests for shared analysis-service helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from analysis.risk_scorer import RiskAssessment, RiskContributor
from analysis.blast_radius import BlastRadiusResult, ImpactNode
from analysis.rollback_planner import RollbackPlan, RollbackStep
from llm.narrator import NarrativeResult
from services.analysis_service import (
    build_advisory_summary,
    build_analysis_artifacts,
    build_share_summary,
)


class AnalysisServiceTests(unittest.TestCase):
    def test_build_analysis_artifacts_extracts_evidence_items(self) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed a security group.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        blast_radius = BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(steps=[], complexity="low", warning=None)
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.load_topology",
                return_value=({}, None),
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch(
                "services.analysis_service.find_incident_matches",
                return_value=[],
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=narrative,
            ),
        ):
            artifacts = build_analysis_artifacts(
                [
                    (
                        "plan.json",
                        b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
                    )
                ]
            )

        self.assertEqual(len(artifacts.evidence_items), 1)
        self.assertEqual(artifacts.evidence_items[0].source_type, "artifact")
        self.assertEqual(artifacts.evidence_items[0].severity_hint, "high")
        self.assertEqual(
            artifacts.evidence_items[0].related_change_ids,
            [artifacts.parse_batch.files[0].changes[0].change_id],
        )

    def test_build_advisory_summary_does_not_require_attention_for_go_with_only_narrative_warnings(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=12,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=False,
            warnings=["Narrative provider warning."],
        )

        advisory = build_advisory_summary(assessment, narrative)

        self.assertFalse(advisory.should_block)
        self.assertFalse(advisory.requires_attention)
        self.assertIn("narrative_warnings", advisory.uncertainty_flags)

    def test_build_advisory_summary_requires_attention_for_partial_or_degraded_results(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=24,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=True,
            warnings=[
                "Analysis used partial context because one or more files failed to parse."
            ],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=True,
            warnings=["Narrative provider unavailable."],
        )

        advisory = build_advisory_summary(assessment, narrative)

        self.assertFalse(advisory.should_block)
        self.assertTrue(advisory.requires_attention)
        self.assertIn("partial_context", advisory.uncertainty_flags)
        self.assertIn("narrative_degraded", advisory.uncertainty_flags)

    def test_build_share_summary_returns_script_friendly_thread_payload(self) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed a security group.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group before deploy."],
            degraded=False,
            warnings=[],
        )
        advisory = build_advisory_summary(assessment, narrative)
        blast_radius = BlastRadiusResult(
            affected=[
                ImpactNode(service_id="database", label="Primary Database", depth=0),
                ImpactNode(service_id="api", label="API Service", depth=1),
            ],
            direct_count=1,
            transitive_count=1,
            warning=None,
            unmatched_resources=[],
        )
        rollback_plan = RollbackPlan(
            steps=[
                RollbackStep(
                    order=1,
                    title="Revert aws_security_group.main",
                    detail="Rollback the terraform change safely.",
                    critical=True,
                )
            ],
            complexity="medium",
            warning=None,
        )

        summary = build_share_summary(
            advisory=advisory,
            narrative=narrative,
            blast_radius=blast_radius,
            rollback_plan=rollback_plan,
        )

        self.assertEqual(summary.severity, "medium")
        self.assertEqual(summary.recommendation, "caution")
        self.assertIn("Primary Database", summary.blast_radius_summary)
        self.assertIn("medium", summary.rollback_summary.lower())
        self.assertIn("Advisory only", summary.markdown)
        self.assertIn("Advisory only", summary.plain_text)
        self.assertFalse(summary.should_block)


if __name__ == "__main__":
    unittest.main()
