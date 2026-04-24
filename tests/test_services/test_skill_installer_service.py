"""Tests for registry-backed skill installer operations."""

from __future__ import annotations

from hashlib import sha256
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.skill_installer_service import (
    SkillInstallerError,
    install_skill,
    list_installed_skills,
    remove_skill,
    update_skill,
)


class _FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class SkillInstallerServiceTests(unittest.TestCase):
    def test_install_skill_fetches_registry_content_into_custom_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            content = (
                "---\n"
                "name: helm\n"
                "version: 1.2.0\n"
                "author: Community\n"
                "license: MIT\n"
                "triggers: [Chart.yaml]\n"
                "token_budget: 900\n"
                "tags: [helm]\n"
                "description: Helm rollout checks.\n"
                "test_suite_path: tests/skill-tests/helm\n"
                "---\n"
                "# Helm\nCommunity guidance.\n"
            )
            response_payload = {
                "data": {
                    "id": "helm",
                    "version": "1.2.0",
                    "content": content,
                    "sha256": sha256(content.encode("utf-8")).hexdigest(),
                }
            }

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_registry_base_url="https://registry.example.com"
                    ),
                ),
                patch(
                    "services.skill_installer_service.request.urlopen",
                    return_value=_FakeHttpResponse(response_payload),
                ) as mocked_urlopen,
            ):
                result = install_skill("helm")
                self.assertEqual(result.action, "installed")
                self.assertEqual(result.skill_id, "helm")
                self.assertEqual(result.version, "1.2.0")
                self.assertEqual(result.mode, "new")
                installed_path = Path(result.destination)
                self.assertTrue(installed_path.exists())
                self.assertEqual(installed_path.read_text(encoding="utf-8"), content)
                request_url = mocked_urlopen.call_args.args[0].full_url
                self.assertEqual(
                    request_url,
                    "https://registry.example.com/api/v1/skills/helm/content",
                )

    def test_update_skill_replaces_existing_custom_file_with_latest_version(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "helm.md").write_text(
                "---\n"
                "name: helm\n"
                "version: 1.0.0\n"
                "author: Community\n"
                "license: MIT\n"
                "triggers: [Chart.yaml]\n"
                "token_budget: 900\n"
                "tags: [helm]\n"
                "description: Helm rollout checks.\n"
                "test_suite_path: tests/skill-tests/helm\n"
                "---\n"
                "# Helm\nOld guidance.\n",
                encoding="utf-8",
            )
            content = (
                "---\n"
                "name: helm\n"
                "version: 1.2.0\n"
                "author: Community\n"
                "license: MIT\n"
                "triggers: [Chart.yaml]\n"
                "token_budget: 900\n"
                "tags: [helm]\n"
                "description: Helm rollout checks.\n"
                "test_suite_path: tests/skill-tests/helm\n"
                "---\n"
                "# Helm\nNew guidance.\n"
            )
            response_payload = {
                "data": {
                    "id": "helm",
                    "version": "1.2.0",
                    "content": content,
                    "sha256": sha256(content.encode("utf-8")).hexdigest(),
                }
            }

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_registry_base_url="https://registry.example.com"
                    ),
                ),
                patch(
                    "services.skill_installer_service.request.urlopen",
                    return_value=_FakeHttpResponse(response_payload),
                ),
            ):
                result = update_skill("helm")

            updated_path = custom_dir / "helm.md"
            self.assertEqual(result.action, "updated")
            self.assertEqual(result.previous_version, "1.0.0")
            self.assertEqual(result.version, "1.2.0")
            self.assertEqual(updated_path.read_text(encoding="utf-8"), content)

    def test_update_skill_rewrites_drifted_file_even_when_version_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            installed_path = custom_dir / "helm.md"
            installed_path.write_text(
                "---\n"
                "name: helm\n"
                "version: 1.2.0\n"
                "author: Community\n"
                "license: MIT\n"
                "triggers: [Chart.yaml]\n"
                "token_budget: 900\n"
                "tags: [helm]\n"
                "description: Helm rollout checks.\n"
                "test_suite_path: tests/skill-tests/helm\n"
                "---\n"
                "# Helm\nLocally drifted guidance.\n",
                encoding="utf-8",
            )
            registry_content = (
                "---\n"
                "name: helm\n"
                "version: 1.2.0\n"
                "author: Community\n"
                "license: MIT\n"
                "triggers: [Chart.yaml]\n"
                "token_budget: 900\n"
                "tags: [helm]\n"
                "description: Helm rollout checks.\n"
                "test_suite_path: tests/skill-tests/helm\n"
                "---\n"
                "# Helm\nCanonical registry guidance.\n"
            )
            response_payload = {
                "data": {
                    "id": "helm",
                    "version": "1.2.0",
                    "content": registry_content,
                    "sha256": sha256(registry_content.encode("utf-8")).hexdigest(),
                }
            }

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_registry_base_url="https://registry.example.com"
                    ),
                ),
                patch(
                    "services.skill_installer_service.request.urlopen",
                    return_value=_FakeHttpResponse(response_payload),
                ),
            ):
                result = update_skill("helm")

            self.assertEqual(result.action, "updated")
            self.assertEqual(result.previous_version, "1.2.0")
            self.assertEqual(result.version, "1.2.0")
            self.assertEqual(
                installed_path.read_text(encoding="utf-8"), registry_content
            )

    def test_remove_skill_deletes_installed_custom_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            installed_path = custom_dir / "helm.md"
            installed_path.write_text(
                "---\n"
                "name: helm\n"
                "version: 1.1.0\n"
                "author: Community\n"
                "license: MIT\n"
                "triggers: [Chart.yaml]\n"
                "token_budget: 900\n"
                "tags: [helm]\n"
                "description: Helm rollout checks.\n"
                "test_suite_path: tests/skill-tests/helm\n"
                "---\n"
                "# Helm\nGuidance.\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
            ):
                result = remove_skill("helm")

        self.assertEqual(result.action, "removed")
        self.assertEqual(result.previous_version, "1.1.0")
        self.assertFalse(Path(result.destination).exists())

    def test_list_installed_skills_reports_override_and_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Built-in\nTerraform guidance.\n",
                encoding="utf-8",
            )
            (custom_dir / "terraform.md").write_text(
                "---\n"
                "name: terraform\n"
                "version: 3.0.0\n"
                "author: Team Ops\n"
                "license: Proprietary\n"
                "triggers: [.tf]\n"
                "token_budget: 500\n"
                "tags: [terraform]\n"
                "description: Team terraform guidance.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "---\n"
                "# Terraform\nOverride guidance.\n",
                encoding="utf-8",
            )
            (custom_dir / "broken.md").write_text(
                "---\ninvalid: [\n---\n", encoding="utf-8"
            )

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
            ):
                entries = list_installed_skills()

        self.assertEqual([entry.id for entry in entries], ["broken", "terraform"])
        self.assertFalse(entries[0].active)
        self.assertEqual(entries[1].mode, "override")
        self.assertEqual(entries[1].version, "3.0.0")

    def test_install_skill_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "helm.md").write_text("# Existing\n", encoding="utf-8")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

        self.assertEqual(ctx.exception.code, "skill_already_installed")

    def test_install_skill_rejects_invalid_skill_id(self) -> None:
        with self.assertRaises(SkillInstallerError) as ctx:
            install_skill("../helm")

        self.assertEqual(ctx.exception.code, "invalid_skill_id")


if __name__ == "__main__":
    unittest.main()
