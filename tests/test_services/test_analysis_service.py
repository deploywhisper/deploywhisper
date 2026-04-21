"""Tests for shared analysis-service helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from analysis.interaction_risk import InteractionRisk
from analysis.risk_scorer import RiskAssessment, RiskContributor
from analysis.blast_radius import BlastRadiusResult
from analysis.rollback_planner import RollbackPlan
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange
from services.analysis_service import (
    build_advisory_summary,
    build_analysis_artifacts,
    build_share_summary,
)


class AnalysisServiceTests(unittest.TestCase):
    def _share_report_payload(self) -> dict:
        return {
            "id": 17,
            "severity": "medium",
            "recommendation": "caution",
            "top_risk": "Terraform changed a security group.",
            "narrative_opening": "CAUTION: review the security group update.",
            "narrative_available": True,
            "warnings": [],
            "findings": [
                {
                    "finding_id": "finding-001",
                    "title": "CRITICAL: aws_security_group.main",
                    "severity": "critical",
                    "confidence": 1.0,
                    "evidence_refs": ["ev-001", "ev-002"],
                },
                {
                    "finding_id": "finding-002",
                    "title": "HIGH: Deployment/api",
                    "severity": "high",
                    "confidence": 0.88,
                    "evidence_refs": ["ev-003"],
                },
                {
                    "finding_id": "finding-003",
                    "title": "MEDIUM: Jenkinsfile",
                    "severity": "medium",
                    "confidence": 0.72,
                    "evidence_refs": ["ev-004"],
                },
                {
                    "finding_id": "finding-004",
                    "title": "LOW: extra detail",
                    "severity": "low",
                    "confidence": 0.55,
                    "evidence_refs": ["ev-005"],
                },
            ],
            "evidence_items": [
                {"finding_id": "finding-001"},
                {"finding_id": "finding-001"},
                {"finding_id": "finding-002"},
                {"finding_id": "finding-003"},
                {"finding_id": "finding-004"},
            ],
            "blast_radius": {
                "affected": [
                    {"label": "Primary Database"},
                    {"label": "API Service"},
                ],
                "direct_count": 1,
                "transitive_count": 1,
                "warning": None,
            },
            "rollback_plan": {
                "steps": [
                    {
                        "title": "Revert aws_security_group.main",
                    }
                ],
                "complexity": "medium",
                "complexity_score": 3,
                "warning": None,
            },
            "context_completeness": {
                "context_score": 0.84,
            },
        }

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
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at=None),
            ),
            patch(
                "services.analysis_service.load_incident_candidates",
                return_value=[],
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ) as evaluate_mock,
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
        passed_evidence_items = evaluate_mock.call_args.kwargs["evidence_items"]
        self.assertEqual(len(passed_evidence_items), 1)
        self.assertEqual(
            passed_evidence_items[0].evidence_id,
            artifacts.evidence_items[0].evidence_id,
        )
        self.assertEqual(artifacts.evidence_items[0].source_type, "artifact")
        self.assertEqual(artifacts.evidence_items[0].severity_hint, "high")
        self.assertEqual(
            artifacts.evidence_items[0].related_change_ids,
            [artifacts.parse_batch.files[0].changes[0].change_id],
        )
        self.assertEqual(len(artifacts.findings), 1)
        self.assertEqual(artifacts.findings[0].confidence, 1.0)
        self.assertAlmostEqual(
            artifacts.assessment.context_completeness.context_score,
            0.45,
        )
        self.assertEqual(
            artifacts.assessment.context_completeness.parser_success_by_tool,
            {"terraform": 1.0},
        )

    def test_build_analysis_artifacts_tracks_topology_timestamp_and_tool_success_rates(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Mixed parser context needs review.",
            contributors=[],
            interaction_risks=[],
            partial_context=True,
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
            opening_sentence="CAUTION: review parser coverage.",
            explanation="Some artifacts could not be parsed cleanly.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.build_parse_batch",
                return_value=ParseBatchResult(
                    files=[
                        ParsedFileResult(
                            file_name="plan.json",
                            tool="terraform",
                            status="parsed",
                            changes=[
                                UnifiedChange(
                                    source_file="plan.json",
                                    tool="terraform",
                                    resource_id="aws_security_group.main",
                                    action="modify",
                                    summary="Terraform changed a security group.",
                                )
                            ],
                        ),
                        ParsedFileResult(
                            file_name="deployment.yaml",
                            tool="kubernetes",
                            status="failed",
                            changes=[],
                        ),
                    ]
                ),
            ),
            patch(
                "services.analysis_service.extract_batch_evidence",
                return_value=[],
            ),
            patch(
                "services.analysis_service.load_topology",
                return_value=({}, None),
            ),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-04-18T11:22:33Z"),
            ),
            patch(
                "services.analysis_service.load_incident_candidates",
                return_value=[{"id": 1}, {"id": 2}],
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
                    ("plan.json", b"{}"),
                    ("deployment.yaml", b"invalid"),
                ]
            )

        self.assertEqual(
            artifacts.assessment.context_completeness.topology_last_imported_at,
            "2026-04-18T11:22:33Z",
        )
        self.assertEqual(
            artifacts.assessment.context_completeness.parser_success_by_tool,
            {"kubernetes": 0.0, "terraform": 1.0},
        )

    def test_build_analysis_artifacts_builds_inferred_interaction_finding(self) -> None:
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Terraform and Kubernetes changes overlap.",
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Terraform changed a security group.",
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
            source="heuristic+llm",
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
            opening_sentence="NO-GO: review the overlapping change set.",
            explanation="The deployment changes overlap.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-04-18T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.load_incident_candidates",
                return_value=[{"id": 1}, {"id": 2}, {"id": 3}],
            ),
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_completion_with_settings",
                return_value='{"confidences":[{"key":"terraform-kubernetes","confidence":0.73}]}',
            ),
            patch(
                "services.analysis_service.compute_blast_radius",
                return_value=blast_radius,
            ),
            patch(
                "services.analysis_service.generate_rollback_plan",
                return_value=rollback_plan,
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
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

        self.assertEqual(len(artifacts.findings), 2)
        inferred = artifacts.findings[1]
        self.assertFalse(inferred.deterministic)
        self.assertAlmostEqual(inferred.confidence, 0.73)
        self.assertGreater(artifacts.assessment.context_completeness.context_score, 0.7)

    def test_build_analysis_artifacts_reduces_context_score_for_stale_topology(
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
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2025-01-01T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.load_incident_candidates",
                return_value=[],
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
            patch("services.analysis_service.find_incident_matches", return_value=[]),
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

        self.assertGreater(
            artifacts.assessment.context_completeness.topology_freshness_days, 30
        )
        self.assertLess(artifacts.assessment.context_completeness.context_score, 0.7)

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

    def test_build_advisory_summary_requires_attention_for_low_context_completeness(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=18,
            severity="low",
            recommendation="go",
            top_risk="Low risk example",
            contributors=[],
            interaction_risks=[],
            context_completeness={
                "topology_freshness_days": 45,
                "incident_index_size": 0,
                "parser_success_rate": 1.0,
                "context_score": 0.52,
            },
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk example.",
            explanation="All good.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        advisory = build_advisory_summary(assessment, narrative)

        self.assertTrue(advisory.requires_attention)
        self.assertIn("low_context_completeness", advisory.uncertainty_flags)

    def test_build_share_summary_returns_thread_ready_markdown_and_json_payload(
        self,
    ) -> None:
        with patch(
            "services.analysis_service.config_module.settings",
            new=SimpleNamespace(app_base_url="https://deploywhisper.example.com"),
        ):
            summary = build_share_summary(self._share_report_payload())
        self.assertEqual(summary.severity, "medium")
        self.assertEqual(summary.recommendation, "caution")
        self.assertIn("Primary Database", summary.blast_radius_summary)
        self.assertIn("3/5", summary.rollback_summary)
        self.assertIn("Advisory only", summary.markdown)
        self.assertIn("Advisory only", summary.plain_text)
        self.assertFalse(summary.should_block)
        self.assertLessEqual(len(summary.markdown), 1500)
        self.assertEqual(summary.json_payload.report_id, 17)
        self.assertEqual(len(summary.json_payload.top_findings), 3)
        self.assertEqual(summary.json_payload.evidence_count, 5)
        self.assertEqual(
            summary.json_payload.rollback_link,
            "https://deploywhisper.example.com/history?report_id=17",
        )
        self.assertEqual(
            summary.json_payload.context_completeness.label, "STRONG CONTEXT"
        )

    def test_build_share_summary_falls_back_to_deterministic_headline_without_narrative(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["narrative_opening"] = ""
        report["narrative_available"] = False
        report["warnings"] = ["Narrative provider unavailable: provider offline"]
        report["context_completeness"] = {"context_score": 0.52}
        summary = build_share_summary(report)

        self.assertEqual(
            summary.headline, "CAUTION: Terraform changed a security group."
        )
        self.assertIn("CAUTION: Terraform changed a security group.", summary.markdown)
        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )

    def test_build_share_summary_requires_attention_for_partial_context_signal(
        self,
    ) -> None:
        report = self._share_report_payload()
        report["warnings"] = [
            "Analysis used partial context because one or more files failed to parse."
        ]
        summary = build_share_summary(report)

        self.assertIn(
            "requires additional human review",
            summary.uncertainty_summary.lower(),
        )
        self.assertIn("requires additional human review", summary.plain_text.lower())
        self.assertEqual(
            summary.json_payload.context_completeness.label, "LIMITED CONTEXT"
        )

    def test_build_share_summary_falls_back_to_local_report_link_without_public_base_url(
        self,
    ) -> None:
        summary = build_share_summary(self._share_report_payload())

        self.assertEqual(
            summary.json_payload.report_link,
            "http://127.0.0.1:8080/history?report_id=17",
        )
        self.assertEqual(
            summary.json_payload.rollback_link,
            "http://127.0.0.1:8080/history?report_id=17",
        )
        self.assertIn(
            "[View rollback plan](http://127.0.0.1:8080/history?report_id=17)",
            summary.markdown,
        )

    def test_build_analysis_artifacts_shields_scored_assessment_from_narrator_mutation(
        self,
    ) -> None:
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

        def mutating_narrator(
            passed_assessment, passed_findings, completion_client=None, raw_files=None
        ):
            passed_assessment.score = 1
            passed_assessment.severity = "low"
            passed_findings[0].confidence = 0.1
            return NarrativeResult(
                opening_sentence="NO-GO: review the security group update.",
                explanation="The deployment widens database access and should be reviewed.",
                guidance=[],
                degraded=False,
                warnings=[],
            )

        with (
            patch("services.analysis_service.load_topology", return_value=({}, None)),
            patch(
                "services.analysis_service.get_topology_status",
                return_value=SimpleNamespace(updated_at="2026-04-18T00:00:00Z"),
            ),
            patch(
                "services.analysis_service.load_incident_candidates",
                return_value=[],
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
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch(
                "services.analysis_service.generate_narrative",
                side_effect=mutating_narrator,
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

        self.assertEqual(artifacts.assessment.score, 72)
        self.assertEqual(artifacts.assessment.severity, "high")
        self.assertEqual(artifacts.findings[0].confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
