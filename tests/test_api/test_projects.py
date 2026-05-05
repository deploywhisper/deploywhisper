"""Tests for project/workspace API routes."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
from app import create_app
from fastapi.testclient import TestClient


class ProjectsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "projects-api.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_create_project_returns_structured_payload(self) -> None:
        response = self.client.post(
            "/api/v1/projects",
            json={
                "project_key": "payments-api",
                "display_name": "Payments API",
                "repository_url": "https://github.com/acme/payments-api",
                "default_branch": "main",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["project_key"], "payments-api")
        self.assertEqual(payload["data"]["display_name"], "Payments API")

    def test_list_projects_includes_default_project(self) -> None:
        response = self.client.get("/api/v1/projects")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["data"][0]["project_key"], "unassigned")

    def test_create_workspace_returns_structured_payload(self) -> None:
        project_response = self.client.post(
            "/api/v1/projects",
            json={
                "project_key": "payments-api",
                "display_name": "Payments API",
            },
        )
        self.assertEqual(project_response.status_code, 200)

        response = self.client.post(
            "/api/v1/projects/payments-api/workspaces",
            json={
                "workspace_key": "Production / US East",
                "display_name": "Production US East",
                "description": "Primary production environment",
                "environment": "prod",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["project_key"], "payments-api")
        self.assertEqual(payload["data"]["workspace_key"], "production-us-east")
        self.assertEqual(payload["data"]["display_name"], "Production US East")
        self.assertEqual(payload["data"]["environment"], "prod")

    def test_duplicate_workspace_key_returns_explicit_error_without_partial_record(
        self,
    ) -> None:
        project_response = self.client.post(
            "/api/v1/projects",
            json={
                "project_key": "platform",
                "display_name": "Platform",
            },
        )
        self.assertEqual(project_response.status_code, 200)
        first_response = self.client.post(
            "/api/v1/projects/platform/workspaces",
            json={
                "workspace_key": "prod",
                "display_name": "Production",
            },
        )
        self.assertEqual(first_response.status_code, 200)

        duplicate_response = self.client.post(
            "/api/v1/projects/platform/workspaces",
            json={
                "workspace_key": "prod",
                "display_name": "Production Duplicate",
            },
        )

        self.assertEqual(duplicate_response.status_code, 400)
        payload = duplicate_response.json()
        self.assertEqual(payload["error"]["code"], "invalid_workspace_request")
        self.assertIn("Workspace key already exists", payload["error"]["message"])

        list_response = self.client.get("/api/v1/projects/platform/workspaces")
        self.assertEqual(list_response.status_code, 200)
        workspaces = list_response.json()["data"]
        self.assertEqual(len(workspaces), 1)
        self.assertEqual(workspaces[0]["display_name"], "Production")

    def test_workspace_routes_return_not_found_for_unknown_project(self) -> None:
        list_response = self.client.get("/api/v1/projects/missing/workspaces")
        create_response = self.client.post(
            "/api/v1/projects/missing/workspaces",
            json={
                "workspace_key": "prod",
                "display_name": "Production",
            },
        )

        self.assertEqual(list_response.status_code, 404)
        self.assertEqual(create_response.status_code, 404)
        self.assertEqual(
            list_response.json()["error"]["code"],
            "project_not_found",
        )
        self.assertEqual(
            create_response.json()["error"]["code"],
            "project_not_found",
        )
