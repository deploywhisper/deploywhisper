"""Tests for the deterministic skill test harness service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.skill_test_harness_service import (
    iter_built_in_skill_ids,
    run_skill_test_suite,
    run_skill_test_suites,
    summarize_skill_test_suite,
)


class SkillTestHarnessServiceTests(unittest.TestCase):
    def test_run_skill_test_suite_reports_passing_summary(self) -> None:
        result = run_skill_test_suite("terraform")

        assert result is not None
        self.assertEqual(result.skill_id, "terraform")
        self.assertEqual(result.summary.status, "passing")
        self.assertGreaterEqual(result.summary.total_scenarios, 1)
        self.assertEqual(result.summary.failed_scenarios, 0)
        self.assertTrue(all(scenario.passed for scenario in result.scenarios))

    def test_summarize_skill_test_suite_returns_public_display_text(self) -> None:
        summary = summarize_skill_test_suite("docker")

        assert summary is not None
        self.assertEqual(summary.skill_id, "docker")
        self.assertEqual(summary.status, "passing")
        self.assertIn("/", summary.display_text)

    def test_run_skill_test_suite_returns_none_for_missing_skill(self) -> None:
        self.assertIsNone(run_skill_test_suite("missing-skill"))

    def test_missing_scenario_files_are_reported_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            skill_tests_dir = repo_root / "tests" / "skill-tests"
            skills_dir.mkdir(parents=True, exist_ok=True)
            skill_tests_dir.mkdir(parents=True, exist_ok=True)
            (skill_tests_dir / "terraform").mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "---\n"
                "name: terraform\n"
                "version: 1.0.0\n"
                "author: DeployWhisper\n"
                "license: MIT\n"
                "triggers: [.tf]\n"
                "token_budget: 1500\n"
                "tags: [terraform]\n"
                "description: Terraform guidance.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                encoding="utf-8",
            )

            with (
                patch("services.skill_test_harness_service.REPO_ROOT", repo_root),
                patch("services.skill_test_harness_service.SKILLS_DIR", skills_dir),
            ):
                result = run_skill_test_suite("terraform")

        assert result is not None
        self.assertEqual(result.summary.status, "missing")
        self.assertEqual(result.summary.total_scenarios, 0)

    def test_run_skill_test_suites_defaults_to_all_built_in_skills(self) -> None:
        results = run_skill_test_suites()

        self.assertEqual(
            {result.skill_id for result in results},
            set(iter_built_in_skill_ids()),
        )


if __name__ == "__main__":
    unittest.main()
