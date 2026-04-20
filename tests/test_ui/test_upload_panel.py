"""Tests for upload panel state helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ui.components.upload_panel import process_uploaded_files, run_uploaded_analysis


class UploadPanelTests(unittest.TestCase):
    def test_process_uploaded_files_marks_supported_inputs_ready(self) -> None:
        current_files: list[tuple[str, bytes]] = []

        summary = process_uploaded_files(
            current_files,
            [
                (
                    "etcd-pvc-new.yaml",
                    b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: etcd\n",
                )
            ],
        )

        self.assertEqual(summary.ready_count, 1)
        self.assertEqual(summary.items[0].status, "ready")
        self.assertEqual(current_files[0][0], "etcd-pvc-new.yaml")

    def test_run_uploaded_analysis_uses_shared_pipeline_with_dashboard_audit_context(
        self,
    ) -> None:
        files = [("plan.json", b"{}")]
        expected = object()

        with patch(
            "ui.components.upload_panel.analyze_uploaded_files",
            return_value=expected,
        ) as analyze_mock:
            result = run_uploaded_analysis(files)

        self.assertIs(result, expected)
        analyze_mock.assert_called_once_with(
            files,
            completion_client=None,
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )


if __name__ == "__main__":
    unittest.main()
