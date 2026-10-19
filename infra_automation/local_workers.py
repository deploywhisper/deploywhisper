"""Trusted local handlers in bounded spawned processes; no executor queue."""

from __future__ import annotations

from dataclasses import dataclass, field
import multiprocessing
import os
import signal
from typing import Callable

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from infra_automation import claims
from infra_automation.contracts import STEP_CONTRACTS
from infra_automation.lifecycle import SnapshotDocument
from infra_automation.state import AttemptHandle, EngineBounds, WorkerResult
from models.repositories import infra_automation_runs as repository
from services import project_service as authorization


@dataclass(frozen=True)
class WorkerInput:
    snapshot_bytes: bytes
    step_id: str
    prerequisites: tuple[tuple[str, bytes], ...]

    def __post_init__(self):
        if (
            type(self.snapshot_bytes) is not bytes
            or not 1 <= len(self.snapshot_bytes) <= 524288
            or type(self.step_id) is not str
            or type(self.prerequisites) is not tuple
            or len(self.prerequisites) > 50
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not bytes
                or len(item[1]) > 1024
                for item in self.prerequisites
            )
        ):
            raise ValueError("Invalid immutable worker input.")


@dataclass(frozen=True)
class HandlerRegistration:
    handler_id: str
    handler_version: str
    step_kind: str
    output_kind: str | None
    retry_safe: bool
    handler: Callable[[WorkerInput], WorkerResult] = field(repr=False)

    def __post_init__(self):
        if (
            self.step_kind not in STEP_CONTRACTS
            or STEP_CONTRACTS[self.step_kind].output != self.output_kind
            or type(self.retry_safe) is not bool
            or not callable(self.handler)
            or any(
                type(value) is not str or not 1 <= len(value) <= 128
                for value in (self.handler_id, self.handler_version)
            )
            or (self.output_kind is None and self.retry_safe)
        ):
            raise ValueError("Invalid trusted handler registration.")


@dataclass(frozen=True)
class HandlerRegistry:
    registrations: tuple[HandlerRegistration, ...] = ()

    def __post_init__(self):
        if (
            type(self.registrations) is not tuple
            or any(type(item) is not HandlerRegistration for item in self.registrations)
            or len({item.step_kind for item in self.registrations})
            != len(self.registrations)
        ):
            raise ValueError("Handler registry must be immutable and unique.")

    def get(self, step_kind):
        return next(
            (item for item in self.registrations if item.step_kind == step_kind), None
        )

    def __bool__(self):
        return bool(self.registrations)


DEFAULT_REGISTRY = HandlerRegistry()


@dataclass(frozen=True)
class WorkerCompletion:
    handle: AttemptHandle = field(repr=False)
    result: WorkerResult
    crashed: bool = False


def _worker_main(database_url, handle, registration, value, bounds, channel):
    """Private wrapper owns the capability; trusted handler receives input only."""
    engine = None
    try:
        if os.name == "posix":
            os.setsid()
        channel.send_bytes(b"ready")
        engine = create_engine(database_url, connect_args={"timeout": 2})

        @event.listens_for(engine, "connect")
        def configure(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")

        factory = sessionmaker(engine, expire_on_commit=False)

        def write(function, **kwargs):
            with authorization.authorized_session(factory) as session:
                row = repository.get_attempt(session, handle.attempt_id)
                if row is None:
                    raise ValueError("Attempt unavailable.")
                return function(session, handle, expected_version=row.version, **kwargs)

        with authorization.authorized_session(factory) as session:
            run = repository.get_run(session, handle.run_id)
            attempt = repository.get_attempt(session, handle.attempt_id)
            if (
                run is None
                or attempt is None
                or run.snapshot_bytes != value.snapshot_bytes
                or handle.step_id != value.step_id
            ):
                raise ValueError("Immutable worker binding unavailable.")
            if (
                attempt.handler_id,
                attempt.handler_version,
                attempt.step_kind,
                attempt.retry_safe,
            ) != (
                registration.handler_id,
                registration.handler_version,
                registration.step_kind,
                registration.retry_safe,
            ):
                raise ValueError("Trusted handler binding unavailable.")
            document = SnapshotDocument.model_validate_json(value.snapshot_bytes)
            step = next(
                item for item in document.definition.steps if item.id == value.step_id
            )
            attempts = repository.list_attempts(session, run_id=run.id)
            expected = tuple(
                (
                    dependency,
                    next(
                        item
                        for item in reversed(attempts)
                        if item.step_id == dependency and item.state == "succeeded"
                    ).output_json.encode(),
                )
                for dependency in step.depends_on
            )
            if value.prerequisites != expected:
                raise ValueError("Immutable prerequisite binding unavailable.")
        write(claims.start_attempt)
        result = WorkerResult.model_validate(registration.handler(value).model_dump())
        if result.outcome == "external_unknown":
            raise ValueError("External adapter unavailable.")
        if result.outcome == "local_success":
            if result.output is None or result.output.kind != registration.output_kind:
                raise ValueError("Required typed output unavailable.")
            write(claims.register_upload, reference=result.output, bounds=bounds)
            write(claims.commit_output, output=result.output, bounds=bounds)
        elif result.output is not None:
            raise ValueError("Failed work cannot commit an output.")
        channel.send_bytes(result.model_dump_json().encode("utf-8"))
    except Exception:
        # Fixed diagnostics: exceptions may contain sensitive handler inputs.
        try:
            channel.send_bytes(b'{"outcome":"permanent_local_failure"}')
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        channel.close()
        if engine is not None:
            engine.dispose()


@dataclass
class _OwnedProcess:
    process: object
    channel: object
    handle: AttemptHandle = field(repr=False)
    ready: bool = False


class SpawnProcessWorkers:
    def __init__(self, database_url, *, max_workers=2, bounds=None):
        url = make_url(database_url)
        if (
            url.drivername != "sqlite"
            or not url.database
            or url.database == ":memory:"
            or url.host
            or url.username
            or url.password
            or url.query
            or type(max_workers) is not int
            or not 1 <= max_workers <= 2
        ):
            raise ValueError(
                "Workers require a local file SQLite profile and one or two slots."
            )
        self.database_url = str(url)
        self.max_workers = max_workers
        self.bounds = EngineBounds.model_validate(
            (bounds or EngineBounds()).model_dump()
        )
        if max_workers > self.bounds.analysis_workers:
            raise ValueError("Worker slots exceed server bounds.")
        self._context = multiprocessing.get_context("spawn")
        self._owned = {}
        self._closed = False

    @property
    def can_submit(self):
        return not self._closed and len(self._owned) < self.max_workers

    @property
    def handles(self):
        return tuple(item.handle for item in self._owned.values())

    def submit(self, handle, registration, value):
        if (
            type(handle) is not AttemptHandle
            or type(registration) is not HandlerRegistration
            or type(value) is not WorkerInput
        ):
            raise ValueError("Invalid local worker binding.")
        if value.step_id != handle.step_id:
            raise ValueError("Invalid local worker binding.")
        if not self.can_submit or handle.attempt_id in self._owned:
            raise ValueError("Local worker capacity unavailable.")
        parent, child = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=_worker_main,
            args=(self.database_url, handle, registration, value, self.bounds, child),
        )
        try:
            process.start()
        except BaseException:
            parent.close()
            child.close()
            raise
        child.close()
        self._owned[handle.attempt_id] = _OwnedProcess(process, parent, handle)

    def poll(self):
        completed = []
        for attempt_id, item in tuple(self._owned.items()):
            result = None
            crashed = False
            try:
                # At most a ready marker and one bounded result per child.
                for _ in range(2):
                    if not item.channel.poll():
                        break
                    payload = item.channel.recv_bytes(2048)
                    if payload == b"ready" and not item.ready:
                        item.ready = True
                    else:
                        result = WorkerResult.model_validate_json(payload)
                        break
            except (EOFError, OSError, ValueError):
                crashed = True
            if result is None and not crashed and item.process.is_alive():
                continue
            if result is None:
                crashed = True
                result = WorkerResult(outcome="permanent_local_failure")
            completed.append(WorkerCompletion(item.handle, result, crashed))
            self._dispose(item)
            del self._owned[attempt_id]
        return tuple(completed)

    def _dispose(self, item):
        # A worker group is created by our child, never selected by request data.
        process = item.process
        if process.is_alive():
            process.join(timeout=0.02)
        if process.is_alive():
            self._signal(item, signal.SIGTERM)
            process.join(timeout=0.1)
        # Kill a remaining owned group as well as a noncooperative root process.
        self._signal(item, signal.SIGKILL)
        process.join(timeout=0.2)
        item.channel.close()
        if not process.is_alive():
            process.close()

    @staticmethod
    def _signal(item, signum):
        try:
            owns_group = os.name == "posix" and (
                item.ready or os.getpgid(item.process.pid) == item.process.pid
            )
            if owns_group:
                os.killpg(item.process.pid, signum)
            elif item.process.is_alive():
                os.kill(item.process.pid, signum)
        except ProcessLookupError:
            pass

    def cancel(self, attempt_id):
        item = self._owned.pop(attempt_id, None)
        if item is not None:
            self._dispose(item)

    def close(self):
        self._closed = True
        for attempt_id in tuple(self._owned):
            self.cancel(attempt_id)
