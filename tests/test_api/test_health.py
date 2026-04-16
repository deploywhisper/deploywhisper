"""Smoke tests for the shared health endpoint."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app import create_app


class HealthEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_endpoint_returns_ok(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["data"]["status"], "ok")
        self.assertEqual(body["data"]["mode"], "foundation")

    def test_swagger_ui_is_exposed_under_versioned_api_namespace(self) -> None:
        response = self.client.get("/api/v1/docs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("swagger-ui", response.text)
        self.assertIn("/api/v1/openapi.json", response.text)

    def test_versioned_openapi_document_is_exposed(self) -> None:
        response = self.client.get("/api/v1/openapi.json")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("/api/v1/health", body["paths"])
        self.assertIn("/api/v1/analyses", body["paths"])


if __name__ == "__main__":
    unittest.main()
