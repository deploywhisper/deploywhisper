"""Tests for the shared skills registry service."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.skill_registry_service import (
    fetch_skill_registry_entry,
    fetch_skill_registry_page,
    fetch_skill_registry_versions,
)


class SkillRegistryServiceTests(unittest.TestCase):
    def test_registry_page_applies_filters_search_and_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
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
            (skills_dir / "kubernetes.md").write_text(
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
                    skills_dir,
                ),
                patch(
                    "services.skill_registry_service.CUSTOM_DIR",
                    custom_dir,
                ),
            ):
                page = fetch_skill_registry_page(
                    tool="terraform",
                    tag="iac",
                    author="DeployWhisper",
                    search="registry",
                    page=1,
                    page_size=10,
                )
                paged = fetch_skill_registry_page(page=2, page_size=1)

        self.assertEqual(page.total_count, 1)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].id, "terraform")
        self.assertEqual(page.items[0].name, "Terraform")
        self.assertEqual(page.items[0].test_suite_path, "tests/skill-tests/terraform")
        self.assertEqual(
            page.items[0].install_command, "deploywhisper skill install terraform"
        )
        self.assertGreater(page.items[0].install_count, 0)
        self.assertGreaterEqual(page.items[0].active_issue_count, 0)
        self.assertIsNotNone(page.items[0].analytics_updated_at)
        self.assertGreater(page.items[0].download_count, 0)
        self.assertGreater(page.items[0].star_count, 0)
        self.assertEqual(page.items[0].contributors, ["DeployWhisper"])
        self.assertEqual(paged.total_count, 2)
        self.assertEqual(len(paged.items), 1)
        self.assertEqual(paged.items[0].id, "kubernetes")

    def test_registry_entry_returns_bundled_catalog_version_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
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
            (custom_dir / "terraform.md").write_text(
                "---\n"
                "name: terraform\n"
                "version: 1.2.0\n"
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
            (custom_dir / "README.md").write_text(
                "# Ignore\nRegistry docs only.\n",
                encoding="utf-8",
            )

            with (
                patch(
                    "services.skill_registry_service.SKILLS_DIR",
                    skills_dir,
                ),
                patch(
                    "services.skill_registry_service.CUSTOM_DIR",
                    custom_dir,
                ),
            ):
                entry = fetch_skill_registry_entry("terraform")
                versions = fetch_skill_registry_versions("terraform")

        assert entry is not None
        self.assertEqual(entry.source, "built-in")
        self.assertEqual(entry.version, "1.0.0")
        self.assertEqual(entry.name, "Terraform")
        self.assertEqual(entry.available_versions, 1)
        self.assertEqual(entry.install_command, "deploywhisper skill install terraform")
        self.assertGreater(entry.install_count, 0)
        self.assertGreaterEqual(entry.active_issue_count, 0)
        self.assertIsNotNone(entry.analytics_updated_at)
        self.assertEqual(entry.contributors, ["DeployWhisper"])
        self.assertEqual([version.version for version in versions], ["1.0.0"])
        self.assertTrue(versions[0].is_current)
        self.assertEqual(versions[0].author, "DeployWhisper")
        self.assertEqual(versions[0].source, "built-in")

    def test_registry_page_ignores_local_custom_cache_for_canonical_results(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
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
            (custom_dir / "terraform.md").write_text(
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
                patch("services.skill_registry_service.SKILLS_DIR", skills_dir),
                patch("services.skill_registry_service.CUSTOM_DIR", custom_dir),
            ):
                page = fetch_skill_registry_page()
                entry = fetch_skill_registry_entry("terraform")
                versions = fetch_skill_registry_versions("terraform")

        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items[0].source, "built-in")
        assert entry is not None
        self.assertEqual(entry.source, "built-in")
        self.assertEqual(entry.version, "1.0.0")
        self.assertEqual([version.version for version in versions], ["1.0.0"])

    def test_registry_skips_files_with_invalid_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "---\n: broken\n---\n# Terraform\nBroken frontmatter.\n",
                encoding="utf-8",
            )
            (skills_dir / "kubernetes.md").write_text(
                "---\n"
                "name: kubernetes\n"
                "version: 1.0.0\n"
                "author: DeployWhisper\n"
                "license: MIT\n"
                "description: Healthy skill.\n"
                "test_suite_path: tests/skill-tests/kubernetes\n"
                "token_budget: 900\n"
                "triggers: [.yaml]\n"
                "tags: [cluster]\n"
                "---\n"
                "# Kubernetes\nHealthy guidance.\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_registry_service.SKILLS_DIR", skills_dir),
                patch("services.skill_registry_service.CUSTOM_DIR", custom_dir),
            ):
                page = fetch_skill_registry_page()
                missing = fetch_skill_registry_entry("terraform")
                versions = fetch_skill_registry_versions("terraform")

        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items[0].id, "kubernetes")
        self.assertIsNone(missing)
        self.assertEqual(versions, [])

    def test_registry_page_reports_invalid_suite_json_as_failing_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            suite_dir = repo_root / "tests" / "skill-tests" / "terraform"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            suite_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
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
            (suite_dir / "broken.json").write_text(
                '{"name": "", "assessment_tool": "terraform"}',
                encoding="utf-8",
            )

            with (
                patch("services.skill_registry_service.SKILLS_DIR", skills_dir),
                patch("services.skill_registry_service.CUSTOM_DIR", custom_dir),
                patch("services.skill_test_harness_service.REPO_ROOT", repo_root),
                patch("services.skill_test_harness_service.SKILLS_DIR", skills_dir),
            ):
                page = fetch_skill_registry_page()

        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items[0].id, "terraform")
        assert page.items[0].test_results is not None
        self.assertEqual(page.items[0].test_results.status, "failing")
        self.assertEqual(page.items[0].test_results.failed_scenarios, 1)

    def test_registry_page_supports_recency_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            terraform_path = skills_dir / "terraform.md"
            kubernetes_path = skills_dir / "kubernetes.md"
            terraform_path.write_text(
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
            kubernetes_path.write_text(
                "---\n"
                "name: kubernetes\n"
                "version: 1.0.0\n"
                "author: DeployWhisper\n"
                "license: MIT\n"
                "description: Built-in kubernetes checks.\n"
                "test_suite_path: tests/skill-tests/kubernetes\n"
                "token_budget: 900\n"
                "triggers: [.yaml]\n"
                "tags: [cluster]\n"
                "---\n"
                "# Kubernetes\nBuilt-in guidance.\n",
                encoding="utf-8",
            )
            os.utime(terraform_path, (1000, 1000))
            os.utime(kubernetes_path, (2000, 2000))

            with (
                patch("services.skill_registry_service.SKILLS_DIR", skills_dir),
                patch("services.skill_registry_service.CUSTOM_DIR", custom_dir),
            ):
                page = fetch_skill_registry_page(sort="recency")

        self.assertEqual([item.id for item in page.items], ["kubernetes", "terraform"])

    def test_registry_page_exposes_analytics_fields_for_browser_and_cli(self) -> None:
        page = fetch_skill_registry_page(page_size=5)

        self.assertGreater(page.total_count, 0)
        item = page.items[0]
        self.assertIsInstance(item.install_count, int)
        self.assertGreaterEqual(item.install_count, 0)
        self.assertIsInstance(item.active_issue_count, int)
        self.assertGreaterEqual(item.active_issue_count, 0)
        self.assertIsInstance(item.analytics_updated_at, str)
        if item.test_results is not None:
            self.assertGreaterEqual(item.test_results.pass_rate, 0.0)
            self.assertLessEqual(item.test_results.pass_rate, 1.0)

    def test_registry_page_exposes_editorial_curation_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
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
            (skills_dir / "community-skill.md").write_text(
                "---\n"
                "name: community-skill\n"
                "version: 1.0.0\n"
                "author: Community Builder\n"
                "maintainer: Community Curators\n"
                "featured: true\n"
                "license: MIT\n"
                "description: Curated community guidance.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "token_budget: 900\n"
                "triggers: [.yaml]\n"
                "tags: [community]\n"
                "---\n"
                "# Community Skill\nGuidance.\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_registry_service.SKILLS_DIR", skills_dir),
                patch("services.skill_registry_service.CUSTOM_DIR", custom_dir),
            ):
                page = fetch_skill_registry_page(sort="recency")
                official = fetch_skill_registry_entry("terraform")
                featured = fetch_skill_registry_entry("community-skill")

        self.assertEqual(page.total_count, 2)
        assert official is not None
        assert featured is not None
        self.assertTrue(official.is_official)
        self.assertFalse(official.is_featured)
        self.assertEqual(official.maintainer, "DeployWhisper")
        self.assertFalse(featured.is_official)
        self.assertTrue(featured.is_featured)
        self.assertEqual(featured.author, "Community Builder")
        self.assertEqual(featured.maintainer, "Community Curators")

    def test_registry_page_keeps_bundled_skills_visible_when_runtime_suites_are_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
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

            with (
                patch("services.skill_registry_service.SKILLS_DIR", skills_dir),
                patch("services.skill_registry_service.CUSTOM_DIR", custom_dir),
                patch("services.skill_test_harness_service.SKILLS_DIR", skills_dir),
                patch("services.skill_test_harness_service.REPO_ROOT", repo_root),
            ):
                page = fetch_skill_registry_page()

        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items[0].id, "terraform")
        assert page.items[0].test_results is not None
        self.assertEqual(page.items[0].test_results.status, "missing")
        self.assertEqual(page.items[0].test_results.total_scenarios, 0)


if __name__ == "__main__":
    unittest.main()
