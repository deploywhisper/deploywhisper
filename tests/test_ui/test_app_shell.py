"""Smoke test for the dashboard shell."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch
from importlib import reload

import app as app_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.report_service as report_service_module
import ui.routes.history as history_module
from fastapi.testclient import TestClient


class DashboardShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "ui.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(report_service_module)
        reload(history_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_root_page_contains_deploywhisper_shell_text(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DeployWhisper", response.text)
        self.assertIn("Upload deployment artifacts", response.text)
        self.assertIn("Deploy review", response.text)
        self.assertIn("Analysis snapshot", response.text)
        self.assertIn("Files scanned", response.text)
        self.assertNotIn("Foundation ready", response.text)

    def test_history_page_contains_back_to_dashboard_action(self) -> None:
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Back to dashboard", response.text)

    def test_dashboard_failure_does_not_return_api_error_envelope(self) -> None:
        client = TestClient(app_module.create_app(), raise_server_exceptions=False)
        with patch("app.build_dashboard", side_effect=RuntimeError("ui boom")):
            response = client.get("/")

        self.assertEqual(response.status_code, 500)
        self.assertNotEqual(response.headers.get("content-type"), "application/json")
        self.assertNotIn('"error"', response.text)


if __name__ == "__main__":
    unittest.main()
