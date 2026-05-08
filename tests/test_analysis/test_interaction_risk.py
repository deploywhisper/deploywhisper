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
                resource_id="aws_security_group.payments",
                action="modify",
                summary="Terraform changed the payments security group.",
            ),
            UnifiedChange(
                source_file="deployment.yaml",
                tool="kubernetes",
                resource_id="Deployment/payments",
                action="modify",
                summary="Kubernetes deployment payments changed.",
            ),
        ]
        findings = detect_interaction_risks(changes)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].key, "terraform-kubernetes")
        self.assertIn("payments", findings[0].summary.lower())

    def test_detect_interaction_risk_requires_shared_context_not_just_tool_mix(
        self,
    ) -> None:
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
                resource_id="Deployment/payments",
                action="modify",
                summary="Kubernetes deployment changed.",
            ),
        ]
        findings = detect_interaction_risks(changes)
        self.assertEqual(findings, [])

    def test_score_changes_uses_interaction_risk_as_top_risk(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.payments",
                    action="modify",
                    summary="Terraform changed the payments security group.",
                ),
                UnifiedChange(
                    source_file="deployment.yaml",
                    tool="kubernetes",
                    resource_id="Deployment/payments",
                    action="modify",
                    summary="Kubernetes deployment payments changed.",
                ),
            ]
        )
        self.assertTrue(assessment.interaction_risks)
        self.assertEqual(assessment.top_risk, assessment.interaction_risks[0].summary)

    def test_detect_interaction_risk_ignores_non_mutating_changes(self) -> None:
        changes = [
            UnifiedChange(
                source_file="plan.json",
                tool="terraform",
                resource_id="aws_security_group.payments",
                action="no-op",
                summary="Terraform payments security group has no planned changes.",
            ),
            UnifiedChange(
                source_file="data.json",
                tool="terraform",
                resource_id="data.aws_ami.payments",
                action="read",
                summary="Terraform data source payments marked for read.",
            ),
            UnifiedChange(
                source_file="deployment.yaml",
                tool="kubernetes",
                resource_id="Deployment/payments",
                action="modify",
                summary="Kubernetes deployment payments changed.",
            ),
        ]

        findings = detect_interaction_risks(changes)

        self.assertEqual(findings, [])

    def test_score_changes_does_not_promote_non_mutating_interaction(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.payments",
                    action="no-op",
                    summary="Terraform payments security group has no planned changes.",
                ),
                UnifiedChange(
                    source_file="deployment.yaml",
                    tool="kubernetes",
                    resource_id="Deployment/payments",
                    action="modify",
                    summary="Kubernetes deployment payments changed.",
                ),
            ]
        )

        self.assertEqual(assessment.interaction_risks, [])
        self.assertNotIn("Terraform and Kubernetes", assessment.top_risk)
