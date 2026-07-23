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
            (project_root / "docs/skills").mkdir(parents=True)
            (project_root / "docs/skills/authoring-guide.md").write_text(
                "# Skill Authoring\n",
                encoding="utf-8",
            )
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
                "supported_toolchains: [terraform]\n"
                "trust_level: core\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [docs/skills/authoring-guide.md]\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                expected_name="terraform",
                strict_manifest=True,
                project_root=project_root,
            )

        assert document.manifest is not None
        self.assertEqual(document.manifest.name, "terraform")
        self.assertEqual(document.manifest.version, "1.0.0")
        self.assertEqual(document.manifest.supported_toolchains, ["terraform"])
        self.assertEqual(document.manifest.trust_level, "core")
        self.assertEqual(
            document.manifest.scenario_references, ["tests/skill-tests/terraform"]
        )
        self.assertEqual(
            document.manifest.documentation_links,
            ["docs/skills/authoring-guide.md"],
        )
        self.assertEqual(document.body, "# Terraform\nGuidance.")

    def test_strict_manifest_validation_reports_missing_v1_contract_fields(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
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

        message = str(ctx.exception)
        self.assertIn("supported_toolchains", message)
        self.assertIn("trust_level", message)
        self.assertIn("scenario_references", message)
        self.assertIn("documentation_links", message)

    def test_strict_manifest_validation_accepts_full_semver(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
            document = parse_skill_document(
                "---\n"
                "name: terraform\n"
                "version: 1.2.0-rc.1+build.5\n"
                "author: DeployWhisper\n"
                "license: MIT\n"
                "triggers: [.tf]\n"
                "token_budget: 1200\n"
                "tags: [terraform, iac]\n"
                "description: Terraform review guidance.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "supported_toolchains: [terraform]\n"
                "trust_level: core\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                expected_name="terraform",
                strict_manifest=True,
                project_root=project_root,
            )

        assert document.manifest is not None
        self.assertEqual(document.manifest.version, "1.2.0-rc.1+build.5")

    def test_strict_manifest_validation_rejects_non_semver_versions(self) -> None:
        for version in ("01.2.0", "1.02.0", "1.2", "1.2.0-01"):
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as tmpdir:
                    project_root = Path(tmpdir)
                    (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
                    with self.assertRaises(SkillManifestValidationError) as ctx:
                        parse_skill_document(
                            "---\n"
                            "name: terraform\n"
                            f"version: {version}\n"
                            "author: DeployWhisper\n"
                            "license: MIT\n"
                            "triggers: [.tf]\n"
                            "token_budget: 1200\n"
                            "tags: [terraform, iac]\n"
                            "description: Terraform review guidance.\n"
                            "test_suite_path: tests/skill-tests/terraform\n"
                            "supported_toolchains: [terraform]\n"
                            "trust_level: core\n"
                            "scenario_references: [tests/skill-tests/terraform]\n"
                            "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                            "---\n"
                            "# Terraform\nGuidance.\n",
                            expected_name="terraform",
                            strict_manifest=True,
                            project_root=project_root,
                        )

                self.assertIn("version", str(ctx.exception))

    def test_strict_manifest_validation_rejects_invalid_trust_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
            (project_root / "docs/skills").mkdir(parents=True)
            (project_root / "docs/skills/authoring-guide.md").write_text(
                "# Skill Authoring\n",
                encoding="utf-8",
            )
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
                    "supported_toolchains: [terraform]\n"
                    "trust_level: production-root\n"
                    "scenario_references: [tests/skill-tests/terraform]\n"
                    "documentation_links: [docs/skills/authoring-guide.md]\n"
                    "---\n"
                    "# Terraform\nGuidance.\n",
                    expected_name="terraform",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("trust_level", str(ctx.exception))

    def test_strict_manifest_validation_rejects_uppercase_skill_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/helm").mkdir(parents=True)
            with self.assertRaises(SkillManifestValidationError) as ctx:
                parse_skill_document(
                    "---\n"
                    "name: Helm\n"
                    "version: 1.0.0\n"
                    "author: Community\n"
                    "license: MIT\n"
                    "triggers: [Chart.yaml]\n"
                    "token_budget: 900\n"
                    "tags: [helm]\n"
                    "description: Helm review guidance.\n"
                    "test_suite_path: tests/skill-tests/helm\n"
                    "supported_toolchains: [helm]\n"
                    "trust_level: verified\n"
                    "scenario_references: [tests/skill-tests/helm]\n"
                    "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
                    "---\n"
                    "# Helm\nGuidance.\n",
                    expected_name="helm",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("name", str(ctx.exception))

    def test_strict_manifest_validation_rejects_missing_scenario_reference(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
            (project_root / "docs/skills").mkdir(parents=True)
            (project_root / "docs/skills/authoring-guide.md").write_text(
                "# Skill Authoring\n",
                encoding="utf-8",
            )
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
                    "supported_toolchains: [terraform]\n"
                    "trust_level: core\n"
                    "scenario_references: [tests/skill-tests/missing]\n"
                    "documentation_links: [docs/skills/authoring-guide.md]\n"
                    "---\n"
                    "# Terraform\nGuidance.\n",
                    expected_name="terraform",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("scenario_references", str(ctx.exception))
        self.assertIn("path does not exist", str(ctx.exception))

    def test_strict_manifest_validation_rejects_missing_documentation_link(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
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
                    "supported_toolchains: [terraform]\n"
                    "trust_level: core\n"
                    "scenario_references: [tests/skill-tests/terraform]\n"
                    "documentation_links: [docs/skills/missing.md]\n"
                    "---\n"
                    "# Terraform\nGuidance.\n",
                    expected_name="terraform",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("documentation_links", str(ctx.exception))
        self.assertIn("path does not exist", str(ctx.exception))

    def test_strict_manifest_validation_rejects_malformed_documentation_urls(
        self,
    ) -> None:
        for documentation_link in (
            "https://",
            "https://:443",
            "https://docs.deploywhisper.example:99999/skills/terraform",
            "http:///broken",
            "https://exa mple.com/path",
            "https://example.com/a path",
            "https://example.com/\\bad",
        ):
            with self.subTest(documentation_link=documentation_link):
                with tempfile.TemporaryDirectory() as tmpdir:
                    project_root = Path(tmpdir)
                    (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
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
                            "supported_toolchains: [terraform]\n"
                            "trust_level: core\n"
                            "scenario_references: [tests/skill-tests/terraform]\n"
                            f"documentation_links: ['{documentation_link}']\n"
                            "---\n"
                            "# Terraform\nGuidance.\n",
                            expected_name="terraform",
                            strict_manifest=True,
                            project_root=project_root,
                        )

                self.assertIn("documentation_links", str(ctx.exception))
                self.assertIn("valid HTTP(S) URLs", str(ctx.exception))

    def test_strict_manifest_validation_rejects_name_and_version_whitespace(
        self,
    ) -> None:
        for field_name, value in (
            ("name", '" terraform "'),
            ("version", '"1.0.0 "'),
        ):
            with self.subTest(field_name=field_name):
                with tempfile.TemporaryDirectory() as tmpdir:
                    project_root = Path(tmpdir)
                    (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
                    name = "terraform"
                    version = "1.0.0"
                    if field_name == "name":
                        name = value
                    else:
                        version = value
                    with self.assertRaises(SkillManifestValidationError) as ctx:
                        parse_skill_document(
                            "---\n"
                            f"name: {name}\n"
                            f"version: {version}\n"
                            "author: DeployWhisper\n"
                            "license: MIT\n"
                            "triggers: [.tf]\n"
                            "token_budget: 1200\n"
                            "tags: [terraform, iac]\n"
                            "description: Terraform review guidance.\n"
                            "test_suite_path: tests/skill-tests/terraform\n"
                            "supported_toolchains: [terraform]\n"
                            "trust_level: core\n"
                            "scenario_references: [tests/skill-tests/terraform]\n"
                            "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                            "---\n"
                            "# Terraform\nGuidance.\n",
                            expected_name="terraform",
                            strict_manifest=True,
                            project_root=project_root,
                        )

                self.assertIn(field_name, str(ctx.exception))
                self.assertIn("leading or trailing whitespace", str(ctx.exception))

    def test_strict_manifest_validation_rejects_repo_reference_escape_shapes(
        self,
    ) -> None:
        cases = (
            ("test_suite_path", "https://example.com/tests"),
            ("test_suite_path", "C:\\tests\\terraform"),
            ("scenario_references", "../outside"),
            ("scenario_references", "..\\outside"),
            ("documentation_links", "/tmp/guide.md"),
            ("documentation_links", "C:\\docs\\guide.md"),
            ("documentation_links", "\\\\server\\share\\guide.md"),
        )
        for field_name, value in cases:
            with self.subTest(field_name=field_name, value=value):
                with tempfile.TemporaryDirectory() as tmpdir:
                    project_root = Path(tmpdir)
                    (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
                    (project_root / "docs/skills").mkdir(parents=True)
                    (project_root / "docs/skills/authoring-guide.md").write_text(
                        "# Skill Authoring\n",
                        encoding="utf-8",
                    )
                    scenario_references = "tests/skill-tests/terraform"
                    documentation_links = "docs/skills/authoring-guide.md"
                    test_suite_path = "tests/skill-tests/terraform"
                    if field_name == "test_suite_path":
                        test_suite_path = value
                    elif field_name == "scenario_references":
                        scenario_references = value
                    else:
                        documentation_links = value
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
                            f"test_suite_path: {test_suite_path}\n"
                            "supported_toolchains: [terraform]\n"
                            "trust_level: core\n"
                            f"scenario_references: [{scenario_references}]\n"
                            f"documentation_links: [{documentation_links}]\n"
                            "---\n"
                            "# Terraform\nGuidance.\n",
                            expected_name="terraform",
                            strict_manifest=True,
                            project_root=project_root,
                        )

                self.assertIn(field_name, str(ctx.exception))

    def test_strict_manifest_validation_allows_local_link_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "tests/skill-tests/terraform").mkdir(parents=True)
            (project_root / "docs/skills").mkdir(parents=True)
            (project_root / "docs/skills/authoring-guide.md").write_text(
                "# Skill Authoring\n",
                encoding="utf-8",
            )
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
                "supported_toolchains: [terraform]\n"
                "trust_level: core\n"
                "scenario_references: [tests/skill-tests/terraform#baseline]\n"
                "documentation_links: [docs/skills/authoring-guide.md#manifest-v1]\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                expected_name="terraform",
                strict_manifest=True,
                project_root=project_root,
            )

        assert document.manifest is not None
        self.assertEqual(
            document.manifest.documentation_links,
            ["docs/skills/authoring-guide.md#manifest-v1"],
        )

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
                    "supported_toolchains: [helm]\n"
                    "trust_level: core\n"
                    "scenario_references: [tests/skill-tests/helm]\n"
                    "documentation_links: [https://docs.deploywhisper.example/skills/helm]\n"
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
                    "supported_toolchains: [terraform]\n"
                    "trust_level: core\n"
                    "scenario_references: [tests/skill-tests/terraform]\n"
                    "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
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
        self.assertIn("supported_toolchains", payload["required"])
        self.assertIn("trust_level", payload["required"])
        self.assertIn("scenario_references", payload["required"])
        self.assertIn("documentation_links", payload["required"])
        self.assertEqual(
            payload["properties"]["name"]["pattern"],
            r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        )
        version_pattern = payload["properties"]["version"]["pattern"]
        self.assertRegex("1.2.0-rc.1+build.5", version_pattern)
        self.assertNotRegex("01.2.0", version_pattern)
        self.assertIn("pattern", payload["properties"]["test_suite_path"])
        documentation_links = payload["properties"]["documentation_links"]
        self.assertEqual(
            documentation_links["description"],
            "Repo-relative documentation paths or HTTP(S) links for authors.",
        )
        documentation_url_pattern = documentation_links["items"]["anyOf"][0]["pattern"]
        self.assertRegex(
            "HTTPS://docs.deploywhisper.example/skills/terraform",
            documentation_url_pattern,
        )
        self.assertNotRegex("https://:443", documentation_url_pattern)
        self.assertNotRegex(
            "https://docs.deploywhisper.example:99999/skills/terraform",
            documentation_url_pattern,
        )

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
                "supported_toolchains: [community-skill]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/community-skill]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/community-skill]\n"
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
                    "supported_toolchains: [official-skill]\n"
                    "trust_level: core\n"
                    "scenario_references: [tests/skill-tests/official-skill]\n"
                    "documentation_links: [https://docs.deploywhisper.example/skills/official-skill]\n"
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
                    "supported_toolchains: [official-skill]\n"
                    "trust_level: core\n"
                    "scenario_references: [tests/skill-tests/official-skill]\n"
                    "documentation_links: [https://docs.deploywhisper.example/skills/official-skill]\n"
                    "---\n"
                    "# Official Skill\nGuidance.\n",
                    expected_name="official-skill",
                    strict_manifest=True,
                    project_root=project_root,
                )

        self.assertIn("community-authored", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
