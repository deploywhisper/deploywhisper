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
    import_topology_source,
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

    def test_import_topology_source_reports_diff_and_discards_raw_source_fields(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "topology-import.json"
        source_path.write_text(
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
                    ],
                    "raw_source": "do-not-persist-this",
                }
            ),
            encoding="utf-8",
        )

        first_result = import_topology_source(
            "custom",
            str(source_path),
            project_key="payments",
        )

        self.assertEqual(first_result.source_type, "custom")
        self.assertEqual(sorted(first_result.diff.added_services), ["api", "worker"])
        self.assertEqual(first_result.diff.removed_services, [])
        self.assertEqual(first_result.diff.changed_services, [])
        self.assertEqual(len(first_result.accepted_resources), 2)
        self.assertEqual(first_result.partially_parsed_resources, [])
        self.assertEqual(first_result.unsupported_resources, [])

        source_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API v2",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                        }
                    ],
                    "raw_source": "still-do-not-persist-this",
                }
            ),
            encoding="utf-8",
        )

        second_result = import_topology_source(
            "custom",
            str(source_path),
            project_key="payments",
        )
        topology, _ = load_topology(project_key="payments")

        self.assertEqual(second_result.diff.added_services, [])
        self.assertEqual(second_result.diff.removed_services, ["worker"])
        self.assertEqual(second_result.diff.changed_services, ["api"])
        assert topology is not None
        self.assertNotIn("raw_source", topology)
        with SessionLocal() as session:
            latest = (
                session.query(tables_module.TopologyVersion)
                .filter(tables_module.TopologyVersion.project_id == project.id)
                .order_by(tables_module.TopologyVersion.id.desc())
                .first()
            )
        assert latest is not None
        self.assertNotIn("do-not-persist-this", latest.payload_json)
        self.assertNotIn("still-do-not-persist-this", latest.payload_json)

    def test_import_topology_source_records_partial_and_skipped_resources(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "partial-topology.json"
        source_path.write_text(
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
                            "id": "api",
                            "label": "Duplicate API",
                            "resource_keys": ["Deployment/api-duplicate"],
                            "downstream": [],
                        },
                        {
                            "label": "Missing ID",
                            "resource_keys": ["Deployment/missing-id"],
                            "downstream": [],
                        },
                        "not-a-service",
                    ]
                }
            ),
            encoding="utf-8",
        )

        result = import_topology_source(
            "custom",
            str(source_path),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertEqual(
            [item.resource_ref for item in result.accepted_resources],
            ["Deployment/api"],
        )
        self.assertEqual(len(result.skipped_resources), 1)
        self.assertEqual(len(result.partially_parsed_resources), 3)
        self.assertIn(
            "worker",
            " ".join(item.message for item in result.partially_parsed_resources),
        )
        assert topology is not None
        self.assertEqual(topology["services"][0]["downstream"], [])
        self.assertIn("partially parsed", warning)

    def test_import_topology_source_warns_without_failing_for_unimplemented_source(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        result = import_topology_source(
            "terraform",
            "s3://example-bucket/topology.tfstate",
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertEqual(result.diff.added_services, [])
        self.assertEqual(result.accepted_resources, [])
        self.assertEqual(len(result.unsupported_resources), 1)
        self.assertIn("terraform", result.warnings[0].lower())
        self.assertIsNone(topology)
        self.assertIn("not configured", warning)

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

    def test_import_topology_source_keeps_legacy_default_project_mirror_compatible(
        self,
    ) -> None:
        source_path = Path(self.tempdir.name) / "default-topology-import.json"
        source_path.write_text(
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
            encoding="utf-8",
        )
        legacy_path = Path(self.tempdir.name) / "legacy-topology.json"
        fake_settings = SimpleNamespace(topology_path=str(legacy_path))

        with patch("services.topology_service.settings", fake_settings):
            result = import_topology_source("custom", str(source_path))
            topology, warning = load_topology()

        self.assertTrue(result.applied)
        self.assertTrue(legacy_path.exists())
        mirrored_payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        self.assertIn("services", mirrored_payload)
        self.assertNotIn("metadata", mirrored_payload)
        self.assertIsNotNone(topology)
        self.assertIsNone(warning)

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
