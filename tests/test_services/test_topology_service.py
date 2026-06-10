"""Tests for topology loading and warning behavior."""

from __future__ import annotations

import json
import os
import subprocess
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
from analysis.blast_radius import compute_blast_radius
from models.database import SessionLocal
from parsers.base import UnifiedChange
from parsers.kubernetes_parser import parse_kubernetes
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


def _kubectl_live_state_side_effect(
    resources_by_name: dict[str, list[dict]],
):
    def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
        resource = args[args.index("get") + 1]
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "apiVersion": "v1",
                    "kind": "List",
                    "items": resources_by_name.get(resource, []),
                }
            ),
            stderr="",
        )

    return side_effect


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

    def test_import_topology_source_reads_kubernetes_live_state_relationships(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        live_state = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {
                        "name": "payments",
                        "resourceVersion": "10",
                        "managedFields": [{"manager": "kubectl"}],
                    },
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {
                        "name": "api",
                        "namespace": "payments",
                        "resourceVersion": "20",
                    },
                    "spec": {
                        "selector": {"matchLabels": {"app": "api"}},
                        "template": {
                            "metadata": {"labels": {"app": "api", "tier": "frontend"}}
                        },
                    },
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {
                        "name": "api",
                        "namespace": "payments",
                        "resourceVersion": "30",
                    },
                    "spec": {"selector": {"app": "api"}},
                },
            ],
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {
                    "namespaces": [live_state["items"][0]],
                    "deployments": [live_state["items"][1]],
                    "services": [live_state["items"][2]],
                }
            )

            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertIsNone(warning)
        self.assertGreaterEqual(run.call_count, 1)
        namespace_args = run.call_args_list[0].args[0]
        service_args = run.call_args_list[1].args[0]
        self.assertEqual(namespace_args[:4], ["kubectl", "--context", "prod", "get"])
        self.assertEqual(namespace_args[4:], ["namespaces", "-o", "json"])
        self.assertEqual(service_args[:4], ["kubectl", "--context", "prod", "get"])
        self.assertEqual(service_args[4:], ["services", "-A", "-o", "json"])
        assert topology is not None
        self.assertEqual(topology["metadata"]["import"]["source_type"], "kubernetes")
        self.assertIn("updated_at", topology)
        self.assertNotIn("managedFields", json.dumps(topology))
        service_by_id = {service["id"]: service for service in topology["services"]}
        self.assertEqual(
            service_by_id["Namespace/payments"]["downstream"],
            ["Deployment/payments/api", "Service/payments/api"],
        )
        self.assertEqual(
            service_by_id["Deployment/payments/api"]["downstream"],
            ["Service/payments/api"],
        )
        self.assertNotIn(
            "Deployment/api",
            service_by_id["Deployment/payments/api"]["resource_keys"],
        )
        self.assertNotIn(
            "Namespace/payments",
            service_by_id["Deployment/payments/api"]["resource_keys"],
        )
        self.assertFalse(
            any(
                resource_key.startswith("resourceVersion:")
                for service in topology["services"]
                for resource_key in service["resource_keys"]
            )
        )
        self.assertIn(
            "selector:payments:app=api",
            service_by_id["Service/payments/api"]["resource_keys"],
        )
        changes = parse_kubernetes(
            "deployment.yaml",
            b"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: payments
""",
        )
        blast_radius = compute_blast_radius(changes, topology, warning)
        self.assertEqual(blast_radius.context_source["type"], "kubernetes")
        self.assertEqual(blast_radius.freshness["updated_at"], topology["updated_at"])
        self.assertIsInstance(blast_radius.freshness["age_days"], int)
        self.assertEqual(blast_radius.direct_count, 1)
        self.assertEqual(blast_radius.transitive_count, 1)
        self.assertEqual(
            [node.service_id for node in blast_radius.affected],
            ["Deployment/payments/api", "Service/payments/api"],
        )

    def test_import_topology_source_matches_namespaced_kubernetes_manifest_once(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        live_state = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api", "namespace": "payments"},
                    "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api", "namespace": "payments"},
                    "spec": {"selector": {"app": "api"}},
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api", "namespace": "staging"},
                    "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api", "namespace": "staging"},
                    "spec": {"selector": {"app": "api"}},
                },
            ],
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {
                    "deployments": [live_state["items"][0], live_state["items"][2]],
                    "services": [live_state["items"][1], live_state["items"][3]],
                }
            )
            import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )
        topology, warning = load_topology(project_key="payments")
        changes = parse_kubernetes(
            "deployment.yaml",
            b"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: payments
""",
        )

        blast_radius = compute_blast_radius(changes, topology, warning)

        self.assertEqual(changes[0].resource_id, "Deployment/payments/api")
        self.assertEqual(blast_radius.direct_count, 1)
        self.assertEqual(blast_radius.transitive_count, 1)
        self.assertEqual(
            [node.service_id for node in blast_radius.affected],
            ["Deployment/payments/api", "Service/payments/api"],
        )

    def test_import_topology_source_leaves_namespace_less_manifest_unmatched(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        live_state = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api", "namespace": "default"},
                    "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api", "namespace": "default"},
                    "spec": {"selector": {"app": "api"}},
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api", "namespace": "staging"},
                    "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api", "namespace": "staging"},
                    "spec": {"selector": {"app": "api"}},
                },
            ],
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {
                    "deployments": [live_state["items"][0], live_state["items"][2]],
                    "services": [live_state["items"][1], live_state["items"][3]],
                }
            )
            import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )
        topology, warning = load_topology(project_key="payments")
        changes = parse_kubernetes(
            "deployment.yaml",
            b"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
""",
        )

        blast_radius = compute_blast_radius(changes, topology, warning)

        self.assertEqual(changes[0].resource_id, "Deployment/api")
        self.assertEqual(blast_radius.direct_count, 0)
        self.assertEqual(blast_radius.transitive_count, 0)
        self.assertEqual(blast_radius.affected, [])
        self.assertEqual(blast_radius.unmatched_resources, ["Deployment/api"])
        self.assertIn("no topology mapping", blast_radius.warning.lower())

    def test_import_topology_source_matches_namespace_manifest_through_namespace_node(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        live_state = {
            "apiVersion": "v1",
            "kind": "List",
            "items": [
                {
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {"name": "payments"},
                },
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "metadata": {"name": "api", "namespace": "payments"},
                    "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
                },
                {
                    "apiVersion": "v1",
                    "kind": "Service",
                    "metadata": {"name": "api", "namespace": "payments"},
                    "spec": {"selector": {"app": "api"}},
                },
            ],
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {
                    "namespaces": [live_state["items"][0]],
                    "deployments": [live_state["items"][1]],
                    "services": [live_state["items"][2]],
                }
            )
            import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )
        topology, warning = load_topology(project_key="payments")
        changes = parse_kubernetes(
            "namespace.yaml",
            b"""apiVersion: v1
kind: Namespace
metadata:
  name: payments
""",
        )

        blast_radius = compute_blast_radius(changes, topology, warning)

        self.assertEqual(changes[0].resource_id, "Namespace/payments")
        self.assertEqual(blast_radius.direct_count, 1)
        self.assertEqual(blast_radius.transitive_count, 2)
        self.assertEqual(
            [(node.service_id, node.depth) for node in blast_radius.affected],
            [
                ("Namespace/payments", 0),
                ("Deployment/payments/api", 1),
                ("Service/payments/api", 1),
            ],
        )

    def test_kubernetes_parser_alias_matches_legacy_custom_topology_key(self) -> None:
        topology = {
            "metadata": {"import": {"source_type": "custom", "source_ref": "legacy"}},
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
        changes = parse_kubernetes(
            "deployment.yaml",
            b"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: payments
""",
        )

        blast_radius = compute_blast_radius(changes, topology)

        self.assertEqual(changes[0].resource_id, "Deployment/payments/api")
        self.assertEqual(changes[0].metadata["resource_aliases"], ["Deployment/api"])
        self.assertEqual(blast_radius.direct_count, 1)
        self.assertEqual([node.service_id for node in blast_radius.affected], ["api"])

    def test_import_topology_source_resolves_current_context_source_ref(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            if args == ["kubectl", "config", "current-context"]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="prod\n",
                    stderr="",
                )
            resource = args[args.index("get") + 1]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": [deployment] if resource == "deployments" else [],
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "current-context",
                project_key="payments",
            )

        topology, _ = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertEqual(result.source_ref, "context:prod")
        assert topology is not None
        self.assertEqual(topology["metadata"]["import"]["source_ref"], "context:prod")
        get_args = run.call_args_list[1].args[0]
        self.assertEqual(get_args[:3], ["kubectl", "--context", "prod"])

    def test_import_topology_source_current_context_uses_one_timeout_budget(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        command_timeouts: list[float] = []

        def side_effect(
            args: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess:
            command_timeouts.append(float(kwargs["timeout"]))
            if args == ["kubectl", "config", "current-context"]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="prod\n",
                    stderr="",
                )
            raise FileNotFoundError("kubectl")

        with (
            patch("services.topology_service.subprocess.run", side_effect=side_effect),
            patch(
                "services.topology_service.monotonic",
                side_effect=[100.0, 100.0, 109.0],
            ),
        ):
            result = import_topology_source(
                "kubernetes",
                "current-context",
                project_key="payments",
            )

        self.assertFalse(result.applied)
        self.assertEqual(command_timeouts[0], 10.0)
        self.assertLessEqual(command_timeouts[1], 1.0)

    def test_import_topology_source_preserves_topology_when_current_context_resolver_fails(
        self,
    ) -> None:
        failure_cases = [
            FileNotFoundError("kubectl"),
            OSError("kubectl"),
            subprocess.TimeoutExpired("kubectl", timeout=10),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
            subprocess.CalledProcessError(1, ["kubectl"]),
            subprocess.CompletedProcess(
                args=["kubectl", "config", "current-context"],
                returncode=0,
                stdout="\n",
                stderr="",
            ),
        ]
        baseline = json.dumps(
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

        for index, failure in enumerate(failure_cases):
            project_key = f"resolver-{index}"
            project_service_module.create_project(
                project_key=project_key,
                display_name=f"Resolver {index}",
            )
            save_topology_definition(baseline, project_key=project_key)

            with self.subTest(failure=type(failure).__name__, index=index):
                with patch("services.topology_service.subprocess.run") as run:
                    if isinstance(failure, subprocess.CompletedProcess):
                        run.return_value = failure
                    else:
                        run.side_effect = failure
                    result = import_topology_source(
                        "kubernetes",
                        "current-context",
                        project_key=project_key,
                    )

                topology, warning = load_topology(project_key=project_key)

                self.assertFalse(result.applied)
                assert warning is not None
                self.assertIn("kubernetes live-state context todo", warning.lower())
                assert topology is not None
                self.assertEqual(
                    [service["id"] for service in topology["services"]], ["api"]
                )

    def test_current_context_refresh_failure_warns_existing_resolved_topology(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def successful_resolve(
            args: list[str], **_: object
        ) -> subprocess.CompletedProcess:
            if args == ["kubectl", "config", "current-context"]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="prod\n",
                    stderr="",
                )
            resource = args[args.index("get") + 1]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": [deployment] if resource == "deployments" else [],
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = successful_resolve
            baseline = import_topology_source(
                "kubernetes",
                "current-context",
                project_key="payments",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = subprocess.TimeoutExpired("kubectl", timeout=10)
            refresh = import_topology_source(
                "kubernetes",
                "current-context",
                project_key="payments",
            )

        status = get_topology_status(project_key="payments")

        self.assertTrue(baseline.applied)
        self.assertEqual(baseline.source_ref, "context:prod")
        self.assertFalse(refresh.applied)
        self.assertEqual(
            status.payload["metadata"]["import"]["source_ref"], "context:prod"
        )
        self.assertIn(
            "kubernetes live-state context todo",
            " ".join(status.warnings).lower(),
        )

    def test_current_context_failure_does_not_warn_unrelated_explicit_context(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {"deployments": [deployment]}
            )
            baseline = import_topology_source(
                "kubernetes",
                "context:staging",
                project_key="payments",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = subprocess.TimeoutExpired("kubectl", timeout=10)
            refresh = import_topology_source(
                "kubernetes",
                "current-context",
                project_key="payments",
            )

        status = get_topology_status(project_key="payments")

        self.assertTrue(baseline.applied)
        self.assertEqual(baseline.source_ref, "context:staging")
        self.assertFalse(refresh.applied)
        self.assertEqual(
            status.payload["metadata"]["import"]["source_ref"], "context:staging"
        )
        self.assertNotIn(
            "kubernetes live-state context todo",
            " ".join(status.warnings).lower(),
        )

    def test_current_context_warning_survives_unrelated_context_probe(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def successful_resolve(
            args: list[str], **_: object
        ) -> subprocess.CompletedProcess:
            if args == ["kubectl", "config", "current-context"]:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="prod\n",
                    stderr="",
                )
            resource = args[args.index("get") + 1]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": [deployment] if resource == "deployments" else [],
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = successful_resolve
            baseline = import_topology_source(
                "kubernetes",
                "current-context",
                project_key="payments",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = subprocess.TimeoutExpired("kubectl", timeout=10)
            refresh = import_topology_source(
                "kubernetes",
                "current-context",
                project_key="payments",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            unrelated_probe = import_topology_source(
                "kubernetes",
                "context:staging",
                project_key="payments",
            )

        status = get_topology_status(project_key="payments")
        joined_warnings = " ".join(status.warnings).lower()

        self.assertTrue(baseline.applied)
        self.assertFalse(refresh.applied)
        self.assertFalse(unrelated_probe.applied)
        self.assertIn("resolving the current kubernetes context", joined_warnings)
        self.assertNotIn("context:staging", joined_warnings)

    def test_import_topology_source_warns_without_replacing_for_unavailable_kubernetes(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "baseline-topology.json"
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

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("todo", " ".join(result.warnings).lower())
        self.assertEqual(result.accepted_resources, [])
        self.assertEqual(len(result.unsupported_resources), 1)
        assert topology is not None
        self.assertEqual([service["id"] for service in topology["services"]], ["api"])
        assert warning is not None
        self.assertIn("kubernetes live-state context todo", warning.lower())

    def test_save_topology_definition_clears_cached_kubernetes_live_state_warning(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        _, warning = load_topology(project_key="payments")
        assert warning is not None
        self.assertIn("kubernetes live-state context todo", warning.lower())

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

        _, warning = load_topology(project_key="payments")

        if warning is not None:
            self.assertNotIn("kubernetes live-state context todo", warning.lower())

    def test_import_topology_source_warns_for_invalid_kubernetes_source_ref(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with patch("services.topology_service.subprocess.run") as run:
            result = import_topology_source(
                "kubernetes",
                "context:",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertEqual(run.call_count, 0)
        self.assertIn("context:<name>", " ".join(result.warnings))
        self.assertIsNone(topology)
        assert warning is not None
        self.assertIn("kubernetes live-state context todo", warning.lower())

    def test_import_topology_source_warns_for_kubernetes_timeout(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = subprocess.TimeoutExpired("kubectl", timeout=10)
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("todo", " ".join(result.warnings).lower())
        self.assertIn("timed out", " ".join(result.warnings).lower())
        self.assertEqual(result.accepted_resources, [])
        self.assertIsNone(topology)
        self.assertIn("not configured", warning)
        assert warning is not None
        self.assertIn("kubernetes live-state context todo", warning.lower())

    def test_import_topology_source_warns_for_kubernetes_os_error(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = PermissionError("kubectl")
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("todo", " ".join(result.warnings).lower())
        self.assertIn("could not be executed", " ".join(result.warnings).lower())
        self.assertEqual(result.accepted_resources, [])
        self.assertIsNone(topology)
        assert warning is not None
        self.assertIn("kubernetes live-state context todo", warning.lower())

    def test_import_topology_source_warns_for_kubernetes_decode_error(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("todo", " ".join(result.warnings).lower())
        self.assertIn("utf-8", " ".join(result.warnings).lower())
        self.assertEqual(result.accepted_resources, [])
        self.assertIsNone(topology)
        assert warning is not None
        self.assertIn("kubernetes live-state context todo", warning.lower())

    def test_import_topology_source_partially_skips_live_state_missing_namespace(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "baseline-topology.json"
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
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "payments"},
        }
        malformed_deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {
                    "namespaces": [namespace],
                    "deployments": [malformed_deployment],
                }
            )
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("partially parsed", " ".join(result.warnings).lower())
        self.assertEqual(
            [item.resource_ref for item in result.partially_parsed_resources],
            ["Deployment/api"],
        )
        assert topology is not None
        self.assertEqual([service["id"] for service in topology["services"]], ["api"])
        self.assertNotIn("Deployment/default/api", json.dumps(topology))
        assert warning is not None
        self.assertIn("partially parsed", warning.lower())

    def test_import_topology_source_preserves_partial_kubernetes_rbac_context(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "namespaces":
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": [deployment] if resource == "deployments" else [],
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertIn("namespaces", " ".join(result.warnings))
        assert topology is not None
        self.assertEqual(
            [service["id"] for service in topology["services"]],
            ["Deployment/payments/api"],
        )
        assert warning is not None
        self.assertIn("cluster access is unavailable", warning.lower())

    def test_import_topology_source_preserves_mid_scan_launcher_failure_context(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "statefulsets":
                raise FileNotFoundError("kubectl")
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": [deployment] if resource == "deployments" else [],
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertIn("kubectl", " ".join(result.warnings).lower())
        assert topology is not None
        self.assertEqual(
            [service["id"] for service in topology["services"]],
            ["Deployment/payments/api"],
        )
        assert warning is not None
        self.assertIn("kubectl", warning.lower())

    def test_import_topology_source_does_not_fallback_for_non_rbac_all_namespace_error(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "baseline-topology.json"
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
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "payments"},
        }
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "deployments" and "-A" in args:
                raise subprocess.CalledProcessError(
                    1,
                    args,
                    stderr="dial tcp 10.0.0.1:443: i/o timeout",
                )
            items = []
            if resource == "namespaces":
                items = [namespace]
            elif resource == "deployments":
                items = [deployment]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": items,
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("cluster access is unavailable", " ".join(result.warnings))
        assert topology is not None
        self.assertEqual([service["id"] for service in topology["services"]], ["api"])
        assert warning is not None
        self.assertIn("cluster access is unavailable", warning.lower())

    def test_import_topology_source_does_not_run_immediate_kubernetes_drift_read(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {"deployments": [deployment]}
            )
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        get_calls = [
            call.args[0] for call in run.call_args_list if "get" in call.args[0]
        ]

        self.assertTrue(result.applied)
        self.assertEqual(len(get_calls), 5)

    def test_import_topology_source_retries_namespaced_access_after_all_namespaces_rbac(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "payments"},
        }

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "deployments" and "-A" in args:
                raise subprocess.CalledProcessError(
                    1,
                    args,
                    stderr="Error from server (Forbidden): deployments is forbidden",
                )
            items = []
            if resource == "namespaces":
                items = [namespace]
            elif resource == "deployments":
                items = [deployment]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": items,
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")
        deployment_calls = [
            call.args[0]
            for call in run.call_args_list
            if call.args[0][call.args[0].index("get") + 1] == "deployments"
        ]

        self.assertTrue(result.applied)
        self.assertEqual(deployment_calls[0][4:], ["deployments", "-A", "-o", "json"])
        self.assertEqual(
            deployment_calls[1][4:],
            ["deployments", "-n", "payments", "-o", "json"],
        )
        self.assertIn("all-namespaces access", " ".join(result.warnings))
        assert topology is not None
        self.assertEqual(
            [service["id"] for service in topology["services"]],
            ["Deployment/payments/api", "Namespace/payments"],
        )
        assert warning is not None
        self.assertIn("all-namespaces access", warning)

    def test_import_topology_source_failed_kubernetes_probe_marks_cached_drift_unavailable(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {"deployments": [deployment]}
            )
            import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        initial_status = get_topology_status(project_key="payments")
        assert initial_status.drift is not None
        self.assertEqual(initial_status.drift.status, "up_to_date")

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            failed_result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        status = get_topology_status(project_key="payments")

        self.assertFalse(failed_result.applied)
        self.assertIsNotNone(status.drift)
        assert status.drift is not None
        self.assertEqual(status.drift.status, "unavailable")
        self.assertIn("Kubernetes live-state", " ".join(status.drift.warnings))

    def test_import_topology_source_continues_namespace_fallback_after_forbidden_namespace(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        namespaces = [
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": "restricted"},
            },
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": "payments"},
            },
        ]
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "deployments" and "-A" in args:
                raise subprocess.CalledProcessError(
                    1,
                    args,
                    stderr="Error from server (Forbidden): deployments is forbidden",
                )
            if resource == "deployments" and "restricted" in args:
                raise subprocess.CalledProcessError(1, args)
            items = []
            if resource == "namespaces":
                items = namespaces
            elif resource == "deployments" and "payments" in args:
                items = [deployment]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": items,
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")
        deployment_calls = [
            call.args[0]
            for call in run.call_args_list
            if call.args[0][call.args[0].index("get") + 1] == "deployments"
        ]

        self.assertTrue(result.applied)
        self.assertEqual(
            [args[4:] for args in deployment_calls[:3]],
            [
                ["deployments", "-A", "-o", "json"],
                ["deployments", "-n", "restricted", "-o", "json"],
                ["deployments", "-n", "payments", "-o", "json"],
            ],
        )
        self.assertIn("namespace 'restricted'", " ".join(result.warnings))
        assert topology is not None
        self.assertIn(
            "Deployment/payments/api",
            [service["id"] for service in topology["services"]],
        )
        assert warning is not None
        self.assertIn("namespace 'restricted'", warning)

    def test_import_topology_source_success_clears_previous_kubernetes_todo_from_result(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            failed_result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        self.assertFalse(failed_result.applied)
        self.assertIn(
            "kubernetes live-state context todo",
            " ".join(failed_result.warnings).lower(),
        )

        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "payments"},
        }
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {
                    "namespaces": [namespace],
                    "deployments": [deployment],
                }
            )
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        _, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertNotIn(
            "kubernetes live-state context todo", " ".join(result.warnings).lower()
        )
        if warning is not None:
            self.assertNotIn("kubernetes live-state context todo", warning.lower())

    def test_get_topology_status_ignores_cached_kubernetes_todos_for_other_source_ref(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {"deployments": [deployment]}
            )
            import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            failed_result = import_topology_source(
                "kubernetes",
                "context:staging",
                project_key="payments",
            )
            status = get_topology_status(project_key="payments")

        self.assertFalse(failed_result.applied)
        self.assertEqual(
            status.payload["metadata"]["import"]["source_ref"],
            "context:prod",
        )
        joined_warnings = " ".join(status.warnings).lower()
        self.assertNotIn("context:staging", joined_warnings)
        self.assertNotIn("kubernetes live-state context todo", joined_warnings)

    def test_get_topology_status_ignores_cached_kubernetes_todos_after_custom_import(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            failed_result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        source_path = Path(self.tempdir.name) / "custom-after-kubernetes.json"
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

        self.assertFalse(failed_result.applied)
        self.assertEqual(status.payload["metadata"]["import"]["source_type"], "custom")
        joined_warnings = " ".join(status.warnings).lower()
        self.assertNotIn("kubernetes live-state context todo", joined_warnings)

    def test_import_topology_source_preserves_topology_when_partial_empty_read_fails(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "baseline-topology.json"
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

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "services" and "-A" in args:
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps({"apiVersion": "v1", "kind": "List", "items": []}),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("cluster access is unavailable", " ".join(result.warnings))
        assert topology is not None
        self.assertEqual([service["id"] for service in topology["services"]], ["api"])
        assert warning is not None
        self.assertIn("cluster access is unavailable", warning)

    def test_import_topology_source_empty_stderr_all_namespace_failure_is_not_rbac(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "payments"},
        }
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        def side_effect(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "deployments" and "-A" in args:
                raise subprocess.CalledProcessError(1, args, stderr="")
            items = [namespace] if resource == "namespaces" else []
            if resource == "deployments" and "-n" in args:
                items = [deployment]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": items,
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = side_effect
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        self.assertFalse(result.applied)
        joined_warnings = " ".join(result.warnings)
        self.assertIn("cluster access is unavailable", joined_warnings)
        self.assertNotIn("all-namespaces access", joined_warnings)

    def test_import_topology_source_empty_kubernetes_snapshot_clears_stale_topology(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "baseline-topology.json"
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

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect({})
            result = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        assert topology is not None
        self.assertEqual(topology["services"], [])
        self.assertIn("did not produce", " ".join(result.warnings))
        assert warning is not None
        self.assertIn("did not produce", warning)

    def test_import_topology_source_reads_terraform_state_relationships(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        state_path = Path(self.tempdir.name) / "terraform.tfstate"
        state_path.write_text(
            json.dumps(
                {
                    "version": 4,
                    "terraform_version": "1.8.5",
                    "serial": 42,
                    "lineage": "state-lineage",
                    "resources": [
                        {
                            "mode": "managed",
                            "type": "aws_db_instance",
                            "name": "primary",
                            "provider": 'provider["registry.terraform.io/hashicorp/aws"]',
                            "instances": [
                                {
                                    "attributes": {
                                        "id": "db-123",
                                        "arn": "arn:aws:rds:us-east-1:111122223333:db:primary",
                                    }
                                }
                            ],
                        },
                        {
                            "mode": "managed",
                            "type": "aws_ecs_service",
                            "name": "api",
                            "instances": [
                                {
                                    "dependencies": ["aws_db_instance.primary"],
                                    "attributes": {"id": "svc-123", "name": "api"},
                                }
                            ],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = import_topology_source(
            "terraform",
            str(state_path),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertEqual(
            sorted(result.diff.added_services),
            ["aws_db_instance.primary", "aws_ecs_service.api"],
        )
        self.assertIsNone(warning)
        assert topology is not None
        service_by_id = {service["id"]: service for service in topology["services"]}
        self.assertEqual(
            service_by_id["aws_db_instance.primary"]["downstream"],
            ["aws_ecs_service.api"],
        )
        self.assertIn(
            "arn:aws:rds:us-east-1:111122223333:db:primary",
            service_by_id["aws_db_instance.primary"]["resource_keys"],
        )
        self.assertIn(
            "aws_db_instance.primary",
            service_by_id["aws_db_instance.primary"]["resource_keys"],
        )
        self.assertEqual(
            topology["metadata"]["import"]["source_type"],
            "terraform",
        )
        blast_radius = compute_blast_radius(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_db_instance.primary",
                    action="modify",
                    summary="Terraform changed the database.",
                )
            ],
            topology,
            warning,
        )
        self.assertEqual(blast_radius.context_source["type"], "terraform")
        self.assertEqual(blast_radius.direct_count, 1)
        self.assertEqual(blast_radius.transitive_count, 1)
        self.assertEqual(
            [node.service_id for node in blast_radius.affected],
            ["aws_db_instance.primary", "aws_ecs_service.api"],
        )

    def test_import_topology_source_warns_without_failing_for_missing_terraform_state(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        missing_path = Path(self.tempdir.name) / "missing.tfstate"

        result = import_topology_source(
            "terraform",
            str(missing_path),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertEqual(result.accepted_resources, [])
        self.assertIn("unavailable", " ".join(result.warnings).lower())
        self.assertIsNone(topology)
        self.assertIn("not configured", warning)

    def test_import_topology_source_warns_without_replacing_for_missing_resources(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "baseline-topology.json"
        source_path.write_text(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "api",
                            "label": "API",
                            "resource_keys": ["aws_ecs_service.api"],
                            "downstream": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        import_topology_source("custom", str(source_path), project_key="payments")
        state_path = Path(self.tempdir.name) / "malformed.tfstate"
        state_path.write_text(
            json.dumps({"version": 4, "serial": 1}),
            encoding="utf-8",
        )

        result = import_topology_source(
            "terraform",
            str(state_path),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertFalse(result.applied)
        self.assertIn("resources", " ".join(result.warnings).lower())
        assert topology is not None
        self.assertEqual(
            [service["id"] for service in topology["services"]],
            ["api"],
        )
        self.assertIsNone(warning)

    def test_import_topology_source_matches_for_each_plan_addresses(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        state_path = Path(self.tempdir.name) / "foreach.tfstate"
        state_path.write_text(
            json.dumps(
                {
                    "version": 4,
                    "serial": 1,
                    "resources": [
                        {
                            "mode": "managed",
                            "type": "aws_instance",
                            "name": "web",
                            "instances": [
                                {
                                    "index_key": "blue",
                                    "attributes": {"id": "i-blue"},
                                }
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = import_topology_source(
            "terraform",
            str(state_path),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        assert topology is not None
        service = topology["services"][0]
        self.assertIn('aws_instance.web["blue"]', service["resource_keys"])
        blast_radius = compute_blast_radius(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id='aws_instance.web["blue"]',
                    action="modify",
                    summary="Terraform changed an indexed instance.",
                )
            ],
            topology,
            warning,
        )
        self.assertEqual(blast_radius.direct_count, 1)
        self.assertEqual(blast_radius.unmatched_resources, [])

    def test_import_topology_source_resolves_indexed_dependency_refs(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        state_path = Path(self.tempdir.name) / "indexed-dependency.tfstate"
        state_path.write_text(
            json.dumps(
                {
                    "version": 4,
                    "serial": 1,
                    "resources": [
                        {
                            "mode": "managed",
                            "type": "aws_db_instance",
                            "name": "primary",
                            "instances": [
                                {
                                    "index_key": "blue",
                                    "attributes": {"id": "db-blue"},
                                }
                            ],
                        },
                        {
                            "mode": "managed",
                            "type": "aws_ecs_service",
                            "name": "api",
                            "instances": [
                                {
                                    "dependencies": ['aws_db_instance.primary["blue"]'],
                                    "attributes": {"id": "svc-api"},
                                }
                            ],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = import_topology_source(
            "terraform",
            str(state_path),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertEqual(result.partially_parsed_resources, [])
        self.assertIsNone(warning)
        assert topology is not None
        service_by_id = {service["id"]: service for service in topology["services"]}
        self.assertEqual(
            service_by_id["aws_db_instance.primary"]["downstream"],
            ["aws_ecs_service.api"],
        )
        blast_radius = compute_blast_radius(
            [
                UnifiedChange(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id='aws_db_instance.primary["blue"]',
                    action="modify",
                    summary="Terraform changed an indexed database.",
                )
            ],
            topology,
            warning,
        )
        self.assertEqual(blast_radius.direct_count, 1)
        self.assertEqual(blast_radius.transitive_count, 1)
        self.assertEqual(
            [node.service_id for node in blast_radius.affected],
            ["aws_db_instance.primary", "aws_ecs_service.api"],
        )

    def test_import_topology_source_warns_for_stale_terraform_state(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        state_path = Path(self.tempdir.name) / "stale.tfstate"
        state_path.write_text(
            json.dumps(
                {
                    "version": 4,
                    "serial": 1,
                    "resources": [
                        {
                            "mode": "managed",
                            "type": "aws_lambda_function",
                            "name": "worker",
                            "instances": [{"attributes": {"id": "worker"}}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        stale_timestamp = datetime(2025, 1, 1, tzinfo=UTC).timestamp()
        os.utime(state_path, (stale_timestamp, stale_timestamp))

        result = import_topology_source(
            "terraform",
            str(state_path),
            project_key="payments",
        )
        topology, warning = load_topology(project_key="payments")

        self.assertTrue(result.applied)
        self.assertIn("stale", " ".join(result.warnings).lower())
        self.assertIsNotNone(topology)
        self.assertIn("stale", warning)

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

    def test_check_topology_drift_marks_partial_kubernetes_reread_unavailable(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "payments"},
        }
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {
                    "namespaces": [namespace],
                    "deployments": [deployment],
                }
            )
            imported = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        def partial_reread(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            if resource == "deployments" and "-A" in args:
                raise subprocess.CalledProcessError(
                    1,
                    args,
                    stderr="Error from server (Forbidden): deployments is forbidden",
                )
            items = []
            if resource == "namespaces":
                items = [namespace]
            elif resource == "deployments":
                items = [deployment]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": items,
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = partial_reread
            drift = check_topology_drift(project_key="payments", force=True)

        self.assertTrue(imported.applied)
        self.assertEqual(drift.status, "unavailable")
        self.assertFalse(drift.alert)
        self.assertEqual(drift.added_resources, [])
        self.assertEqual(drift.removed_resources, [])
        self.assertIn("all-namespaces access", " ".join(drift.warnings))

    def test_check_topology_drift_marks_malformed_partial_kubernetes_reread_unavailable(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "api", "namespace": "payments"},
            "spec": {"template": {"metadata": {"labels": {"app": "api"}}}},
        }
        malformed_statefulset = {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {"name": "db"},
            "spec": {"template": {"metadata": {"labels": {"app": "db"}}}},
        }

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = _kubectl_live_state_side_effect(
                {"deployments": [deployment]}
            )
            imported = import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )

        def partial_reread(args: list[str], **_: object) -> subprocess.CompletedProcess:
            resource = args[args.index("get") + 1]
            items = []
            if resource == "deployments":
                items = [deployment]
            elif resource == "statefulsets":
                items = [malformed_statefulset]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "apiVersion": "v1",
                        "kind": "List",
                        "items": items,
                    }
                ),
                stderr="",
            )

        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = partial_reread
            drift = check_topology_drift(project_key="payments", force=True)

        self.assertTrue(imported.applied)
        self.assertEqual(drift.status, "unavailable")
        self.assertFalse(drift.alert)
        self.assertIn("partially parsed", " ".join(drift.warnings).lower())

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

    def test_check_topology_drift_ignores_cached_status_after_source_changes(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        source_path = Path(self.tempdir.name) / "cached-source-topology.json"
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
        save_topology_definition(
            json.dumps(
                {
                    "services": [
                        {
                            "id": "manual-api",
                            "label": "Manual API",
                            "resource_keys": ["Deployment/manual-api"],
                            "downstream": [],
                        }
                    ]
                }
            ),
            project_key="payments",
        )

        drift = check_topology_drift(project_key="payments")

        self.assertEqual(drift.status, "unavailable")
        self.assertEqual(drift.source_type, "manual")
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

    def test_run_due_topology_drift_checks_updates_workspace_imports(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        source_path = Path(self.tempdir.name) / "workspace-drift-topology.json"
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

        import_topology_source(
            "custom",
            str(source_path),
            project_key="payments",
            workspace_key="prod",
        )
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
                f"topology_drift_status::{project.id}::{workspace.id}",
            )
            assert cached_drift is not None
            cached_payload = json.loads(cached_drift.value)
            cached_payload["checked_at"] = "2026-04-01T00:00:00Z"
            cached_payload["next_check_at"] = "2026-04-02T00:00:00Z"
            cached_drift.value = json.dumps(cached_payload)
            session.commit()

        run_due_topology_drift_checks()
        with SessionLocal() as session:
            cached_drift = session.get(
                tables_module.AppSetting,
                f"topology_drift_status::{project.id}::{workspace.id}",
            )
            assert cached_drift is not None
            cached_payload = json.loads(cached_drift.value)

        self.assertEqual(cached_payload["status"], "drifted")
        self.assertEqual(cached_payload["added_resources"], ["Deployment/worker"])

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

    def test_get_topology_status_merges_cached_kubernetes_todos_for_invalid_payload(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        with patch("services.topology_service.subprocess.run") as run:
            run.side_effect = FileNotFoundError("kubectl")
            import_topology_source(
                "kubernetes",
                "context:prod",
                project_key="payments",
            )
        with SessionLocal() as session:
            session.add(
                tables_module.TopologyVersion(
                    project_id=project.id,
                    source_type="kubernetes",
                    payload_json="{bad json",
                )
            )
            session.commit()

        status = get_topology_status(project_id=project.id)

        self.assertTrue(status.exists)
        self.assertIn(
            "stored topology JSON is invalid", " ".join(status.blocking_errors)
        )
        self.assertIn(
            "kubernetes live-state context todo",
            " ".join(status.warnings).lower(),
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
