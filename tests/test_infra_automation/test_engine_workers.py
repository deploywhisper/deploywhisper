"""Spawned worker capacity and process-local immutable input contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest import TestCase
from unittest.mock import patch

from infra_automation.local_workers import SpawnProcessWorkers, WorkerInput
from infra_automation.state import EngineBounds


class EngineWorkerContractTests(TestCase):
    def test_implicit_worker_slots_follow_dynamic_server_reduction(self):
        with patch(
            "config.engine_bounds", return_value=EngineBounds(analysis_workers=1)
        ):
            workers = SpawnProcessWorkers("sqlite:////tmp/unused-engine.db")
        self.addCleanup(workers.close)
        self.assertEqual(workers.max_workers, 1)
        self.assertEqual(workers.bounds.analysis_workers, 1)

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
