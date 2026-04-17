"""Tests for unified risk scoring."""

from __future__ import annotations

import unittest

from analysis.risk_scorer import score_changes, score_parse_batch
from parsers.base import ParseBatchResult, ParsedFileResult, ParseIssue, UnifiedChange


class RiskScorerTests(unittest.TestCase):
    def test_score_changes_returns_explainable_contributors(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.payments",
                    action="destroy",
                    summary="Terraform resource aws_security_group.payments marked for destroy.",
                ),
                UnifiedChange(
                    source_file="deployment.yaml",
                    tool="kubernetes",
                    resource_id="Deployment/payments",
                    action="modify",
                    summary="Kubernetes Deployment payments included in analysis set.",
                ),
            ]
        )
        self.assertIn(assessment.severity, {"high", "critical"})
        self.assertEqual(assessment.recommendation, "no-go")
        self.assertEqual(len(assessment.contributors), 2)
        self.assertEqual(assessment.contributors[0].source_file, "plan.json")
        self.assertTrue(assessment.interaction_risks)
        self.assertEqual(assessment.top_risk, assessment.interaction_risks[0].summary)
        self.assertTrue(assessment.contributors[0].reasoning)

    def test_many_small_changes_do_not_escalate_to_critical(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file=f"file-{index}.yaml",
                    tool="kubernetes",
                    resource_id=f"Deployment/api-{index}",
                    action="modify",
                    summary=f"Kubernetes Deployment api-{index} included in analysis set.",
                )
                for index in range(1, 7)
            ]
        )
        self.assertLessEqual(assessment.score, 60)
        self.assertIn(assessment.severity, {"medium", "low"})
        self.assertEqual(assessment.recommendation, "go")

    def test_high_impact_changes_can_reach_critical_and_no_go(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_db_instance.primary",
                    action="destroy",
                    summary="Terraform resource aws_db_instance.primary marked for destroy.",
                ),
                UnifiedChange(
                    source_file="stack.yaml",
                    tool="cloudformation",
                    resource_id="resource/PrimaryDatabase",
                    action="destroy",
                    summary="CloudFormation resource PrimaryDatabase included in analysis set.",
                ),
                UnifiedChange(
                    source_file="Jenkinsfile",
                    tool="jenkins",
                    resource_id="stage/Deploy",
                    action="destroy",
                    summary="Jenkins stage Deploy included in analysis set.",
                ),
            ]
        )
        self.assertEqual(assessment.severity, "critical")
        self.assertEqual(assessment.recommendation, "no-go")

    def test_score_caps_at_100(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file=f"file-{index}.json",
                    tool="terraform",
                    resource_id=f"resource-{index}",
                    action="destroy",
                    summary=f"Terraform resource resource-{index} marked for destroy.",
                )
                for index in range(10)
            ]
        )
        self.assertEqual(assessment.score, 100)

    def test_score_parse_batch_preserves_partial_context_warning(self) -> None:
        batch = ParseBatchResult(
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
                            summary="Terraform resource aws_security_group.main marked for modify.",
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name="broken.json",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="broken.json",
                        tool="terraform",
                        message="Invalid JSON payload",
                    ),
                ),
            ]
        )
        assessment = score_parse_batch(batch)
        self.assertTrue(assessment.partial_context)
        self.assertTrue(assessment.warnings)
        self.assertGreaterEqual(assessment.score, 17)

    def test_score_changes_detects_security_findings_from_raw_content(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    summary="Security group update",
                )
            ],
            raw_files={
                "plan.json": b"""
resource_changes:
  - address: aws_security_group.main
protocol = "-1"
from_port = 0
to_port = 0
cidr_blocks = ["0.0.0.0/0"]
"""
            },
        )

        self.assertEqual(assessment.recommendation, "no-go")
        self.assertTrue(assessment.contributors[0].security_flags)

    def test_preproduction_storage_manifest_scores_low_go_without_fake_scope(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="etcd-sc-backup.yaml",
                    tool="kubernetes",
                    resource_id="StorageClass/apisix-api-gateway-preproduction-green-efs",
                    action="apply",
                    summary=(
                        "Kubernetes StorageClass apisix-api-gateway-preproduction-green-efs supplied as a standalone "
                        "manifest; previous cluster state is unknown, so the delta cannot be confirmed."
                    ),
                )
            ],
            raw_files={
                "etcd-sc-backup.yaml": b"""
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: apisix-api-gateway-preproduction-green-efs
  namespace: apisix-preproduction
provisioner: efs.csi.aws.com
"""
            },
        )

        contributor = assessment.contributors[0]
        self.assertEqual(contributor.environment, "preproduction")
        self.assertEqual(contributor.resource_category, "storage")
        self.assertEqual(contributor.normalized_action, "apply")
        self.assertIsNone(contributor.downstream_scope)
        self.assertIn("unknown downstream impact", contributor.blast_radius)
        self.assertEqual(assessment.severity, "low")
        self.assertEqual(assessment.recommendation, "go")


if __name__ == "__main__":
    unittest.main()
