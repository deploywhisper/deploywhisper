"""Smoke and workflow tests for the settings page."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import create_app
from ui.routes.settings import process_custom_skill_upload_content, process_topology_upload_content


class SettingsPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_settings_page_contains_topology_context_workflow(self) -> None:
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn("AI provider", response.text)
        self.assertIn("OpenAI / ChatGPT", response.text)
        self.assertIn("API key", response.text)
        self.assertIn("Dashboard Result Display Duration", response.text)
        self.assertIn("Topology context", response.text)
        self.assertIn("blast-radius analysis", response.text)

    def test_process_topology_upload_content_reports_success_for_valid_upload(self) -> None:
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

    def test_process_topology_upload_content_preserves_active_topology_when_upload_is_invalid(self) -> None:
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
        self.assertEqual(invalid_result["status"].updated_at, valid_result["status"].updated_at)

    def test_process_custom_skill_upload_content_reports_override_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text("# Built-in\nDefault terraform guidance.", encoding="utf-8")
            with patch("llm.skill_context.SKILLS_DIR", skills_dir), patch("llm.skill_context.CUSTOM_DIR", custom_dir):
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
            with patch("llm.skill_context.SKILLS_DIR", skills_dir), patch("llm.skill_context.CUSTOM_DIR", custom_dir):
                result = process_custom_skill_upload_content(
                    "helm.md",
                    b"---\ntitle: empty\n---",
                )
        self.assertIn("Custom skill update failed", result["error_message"])
        self.assertEqual(result["statuses"], [])


if __name__ == "__main__":
    unittest.main()
