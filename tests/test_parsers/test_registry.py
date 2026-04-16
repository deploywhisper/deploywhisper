"""Tests for parser registry normalization behavior."""

from __future__ import annotations

import unittest

from parsers.registry import parse_uploaded_files
from services.intake_service import build_parse_batch


class ParserRegistryTests(unittest.TestCase):
    def test_parse_uploaded_files_normalizes_mixed_inputs(self) -> None:
        files = [
            ("plan.json", b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}'),
            ("deployment.yaml", b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"),
            ("Jenkinsfile", b"pipeline { stage('Deploy') { steps { echo 'hi' } } }"),
        ]
        batch = parse_uploaded_files(files)
        self.assertEqual(batch.parsed_count, 3)
        self.assertEqual(batch.failed_count, 0)
        self.assertGreaterEqual(batch.total_change_count, 3)
        self.assertEqual(batch.files[0].changes[0].source_file, "plan.json")

    def test_parse_uploaded_files_isolates_failures(self) -> None:
        files = [
            ("plan.json", b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}'),
            ("empty-plan.json", b'{"resource_changes": []}'),
        ]
        batch = parse_uploaded_files(files)
        self.assertEqual(batch.parsed_count, 1)
        self.assertEqual(batch.failed_count, 1)
        self.assertTrue(batch.has_partial_context)
        self.assertEqual(batch.files[1].status, "failed")
        self.assertEqual(batch.files[1].tool, "terraform")

    def test_parse_uploaded_files_supports_terraform_hcl_configuration(self) -> None:
        batch = parse_uploaded_files(
            [
                (
                    "eks.tf",
                    b'''
resource "aws_security_group" "cluster" {
  name = "cluster"
}

module "network" {
  source = "./modules/network"
}
''',
                )
            ]
        )
        self.assertEqual(batch.parsed_count, 1)
        self.assertEqual(batch.failed_count, 0)
        self.assertEqual(batch.files[0].changes[0].resource_id, "aws_security_group.cluster")
        self.assertIn("network access rules", batch.files[0].changes[0].summary)
        self.assertEqual(batch.files[0].changes[1].resource_id, "module.network")
        self.assertIn("multiple downstream resources", batch.files[0].changes[1].summary)

    def test_parse_uploaded_files_formats_terraform_plan_with_resource_specific_summary(self) -> None:
        batch = parse_uploaded_files(
            [
                (
                    "eks-plan.json",
                    b'{"resource_changes": [{"address": "aws_eks_cluster.platform", "change": {"actions": ["modify"]}}]}',
                )
            ]
        )
        self.assertEqual(batch.parsed_count, 1)
        self.assertIn("cluster or node-group behavior", batch.files[0].changes[0].summary)

    def test_build_parse_batch_skips_sensitive_and_unsupported_files(self) -> None:
        batch = build_parse_batch(
            [
                ("plan.json", b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}'),
                ("deployment.yaml", b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"),
                (".env", b"SECRET=1"),
                ("README.txt", b"hello"),
            ]
        )
        self.assertEqual(batch.parsed_count, 2)
        self.assertEqual(batch.failed_count, 0)
        self.assertEqual(batch.skipped_count, 0)

    def test_parse_uploaded_files_marks_unsupported_as_skipped(self) -> None:
        batch = parse_uploaded_files([("README.txt", b"hello")])
        self.assertEqual(batch.parsed_count, 0)
        self.assertEqual(batch.failed_count, 0)
        self.assertEqual(batch.skipped_count, 1)
        self.assertFalse(batch.has_partial_context)
        self.assertEqual(batch.files[0].status, "skipped")

    def test_parse_uploaded_files_marks_supported_but_empty_result_as_failure(self) -> None:
        batch = parse_uploaded_files([("plan.json", b'{"resource_changes": []}')])
        self.assertEqual(batch.parsed_count, 0)
        self.assertEqual(batch.failed_count, 1)
        self.assertIn("No normalized changes produced", batch.files[0].issue.message)


if __name__ == "__main__":
    unittest.main()
