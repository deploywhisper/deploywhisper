"""Tests for project-scoped context API routes."""

from __future__ import annotations

import json
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
        self.assertIn("drift", get_response.json()["data"]["topology"])

    def test_save_project_topology_denies_role_without_topology_capability(
        self,
    ) -> None:
        response = self.client.post(
            "/api/v1/context/topology",
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
            json={
                "project_key": self.project.project_key,
                "topology": {"services": []},
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn(self.project.project_key, payload["error"]["message"])

    def test_get_project_topology_allows_topology_read_capability(self) -> None:
        response = self.client.get(
            "/api/v1/context/topology",
            params={"project_key": self.project.project_key},
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["data"]["project"]["project_key"],
            self.project.project_key,
        )

    def test_get_project_topology_masks_missing_id_for_scoped_actor(self) -> None:
        response = self.client.get(
            "/api/v1/context/topology",
            params={"project_id": 999},
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")

    def test_get_project_topology_masks_conflicting_reference_for_scoped_actor(
        self,
    ) -> None:
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        response = self.client.get(
            "/api/v1/context/topology",
            params={
                "project_key": self.project.project_key,
                "project_id": forbidden.id,
            },
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")

    def test_save_project_topology_rejects_invalid_relationships(self) -> None:
        response = self.client.post(
            "/api/v1/context/topology",
            json={
                "project_key": self.project.project_key,
                "topology": {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": ["worker"],
                        }
                    ]
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"], "invalid_topology_definition"
        )
        self.assertIn(
            "missing downstream services", response.json()["error"]["message"]
        )

    def test_fetch_project_topology_includes_drift_resource_lists(self) -> None:
        topology_path = Path(self.tempdir.name) / "drift-topology.json"
        topology_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                        },
                        {
                            "id": "billing",
                            "label": "Billing",
                            "resource_keys": ["Deployment/billing"],
                            "downstream": [],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        import services.topology_service as topology_service_module

        topology_service_module.import_topology_source(
            "custom",
            str(topology_path),
            project_key=self.project.project_key,
        )
        topology_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": ["worker"],
                        },
                        {
                            "id": "worker",
                            "label": "Worker",
                            "resource_keys": ["Deployment/worker"],
                            "downstream": [],
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        topology_service_module.check_topology_drift(
            project_key=self.project.project_key,
            force=True,
        )

        response = self.client.get(
            "/api/v1/context/topology",
            params={"project_key": self.project.project_key},
        )

        self.assertEqual(response.status_code, 200)
        drift = response.json()["data"]["topology"]["drift"]
        self.assertEqual(drift["added_resources"], ["Deployment/worker"])
        self.assertEqual(drift["removed_resources"], ["Deployment/billing"])
        self.assertEqual(drift["modified_resources"], ["Deployment/api"])
