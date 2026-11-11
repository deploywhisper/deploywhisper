"""Measure current SQLite capacity with twenty authenticated local runner ports.

Reuses the frozen Story16.5 ten-run/two-spawned-worker workload without changing
its file. Local synthetic analysis handlers and authenticated runner service
calls do not qualify remote HTTPS agents, collectors, receivers or cloud support.
The full horizon requires 1800 actual monotonic seconds; smoke is unqualified.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from importlib import import_module
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

from sqlalchemy import create_engine, event, func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
frozen = import_module("tests.fixtures.infra_automation.engine_v1.qualification")
frozen_source_hashes = frozen.source_hashes
runners = import_module("services.infra_automation_runners")
tasks = import_module("services.infra_automation_runner_tasks")
auth = import_module("services.project_service")
tables = import_module("models.tables")

REVISION = "042_add_receiver_recovery"
RUNNER_COUNT = 20
SCOPE = (
    "Current SQLite schema with configured bound operator recovery controls; "
    "ten active runs and at most two actual spawned "
    "synthetic analysis workers plus twenty persisted, enrolled, redeemed and "
    "polled local authenticated runner service ports. No remote HTTPS agent, "
    "collector, receiver, cloud or host-power-loss qualification."
)


def source_hashes():
    paths = set(frozen_source_hashes())
    for directory in ("api", "cli", "scripts"):
        paths.update(
            str(path.relative_to(ROOT)) for path in (ROOT / directory).rglob("*.py")
        )
    paths.update(("app.py", "api_server.py", "cli.py"))
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in sorted(paths)
    }


class CurrentFixture(frozen.Fixture):
    """Use current real migrations in place of the historical revision032 target."""

    def setUp(self):
        from alembic import command

        upgrade = command.upgrade

        def current_upgrade(configuration, revision):
            if revision != "032_add_infra_automation_engine":
                raise AssertionError("Frozen fixture migration entry changed")
            return upgrade(configuration, REVISION)

        with patch.object(command, "upgrade", side_effect=current_upgrade):
            super().setUp()
        with self.engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT version_num FROM alembic_version"
                ).scalar()
                == REVISION
            )
        # Qualify the configured participation/epoch guards, including children
        # created with multiprocessing spawn; do not measure the unset fast path.
        recovery = import_module("infra_automation.operator_recovery")
        database = Path(self.engine.url.database).resolve()
        database.chmod(0o600)
        if self.engine.url.database != str(database):
            # macOS tempfile paths can use /var, which aliases /private/var.
            # Retain the production no-symlink rule by opening the actual
            # canonical URL, rather than teaching the recovery guard aliases.
            self.engine.dispose()
            self.engine = create_engine(
                "sqlite:///" + str(database), connect_args={"timeout": 10}
            )

            @event.listens_for(self.engine, "connect")
            def foreign_keys(connection, record):
                connection.execute("PRAGMA foreign_keys=ON")

            frozen.configure_engine_sqlite(self.engine)
            self.factory.configure(bind=self.engine)
            self.addCleanup(self.engine.dispose)
        roots = {}
        for role in ("artifacts", "custody"):
            path = database.parent / role
            path.mkdir(mode=0o700)
            roots[role] = path
        self.recovery_control = database.parent / "operator-control"
        self.recovery_store = recovery.RecoveryStore(self.recovery_control)
        self.recovery_store.initialize(database, roots)
        settings_patch = patch.object(
            frozen.config,
            "settings",
            replace(
                frozen.config.settings,
                recovery_control_path=str(self.recovery_control),
            ),
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        environment_patch = patch.dict(
            os.environ,
            {"DEPLOYWHISPER_RECOVERY_CONTROL_PATH": str(self.recovery_control)},
        )
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        state = self.recovery_store.status()
        self.recovery_observation = {
            "configured": True,
            "phase": state["phase"],
            "generation": state["generation"],
        }


def make_current_fixture():
    fixture = CurrentFixture(methodName="runTest")
    try:
        fixture.setUp()
    except BaseException:
        fixture.doCleanups()
        raise
    return fixture


class AuthenticatedRunnerPort:
    """Exercise persisted credential checks, rotation and health, never fake slots."""

    def __init__(self, fixture, *, rotate_before_seconds=120):
        if (
            type(rotate_before_seconds) is not int
            or not 1 <= rotate_before_seconds <= 900
        ):
            raise ValueError("Invalid runner rotation window")
        self.fixture = fixture
        self.rotate_before_seconds = rotate_before_seconds
        self.credentials = {}
        self.expires_at = {}
        self.heartbeat_calls = self.read_calls = self.rotation_count = 0
        self.storage_samples = []
        self.last_sequence = 0
        fixture.current_time()
        for index in range(RUNNER_COUNT):
            with fixture.credentials():
                issued = runners.create_enrollment(
                    runners.EnrollmentRequest(
                        project_id=fixture.project_id,
                        workspace_id=fixture.workspace_id,
                        tags=["capacity-service-port"],
                        tool="opentofu",
                        profile_digest="sha256:" + "a" * 64,
                        runner_version="capacity-local-v1",
                        reason=f"Capacity qualification local runner {index + 1}",
                    )
                )
            credential = runners.redeem(
                issued.enrollment.enrollment_id,
                issued.token.get_secret_value(),
                enrollment=issued.enrollment,
            )
            self._retain_credential(credential)

    def _retain_credential(self, issued):
        self.credentials[issued.runner_id] = runners.RunnerCredential(
            issued.runner_id, issued.token.get_secret_value()
        )
        self.expires_at[issued.runner_id] = datetime.strptime(
            issued.expires_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

    def exercise(self, sequence, observed_monotonic):
        if type(sequence) is not int or sequence <= self.last_sequence:
            raise ValueError("Stale local runner sample")
        self.last_sequence = sequence
        self.fixture.current_time()
        for runner_id in self.credentials:
            now = datetime.now(timezone.utc)
            if now >= self.expires_at[runner_id] - timedelta(
                seconds=self.rotate_before_seconds
            ):
                with self.fixture.credentials():
                    issued = runners.rotate(
                        runner_id, reason="Rotate measured local runner before expiry"
                    )
                self._retain_credential(issued)
                self.rotation_count += 1
            assignment = tasks.poll(self.credentials[runner_id])
            assert assignment is None, (
                "Capacity-only runner received an unexpected task"
            )
            self.heartbeat_calls += 1
        with self.fixture.credentials(mutation=False):
            page = runners.health(
                self.fixture.project_id, self.fixture.workspace_id, limit=100
            )
        self.read_calls += 1
        items = page["items"]
        assert page["cursor"]["next_cursor"] is None
        assert {row["id"] for row in items} == self.credentials.keys()
        assert all(
            row["credential_status"] == "valid" and row["connectivity"] == "online"
            for row in items
        )
        # Persisted rows and the public health projection must agree. The count
        # cannot be satisfied by in-memory heartbeat identities.
        with self.fixture.factory() as session:
            retained = (
                session.scalar(
                    select(func.sum(tables.InfraAutomationRun.retained_bytes))
                )
                or 0
            )
            queued = (
                session.scalar(
                    select(func.count())
                    .select_from(tables.InfraAutomationRun)
                    .where(tables.InfraAutomationRun.state == "queued")
                )
                or 0
            )
            count = session.scalar(
                select(func.count())
                .select_from(tables.InfraAutomationRunner)
                .where(tables.InfraAutomationRunner.status == "active")
            )
        assert count == RUNNER_COUNT
        assert (
            retained
            <= self.fixture.bounds.project_bytes
            <= self.fixture.bounds.global_bytes
        )
        assert queued <= self.fixture.bounds.global_queued_runs
        self.storage_samples.append(
            {
                "retained_run_bytes": retained,
                "queued": queued,
                "authenticated_runners": count,
                "process_cpu_seconds": time.process_time(),
            }
        )
        return len(items)


def run_capacity(output, *, seconds=1800, smoke=False):
    if type(seconds) is not int or seconds < 1 or (not smoke and seconds != 1800):
        raise ValueError("Full capacity proof requires exactly1800 actual seconds")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    context = {}
    hashes = source_hashes()
    started = time.monotonic()

    def fixture_factory():
        value = make_current_fixture()
        context["fixture"] = value
        return value

    def runner_factory():
        value = AuthenticatedRunnerPort(context["fixture"])
        context["runners"] = value
        return value

    # Replace only the factory, synthetic runner port and hash supplier. The
    # original scheduling workload, spawned workers, clocks and guards remain.
    try:
        with (
            patch.object(frozen, "make_fixture", fixture_factory),
            patch.object(frozen, "SyntheticSlotPort", runner_factory),
            patch.object(frozen, "source_hashes", source_hashes),
        ):
            result = frozen.run_workload(
                output, capacity=True, seconds=seconds, smoke=smoke
            )
        end_hashes = source_hashes()
        assert hashes == end_hashes, "Capacity source changed during measurement"
        port = context["runners"]
        assert result["elapsed_seconds"] >= seconds
        if not smoke:
            assert port.rotation_count >= RUNNER_COUNT, (
                "Real credential rotation not exercised"
            )
        result.update(
            scope=SCOPE,
            schema_revision=REVISION,
            engine_bounds=context["fixture"].bounds.model_dump(),
            operator_recovery=context["fixture"].recovery_observation,
            source_hashes_start=hashes,
            source_hashes_end=end_hashes,
            source_hashes_identical=True,
            online_runner_kind="persisted authenticated local service ports",
            max_authenticated_online_runners=result["max_online_slots"],
            runner_poll_authentications=port.heartbeat_calls,
            runner_health_reads=port.read_calls,
            runner_credential_rotations=port.rotation_count,
            storage_samples=port.storage_samples,
            remote_https_agents_qualified=False,
            collector_qualified=False,
        )
        frozen.write_json(output / "operator-capacity.json", result)
        return result
    except BaseException as error:
        frozen.write_json(
            output / "operator-capacity-failure.json",
            {
                "acceptance_qualified": False,
                "scope": SCOPE,
                "error_type": type(error).__name__,
                "elapsed_seconds": time.monotonic() - started,
                "source_hashes_start": hashes,
                "source_hashes_end": source_hashes(),
            },
        )
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    if args.seconds < 1 or (not args.smoke and args.seconds != 1800):
        parser.error("Full capacity proof requires1800 actual monotonic seconds")
    result = run_capacity(args.output, seconds=args.seconds, smoke=args.smoke)
    print(
        json.dumps(
            {
                "acceptance_qualified": result["acceptance_qualified"],
                "scope": SCOPE,
                "elapsed_seconds": result["elapsed_seconds"],
                "authenticated_runners": result["max_authenticated_online_runners"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
