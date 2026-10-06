"""Synthetic credential boundaries for topology connectors."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

import services.topology_service as topology

SECRET = "synthetic-topology-secret-731"


class TopologyCredentialTests(unittest.TestCase):
    def test_manual_topology_discovers_credentials_before_projection(self):
        secret = "manual-review/value!"
        encoded = secret
        for _ in range(5):
            encoded = quote(encoded, safe="")
        payload = {
            "connector": {"password": secret},
            "services": [
                {
                    "id": "api",
                    "label": encoded,
                    "owner": encoded,
                    "owners": [encoded, "safe-team"],
                    "resource_keys": [encoded, "safe-key"],
                    "downstream": [],
                }
            ],
            "metadata": {
                "import": {"source_ref": encoded, "requested_source_ref": encoded}
            },
        }
        screened = topology._screen_topology_payload(payload)
        self.assertNotIn(encoded, json.dumps(screened))
        self.assertNotIn(secret, json.dumps(screened))
        projected = topology._build_custom_change_set(payload)
        self.assertNotIn(encoded, projected.model_dump_json())
        self.assertEqual(projected.services[0]["id"], "api")
        self.assertEqual(projected.services[0]["resource_keys"], ["safe-key"])
        self.assertEqual(
            projected.services[0]["owners"], [topology.REDACTED, "safe-team"]
        )

    def test_manual_validate_and_save_screen_raw_local_credentials(self):
        secret = "manual-review/value!"
        encoded = secret
        for _ in range(5):
            encoded = quote(encoded, safe="")
        raw_text = json.dumps(
            {
                "connector": {"password": secret},
                "services": [
                    {
                        "id": "api",
                        "label": "API",
                        "owner": encoded,
                        "resource_keys": ["safe-key"],
                        "downstream": [],
                    },
                ],
            }
        )
        project = {"id": 1, "project_key": "synthetic"}
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(topology, "resolve_project_reference"),
            patch.object(topology, "build_project_payload", return_value=project),
            patch.object(topology, "resolve_workspace_reference", return_value=None),
            patch.object(
                topology,
                "_topology_scope_path",
                return_value=Path(directory) / "topology.json",
            ),
            patch.object(topology, "_persist_topology_payload") as persist,
            patch.object(topology, "_save_topology_source_status"),
            patch.object(topology, "get_topology_status") as get_status,
        ):
            status = topology.validate_topology_definition(raw_text, project_id=1)
            self.assertEqual(status.blocking_errors, [])
            self.assertNotIn(encoded, status.model_dump_json())
            self.assertEqual(status.payload["services"][0]["owner"], topology.REDACTED)
            persist.return_value = get_status.return_value = status
            saved = topology.save_topology_definition(raw_text, project_id=1)
            self.assertNotIn(encoded, saved.model_dump_json())
            persisted_payload = persist.call_args.args[0]
            self.assertNotIn(encoded, json.dumps(persisted_payload))
            self.assertNotIn(secret, json.dumps(persisted_payload))
            self.assertEqual(
                persisted_payload["services"][0]["owner"], topology.REDACTED
            )
            self.assertNotIn("connector", persisted_payload)

    def test_local_discarded_credentials_screen_all_encoded_topology_references(self):
        secret = "opaque-review/value!"
        values = topology._sensitive_topology_values(
            {"resources": [{"attributes": {"password": secret}}]}
        )
        self.assertIn(secret, values)
        for depth in (3, 5):
            encoded = secret
            for _ in range(depth):
                encoded = quote(encoded, safe="")
            with self.subTest(depth=depth):
                payload = {
                    "services": [
                        {
                            "id": "api",
                            "label": encoded,
                            "owner": encoded,
                            "owners": [encoded, "safe-team"],
                            "resource_keys": [encoded, "safe-key"],
                            "downstream": ["database"],
                        },
                        {"id": "database", "label": "database"},
                    ],
                    "metadata": {
                        "import": {
                            "source_ref": encoded,
                            "requested_source_ref": encoded,
                        }
                    },
                }
                screened = topology._screen_topology_payload(
                    payload, sensitive_values=values
                )
                service = screened["services"][0]
                self.assertEqual(service["label"], topology.REDACTED)
                self.assertEqual(service["owner"], topology.REDACTED)
                self.assertEqual(service["owners"], [topology.REDACTED, "safe-team"])
                self.assertEqual(service["resource_keys"], ["safe-key"])
                self.assertEqual(service["id"], "api")
                self.assertEqual(service["downstream"], ["database"])
                self.assertEqual(
                    screened["metadata"]["import"],
                    {
                        "source_ref": topology.REDACTED,
                        "requested_source_ref": topology.REDACTED,
                    },
                )
                self.assertNotIn(encoded, json.dumps(screened))

    def test_sensitive_instance_index_key_cannot_echo_in_attribute_identity(
        self,
    ) -> None:
        keys = topology._terraform_state_identity_keys(
            "test.example",
            {"type": "test"},
            [
                {
                    "index_key": SECRET,
                    "attributes": {"name": SECRET},
                    "sensitive_attributes": [["index_key"]],
                }
            ],
        )
        self.assertNotIn(SECRET, json.dumps(keys))

    def test_terraform_discarded_sensitive_values_do_not_echo_across_resources(
        self,
    ) -> None:
        for credential in (
            {"attributes": {"password": SECRET}},
            {
                "attributes": {"nested": [{"opaque": SECRET}]},
                "sensitive_attributes": [["nested", 0, "opaque"]],
            },
            {
                "attributes": {"nested": [{"opaque": SECRET}]},
                "sensitive_values": {"nested": [{"opaque": True}]},
            },
        ):
            with (
                self.subTest(credential=credential),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory) / "synthetic.tfstate"
                path.write_text(
                    json.dumps(
                        {
                            "resources": [
                                {
                                    "type": "test",
                                    "name": "echo",
                                    "instances": [
                                        {
                                            "attributes": {"name": SECRET},
                                            "dependencies": [f"test.{SECRET}"],
                                        }
                                    ],
                                },
                                {
                                    "type": "test",
                                    "name": "credential",
                                    "instances": [credential],
                                },
                            ]
                        }
                    )
                )
                result = topology._parse_terraform_state_source(str(path))
                self.assertNotIn(SECRET, result.model_dump_json())
                payload = topology._build_payload_from_change_set(
                    change_set=result, source_type="terraform", source_ref=str(path)
                )
                public_result = topology._build_import_result(
                    source_type="terraform",
                    source_ref=str(path),
                    applied=True,
                    change_set=result,
                    before_payload=None,
                    after_payload=payload,
                    warnings=result.warnings,
                )
                self.assertNotIn(SECRET, public_result.model_dump_json())
                with patch.object(topology, "SessionLocal") as factory:
                    topology._persist_topology_payload(
                        payload,
                        project={"id": 1, "project_key": "synthetic"},
                        workspace=None,
                        source_type="terraform",
                    )
                    row = (
                        factory.return_value.__enter__.return_value.add.call_args.args[
                            0
                        ]
                    )
                    self.assertNotIn(SECRET, row.payload_json)

    def test_terraform_discarded_sensitive_field_blocks_echoed_graph_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.tfstate"
            path.write_text(
                json.dumps(
                    {
                        "resources": [
                            {"type": "test", "name": SECRET, "instances": []},
                            {
                                "type": "test",
                                "name": "credential",
                                "instances": [
                                    {
                                        "attributes": {"opaque": SECRET},
                                        "sensitive_attributes": [["opaque"]],
                                    }
                                ],
                            },
                        ]
                    }
                )
            )
            with self.assertRaises(topology.TopologyImportError) as caught:
                topology._parse_terraform_state_source(str(path))
        self.assertNotIn(SECRET, str(caught.exception))

    def test_kubernetes_discarded_selector_credential_blocks_identity_echo(
        self,
    ) -> None:
        items = [
            {"kind": "Deployment", "metadata": {"name": SECRET, "namespace": "test"}},
            {
                "kind": "Service",
                "metadata": {"name": "api", "namespace": "test"},
                "spec": {"selector": {"token": SECRET}},
            },
        ]
        with patch.object(
            topology,
            "_read_kubernetes_live_state",
            return_value=(json.dumps({"items": items}), []),
        ):
            with self.assertRaises(topology.TopologyImportError) as caught:
                topology._parse_kubernetes_live_state_source("context:test")
        self.assertNotIn(SECRET, str(caught.exception))

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
