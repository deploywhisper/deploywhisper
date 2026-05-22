"""Tests for incident ingestion management API routes."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import api.routes.incidents as incidents_route_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.incident_import_service as incident_import_service_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module
from app import create_app
from fastapi.testclient import TestClient


class IncidentsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "incidents-api.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(incident_service_module)
        reload(incident_import_service_module)
        reload(incidents_route_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_get_incident_ingestion_status_returns_index_summary(self) -> None:
        incident_service_module.ingest_incident_document(
            "checkout.md",
            "# Checkout incident\nDate: 2026-05-20\nSeverity: high\nRedaction status: redacted\n",
            project_id=self.project.id,
        )

        response = self.client.get(
            "/api/v1/incidents/ingestion",
            params={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["project_id"], self.project.id)
        self.assertEqual(payload["data"]["indexed_count"], 1)
        self.assertEqual(payload["data"]["redaction_status"], "redacted")
        self.assertEqual(payload["data"]["freshness_status"], "current")
        self.assertEqual(payload["data"]["sources"][0]["import_source"], "checkout.md")
        self.assertEqual(payload["meta"]["count"], 1)

    def test_reindex_incidents_replaces_stale_entries_and_reports_failures(
        self,
    ) -> None:
        incident_service_module.ingest_incident_document(
            "checkout.json",
            "# Old checkout incident\nSeverity: low\nRedaction status: none\n",
            project_id=self.project.id,
        )

        response = self.client.post(
            "/api/v1/incidents/reindex",
            json={
                "project_key": "payments",
                "remove_missing_sources": False,
                "files": [
                    {
                        "source_file": "checkout.json",
                        "content": json.dumps(
                            {
                                "title": "Updated checkout incident",
                                "severity": "high",
                                "incident_date": "2026-05-20",
                                "root_cause": "Ingress drift.",
                                "trigger_change": "Security group update.",
                                "affected_services": ["checkout-api"],
                                "rollback_path": "Restore previous security group.",
                                "prevention_notes": ["Review ingress diffs."],
                                "source": {
                                    "system": "manual",
                                    "reference": "INC-900",
                                },
                                "redaction": {
                                    "status": "redacted",
                                    "contains_sensitive_data": False,
                                },
                            }
                        ),
                    },
                    {
                        "source_file": "broken.json",
                        "content": "{}",
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 422)
        failure_payload = response.json()
        self.assertEqual(
            failure_payload["error"]["code"],
            "incident_reindex_validation_failed",
        )
        failure = failure_payload["error"]["details"]["failures"][0]
        self.assertEqual(failure["source_file"], "broken.json")
        self.assertIn("Add", failure["correction_path"])

        retry_response = self.client.post(
            "/api/v1/incidents/reindex",
            json={
                "project_key": "payments",
                "remove_missing_sources": False,
                "files": [
                    {
                        "source_file": "checkout.json",
                        "content": json.dumps(
                            {
                                "title": "Updated checkout incident",
                                "severity": "high",
                                "incident_date": "2026-05-20",
                                "root_cause": "Ingress drift.",
                                "trigger_change": "Security group update.",
                                "affected_services": ["checkout-api"],
                                "rollback_path": "Restore previous security group.",
                                "prevention_notes": ["Review ingress diffs."],
                                "source": {
                                    "system": "manual",
                                    "reference": "INC-900",
                                },
                                "redaction": {
                                    "status": "redacted",
                                    "contains_sensitive_data": False,
                                },
                            }
                        ),
                    }
                ],
            },
        )

        self.assertEqual(retry_response.status_code, 200)
        payload = retry_response.json()
        self.assertEqual(payload["data"]["indexed_count"], 1)
        self.assertEqual(payload["data"]["replaced_count"], 1)
        self.assertEqual(payload["data"]["status"]["indexed_count"], 1)
        sources_by_file = {
            source["import_source"]: source
            for source in payload["data"]["status"]["sources"]
        }
        self.assertEqual(
            sources_by_file["checkout.json"]["title"],
            "Updated checkout incident",
        )
        self.assertIn("broken.json", sources_by_file)
        self.assertGreater(sources_by_file["broken.json"]["rejected_count"], 0)
        self.assertEqual(payload["meta"]["count"], len(sources_by_file))

    def test_reindex_masks_workspace_reference_for_restricted_project_scope(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/incidents/reindex",
            headers={
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            json={
                "project_key": "payments",
                "workspace_id": 999,
                "files": [
                    {
                        "source_file": "checkout.json",
                        "content": json.dumps(
                            {
                                "title": "Updated checkout incident",
                                "severity": "high",
                                "incident_date": "2026-05-20",
                                "root_cause": "Ingress drift.",
                                "trigger_change": "Security group update.",
                                "affected_services": ["checkout-api"],
                                "rollback_path": "Restore previous security group.",
                                "prevention_notes": ["Review ingress diffs."],
                                "source": {
                                    "system": "manual",
                                    "reference": "INC-900",
                                },
                                "redaction": {
                                    "status": "redacted",
                                    "contains_sensitive_data": False,
                                },
                            }
                        ),
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")
