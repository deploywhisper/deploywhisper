"""Tests for topology loading and warning behavior."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
from models.database import SessionLocal
from services.topology_service import (
    get_topology_status,
    load_topology,
    save_topology_definition,
)


class TopologyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "topology.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_load_topology_warns_when_missing(self) -> None:
        fake_settings = SimpleNamespace(topology_path="missing-topology.json")
        with patch("services.topology_service.settings", fake_settings):
            topology, warning = load_topology()
        self.assertIsNone(topology)
        self.assertIn("not configured", warning)

    def test_save_topology_definition_scopes_payload_to_project(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        fake_settings = SimpleNamespace(
            topology_path=str(Path(self.tempdir.name) / "missing-topology.json")
        )

        with patch("services.topology_service.settings", fake_settings):
            save_topology_definition(
                json.dumps(
                    {
                        "services": [
                            {
                                "id": "api",
                                "label": "API",
                                "resource_keys": ["Deployment/api"],
                                "downstream": [],
                            }
                        ]
                    }
                ),
                project_key="payments",
            )

            scoped_topology, _ = load_topology(project_key="payments")
            default_topology, default_warning = load_topology()

        self.assertIsNotNone(scoped_topology)
        assert scoped_topology is not None
        self.assertEqual(scoped_topology["services"][0]["id"], "api")
        self.assertIsNone(default_topology)
        self.assertIn("not configured", default_warning)

    def test_load_topology_imports_legacy_file_into_default_project(self) -> None:
        legacy_path = Path(self.tempdir.name) / "legacy-topology.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "updated_at": "2026-04-16T00:00:00Z",
                    "services": [
                        {
                            "id": "legacy-api",
                            "label": "Legacy API",
                            "resource_keys": ["Deployment/legacy-api"],
                            "downstream": [],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        fake_settings = SimpleNamespace(topology_path=str(legacy_path))

        with patch("services.topology_service.settings", fake_settings):
            topology, warning = load_topology()

        self.assertIsNotNone(topology)
        self.assertIsNone(warning)
        assert topology is not None
        self.assertEqual(topology["services"][0]["id"], "legacy-api")

    def test_get_topology_status_returns_validation_error_for_malformed_stored_payload(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        with SessionLocal() as session:
            session.add(
                tables_module.TopologyVersion(
                    project_id=project.id,
                    source_type="manual",
                    payload_json="{bad json",
                )
            )
            session.commit()

        status = get_topology_status(project_id=project.id)

        self.assertTrue(status.exists)
        self.assertIn(
            "stored topology JSON is invalid", " ".join(status.blocking_errors)
        )

    def test_save_topology_definition_aborts_default_project_write_when_legacy_mirror_fails(
        self,
    ) -> None:
        fake_settings = SimpleNamespace(
            topology_path=str(Path(self.tempdir.name) / "legacy-topology.json")
        )
        with patch("services.topology_service.settings", fake_settings):
            with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
                with self.assertRaises(ValueError):
                    save_topology_definition(
                        json.dumps(
                            {
                                "services": [
                                    {
                                        "id": "api",
                                        "label": "API",
                                        "resource_keys": ["Deployment/api"],
                                        "downstream": [],
                                    }
                                ]
                            }
                        )
                    )

        with SessionLocal() as session:
            rows = session.query(tables_module.TopologyVersion).all()
        self.assertEqual(rows, [])

    def test_load_topology_returns_payload_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service_topology.json"
            path.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-04-16T00:00:00Z",
                        "services": [
                            {
                                "id": "api",
                                "label": "API",
                                "resource_keys": ["Deployment/api"],
                                "downstream": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                topology, warning = load_topology()
        self.assertIsNotNone(topology)
        self.assertIsNone(warning)

    def test_load_topology_warns_when_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service_topology.json"
            path.write_text(
                json.dumps(
                    {
                        "updated_at": "2025-01-01T00:00:00Z",
                        "services": [
                            {
                                "id": "api",
                                "label": "API",
                                "resource_keys": ["Deployment/api"],
                                "downstream": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                topology, warning = load_topology()
        self.assertIsNotNone(topology)
        self.assertIn("last updated more than", warning)

    def test_save_topology_definition_persists_active_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "service_topology.json"
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                status = save_topology_definition(
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
                                    "resource_keys": ["task-background-jobs"],
                                    "downstream": [],
                                },
                            ]
                        }
                    )
                )
                topology, warning = load_topology()
                self.assertTrue(path.exists())
                self.assertEqual(status.service_count, 2)
                self.assertEqual(status.dependency_count, 1)
                self.assertIsNotNone(status.updated_at)
                self.assertIsNotNone(topology)
                self.assertIsNone(warning)

    def test_get_topology_status_surfaces_structural_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service_topology.json"
            path.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-04-16T00:00:00Z",
                        "services": [
                            {
                                "id": "api",
                                "label": "API",
                                "resource_keys": ["Deployment/api"],
                                "downstream": ["worker", "cache"],
                            },
                            {
                                "id": "worker",
                                "label": "Worker",
                                "resource_keys": ["task-background-jobs"],
                                "downstream": ["api"],
                            },
                            {
                                "id": "frontend",
                                "label": "Frontend",
                                "resource_keys": ["Deployment/frontend"],
                                "downstream": [],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                status = get_topology_status()
        combined_errors = " ".join(status.blocking_errors)
        combined_warnings = " ".join(status.warnings)
        self.assertIn("missing downstream services", combined_errors)
        self.assertIn("circular dependency detected", combined_errors)
        self.assertIn("orphaned services", combined_warnings)

    def test_save_topology_definition_rejects_invalid_structure_and_keeps_previous_active_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "service_topology.json"
            fake_settings = SimpleNamespace(topology_path=str(path))
            with patch("services.topology_service.settings", fake_settings):
                saved = save_topology_definition(
                    json.dumps(
                        {
                            "services": [
                                {
                                    "id": "api",
                                    "label": "API",
                                    "resource_keys": ["Deployment/api"],
                                    "downstream": [],
                                }
                            ]
                        }
                    )
                )
                original_updated_at = saved.updated_at

                with self.assertRaises(ValueError) as exc_info:
                    save_topology_definition(
                        json.dumps(
                            {
                                "services": [
                                    {
                                        "id": "api",
                                        "label": "API",
                                        "resource_keys": ["Deployment/api"],
                                        "downstream": ["worker"],
                                    }
                                ]
                            }
                        )
                    )

                active_status = get_topology_status()
        self.assertIn("missing downstream services", str(exc_info.exception))
        self.assertEqual(active_status.service_count, 1)
        self.assertEqual(active_status.updated_at, original_updated_at)
