"""Tests for upload panel state helpers."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from ui.components.upload_panel import (
    DASHBOARD_UPLOAD_ACCEPT,
    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
    DASHBOARD_UPLOAD_ROUTE_PREFIX,
    app as dashboard_app,
    apply_upload_widget_state,
    build_feedback_rerender_handler,
    configure_dashboard_upload_widget,
    dashboard_upload_field_name_prop,
    dashboard_file_uploads_from_request,
    dashboard_upload_directory_javascript,
    format_analysis_failure,
    persisted_report_reference,
    format_submission_manifest_fallback_summary,
    format_submission_manifest_partial_notice,
    format_submission_manifest_summary,
    process_uploaded_files,
    render_report_incident_matches,
    reset_upload_widgets,
    resolve_initial_project_selection,
    register_dashboard_upload_handler,
    unregister_dashboard_upload_handler,
    should_clear_pending_uploads,
    uploaded_file_artifact_name,
    uploads_allowed,
    run_uploaded_analysis,
)
from services.analysis_service import AnalysisPersistenceError
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


class FakeUploadFile:
    def __init__(self, name: str, **attrs: str) -> None:
        self.name = name
        for key, value in attrs.items():
            setattr(self, key, value)


class FakeUploadWidget:
    def __init__(self) -> None:
        self.props_calls: list[str] = []
        self._props: dict[str, str] = {"url": "/old-upload"}
        self.enabled = True
        self.reset_count = 0

    def props(self, value: str) -> "FakeUploadWidget":
        self.props_calls.append(value)
        return self

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def reset(self) -> None:
        self.reset_count += 1


class FakeDashboardUploadWidget(FakeUploadWidget):
    def __init__(self, client_id: str, widget_id: str) -> None:
        super().__init__()
        self.client = type("Client", (), {"id": client_id})()
        self.id = widget_id
        self.handled_files: list[object] = []

    async def handle_uploads(self, files: list[object]) -> None:
        self.handled_files = files
        return None


class FakeForm:
    def __init__(self, items: list[tuple[str, object]]) -> None:
        self._items = items

    async def __aenter__(self) -> "FakeForm":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def multi_items(self) -> list[tuple[str, object]]:
        return self._items


class FakeRequest:
    def __init__(self, items: list[tuple[str, object]]) -> None:
        self._items = items

    def form(self) -> FakeForm:
        return FakeForm(self._items)


class FakeStarletteUpload:
    def __init__(self, filename: str, content: bytes = b"") -> None:
        self.filename = filename
        self.content_type = "application/octet-stream"
        self._content = content
        self._offset = 0
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._content) - self._offset
        start = self._offset
        self._offset = min(len(self._content), self._offset + size)
        return self._content[start : self._offset]

    async def close(self) -> None:
        self.closed = True


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

    def test_process_uploaded_files_preserves_safe_relative_paths(self) -> None:
        current_files: list[tuple[str, bytes]] = []

        summary = process_uploaded_files(
            current_files,
            [
                (
                    "repo/services/payments/plan.json",
                    b'{"resource_changes": []}',
                )
            ],
        )

        self.assertEqual(summary.ready_count, 1)
        self.assertEqual(current_files[0][0], "repo/services/payments/plan.json")

    def test_uploaded_file_artifact_name_prefers_relative_path_metadata(self) -> None:
        upload = FakeUploadFile(
            "plan.json",
            webkitRelativePath="repo/services/payments/plan.json",
        )

        self.assertEqual(
            uploaded_file_artifact_name(upload),
            "repo/services/payments/plan.json",
        )
        self.assertEqual(
            uploaded_file_artifact_name(FakeUploadFile("plan.json")),
            "plan.json",
        )

    def test_uploaded_file_artifact_name_ignores_untrusted_local_paths(self) -> None:
        upload = FakeUploadFile(
            "plan.json",
            full_path="/Users/alice/private/repo/services/payments/plan.json",
            path="/private/tmp/nicegui-upload/plan.json",
        )

        self.assertEqual(uploaded_file_artifact_name(upload), "plan.json")

    def test_uploaded_file_artifact_name_rejects_unsafe_relative_metadata(
        self,
    ) -> None:
        unsafe_uploads = [
            FakeUploadFile(
                "CODEOWNERS",
                relative_path="/Users/alice/repo/.github/CODEOWNERS",
            ),
            FakeUploadFile(
                "CODEOWNERS",
                webkitRelativePath="C:\\Users\\alice\\repo\\.github\\CODEOWNERS",
            ),
            FakeUploadFile(
                "CODEOWNERS",
                webkit_relative_path="repo/../.github/CODEOWNERS",
            ),
            FakeUploadFile(
                "CODEOWNERS",
                relative_path="__unsafe_path__/CODEOWNERS",
            ),
            FakeUploadFile(
                "CODEOWNERS",
                relative_path="__UNSAFE_PATH__/CODEOWNERS",
            ),
        ]

        self.assertEqual(
            [uploaded_file_artifact_name(upload) for upload in unsafe_uploads],
            [
                "__unsafe_path__/CODEOWNERS",
                "__unsafe_path__/CODEOWNERS",
                "__unsafe_path__/CODEOWNERS",
                "__unsafe_path__/CODEOWNERS",
                "__unsafe_path__/CODEOWNERS",
            ],
        )

    def test_configure_dashboard_upload_widget_sends_browser_relative_paths(
        self,
    ) -> None:
        widget = FakeUploadWidget()

        configure_dashboard_upload_widget(widget, upload_url="/dashboard-upload")

        self.assertEqual(widget._props["url"], "/dashboard-upload")
        props = " ".join(widget.props_calls)
        self.assertNotIn("data-dw-dashboard-directory-upload", props)
        self.assertIn(":form-fields", props)
        self.assertIn(":field-name", props)
        self.assertIn(DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, props)
        self.assertIn("webkitRelativePath", props)
        self.assertEqual(
            dashboard_upload_field_name_prop(),
            ":field-name=\"file => file.webkitRelativePath || file.relativePath || file.name || 'files'\"",
        )
        self.assertIn(f"accept={DASHBOARD_UPLOAD_ACCEPT}", props)

        directory_widget = FakeUploadWidget()
        configure_dashboard_upload_widget(
            directory_widget,
            upload_url="/dashboard-directory-upload",
            enable_directory=True,
        )
        directory_props = " ".join(directory_widget.props_calls)
        self.assertEqual(
            directory_widget._props["url"],
            "/dashboard-directory-upload",
        )
        self.assertIn('data-dw-dashboard-directory-upload="1"', directory_props)
        self.assertIn(f"accept={DASHBOARD_UPLOAD_ACCEPT}", directory_props)

        directory_script = dashboard_upload_directory_javascript()
        self.assertIn("webkitdirectory", directory_script)
        self.assertIn("directory", directory_script)

    def test_dashboard_upload_request_rejects_reordered_artifact_paths(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (
                    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                    "services/payments/plan.json",
                ),
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, ".github/CODEOWNERS"),
                ("files", FakeStarletteUpload("CODEOWNERS")),
                ("files", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata must match uploaded files"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_preserves_duplicate_artifact_path_filenames(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (
                    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                    "services/payments/plan.json",
                ),
                (
                    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                    "services/billing/plan.json",
                ),
                ("services/payments/plan.json", FakeStarletteUpload("plan.json")),
                ("services/billing/plan.json", FakeStarletteUpload("plan.json")),
            ]
        )

        files = asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

        self.assertEqual([file.name for file in files], ["plan.json", "plan.json"])
        self.assertEqual(
            [getattr(file, "relative_path") for file in files],
            ["services/payments/plan.json", "services/billing/plan.json"],
        )

    def test_dashboard_upload_request_rejects_duplicate_basenames_without_path_binding(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (
                    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                    "services/payments/plan.json",
                ),
                (
                    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                    "services/billing/plan.json",
                ),
                ("files", FakeStarletteUpload("plan.json")),
                ("files", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata is ambiguous"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_rejects_codeowners_field_paths_without_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (
                    ".github/CODEOWNERS",
                    FakeStarletteUpload(
                        ".github/CODEOWNERS",
                        content=b"/services/payments/ @payments-sre",
                    ),
                ),
                (
                    "services/payments/plan.json",
                    FakeStarletteUpload(
                        "services/payments/plan.json",
                        content=b'{"resource_changes": []}',
                    ),
                ),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata must match uploaded files"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_does_not_trust_bare_codeowners_without_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (
                    "CODEOWNERS",
                    FakeStarletteUpload(
                        "CODEOWNERS",
                        content=b"/services/payments/ @payments-sre",
                    ),
                ),
                (
                    "plan.json",
                    FakeStarletteUpload(
                        "plan.json",
                        content=b'{"resource_changes": []}',
                    ),
                ),
            ]
        )

        files = asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

        self.assertEqual(
            [file.name for file in files],
            ["__unsafe_path__/CODEOWNERS", "plan.json"],
        )
        self.assertFalse(any(hasattr(file, "relative_path") for file in files))

    def test_dashboard_upload_request_taints_pathlike_upload_filename_without_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (
                    "files",
                    FakeStarletteUpload(
                        "services/payments/plan.json",
                        content=b'{"resource_changes": []}',
                    ),
                ),
            ]
        )

        files = asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

        self.assertEqual(
            [file.name for file in files],
            ["__unsafe_path__/services/payments/plan.json"],
        )
        self.assertFalse(any(hasattr(file, "relative_path") for file in files))

    def test_dashboard_upload_request_does_not_trust_codeowners_basename_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "CODEOWNERS"),
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                (
                    "CODEOWNERS",
                    FakeStarletteUpload(
                        "CODEOWNERS",
                        content=b"/services/payments/ @payments-sre",
                    ),
                ),
                (
                    "plan.json",
                    FakeStarletteUpload(
                        "plan.json",
                        content=b'{"resource_changes": []}',
                    ),
                ),
            ]
        )

        files = asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

        self.assertEqual(
            [file.name for file in files],
            ["__unsafe_path__/CODEOWNERS", "plan.json"],
        )
        self.assertFalse(any(hasattr(file, "relative_path") for file in files))

    def test_dashboard_upload_request_preserves_duplicate_basename_fallback_uploads(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                ("plan.json", FakeStarletteUpload("plan.json")),
                ("plan.json", FakeStarletteUpload("plan.json")),
            ]
        )

        files = asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

        self.assertEqual([file.name for file in files], ["plan.json", "plan.json"])
        self.assertFalse(any(hasattr(file, "relative_path") for file in files))

    def test_dashboard_upload_request_rejects_basename_fallback_with_field_path(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                ("services/payments/plan.json", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "directory path metadata"):
            asyncio.run(  # type: ignore[arg-type]
                dashboard_file_uploads_from_request(
                    request,
                    require_directory_paths=True,
                )
            )

    def test_dashboard_upload_request_rejects_conflicting_basename_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                ("services/payments/plan.json", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata must match uploaded files"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_directory_upload_rejects_duplicate_basename_fallbacks(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                ("plan.json", FakeStarletteUpload("plan.json")),
                ("plan.json", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "directory path metadata"):
            asyncio.run(  # type: ignore[arg-type]
                dashboard_file_uploads_from_request(
                    request,
                    require_directory_paths=True,
                )
            )

    def test_dashboard_upload_request_rejects_duplicate_artifact_paths(
        self,
    ) -> None:
        request = FakeRequest(
            [
                (
                    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                    "services/payments/plan.json",
                ),
                (
                    DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                    "services/payments/plan.json",
                ),
                ("files", FakeStarletteUpload("plan.json")),
                ("files", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata is ambiguous"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_rejects_duplicate_field_paths_without_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                ("services/payments/plan.json", FakeStarletteUpload("plan.json")),
                ("services/payments/plan.json", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata must match uploaded files"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_rejects_mismatched_field_path_without_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                ("services/payments/vars.tfvars", FakeStarletteUpload("plan.json")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata must match uploaded files"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_rejects_mixed_field_path_metadata(
        self,
    ) -> None:
        request = FakeRequest(
            [
                ("services/payments/plan.json", FakeStarletteUpload("plan.json")),
                ("files", FakeStarletteUpload("vars.tfvars")),
            ]
        )

        with self.assertRaisesRegex(ValueError, "metadata must match uploaded files"):
            asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_rejects_oversized_route_payload(
        self,
    ) -> None:
        request = FakeRequest(
            [("files", FakeStarletteUpload("plan.json", b"123456789"))]
        )

        with patch("ui.components.upload_panel.MAX_TOTAL_UPLOAD_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "upload size exceeds"):
                asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_request_rejects_invalid_artifact_paths(
        self,
    ) -> None:
        invalid_values = (
            "/Users/alice/repo/services/payments/plan.json",
            "services/../payments/plan.json",
            "__unsafe_path__/services/payments/plan.json",
            "__external_path__/services/payments/plan.json",
        )

        for artifact_path in invalid_values:
            with self.subTest(artifact_path=artifact_path):
                request = FakeRequest(
                    [
                        (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, artifact_path),
                        ("files", FakeStarletteUpload("plan.json")),
                    ]
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "metadata must match uploaded files",
                ):
                    asyncio.run(dashboard_file_uploads_from_request(request))  # type: ignore[arg-type]

    def test_dashboard_upload_handler_registers_single_stable_route(self) -> None:
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        before_count = sum(
            1
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        first_url = register_dashboard_upload_handler(
            FakeDashboardUploadWidget("client-a", "upload-a"),
            lambda _text: None,
        )
        second_url = register_dashboard_upload_handler(
            FakeDashboardUploadWidget("client-b", "upload-b"),
            lambda _text: None,
        )

        after_count = sum(
            1
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )
        self.assertEqual(after_count, max(before_count, 1))
        self.assertTrue(first_url.startswith(f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/"))
        self.assertTrue(second_url.startswith(f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/"))
        self.assertNotEqual(first_url, second_url)

    def test_dashboard_upload_handler_replaces_stale_widget_keys(self) -> None:
        widget = FakeDashboardUploadWidget("client-random", "upload-random")
        first_url = register_dashboard_upload_handler(widget, lambda _text: None)
        second_url = register_dashboard_upload_handler(widget, lambda _text: None)
        first_key = first_url.rsplit("/", maxsplit=1)[-1]
        second_key = second_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        old_response = asyncio.run(route.endpoint(first_key, FakeRequest([])))  # type: ignore[attr-defined]
        new_response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                second_key,
                FakeRequest([("files", FakeStarletteUpload("plan.json", b"{}"))]),
            )
        )

        self.assertNotEqual(first_url, second_url)
        self.assertNotEqual(first_key, "client-random-upload-random")
        self.assertNotEqual(second_key, "client-random-upload-random")
        self.assertEqual(old_response.status_code, 404)
        self.assertEqual(new_response, {"upload": "success"})
        self.assertEqual([file.name for file in widget.handled_files], ["plan.json"])

    def test_dashboard_upload_handler_replaces_stale_client_widget_set(
        self,
    ) -> None:
        old_file_widget = FakeDashboardUploadWidget("client-rebuild", "upload-old")
        old_directory_widget = FakeDashboardUploadWidget(
            "client-rebuild", "directory-old"
        )
        old_file_url = register_dashboard_upload_handler(
            old_file_widget,
            lambda _text: None,
        )
        old_directory_url = register_dashboard_upload_handler(
            old_directory_widget,
            lambda _text: None,
        )
        new_file_widget = FakeDashboardUploadWidget("client-rebuild", "upload-new")
        new_directory_widget = FakeDashboardUploadWidget(
            "client-rebuild", "directory-new"
        )
        new_file_url = register_dashboard_upload_handler(
            new_file_widget,
            lambda _text: None,
        )
        new_directory_url = register_dashboard_upload_handler(
            new_directory_widget,
            lambda _text: None,
        )
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        old_file_response = asyncio.run(
            route.endpoint(old_file_url.rsplit("/", maxsplit=1)[-1], FakeRequest([]))  # type: ignore[attr-defined]
        )
        old_directory_response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                old_directory_url.rsplit("/", maxsplit=1)[-1],
                FakeRequest([]),
            )
        )
        new_file_response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                new_file_url.rsplit("/", maxsplit=1)[-1],
                FakeRequest([("files", FakeStarletteUpload("plan.json", b"{}"))]),
            )
        )
        new_directory_response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                new_directory_url.rsplit("/", maxsplit=1)[-1],
                FakeRequest([("files", FakeStarletteUpload("values.yaml", b"{}"))]),
            )
        )

        self.assertEqual(old_file_response.status_code, 404)
        self.assertEqual(old_directory_response.status_code, 404)
        self.assertEqual(new_file_response, {"upload": "success"})
        self.assertEqual(new_directory_response, {"upload": "success"})
        self.assertEqual(
            [file.name for file in new_file_widget.handled_files], ["plan.json"]
        )
        self.assertEqual(
            [file.name for file in new_directory_widget.handled_files],
            ["values.yaml"],
        )

    def test_dashboard_upload_handler_unregisters_widget_keys(self) -> None:
        widget = FakeDashboardUploadWidget("client-cleanup", "upload-cleanup")
        upload_url = register_dashboard_upload_handler(widget, lambda _text: None)
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        unregister_dashboard_upload_handler(upload_url)

        response = asyncio.run(route.endpoint(upload_key, FakeRequest([])))  # type: ignore[attr-defined]
        self.assertEqual(response.status_code, 404)

    def test_dashboard_upload_route_rejects_invalid_artifact_path_metadata(
        self,
    ) -> None:
        widget = FakeDashboardUploadWidget("client-route", "upload-route")
        upload_url = register_dashboard_upload_handler(widget, lambda _text: None)
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                upload_key,
                FakeRequest(
                    [
                        (
                            DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD,
                            "/Users/alice/repo/plan.json",
                        ),
                        ("files", FakeStarletteUpload("plan.json")),
                    ]
                ),
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(widget.handled_files, [])

    def test_dashboard_upload_route_rejects_empty_payload(self) -> None:
        widget = FakeDashboardUploadWidget("client-empty", "upload-empty")
        upload_url = register_dashboard_upload_handler(widget, lambda _text: None)
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(route.endpoint(upload_key, FakeRequest([])))  # type: ignore[attr-defined]

        self.assertEqual(response.status_code, 400)
        self.assertEqual(widget.handled_files, [])

    def test_dashboard_upload_route_taints_codeowners_basename_metadata(self) -> None:
        widget = FakeDashboardUploadWidget(
            "client-codeowners-basename",
            "upload-codeowners-basename",
        )
        upload_url = register_dashboard_upload_handler(widget, lambda _text: None)
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                upload_key,
                FakeRequest(
                    [
                        (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "CODEOWNERS"),
                        (
                            "CODEOWNERS",
                            FakeStarletteUpload(
                                "CODEOWNERS",
                                content=b"/services/payments/ @payments-sre",
                            ),
                        ),
                    ]
                ),
            )
        )

        self.assertEqual(response, {"upload": "success"})
        self.assertEqual(
            [file.name for file in widget.handled_files],
            ["__unsafe_path__/CODEOWNERS"],
        )
        self.assertFalse(
            any(hasattr(file, "relative_path") for file in widget.handled_files)
        )

    def test_dashboard_upload_route_rejects_conflicting_basename_metadata(self) -> None:
        widget = FakeDashboardUploadWidget(
            "client-conflicting-basename",
            "upload-conflicting-basename",
        )
        upload_url = register_dashboard_upload_handler(widget, lambda _text: None)
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                upload_key,
                FakeRequest(
                    [
                        (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                        (
                            "services/payments/plan.json",
                            FakeStarletteUpload(
                                "plan.json",
                                content=b'{"resource_changes": []}',
                            ),
                        ),
                    ]
                ),
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(widget.handled_files, [])

    def test_dashboard_directory_upload_route_rejects_basename_only_metadata(
        self,
    ) -> None:
        widget = FakeDashboardUploadWidget("client-dir-route", "upload-dir-route")
        upload_url = register_dashboard_upload_handler(
            widget,
            lambda _text: None,
            require_directory_paths=True,
        )
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                upload_key,
                FakeRequest(
                    [
                        (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                        (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                        ("plan.json", FakeStarletteUpload("plan.json")),
                        ("plan.json", FakeStarletteUpload("plan.json")),
                    ]
                ),
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(widget.handled_files, [])

    def test_dashboard_directory_upload_route_rejects_missing_artifact_paths(
        self,
    ) -> None:
        widget = FakeDashboardUploadWidget(
            "client-dir-no-paths",
            "upload-dir-no-paths",
        )
        upload_url = register_dashboard_upload_handler(
            widget,
            lambda _text: None,
            require_directory_paths=True,
        )
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                upload_key,
                FakeRequest(
                    [
                        (
                            "files",
                            FakeStarletteUpload(
                                "services/unowned/plan.json",
                                content=b'{"resource_changes": []}',
                            ),
                        )
                    ]
                ),
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(widget.handled_files, [])

    def test_dashboard_directory_upload_route_rejects_basename_artifact_paths(
        self,
    ) -> None:
        widget = FakeDashboardUploadWidget(
            "client-dir-basename-paths",
            "upload-dir-basename-paths",
        )
        upload_url = register_dashboard_upload_handler(
            widget,
            lambda _text: None,
            require_directory_paths=True,
        )
        upload_key = upload_url.rsplit("/", maxsplit=1)[-1]
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(
            route.endpoint(  # type: ignore[attr-defined]
                upload_key,
                FakeRequest(
                    [
                        (DASHBOARD_UPLOAD_ARTIFACT_PATH_FIELD, "plan.json"),
                        (
                            "files",
                            FakeStarletteUpload(
                                "plan.json",
                                content=b'{"resource_changes": []}',
                            ),
                        ),
                    ]
                ),
            )
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(widget.handled_files, [])

    def test_dashboard_upload_route_rejects_unknown_upload_key(self) -> None:
        register_dashboard_upload_handler(
            FakeDashboardUploadWidget("client-known", "upload-known"),
            lambda _text: None,
        )
        route_path = f"{DASHBOARD_UPLOAD_ROUTE_PREFIX}/{{upload_key}}"
        route = next(
            route
            for route in getattr(dashboard_app.router, "routes", [])
            if getattr(route, "path", None) == route_path
        )

        response = asyncio.run(route.endpoint("missing-upload-key", FakeRequest([])))  # type: ignore[attr-defined]

        self.assertEqual(response.status_code, 404)

    def test_apply_upload_widget_state_updates_all_upload_widgets(self) -> None:
        file_widget = FakeUploadWidget()
        directory_widget = FakeUploadWidget()

        apply_upload_widget_state((file_widget, directory_widget), enabled=False)

        self.assertFalse(file_widget.enabled)
        self.assertFalse(directory_widget.enabled)

        apply_upload_widget_state((file_widget, directory_widget), enabled=True)

        self.assertTrue(file_widget.enabled)
        self.assertTrue(directory_widget.enabled)

    def test_reset_upload_widgets_updates_all_upload_widgets(self) -> None:
        file_widget = FakeUploadWidget()
        directory_widget = FakeUploadWidget()

        reset_upload_widgets((file_widget, directory_widget, None))

        self.assertEqual(file_widget.reset_count, 1)
        self.assertEqual(directory_widget.reset_count, 1)

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
                "actor": "ui_local_user",
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

    def test_format_analysis_failure_surfaces_persistence_error_actionably(
        self,
    ) -> None:
        title, message, notification = format_analysis_failure(
            AnalysisPersistenceError("database is read-only")
        )

        self.assertEqual(title, "Report persistence failed")
        self.assertEqual(message, AnalysisPersistenceError.public_reason)
        self.assertIn("report was not saved", notification)
        self.assertIn("persistence configuration", notification)
        self.assertNotIn("database is read-only", message)
        self.assertNotIn("database is read-only", notification)
        self.assertNotIn("local storage", notification)

    def test_persisted_report_reference_prefers_saved_report_id(self) -> None:
        self.assertEqual(
            persisted_report_reference({"id": 42}),
            ("Saved report #42", "/reports/42"),
        )
        self.assertEqual(
            persisted_report_reference({"audit": {"delivery": {"report_id": "43"}}}),
            ("Saved report #43", "/reports/43"),
        )
        self.assertIsNone(persisted_report_reference({"id": "not-a-number"}))

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

    def test_report_incident_matches_preserves_empty_state(self) -> None:
        with patch("ui.components.upload_panel.render_incident_matches") as render_mock:
            render_report_incident_matches({"incident_matches": []})

        render_mock.assert_called_once_with([])

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
