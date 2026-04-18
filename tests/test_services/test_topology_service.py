"""Tests for topology loading and warning behavior."""

from __future__ import annotations

import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from services.topology_service import (
    get_topology_status,
    load_topology,
    save_topology_definition,
)


class TopologyServiceTests(unittest.TestCase):
    def test_load_topology_warns_when_missing(self) -> None:
        fake_settings = SimpleNamespace(topology_path="missing-topology.json")
        with patch("services.topology_service.settings", fake_settings):
            topology, warning = load_topology()
        self.assertIsNone(topology)
        self.assertIn("not configured", warning)

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
