"""Tests for configured-source skill installer operations."""

from __future__ import annotations

from hashlib import sha256
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib import request

from services.skill_installer_service import (
    SkillInstallerError,
    _RegistryRedirectHandler,
    install_skill,
    list_installed_skills,
    remove_skill,
    update_skill,
)


class _FakeHttpResponse:
    def __init__(
        self,
        payload: object | bytes,
        *,
        final_url: str | None = None,
    ) -> None:
        self._payload = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )
        self._final_url = final_url

    def read(self) -> bytes:
        return self._payload

    def geturl(self) -> str:
        if self._final_url is None:
            raise AttributeError("final URL not set")
        return self._final_url

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class SkillInstallerServiceTests(unittest.TestCase):
    @staticmethod
    def _local_skill_content(
        *,
        version: str = "1.2.0",
        guidance: str = "Community guidance.",
    ) -> str:
        return (
            "---\n"
            "name: helm\n"
            f"version: {version}\n"
            "author: Community\n"
            "license: MIT\n"
            "triggers: [Chart.yaml]\n"
            "token_budget: 900\n"
            "tags: [helm]\n"
            "description: Helm rollout checks.\n"
            "test_suite_path: tests/skill-tests/helm\n"
            "supported_toolchains: [helm]\n"
            "trust_level: verified\n"
            "scenario_references: [tests/skill-tests/helm]\n"
            "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
            "---\n"
            f"# Helm\n{guidance}\n"
        )

    def test_install_skill_reads_configured_local_source_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            source_dir = repo_root / "private-skills"
            skills_dir.mkdir(parents=True)
            source_dir.mkdir()
            content = self._local_skill_content()
            source_path = source_dir / "helm.md"
            source_path.write_text(content, encoding="utf-8")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url="https://registry.example.com",
                    ),
                ),
                patch(
                    "services.skill_installer_service._open_registry_request"
                ) as mocked_open,
            ):
                result = install_skill("helm")

            self.assertEqual(result.action, "installed")
            self.assertEqual(result.version, "1.2.0")
            self.assertEqual(result.source_url, source_path.resolve().as_uri())
            self.assertEqual(
                (custom_dir / "helm.md").read_text(encoding="utf-8"),
                content,
            )
            mocked_open.assert_not_called()

    def test_update_skill_refreshes_from_configured_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            source_dir = repo_root / "private-skills"
            custom_dir.mkdir(parents=True)
            source_dir.mkdir()
            installed_path = custom_dir / "helm.md"
            installed_path.write_text(
                self._local_skill_content(
                    version="1.0.0",
                    guidance="Old guidance.",
                ),
                encoding="utf-8",
            )
            source_content = self._local_skill_content(
                version="1.2.0",
                guidance="New private guidance.",
            )
            (source_dir / "helm.md").write_text(source_content, encoding="utf-8")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                result = update_skill("helm")

            self.assertEqual(result.action, "updated")
            self.assertEqual(result.previous_version, "1.0.0")
            self.assertEqual(result.version, "1.2.0")
            self.assertEqual(installed_path.read_text(encoding="utf-8"), source_content)

    def test_invalid_local_source_never_writes_or_executes_skill_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            source_dir = repo_root / "private-skills"
            marker_path = repo_root / "untrusted-content-executed"
            skills_dir.mkdir(parents=True)
            source_dir.mkdir()
            (source_dir / "helm.md").write_text(
                "---\n"
                "name: ../helm\n"
                "version: not-semver\n"
                "---\n"
                f"# Untrusted\nopen({str(marker_path)!r}, 'w').write('executed')\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "invalid_skill_manifest")
            self.assertFalse((custom_dir / "helm.md").exists())
            self.assertFalse(marker_path.exists())

    def test_invalid_local_update_preserves_installed_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            source_dir = repo_root / "private-skills"
            custom_dir.mkdir(parents=True)
            source_dir.mkdir()
            installed_path = custom_dir / "helm.md"
            installed_content = self._local_skill_content(version="1.0.0")
            installed_path.write_text(installed_content, encoding="utf-8")
            (source_dir / "helm.md").write_text(
                "---\nname: wrong-name\nversion: 2.0.0\n---\n# Invalid\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    update_skill("helm")

            self.assertEqual(ctx.exception.code, "invalid_skill_manifest")
            self.assertEqual(
                installed_path.read_text(encoding="utf-8"),
                installed_content,
            )

    def test_update_write_failure_preserves_installed_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            source_dir = repo_root / "private-skills"
            custom_dir.mkdir(parents=True)
            source_dir.mkdir()
            installed_path = custom_dir / "helm.md"
            installed_content = self._local_skill_content(version="1.0.0")
            installed_path.write_text(installed_content, encoding="utf-8")
            (source_dir / "helm.md").write_text(
                self._local_skill_content(version="2.0.0"),
                encoding="utf-8",
            )

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
                patch.object(Path, "replace", side_effect=OSError("disk full")),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    update_skill("helm")

            self.assertEqual(ctx.exception.code, "skill_write_failed")
            self.assertEqual(
                installed_path.read_text(encoding="utf-8"),
                installed_content,
            )
            self.assertEqual(list(custom_dir.glob(".helm.md.*.tmp")), [])

    def test_local_source_rejects_missing_skill_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            source_dir = repo_root / "private-skills"
            skills_dir.mkdir()
            source_dir.mkdir()

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skill_source_not_found")
            self.assertEqual(ctx.exception.details["skill_id"], "helm")

    def test_install_skill_reports_all_supported_source_configuration_options(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            skills_dir.mkdir()
            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=None,
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_source_unconfigured")
        self.assertIn("DEPLOYWHISPER_SKILLS_SOURCE_DIR", ctx.exception.message)
        self.assertIn("DEPLOYWHISPER_SKILLS_REGISTRY_URL", ctx.exception.message)

    def test_local_source_rejects_symlink_outside_configured_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            source_dir = repo_root / "private-skills"
            outside_dir = repo_root / "outside"
            skills_dir.mkdir()
            source_dir.mkdir()
            outside_dir.mkdir()
            outside_path = outside_dir / "helm.md"
            outside_path.write_text(self._local_skill_content(), encoding="utf-8")
            (source_dir / "helm.md").symlink_to(outside_path)

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skills_local_source_invalid")

    def test_local_source_rejects_symlink_swap_between_validation_and_read(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            source_dir = repo_root / "private-skills"
            outside_path = repo_root / "outside.md"
            skills_dir.mkdir()
            source_dir.mkdir()
            source_path = source_dir / "helm.md"
            source_path.write_text(self._local_skill_content(), encoding="utf-8")
            outside_path.write_text(self._local_skill_content(), encoding="utf-8")
            real_open = os.open
            source_opened = False

            def swap_before_file_open(path, flags, *args, **kwargs):
                nonlocal source_opened
                if kwargs.get("dir_fd") is not None and not source_opened:
                    source_opened = True
                    source_path.unlink()
                    source_path.symlink_to(outside_path)
                return real_open(path, flags, *args, **kwargs)

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
                patch(
                    "services.skill_installer_service.os.open",
                    side_effect=swap_before_file_open,
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skills_local_source_invalid")
            self.assertFalse((skills_dir / "custom" / "helm.md").exists())

    def test_local_source_reports_non_utf8_file_as_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            source_dir = repo_root / "private-skills"
            skills_dir.mkdir()
            source_dir.mkdir()
            (source_dir / "helm.md").write_bytes(b"\xff\xfe\x00")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skill_source_unreadable")

    def test_local_source_rejects_oversized_file_before_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            source_dir = repo_root / "private-skills"
            skills_dir.mkdir()
            source_dir.mkdir()
            content = self._local_skill_content()
            (source_dir / "helm.md").write_text(content, encoding="utf-8")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
                patch(
                    "services.skill_installer_service.MAX_SKILL_SOURCE_BYTES",
                    len(content.encode("utf-8")) - 1,
                    create=True,
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skill_source_too_large")
            self.assertFalse((skills_dir / "custom" / "helm.md").exists())

    def test_local_source_reports_permission_failure_as_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            source_dir = repo_root / "private-skills"
            skills_dir.mkdir()
            source_dir.mkdir()
            (source_dir / "helm.md").write_text(
                self._local_skill_content(),
                encoding="utf-8",
            )
            real_stat = os.stat

            def deny_skill_stat(path, *args, **kwargs):
                if Path(path).name == "helm.md":
                    raise PermissionError("permission denied")
                return real_stat(path, *args, **kwargs)

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
                patch(
                    "services.skill_installer_service.os.stat",
                    side_effect=deny_skill_stat,
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skill_source_unreadable")

    def test_configured_local_source_reports_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            missing_source_dir = repo_root / "missing-private-skills"
            skills_dir.mkdir()

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(missing_source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skills_local_source_unavailable")

    def test_configured_local_source_rejects_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            source_path = repo_root / "private-skills"
            skills_dir.mkdir()
            source_path.write_text("not a directory", encoding="utf-8")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch(
                    "services.skill_installer_service.CUSTOM_DIR",
                    skills_dir / "custom",
                ),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_path),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

            self.assertEqual(ctx.exception.code, "skills_local_source_invalid")

    def test_update_skill_reports_unchanged_for_matching_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            source_dir = repo_root / "private-skills"
            custom_dir.mkdir(parents=True)
            source_dir.mkdir()
            content = self._local_skill_content()
            installed_path = custom_dir / "helm.md"
            installed_path.write_text(content, encoding="utf-8")
            (source_dir / "helm.md").write_text(content, encoding="utf-8")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_local_source_dir=str(source_dir),
                        skills_registry_base_url=None,
                    ),
                ),
            ):
                result = update_skill("helm")

            self.assertEqual(result.action, "unchanged")
            self.assertEqual(result.previous_version, "1.2.0")
            self.assertEqual(installed_path.read_text(encoding="utf-8"), content)

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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [docs/skills/helm.md]\n"
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
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(response_payload),
                ) as mocked_open,
            ):
                result = install_skill("helm")
                self.assertEqual(result.action, "installed")
                self.assertEqual(result.skill_id, "helm")
                self.assertEqual(result.version, "1.2.0")
                self.assertEqual(result.mode, "new")
                installed_path = Path(result.destination)
                self.assertTrue(installed_path.exists())
                self.assertEqual(installed_path.read_text(encoding="utf-8"), content)
                request_url = mocked_open.call_args.args[0].full_url
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
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
                    "services.skill_installer_service._open_registry_request",
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
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
                    "services.skill_installer_service._open_registry_request",
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

    def test_install_skill_accepts_registry_owned_missing_references(
        self,
    ) -> None:
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/missing]\n"
                "documentation_links: [docs/skills/missing.md]\n"
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
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(response_payload),
                ),
            ):
                result = install_skill("helm")

        self.assertEqual(result.action, "installed")
        self.assertEqual(result.skill_id, "helm")

    def test_install_skill_rejects_registry_content_with_unsafe_references(
        self,
    ) -> None:
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [../outside]\n"
                "documentation_links: [docs/skills/helm.md]\n"
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
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(response_payload),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

        self.assertEqual(ctx.exception.code, "invalid_skill_manifest")
        self.assertIn("scenario_references", ctx.exception.details["issues"])

    def test_install_skill_rejects_insecure_registry_redirect(self) -> None:
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [docs/skills/helm.md]\n"
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
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(
                        response_payload,
                        final_url="http://registry.example.com/api/v1/skills/helm/content",
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_insecure_redirect")

    def test_registry_redirect_handler_rejects_insecure_redirect_before_following(
        self,
    ) -> None:
        handler = _RegistryRedirectHandler()
        req = request.Request("https://registry.example.com/api/v1/skills/helm/content")

        with self.assertRaises(SkillInstallerError) as ctx:
            handler.redirect_request(
                req,
                None,
                302,
                "Found",
                {},
                "http://registry.example.com/api/v1/skills/helm/content",
            )

        self.assertEqual(ctx.exception.code, "skills_registry_insecure_redirect")

    def test_registry_redirect_handler_rejects_host_change_before_following(
        self,
    ) -> None:
        handler = _RegistryRedirectHandler()
        req = request.Request("https://registry.example.com/api/v1/skills/helm/content")

        with self.assertRaises(SkillInstallerError) as ctx:
            handler.redirect_request(
                req,
                None,
                302,
                "Found",
                {},
                "https://evil.example.com/api/v1/skills/helm/content",
            )

        self.assertEqual(ctx.exception.code, "skills_registry_redirect_host_mismatch")

    def test_install_skill_rejects_registry_redirect_to_different_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            response_payload = {"data": {"content": "# not trusted yet"}}

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
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(
                        response_payload,
                        final_url="https://evil.example.com/api/v1/skills/helm/content",
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_redirect_host_mismatch")

    def test_install_skill_rejects_registry_redirect_to_different_port(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            response_payload = {"data": {"content": "# not trusted yet"}}

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
                patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(
                        skills_registry_base_url="https://registry.example.com:8443"
                    ),
                ),
                patch(
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(
                        response_payload,
                        final_url="https://registry.example.com/api/v1/skills/helm/content",
                    ),
                ),
            ):
                with self.assertRaises(SkillInstallerError) as ctx:
                    install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_redirect_host_mismatch")

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
                "supported_toolchains: [helm]\n"
                "trust_level: experimental\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
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
                "supported_toolchains: [terraform]\n"
                "trust_level: experimental\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                "---\n"
                "# Terraform\nOverride guidance.\n",
                encoding="utf-8",
            )
            (custom_dir / "broken.md").write_text(
                "---\ninvalid: [\n---\n", encoding="utf-8"
            )
            (custom_dir / "invalid-v1.md").write_text(
                "---\n"
                "name: invalid-v1\n"
                "version: 3.0.0\n"
                "author: Team Ops\n"
                "license: Proprietary\n"
                "triggers: [.tf]\n"
                "token_budget: 500\n"
                "tags: [terraform]\n"
                "description: Missing required v1 fields.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "---\n"
                "# Invalid\nBroken v1 guidance.\n",
                encoding="utf-8",
            )
            (custom_dir / "legacy.md").write_text(
                "# Legacy\nNo v1 manifest yet.\n",
                encoding="utf-8",
            )
            (custom_dir / "legacy-name.md").write_text(
                "---\n"
                "skill: legacy-name\n"
                "version: 3.0.0\n"
                "author: Team Ops\n"
                "license: Proprietary\n"
                "triggers: [.tf]\n"
                "token_budget: 500\n"
                "tags: [terraform]\n"
                "description: Legacy name metadata.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "supported_toolchains: [terraform]\n"
                "trust_level: experimental\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                "---\n"
                "# Legacy Name\nBroken v1 guidance.\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
            ):
                entries = list_installed_skills()

        self.assertEqual(
            [entry.id for entry in entries],
            ["broken", "invalid-v1", "legacy-name", "legacy", "terraform"],
        )
        self.assertFalse(entries[0].active)
        self.assertFalse(entries[1].active)
        self.assertIn("supported_toolchains", entries[1].warning or "")
        self.assertFalse(entries[2].active)
        self.assertIn("name", entries[2].warning or "")
        self.assertFalse(entries[3].active)
        self.assertIsNone(entries[3].version)
        self.assertIn("frontmatter", entries[3].warning or "")
        self.assertEqual(entries[4].mode, "override")
        self.assertEqual(entries[4].version, "3.0.0")

    def test_list_installed_skills_reports_non_utf8_entry_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "bad.md").write_bytes(b"\xff")
            (custom_dir / "legacy.md").write_text(
                "# Legacy\nNo v1 manifest yet.\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
            ):
                entries = list_installed_skills()

        self.assertEqual([entry.id for entry in entries], ["bad", "legacy"])
        self.assertFalse(entries[0].active)
        self.assertIn("UTF-8", entries[0].warning or "")
        self.assertFalse(entries[1].active)
        self.assertIn("frontmatter", entries[1].warning or "")

    def test_list_installed_skills_reports_empty_entry_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (custom_dir / "empty.md").write_text("   ", encoding="utf-8")

            with (
                patch("services.skill_installer_service.SKILLS_DIR", skills_dir),
                patch("services.skill_installer_service.CUSTOM_DIR", custom_dir),
            ):
                entries = list_installed_skills()

        self.assertEqual([entry.id for entry in entries], ["empty"])
        self.assertFalse(entries[0].active)
        self.assertIn("body", entries[0].warning or "")

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

    def test_install_skill_rejects_non_http_registry_url(self) -> None:
        with patch(
            "services.skill_installer_service.settings",
            SimpleNamespace(skills_registry_base_url="file:///tmp/skills"),
        ):
            with self.assertRaises(SkillInstallerError) as ctx:
                install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_invalid_url")

    def test_install_skill_rejects_hostless_registry_url(self) -> None:
        for base_url in ("https://:443", "https://"):
            with self.subTest(base_url=base_url):
                with patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(skills_registry_base_url=base_url),
                ):
                    with self.assertRaises(SkillInstallerError) as ctx:
                        install_skill("helm")

                self.assertEqual(ctx.exception.code, "skills_registry_invalid_url")

    def test_install_skill_rejects_registry_url_credentials_without_leaking_them(
        self,
    ) -> None:
        with patch(
            "services.skill_installer_service.settings",
            SimpleNamespace(
                skills_registry_base_url="https://user:secret@registry.example.com"
            ),
        ):
            with self.assertRaises(SkillInstallerError) as ctx:
                install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_invalid_url")
        self.assertNotIn("secret", str(ctx.exception.details))
        self.assertEqual(
            ctx.exception.details,
            {"url": "https://registry.example.com"},
        )

    def test_install_skill_redacts_malformed_registry_url_credentials(self) -> None:
        with patch(
            "services.skill_installer_service.settings",
            SimpleNamespace(skills_registry_base_url="https://user:secret@"),
        ):
            with self.assertRaises(SkillInstallerError) as ctx:
                install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_invalid_url")
        self.assertNotIn("secret", str(ctx.exception.details))

    def test_install_skill_rejects_insecure_remote_http_registry_url(self) -> None:
        with patch(
            "services.skill_installer_service.settings",
            SimpleNamespace(skills_registry_base_url="http://registry.example.com"),
        ):
            with self.assertRaises(SkillInstallerError) as ctx:
                install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_insecure_url")

    def test_install_skill_rejects_registry_base_url_query_or_fragment(self) -> None:
        for base_url in (
            "https://registry.example.com?token=abc",
            "https://registry.example.com#skills",
        ):
            with self.subTest(base_url=base_url):
                with patch(
                    "services.skill_installer_service.settings",
                    SimpleNamespace(skills_registry_base_url=base_url),
                ):
                    with self.assertRaises(SkillInstallerError) as ctx:
                        install_skill("helm")

                self.assertEqual(ctx.exception.code, "skills_registry_invalid_url")

    def test_install_skill_reports_non_utf8_registry_success_as_invalid_response(
        self,
    ) -> None:
        with (
            patch(
                "services.skill_installer_service.settings",
                SimpleNamespace(
                    skills_registry_base_url="https://registry.example.com"
                ),
            ),
            patch(
                "services.skill_installer_service._open_registry_request",
                return_value=_FakeHttpResponse(b"\xff"),
            ),
        ):
            with self.assertRaises(SkillInstallerError) as ctx:
                install_skill("helm")

        self.assertEqual(ctx.exception.code, "skills_registry_invalid_response")

    def test_install_skill_reports_non_object_registry_json_as_invalid_response(
        self,
    ) -> None:
        for response_payload in ([], "ok"):
            with self.subTest(response_payload=response_payload):
                with (
                    patch(
                        "services.skill_installer_service.settings",
                        SimpleNamespace(
                            skills_registry_base_url="https://registry.example.com"
                        ),
                    ),
                    patch(
                        "services.skill_installer_service._open_registry_request",
                        return_value=_FakeHttpResponse(response_payload),
                    ),
                ):
                    with self.assertRaises(SkillInstallerError) as ctx:
                        install_skill("helm")

                self.assertEqual(ctx.exception.code, "skills_registry_invalid_response")

    def test_install_skill_allows_local_http_registry_url(self) -> None:
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [docs/skills/helm.md]\n"
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
                    SimpleNamespace(skills_registry_base_url="http://localhost:8080"),
                ),
                patch(
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(response_payload),
                ),
            ):
                result = install_skill("helm")

        self.assertEqual(result.action, "installed")

    def test_install_skill_allows_loopback_http_registry_url(self) -> None:
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
                "supported_toolchains: [helm]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/helm]\n"
                "documentation_links: [docs/skills/helm.md]\n"
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
                    SimpleNamespace(skills_registry_base_url="http://127.0.1.1:8080"),
                ),
                patch(
                    "services.skill_installer_service._open_registry_request",
                    return_value=_FakeHttpResponse(response_payload),
                ),
            ):
                result = install_skill("helm")

        self.assertEqual(result.action, "installed")


if __name__ == "__main__":
    unittest.main()
