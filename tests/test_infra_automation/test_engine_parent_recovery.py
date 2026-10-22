"""Actual coordinator death cannot leave analysis trees outside global capacity."""

from __future__ import annotations

from datetime import datetime, timezone
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra_automation.coordinator import Coordinator
from infra_automation.lifecycle import SnapshotDocument
from infra_automation.local_workers import (
    HandlerRegistration,
    HandlerRegistry,
    SpawnProcessWorkers,
)
from infra_automation.state import CancelRunRequest
from models.repositories import infra_automation_runs as repo
from services import infra_automation_engine_service as service
from services.infra_automation_support import digest
from tests.test_infra_automation import test_engine_coordinator as coordinator_tests
from tests.test_infra_automation.test_engine_cancellation import alive


def parent_recovery_tree(value):
    folder = Path(
        SnapshotDocument.model_validate_json(value.snapshot_bytes).inputs["note"]
    )
    (folder / ("worker." + str(os.getpid()))).write_text(str(os.getpid()))
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import os,signal,sys,time; from pathlib import Path; "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            'Path(sys.argv[1],"descendant."+str(os.getpid())).write_text(str(os.getpid())); '
            "time.sleep(90)",
            str(folder),
        ]
    )
    try:
        time.sleep(90)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def parent_recovery_registry():
    return HandlerRegistry(
        (
            HandlerRegistration(
                "synthetic",
                "1",
                "uploaded_intake",
                "screened_artifacts",
                True,
                parent_recovery_tree,
            ),
        )
    )


def crash_coordinator(database_url, marker_folder):
    engine = create_engine(database_url, connect_args={"timeout": 2})
    factory = sessionmaker(engine, expire_on_commit=False)
    workers = SpawnProcessWorkers(database_url)
    coordinator = Coordinator(factory, workers, registry=parent_recovery_registry())
    coordinator.tick()
    folder = Path(marker_folder)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if (
            len(list(folder.glob("worker.*"))) == 2
            and len(list(folder.glob("descendant.*"))) == 2
        ):
            (folder / "owner-exiting").write_text(str(time.monotonic()))
            os._exit(79)
        time.sleep(0.02)
    os._exit(80)


class ParentRecoveryTests(TestCase):
    def setUp(self):
        if os.name != "posix":
            self.skipTest("Qualified process-tree supervision is POSIX scoped")
        self.fixture = coordinator_tests.EngineCoordinatorRuntimeTests(
            "test_worker_saturation_keeps_active_run_waiting_without_attempt"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.folder = Path(self.fixture.temp.name) / "tree"
        self.folder.mkdir()
        doc = self.fixture.snapshot.snapshot
        self.fixture.request["snapshot"] = self.fixture.export(
            (doc.workflow_id, doc.revision_id), inputs={"note": str(self.folder)}
        )
        self.runs = []
        for index in range(2):
            with self.fixture.factory.begin() as db:
                self.runs.append(
                    repo.create_run(
                        db,
                        **{
                            **self.fixture.request,
                            "key_digest": digest(f"parent-recovery-{index}".encode()),
                        },
                    ).id
                )
        self.addCleanup(self.cleanup_groups)

    def cleanup_groups(self):
        # Only fresh groups created by this test; never a global PID marker folder.
        for marker in self.folder.glob("worker.*"):
            pid = int(marker.read_text())
            if alive(pid):
                try:
                    if os.getpgid(pid) == pid:
                        os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def wait_for(self, predicate, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.assertTrue(predicate(), "Owned process-tree state did not converge")

    def start_and_crash(self):
        process = multiprocessing.get_context("spawn").Process(
            target=crash_coordinator,
            args=(str(self.fixture.engine.url), str(self.folder)),
        )
        process.start()
        self.addCleanup(process.close)
        process.join(15)
        if process.is_alive():
            process.kill()
            process.join()
        self.assertEqual(process.exitcode, 79)
        self.assertEqual(len(list(self.folder.glob("worker.*"))), 2)
        self.assertEqual(len(list(self.folder.glob("descendant.*"))), 2)
        return float((self.folder / "owner-exiting").read_text())

    def marker_pids(self):
        return [
            int(p.read_text())
            for p in self.folder.iterdir()
            if p.name.startswith(("worker.", "descendant."))
        ]

    def test_coordinator_death_stops_both_actual_process_trees_within_five_seconds(
        self,
    ):
        exited_at = self.start_and_crash()
        pids = self.marker_pids()
        self.wait_for(
            lambda: not any(alive(pid) for pid in pids),
            max(0.1, 5 - (time.monotonic() - exited_at)),
        )
        self.assertLess(time.monotonic() - exited_at, 5)

    def test_successor_after_real_lease_expiry_obeys_global_bound_and_cancels(self):
        exited_at = self.start_and_crash()
        old = set(self.marker_pids())
        self.wait_for(
            lambda: not any(alive(pid) for pid in old),
            max(0.1, 5 - (time.monotonic() - exited_at)),
        )
        self.wait_for(lambda: time.monotonic() - exited_at >= 31, 32)
        workers = SpawnProcessWorkers(str(self.fixture.engine.url))
        coordinator = Coordinator(
            self.fixture.factory, workers, registry=parent_recovery_registry()
        )
        self.addCleanup(coordinator.close)

        def replacements_ready():
            coordinator.tick()
            return (
                len(list(self.folder.glob("worker.*"))) == 4
                and len(list(self.folder.glob("descendant.*"))) == 4
            )

        self.wait_for(replacements_ready, 12)
        self.assertEqual(len(workers.handles), 2)
        self.assertLessEqual(
            sum(alive(int(p.read_text())) for p in self.folder.glob("worker.*")), 2
        )
        self.assertFalse(any(alive(pid) for pid in old))
        started = time.monotonic()
        for run_id in self.runs:
            with self.fixture.factory() as db:
                current = repo.get_run(db, run_id)
            with self.fixture.credentials():
                service.cancel_run(
                    run_id,
                    CancelRunRequest(
                        expected_version=current.version,
                        reason="Synthetic successor cancellation",
                    ),
                    cancel_port=coordinator.cancel_run,
                    now=datetime.now(timezone.utc),
                )
        self.assertLess(time.monotonic() - started, 5)
        self.assertFalse(any(alive(pid) for pid in self.marker_pids()))
        self.assertEqual(workers.handles, ())
