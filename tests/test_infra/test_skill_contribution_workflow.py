"""Tests for the skill contribution workflow assets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.publish_skills_registry import publish_skill


class SkillContributionWorkflowTests(unittest.TestCase):
    def test_skill_pr_template_exists_with_validation_sections(self) -> None:
        template = Path(".github/PULL_REQUEST_TEMPLATE/skill.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("## Skill Summary", template)
        self.assertIn("deploywhisper skill lint", template)
        self.assertIn("deploywhisper skill test", template)

    def test_codeowners_contains_explicit_skill_contribution_paths(self) -> None:
        codeowners = Path(".github/CODEOWNERS").read_text(encoding="utf-8")

        self.assertIn("/skills/", codeowners)
        self.assertIn("/tests/skill-tests/", codeowners)
        self.assertIn("/.github/PULL_REQUEST_TEMPLATE/skill.md", codeowners)
        self.assertIn("/docs/contributing/skills.md", codeowners)

    def test_changed_skill_script_runs_lint_before_harness(self) -> None:
        script = Path("scripts/test-changed-skills.sh").read_text(encoding="utf-8")

        self.assertIn('cli.py skill lint "skills/${skill}.md"', script)
        self.assertIn('cli.py skill test "${UNIQUE_SKILLS[@]}"', script)

    def test_publish_workflow_exists_and_targets_main_skill_changes(self) -> None:
        workflow = Path(".github/workflows/publish-skills-registry.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Publish Skills Registry", workflow)
        self.assertIn("branches:", workflow)
        self.assertIn("- main", workflow)
        self.assertIn("skills/*.md", workflow)
        self.assertIn("REGISTRY_REPO: deploywhisper/skills-registry", workflow)
        self.assertIn("DEPLOYWHISPER_SKILLS_REGISTRY_PUSH_TOKEN", workflow)
        self.assertIn("scripts/publish_skills_registry.py", workflow)

    def test_publish_skill_writes_registry_bundle_and_removes_deleted_skill(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target_repo = Path(tmpdir) / "registry"
            target_repo.mkdir(parents=True, exist_ok=True)

            publish_skill("terraform", target_repo=target_repo)
            exported_dir = target_repo / "skills" / "terraform"
            self.assertTrue((exported_dir / "skill.md").exists())
            self.assertTrue((exported_dir / "manifest.json").exists())
            self.assertTrue((exported_dir / "tests" / "scenarios").exists())

            publish_skill("missing-skill", target_repo=target_repo)
            self.assertFalse((target_repo / "skills" / "missing-skill").exists())


if __name__ == "__main__":
    unittest.main()
