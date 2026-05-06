"""Tests for upload panel state helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ui.components.upload_panel import (
    process_uploaded_files,
    resolve_initial_project_selection,
    should_clear_pending_uploads,
    uploads_allowed,
    run_uploaded_analysis,
)


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
            result = run_uploaded_analysis(files, project_key="payments")

        self.assertIs(result, expected)
        analyze_mock.assert_called_once_with(
            files,
            completion_client=None,
            project_key="payments",
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )

    def test_run_uploaded_analysis_requires_project_scope_before_parsing(self) -> None:
        with (
            patch(
                "services.analysis_service.build_parse_batch",
                side_effect=AssertionError("project must resolve before parsing"),
            ) as build_parse_batch,
            self.assertRaisesRegex(ValueError, "Project scope is required") as exc_info,
        ):
            run_uploaded_analysis([("plan.json", b'{"resource_changes": []}')])

        self.assertEqual(
            getattr(exc_info.exception, "code", ""), "missing_project_scope"
        )
        build_parse_batch.assert_not_called()

    def test_resolve_initial_project_selection_requires_saved_choice(self) -> None:
        project_id, project_key = resolve_initial_project_selection(
            has_saved_selection=False,
            active_project=type(
                "Project", (), {"id": 1, "project_key": "unassigned"}
            )(),
        )

        self.assertIsNone(project_id)
        self.assertIsNone(project_key)

    def test_uploads_allowed_requires_selected_project(self) -> None:
        self.assertFalse(uploads_allowed(None))
        self.assertFalse(uploads_allowed(""))
        self.assertTrue(uploads_allowed("payments"))

    def test_should_clear_pending_uploads_only_when_project_changes_with_files(
        self,
    ) -> None:
        self.assertTrue(
            should_clear_pending_uploads(
                current_file_count=2,
                previous_project_id=1,
                next_project_id=2,
            )
        )
        self.assertFalse(
            should_clear_pending_uploads(
                current_file_count=0,
                previous_project_id=1,
                next_project_id=2,
            )
        )
        self.assertFalse(
            should_clear_pending_uploads(
                current_file_count=2,
                previous_project_id=1,
                next_project_id=1,
            )
        )


if __name__ == "__main__":
    unittest.main()
