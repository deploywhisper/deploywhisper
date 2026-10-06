"""Configured connector and OAuth credential boundary regressions."""

from __future__ import annotations
import logging
import os
import unittest
from unittest.mock import patch
from services import content_security as security
from logging_config import SafeFormatter


class ConnectorContentSecurityTests(unittest.TestCase):
    def test_configured_connector_values_are_screened_without_labels(self):
        for name in (
            "GH_TOKEN",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "KUBERNETES_TOKEN",
            "DEPLOYWHISPER_GITHUB_APP_CLIENT_SECRET",
            "DEPLOYWHISPER_SHARE_TOKEN",
            "TF_TOKEN_example_com",
        ):
            with (
                self.subTest(name=name),
                patch.dict(os.environ, {name: "opaque-connector-credential-123"}),
            ):
                self.assertNotIn(
                    "opaque-connector-credential-123",
                    security.redact_text("Rejected opaque-connector-credential-123"),
                )
                self.assertNotIn(
                    "opaque-connector-credential-123",
                    str(
                        security.redact_value(
                            {"message": "Rejected opaque-connector-credential-123"}
                        )
                    ),
                )

    def test_oauth_queries_are_screened_in_access_logs_and_sibling_context(self):
        for key in ("code", "state", "%63ode", "session", "sig"):
            uri = f"/api/v1/github/app/oauth/callback?{key}=opaque-oauth-credential&project_id=42"
            with self.subTest(key=key):
                record = logging.makeLogRecord(
                    {
                        "msg": "GET %s HTTP/1.1",
                        "args": (uri,),
                        "levelno": logging.INFO,
                        "levelname": "INFO",
                        "name": "uvicorn.access",
                    }
                )
                output = SafeFormatter("%(message)s").format(record)
                self.assertNotIn("opaque-oauth-credential", output)
                self.assertIn("project_id=42", output)
                values = security.sensitive_artifact_values(uri.encode())
                self.assertNotIn(
                    "opaque-oauth-credential",
                    security.redact_value(
                        {"echo": "opaque-oauth-credential"}, sensitive_values=values
                    )["echo"],
                )

    def test_configured_connector_values_protect_public_errors_and_model_calls(self):
        import json
        from api.errors import build_error
        from llm.providers import (
            generate_completion_with_settings,
            NarrativeProviderError,
        )

        secret = "opaque-connector-prompt-credential"
        seen = []

        def completion(**kwargs):
            seen.extend(kwargs["messages"])
            return '{"ok":true}'

        with patch.dict(os.environ, {"GH_TOKEN": secret}):
            error = build_error("connector_error", f"Rejected {secret}")
            self.assertNotIn(secret, json.dumps(error))
            output = generate_completion_with_settings(
                [
                    {
                        "role": "user",
                        "content": json.dumps({"context": f"echo {secret}"}),
                    }
                ],
                provider="openai",
                model="gpt-test",
                api_base="https://example.invalid/v1",
                api_key="synthetic-provider-key",
                completion_client=completion,
            )
            self.assertEqual(output, '{"ok":true}')
            self.assertNotIn(secret, json.dumps(seen))
            with self.assertRaises(NarrativeProviderError):
                generate_completion_with_settings(
                    [{"role": "user", "content": "{}"}],
                    provider="openai",
                    model="gpt-test",
                    api_base="https://example.invalid/v1",
                    api_key="synthetic-provider-key",
                    completion_client=lambda **kwargs: secret,
                )

    def test_secure_reference_paths_and_protocol_enums_keep_their_meaning(self):
        with patch.dict(
            os.environ,
            {"GH_TOKEN": "high", "KUBECONFIG": "/run/credentials/kubeconfig"},
        ):
            result = security.redact_value(
                {
                    "severity": "high",
                    "metadata": {"note": "high"},
                    "ref": "/run/credentials/kubeconfig",
                }
            )
        self.assertEqual(result["severity"], "high")
        self.assertEqual(result["metadata"]["note"], security.REDACTED)
        self.assertEqual(result["ref"], "/run/credentials/kubeconfig")

    def test_reference_screen_handles_nested_encoding(self):
        with patch.dict(os.environ, {"GH_TOKEN": "opaque-reference-credential"}):
            self.assertEqual(
                security.redact_reference(
                    "context:https://user:password@example.invalid"
                ),
                security.REDACTED,
            )
            self.assertEqual(
                security.redact_reference(
                    "https://example.invalid/%256Fpaque-reference-credential"
                ),
                security.REDACTED,
            )
            self.assertEqual(
                security.redact_reference("/run/credentials/kubeconfig"),
                "/run/credentials/kubeconfig",
            )
