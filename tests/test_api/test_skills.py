"""Tests for skills registry API routes."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.skill_registry_service as skill_registry_service_module
from app import create_app
from fastapi.testclient import TestClient


class SkillsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "skills.db"
        self.skills_dir = Path(self.tempdir.name) / "skills"
        self.custom_dir = self.skills_dir / "custom"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(skill_registry_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_list_skills_returns_paginated_filtered_metadata(self) -> None:
        (self.skills_dir / "terraform.md").write_text(
            "---\n"
            "skill: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "tool_type: terraform\n"
            "tags: [iac, security]\n"
            "description: Terraform registry skill.\n"
            "triggers: [.tf]\n"
            "---\n"
            "# Terraform\nDetails\n",
            encoding="utf-8",
        )
        (self.skills_dir / "kubernetes.md").write_text(
            "---\n"
            "skill: kubernetes\n"
            "version: 2.0.0\n"
            "author: Platform Team\n"
            "tool_type: kubernetes\n"
            "tags: [cluster]\n"
            "description: Kubernetes rollout checks.\n"
            "---\n"
            "# Kubernetes\nDetails\n",
            encoding="utf-8",
        )

        with (
            patch(
                "services.skill_registry_service.SKILLS_DIR",
                self.skills_dir,
            ),
            patch(
                "services.skill_registry_service.CUSTOM_DIR",
                self.custom_dir,
            ),
        ):
            response = self.client.get(
                "/api/v1/skills",
                params={
                    "tool": "terraform",
                    "tag": "iac",
                    "author": "DeployWhisper",
                    "search": "registry",
                    "page": 1,
                    "page_size": 25,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["meta"]["filters"]["tool"], "terraform")
        self.assertEqual(payload["data"][0]["id"], "terraform")
        self.assertEqual(payload["data"][0]["tool"], "terraform")
        self.assertEqual(payload["data"][0]["triggers"], [".tf"])

    def test_get_skill_and_versions_return_effective_skill_and_history(self) -> None:
        (self.skills_dir / "terraform.md").write_text(
            "---\n"
            "skill: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "tool_type: terraform\n"
            "description: Built-in terraform checks.\n"
            "---\n"
            "# Terraform\nBuilt-in guidance.\n",
            encoding="utf-8",
        )
        (self.custom_dir / "terraform.md").write_text(
            "---\n"
            "skill: terraform\n"
            "version: 1.3.0\n"
            "author: Team Ops\n"
            "tool_type: terraform\n"
            "tags: [private]\n"
            "description: Team override.\n"
            "---\n"
            "# Terraform\nCustom guidance.\n",
            encoding="utf-8",
        )

        with (
            patch(
                "services.skill_registry_service.SKILLS_DIR",
                self.skills_dir,
            ),
            patch(
                "services.skill_registry_service.CUSTOM_DIR",
                self.custom_dir,
            ),
        ):
            detail_response = self.client.get("/api/v1/skills/terraform")
            versions_response = self.client.get("/api/v1/skills/terraform/versions")

        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["data"]["source"], "built-in")
        self.assertEqual(detail_payload["data"]["available_versions"], 1)
        self.assertEqual(detail_payload["meta"]["id"], "terraform")

        self.assertEqual(versions_response.status_code, 200)
        versions_payload = versions_response.json()
        self.assertEqual(len(versions_payload["data"]), 1)
        self.assertEqual(versions_payload["data"][0]["version"], "1.0.0")
        self.assertTrue(versions_payload["data"][0]["is_current"])
        self.assertEqual(versions_payload["data"][0]["source"], "built-in")

    def test_registry_api_ignores_local_custom_cache_entries(self) -> None:
        (self.skills_dir / "terraform.md").write_text(
            "---\n"
            "skill: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "tool_type: terraform\n"
            "description: Built-in terraform checks.\n"
            "---\n"
            "# Terraform\nBuilt-in guidance.\n",
            encoding="utf-8",
        )
        (self.custom_dir / "terraform.md").write_text(
            "---\n"
            "skill: terraform\n"
            "version: 9.9.9\n"
            "author: Team Ops\n"
            "tool_type: terraform\n"
            "description: Local install cache override.\n"
            "---\n"
            "# Terraform\nCustom guidance.\n",
            encoding="utf-8",
        )

        with (
            patch("services.skill_registry_service.SKILLS_DIR", self.skills_dir),
            patch("services.skill_registry_service.CUSTOM_DIR", self.custom_dir),
        ):
            detail_response = self.client.get("/api/v1/skills/terraform")
            versions_response = self.client.get("/api/v1/skills/terraform/versions")

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["data"]["source"], "built-in")
        self.assertEqual(detail_response.json()["data"]["version"], "1.0.0")
        self.assertEqual(versions_response.status_code, 200)
        self.assertEqual(len(versions_response.json()["data"]), 1)

    def test_registry_api_skips_invalid_frontmatter_instead_of_failing(self) -> None:
        (self.skills_dir / "terraform.md").write_text(
            "---\n: broken\n---\n# Terraform\nBroken frontmatter.\n",
            encoding="utf-8",
        )

        with (
            patch("services.skill_registry_service.SKILLS_DIR", self.skills_dir),
            patch("services.skill_registry_service.CUSTOM_DIR", self.custom_dir),
        ):
            list_response = self.client.get("/api/v1/skills")
            detail_response = self.client.get("/api/v1/skills/terraform")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["data"], [])
        self.assertEqual(detail_response.status_code, 404)

    def test_missing_skill_returns_api_error(self) -> None:
        with (
            patch(
                "services.skill_registry_service.SKILLS_DIR",
                self.skills_dir,
            ),
            patch(
                "services.skill_registry_service.CUSTOM_DIR",
                self.custom_dir,
            ),
        ):
            response = self.client.get("/api/v1/skills/missing-skill")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "skill_not_found")

    def test_openapi_includes_skills_registry_routes(self) -> None:
        response = self.client.get("/api/v1/openapi.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("/api/v1/skills", payload["paths"])
        self.assertIn("/api/v1/skills/{skill_id}", payload["paths"])
        self.assertIn("/api/v1/skills/{skill_id}/versions", payload["paths"])


if __name__ == "__main__":
    unittest.main()
