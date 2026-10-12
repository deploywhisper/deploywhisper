"""Disposable file-backed SQLite qualification; no application persistence imports."""

from __future__ import annotations

import importlib
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest


PROTOTYPE = (
    Path(__file__).resolve().parents[1]
    / "fixtures/infra_automation/qualification/16_0/sqlite/prototype.py"
)
prototype = importlib.import_module(
    "tests.fixtures.infra_automation.qualification.16_0.sqlite.prototype"
)


class SQLiteQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "qualification.sqlite"
        self.store = prototype.Store(self.path)

    def test_independent_process_race_has_one_owner(self):
        results = prototype.race(self.path)
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.store.row()["attempt"], 1)
        self.assertEqual(len(self.store.attempts()), 1)

    def test_reclaim_fences_all_stale_mutations_and_generation(self):
        old = self.store.claim("old", 0, 1, 10)
        self.assertIsNotNone(old)
        self.assertIsNone(self.store.claim("early", 1, 1, 19))
        self.store.new_generation()
        for kind in ("heartbeat", "log", "upload", "complete"):
            self.assertFalse(self.store.mutate(old, kind, 15))
        new = self.store.claim("new", 1, 2, 21)
        self.assertEqual((new["attempt"], new["fence"]), (2, 2))
        for kind in ("heartbeat", "log", "upload", "complete"):
            self.assertFalse(self.store.mutate(old, kind, 22))
        self.assertTrue(self.store.mutate(new, "upload", 22))
        self.assertTrue(self.store.mutate(new, "complete", 22))

    def test_authority_and_restore_epochs_invalidate(self):
        for field in ("auth_epoch", "restore_epoch"):
            with self.subTest(field=field):
                path = Path(self.temp.name) / f"{field}.sqlite"
                store = prototype.Store(path)
                token = store.claim("runner", 0, 1, 10)
                store.revoke(field)
                for kind in ("heartbeat", "log", "upload", "complete"):
                    self.assertFalse(store.mutate(token, kind, 11))

    def test_completion_requires_committed_output(self):
        token = self.store.claim("runner", 0, 1, 10)
        self.assertFalse(self.store.mutate(token, "complete", 11))
        self.assertTrue(self.store.mutate(token, "upload", 11))
        self.assertTrue(self.store.mutate(token, "complete", 12))
        self.assertFalse(self.store.mutate(token, "log", 12))

    def test_crash_restart_boundaries(self):
        for point, state, outputs in (
            ("precommit", "queued", 0),
            ("postcommit", "running", 0),
            ("output-before-success", "running", 1),
        ):
            with self.subTest(point=point):
                path = Path(self.temp.name) / f"{point}.sqlite"
                prototype.Store(path)
                child = subprocess.run(
                    [sys.executable, str(PROTOTYPE), "crash", str(path), point],
                    check=False,
                    capture_output=True,
                )
                self.assertEqual(child.returncode, 73)
                restarted = prototype.Store(path)
                self.assertEqual(restarted.row()["state"], state)
                self.assertEqual(len(restarted.outputs()), outputs)
                if outputs:
                    token = restarted.row()
                    self.assertTrue(restarted.mutate(token, "complete", 11))
                    self.assertEqual(prototype.Store(path).row()["state"], "succeeded")

    def test_unknown_external_effect_retains_lock_and_never_retries(self):
        self.store.set_kind("external")
        token = self.store.claim("receiver", 0, 1, 10)
        self.assertTrue(self.store.recover(21))
        self.assertEqual(self.store.row()["state"], "delivery_unknown")
        self.assertEqual(self.store.row()["target_lock"], 1)
        self.assertIsNone(self.store.claim("retry", 2, 1, 22))
        self.assertFalse(self.store.mutate(token, "complete", 22))

    def test_local_idempotent_work_can_reclaim(self):
        self.store.claim("first", 0, 1, 10)
        token = self.store.claim("retry", 1, 1, 21)
        self.assertEqual(token["attempt"], 2)

    def test_wrong_scope_fences_version_and_expired_lease_deny(self):
        self.assertIsNone(self.store.claim("runner", 99, 1, 10))
        token = self.store.claim("runner", 0, 1, 10)
        for field in (
            "id",
            "owner",
            "attempt",
            "fence",
            "generation",
            "auth_epoch",
            "restore_epoch",
        ):
            wrong = dict(token)
            wrong[field] = "other" if field == "owner" else token[field] + 1
            for kind in ("heartbeat", "log", "upload", "complete"):
                self.assertFalse(self.store.mutate(wrong, kind, 11))
        for kind in ("heartbeat", "log", "upload", "complete"):
            self.assertFalse(self.store.mutate(token, kind, 20))

    def test_busy_retry_succeeds_inside_budget(self):
        connection = sqlite3.connect(self.path, timeout=0, check_same_thread=False)
        self.addCleanup(connection.close)
        connection.execute("BEGIN IMMEDIATE")
        release = threading.Timer(0.015, connection.rollback)
        release.start()
        self.addCleanup(release.join)
        self.assertIsNotNone(self.store.claim("retry", 0, 1, 10))
        self.assertGreaterEqual(self.store.busy_count, 1)

    def test_busy_is_bounded_and_retried_after_release(self):
        connection = sqlite3.connect(self.path, timeout=0)
        self.addCleanup(connection.close)
        connection.execute("BEGIN IMMEDIATE")
        with self.assertRaises(prototype.Busy):
            self.store.claim("busy", 0, 1, 10)
        self.assertEqual(self.store.busy_count, 4)
        connection.rollback()
        self.assertIsNotNone(self.store.claim("released", 0, 1, 10))

    def test_unique_constraints_reject_duplicate_attempt_and_fence(self):
        self.store.claim("first", 0, 1, 10)
        connection = sqlite3.connect(self.path)
        self.addCleanup(connection.close)
        for values in ((1, 2), (2, 1)):
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO attempts VALUES (1, ?, ?)", values)
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
