"""Reproducible synthetic engine qualification; standard library plus runtime deps.

Run from the repository root with ``python -m
 tests.fixtures.infra_automation.engine_v1.qualification --mode capacity --output DIR``.
The capacity horizon uses real monotonic elapsed time. No receiver or real runner
support, host power-loss durability, or uploaded-analysis integration is claimed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import resource
import sqlite3
import sys
import time
from unittest.mock import patch

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

import config
from infra_automation import claims
from infra_automation.coordinator import Coordinator
from infra_automation.contracts import STEP_CONTRACTS
from infra_automation.lifecycle import LifecycleError
from infra_automation.local_workers import (
    HandlerRegistration,
    HandlerRegistry,
    SpawnProcessWorkers,
)
from infra_automation.state import (
    AuditActor,
    LogChunk,
    OutputReference,
    RunRequest,
    WorkerResult,
)
from infra_automation.storage import configure_engine_sqlite, ensure_capacity
from models.repositories import infra_automation_runs as repo
from models.tables import InfraAutomationAttempt, InfraAutomationRun
from services import infra_automation_engine_service as service
from services import infra_automation_support as support
from services import project_service as auth
from tests.test_infra_automation.test_engine_claims import EngineClaimsTests
from tests.test_infra_automation.lifecycle_support import LifecycleCase

ROOT = Path(__file__).resolve().parents[4]
CONTRACT = json.loads(Path(__file__).with_name("contract.json").read_text())
EXIT_CODE = 79


def utc_now():
    return datetime.now(timezone.utc)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def source_hashes():
    paths = {ROOT / "config.py", Path(__file__)}
    paths.add(Path(__file__).with_name("contract.json"))
    paths.update((ROOT / "tests/test_infra_automation").glob("*.py"))
    for folder in ("infra_automation", "models", "services", "migrations"):
        paths.update((ROOT / folder).rglob("*.py"))
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def file_bytes(path):
    try:
        return Path(path).stat().st_size
    except FileNotFoundError:
        return 0


def resource_sample():
    value = {
        "self_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "children_maxrss": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "maxrss_units": "bytes" if sys.platform == "darwin" else "KiB",
    }
    for name in ("memory.current", "memory.max", "cpu.max", "memory.events"):
        path = Path("/sys/fs/cgroup") / name
        if path.exists():
            value[name] = path.read_text().strip()
    return value


def environment(engine):
    with engine.connect() as connection:
        pragmas = {
            name: connection.exec_driver_sql("PRAGMA " + name).scalar()
            for name in ("journal_mode", "synchronous", "foreign_keys", "page_size")
        }
        guards = (
            connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
            )
            .scalars()
            .all()
        )
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "pragmas": pragmas,
        "installed_sqlite_guards": guards,
        "resources": resource_sample(),
        "meminfo": Path("/proc/meminfo").read_text()
        if Path("/proc/meminfo").exists()
        else None,
        "cpuinfo": Path("/proc/cpuinfo").read_text()
        if Path("/proc/cpuinfo").exists()
        else None,
    }


class Fixture(EngineClaimsTests):
    """Use only scoped synthetic identity/workflow fixtures, with actual SQL guards."""

    def setUp(self):
        from alembic import command
        from alembic.config import Config
        from models.database import Base

        def migrate(engine):
            settings = Config(str(ROOT / "alembic.ini"))
            settings.set_main_option("script_location", str(ROOT / "migrations"))
            settings.set_main_option("sqlalchemy.url", str(engine.url))
            with patch.dict(os.environ, {"DATABASE_URL": str(engine.url)}):
                command.upgrade(settings, "032_add_infra_automation_engine")

        # Replace the legacy fixture's metadata shortcut with the actual upgrade
        # before it creates any synthetic identity, policy or workflow rows.
        with patch.object(Base.metadata, "create_all", side_effect=migrate):
            LifecycleCase.setUp(self)
        self.enable()
        self.snapshot = self.export(self.publish_fixture())
        self.actor = AuditActor("human-a", "human", "admin")
        self.request = dict(
            snapshot=self.snapshot,
            request_digest=support.digest(b"request"),
            key_digest=support.digest(b"key"),
            requested_by="human-a",
            deadline_at=self.now + timedelta(minutes=10),
            audit_actor=self.actor,
            reason="synthetic",
            now=self.now,
        )
        from services import infra_automation_engine_support as engine_support

        with self.credentials(), auth.authorized_session(self.factory) as session:
            engine_support.ensure_engine_actor(
                session,
                support.scope(session, 100, 100, "automation.request", mutation=True),
            )
        self.run = self.admit()
        self.pending = self.attempt(self.run)
        configure_engine_sqlite(self.engine)
        # Install every guard from the actual migration, never a copied test stub.
        migration = importlib.import_module(
            "migrations.versions.032_add_infra_automation_engine"
        )
        with self.engine.connect() as connection:
            installed = set(
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                ).scalars()
            )
        assert set(migration.GUARDS) <= installed
        self.bounds = config.engine_bounds()
        self.current_time()

    def current_time(self):
        self.now = utc_now()
        captured = datetime.strptime(
            self.snapshot.snapshot.captured_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        self.request["deadline_at"] = captured + timedelta(seconds=3600)
        self.request["now"] = self.now
        return self.now

    def new_workflow(self, steps=50):
        definition = {
            "workflow_version": 2,
            "project_id": "100",
            "workspace_id": "100",
            "environment": "dev",
            "inputs": {"note": {"type": "string", "max_length": 100}},
            "steps": [
                {
                    "id": "source",
                    "kind": "uploaded_intake",
                    "depends_on": [],
                    "source": {"kind": "uploaded"},
                }
            ],
        }
        for index in range(1, steps):
            definition["steps"].append(
                {
                    "id": f"analysis{index}",
                    "kind": "shared_analysis",
                    "depends_on": ["source"],
                    "artifact": {
                        "ref": "step",
                        "step_id": "source",
                        "output": "screened_artifacts",
                    },
                }
            )
        return self.publish_fixture(definition)

    def request_ready(self, ids, sequence, registry, bounds=None):
        self.current_time()
        request = RunRequest(
            workflow_id=ids[0],
            revision_id=ids[1],
            workspace_id=100,
            inputs={"note": "synthetic qualification"},
            idempotency_key=f"qualification-{sequence}",
            reason="Synthetic engine qualification.",
            total_timeout_seconds=3600,
        )
        with self.credentials():
            return service.request_run(
                request, registry=registry, bounds=bounds or self.bounds
            )


def make_fixture():
    value = Fixture(methodName="runTest")
    try:
        value.setUp()
    except BaseException:
        value.doCleanups()
        raise
    return value


def uploaded(value):
    return WorkerResult(
        outcome="local_success",
        output=OutputReference(
            kind="screened_artifacts",
            reference="synthetic-source",
            digest=support.digest(value.snapshot_bytes),
        ),
    )


def analyzed(value):
    return WorkerResult(
        outcome="local_success",
        output=OutputReference(
            kind="report",
            reference=value.step_id,
            digest=support.digest(value.step_id.encode()),
        ),
    )


def slow_analysis(value):
    time.sleep(10)
    return analyzed(value)


def registry(slow=False):
    return HandlerRegistry(
        (
            HandlerRegistration(
                "synthetic-upload",
                "1",
                "uploaded_intake",
                "screened_artifacts",
                True,
                uploaded,
            ),
            HandlerRegistration(
                "synthetic-analysis",
                "1",
                "shared_analysis",
                "report",
                True,
                slow_analysis if slow else analyzed,
            ),
        )
    )


@dataclass(frozen=True)
class SlotHeartbeat:
    slot_id: str
    sequence: int
    observed_monotonic: float


class SyntheticSlotPort:
    """Local typed heartbeat/read double; no enrollment or runner transport."""

    def __init__(self, count=20):
        self.identities = tuple(f"synthetic-slot-{index}" for index in range(count))
        self._heartbeats = {}
        self.heartbeat_calls = self.read_calls = 0

    def heartbeat(self, heartbeat: SlotHeartbeat):
        if (
            type(heartbeat) is not SlotHeartbeat
            or heartbeat.slot_id not in self.identities
        ):
            raise ValueError("Unregistered synthetic slot")
        previous = self._heartbeats.get(heartbeat.slot_id)
        if previous and heartbeat.sequence <= previous.sequence:
            raise ValueError("Stale synthetic slot heartbeat")
        self._heartbeats[heartbeat.slot_id] = heartbeat
        self.heartbeat_calls += 1

    def read_online(self, now):
        self.read_calls += 1
        return tuple(
            heartbeat
            for heartbeat in self._heartbeats.values()
            if 0 <= now - heartbeat.observed_monotonic < 5
        )

    def exercise(self, sequence, now):
        for identity in self.identities:
            self.heartbeat(SlotHeartbeat(identity, sequence, now))
        online = self.read_online(now)
        assert len(online) == len(self.identities)
        return len(online)


def durable_rows(connection):
    """Exact row values, including immutable bytes, request keys and ordered audit."""
    result = {}
    tables = (
        connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        .scalars()
        .all()
    )
    for table in tables:
        rows = connection.exec_driver_sql('SELECT * FROM "' + table + '"').all()
        converted = [
            [
                dict(hex=value.hex()) if isinstance(value, bytes) else value
                for value in row
            ]
            for row in rows
        ]
        result[table] = sorted(
            converted, key=lambda row: json.dumps(row, sort_keys=True)
        )
    return result


def dump_factory(factory):
    with factory() as session:
        return durable_rows(session.connection())


def child_engine(url):
    engine = create_engine(url, connect_args={"timeout": 10})

    @event.listens_for(engine, "connect")
    def configure(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    configure_engine_sqlite(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def fault_operation(session, case):
    name, payload = case["name"], case["payload"]
    owner, handle, now = payload.get("owner"), payload.get("handle"), payload["now"]
    attempt_id, run_id = payload["attempt_id"], payload["run_id"]
    attempt = repo.get_attempt(session, attempt_id)
    run = repo.get_run(session, run_id)
    output = OutputReference(
        kind="screened_artifacts",
        reference="synthetic-fault-output",
        digest=support.digest(b"output"),
    )
    if name == "run_admission":
        return repo.create_run(session, **payload["request"])
    if name == "coordinator_acquire":
        return claims.acquire_coordinator(
            session, project_id=100, workspace_id=100, now=now
        )
    if name in ("coordinator_renew", "coordinator_release"):
        function = (
            claims.renew_coordinator
            if name.endswith("renew")
            else claims.release_coordinator
        )
        return function(session, owner, project_id=100, workspace_id=100, now=now)
    if name == "begin_external":
        return claims.begin_external(
            session, handle, expected_version=attempt.version, now=now
        )
    if name == "attempt_adopt_output":
        return claims.adopt_committed_output(
            session, handle, expected_version=attempt.version, now=now
        )
    if name == "attempt_prepare":
        return claims.prepare_attempt(
            session,
            owner,
            run_id=run.id,
            step_id="upload",
            handler_id="prepared-double",
            handler_version="1",
            retry_safe=True,
            now=now,
        )
    if name == "attempt_claim":
        return claims.claim_attempt(
            session,
            owner,
            attempt_id=attempt.id,
            expected_version=attempt.version,
            now=now,
        )
    if name in ("attempt_start", "attempt_heartbeat"):
        function = (
            claims.start_attempt if name.endswith("start") else claims.heartbeat_attempt
        )
        return function(session, handle, expected_version=attempt.version, now=now)
    if name == "attempt_log":
        return claims.append_log(
            session,
            handle,
            expected_version=attempt.version,
            chunk=LogChunk(sequence=1, text="synthetic"),
            now=now,
        )
    if name == "attempt_upload_reference":
        return claims.register_upload(
            session, handle, expected_version=attempt.version, reference=output, now=now
        )
    if name == "attempt_output":
        return claims.commit_output(
            session, handle, expected_version=attempt.version, output=output, now=now
        )
    if name == "attempt_complete":
        return claims.complete_attempt(
            session,
            handle,
            expected_version=attempt.version,
            state="succeeded",
            now=now,
        )
    if name == "attempt_retry":
        return claims.prepare_retry(
            session,
            owner,
            previous_attempt_id=attempt.id,
            expected_version=attempt.version,
            now=now,
        )
    if name == "attempt_expire":
        return claims.safety_cleanup(
            session,
            owner,
            attempt_id=attempt.id,
            expected_version=attempt.version,
            state="timed_out",
            now=now,
        )
    if name in ("cancel_request", "cancel_completion"):
        from infra_automation.state import CancelRunRequest

        return service.cancel_run(
            run.id,
            CancelRunRequest(
                expected_version=run.version, reason="Synthetic fault cancellation"
            ),
            now=now,
        )
    if name == "run_transition":
        return repo.transition_run(
            session,
            run_id=run.id,
            expected_version=run.version,
            state="cancelled" if name.startswith("cancel") else "failed",
            audit_actor=payload["actor"],
            reason="Synthetic fault boundary",
            now=now,
        )
    if name == "run_edge":
        return repo.transition_run(
            session,
            run_id=run.id,
            expected_version=run.version,
            state=payload["target"],
            audit_actor=payload["actor"],
            reason="Synthetic run edge",
            now=now,
        )
    if name == "attempt_edge":
        return repo.transition_attempt(
            session,
            attempt_id=attempt.id,
            expected_version=attempt.version,
            state=payload["target"],
            audit_actor=payload["actor"],
            reason="Synthetic attempt edge",
            now=now,
        )
    raise ValueError("Unknown fault boundary")


def fault_child(url, case, point, manifest):
    engine, factory = child_engine(url)
    from services.identity_service import IdentityService

    origin = "https://lifecycle.invalid"
    identity = IdentityService(
        factory,
        now=lambda: case["payload"]["now"],
        security_profile="https",
        trusted_origin=origin,
    )
    with (
        patch("services.project_service.SessionLocal", factory),
        patch(
            "config.settings",
            replace(
                config.settings,
                identity_profile="https",
                identity_origin=origin,
                authorization_profile="legacy-evaluation",
            ),
        ),
        auth.credential_context(
            identity,
            case["payload"]["token"],
            csrf_token=case["payload"]["csrf"],
            mutation=True,
        ),
        auth.authorized_session(factory) as session,
    ):
        result = fault_operation(session, case)
        if result is None:
            raise AssertionError("Fault operation did not change durable state")
        session.flush()
        expected = durable_rows(session.connection())
        write_json(manifest, expected)
        if point == "before_commit":
            os._exit(EXIT_CODE)
        session.commit()
        os._exit(EXIT_CODE)
    engine.dispose()


def prepare_fault(fixture, name, old=None, target=None):
    payload = {
        "now": fixture.now,
        "run_id": fixture.run.id,
        "attempt_id": fixture.pending.id,
        "actor": fixture.actor,
        "token": fixture.tokens["human-a"][0],
        "csrf": fixture.tokens["human-a"][1],
    }
    if name == "run_admission":
        payload["request"] = {
            **fixture.request,
            "key_digest": support.digest(b"fault-admission"),
        }
    if name not in ("run_admission", "coordinator_acquire", "run_edge", "attempt_edge"):
        payload["owner"] = fixture.acquire()
    if name == "begin_external":
        snapshot = fixture.export(
            fixture.publish_fixture(fixture.definition()), inputs={}
        )
        fixture.request.update(
            snapshot=snapshot,
            key_digest=support.digest(b"external-boundary"),
            deadline_at=fixture.now + timedelta(minutes=10),
        )
        run = fixture.admit()
        fixture.operation(
            claims.start_run,
            payload["owner"],
            run_id=run.id,
            expected_version=run.version,
        )
        for step in snapshot.snapshot.definition.steps:
            pending = fixture.operation(
                claims.prepare_attempt,
                payload["owner"],
                run_id=run.id,
                step_id=step.id,
                handler_id="typed-" + step.kind,
                handler_version="1",
                retry_safe=False,
            )
            handle = fixture.operation(
                claims.claim_attempt,
                payload["owner"],
                attempt_id=pending.id,
                expected_version=pending.version,
            )
            row = fixture.operation(claims.start_attempt, handle, expected_version=2)
            if step.kind == "registered_github_handoff":
                payload.update(run_id=run.id, attempt_id=pending.id, handle=handle)
                break
            reference = OutputReference(
                kind=STEP_CONTRACTS[step.kind].output,
                reference=step.id,
                digest=support.digest(step.id.encode()),
            )
            row = fixture.operation(
                claims.register_upload,
                handle,
                expected_version=row.version,
                reference=reference,
            )
            row = fixture.operation(
                claims.commit_output,
                handle,
                expected_version=row.version,
                output=reference,
            )
            fixture.operation(
                claims.complete_attempt,
                handle,
                expected_version=row.version,
                state="succeeded",
            )
        return {"name": name, "payload": payload}
    if name == "attempt_prepare":
        fixture.request["key_digest"] = support.digest(b"prepare-boundary")
        run = fixture.admit()
        fixture.operation(
            claims.start_run,
            payload["owner"],
            run_id=run.id,
            expected_version=run.version,
        )
        payload["run_id"] = run.id
        return {"name": name, "payload": payload}
    if name.startswith("attempt_") and name not in ("attempt_edge",):
        fixture.operation(
            claims.start_run,
            payload["owner"],
            run_id=fixture.run.id,
            expected_version=1,
        )
        if name != "attempt_claim":
            handle = fixture.operation(
                claims.claim_attempt,
                payload["owner"],
                attempt_id=fixture.pending.id,
                expected_version=1,
            )
            payload["handle"] = handle
            if name != "attempt_start":
                row = fixture.operation(
                    claims.start_attempt, handle, expected_version=2
                )
                output = OutputReference(
                    kind="screened_artifacts",
                    reference="synthetic-fault-output",
                    digest=support.digest(b"output"),
                )
                if name in ("attempt_output", "attempt_complete"):
                    row = fixture.operation(
                        claims.register_upload,
                        handle,
                        expected_version=row.version,
                        reference=output,
                    )
                if name == "attempt_complete":
                    fixture.operation(
                        claims.commit_output,
                        handle,
                        expected_version=row.version,
                        output=output,
                    )
                if name == "attempt_retry":
                    fixture.operation(
                        claims.complete_attempt,
                        handle,
                        expected_version=row.version,
                        state="failed",
                    )
    if name == "attempt_adopt_output":
        handle = payload["handle"]
        row = fixture.operation(
            claims.register_upload,
            handle,
            expected_version=row.version,
            reference=output,
        )
        row = fixture.operation(
            claims.commit_output, handle, expected_version=row.version, output=output
        )
        row = fixture.operation(
            claims.complete_attempt,
            handle,
            expected_version=row.version,
            state="failed",
        )
        pending = fixture.operation(
            claims.prepare_retry,
            payload["owner"],
            previous_attempt_id=row.id,
            expected_version=row.version,
        )
        handle = fixture.operation(
            claims.claim_attempt,
            payload["owner"],
            attempt_id=pending.id,
            expected_version=pending.version,
        )
        fixture.operation(claims.start_attempt, handle, expected_version=2)
        payload.update(handle=handle, attempt_id=pending.id)
    if name in ("run_edge", "attempt_edge"):
        payload["target"] = target
        with fixture.factory.begin() as session:
            if name == "run_edge":
                row = session.get(InfraAutomationRun, fixture.run.sequence)
                row.state = old
                row.version += 1
                if target == "succeeded":
                    attempt = session.get(
                        InfraAutomationAttempt, fixture.pending.sequence
                    )
                    attempt.state = "succeeded"
                    attempt.version += 1
                    reference = OutputReference(
                        kind="screened_artifacts",
                        reference="synthetic",
                        digest=support.digest(b"output"),
                    )
                    attempt.output_json = reference.model_dump_json()
                    attempt.output_digest = reference.digest
            else:
                row = session.get(InfraAutomationAttempt, fixture.pending.sequence)
                row.state = old
                row.version += 1
                if target == "succeeded":
                    reference = OutputReference(
                        kind="screened_artifacts",
                        reference="synthetic",
                        digest=support.digest(b"output"),
                    )
                    row.output_json = reference.model_dump_json()
                    row.output_digest = reference.digest
    return {"name": name, "payload": payload}


def run_faults(output, *, smoke=False):
    started = time.monotonic()
    started_utc = utc_now().isoformat()
    hashes = source_hashes()
    initial = None
    cases = [(name, None, None) for name in CONTRACT["fault_boundaries"]]
    cases.extend(
        (name, None, None)
        for name in ("attempt_prepare", "attempt_adopt_output", "begin_external")
    )
    if smoke:
        cases = cases[:1]
    else:
        cases += [
            (kind + "_edge", old, target)
            for kind in ("run", "attempt")
            for old, targets in CONTRACT[kind + "_edges"].items()
            for target in targets
        ]
    reports = []
    context = multiprocessing.get_context("spawn")
    for name, old, target in cases:
        for point in CONTRACT["fault_points"]:
            fixture = make_fixture()
            try:
                if initial is None:
                    initial = environment(fixture.engine)
                case = prepare_fault(fixture, name, old, target)
                before = dump_factory(fixture.factory)
                manifest = Path(fixture.temp.name) / "expected.json"
                process = context.Process(
                    target=fault_child,
                    args=(str(fixture.engine.url), case, point, str(manifest)),
                )
                process.start()
                process.join(30)
                if process.is_alive():
                    process.kill()
                    process.join()
                    raise AssertionError("Fault child exceeded deadline")
                assert process.exitcode == EXIT_CODE, (
                    name,
                    old,
                    target,
                    point,
                    process.exitcode,
                )
                process.close()
                assert manifest.exists(), "Expected-state manifest missing"
                engine, factory = child_engine(str(fixture.engine.url))
                try:
                    recovered = dump_factory(factory)
                    expected = (
                        before
                        if point == "before_commit"
                        else json.loads(manifest.read_text())
                    )
                    assert recovered == expected, (
                        name,
                        old,
                        target,
                        point,
                        "Restart state/audit mismatch",
                    )
                    with engine.connect() as connection:
                        assert (
                            connection.exec_driver_sql(
                                "PRAGMA integrity_check"
                            ).scalar()
                            == "ok"
                        )
                        assert not connection.exec_driver_sql(
                            "PRAGMA foreign_key_check"
                        ).all()
                finally:
                    engine.dispose()
                reports.append(
                    {
                        "boundary": name,
                        "from": old,
                        "to": target,
                        "point": point,
                        "exitcode": EXIT_CODE,
                        "exact_restart_state_and_audit": True,
                    }
                )
            finally:
                fixture.doCleanups()
    end_hashes = source_hashes()
    assert hashes == end_hashes, "Fault-qualified source changed during measurement"
    result = {
        "started_utc": started_utc,
        "ended_utc": utc_now().isoformat(),
        "started_monotonic": started,
        "ended_monotonic": time.monotonic(),
        "elapsed_seconds": time.monotonic() - started,
        "environment": initial,
        "source_hashes_start": hashes,
        "source_hashes_end": end_hashes,
        "source_hashes_identical": hashes == end_hashes,
        "cancel_boundary_mapping": "E request flag, idempotency and cancelled run/attempt completion are one atomic service.cancel_run transaction; both fixture labels exercise that same outer commit",
        "mode": "fault",
        "acceptance_qualified": not smoke,
        "cases": reports,
        "count": len(reports),
        "host_power_loss_qualified": False,
    }
    write_json(Path(output) / "faults.json", result)
    return result


class MeasuredCoordinator(Coordinator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready_samples = []

    def _schedule(self, run_id, now):
        before = len(self.workers.handles)
        started = time.monotonic()
        super()._schedule(run_id, now)
        elapsed = time.monotonic() - started
        if len(self.workers.handles) > before:
            self.ready_samples.append(elapsed)


def states(factory):
    with factory() as session:
        runs = list(
            session.execute(
                select(InfraAutomationRun.workflow_id, InfraAutomationRun.state)
            )
        )
        completed = session.scalar(
            select(func.count())
            .select_from(InfraAutomationAttempt)
            .where(InfraAutomationAttempt.state == "succeeded")
        )
        analysis = session.scalar(
            select(func.count())
            .select_from(InfraAutomationAttempt)
            .where(
                InfraAutomationAttempt.step_kind == "shared_analysis",
                InfraAutomationAttempt.state.in_(("claimed", "running")),
            )
        )
        errors = session.scalar(
            select(func.count())
            .select_from(InfraAutomationRun)
            .where(
                InfraAutomationRun.state.in_(
                    ("failed", "expired", "timed_out", "delivery_unknown")
                )
            )
        )
    return runs, completed, analysis, errors


def p95(samples):
    return sorted(samples)[math.ceil(len(samples) * 0.95) - 1]


def run_workload(
    output, *, capacity=False, seconds=1800, transitions=1000, smoke=False
):
    fixture = make_fixture()
    workers = coordinator = None
    started = time.monotonic()
    started_utc = utc_now().isoformat()
    hashes = source_hashes()
    samples = []
    try:
        registrations = registry(slow=capacity)
        workers = SpawnProcessWorkers(str(fixture.engine.url), bounds=fixture.bounds)
        coordinator = MeasuredCoordinator(
            fixture.factory, workers, registry=registrations, bounds=fixture.bounds
        )
        workflows = [
            fixture.new_workflow(steps=50 if not smoke else 3) for _ in range(2)
        ]
        sequence = 0
        slots = SyntheticSlotPort()
        # The claims fixture's separate initial run is not part of workload capacity.
        with fixture.factory.begin() as session:
            repo.transition_run(
                session,
                run_id=fixture.run.id,
                expected_version=1,
                state="cancelled",
                audit_actor=fixture.actor,
                reason="Synthetic setup complete",
            )
        initial = environment(fixture.engine)
        next_integrity = time.monotonic()
        next_progress = time.monotonic() + (40 if capacity and not smoke else 15)
        last_completed = 0
        max_active = max_workers = max_analysis = max_slots = 0
        max_database = max_wal = 0
        all_capacity = True
        horizon_started = None
        denial_checks = 0
        backpressure_checked = False
        # Warm up to real ten active runs before beginning the capacity horizon.
        while True:
            fixture.current_time()
            runs, completed, analysis, errors = states(fixture.factory)
            assert errors == 0, "Unexpected terminal engine error"
            for workflow in workflows:
                nonterminal = sum(
                    wid == workflow[0] and state in ("queued", "running")
                    for wid, state in runs
                )
                for _ in range(max(0, 5 - nonterminal)):
                    sequence += 1
                    fixture.request_ready(workflow, sequence, registrations)
            coordinator.tick()
            # A terminal run is replenished through the same authenticated API;
            # allow the coordinator to promote the replacement before sampling.
            after_tick, _, _, _ = states(fixture.factory)
            replenished = False
            for workflow in workflows:
                retained = sum(
                    wid == workflow[0] and state in ("queued", "running")
                    for wid, state in after_tick
                )
                for _ in range(max(0, 5 - retained)):
                    sequence += 1
                    fixture.request_ready(workflow, sequence, registrations)
                    replenished = True
            if replenished:
                coordinator.tick()
            now = time.monotonic()
            runs, completed, analysis, errors = states(fixture.factory)
            active_by_workflow = {
                workflow[0]: sum(
                    wid == workflow[0] and state == "running" for wid, state in runs
                )
                for workflow in workflows
            }
            active = sum(active_by_workflow.values())
            assert active <= 10 and all(
                value <= 5 for value in active_by_workflow.values()
            )
            assert len(workers.handles) <= 2 and analysis <= 2 and errors == 0
            if capacity and active == 10 and not backpressure_checked:
                from infra_automation.state import CancelRunRequest

                limited = fixture.bounds.model_copy(update={"workflow_queued_runs": 1})
                queued = fixture.request_ready(
                    workflows[0], 10000000, registrations, bounds=limited
                )
                try:
                    fixture.request_ready(
                        workflows[0], 10000001, registrations, bounds=limited
                    )
                except LifecycleError as error:
                    assert error.status_code == 429
                else:
                    raise AssertionError(
                        "Queue backpressure did not reject saturated admission"
                    )
                with fixture.credentials():
                    service.cancel_run(
                        queued["run_id"] if "run_id" in queued else queued["id"],
                        CancelRunRequest(
                            expected_version=queued["version"],
                            reason="Synthetic queue probe complete",
                        ),
                    )
                backpressure_checked = True
            if capacity and active == 10 and horizon_started is None:
                horizon_started = now
                started_utc = utc_now().isoformat()
                write_json(
                    Path(output) / "capacity-start.json",
                    {
                        "started_utc": started_utc,
                        "started_monotonic": now,
                        "source_hashes": hashes,
                        "environment": initial,
                    },
                )
            if completed > last_completed:
                last_completed = completed
                next_progress = now + (40 if capacity and not smoke else 15)
            assert now < next_progress, "Continuous workload progress stalled"
            assert now - started < (seconds + 120 if capacity else 2400), (
                "Workload exceeded finite deadline"
            )
            count_slots = slots.exercise(len(samples) + 1, now)
            db = fixture.engine.url.database
            max_database = max(max_database, file_bytes(db))
            max_wal = max(max_wal, file_bytes(str(db) + "-wal"))
            max_active = max(max_active, active)
            max_workers = max(max_workers, len(workers.handles))
            max_analysis = max(max_analysis, analysis)
            max_slots = max(max_slots, count_slots)
            if now >= next_integrity:
                with fixture.engine.connect() as connection:
                    assert (
                        connection.exec_driver_sql("PRAGMA integrity_check").scalar()
                        == "ok"
                    )
                    assert not connection.exec_driver_sql(
                        "PRAGMA foreign_key_check"
                    ).all()
                with auth.authorized_session(fixture.factory) as session:
                    ensure_capacity(session, bounds=fixture.bounds)
                for handle in workers.handles[:1]:
                    try:
                        with auth.authorized_session(fixture.factory) as session:
                            row = repo.get_attempt(session, handle.attempt_id)
                            claims.heartbeat_attempt(
                                session,
                                replace(handle, owner_secret="0" * 64),
                                expected_version=row.version,
                            )
                    except LifecycleError:
                        denial_checks += 1
                    else:
                        raise AssertionError("Forged private attempt owner accepted")
                next_integrity = now + 15
            sample = {
                "elapsed": now - (horizon_started or started),
                "active": active,
                "active_by_workflow": active_by_workflow,
                "workers": len(workers.handles),
                "analysis_inflight": analysis,
                "slots": count_slots,
                "completed_attempts": completed,
                "queued": sum(state == "queued" for _, state in runs),
                "resources": resource_sample(),
            }
            samples.append(sample)
            if horizon_started is not None and active != 10:
                # A completion is replenished on the next iteration, and is recorded.
                all_capacity = False
            if capacity:
                if horizon_started is not None and now - horizon_started >= seconds:
                    break
            elif len(coordinator.ready_samples) >= transitions:
                break
            time.sleep(0.1 if not capacity else 0.25)
        end = time.monotonic()
        end_hashes = source_hashes()
        assert hashes == end_hashes, "Qualified source changed during measurement"
        ready = (
            coordinator.ready_samples[:transitions]
            if not capacity
            else coordinator.ready_samples
        )
        elapsed = end - (horizon_started if capacity else started)
        if not smoke:
            if capacity:
                assert (
                    elapsed >= 1800
                    and max_active == 10
                    and max_analysis == 2
                    and max_slots == 20
                    and all_capacity
                    and backpressure_checked
                    and denial_checks > 0
                )
            else:
                assert len(ready) == 1000 and p95(ready) < 1
        result = {
            "mode": "capacity" if capacity else "benchmark",
            "acceptance_qualified": not smoke,
            "scope": "Synthetic local engine/analysis handlers and heartbeat/read slots only; no real runner/receiver or host power loss qualification",
            "started_utc": started_utc,
            "ended_utc": utc_now().isoformat(),
            "started_monotonic": horizon_started if capacity else started,
            "ended_monotonic": end,
            "elapsed_seconds": elapsed,
            "environment": initial,
            "final_resources": resource_sample(),
            "source_hashes_start": hashes,
            "source_hashes_end": end_hashes,
            "source_hashes_identical": hashes == end_hashes,
            "max_active": max_active,
            "max_workers": max_workers,
            "max_analysis_inflight": max_analysis,
            "max_online_slots": max_slots,
            "slot_heartbeat_calls": slots.heartbeat_calls,
            "slot_read_calls": slots.read_calls,
            "ready_transition_count": len(ready),
            "ready_transition_seconds": ready,
            "ready_transition_p95_seconds": p95(ready) if ready else None,
            "completed_attempts": last_completed,
            "error_count": 0,
            "sample_count": len(samples),
            "samples": samples,
            "active_ten_every_sample_after_warmup": all_capacity,
            "max_database_bytes": max_database,
            "max_wal_bytes": max_wal,
            "handler_seconds": 10 if capacity else 0,
            "continuous_private_owner_denials": denial_checks,
            "queue_backpressure_checked": backpressure_checked,
            "ready_measurement": "Actual Coordinator._schedule calls which submit a committed attempt to SpawnProcessWorkers; includes orchestration/database/spawn; excludes handler execution",
        }
        write_json(Path(output) / (result["mode"] + ".json"), result)
        return result
    finally:
        if coordinator:
            coordinator.close()
        elif workers:
            workers.close()
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("fault", "benchmark", "capacity", "all"), required=True
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--capacity-seconds", type=int, default=1800)
    parser.add_argument("--transitions", type=int, default=1000)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Explicitly unqualified short harness validation",
    )
    args = parser.parse_args()
    if not args.smoke and (args.capacity_seconds < 1800 or args.transitions != 1000):
        parser.error(
            "Acceptance requires >=1800 real seconds and exactly1000 ready transitions"
        )
    Path(args.output).mkdir(parents=True, exist_ok=True)
    for mode in ("fault", "benchmark", "capacity"):
        if args.mode in (mode, "all"):
            print(
                json.dumps(
                    {"mode": mode, "event": "start", "utc": utc_now().isoformat()}
                ),
                flush=True,
            )
            if mode == "fault":
                result = run_faults(args.output, smoke=args.smoke)
            else:
                result = run_workload(
                    args.output,
                    capacity=mode == "capacity",
                    seconds=args.capacity_seconds,
                    transitions=args.transitions,
                    smoke=args.smoke,
                )
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "event": "complete",
                        "qualified": result["acceptance_qualified"],
                        "sample_count": result.get("sample_count", result.get("count")),
                        "elapsed_seconds": result.get("elapsed_seconds"),
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
