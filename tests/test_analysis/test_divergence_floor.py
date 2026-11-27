"""A confirmed divergence floor preserves the existing advisory verdict contract."""

from __future__ import annotations

import unittest

from analysis.risk_scorer import RiskAssessment, apply_divergence_floor


class DivergenceFloorTests(unittest.TestCase):
    def test_no_floor_leaves_assessment_unchanged(self) -> None:
        assessment = RiskAssessment(
            score=18,
            severity="low",
            recommendation="go",
            top_risk="Existing assessment",
            partial_context=False,
        )

        self.assertIs(
            apply_divergence_floor(assessment, requires_caution=False), assessment
        )

    def test_floor_raises_severity_score_and_recommendation_on_a_copy(self) -> None:
        assessment = RiskAssessment(
            score=18,
            severity="low",
            recommendation="go",
            confidence=0.83,
            top_risk="Existing assessment",
            partial_context=False,
            warnings=["Existing warning"],
        )
        original = assessment.model_dump()

        result = apply_divergence_floor(assessment, requires_caution=True)

        self.assertEqual((result.severity, result.score), ("medium", 42))
        self.assertEqual(result.recommendation, "caution")
        self.assertEqual(result.confidence, 0.83)
        self.assertEqual(result.warnings[0], "Existing warning")
        self.assertEqual(len(result.warnings), 2)
        self.assertIn("divergence", result.warnings[1].lower())
        self.assertEqual(assessment.model_dump(), original)

    def test_floor_preserves_a_stronger_assessment_and_is_idempotent(self) -> None:
        assessment = RiskAssessment(
            score=94,
            severity="critical",
            recommendation="no-go",
            top_risk="Existing critical risk",
            partial_context=True,
        )

        result = apply_divergence_floor(assessment, requires_caution=True)

        self.assertEqual((result.severity, result.score), ("critical", 94))
        self.assertEqual(result.recommendation, "no-go")
        self.assertEqual(result.top_risk, "Existing critical risk")
        self.assertTrue(result.partial_context)
        self.assertEqual(
            apply_divergence_floor(result, requires_caution=True).model_dump(),
            result.model_dump(),
        )
