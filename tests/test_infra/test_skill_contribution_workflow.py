"""Tests for the skill contribution workflow assets."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
