"""Synthetic credential boundaries for topology connectors."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import services.topology_service as topology

SECRET = "synthetic-topology-secret-731"


class TopologyCredentialTests(unittest.TestCase):
    def test_persistence_screens_database_json_and_legacy_mirror(self) -> None:
        project = {"id": 1, "project_key": "synthetic", "is_default": True}
        payload = {
            "services": [{"id": "api", "label": f"token={SECRET}"}],
            "metadata": {
                "import": {"source_type": "manual", "source_ref": "inline://manual"}
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-topology.json"
            with (
                patch.object(topology, "_topology_path", return_value=path),
                patch.object(topology, "SessionLocal") as factory,
            ):
                status = topology._persist_topology_payload(
                    payload, project=project, workspace=None, source_type="manual"
                )
                row = factory.return_value.__enter__.return_value.add.call_args.args[0]
                self.assertNotIn(SECRET, row.payload_json)
                self.assertNotIn(SECRET, path.read_text())
        self.assertNotIn(SECRET, status.model_dump_json())

    def test_cached_drift_and_source_status_screen_historical_credentials(self) -> None:
        project = {"id": 1, "project_key": "synthetic"}
        payload = {
            "status": "unavailable",
            "source_ref": f"https://user:{SECRET}@example.invalid",
            "warnings": [f"Bearer {SECRET}"],
        }
        with (
            patch.object(topology, "SessionLocal"),
            patch.object(
                topology,
                "get_setting",
                return_value=SimpleNamespace(value=json.dumps(payload)),
            ),
        ):
            drift = topology._load_cached_topology_drift(project)
            source = topology._load_topology_source_status(project)
        self.assertNotIn(SECRET, drift.model_dump_json())
        self.assertNotIn(SECRET, json.dumps(source))

    def test_resolved_current_context_rejects_credentials(self) -> None:
        completed = subprocess.CompletedProcess(
            ["kubectl"], 0, stdout=f"https://user:{SECRET}@example.invalid"
        )
        with patch.object(topology.subprocess, "run", return_value=completed):
            with self.assertRaises(topology.TopologyImportError) as caught:
                topology._resolve_kubernetes_import_source_ref("current-context")
        self.assertNotIn(SECRET, str(caught.exception))

    def test_marked_terraform_identity_is_not_reintroduced_through_other_keys(
        self,
    ) -> None:
        keys = topology._terraform_state_identity_keys(
            "test.example",
            {"type": "test"},
            [
                {
                    "attributes": {"name": SECRET, "id": f"resource/{SECRET}"},
                    "sensitive_attributes": [["name"]],
                }
            ],
        )
        self.assertNotIn(SECRET, json.dumps(keys))

    def test_terraform_marked_sensitive_identity_is_omitted(self) -> None:
        for mask in ([["name"]], {"name": True}):
            with self.subTest(mask=mask):
                keys = topology._terraform_state_identity_keys(
                    "test.example",
                    {"type": "test"},
                    [
                        {
                            "attributes": {"name": SECRET, "id": "safe-id"},
                            "sensitive_attributes": mask,
                        }
                    ],
                )
                self.assertNotIn(SECRET, json.dumps(keys))
                self.assertIn("safe-id", keys)

    def test_terraform_sensitive_values_mask_and_credential_url_are_omitted(
        self,
    ) -> None:
        keys = topology._terraform_state_identity_keys(
            "test.example",
            {"type": "test"},
            [
                {
                    "attributes": {
                        "name": SECRET,
                        "self_link": f"https://user:{SECRET}@example.invalid",
                    },
                    "sensitive_values": {"name": True},
                }
            ],
        )
        self.assertNotIn(SECRET, json.dumps(keys))

    def test_kubernetes_sensitive_selector_still_matches_without_persistence(
        self,
    ) -> None:
        items = [
            {
                "kind": "Service",
                "metadata": {"name": "api", "namespace": "test"},
                "spec": {"selector": {"token": SECRET}},
            },
            {
                "kind": "Deployment",
                "metadata": {"name": "worker", "namespace": "test"},
                "spec": {"template": {"metadata": {"labels": {"token": SECRET}}}},
            },
        ]
        with patch.object(
            topology,
            "_read_kubernetes_live_state",
            return_value=(json.dumps({"items": items}), []),
        ):
            change_set = topology._parse_kubernetes_live_state_source("context:test")
        self.assertNotIn(SECRET, change_set.model_dump_json())
        worker = next(
            s for s in change_set.services if s["id"].startswith("Deployment/")
        )
        self.assertIn("Service/test/api", worker["downstream"])

    def test_operational_source_is_rejected_before_scope_or_dispatch(self) -> None:
        with patch.object(topology, "resolve_project_reference") as scope:
            with self.assertRaises(topology.TopologyImportError) as caught:
                topology.import_topology_source(
                    "kubernetes", f"context:https://user:{SECRET}@example.invalid"
                )
        scope.assert_not_called()
        self.assertNotIn(SECRET, str(caught.exception))

    def test_custom_preview_and_normalized_graph_screen_credentials(self) -> None:
        payload = {
            "services": [
                {
                    "id": "api",
                    "label": f"token={SECRET}",
                    "owner": f"Bearer {SECRET}",
                    "resource_keys": [f"https://user:{SECRET}@example.invalid", "safe"],
                    "downstream": [],
                }
            ]
        }
        change_set = topology._build_custom_change_set(payload)
        status = topology._build_topology_status(
            payload, path=Path("synthetic"), exists=False
        )
        self.assertNotIn(SECRET, change_set.model_dump_json())
        self.assertNotIn(SECRET, status.model_dump_json())
        self.assertEqual(change_set.services[0]["id"], "api")
        self.assertIn("safe", change_set.services[0]["resource_keys"])

    def test_unsafe_graph_identity_is_blocked_without_echo(self) -> None:
        payload = {"services": [{"id": f"token={SECRET}", "downstream": []}]}
        status = topology._build_topology_status(
            payload, path=Path("synthetic"), exists=False
        )
        self.assertTrue(status.blocking_errors)
        self.assertIsNone(status.payload)
        self.assertNotIn(SECRET, status.model_dump_json())

    def test_legacy_topology_reads_screen_unknown_metadata_and_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(
                json.dumps(
                    {
                        "services": [{"id": "api", "label": f"token={SECRET}"}],
                        "metadata": {"api_token": SECRET},
                    }
                )
            )
            with patch.object(topology, "_topology_path", return_value=path):
                status = topology._read_legacy_topology_status()
        self.assertNotIn(SECRET, status.model_dump_json())

    def test_kubectl_exception_output_never_becomes_warning(self) -> None:
        failure = subprocess.CalledProcessError(
            1, ["kubectl"], output=SECRET, stderr=f"Bearer {SECRET}"
        )
        with patch.object(topology.subprocess, "run", side_effect=failure):
            _, warnings = topology._read_kubernetes_live_state("context:test")
        self.assertNotIn(SECRET, json.dumps(warnings))
