"""Tests for the skill contribution workflow assets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.collect_changed_skills import _changed_skill_ids
from scripts.publish_skills_registry import publish_skill
from scripts.refresh_skill_analytics import (
    DEFAULT_METRICS_URL,
    build_snapshot,
    iter_built_in_skill_ids,
    resolve_metrics_url,
)


class SkillContributionWorkflowTests(unittest.TestCase):
    def test_skill_pr_template_exists_with_validation_sections(self) -> None:
        template = Path(".github/PULL_REQUEST_TEMPLATE/skill.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("## Skill Summary", template)
        self.assertIn("deploywhisper skill lint", template)
        self.assertIn("deploywhisper skill test", template)
        self.assertIn("## Reviewer Assignment", template)
        self.assertIn("Requested maintainer or domain reviewer:", template)

    def test_codeowners_contains_explicit_skill_contribution_paths(self) -> None:
        rules: dict[str, tuple[str, ...]] = {}
        for line in Path(".github/CODEOWNERS").read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            pattern, *owners = stripped.split()
            rules[pattern] = tuple(owners)

        expected_paths = (
            "/skills/",
            "/tests/skill-tests/",
            "/.github/PULL_REQUEST_TEMPLATE/skill.md",
            "/docs/contributing/skills.md",
        )
        for path in expected_paths:
            with self.subTest(path=path):
                self.assertIn(path, rules)
                self.assertTrue(rules[path])
                self.assertTrue(all(owner.startswith("@") for owner in rules[path]))

    def test_changed_skill_script_runs_lint_before_harness(self) -> None:
        script = Path("scripts/test-changed-skills.sh").read_text(encoding="utf-8")

        self.assertIn("^skills/([^/]+)\\.md$", script)
        self.assertIn('cli.py skill lint "skills/${skill}.md"', script)
        self.assertIn('cli.py skill test "${UNIQUE_SKILLS[@]}"', script)

    def test_changed_skill_ci_preserves_actionable_failure_logs(self) -> None:
        workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

        self.assertIn("Run changed skill lint and harness checks", workflow)
        self.assertIn("changed-skill-harness.log", workflow)
        self.assertIn("if: failure()", workflow)
        self.assertNotIn(
            "if [ -f scripts/test-changed-skills.sh ]; then",
            workflow,
        )

    def test_changed_skill_script_handles_an_empty_diff(self) -> None:
        result = subprocess.run(
            ["bash", "scripts/test-changed-skills.sh"],
            check=False,
            capture_output=True,
            env={
                **os.environ,
                "BASE_REF": "HEAD",
                "PYTHON_BIN": sys.executable,
            },
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No changed built-in skills detected", result.stdout)

    def test_changed_skill_script_fails_closed_when_base_is_missing(self) -> None:
        result = subprocess.run(
            ["bash", "scripts/test-changed-skills.sh"],
            check=False,
            capture_output=True,
            env={
                **os.environ,
                "BASE_REF": "missing/story-9-6-base",
                "PYTHON_BIN": sys.executable,
            },
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Base ref 'missing/story-9-6-base' is unavailable", result.stderr)

    def test_changed_skill_script_fails_closed_when_diff_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_git = Path(tmpdir) / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "rev-parse" ]; then exit 0; fi\n'
                'if [ "$1" = "diff" ]; then echo "diff failed" >&2; exit 7; fi\n'
                "exit 1\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            result = subprocess.run(
                ["bash", "scripts/test-changed-skills.sh"],
                check=False,
                capture_output=True,
                env={
                    **os.environ,
                    "BASE_REF": "develop",
                    "PATH": f"{tmpdir}{os.pathsep}{os.environ['PATH']}",
                    "PYTHON_BIN": sys.executable,
                },
                text=True,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("diff failed", result.stderr)

    def test_changed_skill_script_excludes_nested_skill_docs(self) -> None:
        diff_output = "\n".join(
            [
                "skills/custom/README.md",
                "skills/custom/team-skill.md",
                "skills/helm.md",
                "tests/skill-tests/terraform/scenario.json",
            ]
        )

        with patch(
            "scripts.collect_changed_skills.subprocess.run",
            return_value=SimpleNamespace(stdout=diff_output),
        ):
            skill_ids = _changed_skill_ids("origin/develop", "HEAD")

        self.assertEqual(skill_ids, ["helm", "terraform"])

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
        self.assertNotIn("pull_request:", workflow)

    def test_publish_workflow_revalidates_before_registry_checkout(self) -> None:
        workflow = Path(".github/workflows/publish-skills-registry.yml").read_text(
            encoding="utf-8"
        )

        validation_index = workflow.index("Validate changed skills before publish")
        checkout_index = workflow.index("Checkout registry repository")
        publish_index = workflow.index("scripts/publish_skills_registry.py")

        self.assertLess(validation_index, checkout_index)
        self.assertLess(validation_index, publish_index)
        self.assertIn("python cli.py skill lint", workflow)
        self.assertIn("python cli.py skill test", workflow)

    def test_contribution_docs_define_failure_and_publish_boundary(self) -> None:
        guide = Path("docs/contributing/skills.md").read_text(encoding="utf-8")
        normalized_guide = " ".join(guide.split())
        contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
        authoring = Path("docs/skills/authoring-guide.md").read_text(encoding="utf-8")

        self.assertIn("Story 9.6", guide)
        self.assertIn(
            "A failed manifest lint or harness check stops the workflow before",
            normalized_guide,
        )
        self.assertIn("No pull request event can publish a Skill", normalized_guide)
        self.assertIn("docs/contributing/skills.md", contributing)
        self.assertIn("docs/contributing/skills.md", authoring)

    def test_daily_skill_analytics_refresh_workflow_exists(self) -> None:
        workflow = Path(".github/workflows/refresh-skill-analytics.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Refresh Skill Analytics", workflow)
        self.assertIn("schedule:", workflow)
        self.assertIn("cron:", workflow)
        self.assertIn("scripts/refresh_skill_analytics.py", workflow)
        self.assertIn("issues: read", workflow)
        self.assertIn("GITHUB_TOKEN", workflow)
        self.assertIn("DEPLOYWHISPER_SKILL_ANALYTICS_URL", workflow)
        self.assertIn(DEFAULT_METRICS_URL, workflow)

    def test_refresh_skill_analytics_defaults_to_public_registry_feed(self) -> None:
        with patch.dict("os.environ", {"DEPLOYWHISPER_SKILL_ANALYTICS_URL": ""}):
            self.assertEqual(resolve_metrics_url(), DEFAULT_METRICS_URL)

    def test_refresh_skill_analytics_updates_issue_counts_from_runtime_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "skill-analytics.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-24T00:00:00Z",
                        "skills": {
                            "terraform": {
                                "install_count": 1842,
                                "star_count": 418,
                                "active_issue_count": 1,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            payload = build_snapshot(
                snapshot_path,
                issue_counts={skill_id: 0 for skill_id in iter_built_in_skill_ids()}
                | {"terraform": 7},
                popularity_metrics={
                    skill_id: {"install_count": 100, "star_count": 10}
                    for skill_id in iter_built_in_skill_ids()
                }
                | {"terraform": {"install_count": 1900, "star_count": 430}},
            )

        self.assertEqual(payload["skills"]["terraform"]["install_count"], 1900)
        self.assertEqual(payload["skills"]["terraform"]["star_count"], 430)
        self.assertEqual(payload["skills"]["terraform"]["active_issue_count"], 7)

    def test_refresh_skill_analytics_rejects_missing_popularity_metrics_for_skill(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "skill-analytics.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-24T00:00:00Z",
                        "skills": {
                            "terraform": {
                                "install_count": 1842,
                                "star_count": 418,
                                "active_issue_count": 1,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError) as ctx:
                build_snapshot(
                    snapshot_path,
                    issue_counts={"terraform": 7},
                    popularity_metrics={},
                )

        self.assertIn("missing popularity metrics", str(ctx.exception).lower())

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
