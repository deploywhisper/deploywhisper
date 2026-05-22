"""Rendered smoke tests for the incident ingestion management page."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import app as app_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module
import ui.project_authorization as project_authorization_module
import ui.routes.dashboard as dashboard_module
import ui.routes.incidents as incidents_route_module
import ui.theme as theme_module
from fastapi.testclient import TestClient


class IncidentsPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "incidents-ui.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(incident_service_module)
        reload(project_authorization_module)
        reload(theme_module)
        reload(incidents_route_module)
        reload(dashboard_module)
        reload(app_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.set_active_project(self.project.id)
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEPLOYWHISPER_PROJECT_ROLE", None)
        os.environ.pop("DEPLOYWHISPER_PROJECT_KEYS", None)
        self.tempdir.cleanup()

    def test_incidents_page_renders_ingestion_status(self) -> None:
        incident_service_module.ingest_incident_document(
            "checkout.md",
            "# Checkout incident\nSeverity: high\nRedaction status: redacted\n",
            project_id=self.project.id,
        )

        response = self.client.get("/incidents")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Incident ingestion management", response.text)
        self.assertIn("Payments", response.text)
        self.assertIn("Indexed incidents", response.text)
        self.assertIn("Rejected records", response.text)
        self.assertIn("checkout.md", response.text)
        self.assertIn("redacted", response.text)
        self.assertIn("current", response.text)

    def test_incidents_page_denies_reviewer_without_incident_manage(self) -> None:
        incident_service_module.ingest_incident_document(
            "checkout.md",
            "# Checkout incident\nSeverity: high\nRedaction status: redacted\n",
            project_id=self.project.id,
        )
        os.environ["DEPLOYWHISPER_PROJECT_ROLE"] = "reviewer"
        os.environ["DEPLOYWHISPER_PROJECT_KEYS"] = "payments"

        response = self.client.get("/incidents")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Incident ingestion management", response.text)
        self.assertIn("Project authorization unavailable", response.text)
        self.assertIn("Caller role is not authorized", response.text)
        self.assertNotIn("checkout.md", response.text)
