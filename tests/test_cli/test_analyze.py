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
import services.project_service as project_service_module
from analysis.incident_matcher import IncidentMatch
from analysis.risk_scorer import RiskAssessment, RiskContributor
from cli.analyze import main
from importlib import reload
from integrations.github.init_service import GitHubInitOptions, GitHubInitResult
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult
from services.skill_installer_service import InstalledSkillEntry, SkillInstallResult
from services.skill_registry_service import SkillRegistryEntry
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
        reload(project_service_module)
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

    def test_skill_list_catalog_command_prints_registry_analytics(self) -> None:
        output = io.StringIO()
        entry = SkillRegistryEntry(
            id="terraform",
            name="Terraform",
            version="1.0.0",
            source="built-in",
            author="DeployWhisper",
            maintainer="DeployWhisper",
            is_official=True,
            is_featured=False,
            license="MIT",
            description="Terraform registry skill.",
            tool="terraform",
            tags=["iac"],
            token_budget=1200,
            test_suite_path="tests/skill-tests/terraform",
            test_results=SkillTestSummary(
                skill_id="terraform",
                total_scenarios=3,
                passed_scenarios=3,
                failed_scenarios=0,
                pass_rate=1.0,
                status="passing",
                display_text="3/3 scenarios passing",
                generated_at="2026-04-25T00:00:00Z",
            ),
            triggers=[".tf"],
            trigger_content_patterns=[],
            contributors=["DeployWhisper"],
            install_count=1842,
            active_issue_count=1,
            analytics_updated_at="2026-04-25T00:00:00Z",
            download_count=1842,
            star_count=418,
            install_command="deploywhisper skill install terraform",
            updated_at="2026-04-24T00:00:00Z",
            available_versions=1,
        )

        with (
            patch("cli.analyze.fetch_skill_registry_page") as fetch_page,
            patch("sys.argv", ["deploywhisper", "skill", "list", "--catalog"]),
            redirect_stdout(output),
        ):
            fetch_page.return_value.items = [entry]
            fetch_page.return_value.total_count = 1
            fetch_page.return_value.page = 1
            fetch_page.return_value.page_size = 100
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("terraform", output.getvalue().lower())
        self.assertIn("installs=1842", output.getvalue().lower())
        self.assertIn("pass-rate=100%", output.getvalue().lower())
        self.assertIn("active-issues=1", output.getvalue().lower())

    def test_skill_list_catalog_command_fetches_all_registry_pages(self) -> None:
        output = io.StringIO()
        first = SkillRegistryEntry(
            id="terraform",
            name="Terraform",
            version="1.0.0",
            source="built-in",
            author="DeployWhisper",
            maintainer="DeployWhisper",
            is_official=True,
            is_featured=False,
            license="MIT",
            description="Terraform registry skill.",
            tool="terraform",
            tags=["iac"],
            token_budget=1200,
            test_suite_path="tests/skill-tests/terraform",
            test_results=None,
            triggers=[".tf"],
            trigger_content_patterns=[],
            contributors=["DeployWhisper"],
            install_count=1842,
            active_issue_count=1,
            analytics_updated_at="2026-04-25T00:00:00Z",
            download_count=1842,
            star_count=418,
            install_command="deploywhisper skill install terraform",
            updated_at="2026-04-24T00:00:00Z",
            available_versions=1,
        )
        second = SkillRegistryEntry(
            id="kubernetes",
            name="Kubernetes",
            version="1.0.0",
            source="built-in",
            author="DeployWhisper",
            maintainer="DeployWhisper",
            is_official=True,
            is_featured=False,
            license="MIT",
            description="Kubernetes registry skill.",
            tool="kubernetes",
            tags=["cluster"],
            token_budget=1200,
            test_suite_path="tests/skill-tests/kubernetes",
            test_results=None,
            triggers=[".yaml"],
            trigger_content_patterns=[],
            contributors=["DeployWhisper"],
            install_count=1765,
            active_issue_count=2,
            analytics_updated_at="2026-04-25T00:00:00Z",
            download_count=1765,
            star_count=403,
            install_command="deploywhisper skill install kubernetes",
            updated_at="2026-04-24T00:00:00Z",
            available_versions=1,
        )

        with (
            patch("cli.analyze.fetch_skill_registry_page") as fetch_page,
            patch("sys.argv", ["deploywhisper", "skill", "list", "--catalog"]),
            redirect_stdout(output),
        ):
            fetch_page.side_effect = [
                type(
                    "Page",
                    (),
                    {"items": [first], "total_count": 2, "page": 1, "page_size": 100},
                )(),
                type(
                    "Page",
                    (),
                    {"items": [second], "total_count": 2, "page": 2, "page_size": 100},
                )(),
            ]
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("terraform", output.getvalue().lower())
        self.assertIn("kubernetes", output.getvalue().lower())

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
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            (
                '{"planned_values": {}, "resource_changes": [{"address": "module.network.aws_security_group.main", '
                '"module_address": "module.network", "type": "aws_security_group", '
                '"name": "main", "provider_name": "registry.terraform.io/hashicorp/aws", '
                '"change": {"actions": ["update"], "after_unknown": {"arn": true}, '
                '"after_sensitive": {"ingress": [{"description": true}]}, '
                '"replace_paths": [["ingress", 0, "cidr_blocks"]]}}]}'
            ),
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
        incident_match = IncidentMatch(
            incident_id=0,
            match_type="public_risk_pattern",
            public_pattern_id="public-ingress-wide-open",
            title="Wide-open administrative ingress",
            severity="high",
            source_file="plan.json",
            incident_date=None,
            similarity=0.86,
            confidence=0.86,
            reason="The change exposes administrative ingress publicly.",
            evidence=["plan.json: aws_security_group.main (modify) - public SSH"],
            verification_guidance=[
                "Confirm public CIDR is intentional.",
                "Restrict ingress to trusted networks.",
            ],
            summary="Public risk pattern match: wide-open administrative ingress.",
        )

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch(
                "services.analysis_service.find_incident_matches",
                return_value=[incident_match],
            ),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
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
        self.assertEqual(
            payload["data"]["incident_matches"][0]["public_pattern_id"],
            "public-ingress-wide-open",
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["incident_matches"][0][
                "public_pattern_id"
            ],
            "public-ingress-wide-open",
        )
        self.assertTrue(
            payload["data"]["persisted_report"]["incident_matches"][0]["evidence"]
        )
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
            payload["data"]["share_summary"]["json_payload"]["report_schema_version"],
            "v2",
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
        change = payload["data"]["parse_batch"]["files"][0]["changes"][0]
        self.assertEqual(
            change["resource_id"], "module.network.aws_security_group.main"
        )
        self.assertEqual(change["metadata"]["module_address"], "module.network")
        self.assertEqual(change["metadata"]["unknown_after_apply"], ["arn"])
        self.assertEqual(
            change["metadata"]["redacted_fields"], ["ingress.0.description"]
        )
        self.assertEqual(
            change["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["source_interface"], "cli"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["actor"], "cli_local_user"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["persisted_at"],
            payload["data"]["persisted_report"]["created_at"],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["redaction_status"], "none"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "cli_command"
        )
        self.assertEqual(payload["data"]["persisted_report"]["id"], 1)

    def test_analyze_command_serializes_duplicate_terraform_action_parse_failure(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        valid_path = Path(self.tempdir.name) / "plan.json"
        valid_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        duplicate_path = Path(self.tempdir.name) / "duplicate-plan.json"
        duplicate_path.write_text(
            '{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["create", "create"]}}]}',
            encoding="utf-8",
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review partial analysis.",
            explanation="One Terraform plan could not be parsed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        output = io.StringIO()

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(valid_path),
                    str(duplicate_path),
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        by_name = {
            file_result["file_name"]: file_result
            for file_result in payload["data"]["parse_batch"]["files"]
        }
        self.assertEqual(by_name["plan.json"]["status"], "parsed")
        self.assertEqual(by_name["duplicate-plan.json"]["status"], "failed")
        self.assertIn(
            "Duplicate Terraform action",
            by_name["duplicate-plan.json"]["issue"]["message"],
        )

    def test_analyze_command_captures_trigger_context_from_environment_when_available(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
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

    def test_analyze_command_accepts_project_key(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        output = io.StringIO()

        def passthrough_analyze_uploaded_files(
            files,
            completion_client=None,
            audit_context=None,
            project_id=None,
            project_key=None,
            workspace_id=None,
            workspace_key=None,
        ):
            return analysis_service_module.analyze_uploaded_files(
                files,
                completion_client=completion_client,
                audit_context=audit_context,
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )

        with (
            patch(
                "cli.analyze.analyze_uploaded_files",
                side_effect=passthrough_analyze_uploaded_files,
            ),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )

    def test_analyze_command_accepts_project_id(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        output = io.StringIO()

        def passthrough_analyze_uploaded_files(
            files,
            completion_client=None,
            audit_context=None,
            project_id=None,
            project_key=None,
            workspace_id=None,
            workspace_key=None,
        ):
            return analysis_service_module.analyze_uploaded_files(
                files,
                completion_client=completion_client,
                audit_context=audit_context,
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )

        with (
            patch(
                "cli.analyze.analyze_uploaded_files",
                side_effect=passthrough_analyze_uploaded_files,
            ),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project-id",
                    str(project.id),
                    str(artifact_path),
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )

    def test_analyze_command_accepts_project_id_with_blank_project_key(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        output = io.StringIO()

        def passthrough_analyze_uploaded_files(
            files,
            completion_client=None,
            audit_context=None,
            project_id=None,
            project_key=None,
            workspace_id=None,
            workspace_key=None,
        ):
            return analysis_service_module.analyze_uploaded_files(
                files,
                completion_client=completion_client,
                audit_context=audit_context,
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )

        with (
            patch(
                "cli.analyze.analyze_uploaded_files",
                side_effect=passthrough_analyze_uploaded_files,
            ),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project-id",
                    str(project.id),
                    "--project",
                    "   ",
                    str(artifact_path),
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )

    def test_analyze_command_accepts_project_workspace_key(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        output = io.StringIO()

        def passthrough_analyze_uploaded_files(
            files,
            completion_client=None,
            audit_context=None,
            project_id=None,
            project_key=None,
            workspace_id=None,
            workspace_key=None,
        ):
            return analysis_service_module.analyze_uploaded_files(
                files,
                completion_client=completion_client,
                audit_context=audit_context,
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
            )

        with (
            patch(
                "cli.analyze.analyze_uploaded_files",
                side_effect=passthrough_analyze_uploaded_files,
            ),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    "--workspace",
                    "prod",
                    str(artifact_path),
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["workspace"]["workspace_key"], "prod"
        )
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertFalse(payload["data"]["advisory"]["should_block"])
        self.assertIn(
            payload["data"]["advisory"]["recommendation"],
            {"go", "caution", "no-go"},
        )
        self.assertIn(
            "DeployWhisper",
            payload["data"]["share_summary"]["json_payload"]["verdict_banner"],
        )
        self.assertIn(
            payload["data"]["share_summary"]["json_payload"]["evidence_law_status"],
            {"Satisfied", "Needs review", "Reconciled", "Detail omitted"},
        )
        self.assertIn("top_findings", payload["data"]["share_summary"]["json_payload"])
        self.assertIn("uncertainty_flags", payload["data"]["advisory"])

    def test_outcome_record_command_records_deployment_result(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        persisted = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Outcome capture test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: outcome capture test report.",
                explanation="Outcome capture test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "cli"},
        )
        output = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "outcome",
                    "record",
                    "--analysis-id",
                    str(persisted["id"]),
                    "--outcome",
                    "success",
                    "--deployed-at",
                    "2026-04-30T08:15:00Z",
                    "--notes",
                    "Deployment succeeded after review.",
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["meta"]["interface"], "cli")
        self.assertEqual(payload["data"]["analysis_id"], persisted["id"])
        self.assertEqual(payload["data"]["project"]["project_key"], "payments")
        self.assertEqual(payload["data"]["outcome"], "success")
        self.assertIsNone(payload["data"]["summary"])
        self.assertEqual(payload["data"]["notes"], "Deployment succeeded after review.")

    def test_outcome_record_command_reports_unknown_analysis_with_structured_error(
        self,
    ) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "outcome",
                    "record",
                    "--analysis-id",
                    "999",
                    "--outcome",
                    "success",
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "analysis_not_found")

    def test_outcome_record_command_returns_authorization_error_for_reviewer(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        persisted = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Outcome capture authorization test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: outcome capture authorization test report.",
                explanation="Outcome capture authorization test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "cli"},
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "outcome",
                    "record",
                    "--analysis-id",
                    str(persisted["id"]),
                    "--outcome",
                    "success",
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "reviewer",
                    "DEPLOYWHISPER_PROJECT_KEYS": "payments",
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn("payments", payload["error"]["message"])

    def test_outcome_record_command_masks_missing_analysis_for_scoped_actor(
        self,
    ) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "outcome",
                    "record",
                    "--analysis-id",
                    "999",
                    "--outcome",
                    "success",
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "maintainer",
                    "DEPLOYWHISPER_PROJECT_KEYS": "payments",
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_outcome_record_command_masks_conflicting_project_for_scoped_actor(
        self,
    ) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        persisted = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Outcome capture authorization test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: outcome capture authorization test report.",
                explanation="Outcome capture authorization test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=allowed.id,
            audit_context={"source_interface": "cli"},
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "outcome",
                    "record",
                    "--analysis-id",
                    str(persisted["id"]),
                    "--project-id",
                    str(forbidden.id),
                    "--outcome",
                    "success",
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "maintainer",
                    "DEPLOYWHISPER_PROJECT_KEYS": allowed.project_key,
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_outcome_record_command_masks_foreign_workspace_for_scoped_actor(
        self,
    ) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        workspace = project_service_module.create_workspace(
            project_key=forbidden.project_key,
            workspace_key="prod",
            display_name="Production",
        )
        persisted = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Outcome capture authorization test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: outcome capture authorization test report.",
                explanation="Outcome capture authorization test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=allowed.id,
            audit_context={"source_interface": "cli"},
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "outcome",
                    "record",
                    "--analysis-id",
                    str(persisted["id"]),
                    "--workspace-id",
                    str(workspace.id),
                    "--outcome",
                    "success",
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "maintainer",
                    "DEPLOYWHISPER_PROJECT_KEYS": allowed.project_key,
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_analyze_command_reports_unsupported_inputs_with_structured_error(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "README.txt"
        artifact_path.write_text("hello", encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
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

    def test_analyze_command_rejects_missing_scope_before_unsupported_preflight(
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
        self.assertEqual(payload["error"]["code"], "missing_project_scope")

    def test_analyze_command_reports_missing_files_with_structured_error(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        missing_path = Path(self.tempdir.name) / "missing-plan.json"
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(missing_path),
                ],
            ),
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

    def test_analyze_command_returns_authorization_error_for_read_only(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text('{"resource_changes": []}', encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "read-only",
                    "DEPLOYWHISPER_PROJECT_KEYS": "payments",
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn("payments", payload["error"]["message"])

    def test_analyze_command_requires_scope_for_non_admin_role(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text('{"resource_changes": []}', encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
            patch.dict(
                os.environ,
                {"DEPLOYWHISPER_PROJECT_ROLE": "contributor"},
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_scope_required")

    def test_analyze_command_masks_missing_project_id_for_scoped_actor(self) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text('{"resource_changes": []}', encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project-id",
                    "999",
                    str(artifact_path),
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "contributor",
                    "DEPLOYWHISPER_PROJECT_KEYS": "payments",
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_analyze_command_masks_conflicting_project_reference_for_scoped_actor(
        self,
    ) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text('{"resource_changes": []}', encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    allowed.project_key,
                    "--project-id",
                    str(forbidden.id),
                    str(artifact_path),
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "contributor",
                    "DEPLOYWHISPER_PROJECT_KEYS": allowed.project_key,
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_project_create_command_reports_created_workspace(self) -> None:
        output = io.StringIO()

        with (
            patch(
                "sys.argv",
                ["deploywhisper", "project", "create", "payments", "Payments API"],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Created project payments", output.getvalue())

    def test_project_list_command_includes_default_workspace(self) -> None:
        output = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "project", "list"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("unassigned", output.getvalue())

    def test_project_roles_command_lists_capabilities(self) -> None:
        output = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "project", "roles"]),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("admin:", output.getvalue())
        self.assertIn("project.manage", output.getvalue())

    def test_project_create_command_returns_authorization_error_for_read_only(
        self,
    ) -> None:
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                ["deploywhisper", "project", "create", "payments", "Payments API"],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "read-only",
                    "DEPLOYWHISPER_PROJECT_KEYS": "payments",
                },
                clear=False,
            ),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn("payments", payload["error"]["message"])

    def test_project_workspace_create_and_list_commands(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        create_output = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "project",
                    "workspace",
                    "create",
                    "payments",
                    "Production / US East",
                    "Production US East",
                    "--environment",
                    "prod",
                ],
            ),
            redirect_stdout(create_output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Created workspace production-us-east", create_output.getvalue())

        list_output = io.StringIO()
        with (
            patch(
                "sys.argv",
                ["deploywhisper", "project", "workspace", "list", "payments"],
            ),
            redirect_stdout(list_output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(
            "payments/production-us-east: Production US East (prod)",
            list_output.getvalue(),
        )

    def test_project_command_requires_subcommand(self) -> None:
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "project"]),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("required", stderr.getvalue().lower())

    def test_topology_import_command_saves_project_scoped_context(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        topology_path = Path(self.tempdir.name) / "topology.json"
        topology_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        output = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "topology",
                    "import",
                    "--from",
                    "custom",
                    "--source",
                    str(topology_path),
                    "--project",
                    "payments",
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["data"]["project"]["project_key"], "payments")
        self.assertEqual(payload["data"]["topology"]["service_count"], 1)
        self.assertEqual(payload["data"]["import"]["source_type"], "custom")
        self.assertEqual(
            payload["data"]["import"]["diff"]["added_services"],
            ["api"],
        )

    def test_topology_import_command_requires_project_scope_for_workspace_id(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        workspace = project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="prod",
            display_name="Production",
        )
        topology_path = Path(self.tempdir.name) / "topology.json"
        topology_path.write_text(json.dumps({"services": []}), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "topology",
                    "import",
                    "--from",
                    "custom",
                    "--source",
                    str(topology_path),
                    "--workspace-id",
                    str(workspace.id),
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "missing_project_scope")

    def test_topology_import_command_returns_authorization_error_for_read_only(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        topology_path = Path(self.tempdir.name) / "topology.json"
        topology_path.write_text(json.dumps({"services": []}), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "topology",
                    "import",
                    "--from",
                    "custom",
                    "--source",
                    str(topology_path),
                    "--project",
                    "payments",
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "read-only",
                    "DEPLOYWHISPER_PROJECT_KEYS": "payments",
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn("payments", payload["error"]["message"])

    def test_topology_import_command_rejects_unknown_project(self) -> None:
        topology_path = Path(self.tempdir.name) / "topology.json"
        topology_path.write_text(json.dumps({"services": []}), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "topology",
                    "import",
                    "--from",
                    "custom",
                    "--source",
                    str(topology_path),
                    "--project",
                    "missing",
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_not_found")

    def test_topology_import_command_masks_conflicting_project_for_scoped_actor(
        self,
    ) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        topology_path = Path(self.tempdir.name) / "topology.json"
        topology_path.write_text(json.dumps({"services": []}), encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "topology",
                    "import",
                    "--from",
                    "custom",
                    "--source",
                    str(topology_path),
                    "--project",
                    allowed.project_key,
                    "--project-id",
                    str(forbidden.id),
                ],
            ),
            patch.dict(
                os.environ,
                {
                    "DEPLOYWHISPER_PROJECT_ROLE": "maintainer",
                    "DEPLOYWHISPER_PROJECT_KEYS": allowed.project_key,
                },
                clear=False,
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_topology_import_command_warns_without_failing_for_unknown_source(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        output = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "topology",
                    "import",
                    "--from",
                    "pulumi",
                    "--source",
                    "state.json",
                    "--project",
                    "payments",
                ],
            ),
            redirect_stdout(output),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["data"]["import"]["applied"])
        self.assertEqual(
            payload["data"]["import"]["unsupported_resources"][0]["resource_ref"],
            "state.json",
        )
        self.assertIn("unsupported", payload["data"]["import"]["warnings"][0].lower())

    def test_topology_command_requires_subcommand(self) -> None:
        stderr = io.StringIO()

        with (
            patch("sys.argv", ["deploywhisper", "topology"]),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("required", stderr.getvalue().lower())

    def test_analyze_command_rejects_conflicting_project_reference(self) -> None:
        first = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "services.analysis_service.build_parse_batch",
                side_effect=AssertionError("project must resolve before parsing"),
            ) as build_parse_batch,
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project-id",
                    str(first.id),
                    "--project",
                    "platform",
                    str(artifact_path),
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "conflicting_project_reference")
        build_parse_batch.assert_not_called()
        with database_module.SessionLocal() as session:
            self.assertEqual(
                analysis_reports_repository_module.count_analysis_reports(session),
                0,
            )

    def test_analyze_command_rejects_unknown_project_before_parsing(self) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "services.analysis_service.build_parse_batch",
                side_effect=AssertionError("project must resolve before parsing"),
            ) as build_parse_batch,
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "missing",
                    str(artifact_path),
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "project_not_found")
        build_parse_batch.assert_not_called()
        with database_module.SessionLocal() as session:
            self.assertEqual(
                analysis_reports_repository_module.count_analysis_reports(session),
                0,
            )

    def test_analyze_command_rejects_missing_project_scope_before_parsing(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "services.analysis_service.build_parse_batch",
                side_effect=AssertionError("project must resolve before parsing"),
            ) as build_parse_batch,
            patch("sys.argv", ["deploywhisper", "analyze", str(artifact_path)]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "missing_project_scope")
        build_parse_batch.assert_not_called()
        with database_module.SessionLocal() as session:
            self.assertEqual(
                analysis_reports_repository_module.count_analysis_reports(session),
                0,
            )

    def test_analyze_command_rejects_blank_explicit_project_key_before_parsing(
        self,
    ) -> None:
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "services.analysis_service.build_parse_batch",
                side_effect=AssertionError("project must resolve before parsing"),
            ) as build_parse_batch,
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "   ",
                    str(artifact_path),
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "invalid_project_reference")
        build_parse_batch.assert_not_called()

    def test_analyze_command_preserves_distinct_files_with_same_basename(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        first_dir = Path(self.tempdir.name) / "first"
        second_dir = Path(self.tempdir.name) / "second"
        first_dir.mkdir(parents=True, exist_ok=True)
        second_dir.mkdir(parents=True, exist_ok=True)
        first_path = first_dir / "plan.json"
        second_path = second_dir / "plan.json"
        first_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.first", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        second_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.second", "change": {"actions": ["update"]}}]}',
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
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(first_path),
                    str(second_path),
                ],
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
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
            encoding="utf-8",
        )
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "cli.analyze.analyze_uploaded_files", side_effect=RuntimeError("boom")
            ),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
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

    def test_analyze_command_reports_persistence_failures_without_success(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text('{"resource_changes": []}', encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch(
                "cli.analyze.analyze_uploaded_files",
                side_effect=analysis_service_module.AnalysisPersistenceError(
                    "database is read-only"
                ),
            ),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertEqual(payload["error"]["code"], "report_persistence_failed")
        self.assertEqual(
            payload["error"]["message"],
            "Report persistence failed; final analysis success was not returned.",
        )
        self.assertEqual(
            payload["error"]["details"]["reason"],
            analysis_service_module.AnalysisPersistenceError.public_reason,
        )
        self.assertNotIn("database is read-only", stderr.getvalue())

    def test_analyze_command_rejects_payloads_over_limit_before_reading_all_bytes(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "large-plan.json"
        artifact_path.write_text("x" * 11, encoding="utf-8")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("cli.analyze.MAX_TOTAL_UPLOAD_BYTES", 10),
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
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
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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
                    normalized_action="destroy",
                    severity="critical",
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
            source="fallback",
            provider="openai",
            model="gpt-4.1-mini",
            local_mode=False,
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
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
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
        self.assertEqual(payload["data"]["advisory"]["recommendation"], "no-go")
        self.assertEqual(payload["data"]["advisory"]["severity"], "critical")
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["evidence_law_status"],
            "Satisfied",
        )
        self.assertIn(
            "deterministic evidence",
            payload["data"]["share_summary"]["json_payload"]["evidence_law_detail"],
        )
        self.assertIn("Evidence Law", payload["data"]["share_summary"]["plain_text"])
        self.assertIn("context_completeness", payload["data"]["assessment"])
        self.assertIn("context_completeness", payload["data"]["persisted_report"])
        self.assertIn("rollback_plan", payload["data"]["persisted_report"])
        self.assertIn("blast_radius", payload["data"]["persisted_report"])
        self.assertFalse(payload["data"]["narrative"]["available"])
        self.assertTrue(payload["data"]["narrative"]["degraded"])
        self.assertTrue(payload["data"]["persisted_report"]["narrative_degraded"])
        self.assertEqual(
            payload["data"]["persisted_report"]["narrative_provider"], "openai"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["narrative_model"], "gpt-4.1-mini"
        )
        self.assertFalse(payload["data"]["persisted_report"]["narrative_local_mode"])
        self.assertTrue(payload["data"]["evidence_items"])
        self.assertTrue(payload["data"]["findings"])
        self.assertTrue(payload["data"]["persisted_report"]["findings"])
        self.assertTrue(payload["data"]["persisted_report"]["evidence_items"])
        self.assertIn(
            "partial_context", payload["data"]["advisory"]["uncertainty_flags"]
        )
        self.assertIn(
            "narrative_degraded", payload["data"]["advisory"]["uncertainty_flags"]
        )

    def test_analyze_command_suppresses_non_json_stream_noise_on_success(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        artifact_path = Path(self.tempdir.name) / "plan.json"
        artifact_path.write_text(
            '{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
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

        def noisy_analyze_uploaded_files(
            files,
            completion_client=None,
            audit_context=None,
            project_id=None,
            project_key=None,
            workspace_id=None,
            workspace_key=None,
        ):
            print("unexpected provider noise")
            print("unexpected provider noise", file=sys.stderr)
            return analysis_service_module.analyze_uploaded_files(
                files,
                completion_client=completion_client,
                audit_context=audit_context,
                project_id=project_id,
                project_key=project_key,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
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
            patch(
                "sys.argv",
                [
                    "deploywhisper",
                    "analyze",
                    "--project",
                    "payments",
                    str(artifact_path),
                ],
            ),
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
