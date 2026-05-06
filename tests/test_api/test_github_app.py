"""API tests for the GitHub App adapter routes."""

from __future__ import annotations

import hmac
import hashlib
import os
import tempfile
import unittest
from importlib import reload
from unittest.mock import patch

import app as app_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
from integrations.github.app_service import GitHubAppProjectScopeError
from fastapi.testclient import TestClient


class GitHubAppRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tempdir.name}/github_app.db"
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
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        for key in [
            "DATABASE_URL",
            "APP_BASE_URL",
            "DEPLOYWHISPER_GITHUB_APP_ENABLED",
            "DEPLOYWHISPER_GITHUB_APP_ID",
            "DEPLOYWHISPER_GITHUB_APP_SLUG",
            "DEPLOYWHISPER_GITHUB_APP_CLIENT_ID",
            "DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET",
            "DEPLOYWHISPER_GITHUB_APP_WEBHOOK_SECRET",
            "DEPLOYWHISPER_GITHUB_APP_PRIVATE_KEY",
            "DEPLOYWHISPER_GITHUB_APP_PR_EVENTS_ENABLED",
        ]:
            os.environ.pop(key, None)
        self.tempdir.cleanup()

    def test_oauth_start_redirects_to_github(self) -> None:
        response = self.client.get(
            "/api/v1/github/app/oauth/start",
            params={"return_to": "/settings"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("client_id=client-123", response.headers["location"])
        self.assertIn("state=", response.headers["location"])

    def test_webhook_rejects_invalid_signature(self) -> None:
        response = self.client.post(
            "/api/v1/github/app/webhook",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=bad",
            },
            json={"action": "opened"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("github_app_webhook_forbidden", response.text)

    @patch("api.routes.github_app.handle_github_app_webhook")
    def test_webhook_returns_service_payload(self, handle_github_app_webhook) -> None:
        payload = b'{"action":"opened"}'
        signature = (
            "sha256="
            + hmac.new(
                b"webhook-secret",
                payload,
                hashlib.sha256,
            ).hexdigest()
        )
        handle_github_app_webhook.return_value = type(
            "Result",
            (),
            {
                "event": "pull_request",
                "action": "opened",
                "handled": True,
                "automatic_analysis_triggered": True,
                "check_run_id": 7,
                "report_id": 17,
                "report_url": "https://deploywhisper.example.com/reports/17",
                "note": "ok",
            },
        )()

        response = self.client.post(
            "/api/v1/github/app/webhook",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
            content=payload,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["data"]["automatic_analysis_triggered"])
        self.assertEqual(body["data"]["check_run_id"], 7)
        self.assertEqual(body["data"]["report_id"], 17)

    @patch("api.routes.github_app.handle_github_app_webhook")
    def test_webhook_acknowledges_project_scope_error(
        self, handle_github_app_webhook
    ) -> None:
        payload = b'{"action":"opened"}'
        signature = (
            "sha256="
            + hmac.new(
                b"webhook-secret",
                payload,
                hashlib.sha256,
            ).hexdigest()
        )
        handle_github_app_webhook.side_effect = GitHubAppProjectScopeError(
            "project_not_found",
            "Unknown project reference: project_key=missing.",
        )

        response = self.client.post(
            "/api/v1/github/app/webhook",
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
            content=payload,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["data"]["automatic_analysis_triggered"])
        self.assertTrue(body["data"]["handled"])
        self.assertIn("project_not_found", body["data"]["note"])
