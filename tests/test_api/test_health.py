"""Smoke tests for the shared health endpoint."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import create_app


class HealthEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_endpoint_returns_ok(self) -> None:
        with patch(
            "api.routes.health.get_provider_health_snapshot",
            return_value=type(
                "Readiness",
                (),
                {
                    "ready": True,
                    "provider": "ollama",
                    "model": "ollama/llama3",
                    "local_mode": True,
                    "capabilities": type(
                        "Capabilities",
                        (),
                        {
                            "supports_structured_output": True,
                            "supports_remote_mcp": False,
                            "supports_local_mcp": False,
                            "supports_tool_approval": False,
                            "supports_local_only_mode": True,
                        },
                    )(),
                    "requires_api_key": False,
                    "has_api_key": False,
                    "message": "LLM provider connection validated for analysis.",
                    "source": "environment",
                },
            )(),
        ):
            response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["status"], "ok")
        self.assertEqual(body["data"]["core_status"], "ok")
        self.assertEqual(body["data"]["mode"], "foundation")
        self.assertEqual(body["data"]["llm"]["status"], "ok")
        self.assertEqual(body["data"]["llm"]["provider"], "ollama")
        self.assertTrue(body["data"]["llm"]["capabilities"]["supports_local_only_mode"])

    def test_health_endpoint_reports_llm_status_separately_from_core_health(
        self,
    ) -> None:
        with patch(
            "api.routes.health.get_provider_health_snapshot",
            return_value=type(
                "Readiness",
                (),
                {
                    "ready": False,
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "local_mode": False,
                    "capabilities": type(
                        "Capabilities",
                        (),
                        {
                            "supports_structured_output": True,
                            "supports_remote_mcp": False,
                            "supports_local_mcp": False,
                            "supports_tool_approval": False,
                            "supports_local_only_mode": False,
                        },
                    )(),
                    "requires_api_key": True,
                    "has_api_key": False,
                    "message": "openai is selected but no API key is available in environment variables. Analysis can continue with heuristic-only results.",
                    "source": "database",
                },
            )(),
        ):
            response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["status"], "ok")
        self.assertEqual(body["data"]["core_status"], "ok")
        self.assertEqual(body["data"]["llm"]["status"], "degraded")
        self.assertFalse(body["data"]["llm"]["ready"])
        self.assertTrue(body["data"]["llm"]["requires_api_key"])
        self.assertFalse(
            body["data"]["llm"]["capabilities"]["supports_local_only_mode"]
        )

    def test_swagger_ui_is_exposed_under_versioned_api_namespace(self) -> None:
        response = self.client.get("/api/v1/docs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("swagger-ui", response.text)
        self.assertIn("/api/v1/openapi.json", response.text)

    def test_versioned_openapi_document_is_exposed(self) -> None:
        response = self.client.get("/api/v1/openapi.json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["info"]["version"], "1.3.0")
        self.assertIn("/api/v1/health", body["paths"])
        self.assertIn("/api/v1/analyses", body["paths"])
        self.assertIn("/api/v1/stats/summary", body["paths"])
        self.assertIn("/api/v1/stats/verdict-distribution", body["paths"])


if __name__ == "__main__":
    unittest.main()
