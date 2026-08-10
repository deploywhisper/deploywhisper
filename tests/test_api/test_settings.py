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
import models.repositories.settings as settings_repository_module
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
                "request_timeout_seconds": 120,
                "local_mode": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["settings"]["provider"], "ollama")
        self.assertTrue(payload["data"]["settings"]["local_mode"])
        self.assertEqual(payload["data"]["settings"]["request_timeout_seconds"], 120)
        self.assertIn("valid", payload["data"]["validation"])

    def test_policy_adapter_defaults_can_be_managed_per_project_and_integration(
        self,
    ) -> None:
        project_payload = {
            "project_key": self.project.project_key,
            "warn_at": "medium",
            "soft_block_at": "high",
            "hard_block_at": "critical",
            "reporting_default": "advisory",
        }
        saved_project = self.client.put(
            "/api/v1/settings/policy-adapter",
            json=project_payload,
        )
        saved_integration = self.client.put(
            "/api/v1/settings/policy-adapter",
            json={
                **project_payload,
                "integration": "jenkins",
                "warn_at": "high",
                "soft_block_at": "critical",
                "hard_block_at": None,
                "reporting_default": "warn",
            },
        )
        loaded = self.client.get(
            "/api/v1/settings/policy-adapter",
            params={
                "project_key": self.project.project_key,
                "integration": "jenkins",
            },
        )

        self.assertEqual(saved_project.status_code, 200)
        self.assertEqual(saved_project.json()["data"]["source"], "project")
        self.assertEqual(saved_integration.status_code, 200)
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["data"]["source"], "integration")
        self.assertEqual(loaded.json()["data"]["reporting_default"], "warn")
        self.assertIsNone(loaded.json()["data"]["hard_block_at"])

    def test_policy_adapter_defaults_require_admin_settings_permission(self) -> None:
        response = self.client.put(
            "/api/v1/settings/policy-adapter",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
            json={
                "project_key": self.project.project_key,
                "warn_at": "medium",
                "soft_block_at": "high",
                "hard_block_at": "critical",
                "reporting_default": "advisory",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_permission_denied")

    def test_policy_adapter_update_preserves_project_resolution_error_contract(
        self,
    ) -> None:
        response = self.client.put(
            "/api/v1/settings/policy-adapter",
            json={
                "project_id": 999_999,
                "warn_at": "medium",
                "soft_block_at": "high",
                "hard_block_at": "critical",
                "reporting_default": "advisory",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_policy_adapter_defaults_can_be_reset_to_inherited_scope(self) -> None:
        project_payload = {
            "project_key": self.project.project_key,
            "warn_at": "medium",
            "soft_block_at": "high",
            "hard_block_at": "critical",
            "reporting_default": "advisory",
        }
        self.client.put("/api/v1/settings/policy-adapter", json=project_payload)
        self.client.put(
            "/api/v1/settings/policy-adapter",
            json={
                **project_payload,
                "integration": "jenkins",
                "warn_at": "high",
                "soft_block_at": "critical",
                "hard_block_at": None,
                "reporting_default": "warn",
            },
        )

        reset_integration = self.client.delete(
            "/api/v1/settings/policy-adapter",
            params={
                "project_key": self.project.project_key,
                "integration": "jenkins",
            },
        )
        reset_project = self.client.delete(
            "/api/v1/settings/policy-adapter",
            params={"project_key": self.project.project_key},
        )

        self.assertEqual(reset_integration.status_code, 200)
        self.assertEqual(reset_integration.json()["data"]["source"], "project")
        self.assertEqual(reset_project.status_code, 200)
        self.assertEqual(reset_project.json()["data"]["source"], "built-in")

    def test_policy_adapter_defaults_require_explicit_project_scope(self) -> None:
        requests = (
            self.client.get("/api/v1/settings/policy-adapter"),
            self.client.put(
                "/api/v1/settings/policy-adapter",
                json={
                    "warn_at": "medium",
                    "soft_block_at": "high",
                    "hard_block_at": "critical",
                    "reporting_default": "advisory",
                },
            ),
            self.client.delete("/api/v1/settings/policy-adapter"),
        )

        for response in requests:
            with self.subTest(method=response.request.method):
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["code"],
                    "missing_project_scope",
                )

    def test_policy_adapter_query_integration_validation_matches_write_contract(
        self,
    ) -> None:
        for method in (self.client.get, self.client.delete):
            with self.subTest(method=method.__name__, integration="empty"):
                response = method(
                    "/api/v1/settings/policy-adapter",
                    params={
                        "project_key": self.project.project_key,
                        "integration": "",
                    },
                )
                self.assertEqual(response.status_code, 422)

            with self.subTest(method=method.__name__, integration="whitespace"):
                response = method(
                    "/api/v1/settings/policy-adapter",
                    params={
                        "project_key": self.project.project_key,
                        "integration": "   ",
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["code"],
                    "invalid_policy_adapter_settings",
                )

    def test_policy_adapter_defaults_report_corrupt_storage_as_server_error(
        self,
    ) -> None:
        with database_module.SessionLocal() as session:
            settings_repository_module.upsert_setting(
                session,
                key=(f"policy_adapter_defaults::{self.project.project_key}::project"),
                value="not-json",
            )

        response = self.client.get(
            "/api/v1/settings/policy-adapter",
            params={"project_key": self.project.project_key},
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["error"]["code"],
            "policy_adapter_settings_integrity_error",
        )

    def test_openapi_documents_policy_adapter_settings_error_contracts(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        operations = response.json()["paths"]["/api/v1/settings/policy-adapter"]
        for method in ("get", "put", "delete"):
            with self.subTest(method=method):
                responses = operations[method]["responses"]
                for status_code in ("400", "403", "404", "422", "500"):
                    self.assertIn("ErrorResponse", str(responses[status_code]))

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
        self.assertEqual(
            saved.json()["data"]["success_message"], "Topology context saved."
        )

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
