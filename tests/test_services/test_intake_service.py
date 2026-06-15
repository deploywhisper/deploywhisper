"""Tests for upload classification and intake validation."""

from __future__ import annotations

import unittest

from services.intake_service import (
    EXTERNAL_ARTIFACT_PREFIX,
    UNSAFE_ARTIFACT_PREFIX,
    build_pending_analysis,
    detect_tool_type,
    is_sensitive_file,
    normalize_artifact_name,
    trusted_artifact_path_binding_is_ambiguous,
    trusted_artifact_path_matches_filename,
    trusted_relative_artifact_path,
    uniquify_artifact_names,
    untrusted_upload_filename,
)
from parsers.base import ParseBatchResult, ParseIssue, ParsedFileResult, UnifiedChange
from services.submission_manifest import build_submission_manifest


class IntakeServiceTests(unittest.TestCase):
    def test_detect_tool_type_for_terraform_plan_json(self) -> None:
        raw = b'{"resource_changes": [{"address": "aws_security_group.main"}]}'
        self.assertEqual(detect_tool_type("plan.json", raw), "terraform")

    def test_detect_tool_type_for_kubernetes_yaml(self) -> None:
        raw = b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"
        self.assertEqual(detect_tool_type("deployment.yaml", raw), "kubernetes")

    def test_kubernetes_manifest_with_resources_block_is_not_misclassified(
        self,
    ) -> None:
        raw = b"""apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: api
          resources:
            requests:
              cpu: '100m'
"""
        self.assertEqual(detect_tool_type("deployment.yaml", raw), "kubernetes")

    def test_detect_tool_type_for_cloudformation_yaml(self) -> None:
        raw = b"AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  Bucket:\n    Type: AWS::S3::Bucket\n"
        self.assertEqual(detect_tool_type("stack.yaml", raw), "cloudformation")

    def test_detect_tool_type_for_cloudformation_yaml_with_intrinsic_tags(self) -> None:
        raw = b"""Resources:
  AppBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub '${AWS::StackName}-app'
Outputs:
  BucketArn:
    Value: !GetAtt AppBucket.Arn
"""
        self.assertEqual(
            detect_tool_type("galaxy-metl-sg-rules.yaml", raw), "cloudformation"
        )

    def test_detect_tool_type_for_jenkinsfile(self) -> None:
        self.assertEqual(
            detect_tool_type("Jenkinsfile", b"pipeline { agent any }"), "jenkins"
        )

    def test_sensitive_file_detection(self) -> None:
        self.assertTrue(is_sensitive_file(".env"))
        self.assertTrue(is_sensitive_file("terraform.tfstate"))
        self.assertFalse(is_sensitive_file("deployment.yaml"))

    def test_pending_analysis_marks_ready_and_sensitive_items(self) -> None:
        pending = build_pending_analysis(
            [
                ("plan.json", b'{"resource_changes": []}'),
                (".env", b"SECRET=1"),
                ("README.txt", b"hello"),
            ]
        )
        self.assertEqual(len(pending.items), 3)
        self.assertEqual(pending.ready_count, 1)
        self.assertEqual(pending.items[0].status, "ready")
        self.assertEqual(pending.items[1].status, "sensitive")
        self.assertEqual(pending.items[2].status, "unsupported")

    def test_uniquify_artifact_names_preserves_same_basename_uploads(self) -> None:
        files = uniquify_artifact_names(
            [
                ("plan.json", b"first"),
                ("plan.json", b"second"),
            ]
        )
        self.assertEqual([name for name, _ in files], ["plan.json", "plan#2.json"])

    def test_uniquify_artifact_names_preserves_safe_relative_paths(self) -> None:
        files = uniquify_artifact_names(
            [
                ("repo/services/payments/plan.json", b"first"),
                ("repo/services/payments/plan.json", b"second"),
                ("../repo/./CODEOWNERS", b"owners"),
                ("repo/../CODEOWNERS", b"root owners"),
            ]
        )

        self.assertEqual(
            [name for name, _ in files],
            [
                "repo/services/payments/plan.json",
                "repo/services/payments/plan#2.json",
                f"{UNSAFE_ARTIFACT_PREFIX}/repo/CODEOWNERS",
                f"{UNSAFE_ARTIFACT_PREFIX}/repo/CODEOWNERS#2",
            ],
        )

    def test_normalize_artifact_name_removes_unsafe_path_segments(self) -> None:
        self.assertEqual(
            normalize_artifact_name("../C:/repo/./services\\plan.json"),
            f"{UNSAFE_ARTIFACT_PREFIX}/repo/services/plan.json",
        )
        self.assertEqual(
            normalize_artifact_name("repo/../CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/repo/CODEOWNERS",
        )
        self.assertEqual(
            normalize_artifact_name(f"{UNSAFE_ARTIFACT_PREFIX}/CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/CODEOWNERS",
        )
        self.assertEqual(
            normalize_artifact_name("/Users/alice/repo/.github/CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/Users/alice/repo/.github/CODEOWNERS",
        )
        self.assertEqual(
            normalize_artifact_name("C:\\Users\\alice\\repo\\.github\\CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/Users/alice/repo/.github/CODEOWNERS",
        )
        self.assertEqual(
            normalize_artifact_name("./C:/Users/alice/repo/.github/CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/Users/alice/repo/.github/CODEOWNERS",
        )
        self.assertEqual(
            normalize_artifact_name("C:repo/services/payments/plan.json"),
            f"{UNSAFE_ARTIFACT_PREFIX}/services/payments/plan.json",
        )
        self.assertEqual(
            normalize_artifact_name("__UNSAFE_PATH__/CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/CODEOWNERS",
        )
        self.assertEqual(
            normalize_artifact_name(f"{EXTERNAL_ARTIFACT_PREFIX}/plan.json"),
            f"{UNSAFE_ARTIFACT_PREFIX}/plan.json",
        )
        self.assertEqual(normalize_artifact_name(""), "artifact.bin")

    def test_trusted_relative_artifact_path_canonicalizes_safe_metadata(
        self,
    ) -> None:
        self.assertEqual(
            trusted_relative_artifact_path("./repo/./services/payments/plan.json"),
            "repo/services/payments/plan.json",
        )

    def test_trusted_relative_artifact_path_rejects_host_and_reserved_metadata(
        self,
    ) -> None:
        unsafe_values = [
            "./C:/Users/alice/repo/.github/CODEOWNERS",
            "C:repo/services/plan.json",
            "repo/C:/services/plan.json",
            f"{UNSAFE_ARTIFACT_PREFIX}/CODEOWNERS",
            f"{EXTERNAL_ARTIFACT_PREFIX}/plan.json",
        ]

        self.assertEqual(
            [trusted_relative_artifact_path(value) for value in unsafe_values],
            [None, None, None, None, None],
        )

    def test_trusted_artifact_path_rejects_traversal_filename_leaf_match(
        self,
    ) -> None:
        self.assertFalse(
            trusted_artifact_path_matches_filename(
                "services/payments/plan.json",
                "../payments/plan.json",
            )
        )

    def test_untrusted_upload_filename_taints_pathlike_codeowners(self) -> None:
        self.assertEqual(
            untrusted_upload_filename(".github/CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/.github/CODEOWNERS",
        )
        self.assertEqual(
            untrusted_upload_filename("repo/docs/CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/repo/docs/CODEOWNERS",
        )
        self.assertEqual(
            untrusted_upload_filename("CODEOWNERS"),
            f"{UNSAFE_ARTIFACT_PREFIX}/CODEOWNERS",
        )
        self.assertEqual(
            untrusted_upload_filename("services/payments/plan.json"),
            f"{UNSAFE_ARTIFACT_PREFIX}/services/payments/plan.json",
        )
        self.assertEqual(
            untrusted_upload_filename("../services/payments/plan.json"),
            f"{UNSAFE_ARTIFACT_PREFIX}/services/payments/plan.json",
        )
        self.assertEqual(
            untrusted_upload_filename("repo/__external_path__/plan.json"),
            f"{UNSAFE_ARTIFACT_PREFIX}/repo/plan.json",
        )

    def test_duplicate_basename_bindings_require_full_path_filename_proof(
        self,
    ) -> None:
        paths = ["services/payments/plan.json", "services/billing/plan.json"]

        self.assertTrue(
            trusted_artifact_path_binding_is_ambiguous(
                paths, ["plan.json", "plan.json"]
            )
        )
        self.assertFalse(trusted_artifact_path_binding_is_ambiguous(paths, paths))
        self.assertTrue(
            trusted_artifact_path_binding_is_ambiguous(
                paths,
                ["services/billing/plan.json", "services/payments/plan.json"],
            )
        )
        self.assertTrue(
            trusted_artifact_path_matches_filename(
                "services/payments/plan.json",
                "services/payments/plan.json",
            )
        )
        self.assertFalse(
            trusted_artifact_path_matches_filename(
                "services/payments/plan.json",
                "services/billing/plan.json",
            )
        )

    def test_pending_analysis_preserves_duplicate_file_names_after_uniquifying(
        self,
    ) -> None:
        pending = build_pending_analysis(
            uniquify_artifact_names(
                [
                    ("plan.json", b'{"resource_changes": []}'),
                    ("plan.json", b'{"resource_changes": []}'),
                ]
            )
        )
        self.assertEqual(len(pending.items), 2)
        self.assertEqual(pending.items[0].name, "plan.json")
        self.assertEqual(pending.items[1].name, "plan#2.json")
        self.assertTrue(all(item.status == "ready" for item in pending.items))

    def test_submission_manifest_records_final_artifact_outcomes(self) -> None:
        files = [
            ("plan.json", b'{"resource_changes": []}'),
            ("broken.tf", b"resource {"),
            (".env", b"SECRET=1"),
            ("notes.txt", b"hello"),
        ]
        pending = build_pending_analysis(files)
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_s3_bucket.logs",
                            action="modify",
                            summary="Terraform resource changed.",
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name="broken.tf",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="broken.tf",
                        tool="terraform",
                        message="Unexpected token",
                    ),
                ),
                ParsedFileResult(
                    file_name="notes.txt",
                    tool="unsupported",
                    status="skipped",
                    issue=ParseIssue(
                        file_name="notes.txt",
                        tool="unsupported",
                        message="Unsupported or unrecognized file excluded from parsing.",
                    ),
                ),
            ]
        )

        manifest = build_submission_manifest(
            files,
            pending_analysis=pending,
            parse_batch=parse_batch,
            audit_context={
                "source_interface": "api",
                "trigger_type": "api_request",
                "trigger_id": "run-123",
            },
        )

        self.assertEqual(manifest.submitted_artifact_count, 4)
        self.assertEqual(manifest.accepted_artifact_count, 2)
        self.assertEqual(manifest.analyzed_artifact_count, 1)
        self.assertEqual(manifest.excluded_artifact_count, 1)
        self.assertEqual(manifest.sensitive_artifact_count, 1)
        self.assertEqual(manifest.failed_artifact_count, 1)
        self.assertEqual(manifest.partial_artifact_count, 3)
        self.assertTrue(manifest.partial_analysis)
        by_name = {item.name: item for item in manifest.items}
        self.assertEqual(by_name["plan.json"].status, "accepted")
        self.assertEqual(
            by_name["plan.json"].message,
            "Terraform artifact parsed successfully and included in analysis.",
        )
        self.assertEqual(by_name["broken.tf"].status, "failed")
        self.assertTrue(by_name["broken.tf"].partial)
        self.assertEqual(
            by_name["broken.tf"].message,
            "Terraform artifact failed parser validation; analysis coverage is partial.",
        )
        self.assertNotIn("Unexpected token", by_name["broken.tf"].message)
        self.assertEqual(by_name[".env"].status, "sensitive")
        self.assertTrue(by_name[".env"].partial)
        self.assertEqual(by_name[".env"].redaction_status, "sensitive_blocked")
        self.assertEqual(by_name["notes.txt"].status, "excluded")
        self.assertTrue(by_name["notes.txt"].partial)
        self.assertEqual(
            by_name["notes.txt"].message,
            "Unsupported file type or unsupported content fingerprint.",
        )
        self.assertEqual(
            by_name["plan.json"].provenance["source_interface"],
            "api",
        )
        self.assertFalse(manifest.redaction["filenames_redacted"])

    def test_submission_manifest_marks_non_analyzed_submissions_partial(self) -> None:
        files = [
            ("plan.json", b'{"resource_changes": []}'),
            (".env", b"SECRET=1"),
            ("notes.txt", b"hello"),
        ]
        pending = build_pending_analysis(files)
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_s3_bucket.logs",
                            action="modify",
                            summary="Terraform resource changed.",
                        )
                    ],
                )
            ]
        )

        manifest = build_submission_manifest(
            files,
            pending_analysis=pending,
            parse_batch=parse_batch,
        )

        by_name = {item.name: item for item in manifest.items}
        self.assertEqual(manifest.partial_artifact_count, 2)
        self.assertTrue(manifest.partial_analysis)
        self.assertFalse(by_name["plan.json"].partial)
        self.assertTrue(by_name[".env"].partial)
        self.assertTrue(by_name["notes.txt"].partial)

    def test_submission_manifest_trusts_parse_batch_for_parsed_artifacts(
        self,
    ) -> None:
        files = [
            (
                "plan.json",
                b'resource "aws_security_group" "main" {\n  name = "web"\n}\n',
            )
        ]
        pending = build_pending_analysis(files)
        parse_batch = ParseBatchResult(
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
                )
            ]
        )

        manifest = build_submission_manifest(
            files,
            pending_analysis=pending,
            parse_batch=parse_batch,
        )

        self.assertEqual(pending.items[0].status, "unsupported")
        self.assertEqual(manifest.accepted_artifact_count, 1)
        self.assertEqual(manifest.excluded_artifact_count, 0)
        self.assertEqual(manifest.items[0].status, "accepted")
        self.assertFalse(manifest.items[0].partial)


if __name__ == "__main__":
    unittest.main()
