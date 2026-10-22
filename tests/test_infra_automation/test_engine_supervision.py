"""Process-independent admission and parent-death supervision."""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest import TestCase
from unittest.mock import Mock, patch

from infra_automation.worker_supervision import (
    _group_executing,
    _stop_worker,
    global_slot_available,
    supervisor_main,
)


def waiting_worker(marker, result, ready, gate):
    os.setsid()
    ready.send_bytes(b"ready")
    ready.close()
    try:
        if gate.recv_bytes() != b"start":
            return
    except EOFError:
        return
    finally:
        gate.close()
    Path(marker).write_text(str(os.getpid()))
    while True:
        time.sleep(0.1)


def descendant_worker(marker, result, ready, gate):
    os.setsid()
    ready.send_bytes(b"ready")
    ready.close()
    try:
        if gate.recv_bytes() != b"start":
            return
    except EOFError:
        return
    finally:
        gate.close()
    descendant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(90)"])
    Path(marker).write_text(f"{os.getpid()} {descendant.pid}")
    # Exiting with a live descendant must not release its global analysis slot.


class WorkerSupervisionTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "engine.db"
        self.database.touch()
        self.url = "sqlite:///" + str(self.database)
        self.context = multiprocessing.get_context("spawn")

    def launch(self, suffix="worker", target=waiting_worker, max_slots=1):
        result_rx, result_tx = self.context.Pipe(duplex=False)
        life_rx, life_tx = self.context.Pipe(duplex=False)
        marker = Path(self.directory.name) / suffix
        process = self.context.Process(
            target=supervisor_main,
            args=(
                self.url,
                suffix,
                target,
                (str(marker), result_tx),
                life_rx,
                result_tx,
                max_slots,
            ),
        )
        process.start()
        life_rx.close()
        result_tx.close()
        self.addCleanup(result_rx.close)
        self.addCleanup(life_tx.close)
        self.addCleanup(self.cleanup_process, process, life_tx)
        deadline = time.monotonic() + 8
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(marker.exists(), "Worker did not pass its execution gate")
        return process, life_tx, int(marker.read_text().split()[0])

    @staticmethod
    def cleanup_process(process, life):
        life.close()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(2)

    def test_parent_eof_stops_execution_before_releasing_global_slot(self):
        process, life, pid = self.launch()
        self.assertFalse(global_slot_available(self.url, 1))
        started = time.monotonic()
        life.close()
        process.join(4)
        self.assertEqual(process.exitcode, 0)
        self.assertLess(time.monotonic() - started, 4)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertTrue(global_slot_available(self.url, 1))

    def test_supervisor_crash_leaves_slot_unavailable(self):
        process, life, pid = self.launch()
        process.kill()
        process.join(2)
        self.assertFalse(global_slot_available(self.url, 1))
        os.killpg(pid, signal.SIGKILL)
        # Dirty metadata stays fail closed even after the orphan is killed.
        self.assertFalse(global_slot_available(self.url, 1))

    def test_symlink_database_uses_the_same_slots(self):
        process, life, _pid = self.launch()
        alias = Path(self.directory.name) / "alias.db"
        alias.symlink_to(self.database)
        self.assertFalse(global_slot_available("sqlite:///" + str(alias), 1))
        life.close()
        process.join(4)
        self.assertEqual(process.exitcode, 0)

    def test_worker_exit_cleans_its_surviving_descendant_before_slot_reuse(self):
        process, _life, pgid = self.launch(target=descendant_worker)
        process.join(4)
        self.assertEqual(process.exitcode, 0)
        self.assertFalse(_group_executing(pgid))
        self.assertTrue(global_slot_available(self.url, 1))

    def test_reduced_bound_accounts_for_both_physical_slots(self):
        first, first_life, _first_pid = self.launch("first", max_slots=2)
        second, second_life, _second_pid = self.launch("second", max_slots=2)
        first_life.close()
        first.join(4)
        self.assertEqual(first.exitcode, 0)
        self.assertFalse(global_slot_available(self.url, 1))
        second_life.close()
        second.join(4)
        self.assertEqual(second.exitcode, 0)
        self.assertTrue(global_slot_available(self.url, 1))

    def test_parent_gone_before_start_never_opens_worker_gate(self):
        result_rx, result_tx = self.context.Pipe(duplex=False)
        life_rx, life_tx = self.context.Pipe(duplex=False)
        marker = Path(self.directory.name) / "never-started"
        process = self.context.Process(
            target=supervisor_main,
            args=(
                self.url,
                "not-started",
                waiting_worker,
                (str(marker), result_tx),
                life_rx,
                result_tx,
                1,
            ),
        )
        life_tx.close()
        process.start()
        life_rx.close()
        result_tx.close()
        process.join(4)
        self.assertEqual(process.exitcode, 0)
        self.assertFalse(marker.exists())
        self.assertTrue(global_slot_available(self.url, 1))
        result_rx.close()

    def test_corrupt_metadata_is_capacity_not_a_reason_to_signal(self):
        self.assertTrue(global_slot_available(self.url, 1))
        directory = self.database.parent / (
            "." + self.database.name + ".engine-worker-slots"
        )
        (directory / "0").write_bytes(b"partial dirty record")
        self.assertFalse(global_slot_available(self.url, 1))
        self.assertTrue(global_slot_available(self.url, 2))

    def test_already_exited_group_is_confirmed_without_signalling_zombies(self):
        process = Mock(pid=12345)
        process.exitcode = 0
        with (
            patch("infra_automation.worker_supervision.os.getpgid", return_value=12345),
            patch(
                "infra_automation.worker_supervision.wait",
                return_value=[process.sentinel],
            ),
            patch(
                "infra_automation.worker_supervision._group_executing",
                return_value=False,
            ),
            patch(
                "infra_automation.worker_supervision.os.killpg",
                side_effect=PermissionError,
            ) as send,
        ):
            _stop_worker(process, True)
        send.assert_not_called()
        process.join.assert_called_once()

    def test_unsupported_file_locking_is_inert_before_touching_storage(self):
        with (
            patch("infra_automation.worker_supervision.fcntl", None),
            patch("infra_automation.worker_supervision._slot_directory") as directory,
        ):
            self.assertFalse(global_slot_available(self.url, 2))
        directory.assert_not_called()
