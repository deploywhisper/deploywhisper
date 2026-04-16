"""Tests for upload classification and intake validation."""

from __future__ import annotations

import unittest

from services.intake_service import build_pending_analysis, detect_tool_type, is_sensitive_file


class IntakeServiceTests(unittest.TestCase):
    def test_detect_tool_type_for_terraform_plan_json(self) -> None:
        raw = b'{"resource_changes": [{"address": "aws_security_group.main"}]}'
        self.assertEqual(detect_tool_type("plan.json", raw), "terraform")

    def test_detect_tool_type_for_kubernetes_yaml(self) -> None:
        raw = b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"
        self.assertEqual(detect_tool_type("deployment.yaml", raw), "kubernetes")

    def test_kubernetes_manifest_with_resources_block_is_not_misclassified(self) -> None:
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
        self.assertEqual(detect_tool_type("galaxy-metl-sg-rules.yaml", raw), "cloudformation")

    def test_detect_tool_type_for_jenkinsfile(self) -> None:
        self.assertEqual(detect_tool_type("Jenkinsfile", b"pipeline { agent any }"), "jenkins")

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

    def test_pending_analysis_replaces_duplicate_file_names_with_latest_upload(self) -> None:
        pending = build_pending_analysis(
            [
                ("plan.json", b"not-json"),
                ("plan.json", b'{"resource_changes": []}'),
            ]
        )
        self.assertEqual(len(pending.items), 1)
        self.assertEqual(pending.items[0].tool, "terraform")
        self.assertEqual(pending.items[0].status, "ready")


if __name__ == "__main__":
    unittest.main()
