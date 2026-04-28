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
