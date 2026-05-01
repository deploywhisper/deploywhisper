"""Smoke and workflow tests for the settings page."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app as app_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
from fastapi.testclient import TestClient

from ui.routes.settings import (
    preview_topology_upload_content,
    process_custom_skill_upload_content,
    process_topology_upload_content,
)


class SettingsPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "settings.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_settings_page_contains_topology_context_workflow(self) -> None:
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI provider", response.text)
        self.assertIn("OpenAI / ChatGPT", response.text)
        self.assertIn("Secrets", response.text)
        self.assertIn("API keys are not stored in the app database", response.text)
        self.assertIn("API key", response.text)
        self.assertIn("Provider capabilities", response.text)
        self.assertIn("MCP readiness remains optional", response.text)
        self.assertIn("Dashboard Result Display Duration", response.text)
        self.assertIn("Topology context", response.text)
        self.assertIn("blast-radius analysis", response.text)
        self.assertIn(
            "DeployWhisper validates the structure when you select a file",
            response.text,
        )
        self.assertIn("Save topology to active project", response.text)
        self.assertIn(
            "Choose a topology JSON, review the validation result, then click save to apply it to the active project shown above.",
            response.text,
        )
        self.assertIn("Drift check cadence", response.text)
        self.assertIn("Topology drift", response.text)
        self.assertIn("Reviewer feedback summary", response.text)

    def test_settings_page_lists_drift_resource_names(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.set_active_project(project.id)
        source_path = Path(self.tempdir.name) / "ui-drift-topology.json"
        source_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                        },
                        {
                            "id": "billing",
                            "label": "Billing",
                            "resource_keys": ["Deployment/billing"],
                            "downstream": [],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        import services.topology_service as topology_service_module

        topology_service_module.import_topology_source(
            "custom",
            str(source_path),
            project_key="payments",
        )
        source_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": ["worker"],
                        },
                        {
                            "id": "worker",
                            "label": "Worker",
                            "resource_keys": ["Deployment/worker"],
                            "downstream": [],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        topology_service_module.check_topology_drift(
            project_key="payments",
            force=True,
        )

        response = self.client.get("/settings")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Deployment/worker", response.text)
        self.assertIn("Deployment/billing", response.text)
        self.assertIn("Deployment/api", response.text)

    def test_topology_drift_scheduler_loop_runs_a_pass(self) -> None:
        stop_event = asyncio.Event()

        def run_once() -> None:
            stop_event.set()

        with (
            patch("app.run_due_topology_drift_checks", side_effect=run_once) as mocked,
            patch("app.run_due_weekly_backtests") as mocked_backtests,
        ):
            asyncio.run(app_module._topology_drift_scheduler_loop(stop_event))

        self.assertTrue(mocked.called)
        self.assertTrue(mocked_backtests.called)

    def test_process_topology_upload_content_reports_success_for_valid_upload(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service_topology.json"
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                result = process_topology_upload_content(
                    json.dumps(
                        {
                            "services": [
                                {
                                    "id": "api",
                                    "label": "API",
                                    "resource_keys": ["Deployment/api"],
                                    "downstream": [],
                                }
                            ]
                        }
                    ).encode("utf-8")
                )
        self.assertIsNone(result["error_message"])
        self.assertIn("Service topology updated", result["success_message"])
        self.assertEqual(result["status"].service_count, 1)

    def test_preview_topology_upload_content_reports_success_for_valid_upload(
        self,
    ) -> None:
        result = preview_topology_upload_content(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                        }
                    ]
                }
            ).encode("utf-8")
        )

        self.assertIsNone(result["error_message"])
        self.assertIn("Topology JSON is valid", result["success_message"])
        self.assertEqual(result["status"].service_count, 1)

    def test_process_topology_upload_content_preserves_active_topology_when_upload_is_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service_topology.json"
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                valid_result = process_topology_upload_content(
                    json.dumps(
                        {
                            "services": [
                                {
                                    "id": "api",
                                    "label": "API",
                                    "resource_keys": ["Deployment/api"],
                                    "downstream": [],
                                }
                            ]
                        }
                    ).encode("utf-8")
                )
                invalid_result = process_topology_upload_content(
                    json.dumps(
                        {
                            "services": [
                                {
                                    "id": "api",
                                    "label": "API",
                                    "resource_keys": ["Deployment/api"],
                                    "downstream": ["worker"],
                                }
                            ]
                        }
                    ).encode("utf-8")
                )
        self.assertIsNone(valid_result["error_message"])
        self.assertIn("Topology update failed", invalid_result["error_message"])
        self.assertEqual(invalid_result["status"].service_count, 1)
        self.assertEqual(
            invalid_result["status"].updated_at, valid_result["status"].updated_at
        )

    def test_preview_topology_upload_content_reports_validation_errors_without_saving(
        self,
    ) -> None:
        result = preview_topology_upload_content(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": ["worker"],
                        }
                    ]
                }
            ).encode("utf-8")
        )

        self.assertIn("Topology validation failed", result["error_message"])
        self.assertEqual(result["status"].service_count, 1)

    def test_preview_topology_upload_content_does_not_reuse_active_topology_on_parse_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service_topology.json"
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                valid_result = process_topology_upload_content(
                    json.dumps(
                        {
                            "services": [
                                {
                                    "id": "api",
                                    "label": "API",
                                    "resource_keys": ["Deployment/api"],
                                    "downstream": [],
                                }
                            ]
                        }
                    ).encode("utf-8")
                )
                invalid_preview = preview_topology_upload_content(b"{not-json")

        self.assertIsNone(valid_result["error_message"])
        self.assertIn("Topology validation failed", invalid_preview["error_message"])
        self.assertEqual(invalid_preview["status"].service_count, 0)
        self.assertEqual(invalid_preview["status"].preview_services, [])

    def test_process_custom_skill_upload_content_reports_override_detection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Built-in\nDefault terraform guidance.", encoding="utf-8"
            )
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                result = process_custom_skill_upload_content(
                    "terraform.md",
                    b"# Custom\nTeam terraform guidance.",
                )
        self.assertIsNone(result["error_message"])
        self.assertIn("terraform (override)", result["success_message"])
        self.assertEqual(result["statuses"][0].mode, "override")

    def test_process_custom_skill_upload_content_rejects_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                result = process_custom_skill_upload_content(
                    "helm.md",
                    b"---\ntitle: empty\n---",
                )
        self.assertIn("Custom skill update failed", result["error_message"])
        self.assertEqual(result["statuses"], [])


if __name__ == "__main__":
    unittest.main()
