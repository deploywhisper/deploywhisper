"""Private host lifetime, two-phase credential delivery and durable cancellation."""

from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
import re
from pathlib import Path
import selectors
import sqlite3
import threading
import time

from infra_automation.receiver_custody import private_directory, check_file, canonical
from infra_automation.runner.execution_profile import ExecutionProfile, IsolationError
from infra_automation.runner.protocol import TaskScope
from infra_automation.runner.sandbox import kill_process
from services.content_security import redact_text

_CALLBACK_SLOTS = threading.BoundedSemaphore(8)
_READY = b"DW_RUNNER_READY_V1\n"


@dataclass(frozen=True)
class CollectorCredentials:
    identity: str
    environment: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ExecutionResult:
    state: str
    exit_code: int | None
    output: str = field(repr=False)
    output_digest: str | None
    container_id: str
    cleanup_complete: bool
    profile_digest: str
    collection: dict | None = field(default=None, repr=False)

    @property
    def finalizable(self):
        return (
            self.state == "succeeded"
            and self.cleanup_complete
            and self.output_digest is not None
        )


class _Stop(Exception):
    def __init__(self, state):
        self.state = state


class ExecutionJournal:
    """Private operator state; only hashes/closed statuses, never credentials/output."""

    def __init__(self, root):
        self.root = Path(root)
        fd = private_directory(self.root)
        try:
            file = os.open(
                "executions.sqlite3",
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
                dir_fd=fd,
            )
            try:
                check_file(file, 0o600)
            finally:
                os.close(file)
        finally:
            os.close(fd)
        self.path = self.root / "executions.sqlite3"
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS executions(task_digest TEXT PRIMARY KEY,container_id TEXT UNIQUE NOT NULL,profile_digest TEXT NOT NULL,owner_nonce TEXT NOT NULL,container_ref TEXT,state TEXT NOT NULL,cancel_requested INTEGER NOT NULL DEFAULT 0,cleanup_complete INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL)"
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(executions)")}
            if "container_ref" not in columns:
                # Preserve previous private journals as unknown creation intents;
                # no existing record is upgraded to acknowledged or cleaned up.
                db.execute("ALTER TABLE executions ADD COLUMN container_ref TEXT")

    @contextmanager
    def connection(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            check_file(fd, 0o600)
        finally:
            os.close(fd)
        db = sqlite3.connect(self.path, timeout=1)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def begin(self, key, name, profile, nonce):
        with self.connection() as db:
            db.execute(
                "INSERT INTO executions(task_digest,container_id,profile_digest,owner_nonce,state,updated_at) VALUES(?,?,?,?,?,?)",
                (
                    key,
                    name,
                    profile,
                    nonce,
                    "preparing",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def acknowledge_creation(self, key, container_id):
        if type(container_id) is not str or not re.fullmatch(
            r"[a-f0-9]{64}", container_id
        ):
            raise IsolationError()
        with self.connection() as db:
            changed = db.execute(
                "UPDATE executions SET container_ref=? WHERE task_digest=? AND (container_ref IS NULL OR container_ref=?)",
                (container_id, key, container_id),
            )
            if changed.rowcount != 1:
                raise IsolationError()

    def creation_reference(self, key):
        with self.connection() as db:
            row = db.execute(
                "SELECT container_ref FROM executions WHERE task_digest=?", (key,)
            ).fetchone()
            if row is None:
                raise IsolationError()
            return row[0]

    def set(self, key, state, *, cancel=False, clean=False):
        with self.connection() as db:
            changed = db.execute(
                "UPDATE executions SET state=?,cancel_requested=max(cancel_requested,?),cleanup_complete=?,updated_at=? WHERE task_digest=?",
                (
                    state,
                    int(cancel),
                    int(clean),
                    datetime.now(timezone.utc).isoformat(),
                    key,
                ),
            )
            if changed.rowcount != 1:
                raise IsolationError()

    def request_cancel(self, key):
        with self.connection() as db:
            changed = db.execute(
                "UPDATE executions SET state='cancel_requested',cancel_requested=1,updated_at=? WHERE task_digest=? AND cleanup_complete=0",
                (datetime.now(timezone.utc).isoformat(), key),
            )
            return changed.rowcount == 1

    def finish(self, key, state, clean, *, deadline, lease):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT cancel_requested FROM executions WHERE task_digest=?", (key,)
            ).fetchone()
            if row is None:
                raise IsolationError()
            if state == "succeeded":
                if row[0]:
                    state = "cancelled"
                elif datetime.now(timezone.utc) >= lease:
                    state = "lease_lost"
                elif time.monotonic() >= deadline:
                    state = "timed_out"
            db.execute(
                "UPDATE executions SET state=?,cleanup_complete=?,cancel_requested=max(cancel_requested,?),updated_at=? WHERE task_digest=?",
                (
                    state,
                    int(clean),
                    int(
                        state
                        in (
                            "cancelled",
                            "timed_out",
                            "lease_lost",
                            "authority_unavailable",
                        )
                    ),
                    datetime.now(timezone.utc).isoformat(),
                    key,
                ),
            )
            return state

    def cancelled(self, key):
        with self.connection() as db:
            row = db.execute(
                "SELECT cancel_requested FROM executions WHERE task_digest=?", (key,)
            ).fetchone()
            return bool(row and row[0])

    def pending(self):
        with self.connection() as db:
            return db.execute(
                "SELECT task_digest,container_id,profile_digest,owner_nonce FROM executions WHERE cleanup_complete=0"
            ).fetchall()


def scope_key(scope):
    scope = TaskScope.model_validate(scope.model_dump())
    return hashlib.sha256(
        canonical(scope.model_dump(exclude={"lease_deadline"}))
    ).hexdigest()


class ExecutionRunner:
    def __init__(self, sandbox, catalog_path, catalog_digest, journal_root):
        self.sandbox = sandbox
        self.catalog_path = Path(catalog_path)
        self.catalog_digest = catalog_digest
        self.journal = ExecutionJournal(journal_root)

    @property
    def profile_digest(self):
        profile = ExecutionProfile.model_validate(self.sandbox.profile.model_dump())
        return (
            "sha256:"
            + hashlib.sha256(
                canonical(
                    {
                        "profile": profile.model_dump(),
                        "catalog_digest": self.catalog_digest,
                    }
                )
            ).hexdigest()
        )

    def cancel(self, scope):
        # The host owns this private journal; there is no unauthenticated HTTP port.
        return self.journal.request_cancel(scope_key(scope))

    def recover_pending(self):
        """Stop retained owned tasks after host restart; never resume their work."""
        recovered = []
        for key, name, _, nonce in self.journal.pending():
            clean = False
            try:
                self.sandbox.cleanup_deadline = (
                    time.monotonic() + self.sandbox.profile.cleanup_seconds
                )
                owned = self.sandbox.recover_owned(
                    name, key, nonce, container_id=self.journal.creation_reference(key)
                )
                if owned:
                    self.journal.acknowledge_creation(key, self.sandbox.owned_id(name))
                self.journal.set(key, "recovery_stopping", cancel=True)
                if (
                    owned
                    and self.sandbox.exists(name)
                    and self.sandbox.inspect(name)["State"].get("Running")
                ):
                    self.sandbox.terminate(name)
                if owned:
                    self.sandbox.remove(name)
                clean = True
                self.journal.set(key, "interrupted", cancel=True, clean=True)
            except Exception:
                try:
                    self.journal.set(key, "cleanup_failed", cancel=True, clean=clean)
                except Exception:
                    pass
            self.sandbox.cleanup_deadline = None
            recovered.append({"task_digest": key, "cleanup_complete": clean})
        return recovered

    def _call(self, function, deadline, lease):
        """Bound trusted callback latency without a blocking executor shutdown."""

        def check_deadlines():
            if datetime.now(timezone.utc) >= lease:
                raise _Stop("lease_lost")
            if time.monotonic() >= deadline:
                raise _Stop("timed_out")

        check_deadlines()
        if not _CALLBACK_SLOTS.acquire(blocking=False):
            raise _Stop("authority_unavailable")
        done = threading.Event()
        box = []

        def invoke():
            try:
                check_deadlines()
                box.append((True, function()))
            except BaseException:
                box.append((False, None))
            finally:
                _CALLBACK_SLOTS.release()
                done.set()

        threading.Thread(target=invoke, daemon=True, name="runner-authority").start()
        until = min(deadline, time.monotonic() + 0.5)
        while not done.wait(0.02):
            check_deadlines()
            if time.monotonic() >= until:
                raise _Stop("authority_unavailable")
        check_deadlines()
        if not box[0][0]:
            raise _Stop("authority_unavailable")
        return box[0][1]

    def execute(
        self,
        scope,
        command_id,
        parameters,
        source_snapshot,
        *,
        expected_profile_digest,
        credential_resolver=lambda: CollectorCredentials("qualification-collector"),
        authority_check=lambda: False,
        cancellation_check=lambda: False,
        custody_finalizer=None,
    ):
        from infra_automation.runner.catalog import (
            load_catalog,
            build_argv,
            CommandRequest,
        )
        from infra_automation.runner.source import SourceSnapshot

        try:
            scope = TaskScope.model_validate(scope.model_dump())
            profile = ExecutionProfile.model_validate(self.sandbox.profile.model_dump())
            lease = datetime.strptime(
                scope.lease_deadline, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            started_monotonic = time.monotonic()
            started_utc = datetime.now(timezone.utc)
            execution_deadline = min(
                lease, started_utc + timedelta(seconds=profile.timeout_seconds)
            )
            deadline = (
                started_monotonic + (execution_deadline - started_utc).total_seconds()
            )
            if datetime.now(timezone.utc) >= lease:
                raise IsolationError()
            if type(source_snapshot) is not SourceSnapshot:
                raise IsolationError()
            source_snapshot.verify()
            catalog = load_catalog(self.catalog_path, self.catalog_digest)
            if (
                expected_profile_digest != self.profile_digest
                or catalog.image_id != profile.image_id
            ):
                raise IsolationError()
            request = CommandRequest(command=command_id, **parameters)
            argv = build_argv(catalog, request)
            if request.command == "collect_plan" and not callable(custody_finalizer):
                raise IsolationError()
            source_snapshot.verify()
            self.sandbox.preflight()
            if (
                time.monotonic() >= deadline
                or datetime.now(timezone.utc) >= execution_deadline
            ):
                raise IsolationError()
            key = scope_key(scope)
            name = self.sandbox.reserve()
            profile_digest = (
                "sha256:"
                + hashlib.sha256(
                    canonical(
                        {
                            "profile": profile.model_dump(),
                            "catalog_digest": self.catalog_digest,
                        }
                    )
                ).hexdigest()
            )
            self.journal.begin(
                key, name, profile_digest, self.sandbox.reservation_nonce(name)
            )
        except (ValueError, TypeError, AttributeError, sqlite3.Error):
            raise IsolationError() from None
        process = None
        state = "failed"
        exit_code = None
        output = bytearray()
        text = ""
        checksum = None
        secret_values = ()
        clean = False
        created = False
        collected = None
        collection = None
        try:
            if self._call(authority_check, deadline, lease) is not True:
                raise _Stop("lease_lost")
            if self._call(cancellation_check, deadline, lease) is not False:
                raise _Stop("cancelled")
            source_snapshot.verify()
            self.sandbox.create(source_snapshot.path, name=name, task_digest=key)
            created = True
            self.journal.acknowledge_creation(key, self.sandbox.owned_id(name))
            if datetime.now(timezone.utc) >= lease:
                raise _Stop("lease_lost")
            if (
                time.monotonic() >= deadline
                or datetime.now(timezone.utc) >= execution_deadline
            ):
                raise _Stop("timed_out")
            self.journal.set(key, "prepared")
            process = self.sandbox.start(name)
            config = {
                "profile": profile.model_dump(),
                "pins": [p.model_dump() for p in catalog.files],
                "source_files": list(source_snapshot.files),
                "argv": list(argv),
                "lease_deadline": scope.lease_deadline,
                "execution_deadline": execution_deadline.strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "remaining_budget_seconds": max(0, deadline - time.monotonic()),
            }
            pending = canonical(config) + b"\n"
            if len(pending) > 65536:
                raise _Stop("failed")
            ready = False
            received = bytearray()
            total = 0
            next_check = 0.0
            with selectors.DefaultSelector() as selector:
                for stream in (process.stdout, process.stderr):
                    selector.register(stream, selectors.EVENT_READ)
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE)
                while selector.get_map():
                    if datetime.now(timezone.utc) >= lease:
                        raise _Stop("lease_lost")
                    if time.monotonic() >= deadline:
                        raise _Stop("timed_out")
                    if self.journal.cancelled(key):
                        raise _Stop("cancelled")
                    if time.monotonic() >= next_check:
                        if self._call(cancellation_check, deadline, lease) is not False:
                            raise _Stop("cancelled")
                        if self._call(authority_check, deadline, lease) is not True:
                            raise _Stop("lease_lost")
                        next_check = time.monotonic() + 0.2
                    for event, mask in selector.select(0.05):
                        stream = event.fileobj
                        if stream is process.stdin:
                            if pending:
                                try:
                                    written = os.write(stream.fileno(), pending[:4096])
                                except BrokenPipeError:
                                    written = 0
                                    pending = b""
                                pending = pending[written:]
                            if not pending:
                                selector.unregister(stream)
                                if ready:
                                    stream.close()
                            continue
                        chunk = os.read(stream.fileno(), 8192)
                        if not chunk:
                            selector.unregister(stream)
                            continue
                        total += len(chunk)
                        if total > profile.output_bytes + len(_READY):
                            raise _Stop("output_limit")
                        if not ready:
                            if stream is process.stderr:
                                raise _Stop("unsupported_profile")
                            received.extend(chunk)
                            if not _READY.startswith(
                                received
                            ) and not received.startswith(_READY):
                                raise _Stop("unsupported_profile")
                            if received == _READY:
                                source_snapshot.verify()
                                # Reopen protected catalog before any secret resolution.
                                load_catalog(self.catalog_path, self.catalog_digest)
                                if (
                                    self._call(authority_check, deadline, lease)
                                    is not True
                                ):
                                    raise _Stop("lease_lost")
                                credentials = self._call(
                                    credential_resolver, deadline, lease
                                )
                                if (
                                    type(credentials) is not CollectorCredentials
                                    or credentials.identity
                                    != profile.collector_identity
                                    or type(credentials.environment) is not dict
                                    or set(credentials.environment)
                                    - set(profile.credential_names)
                                ):
                                    raise _Stop("credential_denied")
                                if any(
                                    type(v) is not str
                                    or not v
                                    or len(v) > 4096
                                    or "\0" in v
                                    for v in credentials.environment.values()
                                ):
                                    raise _Stop("credential_denied")
                                credentials = CollectorCredentials(
                                    credentials.identity, dict(credentials.environment)
                                )
                                secret_values = tuple(credentials.environment.values())
                                if (
                                    self._call(authority_check, deadline, lease)
                                    is not True
                                ):
                                    raise _Stop("lease_lost")
                                pending = canonical(credentials.environment) + b"\n"
                                if len(pending) > 16384:
                                    raise _Stop("credential_denied")
                                ready = True
                                selector.register(process.stdin, selectors.EVENT_WRITE)
                                self.journal.set(key, "running")
                        else:
                            output.extend(chunk)
                exit_code = process.wait(timeout=0.5)
            if not ready:
                raise _Stop("unsupported_profile")
            if self._call(authority_check, deadline, lease) is not True:
                raise _Stop("lease_lost")
            details = self.sandbox.inspect(name)
            if details["State"].get("OOMKilled"):
                raise _Stop("memory_limit")
            if details["State"].get("Running"):
                raise _Stop("failed")
            if exit_code == 126:
                raise _Stop("output_limit")
            if exit_code == 124:
                raise _Stop("timed_out")
            if exit_code != 0:
                raise _Stop("failed")
            if request.command == "collect_plan":
                from infra_automation.runner.collection_output import (
                    parse_collection_output,
                )

                try:
                    collected = parse_collection_output(
                        bytes(output),
                        tool=request.tool,
                        version=argv[-1],
                        sensitive_values=secret_values,
                    )
                except ValueError:
                    raise _Stop("output_rejected") from None
                text = collected.screened_json.decode("utf-8")
                output.clear()
            else:
                text = bytes(output).decode("utf-8", errors="strict")
            if redact_text(text, sensitive_values=secret_values) != text:
                raise _Stop("output_rejected")
            if (
                self.journal.cancelled(key)
                or self._call(cancellation_check, deadline, lease) is not False
            ):
                raise _Stop("cancelled")
            checksum = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
            state = "succeeded"
        except _Stop as exc:
            state = exc.state
        except (Exception, KeyboardInterrupt):
            state = "failed"
        finally:
            # Persist closed cancellation intent before attempting to stop descendants.
            try:
                self.journal.set(
                    key,
                    "stopping" if state == "succeeded" else state,
                    cancel=state
                    in (
                        "cancelled",
                        "timed_out",
                        "lease_lost",
                        "authority_unavailable",
                    ),
                )
            except Exception:
                state = "journal_failed"
            self.sandbox.cleanup_deadline = time.monotonic() + profile.cleanup_seconds
            if created or self.sandbox.owns(name):
                try:
                    if self.sandbox.exists(name) and self.sandbox.inspect(name)[
                        "State"
                    ].get("Running"):
                        self.sandbox.terminate(name)
                    self.sandbox.remove(name)
                    clean = True
                except Exception:
                    clean = False
            else:
                clean = not self.sandbox.pending_creation(name)
            self.sandbox.cleanup_deadline = None
            if process is not None:
                if not kill_process(process):
                    clean = False
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
            if not clean:
                state = "cleanup_failed"
            if state == "succeeded":
                try:
                    if (
                        self.journal.cancelled(key)
                        or self._call(cancellation_check, deadline, lease) is not False
                    ):
                        state = "cancelled"
                    elif self._call(authority_check, deadline, lease) is not True:
                        state = "lease_lost"
                except _Stop as exc:
                    state = exc.state
                except Exception:
                    state = "failed"
            if state == "succeeded" and collected is not None:
                try:
                    source_snapshot.verify()
                    load_catalog(self.catalog_path, self.catalog_digest)
                    custody = self._call(
                        lambda: custody_finalizer(
                            collected.raw_plan,
                            collected.screened_json,
                            collected.exit_code,
                            collected.argv_digest,
                        ),
                        deadline,
                        lease,
                    )
                    from infra_automation.receiver_protocol import Custody

                    custody = Custody.model_validate(custody).model_dump(mode="json")
                    if (
                        custody["raw_local_digest"]
                        != "sha256:" + hashlib.sha256(collected.raw_plan).hexdigest()
                    ):
                        raise ValueError("Custody digest mismatch.")
                    if datetime.strptime(
                        custody["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
                        raise ValueError("Expired custody.")
                    custody_text = canonical(custody).decode("utf-8")
                    if (
                        redact_text(custody_text, sensitive_values=secret_values)
                        != custody_text
                    ):
                        raise ValueError("Invalid custody metadata.")
                    if self._call(authority_check, deadline, lease) is not True:
                        raise _Stop("lease_lost")
                    if self._call(cancellation_check, deadline, lease) is not False:
                        raise _Stop("cancelled")
                    collection = {
                        "tool": collected.tool,
                        "tool_version": collected.tool_version,
                        "exit_code": collected.exit_code,
                        "command_digest": collected.command_digest,
                        "argv_digest": collected.argv_digest,
                        "custody": custody,
                    }
                except _Stop as exc:
                    state = exc.state
                except Exception:
                    state = "custody_failed"
            try:
                state = self.journal.finish(
                    key, state, clean, deadline=deadline, lease=lease
                )
            except Exception:
                state = "journal_failed"
        if state != "succeeded" or not clean:
            text = ""
            checksum = None
            collection = None
        return ExecutionResult(
            state, exit_code, text, checksum, name, clean, profile_digest, collection
        )
