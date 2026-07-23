"""Tests for the deterministic skill test harness service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm.skill_context import ActiveSkill
from services.skill_test_harness_service import (
    SkillTestScenarioDefinition,
    SkillTestScenarioResult,
    _evaluate_coverage,
    _filename_matches_trigger,
    iter_built_in_skill_ids,
    run_skill_test_suite,
    run_skill_test_suites,
    summarize_skill_test_suite,
)


class SkillTestHarnessServiceTests(unittest.TestCase):
    def test_full_path_trigger_matching_stays_in_parity_with_runtime(self) -> None:
        self.assertTrue(
            _filename_matches_trigger(
                "environments/prod/custom.trigger",
                "environments/prod/custom.trigger",
            )
        )

    def test_failed_scenarios_do_not_claim_verified_coverage(self) -> None:
        active_skill = ActiveSkill(
            name="terraform",
            source="built-in",
            path="skills/terraform.md",
            content="Guidance.",
            triggers=[".tf"],
        )
        positive = SkillTestScenarioDefinition(
            name="positive",
            assessment_tool="terraform",
            contributor_summary="Terraform evidence.",
            raw_files={"main.tf": "resource {}"},
            expected_substrings=["missing output"],
        )
        negative = SkillTestScenarioDefinition(
            name="negative",
            assessment_tool="unrelated",
            contributor_summary="Unrelated evidence.",
            raw_files={"notes.txt": "documentation"},
            expect_selected=False,
            expected_absent_substrings=["Guidance."],
        )

        coverage = _evaluate_coverage(
            active_skill,
            [positive, negative],
            [
                SkillTestScenarioResult(name="positive", passed=False),
                SkillTestScenarioResult(name="negative", passed=True),
            ],
        )

        self.assertFalse(coverage.expected_triggers)
        self.assertFalse(coverage.expected_outputs)
        self.assertFalse(coverage.evidence_assumptions)
        self.assertTrue(coverage.safety_constraints)
        self.assertFalse(coverage.complete)

    def test_run_skill_test_suite_reports_passing_summary(self) -> None:
        result = run_skill_test_suite("terraform")

        assert result is not None
        self.assertEqual(result.skill_id, "terraform")
        self.assertEqual(result.summary.status, "passing")
        self.assertGreaterEqual(result.summary.total_scenarios, 1)
        self.assertEqual(result.summary.failed_scenarios, 0)
        self.assertTrue(all(scenario.passed for scenario in result.scenarios))
        self.assertTrue(result.coverage.expected_triggers)
        self.assertTrue(result.coverage.expected_outputs)
        self.assertTrue(result.coverage.evidence_assumptions)
        self.assertTrue(result.coverage.safety_constraints)
        self.assertTrue(result.coverage.complete)
        self.assertTrue(result.trust_requirement.required)
        self.assertTrue(result.trust_requirement.satisfied)
        self.assertEqual(result.trust_requirement.failures, [])

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
                "supported_toolchains: [terraform]\n"
                "trust_level: core\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
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
        self.assertEqual(result.summary.pass_rate, 0.0)
        self.assertFalse(result.coverage.complete)
        self.assertTrue(result.trust_requirement.required)
        self.assertFalse(result.trust_requirement.satisfied)
        self.assertIn(
            "A verified/core Skill must have at least one passing scenario.",
            result.trust_requirement.failures,
        )

    def test_invalid_scenario_json_is_reported_as_failing_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            suite_dir = repo_root / "tests" / "skill-tests" / "terraform"
            skills_dir.mkdir(parents=True, exist_ok=True)
            suite_dir.mkdir(parents=True, exist_ok=True)
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
                "supported_toolchains: [terraform]\n"
                "trust_level: core\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                encoding="utf-8",
            )
            (suite_dir / "broken.json").write_text(
                '{"name": "", "assessment_tool": "terraform"}',
                encoding="utf-8",
            )

            with (
                patch("services.skill_test_harness_service.REPO_ROOT", repo_root),
                patch("services.skill_test_harness_service.SKILLS_DIR", skills_dir),
            ):
                result = run_skill_test_suite("terraform")

        assert result is not None
        self.assertEqual(result.summary.status, "failing")
        self.assertEqual(result.summary.failed_scenarios, 1)
        self.assertEqual(result.scenarios[0].name, "suite-load-error")
        self.assertIn("broken.json", result.scenarios[0].failures[0])
        self.assertFalse(result.trust_requirement.satisfied)

    def test_verified_suite_requires_complete_deterministic_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            suite_dir = repo_root / "tests" / "skill-tests" / "terraform"
            skills_dir.mkdir(parents=True, exist_ok=True)
            suite_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "---\n"
                "name: terraform\n"
                "version: 1.0.0\n"
                "author: Community Maintainer\n"
                "license: MIT\n"
                "triggers: [.tf]\n"
                "token_budget: 1500\n"
                "tags: [terraform]\n"
                "description: Terraform guidance.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "supported_toolchains: [terraform]\n"
                "trust_level: verified\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                encoding="utf-8",
            )
            (suite_dir / "positive.json").write_text(
                '{"name":"positive","assessment_tool":"terraform",'
                '"contributor_summary":"Terraform resource evidence.",'
                '"raw_files":{"main.tf":"resource {}"},'
                '"expected_substrings":["Guidance."]}',
                encoding="utf-8",
            )

            with (
                patch("services.skill_test_harness_service.REPO_ROOT", repo_root),
                patch("services.skill_test_harness_service.SKILLS_DIR", skills_dir),
            ):
                result = run_skill_test_suite("terraform")

        assert result is not None
        self.assertEqual(result.summary.status, "failing")
        self.assertEqual(result.summary.total_scenarios, 1)
        self.assertEqual(result.summary.passed_scenarios, 1)
        self.assertEqual(result.summary.failed_scenarios, 0)
        self.assertFalse(result.coverage.safety_constraints)
        self.assertFalse(result.trust_requirement.satisfied)
        self.assertEqual([scenario.name for scenario in result.scenarios], ["positive"])
        self.assertNotIn(
            "Every declared scenario must pass for verified/core trust.",
            result.trust_requirement.failures,
        )

    def test_experimental_suite_reports_coverage_without_enforcing_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            skills_dir = repo_root / "skills"
            suite_dir = repo_root / "tests" / "skill-tests" / "terraform"
            skills_dir.mkdir(parents=True, exist_ok=True)
            suite_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "---\n"
                "name: terraform\n"
                "version: 1.0.0\n"
                "author: Community Maintainer\n"
                "license: MIT\n"
                "triggers: [.tf]\n"
                "token_budget: 1500\n"
                "tags: [terraform]\n"
                "description: Terraform guidance.\n"
                "test_suite_path: tests/skill-tests/terraform\n"
                "supported_toolchains: [terraform]\n"
                "trust_level: experimental\n"
                "scenario_references: [tests/skill-tests/terraform]\n"
                "documentation_links: [https://docs.deploywhisper.example/skills/terraform]\n"
                "---\n"
                "# Terraform\nGuidance.\n",
                encoding="utf-8",
            )
            (suite_dir / "positive.json").write_text(
                '{"name":"positive","assessment_tool":"terraform",'
                '"contributor_summary":"Terraform resource evidence.",'
                '"raw_files":{"main.tf":"resource {}"},'
                '"expected_substrings":["Guidance."]}',
                encoding="utf-8",
            )

            with (
                patch("services.skill_test_harness_service.REPO_ROOT", repo_root),
                patch("services.skill_test_harness_service.SKILLS_DIR", skills_dir),
            ):
                result = run_skill_test_suite("terraform")

        assert result is not None
        self.assertEqual(result.summary.status, "passing")
        self.assertFalse(result.coverage.complete)
        self.assertFalse(result.trust_requirement.required)
        self.assertTrue(result.trust_requirement.satisfied)

    def test_run_skill_test_suites_defaults_to_all_built_in_skills(self) -> None:
        results = run_skill_test_suites()

        self.assertEqual(
            {result.skill_id for result in results},
            set(iter_built_in_skill_ids()),
        )
        for result in results:
            with self.subTest(skill_id=result.skill_id):
                requires_gate = result.trust_requirement.trust_level in {
                    "verified",
                    "core",
                }
                self.assertEqual(result.trust_requirement.required, requires_gate)
                if requires_gate:
                    self.assertTrue(result.coverage.complete)
                self.assertTrue(result.trust_requirement.satisfied)
                self.assertEqual(result.summary.status, "passing")


if __name__ == "__main__":
    unittest.main()
