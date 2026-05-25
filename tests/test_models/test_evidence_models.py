"""Tests for evidence-domain Pydantic models."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from evidence.models import (
    ContextCompleteness,
    ContextSnapshot,
    EvidenceItem,
    Finding,
    RiskAssessment,
    SkillReference,
)


class EvidenceModelTests(unittest.TestCase):
    def test_context_completeness_constructs_and_serializes(self) -> None:
        completeness = ContextCompleteness(
            topology_freshness_days=3,
            topology_last_imported_at="2026-04-20T12:00:00Z",
            incident_index_size=7,
            evidence_success_rate=0.67,
            parser_success_rate=0.75,
            parser_success_by_tool={"terraform": 1.0, "kubernetes": 0.5},
            context_score=0.8,
            confidence_level="medium",
            uncertainty="Kubernetes parser coverage was partial.",
            context_todos=["Refresh Kubernetes context."],
        )

        self.assertEqual(
            completeness.model_dump(mode="json"),
            {
                "topology_freshness_days": 3,
                "topology_last_imported_at": "2026-04-20T12:00:00Z",
                "incident_index_size": 7,
                "incident_index_version": None,
                "incident_index_last_indexed_at": None,
                "incident_index_freshness_status": None,
                "evidence_success_rate": 0.67,
                "parser_success_rate": 0.75,
                "parser_success_by_tool": {"terraform": 1.0, "kubernetes": 0.5},
                "context_score": 0.8,
                "confidence_level": "medium",
                "uncertainty": "Kubernetes parser coverage was partial.",
                "context_todos": ["Refresh Kubernetes context."],
                "insufficient_context": False,
                "partial_context": False,
            },
        )

    def test_context_completeness_rejects_invalid_context_score(self) -> None:
        with self.assertRaises(ValidationError):
            ContextCompleteness(context_score=1.2)

    def test_context_completeness_rejects_invalid_parser_success_by_tool_values(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            ContextCompleteness(parser_success_by_tool={"terraform": 1.2})

    def test_skill_reference_constructs_and_serializes(self) -> None:
        reference = SkillReference(skill_id="terraform", version="1.0.0")

        self.assertEqual(
            reference.model_dump(mode="json"),
            {"skill_id": "terraform", "version": "1.0.0"},
        )

    def test_skill_reference_rejects_empty_version(self) -> None:
        with self.assertRaises(ValidationError):
            SkillReference(skill_id="terraform", version="")

    def test_evidence_item_constructs_and_serializes(self) -> None:
        item = EvidenceItem(
            evidence_id="ev-001",
            analysis_id=7,
            finding_id="finding-001",
            source_type="artifact",
            source_ref="terraform://plan.json#aws_security_group.main",
            summary="Security group ingress widened",
            severity_hint="high",
            deterministic=True,
            confidence=1.0,
            related_change_ids=["change-1", "change-2"],
        )

        payload = item.model_dump()

        self.assertEqual(payload["analysis_id"], 7)
        self.assertEqual(payload["artifact"], "plan.json")
        self.assertEqual(payload["location"], "plan.json#aws_security_group.main")
        self.assertEqual(payload["resource"], "aws_security_group.main")
        self.assertEqual(payload["source_kind"], "artifact")
        self.assertEqual(payload["determinism_level"], "deterministic")
        self.assertEqual(payload["redaction_status"], "none")
        self.assertEqual(payload["severity_hint"], "high")
        self.assertEqual(payload["related_change_ids"], ["change-1", "change-2"])

    def test_evidence_item_requires_finding_id(self) -> None:
        with self.assertRaises(ValidationError):
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=7,
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main",
                summary="Security group ingress widened",
                severity_hint="high",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-1"],
            )

    def test_finding_constructs_and_serializes(self) -> None:
        finding = Finding(
            finding_id="finding-001",
            analysis_id=7,
            title="Security group exposure",
            description="Ingress allows broad access",
            severity="high",
            category="networking/ingress",
            deterministic=True,
            confidence=0.8,
            evidence_refs=["ev-001"],
        )

        self.assertEqual(finding.model_dump(mode="json")["evidence_refs"], ["ev-001"])
        self.assertEqual(
            finding.model_dump(mode="json")["explanation"],
            "Ingress allows broad access",
        )
        self.assertEqual(finding.model_dump(mode="json")["guidance"], [])
        self.assertEqual(
            finding.model_dump(mode="json")["evidence_classification"],
            "deterministic",
        )

    def test_finding_serializes_explicit_guidance_and_classification(self) -> None:
        finding = Finding(
            finding_id="finding-001",
            analysis_id=7,
            title="Security group exposure",
            description="Ingress allows broad access",
            explanation="Security group ingress allows database access from the internet.",
            guidance=["Restrict ingress before deployment."],
            severity="high",
            category="networking/ingress",
            deterministic=False,
            confidence=0.74,
            evidence_classification="model_inferred",
            evidence_refs=["ev-001"],
        )

        payload = finding.model_dump(mode="json")

        self.assertEqual(
            payload["explanation"],
            "Security group ingress allows database access from the internet.",
        )
        self.assertEqual(payload["guidance"], ["Restrict ingress before deployment."])
        self.assertEqual(payload["evidence_classification"], "model_inferred")

    def test_non_deterministic_finding_preserves_explicit_deterministic_support(
        self,
    ) -> None:
        finding = Finding(
            finding_id="finding-001",
            analysis_id=7,
            title="Interaction risk",
            description="Cross-tool interaction links deterministic evidence.",
            severity="high",
            category="cross-tool interaction",
            deterministic=False,
            confidence=0.55,
            evidence_classification="deterministic",
            evidence_refs=["ev-001"],
        )

        self.assertEqual(finding.evidence_classification, "deterministic")

    def test_non_deterministic_finding_defaults_to_model_inferred_support(
        self,
    ) -> None:
        finding = Finding(
            finding_id="finding-001",
            analysis_id=7,
            title="Interaction risk",
            description="Cross-tool interaction has no linked evidence.",
            severity="medium",
            category="cross-tool interaction",
            deterministic=False,
            confidence=0.55,
            evidence_refs=[],
        )

        self.assertEqual(finding.evidence_classification, "model_inferred")

    def test_finding_rejects_invalid_confidence(self) -> None:
        with self.assertRaises(ValidationError):
            Finding(
                finding_id="finding-001",
                analysis_id=7,
                title="Security group exposure",
                description="Ingress allows broad access",
                severity="high",
                category="networking/ingress",
                deterministic=True,
                confidence=1.1,
                evidence_refs=["ev-001"],
            )

    def test_risk_assessment_serializes_nested_context(self) -> None:
        assessment = RiskAssessment(
            analysis_id=7,
            overall_severity="high",
            recommendation="caution",
            score=72,
            confidence=0.88,
            top_risk_contributors=["ev-001", "ev-002"],
            context_completeness=ContextCompleteness(
                topology_freshness_days=4,
                incident_index_size=12,
                parser_success_rate=0.9,
                context_score=0.85,
            ),
        )

        payload = assessment.model_dump(mode="json")

        self.assertEqual(payload["score"], 72)
        self.assertEqual(payload["context_completeness"]["context_score"], 0.85)
        self.assertEqual(payload["top_risk_contributors"], ["ev-001", "ev-002"])

    def test_risk_assessment_rejects_invalid_score(self) -> None:
        with self.assertRaises(ValidationError):
            RiskAssessment(
                analysis_id=7,
                overall_severity="high",
                recommendation="caution",
                score=101,
                confidence=0.88,
                top_risk_contributors=["ev-001"],
            )

    def test_context_snapshot_serializes_active_skills(self) -> None:
        snapshot = ContextSnapshot(
            analysis_id=7,
            topology_version="2026-04-20",
            incident_index_version="incidents-v1",
            history_window="90d",
            criticality_inputs={"payments-api": "tier-1"},
            owner_mapping_version="owners-v2",
            skills_active=[SkillReference(skill_id="terraform", version="1.0.0")],
        )

        payload = snapshot.model_dump(mode="json")

        self.assertEqual(payload["analysis_id"], 7)
        self.assertEqual(payload["criticality_inputs"]["payments-api"], "tier-1")
        self.assertEqual(payload["skills_active"][0]["skill_id"], "terraform")

    def test_context_snapshot_validates_nested_skill_reference(self) -> None:
        with self.assertRaises(ValidationError):
            ContextSnapshot(
                analysis_id=7,
                skills_active=[{"skill_id": "", "version": "1.0.0"}],
            )


if __name__ == "__main__":
    unittest.main()
