"""Private host journal and bounded callback regression tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import time
import unittest

from infra_automation.runner.execution import (
    ExecutionJournal,
    ExecutionRunner,
    _Stop,
    scope_key,
)
from infra_automation.runner.protocol import TaskScope


def task_scope():
    return TaskScope(
        runner_id="runner",
        project_id="1",
        workspace_id="1",
        run_id="run",
        step_id="step",
        attempt=1,
        fence=1,
        coordinator_generation=1,
        authorization_epoch=1,
        restore_epoch=1,
        lease_deadline="2099-01-01T00:00:00Z",
        audience="runner-task-v1",
    )


class RunnerExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = ExecutionJournal(Path(self.temp.name) / "journal")

    def test_scope_renewal_does_not_change_attempt_identity(self):
        scope = task_scope()
        renewed = TaskScope.model_validate(
            scope.model_dump() | {"lease_deadline": "2099-01-02T00:00:00Z"}
        )
        self.assertEqual(scope_key(scope), scope_key(renewed))
        changed = TaskScope.model_validate(scope.model_dump() | {"fence": 2})
        self.assertNotEqual(scope_key(scope), scope_key(changed))

    def test_durable_cancel_wins_finalization_and_duplicate_denies(self):
        self.journal.begin(
            "a" * 64, "dw-isolated-" + "b" * 32, "sha256:" + "c" * 64, "d" * 32
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.journal.begin(
                "a" * 64, "dw-isolated-" + "e" * 32, "sha256:" + "c" * 64, "d" * 32
            )
        self.assertTrue(self.journal.request_cancel("a" * 64))
        self.assertEqual(
            self.journal.finish(
                "a" * 64,
                "succeeded",
                True,
                deadline=time.monotonic() + 5,
                lease=datetime.now(timezone.utc) + timedelta(seconds=5),
            ),
            "cancelled",
        )
        self.assertTrue(self.journal.cancelled("a" * 64))
        self.assertEqual(self.journal.pending(), [])

    def test_late_cancel_preserves_terminal_success(self):
        self.journal.begin(
            "a" * 64, "dw-isolated-" + "b" * 32, "sha256:" + "c" * 64, "d" * 32
        )
        self.assertEqual(
            self.journal.finish(
                "a" * 64,
                "succeeded",
                True,
                deadline=time.monotonic() + 5,
                lease=datetime.now(timezone.utc) + timedelta(seconds=5),
            ),
            "succeeded",
        )
        self.assertFalse(self.journal.request_cancel("a" * 64))
        with self.journal.connection() as db:
            self.assertEqual(
                db.execute("SELECT state,cancel_requested FROM executions").fetchone(),
                ("succeeded", 0),
            )

    def test_public_or_linked_journal_denied(self):
        root = Path(self.temp.name) / "public"
        root.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            ExecutionJournal(root)
        alias = Path(self.temp.name) / "alias"
        alias.symlink_to(self.journal.root)
        with self.assertRaises(OSError):
            ExecutionJournal(alias)

    def test_callback_deadline_does_not_wait_for_worker_shutdown(self):
        runner = ExecutionRunner.__new__(ExecutionRunner)
        release = Event()
        done = Event()

        def hanging():
            release.wait(2)
            done.set()
            return True

        started = time.monotonic()
        try:
            with self.assertRaises(_Stop):
                runner._call(
                    hanging,
                    time.monotonic() + 0.05,
                    datetime.now(timezone.utc) + timedelta(seconds=2),
                )
            self.assertLess(time.monotonic() - started, 0.5)
        finally:
            release.set()
            self.assertTrue(done.wait(1))

    def test_journal_connections_close_after_success_and_exception(self):
        self.journal.begin(
            "a" * 64, "dw-isolated-" + "b" * 32, "sha256:" + "c" * 64, "d" * 32
        )
        with self.journal.connection() as successful:
            self.assertEqual(
                successful.execute("SELECT count(*) FROM executions").fetchone()[0], 1
            )
        with self.assertRaises(sqlite3.ProgrammingError):
            successful.execute("SELECT 1")
        with self.assertRaises(RuntimeError):
            with self.journal.connection() as failed:
                failed.execute("UPDATE executions SET state='running'")
                raise RuntimeError("Synthetic rollback boundary")
        with self.assertRaises(sqlite3.ProgrammingError):
            failed.execute("SELECT 1")
        with self.journal.connection() as current:
            self.assertEqual(
                current.execute("SELECT state FROM executions").fetchone()[0],
                "preparing",
            )

    def test_poll_connections_close_without_waiting_for_garbage_collection(self):
        from unittest.mock import patch

        connect = sqlite3.connect
        retained = []

        def capture(*args, **kwargs):
            connection = connect(*args, **kwargs)
            retained.append(connection)
            return connection

        with patch(
            "infra_automation.runner.execution.sqlite3.connect", side_effect=capture
        ):
            for _ in range(50):
                self.assertFalse(self.journal.cancelled("a" * 64))
        self.assertEqual(len(retained), 50)
        # Keep strong references: closure must not depend on GC or interpreter exit.
        for connection in retained:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")


class BootstrapOutputTests(unittest.TestCase):
    def test_completed_writer_cannot_hide_output_overflow(self):
        import os
        import sys
        from infra_automation.runner.bootstrap import managed_command

        code = managed_command(
            [sys.executable, "-c", 'print("x"*4096)'],
            dict(os.environ),
            {"output_bytes": 128},
        )
        self.assertEqual(code, 126)


class OriginalDeadlineTests(unittest.TestCase):
    def test_delayed_setup_does_not_get_a_new_full_watchdog_budget(self):
        from infra_automation.runner import bootstrap

        origin = datetime(2026, 11, 4, tzinfo=timezone.utc)
        config = {
            "profile": {"timeout_seconds": 6},
            "lease_deadline": (origin + timedelta(seconds=60)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "execution_deadline": (origin + timedelta(seconds=6)).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "remaining_budget_seconds": 3.0,
        }
        result = bootstrap.watchdog_deadline(
            config,
            now_utc=origin + timedelta(seconds=3.8),
            monotonic_now=100.0,
            started_monotonic=99.8,
        )
        self.assertAlmostEqual(result, 102.2)
        with self.assertRaises(ValueError):
            bootstrap.watchdog_deadline(
                config,
                now_utc=origin + timedelta(seconds=6),
                monotonic_now=102.2,
                started_monotonic=99.8,
            )

    def test_remaining_budget_is_monotonic_cap_even_if_wall_clock_moves_back(self):
        from infra_automation.runner import bootstrap

        origin = datetime(2026, 11, 4, tzinfo=timezone.utc)
        config = {
            "profile": {"timeout_seconds": 6},
            "lease_deadline": (origin + timedelta(seconds=60)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "execution_deadline": (origin + timedelta(seconds=6)).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "remaining_budget_seconds": 3.0,
        }
        self.assertEqual(
            bootstrap.watchdog_deadline(
                config,
                now_utc=origin - timedelta(seconds=30),
                monotonic_now=102.5,
                started_monotonic=100,
            ),
            103.0,
        )
        for budget in (True, 0, -1, float("inf"), float("nan"), 7):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                bootstrap.watchdog_deadline(
                    config | {"remaining_budget_seconds": budget},
                    now_utc=origin,
                    monotonic_now=100,
                    started_monotonic=100,
                )

    def test_expired_callback_budget_never_invokes_credential_resolver(self):
        runner = ExecutionRunner.__new__(ExecutionRunner)
        calls = []
        with self.assertRaises(_Stop):
            runner._call(
                lambda: calls.append("called"),
                time.monotonic() - 1,
                datetime.now(timezone.utc) + timedelta(minutes=1),
            )
        self.assertEqual(calls, [])


class DeadlineReasonTests(unittest.TestCase):
    def test_execution_timeout_is_not_reported_as_lease_loss(self):
        runner = ExecutionRunner.__new__(ExecutionRunner)
        with self.assertRaises(_Stop) as caught:
            runner._call(
                lambda: True,
                time.monotonic() - 1,
                datetime.now(timezone.utc) + timedelta(seconds=30),
            )
        self.assertEqual(caught.exception.state, "timed_out")

    def test_timeout_during_final_authority_callback_keeps_original_reason(self):
        from unittest.mock import patch

        runner = ExecutionRunner.__new__(ExecutionRunner)
        observed = [100.0]

        def delayed():
            observed[0] = 102.0
            return True

        with (
            patch(
                "infra_automation.runner.execution.time.monotonic",
                side_effect=lambda: observed[0],
            ),
            self.assertRaises(_Stop) as caught,
        ):
            runner._call(
                delayed, 101.0, datetime.now(timezone.utc) + timedelta(seconds=30)
            )
        self.assertEqual(caught.exception.state, "timed_out")

    def test_timeout_while_waiting_for_callback_is_timed_out(self):
        runner = ExecutionRunner.__new__(ExecutionRunner)
        release = Event()
        done = Event()

        def delayed():
            release.wait(2)
            done.set()
            return True

        try:
            with self.assertRaises(_Stop) as caught:
                runner._call(
                    delayed,
                    time.monotonic() + 0.05,
                    datetime.now(timezone.utc) + timedelta(seconds=30),
                )
            self.assertEqual(caught.exception.state, "timed_out")
        finally:
            release.set()
            self.assertTrue(done.wait(1))

    def test_actual_expired_lease_remains_distinct(self):
        runner = ExecutionRunner.__new__(ExecutionRunner)
        with self.assertRaises(_Stop) as caught:
            runner._call(
                lambda: True,
                time.monotonic() + 30,
                datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        self.assertEqual(caught.exception.state, "lease_lost")
