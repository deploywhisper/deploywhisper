"""Tests for cross-tool interaction risk detection."""

from __future__ import annotations

import unittest

from analysis.interaction_risk import detect_interaction_risks
from analysis.risk_scorer import score_changes
from parsers.base import UnifiedChange


class InteractionRiskTests(unittest.TestCase):
    def test_detect_interaction_risk_for_terraform_and_kubernetes(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.main",
                action="modify",
                summary="Terraform changed a security group.",
            ),
            UnifiedChange(
                source_file="deployment.yaml",
                tool="kubernetes",
                resource_id="Deployment/api",
                action="modify",
                summary="Kubernetes deployment changed.",
            ),
        ]
        findings = detect_interaction_risks(changes)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].key, "terraform-kubernetes")

    def test_score_changes_uses_interaction_risk_as_top_risk(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    summary="Terraform changed a security group.",
                ),
                UnifiedChange(
                    source_file="deployment.yaml",
                    tool="kubernetes",
                    resource_id="Deployment/api",
                    action="modify",
                    summary="Kubernetes deployment changed.",
                ),
            ]
        )
        self.assertTrue(assessment.interaction_risks)
        self.assertEqual(assessment.top_risk, assessment.interaction_risks[0].summary)
