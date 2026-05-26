"""Tests for the GitHub installation wizard service."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from integrations.github import init_service


class GitHubInitServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_app_base_url = os.environ.get("APP_BASE_URL")
        os.environ["APP_BASE_URL"] = "https://deploywhisper.example.com"

    def tearDown(self) -> None:
        if self.original_app_base_url is None:
            os.environ.pop("APP_BASE_URL", None)
        else:
            os.environ["APP_BASE_URL"] = self.original_app_base_url

    def test_collect_github_init_options_defaults_to_action_first_answers(self) -> None:
        responses = iter(
            [
                "/tmp/example-repo",
                "",
                "",
                "",
                "payments",
                "",
                "n",
            ]
        )

        options = init_service.collect_github_init_options(
            repo_path=None,
            workflow_path=None,
            api_endpoint=None,
            enable_github_app=None,
            base_branch=None,
            github_owner=None,
            github_app_name=None,
            github_app_slug=None,
            public_base_url=None,
            branch_name=None,
            input_fn=lambda _: next(responses),
        )

        self.assertEqual(options.repo_path, "/tmp/example-repo")
        self.assertEqual(options.workflow_path, init_service.DEFAULT_WORKFLOW_PATH)
        self.assertEqual(
            options.api_endpoint,
            "https://deploywhisper.example.com/api/v1/analyses",
        )
        self.assertEqual(options.base_branch, "main")
        self.assertEqual(options.project_key, "payments")
        self.assertEqual(options.workspace_key, "")
        self.assertFalse(options.allow_derived_project_scope)
        self.assertFalse(options.enable_github_app)

    def test_collect_github_init_options_prompts_for_self_hosted_app_fields(
        self,
    ) -> None:
        responses = iter(
            [
                "/tmp/example-repo",
                "",
                "",
                "",
                "payments",
                "prod",
                "y",
                "acme",
                "DeployWhisper Acme",
                "deploywhisper-acme",
                "https://deploywhisper.acme.example.com",
            ]
        )

        options = init_service.collect_github_init_options(
            repo_path=None,
            workflow_path=None,
            api_endpoint=None,
            enable_github_app=None,
            base_branch=None,
            github_owner=None,
            github_app_name=None,
            github_app_slug=None,
            public_base_url=None,
            branch_name=None,
            input_fn=lambda _: next(responses),
        )

        self.assertTrue(options.enable_github_app)
        self.assertEqual(options.base_branch, "main")
        self.assertEqual(options.project_key, "payments")
        self.assertEqual(options.workspace_key, "prod")
        self.assertEqual(options.github_owner, "acme")
        self.assertEqual(options.github_app_name, "DeployWhisper Acme")
        self.assertEqual(options.github_app_slug, "deploywhisper-acme")
        self.assertEqual(
            options.public_base_url, "https://deploywhisper.acme.example.com"
        )

    @patch("integrations.github.init_service._require_binary")
    @patch("integrations.github.init_service._run_command")
    def test_run_github_init_writes_files_and_opens_pr(
        self,
        run_command,
        require_binary,
    ) -> None:
        require_binary.return_value = None
        command_log: list[tuple[str, ...]] = []

        def fake_run_command(repo_root: Path, *args: str, check: bool = True):
            command_log.append(args)
            if args[:3] == ("git", "rev-parse", "--is-inside-work-tree"):
                return subprocess.CompletedProcess(args, 0, "true\n", "")
            if args[:3] == ("git", "status", "--porcelain"):
                return subprocess.CompletedProcess(args, 0, "", "")
            if args[:4] == ("git", "remote", "get-url", "origin"):
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "git@github.com:acme/example-repo.git\n",
                    "",
                )
            if args[:3] == ("git", "branch", "--show-current"):
                return subprocess.CompletedProcess(args, 0, "feature/existing\n", "")
            if args[:4] == ("git", "show-ref", "--verify", "--quiet"):
                if args[4] == "refs/heads/develop":
                    return subprocess.CompletedProcess(args, 0, "", "")
                if args[4] == "refs/heads/feature/deploywhisper-github-init":
                    return subprocess.CompletedProcess(args, 1, "", "")
                return subprocess.CompletedProcess(args, 1, "", "")
            if args[:3] == ("git", "rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args[:3] == ("gh", "pr", "create"):
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "https://github.com/acme/example-repo/pull/7\n",
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        run_command.side_effect = fake_run_command

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "README.md").write_text("# Example Repo\n", encoding="utf-8")

            result = init_service.run_github_init(
                init_service.GitHubInitOptions(
                    repo_path=str(repo_root),
                    workflow_path=".github/workflows/deploywhisper.yml",
                    api_endpoint="https://deploywhisper.example.com/api/v1/analyses",
                    enable_github_app=True,
                    base_branch="develop",
                    project_key="payments",
                    workspace_key="prod",
                    github_owner="acme",
                    github_app_name="DeployWhisper Acme",
                    github_app_slug="deploywhisper-acme",
                    public_base_url="https://deploywhisper.acme.example.com",
                )
            )

            workflow_text = (
                repo_root / ".github/workflows/deploywhisper.yml"
            ).read_text(encoding="utf-8")
            readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
            notes_text = (
                repo_root / ".github/deploywhisper-self-hosted-github-app.md"
            ).read_text(encoding="utf-8")

        self.assertEqual(result.base_branch, "develop")
        self.assertEqual(result.branch_name, "feature/deploywhisper-github-init")
        self.assertEqual(result.commit_sha, "abc123")
        self.assertEqual(result.pr_url, "https://github.com/acme/example-repo/pull/7")
        self.assertIn("deploywhisper/analyze-action@v1", workflow_text)
        self.assertIn(
            "DEPLOYWHISPER_API_URL: https://deploywhisper.example.com/api/v1/analyses",
            workflow_text,
        )
        self.assertIn("project-key: payments", workflow_text)
        self.assertIn("workspace-key: prod", workflow_text)
        self.assertIn('allow-derived-project-scope: "false"', workflow_text)
        self.assertIn(init_service.README_SECTION_START, readme_text)
        self.assertIn("Project scope: `project-key=payments`", readme_text)
        self.assertIn("Workspace scope: `workspace-key=prod`", readme_text)
        self.assertIn("Advanced self-hosted GitHub App", readme_text)
        self.assertIn("DeployWhisper Acme", notes_text)
        self.assertIn(
            ("git", "checkout", "develop"),
            command_log,
        )
        self.assertIn(
            ("git", "checkout", "-b", "feature/deploywhisper-github-init"), command_log
        )
        self.assertIn(
            ("git", "push", "-u", "origin", "feature/deploywhisper-github-init"),
            command_log,
        )
        self.assertTrue(
            any(command[:3] == ("gh", "pr", "create") for command in command_log)
        )

    @patch("integrations.github.init_service._require_binary")
    @patch("integrations.github.init_service._run_command")
    def test_run_github_init_requires_clean_target_repo(
        self,
        run_command,
        require_binary,
    ) -> None:
        require_binary.return_value = None

        def fake_run_command(repo_root: Path, *args: str, check: bool = True):
            if args[:3] == ("git", "rev-parse", "--is-inside-work-tree"):
                return subprocess.CompletedProcess(args, 0, "true\n", "")
            if args[:3] == ("git", "status", "--porcelain"):
                return subprocess.CompletedProcess(args, 0, " M README.md\n", "")
            if args[:4] == ("git", "remote", "get-url", "origin"):
                return subprocess.CompletedProcess(
                    args,
                    0,
                    "git@github.com:acme/example-repo.git\n",
                    "",
                )
            return subprocess.CompletedProcess(args, 0, "", "")

        run_command.side_effect = fake_run_command

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            with self.assertRaisesRegex(
                init_service.GitHubInitError,
                "uncommitted changes",
            ):
                init_service.run_github_init(
                    init_service.GitHubInitOptions(
                        repo_path=str(repo_root),
                        workflow_path=".github/workflows/deploywhisper.yml",
                        api_endpoint="https://deploywhisper.example.com/api/v1/analyses",
                        enable_github_app=False,
                        base_branch="main",
                        project_key="payments",
                    )
                )

    def test_run_github_init_rejects_missing_project_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(
                init_service.GitHubInitError,
                "project scope is required",
            ):
                init_service.run_github_init(
                    init_service.GitHubInitOptions(
                        repo_path=tmpdir,
                        workflow_path=".github/workflows/deploywhisper.yml",
                        api_endpoint="https://deploywhisper.example.com/api/v1/analyses",
                        enable_github_app=False,
                        base_branch="main",
                    )
                )

    def test_run_github_init_rejects_non_positive_project_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(
                init_service.GitHubInitError,
                "project id must be a positive number",
            ):
                init_service.run_github_init(
                    init_service.GitHubInitOptions(
                        repo_path=tmpdir,
                        workflow_path=".github/workflows/deploywhisper.yml",
                        api_endpoint="https://deploywhisper.example.com/api/v1/analyses",
                        enable_github_app=False,
                        base_branch="main",
                        project_id="0",
                    )
                )

    @patch("integrations.github.init_service._git_ref_exists")
    @patch("integrations.github.init_service._run_command")
    def test_infer_base_branch_prefers_develop_when_present(
        self,
        run_command,
        git_ref_exists,
    ) -> None:
        git_ref_exists.side_effect = lambda _repo_root, ref_name: (
            ref_name
            in {
                "refs/heads/develop",
                "refs/remotes/origin/develop",
            }
        )

        inferred = init_service._infer_base_branch(".")

        self.assertEqual(inferred, "develop")
        run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
