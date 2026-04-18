"""Tests for custom skill discovery and precedence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analysis.risk_scorer import RiskAssessment, RiskContributor
from llm.skill_context import (
    build_skill_context,
    get_custom_skill_statuses,
    save_custom_skill,
)


class SkillContextTests(unittest.TestCase):
    def _assessment(self, tool: str = "terraform") -> RiskAssessment:
        return RiskAssessment(
            score=20,
            severity="low",
            recommendation="go",
            top_risk="Low-risk change.",
            partial_context=False,
            warnings=[],
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool=tool,
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=5,
                    summary="Summary",
                )
            ],
        )

    def _assessment_with_summary(self, tool: str, summary: str) -> RiskAssessment:
        assessment = self._assessment(tool)
        assessment.contributors[0].summary = summary
        return assessment

    def test_custom_skill_override_takes_precedence_over_built_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Built-in\nDefault terraform guidance.", encoding="utf-8"
            )
            (custom_dir / "terraform.md").write_text(
                "# Custom\nOverride terraform guidance.", encoding="utf-8"
            )
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                skill_context = build_skill_context(self._assessment("terraform"))
        self.assertIn("custom-override", skill_context)
        self.assertIn("Override terraform guidance.", skill_context)
        self.assertNotIn("Default terraform guidance.", skill_context)

    def test_invalid_custom_skill_falls_back_to_built_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Built-in\nDefault terraform guidance.", encoding="utf-8"
            )
            (custom_dir / "terraform.md").write_text(
                "---\ntitle: empty\n---", encoding="utf-8"
            )
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                skill_context = build_skill_context(self._assessment("terraform"))
                statuses = get_custom_skill_statuses()
        self.assertIn("built-in", skill_context)
        self.assertIn("Default terraform guidance.", skill_context)
        self.assertEqual(statuses[0].name, "terraform")
        self.assertFalse(statuses[0].active)

    def test_save_custom_skill_marks_new_skill_when_no_built_in_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                status = save_custom_skill("helm.md", "# Helm\nInternal helm guidance.")
                statuses = get_custom_skill_statuses()
        self.assertEqual(status.mode, "new")
        self.assertTrue(status.active)
        self.assertEqual(statuses[0].name, "helm")

    def test_custom_new_skill_is_included_when_analysis_context_mentions_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Built-in\nDefault terraform guidance.", encoding="utf-8"
            )
            (custom_dir / "helm.md").write_text(
                "# Helm\nInternal helm guidance.", encoding="utf-8"
            )
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                skill_context = build_skill_context(
                    self._assessment_with_summary(
                        "terraform",
                        "Terraform updates the helm release for the api service.",
                    )
                )
        self.assertIn("custom-new", skill_context)
        self.assertIn("Internal helm guidance.", skill_context)

    def test_non_matching_git_skill_is_not_loaded_for_plain_terraform_analysis(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Terraform\nTerraform guidance.", encoding="utf-8"
            )
            (skills_dir / "git.md").write_text(
                "---\nalways_load: true\n---\n# Git\nGit guidance.",
                encoding="utf-8",
            )
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                skill_context = build_skill_context(self._assessment("terraform"))
        self.assertIn("Terraform guidance.", skill_context)
        self.assertNotIn("Git guidance.", skill_context)

    def test_triggered_skill_is_included_from_raw_file_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Terraform\nTerraform guidance.", encoding="utf-8"
            )
            (skills_dir / "docker.md").write_text(
                "---\ntriggers: [docker-compose.yml]\ntrigger_content_patterns: [services]\n---\n# Docker\nDocker guidance.",
                encoding="utf-8",
            )
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                skill_context = build_skill_context(
                    self._assessment("terraform"),
                    raw_files={
                        "docker-compose.yml": b"services:\n  app:\n    image: example"
                    },
                )
        self.assertIn("Terraform guidance.", skill_context)
        self.assertIn("Docker guidance.", skill_context)

    def test_parser_family_skills_do_not_cross_match_on_shared_yaml_extension(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "kubernetes.md").write_text(
                "---\ntriggers: [.yaml, .yml]\n---\n# Kubernetes\nKubernetes guidance.",
                encoding="utf-8",
            )
            (skills_dir / "ansible.md").write_text(
                "---\ntriggers: [.yaml, .yml]\n---\n# Ansible\nAnsible guidance.",
                encoding="utf-8",
            )
            (skills_dir / "cloudformation.md").write_text(
                "---\ntriggers: [.yaml, .yml]\n---\n# CloudFormation\nCloudFormation guidance.",
                encoding="utf-8",
            )
            assessment = self._assessment("kubernetes")
            with (
                patch("llm.skill_context.SKILLS_DIR", skills_dir),
                patch("llm.skill_context.CUSTOM_DIR", custom_dir),
            ):
                skill_context = build_skill_context(
                    assessment,
                    raw_files={
                        "deployment.yaml": b"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n"
                    },
                )
        self.assertIn("Kubernetes guidance.", skill_context)
        self.assertNotIn("Ansible guidance.", skill_context)
        self.assertNotIn("CloudFormation guidance.", skill_context)


if __name__ == "__main__":
    unittest.main()
