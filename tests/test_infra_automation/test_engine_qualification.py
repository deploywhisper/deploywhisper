"""The qualification harness measures guarded durable operations and typed slots."""

from __future__ import annotations

import json
import tempfile
import unittest

from sqlalchemy import text

from tests.fixtures.infra_automation.engine_v1 import qualification as harness


class EngineQualificationTests(unittest.TestCase):
    def test_slots_require_registered_monotonic_typed_heartbeats(self):
        port = harness.SyntheticSlotPort()
        self.assertEqual(port.exercise(1, 10), 20)
        self.assertEqual(port.heartbeat_calls, 20)
        self.assertEqual(len(port.read_online(16)), 0)
        with self.assertRaises(ValueError):
            port.heartbeat(harness.SlotHeartbeat("unknown", 2, 11))
        with self.assertRaises(ValueError):
            port.heartbeat(harness.SlotHeartbeat("synthetic-slot-0", 1, 11))
        with self.assertRaises(ValueError):
            port.heartbeat({"slot_id": "synthetic-slot-0"})

    def test_real_migrated_fixture_has_sql_guards_and_durable_profile(self):
        fixture = harness.make_fixture()
        self.addCleanup(fixture.doCleanups)
        with fixture.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar(),
                "032_add_infra_automation_engine",
            )
        profile = harness.environment(fixture.engine)
        self.assertEqual(profile["pragmas"]["journal_mode"], "wal")
        self.assertEqual(profile["pragmas"]["synchronous"], 2)
        self.assertIn(
            "infra_engine_output_immutable", profile["installed_sqlite_guards"]
        )

    def test_edge_preconditions_keep_version_guards_enabled(self):
        for kind, old, target in (
            ("run_edge", "running", "succeeded"),
            ("attempt_edge", "running", "succeeded"),
        ):
            fixture = harness.make_fixture()
            try:
                case = harness.prepare_fault(fixture, kind, old, target)
                before = harness.dump_factory(fixture.factory)
                with fixture.factory() as session:
                    self.assertIsNotNone(harness.fault_operation(session, case))
                    session.rollback()
                self.assertEqual(harness.dump_factory(fixture.factory), before)
            finally:
                fixture.doCleanups()

    def test_child_exit_smoke_compares_exact_restart_rows_and_audit(self):
        with tempfile.TemporaryDirectory() as output:
            result = harness.run_faults(output, smoke=True)
            self.assertEqual(result["count"], 2)
            self.assertFalse(result["acceptance_qualified"])
            self.assertTrue(result["source_hashes_identical"])
            for case in result["cases"]:
                self.assertEqual(case["exitcode"], harness.EXIT_CODE)
                self.assertTrue(case["exact_restart_state_and_audit"])
            self.assertEqual(
                json.loads((harness.Path(output) / "faults.json").read_text())["count"],
                2,
            )

    def test_freeze_hashes_include_contract_and_fixture_helpers(self):
        hashes = harness.source_hashes()
        for path in (
            "tests/fixtures/infra_automation/engine_v1/contract.json",
            "tests/test_infra_automation/lifecycle_support.py",
            "tests/test_infra_automation/test_engine_repository.py",
        ):
            self.assertIn(path, hashes)
