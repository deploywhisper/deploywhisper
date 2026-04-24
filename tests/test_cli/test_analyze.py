"""Tests for CLI skill inspection."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.report_service as report_service_module
import services.analysis_service as analysis_service_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from cli.analyze import main
from importlib import reload
from integrations.github.init_service import GitHubInitOptions, GitHubInitResult
from llm.narrator import NarrativeResult
from services.skill_installer_service import InstalledSkillEntry, SkillInstallResult
from services.skill_test_harness_service import (
    SkillTestScenarioResult,
    SkillTestSuiteResult,
    SkillTestSummary,
)


class AnalyzeCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "cli.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["APP_BASE_URL"] = "https://deploywhisper.example.com"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(report_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("APP_BASE_URL", None)
        self.tempdir.cleanup()

    def test_skills_command_uses_shared_custom_skill_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            custom_dir = skills_dir / "custom"
            skills_dir.mkdir(parents=True, exist_ok=True)
            custom_dir.mkdir(parents=True, exist_ok=True)
            (skills_dir / "terraform.md").write_text(
                "# Built-in\nDefault terraform guidance.", encoding="utf-8"
            )
            (custom_dir / "terraform.md").write_text(
                "# Custom\nTeam terraform guidance.", encoding="utf-8"
            )

            output = io.StringIO()
            with (
                patch("cli.analyze.skill_context_module.SKILLS_DIR", skills_dir),
                patch("cli.analyze.skill_context_module.CUSTOM_DIR", custom_dir),
                patch("sys.argv", ["deploywhisper", "skills"]),
                redirect_stdout(output),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("terraform: override (detected)", output.getvalue())

    def test_skill_lint_command_accepts_valid_manifest_v1(self) -> None:
        skill_path = Path(self.tempdir.name) / "terraform.md"
        (Path(self.tempdir.name) / "tests/skill-tests/terraform").mkdir(
            parents=True, exist_ok=True
        )
        skill_path.write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "triggers: [.tf]\n"
            "token_budget: 1500\n"
            "tags: [terraform, iac]\n"
            "description: Terraform review guidance.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "---\n"
            "# Terraform\nGuidance.\n",
            encoding="utf-8",
        )
        output = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "skill", "lint", str(skill_path)]),
            patch("pathlib.Path.cwd", return_value=Path(self.tempdir.name)),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("valid skill manifest v1", output.getvalue())

    def test_skill_lint_command_rejects_missing_required_manifest_fields(self) -> None:
        skill_path = Path(self.tempdir.name) / "terraform.md"
        skill_path.write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "triggers: [.tf]\n"
            "token_budget: 1500\n"
            "tags: [terraform, iac]\n"
            "description: Terraform review guidance.\n"
            "---\n"
            "# Terraform\nGuidance.\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "skill", "lint", str(skill_path)]),
            patch("pathlib.Path.cwd", return_value=Path(self.tempdir.name)),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid skill manifest v1", stderr.getvalue())
        self.assertIn("test_suite_path", stderr.getvalue())

    def test_skill_lint_command_rejects_nonexistent_test_suite_path(self) -> None:
        skill_path = Path(self.tempdir.name) / "terraform.md"
        skill_path.write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "triggers: [.tf]\n"
            "token_budget: 1500\n"
            "tags: [terraform, iac]\n"
            "description: Terraform review guidance.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "---\n"
            "# Terraform\nGuidance.\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "skill", "lint", str(skill_path)]),
            patch("pathlib.Path.cwd", return_value=Path(self.tempdir.name)),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("path does not exist", stderr.getvalue())

    def test_skill_lint_command_uses_current_working_directory_as_project_root(
        self,
    ) -> None:
        repo_root = Path(self.tempdir.name) / "skill-repo"
        skill_dir = repo_root / "skills"
        suite_dir = repo_root / "tests/skill-tests/terraform"
        suite_dir.mkdir(parents=True, exist_ok=True)
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "terraform.md"
        skill_path.write_text(
            "---\n"
            "name: terraform\n"
            "version: 1.0.0\n"
            "author: DeployWhisper\n"
            "license: MIT\n"
            "triggers: [.tf]\n"
            "token_budget: 1500\n"
            "tags: [terraform, iac]\n"
            "description: Terraform review guidance.\n"
            "test_suite_path: tests/skill-tests/terraform\n"
            "---\n"
            "# Terraform\nGuidance.\n",
            encoding="utf-8",
        )
        output = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "skill", "lint", str(skill_path)]),
            patch("pathlib.Path.cwd", return_value=repo_root),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("valid skill manifest v1", output.getvalue())

    def test_skill_test_command_reports_success_for_requested_skill(self) -> None:
        output = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "skill", "test", "terraform"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("terraform:", output.getvalue())
        self.assertIn("scenarios passing", output.getvalue())

    def test_skill_test_command_emits_json(self) -> None:
        output = io.StringIO()

        with (
            patch(
                "sys.argv",
                ["deploywhisper", "skill", "test", "terraform", "--json"],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["data"][0]["skill_id"], "terraform")
        self.assertEqual(payload["data"][0]["summary"]["status"], "passing")

    def test_skill_test_command_rejects_unknown_skill_id(self) -> None:
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "skill", "test", "missing-skill"]),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("Unknown skill ids: missing-skill", stderr.getvalue())

    def test_skill_test_command_emits_structured_error_for_unknown_skill_in_json_mode(
        self,
    ) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                ["deploywhisper", "skill", "test", "missing-skill", "--json"],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "skill_not_found")
        self.assertEqual(payload["error"]["details"]["skill_ids"], ["missing-skill"])

    def test_skill_test_command_returns_nonzero_for_missing_suite_status(self) -> None:
        output = io.StringIO()
        missing_result = SkillTestSuiteResult(
            skill_id="terraform",
            version="1.0.0",
            summary=SkillTestSummary(
                skill_id="terraform",
                total_scenarios=0,
                passed_scenarios=0,
                failed_scenarios=0,
                pass_rate=0.0,
                status="missing",
                display_text="0/0 scenarios passing",
                generated_at="2026-04-24T00:00:00Z",
            ),
            scenarios=[SkillTestScenarioResult(name="suite-missing", passed=False)],
        )

        with (
            patch("cli.analyze.run_skill_test_suites", return_value=[missing_result]),
            patch("sys.argv", ["deploywhisper", "skill", "test", "terraform"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("[missing]", output.getvalue())

    def test_skill_install_command_reports_install_location(self) -> None:
        output = io.StringIO()

        with (
            patch(
                "cli.analyze.install_skill",
                return_value=SkillInstallResult(
                    action="installed",
                    skill_id="helm",
                    version="1.2.0",
                    previous_version=None,
                    destination="skills/custom/helm.md",
                    mode="new",
                    sha256="abc",
                    source_url="https://registry.example.com/api/v1/skills/helm/content",
                ),
            ),
            patch("sys.argv", ["deploywhisper", "skill", "install", "helm"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Installed helm@1.2.0", output.getvalue())
        self.assertIn("skills/custom/helm.md", output.getvalue())

    def test_skill_list_command_prints_installed_skill_inventory(self) -> None:
        output = io.StringIO()

        with (
            patch(
                "cli.analyze.list_installed_skills",
                return_value=[
                    InstalledSkillEntry(
                        id="helm",
                        version="1.2.0",
                        mode="new",
                        active=True,
                        path="skills/custom/helm.md",
                        description="Helm rollout checks.",
                    ),
                    InstalledSkillEntry(
                        id="terraform",
                        version="2.0.0",
                        mode="override",
                        active=False,
                        path="skills/custom/terraform.md",
                        warning="invalid frontmatter",
                    ),
                ],
            ),
            patch("sys.argv", ["deploywhisper", "skill", "list"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("helm@1.2.0 [new, active]", output.getvalue())
        self.assertIn("terraform@2.0.0 [override, ignored]", output.getvalue())

    def test_skill_update_command_reports_noop_when_latest_version_is_installed(
        self,
    ) -> None:
        output = io.StringIO()

        with (
            patch(
                "cli.analyze.update_skill",
                return_value=SkillInstallResult(
                    action="unchanged",
                    skill_id="helm",
                    version="1.2.0",
                    previous_version="1.2.0",
                    destination="skills/custom/helm.md",
                    mode="new",
                    sha256="abc",
                    source_url="https://registry.example.com/api/v1/skills/helm/content",
                ),
            ),
            patch("sys.argv", ["deploywhisper", "skill", "update", "helm"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("already up to date", output.getvalue())
        self.assertIn("1.2.0", output.getvalue())

    def test_skill_remove_command_reports_deleted_custom_skill(self) -> None:
        output = io.StringIO()

        with (
            patch(
                "cli.analyze.remove_skill",
                return_value=SkillInstallResult(
                    action="removed",
                    skill_id="helm",
                    version=None,
                    previous_version="1.2.0",
                    destination="skills/custom/helm.md",
                    mode="new",
                ),
            ),
            patch("sys.argv", ["deploywhisper", "skill", "remove", "helm"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Removed helm", output.getvalue())
        self.assertIn("skills/custom/helm.md", output.getvalue())

    def test_analyze_command_runs_shared_analysis_and_prints_structured_output(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
            encoding="utf-8",
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
        )
        output = io.StringIO()

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["meta"]["interface"], "cli")
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertTrue(payload["meta"]["advisory_only"])
        self.assertEqual(payload["meta"]["accepted_artifact_count"], 1)
        self.assertIn(payload["data"]["assessment"]["severity"], {"high", "critical"})
        self.assertIn("context_completeness", payload["data"]["assessment"])
        self.assertTrue(payload["data"]["findings"])
        self.assertEqual(payload["data"]["findings"][0]["confidence"], 1.0)
        self.assertFalse(payload["data"]["advisory"]["should_block"])
        self.assertTrue(payload["data"]["advisory"]["requires_attention"])
        self.assertIn("Advisory only", payload["data"]["share_summary"]["plain_text"])
        self.assertEqual(payload["data"]["share_summary"]["recommendation"], "no-go")
        self.assertLessEqual(len(payload["data"]["share_summary"]["markdown"]), 1500)
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["version"], "v1"
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["report_id"],
            payload["data"]["persisted_report"]["id"],
        )
        self.assertIn(
            "https://deploywhisper.example.com/reports/",
            payload["data"]["share_summary"]["json_payload"]["rollback_link"],
        )
        self.assertTrue(payload["data"]["persisted_report"]["findings"])
        self.assertEqual(
            payload["data"]["persisted_report"]["report_schema_version"], "v2"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["source_interface"], "cli"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "cli_command"
        )
        self.assertEqual(payload["data"]["persisted_report"]["id"], 1)

    def test_analyze_command_captures_trigger_context_from_environment_when_available(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
            encoding="utf-8",
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
        )
        output = io.StringIO()

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_TRIGGER_TYPE": "ci_job",
                    "DEPLOYWHISPER_TRIGGER_ID": "job-789",
                },
                clear=False,
            ),
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "ci_job"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_id"], "job-789"
        )

    def test_analyze_command_reports_unsupported_inputs_with_structured_error(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "README.txt"
        artifact_path.write_text("hello", encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "no_supported_artifacts")
        self.assertEqual(
            payload["error"]["details"]["items"][0]["status"], "unsupported"
        )

    def test_analyze_command_reports_missing_files_with_structured_error(self) -> None:
        missing_path = Path(self.tempdir.name) / "missing-plan.json"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "analyze", str(missing_path)]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "artifact_read_failed")
        self.assertEqual(payload["error"]["details"]["path"], str(missing_path))

    def test_analyze_command_preserves_distinct_files_with_same_basename(self) -> None:
        first_dir = Path(self.tempdir.name) / "first"
        second_dir = Path(self.tempdir.name) / "second"
        first_dir.mkdir(parents=True, exist_ok=True)
        second_dir.mkdir(parents=True, exist_ok=True)
        first_path = first_dir / "plan.json"
        second_path = second_dir / "plan.json"
        first_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.first", "change": {"actions": ["modify"]}}]}',
            encoding="utf-8",
        )
        second_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.second", "change": {"actions": ["modify"]}}]}',
            encoding="utf-8",
        )
        output = io.StringIO()
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group updates.",
            explanation="Two security group changes should be reviewed together.",
            guidance=["Review both security group changes before deploy."],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch(
                "sys.argv",
                ["deploywhisper", "analyze", str(first_path), str(second_path)],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["meta"]["accepted_artifact_count"], 2)
        intake_names = [item["name"] for item in payload["data"]["intake"]["items"]]
        self.assertEqual(intake_names, ["plan.json", "plan#2.json"])
        source_files = [
            change["source_file"]
            for file_result in payload["data"]["parse_batch"]["files"]
            for change in file_result["changes"]
        ]
        self.assertIn("plan.json", source_files)
        self.assertIn("plan#2.json", source_files)
        self.assertNotIn(str(first_path), source_files)
        self.assertNotIn(str(second_path), source_files)

    def test_analyze_command_reports_shared_analysis_failures_with_structured_error(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "cli.analyze.analyze_uploaded_files", side_effect=RuntimeError("boom")
            ),
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "analysis_failed")
        self.assertEqual(payload["error"]["message"], "Analysis failed.")
        self.assertEqual(payload["error"]["details"]["reason"], "boom")

    def test_analyze_command_rejects_payloads_over_limit_before_reading_all_bytes(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "large-plan.json"
        artifact_path.write_text("x" * 11, encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("cli.analyze.MAX_TOTAL_UPLOAD_BYTES", 10),
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "upload_limit_exceeded")

    def test_analyze_command_preserves_advisory_output_for_high_risk_results(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["delete"]}}]}',
            encoding="utf-8",
        )
        assessment = RiskAssessment(
            score=90,
            severity="critical",
            recommendation="no-go",
            top_risk="Terraform changed a security group.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="delete",
                    contribution=24,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=True,
            warnings=[
                "Analysis used partial context because one or more files failed to parse."
            ],
        )
        narrative = NarrativeResult(
            available=False,
            opening_sentence="",
            explanation="",
            guidance=["Pause deployment until the destructive change is reviewed."],
            degraded=True,
            warnings=["Narrative provider unavailable: offline test"],
            failure_notice="Narrative provider unavailable: offline test",
        )
        output = io.StringIO()

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=assessment,
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["meta"]["advisory_only"])
        self.assertFalse(payload["data"]["advisory"]["should_block"])
        self.assertTrue(payload["data"]["advisory"]["requires_attention"])
        self.assertIn(
            "requires additional human review",
            payload["data"]["share_summary"]["plain_text"],
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["context_completeness"][
                "label"
            ],
            "LIMITED CONTEXT",
        )
        self.assertEqual(payload["data"]["assessment"]["recommendation"], "no-go")
        self.assertTrue(payload["data"]["assessment"]["partial_context"])
        self.assertFalse(payload["data"]["narrative"]["available"])
        self.assertTrue(payload["data"]["narrative"]["degraded"])
        self.assertTrue(payload["data"]["evidence_items"])
        self.assertIn(
            "partial_context", payload["data"]["advisory"]["uncertainty_flags"]
        )
        self.assertIn(
            "narrative_degraded", payload["data"]["advisory"]["uncertainty_flags"]
        )

    def test_analyze_command_suppresses_non_json_stream_noise_on_success(self) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["modify"]}}]}',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
        )

        def noisy_analyze_uploaded_files(files, audit_context=None):
            print("unexpected provider noise")
            print("unexpected provider noise", file=sys.stderr)
            return analysis_service_module.analyze_uploaded_files(
                files, audit_context=audit_context
            )

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch(
                "cli.analyze.analyze_uploaded_files",
                side_effect=noisy_analyze_uploaded_files,
            ),
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(stderr.getvalue(), "")
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["meta"]["interface"], "cli")

    @patch("cli.analyze.run_github_init")
    @patch("cli.analyze.collect_github_init_options")
    def test_github_init_command_uses_shared_init_service(
        self,
        collect_github_init_options,
        run_github_init,
    ) -> None:
        collect_github_init_options.return_value = GitHubInitOptions(
            repo_path="/tmp/example-repo",
            workflow_path=".github/workflows/deploywhisper.yml",
            api_endpoint="https://deploywhisper.example.com/api/v1/analyses",
            enable_github_app=False,
            base_branch="develop",
        )
        run_github_init.return_value = GitHubInitResult(
            repo_path="/tmp/example-repo",
            workflow_path=".github/workflows/deploywhisper.yml",
            readme_path="README.md",
            github_app_notes_path=None,
            branch_name="feature/deploywhisper-github-init",
            base_branch="main",
            commit_sha="abc123",
            pr_url="https://github.com/example/repo/pull/7",
        )
        output = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "github",
                    "init",
                    "--repo",
                    "/tmp/example-repo",
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        collect_github_init_options.assert_called_once_with(
            repo_path="/tmp/example-repo",
            workflow_path=None,
            api_endpoint=None,
            enable_github_app=None,
            base_branch=None,
            github_owner=None,
            github_app_name=None,
            github_app_slug=None,
            public_base_url=None,
            branch_name=None,
        )
        run_github_init.assert_called_once()
        self.assertIn(
            "Updated workflow: .github/workflows/deploywhisper.yml", output.getvalue()
        )
        self.assertIn(
            "Pull request: https://github.com/example/repo/pull/7", output.getvalue()
        )


if __name__ == "__main__":
    unittest.main()
