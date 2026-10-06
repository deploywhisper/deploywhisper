"""Credential echoes must not escape connector permission/scope boundaries."""

from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.errors import ApiError, api_error_handler
from api.routes import incidents, scanner_imports
from models.tables import Base
from services import project_service


class ConnectorScopeSecurityTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        tempdir = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.engine = create_engine(f"sqlite:///{Path(tempdir) / 'scope.db'}")
        self.stack.callback(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        for module in (
            "services.project_service",
            "services.incident_import_service",
            "services.scanner_import_service",
        ):
            self.stack.enter_context(patch(f"{module}.SessionLocal", self.sessions))
        self.project = project_service.create_project(
            project_key="payments", display_name="Payments"
        )
        app = FastAPI()
        app.add_exception_handler(ApiError, api_error_handler)
        app.include_router(incidents.router)
        app.include_router(scanner_imports.router)
        self.client = self.stack.enter_context(TestClient(app))
        self.secret = "Review_Password_ABC"
        self.normalized = project_service.normalize_project_key(self.secret)

    def _payload(self, route, **scope):
        document = {"password": self.secret}
        if route == "sarif":
            document.update(
                {
                    "version": "2.1.0",
                    "runs": [{"tool": {"driver": {"name": "Semgrep"}}, "results": []}],
                }
            )
        elif route == "semgrep":
            document["results"] = []
        content = json.dumps(document)
        if route == "incidents":
            return {
                "files": [{"source_file": "incident.json", "content": content}],
                **scope,
            }
        return {"source_file": "scanner.json", "content": content, **scope}

    def _path(self, route):
        return (
            "/api/v1/incidents/reindex"
            if route == "incidents"
            else f"/api/v1/scanner-imports/{route}"
        )

    def test_permission_precheck_screens_normalized_project_credential_echo(self):
        for route in ("incidents", "sarif", "semgrep"):
            with self.subTest(route=route):
                response = self.client.post(
                    self._path(route),
                    json=self._payload(
                        route, project_id=self.project.id, project_key=self.secret
                    ),
                )
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["error"]["code"], "project_not_found")
                self.assertNotIn(self.secret, response.text)
                self.assertNotIn(self.normalized, response.text)

    def test_workspace_resolution_screens_credential_echo(self):
        for route in ("incidents", "sarif", "semgrep"):
            with self.subTest(route=route):
                response = self.client.post(
                    self._path(route),
                    json=self._payload(
                        route, project_id=self.project.id, workspace_key=self.secret
                    ),
                )
                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response.json()["error"]["code"], "workspace_not_found"
                )
                self.assertNotIn(self.normalized, response.text)

    def test_configured_credentials_are_screened_without_uploaded_secret(self):
        with patch.dict(os.environ, {"GH_TOKEN": self.secret}):
            for route in ("incidents", "sarif", "semgrep"):
                with self.subTest(route=route):
                    payload = self._payload(
                        route, project_id=self.project.id, project_key=self.secret
                    )
                    if route == "incidents":
                        payload["files"][0]["content"] = "{}"
                    else:
                        payload["content"] = "{}"
                    response = self.client.post(self._path(route), json=payload)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(
                        response.json()["error"]["code"], "project_not_found"
                    )
                    self.assertNotIn(self.secret, response.text)
                    self.assertNotIn(self.normalized, response.text)

    def test_denied_callers_never_enter_import_or_parse_sensitive_content(self):
        imports = {
            "incidents": (incidents, "reindex_incident_files"),
            "sarif": (scanner_imports, "import_sarif_file"),
            "semgrep": (scanner_imports, "import_semgrep_json_file"),
        }
        for route, (module, name) in imports.items():
            for headers in (
                {"X-DeployWhisper-Project-Role": "viewer"},
                {
                    "X-DeployWhisper-Project-Role": "admin",
                    "X-DeployWhisper-Project-Keys": "other",
                },
            ):
                with (
                    self.subTest(route=route, headers=headers),
                    patch.object(module, name) as importer,
                    patch.object(module, "sensitive_submission_values") as collector,
                ):
                    response = self.client.post(
                        self._path(route),
                        headers=headers,
                        json=self._payload(
                            route, project_id=self.project.id, project_key=self.secret
                        ),
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertNotIn(self.normalized, response.text)
                    importer.assert_not_called()
                    collector.assert_not_called()

    def test_restricted_scope_reference_errors_remain_forbidden(self):
        for route in ("incidents", "sarif", "semgrep"):
            with self.subTest(route=route):
                response = self.client.post(
                    self._path(route),
                    headers={
                        "X-DeployWhisper-Project-Role": "admin",
                        "X-DeployWhisper-Project-Keys": "payments",
                    },
                    json=self._payload(
                        route, project_id=999999, project_key="payments"
                    ),
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["error"]["code"], "project_scope_forbidden"
                )
