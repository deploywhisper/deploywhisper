"""Tests for upload panel state helpers."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ui.components.upload_panel import (
    build_feedback_rerender_handler,
    format_submission_manifest_fallback_summary,
    format_submission_manifest_partial_notice,
    format_submission_manifest_summary,
    process_uploaded_files,
    resolve_initial_project_selection,
    should_clear_pending_uploads,
    uploads_allowed,
    run_uploaded_analysis,
)
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange
from ui.components.change_table import (
    format_change_metadata_lines,
    render_change_table,
)


class FakeUiElement:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def classes(self, *_args) -> "FakeUiElement":
        return self


class FakeUi:
    def __init__(self) -> None:
        self.labels: list[str] = []

    def card(self) -> FakeUiElement:
        return FakeUiElement()

    def column(self) -> FakeUiElement:
        return FakeUiElement()

    def row(self) -> FakeUiElement:
        return FakeUiElement()

    def label(self, text: object) -> FakeUiElement:
        self.labels.append(str(text))
        return FakeUiElement()


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

    def test_submission_manifest_summary_surfaces_partial_state(self) -> None:
        manifest = {
            "accepted_artifact_count": 2,
            "analyzed_artifact_count": 1,
            "excluded_artifact_count": 1,
            "failed_artifact_count": 1,
            "sensitive_artifact_count": 1,
            "partial_artifact_count": 1,
            "partial_analysis": True,
        }

        self.assertEqual(
            format_submission_manifest_summary(manifest),
            "Submission manifest: 2 accepted, 1 analyzed, 1 excluded, 1 failed, 1 sensitive, 1 partial",
        )
        self.assertEqual(
            format_submission_manifest_partial_notice(manifest),
            "Partial analysis: 1 submitted artifact reduced analysis coverage.",
        )

    def test_submission_manifest_fallback_summary_surfaces_artifact_statuses(
        self,
    ) -> None:
        self.assertEqual(
            format_submission_manifest_fallback_summary(
                [
                    {"name": "plan.json", "status": "accepted"},
                    {"name": "broken.tf", "status": "failed"},
                    {"name": ".env", "status": "sensitive"},
                ]
            ),
            "Fallback submission artifacts: plan.json (accepted), broken.tf (failed), .env (sensitive)",
        )

    def test_change_metadata_formatter_surfaces_terraform_metadata(self) -> None:
        self.assertEqual(
            format_change_metadata_lines(
                {
                    "module_address": "module.network",
                    "provider_name": "registry.terraform.io/hashicorp/aws",
                    "actions": ["delete", "create"],
                    "unknown_after_apply": ["arn"],
                    "redacted_fields": ["ingress.0.description"],
                    "unsupported_fields": ["plan.planned_values"],
                    "plan_unsupported_fields": ["plan.resource_drift"],
                }
            ),
            [
                "Module: module.network",
                "Provider: registry.terraform.io/hashicorp/aws",
                "Actions: delete, create",
                "Unknown after apply: arn",
                "Redacted fields: ingress.0.description",
                "Unsupported fields: plan.planned_values",
                "Unsupported plan fields: plan.resource_drift",
            ],
        )

    def test_change_metadata_formatter_does_not_truncate_sensitive_field_lists(
        self,
    ) -> None:
        lines = format_change_metadata_lines(
            {
                "redacted_fields": [
                    "field.one",
                    "field.two",
                    "field.three",
                    "field.four",
                    "field.five",
                ],
                "unsupported_fields": [
                    "plan.one",
                    "plan.two",
                    "plan.three",
                    "plan.four",
                    "plan.five",
                ],
            }
        )

        self.assertIn(
            "Redacted fields: field.one, field.two, field.three, field.four, field.five",
            lines,
        )
        self.assertIn(
            "Unsupported fields: plan.one, plan.two, plan.three, plan.four, plan.five",
            lines,
        )
        self.assertNotIn("+1 more", "\n".join(lines))

    def test_feedback_rerender_preserves_parse_batch_metadata_table(self) -> None:
        rendered_labels: list[list[str]] = []
        report = {"id": 1}
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
                            resource_id="module.network.aws_security_group.main",
                            action="modify",
                            summary="Terraform changed an AWS security group.",
                            metadata={
                                "module_address": "module.network",
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        ),
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_instance.unchanged",
                            action="no-op",
                            summary="Terraform has no change for aws_instance.unchanged.",
                        ),
                    ],
                )
            ]
        )
        timer_state = {"remaining": 37}

        def render_result_card(current_report, **kwargs) -> None:
            self.assertEqual(current_report, report)
            self.assertEqual(kwargs["remaining_seconds"], 37)
            fake_ui = FakeUi()
            with patch("ui.components.change_table.ui", fake_ui):
                render_change_table(kwargs["parse_batch"])
            rendered_labels.append(fake_ui.labels)

        rerender = build_feedback_rerender_handler(
            render_result_card,
            report=report,
            parse_batch=parse_batch,
            timer_state=timer_state,
        )
        rerender()

        self.assertEqual(len(rendered_labels), 1)
        labels = rendered_labels[0]
        self.assertIn("Normalized changes", labels)
        self.assertIn("Module: module.network", labels)
        self.assertIn("Unsupported plan fields: plan.planned_values", labels)
        self.assertNotIn(
            "Terraform has no change for aws_instance.unchanged.",
            labels,
        )

    def test_change_table_surfaces_hidden_non_mutating_plan_metadata(self) -> None:
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
                            resource_id="terraform-plan",
                            action="no-op",
                            summary="Terraform plan has no resource changes.",
                            metadata={
                                "plan_format_version": "1.2",
                                "terraform_version": "1.7.5",
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        )
                    ],
                )
            ]
        )
        fake_ui = FakeUi()

        with patch("ui.components.change_table.ui", fake_ui):
            render_change_table(parse_batch)

        self.assertIn("Normalized changes", fake_ui.labels)
        self.assertIn("plan.json: Terraform metadata: 1.2 / 1.7.5", fake_ui.labels)
        self.assertIn(
            "plan.json: Unsupported plan fields: plan.planned_values",
            fake_ui.labels,
        )
        self.assertIn("No mutating normalized changes available.", fake_ui.labels)
        self.assertNotIn("Terraform plan has no resource changes.", fake_ui.labels)

    def test_change_table_surfaces_hidden_non_mutating_metadata_by_file(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan-a.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan-a.json",
                            tool="terraform",
                            resource_id="data.aws_ami.selected",
                            action="read",
                            summary="Read selected AMI.",
                            metadata={
                                "module_address": "module.compute",
                                "provider_name": "registry.terraform.io/hashicorp/aws",
                                "actions": ["read"],
                                "unknown_after_apply": ["id"],
                                "redacted_fields": ["filter.0.values"],
                                "unsupported_fields": ["change.generated_config"],
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name="plan-b.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan-b.json",
                            tool="terraform",
                            resource_id="aws_instance.unchanged",
                            action="no-op",
                            summary="Instance unchanged.",
                            metadata={
                                "provider_name": "registry.terraform.io/hashicorp/aws",
                                "actions": ["no-op"],
                                "plan_unsupported_fields": ["plan.checks"],
                            },
                        )
                    ],
                ),
            ]
        )
        fake_ui = FakeUi()

        with patch("ui.components.change_table.ui", fake_ui):
            render_change_table(parse_batch)

        self.assertIn("plan-a.json: Module: module.compute", fake_ui.labels)
        self.assertIn(
            "plan-a.json: Provider: registry.terraform.io/hashicorp/aws",
            fake_ui.labels,
        )
        self.assertIn("plan-a.json: Actions: read", fake_ui.labels)
        self.assertIn("plan-a.json: Unknown after apply: id", fake_ui.labels)
        self.assertIn("plan-a.json: Redacted fields: filter.0.values", fake_ui.labels)
        self.assertIn(
            "plan-a.json: Unsupported fields: change.generated_config",
            fake_ui.labels,
        )
        self.assertIn(
            "plan-a.json: Unsupported plan fields: plan.planned_values",
            fake_ui.labels,
        )
        self.assertIn("plan-b.json: Actions: no-op", fake_ui.labels)
        self.assertIn(
            "plan-b.json: Unsupported plan fields: plan.checks",
            fake_ui.labels,
        )
        self.assertIn("No mutating normalized changes available.", fake_ui.labels)
        self.assertNotIn("Read selected AMI.", fake_ui.labels)
        self.assertNotIn("Instance unchanged.", fake_ui.labels)


if __name__ == "__main__":
    unittest.main()
