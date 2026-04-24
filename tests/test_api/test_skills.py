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
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "tags: [iac, security]\n"
            "description: Terraform registry skill.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "token_budget: 1200\n"
            "triggers: [.tf]\n"
            "---\n"
            "# Terraform\nDetails\n",
            encoding="utf-8",
        )
        (self.skills_dir / "kubernetes.md").write_text(
            "---\n"
            "name: kubernetes\n"
            "version: 2.0.0\n"
            "author: Platform Team\n"
            "license: MIT\n"
            "tags: [cluster]\n"
            "description: Kubernetes rollout checks.\n"
            "test_suite_path: tests/skill-tests/kubernetes\n"
            "token_budget: 900\n"
            "triggers: [.yaml]\n"
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
        self.assertEqual(payload["data"][0]["name"], "Terraform")
        self.assertEqual(payload["data"][0]["tool"], "terraform")
        self.assertEqual(
            payload["data"][0]["test_suite_path"], "tests/skill-tests/terraform"
        )
        self.assertIn("install_count", payload["data"][0])
        self.assertIn("active_issue_count", payload["data"][0])
        self.assertIn("analytics_updated_at", payload["data"][0])
        self.assertEqual(payload["data"][0]["test_results"]["status"], "passing")
        self.assertEqual(payload["data"][0]["triggers"], [".tf"])

    def test_get_skill_and_versions_return_effective_skill_and_history(self) -> None:
        (self.skills_dir / "terraform.md").write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "description: Built-in terraform checks.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "token_budget: 1200\n"
            "triggers: [.tf]\n"
            "tags: [iac]\n"
            "---\n"
            "# Terraform\nBuilt-in guidance.\n",
            encoding="utf-8",
        )
        (self.custom_dir / "terraform.md").write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.3.0\n"
            "author: Team Ops\n"
            "license: Proprietary\n"
            "tags: [private]\n"
            "description: Team override.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "token_budget: 1200\n"
            "triggers: [.tf]\n"
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
        self.assertEqual(detail_payload["data"]["name"], "Terraform")
        self.assertEqual(detail_payload["data"]["available_versions"], 1)
        self.assertIn("install_count", detail_payload["data"])
        self.assertIn("active_issue_count", detail_payload["data"])
        self.assertIn("analytics_updated_at", detail_payload["data"])
        self.assertEqual(detail_payload["data"]["test_results"]["status"], "passing")
        self.assertEqual(detail_payload["meta"]["id"], "terraform")

        self.assertEqual(versions_response.status_code, 200)
        versions_payload = versions_response.json()
        self.assertEqual(len(versions_payload["data"]), 1)
        self.assertEqual(versions_payload["data"][0]["version"], "1.0.0")
        self.assertTrue(versions_payload["data"][0]["is_current"])
        self.assertEqual(versions_payload["data"][0]["source"], "built-in")

    def test_get_skill_content_returns_raw_markdown_payload(self) -> None:
        content = (
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "description: Built-in terraform checks.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "token_budget: 1200\n"
            "triggers: [.tf]\n"
            "tags: [iac]\n"
            "---\n"
            "# Terraform\nBuilt-in guidance.\n"
        )
        (self.skills_dir / "terraform.md").write_text(content, encoding="utf-8")

        with (
            patch("services.skill_registry_service.SKILLS_DIR", self.skills_dir),
            patch("services.skill_registry_service.CUSTOM_DIR", self.custom_dir),
        ):
            response = self.client.get("/api/v1/skills/terraform/content")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["id"], "terraform")
        self.assertEqual(payload["data"]["version"], "1.0.0")
        self.assertEqual(payload["data"]["content"], content)
        self.assertEqual(len(payload["data"]["sha256"]), 64)

    def test_registry_api_ignores_local_custom_cache_entries(self) -> None:
        (self.skills_dir / "terraform.md").write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "description: Built-in terraform checks.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "token_budget: 1200\n"
            "triggers: [.tf]\n"
            "tags: [iac]\n"
            "---\n"
            "# Terraform\nBuilt-in guidance.\n",
            encoding="utf-8",
        )
        (self.custom_dir / "terraform.md").write_text(
            "---\n"
            "name: terraform\n"
            "version: 9.9.9\n"
            "author: Team Ops\n"
            "license: Proprietary\n"
            "description: Local install cache override.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "token_budget: 1200\n"
            "triggers: [.tf]\n"
            "tags: [private]\n"
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
        self.assertIn("/api/v1/skills/{skill_id}/content", payload["paths"])
        self.assertIn("/api/v1/skills/{skill_id}/versions", payload["paths"])

    def test_schema_route_publishes_skill_manifest_v1(self) -> None:
        response = self.client.get("/schemas/skill-manifest-v1.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["title"], "SkillManifestV1")
        self.assertEqual(payload["$id"], "/schemas/skill-manifest-v1.json")
        self.assertIn("name", payload["required"])
        self.assertIn("test_suite_path", payload["properties"])

    def test_skill_test_results_route_returns_public_scenario_results(self) -> None:
        response = self.client.get("/api/v1/skills/terraform/test-results")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["skill_id"], "terraform")
        self.assertEqual(payload["data"]["summary"]["status"], "passing")
        self.assertGreaterEqual(len(payload["data"]["scenarios"]), 1)

    def test_skill_test_results_route_reports_invalid_suite_as_failing_not_500(
        self,
    ) -> None:
        (self.skills_dir / "terraform.md").write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "description: Built-in terraform checks.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "token_budget: 1200\n"
            "triggers: [.tf]\n"
            "tags: [iac]\n"
            "---\n"
            "# Terraform\nBuilt-in guidance.\n",
            encoding="utf-8",
        )
        suite_dir = Path(self.tempdir.name) / "tests" / "skill-tests" / "terraform"
        suite_dir.mkdir(parents=True, exist_ok=True)
        (suite_dir / "broken.json").write_text(
            '{"name": "", "assessment_tool": "terraform"}',
            encoding="utf-8",
        )

        with (
            patch(
                "services.skill_test_harness_service.REPO_ROOT",
                Path(self.tempdir.name),
            ),
            patch("services.skill_test_harness_service.SKILLS_DIR", self.skills_dir),
        ):
            response = self.client.get("/api/v1/skills/terraform/test-results")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["summary"]["status"], "failing")
        self.assertEqual(payload["data"]["scenarios"][0]["name"], "suite-load-error")
        self.assertIn("broken.json", payload["data"]["scenarios"][0]["failures"][0])


if __name__ == "__main__":
    unittest.main()
