"""Synthetic connector credential boundary regression tests."""

from __future__ import annotations

from dataclasses import replace
import io
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request

from integrations.github import app_service, init_service


class GitHubCredentialSecurityTests(unittest.TestCase):
    def test_oauth_state_rejects_sensitive_return_destination(self):
        config = replace(
            app_service.get_github_app_config(),
            client_id="synthetic-client",
            client_secret="synthetic-secret",
            app_base_url="https://deploywhisper.example",
        )
        for return_to in (
            "/settings?token=synthetic-secret",
            "https://user:synthetic-secret@example.com",
            "/settings?%74oken=synthetic-secret",
        ):
            with (
                self.subTest(return_to=return_to),
                self.assertRaises(app_service.GitHubAppConfigurationError),
            ):
                app_service.build_github_app_oauth_url(
                    return_to=return_to, config=config
                )
        self.assertIn(
            "state=",
            app_service.build_github_app_oauth_url(
                return_to="/settings", config=config
            ),
        )

    def test_upstream_error_bodies_never_enter_public_exceptions(self):
        marker = "synthetic-connector-credential-123"
        for oauth in (False, True):
            with self.subTest(oauth=oauth):
                failure = HTTPError(
                    "https://api.github.com",
                    403,
                    "Forbidden",
                    {},
                    io.BytesIO(marker.encode()),
                )
                opener = MagicMock()
                opener.open.side_effect = failure
                with patch.object(
                    app_service.request, "build_opener", return_value=opener
                ):
                    with self.assertRaises(app_service.GitHubAppRequestError) as caught:
                        if oauth:
                            app_service._post_form_json(
                                "https://github.com/login/oauth/access_token",
                                {"client_secret": marker},
                            )
                        else:
                            app_service._github_api_request(
                                "https://api.github.com/repos/org/repo",
                                token=marker,
                                method="GET",
                                body=None,
                            )
                self.assertNotIn(marker, str(caught.exception))
                self.assertIn("403", str(caught.exception))

    def test_static_urls_reject_credentials_and_query_before_publication(self):
        for url in (
            "https://user:synthetic-secret@example.com",
            "https://example.com?token=synthetic-secret",
            "https://example.com#synthetic-secret",
        ):
            with self.subTest(url=url):
                with self.assertRaises(init_service.GitHubInitError):
                    init_service._validate_url(url, field_name="API endpoint")
                config = replace(app_service.get_github_app_config(), authorize_url=url)
                with self.assertRaises(app_service.GitHubAppConfigurationError):
                    app_service._repository_reference("org", "repo", config=config)
        config = replace(
            app_service.get_github_app_config(), slug="app?token=synthetic-secret"
        )
        with self.assertRaises(app_service.GitHubAppConfigurationError):
            app_service._repository_reference("org", "repo", config=config)

    def test_authenticated_fetch_rejects_plain_http_before_network(self):
        with patch.object(app_service.request, "build_opener") as build_opener:
            with self.assertRaises(app_service.GitHubAppConfigurationError):
                app_service._github_api_request(
                    "http://github.example/api/v3",
                    token="synthetic-secret",
                    method="GET",
                    body=None,
                )
            build_opener.assert_not_called()

    def test_wizard_rejects_secret_path_before_any_repository_mutation(self):
        marker = "synthetic-connector-credential-123"
        options = init_service.GitHubInitOptions(
            repo_path=".",
            workflow_path=".github/workflows/deploywhisper.yml",
            api_endpoint=f"https://example.com/{marker}/analyses",
            enable_github_app=False,
            base_branch="develop",
            project_key="payments",
        )
        with (
            patch.dict(os.environ, {"DEPLOYWHISPER_API_TOKEN": marker}),
            patch.object(init_service, "_require_binary") as require_binary,
        ):
            with self.assertRaises(init_service.GitHubInitError) as caught:
                init_service.run_github_init(options)
            self.assertNotIn(marker, str(caught.exception))
            require_binary.assert_not_called()

    def test_redirects_cannot_forward_authorization_to_another_origin(self):
        handler = app_service._GitHubRedirectHandler()
        req = Request(
            "https://github.example/api/v3/repos/org/repo",
            headers={"Authorization": "Bearer synthetic-secret"},
        )
        for url in (
            "https://other.example/collect",
            "http://github.example/collect",
            "https://github.example:8443/collect",
        ):
            with (
                self.subTest(url=url),
                self.assertRaises(app_service.GitHubAppRequestError),
            ):
                handler.redirect_request(req, None, 302, "Found", {}, url)
        redirected = handler.redirect_request(
            req, None, 302, "Found", {}, "https://github.example/api/v3/repos/org/new"
        )
        self.assertEqual(
            redirected.get_header("Authorization"), req.get_header("Authorization")
        )

    def test_download_fallback_uses_trusted_contents_endpoint_for_enterprise(self):
        for base in ("https://api.github.com", "https://github.example/api/v3"):
            with (
                self.subTest(base=base),
                patch.object(
                    app_service,
                    "_github_api_json",
                    return_value={"download_url": "https://other.example/collect"},
                ),
                patch.object(
                    app_service, "_github_api_request", return_value=b"artifact"
                ) as fetch,
            ):
                self.assertEqual(
                    app_service._download_repo_file(
                        owner="org",
                        repo_name="repo",
                        path="plan.tf",
                        ref="abc",
                        installation_token="synthetic-secret",
                        api_base_url=base,
                    ),
                    b"artifact",
                )
                self.assertEqual(
                    fetch.call_args.args[0],
                    base + "/repos/org/repo/contents/plan.tf?ref=abc",
                )
                self.assertEqual(
                    fetch.call_args.kwargs["accept"], "application/vnd.github.raw+json"
                )

    def test_wizard_subprocess_errors_omit_output_and_argument_secrets(self):
        marker = "synthetic-connector-credential-123"
        result = subprocess.CompletedProcess(["git"], 1, marker, marker)
        with patch.object(init_service.subprocess, "run", return_value=result):
            with self.assertRaises(init_service.GitHubInitError) as caught:
                init_service._run_command(Path("."), "git", "push", marker)
        self.assertNotIn(marker, str(caught.exception))
