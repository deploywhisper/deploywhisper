"""Tests for shared skill manifest parsing and validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.skill_manifest_service import (
    build_skill_manifest_v1_schema,
    SkillManifestValidationError,
    load_skill_document,
    parse_skill_document,
)


class SkillManifestServiceTests(unittest.TestCase):
    def test_strict_manifest_validation_accepts_v1_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
            document = parse_skill_document(
                "---\n"
                "name: terraform\n"
                "version: 1.0.0\n"
                "author: DeployWhisper\n"
                "license: MIT\n"
                "triggers: [.tf]\n"
                "token_budget: 1200\n"
                "tags: [terraform, iac]\n"
                "description: Terraform review guidance.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                expected_name="terraform",
                strict_manifest=True,
                project_root=project_root,
            )

        assert document.manifest is not None
        self.assertEqual(document.manifest.name, "terraform")
        self.assertEqual(document.manifest.version, "1.0.0")
        self.assertEqual(document.body, "# Terraform\nGuidance.")

    def test_strict_manifest_validation_rejects_name_filename_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/helm").mkdir(parents=True)
            with self.assertRaises(SkillManifestValidationError) as ctx:
                parse_skill_document(
                    "---\n"
                    "name: helm\n"
                    "version: 1.0.0\n"
                    "author: DeployWhisper\n"
                    "license: MIT\n"
                    "triggers: [Chart.yaml]\n"
                    "token_budget: 900\n"
                    "tags: [helm]\n"
                    "description: Helm guidance.\n"
                    "test_suite_path: tests/skill-tests/helm\n"
                    "---\n"
                    "# Helm\nGuidance.\n",
                    expected_name="terraform",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("filename stem", str(ctx.exception))

    def test_strict_manifest_validation_rejects_missing_test_suite_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            with self.assertRaises(SkillManifestValidationError) as ctx:
                parse_skill_document(
                    "---\n"
                    "name: terraform\n"
                    "version: 1.0.0\n"
                    "author: DeployWhisper\n"
                    "license: MIT\n"
                    "triggers: [.tf]\n"
                    "token_budget: 1200\n"
                    "tags: [terraform, iac]\n"
                    "description: Terraform review guidance.\n"
                    "test_suite_path: tests/skill-tests/terraform\n"
                    "---\n"
                    "# Terraform\nGuidance.\n",
                    expected_name="terraform",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("path does not exist", str(ctx.exception))

    def test_non_strict_runtime_mode_keeps_legacy_markdown_compatible(self) -> None:
        document = parse_skill_document(
            "---\ntriggers: [docker-compose.yml]\n---\n# Docker\nGuidance.\n",
            expected_name="docker",
            strict_manifest=False,
            allow_legacy_name=True,
        )

        self.assertIsNone(document.manifest)
        self.assertEqual(document.body, "# Docker\nGuidance.")

    def test_published_schema_file_matches_public_artifact_shape(self) -> None:
        schema_path = Path("schemas/skill-manifest-v1.json")
        payload = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(payload, build_skill_manifest_v1_schema())
        self.assertEqual(payload["$id"], "/schemas/skill-manifest-v1.json")
        self.assertIn("name", payload["required"])
        self.assertIn("triggers", payload["required"])
        self.assertIn("test_suite_path", payload["required"])

    def test_load_skill_document_reads_repo_file_in_strict_mode(self) -> None:
        document = load_skill_document(
            Path("skills/terraform.md"),
            strict_manifest=True,
            allow_legacy_name=False,
            project_root=Path.cwd(),
        )

        assert document.manifest is not None
        self.assertEqual(document.manifest.name, "terraform")
        self.assertEqual(
            document.manifest.test_suite_path, "tests/skill-tests/terraform"
        )

    def test_strict_manifest_allows_featured_community_skill_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/community-skill").mkdir(parents=True)
            document = parse_skill_document(
                "---\n"
                "name: community-skill\n"
                "version: 1.0.0\n"
                "author: Community Builder\n"
                "maintainer: Community Curators\n"
                "featured: true\n"
                "license: MIT\n"
                "triggers: [.yaml]\n"
                "token_budget: 1200\n"
                "tags: [community]\n"
                "description: Community review guidance.\n"
                "test_suite_path: tests/skill-tests/community-skill\n"
                "---\n"
                "# Community Skill\nGuidance.\n",
                expected_name="community-skill",
                strict_manifest=True,
                project_root=project_root,
            )

        assert document.manifest is not None
        self.assertEqual(document.manifest.maintainer, "Community Curators")
        self.assertTrue(document.manifest.featured)

    def test_strict_manifest_rejects_featured_deploywhisper_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/official-skill").mkdir(parents=True)
            with self.assertRaises(SkillManifestValidationError) as ctx:
                parse_skill_document(
                    "---\n"
                    "name: official-skill\n"
                    "version: 1.0.0\n"
                    "author: DeployWhisper\n"
                    "featured: true\n"
                    "license: MIT\n"
                    "triggers: [.tf]\n"
                    "token_budget: 1200\n"
                    "tags: [official]\n"
                    "description: First-party guidance.\n"
                    "test_suite_path: tests/skill-tests/official-skill\n"
                    "---\n"
                    "# Official Skill\nGuidance.\n",
                    expected_name="official-skill",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("featured", str(ctx.exception).lower())

    def test_strict_manifest_rejects_featured_skill_with_deploywhisper_author(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/official-skill").mkdir(parents=True)
            with self.assertRaises(SkillManifestValidationError) as ctx:
                parse_skill_document(
                    "---\n"
                    "name: official-skill\n"
                    "version: 1.0.0\n"
                    "author: DeployWhisper\n"
                    "maintainer: Community Curators\n"
                    "featured: true\n"
                    "license: MIT\n"
                    "triggers: [.tf]\n"
                    "token_budget: 1200\n"
                    "tags: [official]\n"
                    "description: First-party guidance.\n"
                    "test_suite_path: tests/skill-tests/official-skill\n"
                    "---\n"
                    "# Official Skill\nGuidance.\n",
                    expected_name="official-skill",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("community-authored", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
