"""Tests for React settings API routes."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import llm.skill_context as skill_context_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
import services.settings_service as settings_service_module
from app import create_app
from fastapi.testclient import TestClient


class SettingsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "settings-api.db"
        self.skills_dir = Path(self.tempdir.name) / "skills"
        self.custom_dir = self.skills_dir / "custom"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(settings_service_module)
        reload(skill_context_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_get_settings_summary_returns_provider_topology_feedback_and_skills(
        self,
    ) -> None:
        with (
            patch("llm.skill_context.SKILLS_DIR", self.skills_dir),
            patch("llm.skill_context.CUSTOM_DIR", self.custom_dir),
        ):
            response = self.client.get(
                "/api/v1/settings",
                params={"project_key": self.project.project_key},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["provider"]["provider"], "ollama")
        self.assertGreaterEqual(len(payload["data"]["provider_options"]), 1)
        self.assertEqual(payload["data"]["topology"]["service_count"], 0)
        self.assertEqual(
            payload["data"]["feedback"]["project"]["project_key"],
            self.project.project_key,
        )
        self.assertEqual(payload["data"]["custom_skills"], [])

    def test_update_provider_settings_saves_active_provider(self) -> None:
        response = self.client.put(
            "/api/v1/settings/provider",
            json={
                "provider": "ollama",
                "model": "ollama/llama3.1",
                "api_base": "http://localhost:11434",
                "local_mode": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["settings"]["provider"], "ollama")
        self.assertTrue(payload["data"]["settings"]["local_mode"])
        self.assertIn("valid", payload["data"]["validation"])

    def test_preview_and_save_topology_return_validation_payloads(self) -> None:
        topology = {
            "services": [
                {
                    "id": "api",
                    "label": "API",
                    "resource_keys": ["Deployment/api"],
                    "downstream": [],
                }
            ]
        }
        preview = self.client.post(
            "/api/v1/settings/topology/preview",
            json={"project_key": self.project.project_key, "topology": topology},
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["data"]["topology"]["service_count"], 1)
        self.assertIsNone(preview.json()["data"]["error_message"])

        saved = self.client.put(
            "/api/v1/settings/topology",
            json={"project_key": self.project.project_key, "topology": topology},
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["data"]["topology"]["service_count"], 1)
        self.assertEqual(saved.json()["data"]["success_message"], "Topology context saved.")

    def test_update_drift_cadence_rejects_unsupported_interval(self) -> None:
        rejected = self.client.put(
            "/api/v1/settings/topology/drift-cadence",
            json={"interval_hours": 3},
        )

        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(
            rejected.json()["error"]["code"],
            "invalid_topology_drift_cadence",
        )

        accepted = self.client.put(
            "/api/v1/settings/topology/drift-cadence",
            json={"interval_hours": 12},
        )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["data"]["interval_hours"], 12)

    def test_custom_skill_upload_returns_updated_statuses(self) -> None:
        with (
            patch("llm.skill_context.SKILLS_DIR", self.skills_dir),
            patch("llm.skill_context.CUSTOM_DIR", self.custom_dir),
        ):
            response = self.client.post(
                "/api/v1/settings/custom-skills",
                json={
                    "filename": "terraform.md",
                    "content": "---\nname: terraform\n---\n# Terraform\nCustom guidance.\n",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["saved"]["name"], "terraform")
        self.assertEqual(payload["data"]["statuses"][0]["mode"], "new")
        self.assertTrue((self.custom_dir / "terraform.md").exists())


if __name__ == "__main__":
    unittest.main()
