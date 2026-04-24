"""UI tests for the public skills browser."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import app as app_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.skill_registry_service as skill_registry_service_module
from fastapi.testclient import TestClient


class SkillsBrowserPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "skills-ui.db"
        self.skills_dir = Path(self.tempdir.name) / "skills"
        self.custom_dir = self.skills_dir / "custom"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(skill_registry_service_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _write_skill(
        self,
        skill_id: str,
        *,
        author: str,
        description: str,
        triggers: str,
        tags: str,
        suite_path: str,
    ) -> None:
        (self.skills_dir / f"{skill_id}.md").write_text(
            "---\n"
            f"name: {skill_id}\n"
            "version: 1.0.0\n"
            f"author: {author}\n"
            "license: MIT\n"
            f"description: {description}\n"
            f"test_suite_path: {suite_path}\n"
            "token_budget: 1200\n"
            f"triggers: [{triggers}]\n"
            f"tags: [{tags}]\n"
            "---\n"
            f"# {skill_id.title()}\nGuidance.\n",
            encoding="utf-8",
        )

    def test_skills_browser_page_renders_catalog_and_metrics(self) -> None:
        self._write_skill(
            "terraform",
            author="DeployWhisper",
            description="Terraform registry skill.",
            triggers=".tf",
            tags="iac, security",
            suite_path="tests/skill-tests/terraform",
        )
        self._write_skill(
            "kubernetes",
            author="Platform Team",
            description="Kubernetes rollout checks.",
            triggers=".yaml",
            tags="cluster",
            suite_path="tests/skill-tests/kubernetes",
        )

        with (
            patch("services.skill_registry_service.SKILLS_DIR", self.skills_dir),
            patch("services.skill_registry_service.CUSTOM_DIR", self.custom_dir),
        ):
            response = self.client.get("/skills")

        self.assertEqual(response.status_code, 200)
        self.assertIn("DeployWhisper", response.text)
        self.assertIn("skills atlas", response.text)
        self.assertIn("Search the current skills registry", response.text)
        self.assertIn("Catalog installs", response.text)
        self.assertIn("deploywhisper skill install terraform", response.text)
        self.assertIn("Pass rate", response.text)
        self.assertIn("Active issues", response.text)
        self.assertIn("Terraform", response.text)
        self.assertIn("Kubernetes", response.text)

    def test_skills_browser_page_applies_query_filters(self) -> None:
        self._write_skill(
            "terraform",
            author="DeployWhisper",
            description="Terraform registry skill.",
            triggers=".tf",
            tags="iac, security",
            suite_path="tests/skill-tests/terraform",
        )
        self._write_skill(
            "kubernetes",
            author="Platform Team",
            description="Kubernetes rollout checks.",
            triggers=".yaml",
            tags="cluster",
            suite_path="tests/skill-tests/kubernetes",
        )

        with (
            patch("services.skill_registry_service.SKILLS_DIR", self.skills_dir),
            patch("services.skill_registry_service.CUSTOM_DIR", self.custom_dir),
        ):
            response = self.client.get("/skills?tool=kubernetes&author=Platform+Team")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Kubernetes", response.text)
        self.assertNotIn("Terraform registry skill.", response.text)

    def test_skill_detail_page_shows_install_command_versions_and_contributors(
        self,
    ) -> None:
        self._write_skill(
            "terraform",
            author="DeployWhisper",
            description="Terraform registry skill.",
            triggers=".tf",
            tags="iac, security",
            suite_path="tests/skill-tests/terraform",
        )

        with (
            patch("services.skill_registry_service.SKILLS_DIR", self.skills_dir),
            patch("services.skill_registry_service.CUSTOM_DIR", self.custom_dir),
        ):
            response = self.client.get("/skills/terraform")

        self.assertEqual(response.status_code, 200)
        self.assertIn("deploywhisper skill install terraform", response.text)
        self.assertIn("Version history", response.text)
        self.assertIn("Contributors", response.text)
        self.assertIn("Installs", response.text)
        self.assertIn("Active issues", response.text)
        self.assertIn("Analytics refreshed", response.text)
        self.assertIn("DeployWhisper", response.text)

    def test_skills_browser_page_includes_items_beyond_first_catalog_page(self) -> None:
        for index in range(205):
            self._write_skill(
                f"skill-{index:03d}",
                author="DeployWhisper" if index < 204 else "Late Author",
                description=f"Catalog skill {index}.",
                triggers=".tf",
                tags="iac",
                suite_path="tests/skill-tests/terraform",
            )

        with (
            patch("services.skill_registry_service.SKILLS_DIR", self.skills_dir),
            patch("services.skill_registry_service.CUSTOM_DIR", self.custom_dir),
        ):
            response = self.client.get("/skills?author=Late+Author")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Catalog skill 204.", response.text)
        self.assertIn("Late Author", response.text)


if __name__ == "__main__":
    unittest.main()
