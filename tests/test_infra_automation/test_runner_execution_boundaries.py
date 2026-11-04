"""Unit lifetime boundaries with real pipes/SQLite, never isolation qualification."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from infra_automation.runner import execution
from infra_automation.runner.catalog import CatalogDocument
from infra_automation.runner.execution import (
    ExecutionJournal,
    ExecutionRunner,
    scope_key,
)
from infra_automation.runner.execution_profile import ExecutionProfile, IsolationError
from infra_automation.runner.protocol import TaskScope
from infra_automation.runner.sandbox import DockerSandbox
from infra_automation.runner.source import SourceSnapshot


class _PipeSandbox:
    """Substitute containment only: execute a harmless bounded Python protocol peer."""

    def __init__(self, hook, echo_mode=None, capture_config=False):
        self.profile = ExecutionProfile(
            image_id="sha256:" + "a" * 64,
            credential_names=("COLLECTOR_TOKEN",) if echo_mode else (),
        )
        self.echo_mode = echo_mode
        self.capture_config = capture_config
        self.hook = hook
        self.created = False
        self.finished_wait = False
        self.starts = 0

    def reserve(self):
        return "dw-isolated-" + uuid.uuid4().hex

    def reservation_nonce(self, name):
        return "c" * 32

    def owned_id(self, name):
        return "d" * 64

    def pending_creation(self, name):
        return False

    def preflight(self):
        pass

    def create(self, source, *, name, task_digest):
        self.hook("create")
        self.created = True
        return name

    def start(self, name):
        self.starts += 1
        program = (
            "import json, sys, time; config=json.loads(sys.stdin.readline()); "
            'print("DW_RUNNER_READY_V1", flush=True); '
            "credentials=json.loads(sys.stdin.readline()); "
        )
        if self.echo_mode:
            program += 'value=credentials["COLLECTOR_TOKEN"]; '
            if self.echo_mode in ("percent", "nested_percent", "split_percent"):
                program += 'value="".join("%%%02x" % ord(c) for c in value); '
            if self.echo_mode == "nested_percent":
                program += 'value=value.replace("%", "%25"); '
            if self.echo_mode.startswith("split"):
                program += (
                    "cut=len(value)//2; sys.stdout.write(value[:cut]); "
                    "sys.stdout.flush(); time.sleep(0.1); "
                    "sys.stdout.write(value[cut:]); sys.stdout.flush()"
                )
            else:
                program += "print(value, flush=True)"
        elif self.capture_config:
            program += "print(json.dumps(config), flush=True)"
        else:
            program += 'print("safe fixture output", flush=True)'
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-c",
                program,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        original_wait = process.wait

        def waited(*args, **kwargs):
            result = original_wait(*args, **kwargs)
            self.finished_wait = True
            return result

        process.wait = waited
        return process

    def inspect(self, name):
        self.hook("inspect")
        return {"State": {"Running": False, "OOMKilled": False}}

    def owns(self, name):
        return self.created

    def exists(self, name):
        return self.created

    def remove(self, name):
        self.hook("remove")
        self.created = False


class RunnerExecutionBoundaryTests(unittest.TestCase):
    @contextmanager
    def fixture(
        self, boundary=None, effect=None, *, echo_mode=None, capture_config=False
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            observed = {"offset": 0, "fired": False}
            wall = datetime.now(timezone.utc)
            scope = TaskScope(
                runner_id="runner-fixture",
                project_id="1",
                workspace_id="1",
                run_id="run-fixture",
                step_id="collect",
                attempt=1,
                fence=1,
                coordinator_generation=1,
                authorization_epoch=1,
                restore_epoch=1,
                lease_deadline=(wall + timedelta(seconds=60)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                audience="runner-task-v1",
            )
            renewed = scope.model_copy(
                update={
                    "lease_deadline": (wall + timedelta(seconds=120)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                }
            )

            def hook(point):
                if point == boundary and not observed["fired"]:
                    observed["fired"] = True
                    if effect == "cancel":
                        runner.cancel(scope)
                    elif effect == "renewed_cancel":
                        runner.cancel(renewed)
                    elif effect == "setup":
                        observed["offset"] = 10
                    else:
                        observed["offset"] = 120

            sandbox = _PipeSandbox(hook, echo_mode, capture_config)
            catalog = CatalogDocument(
                image_id=sandbox.profile.image_id,
                files=tuple(
                    {"path": path, "sha256": "sha256:" + "b" * 64, "kind": "probe"}
                    for path in (
                        "/usr/local/bin/python",
                        "/opt/deploywhisper/bootstrap.py",
                        "/opt/deploywhisper/probe.py",
                    )
                ),
            )
            catalog_path = root / "catalog.json"
            raw = catalog.model_dump_json().encode()
            catalog_path.write_bytes(raw)
            catalog_path.chmod(0o600)
            runner = ExecutionRunner(
                sandbox,
                catalog_path,
                "sha256:" + hashlib.sha256(raw).hexdigest(),
                root / "journal",
            )
            # Source admission and containment have separate real qualification.
            # This suite isolates host lifetime using an inert source object.
            snapshot = SourceSnapshot(
                root, "0" * 40, "sha256:" + "b" * 64, (), 0, 0, None, "unit-only"
            )
            real_redact = execution.redact_text
            real_monotonic = execution.time.monotonic

            def redact(*args, **kwargs):
                result = real_redact(*args, **kwargs)
                hook("redaction")
                return result

            def authority():
                if sandbox.finished_wait:
                    hook("authority")
                return True

            class Clock(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime.now(tz) + timedelta(
                        seconds=observed["offset"]
                        if effect in ("lease", "setup")
                        else 0
                    )

            def run(selected=scope, **kwargs):
                return runner.execute(
                    selected,
                    "qualification_probe",
                    {"mode": "success"},
                    snapshot,
                    expected_profile_digest=runner.profile_digest,
                    authority_check=authority,
                    **kwargs,
                )

            with (
                patch.object(SourceSnapshot, "verify", lambda self: None),
                patch.object(execution, "redact_text", redact),
                patch.object(execution, "datetime", Clock),
                patch.object(
                    execution,
                    "time",
                    SimpleNamespace(
                        monotonic=lambda: (
                            real_monotonic()
                            + (
                                observed["offset"]
                                if effect in ("timeout", "setup")
                                else 0
                            )
                        )
                    ),
                ),
            ):
                yield SimpleNamespace(
                    run=run,
                    runner=runner,
                    sandbox=sandbox,
                    scope=scope,
                    renewed=renewed,
                    observed=observed,
                    wall=wall,
                )

    def test_delayed_setup_frame_preserves_original_execution_budget(self):
        with self.fixture("create", "setup", capture_config=True) as case:
            result = case.run()
            self.assertTrue(result.finalizable)
            self.assertTrue(case.observed["fired"])
            frame = json.loads(result.output)
            self.assertLessEqual(frame["remaining_budget_seconds"], 50)
            self.assertGreater(frame["remaining_budget_seconds"], 40)
            execution_deadline = datetime.fromisoformat(
                frame["execution_deadline"].replace("Z", "+00:00")
            )
            self.assertLessEqual(execution_deadline, case.wall + timedelta(seconds=60))
            self.assertEqual(frame["lease_deadline"], case.scope.lease_deadline)

    def test_collector_credential_echo_is_rejected_without_retention(self):
        # These are supported bounded redactor variants, not arbitrary encoding.
        secret = "fixturecollectorvalue-3f74a91c"
        for mode in ("raw", "percent", "nested_percent", "split", "split_percent"):
            with self.subTest(mode=mode), self.fixture(echo_mode=mode) as case:
                result = case.run(
                    credential_resolver=lambda: execution.CollectorCredentials(
                        "qualification-collector", {"COLLECTOR_TOKEN": secret}
                    )
                )
                self.assertEqual(result.state, "output_rejected")
                self.assertFalse(result.finalizable)
                self.assertEqual(result.output, "")
                self.assertIsNone(result.output_digest)
                self.assertTrue(result.cleanup_complete)
                percent = "".join("%%%02x" % ord(char) for char in secret)
                for path in case.runner.journal.root.iterdir():
                    if path.is_file():
                        retained = path.read_bytes()
                        for value in (secret, percent, percent.replace("%", "%25")):
                            self.assertFalse(
                                value.encode() in retained,
                                "Collector credential must not enter journal storage.",
                            )

    def test_cancellation_wins_at_every_finalization_boundary(self):
        for boundary in ("authority", "inspect", "redaction", "remove"):
            with (
                self.subTest(boundary=boundary),
                self.fixture(boundary, "cancel") as case,
            ):
                result = case.run()
                self.assertTrue(case.observed["fired"])
                self.assertFalse(result.finalizable)
                self.assertEqual(result.output, "")
                self.assertIsNone(result.output_digest)
                self.assertTrue(result.cleanup_complete)
                self.assertTrue(case.runner.journal.cancelled(scope_key(case.scope)))

    def test_lease_and_timeout_expiry_cannot_finalize_output(self):
        for boundary in ("inspect", "redaction", "remove"):
            for effect in ("lease", "timeout"):
                with (
                    self.subTest(boundary=boundary, effect=effect),
                    self.fixture(boundary, effect) as case,
                ):
                    result = case.run()
                    self.assertTrue(case.observed["fired"])
                    self.assertFalse(result.finalizable)
                    self.assertEqual(result.output, "")
                    self.assertIsNone(result.output_digest)
                    self.assertTrue(result.cleanup_complete)

    def test_renewed_lease_cancellation_targets_original_execution(self):
        with self.fixture("remove", "renewed_cancel") as case:
            self.assertEqual(scope_key(case.scope), scope_key(case.renewed))
            result = case.run()
            self.assertFalse(result.finalizable)
            self.assertTrue(case.runner.journal.cancelled(scope_key(case.scope)))

    def test_same_attempt_cannot_launch_again_with_renewed_lease(self):
        with self.fixture() as case:
            first = case.run()
            self.assertTrue(first.finalizable)
            with self.assertRaises(IsolationError):
                case.run(case.renewed)
            self.assertEqual(case.sandbox.starts, 1)
            self.assertFalse(case.runner.cancel(case.renewed))
            with case.runner.journal.connection() as db:
                row = db.execute(
                    "SELECT state,cancel_requested,cleanup_complete FROM executions"
                ).fetchone()
            self.assertEqual(row, ("succeeded", 0, 1))

    def test_cancelled_journal_cannot_be_finished_as_success(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ExecutionJournal(Path(root).resolve())
            journal.begin("task", "container", "profile", "c" * 32)
            self.assertTrue(journal.request_cancel("task"))
            self.assertEqual(
                journal.finish(
                    "task",
                    "succeeded",
                    True,
                    deadline=execution.time.monotonic() + 60,
                    lease=datetime.now(timezone.utc) + timedelta(seconds=60),
                ),
                "cancelled",
            )
            with journal.connection() as db:
                row = db.execute(
                    "SELECT state,cancel_requested,cleanup_complete FROM executions"
                ).fetchone()
            self.assertEqual(row, ("cancelled", 1, 1))

    def test_finish_rechecks_deadlines_after_waiting_for_sqlite_writer(self):
        for effect in ("lease", "timeout"):
            with self.subTest(effect=effect), self.fixture(effect=effect) as case:
                journal = case.runner.journal
                original_finish = journal.finish
                original_connection = journal.connection
                attempted = threading.Event()
                released = threading.Event()

                @contextmanager
                def traced_connection():
                    with original_connection() as db:
                        db.set_trace_callback(
                            lambda sql: (
                                attempted.set() if sql == "BEGIN IMMEDIATE" else None
                            )
                        )
                        yield db

                def delayed_finish(*args, **kwargs):
                    blocker = sqlite3.connect(journal.path, check_same_thread=False)
                    blocker.execute("BEGIN IMMEDIATE")

                    def release():
                        try:
                            if attempted.wait(2):
                                case.observed["offset"] = 120
                                released.set()
                        finally:
                            blocker.rollback()
                            blocker.close()

                    thread = threading.Thread(target=release)
                    thread.start()
                    try:
                        return original_finish(*args, **kwargs)
                    finally:
                        thread.join(timeout=3)
                        self.assertFalse(thread.is_alive())

                with (
                    patch.object(journal, "connection", traced_connection),
                    patch.object(journal, "finish", delayed_finish),
                ):
                    result = case.run()
                self.assertTrue(
                    released.is_set(), "Real SQLite contention was exercised."
                )
                self.assertEqual(
                    result.state, "lease_lost" if effect == "lease" else "timed_out"
                )
                self.assertFalse(result.finalizable)
                self.assertEqual(result.output, "")
                self.assertIsNone(result.output_digest)
                self.assertTrue(result.cleanup_complete)


class RunnerContainerOwnershipTests(unittest.TestCase):
    def test_failed_create_must_not_remove_preexisting_name(self):
        sandbox = object.__new__(DockerSandbox)
        sandbox.profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
        sandbox._owned = {}
        sandbox._reservations = {}
        sandbox._attempted = set()
        removed = []
        name = sandbox.reserve("dw-isolated-" + "a" * 32)
        row = {
            "Id": "f" * 64,
            "Image": sandbox.profile.image_id,
            "Config": {"Labels": {}},
            "State": {"Running": True},
        }

        def control(*args, **kwargs):
            if args[0] == "create":
                raise IsolationError()
            if args[0] == "ps":
                return name.encode() if not removed else b""
            if args[0] == "inspect":
                return json.dumps([row]).encode()
            if args[0] == "rm":
                removed.append(args[-1])
                return b""
            raise AssertionError(args)

        sandbox.control = control
        sandbox.preflight = lambda: None
        with tempfile.TemporaryDirectory() as root, self.assertRaises(IsolationError):
            sandbox.create(Path(root).resolve(), name=name, task_digest="b" * 64)
        self.assertEqual(removed, [], "Name collision must not authorize cleanup.")

    def test_ambiguous_create_cleanup_requires_matching_nonce_and_task(self):
        for matching in (True, False):
            with self.subTest(matching=matching):
                sandbox = object.__new__(DockerSandbox)
                sandbox.profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
                sandbox._owned = {}
                sandbox._reservations = {}
                sandbox._attempted = set()
                sandbox.preflight = lambda: None
                name = sandbox.reserve("dw-isolated-" + "d" * 32)
                identifier = "e" * 64
                retained = {}
                removed = []

                def control(*args, **kwargs):
                    if args[0] == "create":
                        labels = dict(
                            args[index + 1].split("=", 1)
                            for index, item in enumerate(args)
                            if item == "--label"
                        )
                        if not matching:
                            labels["deploywhisper.owner"] = "0" * 32
                        retained["row"] = {
                            "Id": identifier,
                            "Name": "/" + name,
                            "Image": sandbox.profile.image_id,
                            "Config": {"Labels": labels},
                            "State": {"Running": False},
                        }
                        # Daemon accepted creation, but the CLI reply was lost.
                        raise IsolationError()
                    if args[0] == "inspect":
                        return json.dumps([retained["row"]]).encode()
                    if args[0] == "ps":
                        return identifier.encode() if retained else b""
                    if args[0] == "rm":
                        removed.append(args[-1])
                        retained.clear()
                        return b""
                    raise AssertionError(args)

                sandbox.control = control
                with (
                    tempfile.TemporaryDirectory() as root,
                    self.assertRaises(IsolationError),
                ):
                    sandbox.create(
                        Path(root).resolve(), name=name, task_digest="b" * 64
                    )
                self.assertEqual(removed, [identifier] if matching else [])
                self.assertFalse(sandbox.owns(name))

    def test_recovery_keeps_uncertain_owned_containers_pending(self):
        for scenario in (
            "changed_image",
            "daemon_unavailable",
            "absent",
            "foreign_nonce",
        ):
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory() as temporary,
            ):
                sandbox = object.__new__(DockerSandbox)
                sandbox.profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
                sandbox._owned = {}
                sandbox._reservations = {}
                sandbox._attempted = set()
                name, key, nonce = "dw-isolated-" + "a" * 32, "b" * 64, "c" * 32
                calls = []
                row = {
                    "Id": "d" * 64,
                    "Name": "/" + name,
                    "Image": "sha256:"
                    + ("e" if scenario == "changed_image" else "a") * 64,
                    "Config": {
                        "Labels": {
                            "deploywhisper.owner": "f" * 32
                            if scenario == "foreign_nonce"
                            else nonce,
                            "deploywhisper.task": key,
                        }
                    },
                    "State": {"Running": True},
                }

                def control(*args, **kwargs):
                    calls.append(args)
                    if scenario == "daemon_unavailable":
                        raise IsolationError()
                    if args[0] == "inspect":
                        if scenario == "absent":
                            raise IsolationError()
                        return json.dumps([row]).encode()
                    if args[0] == "ps" and scenario == "absent":
                        return b""
                    raise AssertionError(args)

                sandbox.control = control
                runner = ExecutionRunner(
                    sandbox, "/unused", "sha256:" + "0" * 64, Path(temporary).resolve()
                )
                runner.journal.begin(key, name, "retained-profile", nonce)
                result = runner.recover_pending()
                expected_clean = False
                self.assertEqual(result[0]["cleanup_complete"], expected_clean)
                self.assertEqual(bool(runner.journal.pending()), not expected_clean)
                self.assertFalse(any(call[0] in ("kill", "rm") for call in calls))

    def test_empty_lookup_preserves_nonce_until_late_creation_can_be_removed(self):
        profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
        name, key, identifier = "dw-isolated-" + "a" * 32, "b" * 64, "d" * 64
        state = {"row": None, "labels": None}
        removed = []

        def control(*args, **kwargs):
            if args[0] == "create":
                state["labels"] = dict(
                    args[index + 1].split("=", 1)
                    for index, item in enumerate(args)
                    if item == "--label"
                )
                raise IsolationError()
            if args[0] == "inspect":
                if state["row"] is None:
                    raise IsolationError()
                return json.dumps([state["row"]]).encode()
            if args[0] == "ps":
                return identifier.encode() if state["row"] is not None else b""
            if args[0] == "rm":
                removed.append(args[-1])
                state["row"] = None
                return b""
            raise AssertionError(args)

        def host_port():
            sandbox = object.__new__(DockerSandbox)
            sandbox.profile = profile
            sandbox._owned, sandbox._reservations, sandbox._attempted = {}, {}, set()
            sandbox.preflight = lambda: None
            sandbox.control = control
            return sandbox

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sandbox = host_port()
            sandbox.reserve(name)
            nonce = sandbox.reservation_nonce(name)
            runner = ExecutionRunner(
                sandbox, "/unused", "sha256:" + "0" * 64, root / "journal"
            )
            runner.journal.begin(key, name, "retained-profile", nonce)
            with self.assertRaises(IsolationError):
                sandbox.create(root, name=name, task_digest=key)
            self.assertTrue(sandbox.pending_creation(name))
            # A fresh host port has only the durable journal; an empty query is
            # still insufficient to resolve an outstanding create operation.
            runner.sandbox = host_port()
            self.assertFalse(runner.recover_pending()[0]["cleanup_complete"])
            self.assertEqual(len(runner.journal.pending()), 1)
            state["row"] = {
                "Id": identifier,
                "Name": "/" + name,
                "Image": profile.image_id,
                "Config": {"Labels": state["labels"]},
                "State": {"Running": False},
            }
            self.assertTrue(runner.recover_pending()[0]["cleanup_complete"])
            self.assertEqual(runner.journal.pending(), [])
            self.assertEqual(removed, [identifier])

    def test_acknowledged_container_absence_is_safe_to_finish(self):
        sandbox = object.__new__(DockerSandbox)
        sandbox.profile = ExecutionProfile(image_id="sha256:" + "a" * 64)
        sandbox._owned, sandbox._reservations, sandbox._attempted = {}, {}, set()
        calls = []

        def control(*args, **kwargs):
            calls.append(args)
            if args[0] == "inspect":
                raise IsolationError()
            if args[0] == "ps":
                return b""
            raise AssertionError(args)

        sandbox.control = control
        with tempfile.TemporaryDirectory() as temporary:
            runner = ExecutionRunner(
                sandbox, "/unused", "sha256:" + "0" * 64, Path(temporary).resolve()
            )
            key, name, nonce, reference = (
                "b" * 64,
                "dw-isolated-" + "a" * 32,
                "c" * 32,
                "d" * 64,
            )
            runner.journal.begin(key, name, "retained-profile", nonce)
            runner.journal.acknowledge_creation(key, reference)
            self.assertEqual(runner.journal.creation_reference(key), reference)
            self.assertTrue(runner.recover_pending()[0]["cleanup_complete"])
            self.assertEqual(runner.journal.pending(), [])
            self.assertFalse(any(call[0] in ("kill", "rm") for call in calls))
