"""Tests for topology loading and warning behavior."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from importlib import reload
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
import services.settings_service as settings_service_module
from models.database import SessionLocal
from services.topology_service import (
    check_topology_drift,
    get_topology_status,
    import_topology_source,
    load_topology,
    run_due_topology_drift_checks,
    save_topology_definition,
)


def _fresh_topology_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class TopologyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "topology.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(settings_service_module)
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

    def test_save_topology_definition_preserves_service_ownership(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        save_topology_definition(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                            "owner": "payments-team",
                            "owners": ["sre", "security"],
                        }
                    ]
                }
            ),
            project_key="payments",
        )

        topology, warning = load_topology(project_key="payments")

        self.assertIsNone(warning)
        assert topology is not None
        self.assertEqual(topology["services"][0]["owner"], "payments-team")
        self.assertEqual(topology["services"][0]["owners"], ["sre", "security"])

    def test_save_topology_definition_drops_malformed_singular_owner(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        status = save_topology_definition(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                            "owner": {"team": "payments"},
                            "owners": ["sre", {"team": "security"}],
                        }
                    ]
                }
            ),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertTrue(status.warnings)
        self.assertIn("partially parsed", warning)
        assert topology is not None
        self.assertNotIn("owner", topology["services"][0])
        self.assertEqual(topology["services"][0]["owners"], ["sre"])

    def test_topology_imports_are_isolated_by_workspace(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        prod_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        staging_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        prod_path = Path(self.tempdir.name) / "prod-topology.json"
        staging_path = Path(self.tempdir.name) / "staging-topology.json"
        prod_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "prod-api",
                            "label": "Prod API",
                            "resource_keys": ["Deployment/prod-api"],
                            "downstream": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        staging_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "staging-api",
                            "label": "Staging API",
                            "resource_keys": ["Deployment/staging-api"],
                            "downstream": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        import_topology_source(
            "custom",
            str(prod_path),
            project_key="payments",
            workspace_id=prod_workspace.id,
        )
        import_topology_source(
            "custom",
            str(staging_path),
            project_key="payments",
            workspace_id=staging_workspace.id,
        )

        prod_topology, _ = load_topology(
            project_key="payments",
            workspace_id=prod_workspace.id,
        )
        staging_topology, _ = load_topology(
            project_key="payments",
            workspace_id=staging_workspace.id,
        )

        assert prod_topology is not None
        assert staging_topology is not None
        self.assertEqual(prod_topology["services"][0]["id"], "prod-api")
        self.assertEqual(staging_topology["services"][0]["id"], "staging-api")

    def test_default_project_workspace_topology_does_not_update_legacy_file(
        self,
    ) -> None:
        default_project = project_service_module.ensure_default_project()
        workspace = project_service_module.create_workspace(
            project_key=default_project.project_key,
            workspace_key="prod",
            display_name="Production",
        )
        topology_path = Path(self.tempdir.name) / "legacy-topology.json"
        topology_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "legacy-api",
                            "label": "Legacy API",
                            "resource_keys": ["Deployment/legacy-api"],
                            "downstream": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        fake_settings = SimpleNamespace(topology_path=str(topology_path))

        with patch("services.topology_service.settings", fake_settings):
            save_topology_definition(
                json.dumps(
                    {
                        "services": [
                            {
                                "id": "prod-api",
                                "label": "Prod API",
                                "resource_keys": ["Deployment/prod-api"],
                                "downstream": [],
                            }
                        ]
                    }
                ),
                project_id=default_project.id,
                workspace_id=workspace.id,
            )
            project_topology, _ = load_topology(project_id=default_project.id)
            workspace_topology, _ = load_topology(
                project_id=default_project.id,
                workspace_id=workspace.id,
            )

        assert project_topology is not None
        assert workspace_topology is not None
        self.assertEqual(project_topology["services"][0]["id"], "legacy-api")
        self.assertEqual(workspace_topology["services"][0]["id"], "prod-api")

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

    def test_import_topology_source_records_malformed_singular_owner(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "owner-topology.json"
        source_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                            "owner": {"team": "payments"},
                        }
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

        self.assertEqual(len(result.partially_parsed_resources), 1)
        self.assertIn(
            "Owner label was malformed",
            result.partially_parsed_resources[0].message,
        )
        self.assertIn("partially parsed", warning)
        assert topology is not None
        self.assertNotIn("owner", topology["services"][0])

    def test_import_topology_source_records_malformed_owner_entries(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "owner-list-topology.json"
        source_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["Deployment/api"],
                            "downstream": [],
                            "owners": ["sre", {"team": "security"}],
                        }
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

        self.assertEqual(len(result.partially_parsed_resources), 1)
        self.assertIn(
            "Owner labels were malformed",
            result.partially_parsed_resources[0].message,
        )
        self.assertIn("partially parsed", warning)
        assert topology is not None
        self.assertEqual(topology["services"][0]["owners"], ["sre"])

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

    def test_check_topology_drift_reports_added_removed_and_modified_resources(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "drift-topology.json"
        source_path.write_text(
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

        import_topology_source("custom", str(source_path), project_key="payments")

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
                    ]
                }
            ),
            encoding="utf-8",
        )

        drift = check_topology_drift(project_key="payments", force=True)
        status = get_topology_status(project_key="payments")

        self.assertTrue(drift.alert)
        self.assertGreater(drift.change_percent, 10.0)
        self.assertEqual(drift.added_resources, ["Deployment/worker"])
        self.assertEqual(drift.removed_resources, ["Deployment/billing"])
        self.assertEqual(drift.modified_resources, ["Deployment/api"])
        self.assertEqual(drift.status, "drifted")
        self.assertIsNotNone(status.drift)
        assert status.drift is not None
        self.assertEqual(status.drift.status, "drifted")

    def test_get_topology_status_runs_due_scheduled_drift_check_by_default(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "scheduled-drift-topology.json"
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

        import_topology_source("custom", str(source_path), project_key="payments")

        status = get_topology_status(project_key="payments")

        self.assertIsNotNone(status.drift)
        assert status.drift is not None
        self.assertEqual(status.drift.interval_hours, 24)
        self.assertEqual(status.drift.status, "up_to_date")
        self.assertFalse(status.drift.alert)
        self.assertIsNotNone(status.drift.checked_at)
        self.assertIsNotNone(status.drift.next_check_at)

    def test_check_topology_drift_marks_manual_topology_as_unavailable(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
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

        drift = check_topology_drift(project_key="payments", force=True)

        self.assertEqual(drift.status, "unavailable")
        self.assertFalse(drift.alert)
        self.assertIn("manual", " ".join(drift.warnings).lower())

    def test_run_due_topology_drift_checks_updates_projects_with_due_imports(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "scheduler-drift-topology.json"
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

        import_topology_source("custom", str(source_path), project_key="payments")
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
                    ]
                }
            ),
            encoding="utf-8",
        )

        with SessionLocal() as session:
            cached_drift = session.get(
                tables_module.AppSetting,
                f"topology_drift_status::{project.id}",
            )
            assert cached_drift is not None
            cached_payload = json.loads(cached_drift.value)
            cached_payload["checked_at"] = "2026-04-01T00:00:00Z"
            cached_payload["next_check_at"] = "2026-04-02T00:00:00Z"
            cached_drift.value = json.dumps(cached_payload)
            session.commit()

        run_due_topology_drift_checks()
        status = get_topology_status(project_key="payments")

        self.assertIsNotNone(status.drift)
        assert status.drift is not None
        self.assertEqual(status.drift.status, "drifted")
        self.assertEqual(status.drift.added_resources, ["Deployment/worker"])

    def test_load_topology_imports_legacy_file_into_default_project(self) -> None:
        legacy_path = Path(self.tempdir.name) / "legacy-topology.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "updated_at": _fresh_topology_timestamp(),
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
        self.assertEqual(topology["metadata"]["import"]["source_type"], "legacy-file")
        self.assertEqual(topology["metadata"]["import"]["source_ref"], str(legacy_path))

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
                        "updated_at": _fresh_topology_timestamp(),
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
                        "updated_at": _fresh_topology_timestamp(),
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
