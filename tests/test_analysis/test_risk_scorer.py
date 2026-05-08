"""Tests for unified risk scoring."""

from __future__ import annotations

import json
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

    def test_noop_changes_do_not_score_as_modifications(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="no-op",
                    summary="Terraform resource aws_security_group.main has no planned changes.",
                )
            ]
        )

        self.assertEqual(assessment.score, 0)
        self.assertEqual(assessment.severity, "low")
        self.assertEqual(assessment.recommendation, "go")
        self.assertEqual(assessment.contributors[0].normalized_action, "no-op")

    def test_noop_changes_keep_no_planned_change_blast_radius_with_topology(
        self,
    ) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="no-op",
                    summary="Terraform resource aws_security_group.main has no planned changes.",
                )
            ],
            topology={
                "services": [
                    {
                        "id": "api",
                        "resource_keys": ["aws_security_group.main"],
                        "downstream": ["worker"],
                    },
                    {"id": "worker", "resource_keys": [], "downstream": []},
                ]
            },
        )

        contributor = assessment.contributors[0]
        self.assertEqual(assessment.score, 0)
        self.assertEqual(contributor.downstream_scope, 2)
        self.assertEqual(contributor.blast_radius, "no planned change")
        self.assertNotIn("may affect", contributor.reasoning)

    def test_replacement_actions_are_not_normalized_as_destroy_only(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_instance.web",
                    action="delete+create",
                    summary="Terraform resource aws_instance.web marked for delete+create.",
                    metadata={"replace_paths": ["ami"]},
                )
            ]
        )

        contributor = assessment.contributors[0]
        self.assertEqual(contributor.normalized_action, "replace")
        self.assertEqual(contributor.severity, "high")
        self.assertEqual(assessment.recommendation, "no-go")
        self.assertEqual(contributor.metadata["replace_paths"], ["ami"])

    def test_mixed_destructive_actions_normalize_as_destroy(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_instance.web",
                    action="modify+delete",
                    summary="Terraform resource aws_instance.web marked for destroy.",
                )
            ]
        )

        self.assertEqual(assessment.contributors[0].normalized_action, "destroy")

    def test_non_mutating_changes_ignore_raw_file_security_flags(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="no-op",
                    summary="Terraform resource aws_security_group.main has no planned changes.",
                )
            ],
            raw_files={"plan.json": b'protocol -1 cidr_blocks = ["0.0.0.0/0"]'},
        )

        contributor = assessment.contributors[0]
        self.assertEqual(assessment.score, 0)
        self.assertEqual(assessment.severity, "low")
        self.assertEqual(assessment.recommendation, "go")
        self.assertEqual(contributor.security_flags, [])

    def test_mixed_non_mutating_and_mutating_actions_do_not_downgrade(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_instance.deleted",
                    action="read+delete",
                    summary="Terraform resource aws_instance.deleted marked for destroy.",
                ),
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_instance.updated",
                    action="no-op+update",
                    summary="Terraform resource aws_instance.updated marked for modify.",
                ),
            ]
        )

        by_resource = {
            contributor.resource_id: contributor.normalized_action
            for contributor in assessment.contributors
        }
        self.assertEqual(by_resource["aws_instance.deleted"], "destroy")
        self.assertEqual(by_resource["aws_instance.updated"], "modify")

    def test_read_only_changes_do_not_score_as_modifications(self) -> None:
        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="data.aws_ami.latest",
                    action="read",
                    summary="Terraform resource data.aws_ami.latest marked for read.",
                    metadata={"mode": "data"},
                )
            ]
        )

        contributor = assessment.contributors[0]
        self.assertEqual(assessment.score, 0)
        self.assertEqual(assessment.severity, "low")
        self.assertEqual(contributor.normalized_action, "read")
        self.assertEqual(
            contributor.blast_radius,
            "read-only lookup; no infrastructure mutation planned",
        )

    def test_llm_scoring_keeps_non_mutating_changes_at_zero(self) -> None:
        def fake_completion(**_: object) -> str:
            self.fail("Non-mutating changes should not invoke LLM scoring.")
            return json.dumps(
                {
                    "overall_severity": "medium",
                    "recommendation": "go",
                    "top_risk": "LLM attempted to score the no-op change.",
                    "overall_reasoning": "No-op entry should remain deterministic.",
                    "change_scores": [
                        {
                            "source_file": "plan.json",
                            "resource_id": "aws_security_group.main",
                            "severity": "medium",
                            "reasoning": "LLM marked this as medium risk.",
                        }
                    ],
                }
            )

        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="no-op",
                    summary="Terraform resource aws_security_group.main has no planned changes.",
                )
            ],
            completion_client=fake_completion,
        )

        self.assertEqual(assessment.source, "heuristic-only")
        self.assertEqual(assessment.score, 0)
        self.assertEqual(assessment.severity, "low")
        self.assertEqual(assessment.recommendation, "go")
        self.assertEqual(assessment.contributors[0].contribution, 0)
        self.assertEqual(assessment.contributors[0].severity, "low")
        self.assertNotIn("medium risk", assessment.contributors[0].reasoning)
        self.assertNotIn("medium risk", assessment.top_risk)

    def test_non_mutating_llm_failure_does_not_emit_provider_warning(self) -> None:
        def failing_completion(**_: object) -> str:
            raise RuntimeError("provider unavailable")

        assessment = score_changes(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="data.aws_ami.latest",
                    action="read",
                    summary="Terraform resource data.aws_ami.latest is read-only.",
                )
            ],
            completion_client=failing_completion,
        )

        self.assertEqual(assessment.source, "heuristic-only")
        self.assertEqual(assessment.score, 0)
        self.assertEqual(assessment.warnings, [])

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

    def test_preproduction_storage_manifest_scores_low_go_without_fake_scope(
        self,
    ) -> None:
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
