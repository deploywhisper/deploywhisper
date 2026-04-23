"""Tests for the GitHub App adapter service."""

from __future__ import annotations

import hmac
import hashlib
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from integrations.github import app_service


class GitHubAppServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_keys = [
            "APP_BASE_URL",
            "DEPLOYWHISPER_GITHUB_APP_ENABLED",
            "DEPLOYWHISPER_GITHUB_APP_ID",
            "DEPLOYWHISPER_GITHUB_APP_SLUG",
            "DEPLOYWHISPER_GITHUB_APP_CLIENT_ID",
            "DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET",
            "DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET",
            "DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY",
            "DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY_PATH",
            "DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED",
            "DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED",
        ]
        self.original_env = {key: os.environ.get(key) for key in self.env_keys}
        os.environ["APP_BASE_URL"] = "https://deploywhisper.example.com"
        os.environ["DEPLOYWHISPER_GITHUB_APP_ENABLED"] = "true"
        os.environ["DEPLOYWHISPER_GITHUB_APP_ID"] = "12345"
        os.environ["DEPLOYWHISPER_GITHUB_APP_SLUG"] = "deploywhisper"
        os.environ["DEPLOYWHISPER_GITHUB_APP_CLIENT_ID"] = "client-123"
        os.environ["DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET"] = "client-secret"
        os.environ["DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET"] = "webhook-secret"
        os.environ["DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY"] = (
            "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----"
        )
        os.environ["DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED"] = "true"
        os.environ["DEPLOYWHISPER_GITHUB_APP_CHECKS_ENABLED"] = "true"

    def tearDown(self) -> None:
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_verify_github_webhook_signature_accepts_valid_sha256(self) -> None:
        payload = b'{"zen":"ship it"}'
        signature = (
            "sha256="
            + hmac.new(
                b"webhook-secret",
                payload,
                hashlib.sha256,
            ).hexdigest()
        )

        self.assertTrue(app_service.verify_github_webhook_signature(payload, signature))
        self.assertFalse(
            app_service.verify_github_webhook_signature(payload, "sha256=bad")
        )

    def test_build_github_app_oauth_url_includes_signed_state(self) -> None:
        authorize_url = app_service.build_github_app_oauth_url(return_to="/settings")
        parsed = urlparse(authorize_url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(query["client_id"], ["client-123"])
        self.assertEqual(
            query["redirect_uri"],
            ["https://deploywhisper.example.com/api/v1/github/app/oauth/callback"],
        )
        self.assertIn("state", query)
        self.assertIn(".", query["state"][0])

    @patch("integrations.github.app_service._post_form_json")
    def test_complete_github_app_oauth_returns_installation_handoff(
        self,
        post_form_json,
    ) -> None:
        post_form_json.return_value = {
            "access_token": "user-token",
            "token_type": "bearer",
            "scope": "checks",
        }
        state = app_service._encode_oauth_state(
            {"return_to": "/settings"},
            secret="client-secret",
        )

        result = app_service.complete_github_app_oauth(code="abc123", state=state)

        self.assertEqual(result.user_access_token, "user-token")
        self.assertEqual(
            result.install_url,
            "https://github.com/apps/deploywhisper/installations/new",
        )
        self.assertEqual(result.state_return_to, "/settings")

    def test_check_run_conclusion_matches_story_contract(self) -> None:
        self.assertEqual(app_service._check_run_conclusion("go"), "success")
        self.assertEqual(app_service._check_run_conclusion("caution"), "neutral")
        self.assertEqual(app_service._check_run_conclusion("no-go"), "failure")

    @patch("integrations.github.app_service._create_check_run")
    @patch("integrations.github.app_service.analyze_uploaded_files")
    @patch("integrations.github.app_service._load_pull_request_artifacts")
    @patch("integrations.github.app_service._generate_installation_access_token")
    def test_handle_github_app_webhook_runs_analysis_and_check_run(
        self,
        generate_installation_access_token,
        load_pull_request_artifacts,
        analyze_uploaded_files,
        create_check_run,
    ) -> None:
        generate_installation_access_token.return_value = "installation-token"
        load_pull_request_artifacts.return_value = [("plan.tf", b'resource "x" "y" {}')]
        analyze_uploaded_files.return_value = type(
            "Result",
            (),
            {
                "assessment": type("Assessment", (), {"recommendation": "caution"})(),
                "persisted_report": {"id": 17},
            },
        )()
        create_check_run.return_value = 991

        result = app_service.handle_github_app_webhook(
            event_name="pull_request",
            payload={
                "action": "opened",
                "number": 3,
                "installation": {"id": 42},
                "repository": {
                    "name": "deploywhisper",
                    "owner": {"login": "deploywhisper"},
                },
                "pull_request": {
                    "number": 3,
                    "head": {"sha": "abc123"},
                },
            },
        )

        self.assertTrue(result.automatic_analysis_triggered)
        self.assertEqual(result.report_id, 17)
        self.assertEqual(result.check_run_id, 991)
        self.assertEqual(
            result.report_url, "https://deploywhisper.example.com/reports/17"
        )
        create_check_run.assert_called_once()
        call = create_check_run.call_args.kwargs
        self.assertEqual(call["title"], app_service.DEFAULT_CHECK_RUN_NAME)
        self.assertEqual(call["conclusion"], "neutral")
        self.assertEqual(
            call["details_url"],
            "https://deploywhisper.example.com/reports/17",
        )
        self.assertIn("advisory-only", call["summary"])
        self.assertIn("Open the full DeployWhisper report", call["text"])

    @patch("integrations.github.app_service.analyze_uploaded_files")
    @patch("integrations.github.app_service._load_pull_request_artifacts")
    @patch("integrations.github.app_service._generate_installation_access_token")
    def test_handle_github_app_webhook_requires_public_base_url_for_check_runs(
        self,
        generate_installation_access_token,
        load_pull_request_artifacts,
        analyze_uploaded_files,
    ) -> None:
        generate_installation_access_token.return_value = "installation-token"
        load_pull_request_artifacts.return_value = [("plan.tf", b'resource "x" "y" {}')]
        analyze_uploaded_files.return_value = type(
            "Result",
            (),
            {
                "assessment": type("Assessment", (), {"recommendation": "go"})(),
                "persisted_report": {"id": 17},
            },
        )()
        config = app_service.GitHubAppConfig(
            enabled=True,
            app_id="12345",
            slug="deploywhisper",
            client_id="client-123",
            client_secret="client-secret",
            webhook_secret="webhook-secret",
            private_key_pem="-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----",
            api_base_url="https://api.github.com",
            authorize_url="https://github.com/login/oauth/authorize",
            access_token_url="https://github.com/login/oauth/access_token",
            app_base_url=None,
            automatic_pr_events_enabled=True,
            checks_enabled=True,
        )

        with self.assertRaisesRegex(
            app_service.GitHubAppConfigurationError,
            "APP_BASE_URL or PUBLIC_APP_URL",
        ):
            app_service.handle_github_app_webhook(
                event_name="pull_request",
                payload={
                    "action": "opened",
                    "number": 3,
                    "installation": {"id": 42},
                    "repository": {
                        "name": "deploywhisper",
                        "owner": {"login": "deploywhisper"},
                    },
                    "pull_request": {
                        "number": 3,
                        "head": {"sha": "abc123"},
                    },
                },
                config=config,
            )
        analyze_uploaded_files.assert_not_called()

    def test_handle_github_app_webhook_skips_when_pr_automation_disabled(self) -> None:
        os.environ["DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED"] = "false"

        result = app_service.handle_github_app_webhook(
            event_name="pull_request",
            payload={"action": "opened"},
        )

        self.assertTrue(result.handled)
        self.assertFalse(result.automatic_analysis_triggered)

    @patch("integrations.github.app_service._download_repo_file")
    @patch("integrations.github.app_service._github_api_json")
    def test_load_pull_request_artifacts_rejects_payloads_over_session_limit(
        self,
        github_api_json,
        download_repo_file,
    ) -> None:
        github_api_json.side_effect = [
            [
                {"status": "modified", "filename": "one.tf"},
                {"status": "modified", "filename": "two.tf"},
            ],
            [],
        ]
        oversize = b"x" * 25_100_000
        download_repo_file.side_effect = [oversize, oversize]

        with self.assertRaisesRegex(
            app_service.GitHubAppRequestError,
            "50 MB analysis-session limit",
        ):
            app_service._load_pull_request_artifacts(
                owner="deploywhisper",
                repo_name="deploywhisper",
                pull_number=7,
                head_sha="abc123",
                installation_token="installation-token",
                api_base_url="https://api.github.com",
            )

    @patch("integrations.github.app_service._github_api_json")
    def test_create_check_run_includes_details_link_and_advisory_text(
        self,
        github_api_json,
    ) -> None:
        github_api_json.return_value = {"id": 991}

        check_run_id = app_service._create_check_run(
            owner="deploywhisper",
            repo_name="deploywhisper",
            head_sha="abc123",
            installation_token="installation-token",
            conclusion="failure",
            title=app_service.DEFAULT_CHECK_RUN_NAME,
            summary="Summary",
            details_url="https://deploywhisper.example.com/reports/17",
            text="[Open the full DeployWhisper report](https://deploywhisper.example.com/reports/17)",
            api_base_url="https://api.github.com",
        )

        self.assertEqual(check_run_id, 991)
        body = github_api_json.call_args.kwargs["body"]
        self.assertEqual(
            body["details_url"], "https://deploywhisper.example.com/reports/17"
        )
        self.assertEqual(body["output"]["title"], app_service.DEFAULT_CHECK_RUN_NAME)
        self.assertEqual(
            body["output"]["text"],
            "[Open the full DeployWhisper report](https://deploywhisper.example.com/reports/17)",
        )
