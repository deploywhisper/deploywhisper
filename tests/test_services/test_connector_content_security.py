"""Configured connector and OAuth credential boundary regressions."""

from __future__ import annotations
import logging
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import quote
from services import content_security as security
from logging_config import SafeFormatter


class ConnectorContentSecurityTests(unittest.TestCase):
    @staticmethod
    def encoded(value, rounds):
        for _ in range(rounds):
            value = quote(value, safe="")
        return value

    def test_repeated_encoding_screens_named_password_echoes_in_nested_values(self):
        secret = "opaque narrative/password!:credential"
        encoded = self.encoded(secret, 5)
        for echo in (encoded, encoded.lower(), encoded.replace("2F", "2f")):
            with self.subTest(echo=echo):
                result = security.redact_value(
                    {
                        "password": secret,
                        "nested": [{"message": f"Scanner returned {echo}"}],
                        "payload_json": json.dumps({"note": echo}),
                    }
                )
                self.assertEqual(result["nested"][0]["message"], security.REDACTED)
                self.assertEqual(
                    json.loads(result["payload_json"])["note"], security.REDACTED
                )
                self.assertEqual(security.redact_value(result), result)

    def test_repeated_encoding_screens_configured_and_direct_text_credentials(self):
        secret = "opaque configured/credential!"
        with patch.dict(os.environ, {"GH_TOKEN": secret}):
            encoded = self.encoded(secret, 5)
            self.assertEqual(
                security.redact_text(f"Incident contains {encoded}"), security.REDACTED
            )
            self.assertEqual(
                security.redact_value({"note": encoded})["note"], security.REDACTED
            )
        self.assertEqual(
            security.redact_text(self.encoded("password=opaque-password", 5)),
            security.REDACTED,
        )
        self.assertEqual(
            security.redact_text("Issue: password=opaque-password; retry"),
            "Issue: password=[REDACTED]; retry",
        )

    def test_encoded_prose_and_literal_percent_keep_exact_original_spelling(self):
        for value in (
            "Progress is 95% complete",
            "Run%20completed%2fnext",
            self.encoded("ordinary prose!", 5),
        ):
            with self.subTest(value=value):
                self.assertEqual(security.redact_text(value), value)
                self.assertEqual(
                    security.redact_value({"note": value}), {"note": value}
                )
        with patch.dict(os.environ, {"GH_TOKEN": "high"}):
            self.assertEqual(
                security.redact_value({"severity": "high", "note": "high"}),
                {"severity": "high", "note": security.REDACTED},
            )

    def test_unresolved_percent_encoding_at_bound_fails_closed(self):
        for rounds in (9, 20):
            value = self.encoded("ordinary prose!", rounds)
            with self.subTest(rounds=rounds):
                self.assertEqual(security.redact_reference(value), security.REDACTED)
                self.assertEqual(security.redact_text(value), security.REDACTED)
                self.assertEqual(
                    security.redact_value({"note": value})["note"], security.REDACTED
                )

    def test_encoded_filename_credentials_collect_plaintext_sibling_context(self):
        for filename in (
            "password%3D%27Opaque%2FValue%21%27.json",
            "https://user:Opaque%2FValue%21@example.invalid/incident.json",
            self.encoded("password='Opaque/Value!'", 5) + ".json",
        ):
            with self.subTest(filename=filename):
                values = security.sensitive_submission_values([(filename, None)])
                self.assertIn("Opaque/Value!", values)
                self.assertEqual(
                    security.redact_text("Opaque/Value!", sensitive_values=values),
                    security.REDACTED,
                )
        self.assertEqual(
            security.sensitive_submission_values([("ordinary%20incident.json", None)]),
            (),
        )

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

    def test_nested_query_encodings_protect_plaintext_sibling_echoes(self):
        for credential in (
            "s%2565cret",
            "%256Fpaque-query-credential",
            "%25256Fpaque-query-credential",
        ):
            expected = (
                "secret" if credential.startswith("s") else "opaque-query-credential"
            )
            with self.subTest(credential=credential):
                payload = {"url": f"/callback?code={credential}", "echo": expected}
                self.assertNotIn(expected, str(security.redact_value(payload)))
                values = security.sensitive_artifact_values(payload["url"].encode())
                self.assertIn(expected, values)

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

    def test_oauth_form_decoding_screens_siblings_and_preserves_literal_plus(self):
        for encoded in (
            "opaque+oauth+state",
            "opaque%2Boauth%2Bstate",
            "opaque%252Boauth%252Bstate",
        ):
            with self.subTest(encoded=encoded):
                url = f"/callback?state={encoded}&project_id=42"
                values = security.sensitive_artifact_values(url.encode())
                self.assertIn("opaque+oauth+state", values)
                self.assertIn("opaque oauth state", values)
                screened = security.redact_value(
                    {
                        "url": url,
                        "literal": "opaque+oauth+state",
                        "decoded": "opaque oauth state",
                    },
                    sensitive_values=values,
                )
                self.assertEqual(screened["literal"], security.REDACTED)
                self.assertEqual(screened["decoded"], security.REDACTED)
                self.assertIn("project_id=42", screened["url"])

    def test_scope_error_screen_covers_raw_lowercase_and_project_slug(self):
        secret = "Opaque Review/Value!"
        message = f"Unknown project_key=opaque-review-value; lowercase=opaque review/value!; raw={secret}"
        screened = security.redact_scope_error_message(message, (secret,))
        self.assertNotIn(secret, screened)
        self.assertNotIn(secret.lower(), screened)
        self.assertNotIn("opaque-review-value", screened)
        self.assertIn("Unknown project_key=", screened)

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

    def test_scope_error_screen_normalizes_configured_credentials_without_upload(self):
        with patch.dict(os.environ, {"GH_TOKEN": "Configured_Secret_ABC"}):
            message = "Unknown project reference: project_key=configured-secret-abc."
            screened = security.redact_scope_error_message(message, ())
        self.assertEqual(screened, "Unknown project reference: project_key=[REDACTED].")
