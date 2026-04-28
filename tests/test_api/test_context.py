"""Tests for project-scoped context API routes."""

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


class ContextApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "context-api.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_save_project_topology_requires_valid_project_reference(self) -> None:
        response = self.client.post(
            "/api/v1/context/topology",
            json={
                "project_key": "missing",
                "topology": {"services": []},
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_save_and_fetch_project_topology(self) -> None:
        save_response = self.client.post(
            "/api/v1/context/topology",
            json={
                "project_key": self.project.project_key,
                "topology": {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                        }
                    ]
                },
            },
        )

        self.assertEqual(save_response.status_code, 200)
        saved_payload = save_response.json()
        self.assertEqual(saved_payload["data"]["project"]["project_key"], "payments")
        self.assertEqual(saved_payload["data"]["topology"]["service_count"], 1)

        get_response = self.client.get(
            "/api/v1/context/topology",
            params={"project_key": self.project.project_key},
        )

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(
            get_response.json()["data"]["topology"]["service_count"],
            1,
        )
