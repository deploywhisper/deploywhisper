"""Spawned worker capacity and process-local immutable input contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest import TestCase

from infra_automation.local_workers import SpawnProcessWorkers, WorkerInput


class EngineWorkerContractTests(TestCase):
    def test_workers_reject_unbounded_or_network_database_profiles(self):
        for slots in (0, 3, True):
            with self.assertRaises(ValueError):
                SpawnProcessWorkers(
                    "sqlite:////tmp/unused-engine.db", max_workers=slots
                )
        for url in ("postgresql://example/db", "sqlite:///:memory:"):
            with self.assertRaises(ValueError):
                SpawnProcessWorkers(url)

    def test_input_bytes_and_prerequisites_are_frozen(self):
        value = WorkerInput(b"{}", "upload", ())
        with self.assertRaises(FrozenInstanceError):
            value.step_id = "other"
