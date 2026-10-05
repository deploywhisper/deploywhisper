"""Regression coverage for sensitive API error content."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import Request
from fastapi.exceptions import RequestValidationError

from api.errors import build_error, internal_error_handler, validation_error_handler


class ErrorSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_errors_omit_raw_input_and_context(self) -> None:
        artifact = "resource confidential_raw_artifact { internal_network = true }"
        request = Request({"type": "http", "path": "/api/v1/analyses", "headers": []})
        error = RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "artifact"),
                    "msg": "Value error",
                    "input": artifact,
                    "ctx": {"error": artifact},
                    "url": "https://errors.example.invalid/value_error",
                }
            ]
        )

        response = await validation_error_handler(request, error)

        issue = json.loads(response.body)["error"]["details"]["issues"][0]
        self.assertEqual(issue["loc"], ["body", "artifact"])
        self.assertEqual(issue["type"], "value_error")
        self.assertNotIn("input", issue)
        self.assertNotIn("ctx", issue)
        self.assertNotIn("url", issue)
        self.assertNotIn(artifact, response.body.decode())

    def test_error_envelope_redacts_message_and_nested_details(self) -> None:
        secret = "sk-proj-" + "syntheticcredential" * 3
        details = {
            "api_key": secret,
            "issues": [{"message": f"Authorization: Bearer {secret}"}],
        }

        result = build_error(
            "provider_error", f"Provider rejected api_key={secret}", details
        )

        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result["error"]["code"], "provider_error")
        self.assertEqual(details["api_key"], secret)

    async def test_internal_errors_log_only_event_and_exception_class(self) -> None:
        artifact = "confidential_raw_artifact_and_prompt_sql_parameter"
        request = Request({"type": "http", "path": "/api/v1/analyses"})
        with patch("api.errors.logger") as logger:
            response = await internal_error_handler(request, RuntimeError(artifact))

        logger.exception.assert_not_called()
        logger.error.assert_called_once_with(
            "Unhandled API exception (%s)", "RuntimeError"
        )
        self.assertNotIn(artifact, response.body.decode())
        self.assertEqual(response.status_code, 500)
