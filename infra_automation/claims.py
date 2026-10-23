"""Transaction-local private capabilities for the singleton durable engine.

Callers hold project_service.authorized_session through each operation and own
commit. Handles are process-local secrets, never public authority stamps.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

from sqlalchemy import select, update, func

from infra_automation.contracts import SAFE_INTEGER, STEP_CONTRACTS
from infra_automation import storage
import config
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.state import (
    CoordinatorHandle,
    EngineBounds,
    AttemptHandle,
    LogChunk,
    OutputReference,
)
from models.repositories import infra_automation_runs as repo
from models.tables import (
    InfraAutomationCoordinatorLease,
    InfraAutomationRun,
    ProjectWorkspace,
)
from services import project_service as authorization
from services import infra_automation_policy as policy
from services import infra_automation_engine_support as engine_support
from services import infra_automation_support as support

LEASE_SECONDS = 30
MAX_ATTEMPT_SECONDS = 600


def _now(value):
    value = datetime.now(timezone.utc) if value is None else value
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise LifecycleError(422)
    return value.astimezone(timezone.utc)


def _deny():
    raise LifecycleError(409)


def _counter(value):
    if type(value) is not int or not 1 <= value < SAFE_INTEGER:
        _deny()
    return value


def _hash(secret):
    if type(secret) is not str or len(secret) != 64:
        _deny()
    try:
        if len(bytes.fromhex(secret)) != 32:
            _deny()
    except ValueError:
        _deny()
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def _lease(session):
    authorization._require_operation(session)
    return session.scalar(
        select(InfraAutomationCoordinatorLease)
        .where(InfraAutomationCoordinatorLease.id == 1)
        .execution_options(populate_existing=True)
    )


def _coordinator(session, handle, now, *, allow_attempt=False):
    if type(handle) is not CoordinatorHandle and not (
        allow_attempt and type(handle) is AttemptHandle
    ):
        _deny()
    for value in (handle.generation,):
        _counter(value)
    if type(handle.owner_id) is not str:
        _deny()
    row = _lease(session)
    supplied = _hash(handle.owner_secret)
    if (
        row is None
        or row.owner_id != handle.owner_id
        or type(handle.generation) is not int
        or row.generation != handle.generation
        or not row.owner_hash
        or (
            type(handle) is CoordinatorHandle
            and not hmac.compare_digest(row.owner_hash, supplied)
        )
        or row.lease_until is None
        or not repo.utc(row.last_observed_at) <= now < repo.utc(row.lease_until)
    ):
        _deny()
    _counter(row.version)
    _counter(row.generation)
    return row


def _coordinator_digest(row):
    if row is None:
        return None
    return support.digest(
        support.canonical(
            {
                "generation": row.generation,
                "version": row.version,
                "owner_id": row.owner_id,
                "lease_until": repo.utc(row.lease_until).isoformat()
                if row.lease_until
                else None,
            }
        )
    )


def _lease_audit(session, row, project_id, workspace_id, event, before, now):
    if (
        type(project_id) is not int
        or type(workspace_id) is not int
        or session.scalar(
            select(ProjectWorkspace.id).where(
                ProjectWorkspace.id == workspace_id,
                ProjectWorkspace.project_id == project_id,
            )
        )
        is None
    ):
        _deny()
    actor = engine_support.engine_actor(session)
    repo.append_audit(
        session,
        project_id=project_id,
        workspace_id=workspace_id,
        actor_principal_id=actor.principal_id,
        actor_type=actor.principal_type,
        actor_role=actor.role,
        event_type=event,
        target_id="engine-coordinator",
        reason="Local engine coordinator ownership.",
        before_digest=before,
        after_digest=_coordinator_digest(row),
        now=now,
    )


def acquire_coordinator(session, *, project_id, workspace_id, now=None):
    timestamp = _now(now)
    row = _lease(session)
    engine_support.engine_actor(session)
    if row is not None:
        _counter(row.version)
        _counter(row.generation)
        if timestamp < repo.utc(row.last_observed_at):
            _deny()
        if (
            row.owner_id is not None
            and row.lease_until is not None
            and timestamp < repo.utc(row.lease_until)
        ):
            return None
    owner, secret = secrets.token_hex(24), secrets.token_hex(32)
    before = _coordinator_digest(row)
    with repo._atomic(session):
        if row is None:
            row = InfraAutomationCoordinatorLease(
                id=1,
                generation=1,
                version=1,
                owner_id=owner,
                owner_hash=_hash(secret),
                lease_until=timestamp + timedelta(seconds=LEASE_SECONDS),
                last_observed_at=timestamp,
            )
            session.add(row)
            session.flush()
        else:
            result = session.execute(
                update(InfraAutomationCoordinatorLease)
                .where(
                    InfraAutomationCoordinatorLease.id == 1,
                    InfraAutomationCoordinatorLease.version == row.version,
                )
                .values(
                    generation=row.generation + 1,
                    version=row.version + 1,
                    owner_id=owner,
                    owner_hash=_hash(secret),
                    lease_until=timestamp + timedelta(seconds=LEASE_SECONDS),
                    last_observed_at=timestamp,
                )
            )
            if result.rowcount != 1:
                return None
        _lease_audit(
            session,
            row,
            project_id,
            workspace_id,
            "engine.coordinator_acquired",
            before,
            timestamp,
        )
        session.flush()
    return CoordinatorHandle(owner, secret, row.generation)


def renew_coordinator(session, handle, *, project_id, workspace_id, now=None):
    timestamp = _now(now)
    row = _coordinator(session, handle, timestamp)
    before = _coordinator_digest(row)
    with repo._atomic(session):
        result = session.execute(
            update(InfraAutomationCoordinatorLease)
            .where(
                InfraAutomationCoordinatorLease.id == 1,
                InfraAutomationCoordinatorLease.version == row.version,
                InfraAutomationCoordinatorLease.generation == handle.generation,
            )
            .values(
                version=row.version + 1,
                lease_until=timestamp + timedelta(seconds=LEASE_SECONDS),
                last_observed_at=timestamp,
            )
        )
        if result.rowcount != 1:
            _deny()
        _lease_audit(
            session,
            row,
            project_id,
            workspace_id,
            "engine.coordinator_renewed",
            before,
            timestamp,
        )
    return True


def release_coordinator(session, handle, *, project_id, workspace_id, now=None):
    timestamp = _now(now)
    row = _coordinator(session, handle, timestamp)
    before = _coordinator_digest(row)
    with repo._atomic(session):
        result = session.execute(
            update(InfraAutomationCoordinatorLease)
            .where(
                InfraAutomationCoordinatorLease.id == 1,
                InfraAutomationCoordinatorLease.version == row.version,
                InfraAutomationCoordinatorLease.generation == handle.generation,
            )
            .values(
                version=row.version + 1,
                generation=row.generation + 1,
                owner_id=None,
                owner_hash=None,
                lease_until=None,
                last_observed_at=timestamp,
            )
        )
        if result.rowcount != 1:
            _deny()
        _lease_audit(
            session,
            row,
            project_id,
            workspace_id,
            "engine.coordinator_released",
            before,
            timestamp,
        )
    return True


def _run(session, run_id, now, *, live=True, operation="consume", active=True):
    row = repo.get_run(session, run_id)
    if row is None or now < repo.utc(row.last_observed_at):
        _deny()
    _counter(row.version)
    try:
        document = SnapshotDocument.model_validate_json(row.snapshot_bytes)
    except ValueError:
        raise LifecycleError(503) from None
    stamp = document.authority
    if support.digest(row.snapshot_bytes) != row.snapshot_digest or (
        document.project_id,
        document.workspace_id,
        document.workflow_id,
        document.revision_id,
        stamp.principal_id,
        document.input_digest,
        document.definition_digest,
    ) != (
        row.project_id,
        row.workspace_id,
        row.workflow_id,
        row.revision_id,
        row.requested_by,
        row.input_digest,
        row.definition_digest,
    ):
        raise LifecycleError(503)
    if active and (
        row.state not in ("queued", "running")
        or row.cancel_requested
        or row.external_possible
        or now >= repo.utc(row.deadline_at)
    ):
        _deny()
    if live:
        policy.check_live_policy(session, stamp, operation)
    return row, document


def validate_coordinator(session, coordinator, *, now=None):
    """Return only the current private owner's finite lease for local liveness."""
    timestamp = _now(now)
    row = _coordinator(session, coordinator, timestamp)
    return repo.utc(row.lease_until)


def start_run(session, coordinator, *, run_id, expected_version, now=None, bounds=None):
    timestamp = _now(now)
    _counter(expected_version)
    _coordinator(session, coordinator, timestamp)
    run, _ = _run(session, run_id, timestamp, operation="start")
    storage.ensure_capacity(session, bounds=bounds)
    if run.version != expected_version or run.state != "queued":
        return None
    return repo.transition_run(
        session,
        run_id=run_id,
        expected_version=expected_version,
        state="running",
        audit_actor=engine_support.engine_actor(session),
        reason="Local engine run started.",
        now=timestamp,
    )


def _dependencies(session, run, document, step_id):
    step = next((s for s in document.definition.steps if s.id == step_id), None)
    if step is None:
        _deny()
    attempts = repo.list_attempts(session, run_id=run.id)
    for dependency in step.depends_on:
        predecessor = next(s for s in document.definition.steps if s.id == dependency)
        required = STEP_CONTRACTS[predecessor.kind].output
        matches = [
            a
            for a in attempts
            if a.step_id == dependency
            and a.state == "succeeded"
            and a.output_json is not None
        ]
        if not matches or required is None:
            return False
        previous = matches[-1]
        try:
            output = OutputReference.model_validate_json(previous.output_json)
        except ValueError:
            raise LifecycleError(503) from None
        if output.kind != required or output.digest != previous.output_digest:
            return False
    return True


def _charge(session, run, delta, now, bounds=None):
    """Count persisted payload bytes including JSON delimiters, never delete evidence."""
    bounds = (
        config.engine_bounds()
        if bounds is None
        else support.revalidate(bounds, EngineBounds)
    )
    if type(delta) is not int or delta < 0 or now < repo.utc(run.last_observed_at):
        _deny()
    if delta:
        storage.ensure_capacity(session, additional_bytes=delta, bounds=bounds)
    counters = session.execute(
        select(
            InfraAutomationRun.retained_bytes,
            func.typeof(InfraAutomationRun.retained_bytes),
            func.length(InfraAutomationRun.snapshot_bytes),
        )
    )
    for retained, sql_type, snapshot_size in counters:
        if (
            sql_type != "integer"
            or type(retained) is not int
            or not 1 <= retained <= SAFE_INTEGER
            or type(snapshot_size) is not int
            or retained < snapshot_size
        ):
            raise LifecycleError(503)
    project_used = (
        session.scalar(
            select(func.sum(InfraAutomationRun.retained_bytes)).where(
                InfraAutomationRun.project_id == run.project_id
            )
        )
        or 0
    )
    global_used = (
        session.scalar(select(func.sum(InfraAutomationRun.retained_bytes))) or 0
    )
    if (
        project_used + delta > bounds.project_bytes
        or global_used + delta > bounds.global_bytes
    ):
        raise LifecycleError(429)
    if not delta:
        return
    _counter(run.version)
    before = repo._binding_digest(run)
    changed = session.execute(
        update(InfraAutomationRun)
        .where(
            InfraAutomationRun.id == run.id, InfraAutomationRun.version == run.version
        )
        .values(
            retained_bytes=run.retained_bytes + delta,
            version=run.version + 1,
            updated_at=now,
            last_observed_at=now,
        )
    )
    if changed.rowcount != 1:
        _deny()
    repo._audit(
        session,
        run,
        engine_support.engine_actor(session),
        "Local engine retained evidence charged.",
        "engine.storage_charged",
        before=before,
        now=now,
    )


def prepare_attempt(
    session,
    coordinator,
    *,
    run_id,
    step_id,
    handler_id,
    handler_version,
    retry_safe,
    attempt_timeout_seconds=300,
    now=None,
    bounds=None,
):
    """Prepare initial work from a trusted local registry, never request fields."""
    timestamp = _now(now)
    _coordinator(session, coordinator, timestamp)
    run, document = _run(session, run_id, timestamp, operation="claim")
    if (
        run.state != "running"
        or not _dependencies(session, run, document, step_id)
        or any(a.step_id == step_id for a in repo.list_attempts(session, run_id=run_id))
    ):
        return None
    if (
        type(attempt_timeout_seconds) is not int
        or not 1 <= attempt_timeout_seconds <= MAX_ATTEMPT_SECONDS
        or type(retry_safe) is not bool
        or type(handler_id) is not str
        or type(handler_version) is not str
        or not 1 <= len(handler_id) <= 128
        or not 1 <= len(handler_version) <= 128
    ):
        raise LifecycleError(422)
    support.screened_label(handler_id)
    support.screened_label(handler_version)
    with repo._atomic(session):
        row = repo.create_attempt(
            session,
            run_id=run_id,
            step_id=step_id,
            handler_id=handler_id,
            handler_version=handler_version,
            retry_safe=retry_safe,
            deadline_at=min(
                timestamp + timedelta(seconds=attempt_timeout_seconds),
                repo.utc(run.deadline_at),
            ),
            audit_actor=engine_support.engine_actor(session),
            reason="Local engine attempt prepared.",
            now=timestamp,
        )
        _charge(session, run, 4, timestamp, bounds)
        return row


def claim_attempt(session, coordinator, *, attempt_id, expected_version, now=None):
    _counter(expected_version)
    timestamp = _now(now)
    _coordinator(session, coordinator, timestamp)
    row = repo.get_attempt(session, attempt_id)
    if row is None or row.version != expected_version or row.state != "pending":
        return None
    run, document = _run(session, row.run_id, timestamp, operation="claim")
    if run.state != "running" or not _dependencies(session, run, document, row.step_id):
        return None
    if (
        (row.project_id, row.workspace_id, row.requested_by, row.input_digest)
        != (run.project_id, run.workspace_id, run.requested_by, run.input_digest)
        or not 1 <= row.attempt_number <= 3
        or not repo.utc(row.last_observed_at)
        <= timestamp
        < repo.utc(row.deadline_at)
        <= repo.utc(run.deadline_at)
        or repo.utc(row.deadline_at)
        > repo.utc(row.created_at) + timedelta(seconds=MAX_ATTEMPT_SECONDS)
    ):
        _deny()
    _counter(row.version)
    _counter(row.fence)
    secret = secrets.token_hex(32)
    before = repo._binding_digest(row)
    with repo._atomic(session):
        result = session.execute(
            update(type(row))
            .where(
                type(row).id == row.id,
                type(row).version == expected_version,
                type(row).state == "pending",
                type(row).coordinator_generation == 0,
            )
            .values(
                state="claimed",
                version=expected_version + 1,
                owner_id=coordinator.owner_id,
                owner_hash=_hash(secret),
                coordinator_generation=coordinator.generation,
                lease_until=min(
                    timestamp + timedelta(seconds=LEASE_SECONDS),
                    repo.utc(row.deadline_at),
                ),
                last_observed_at=timestamp,
            )
        )
        if result.rowcount != 1:
            return None
        repo._audit(
            session,
            row,
            engine_support.engine_actor(session),
            "Local engine attempt claimed.",
            "engine.attempt_claimed",
            before=before,
            now=timestamp,
        )
    return AttemptHandle(
        coordinator.owner_id,
        secret,
        coordinator.generation,
        row.project_id,
        row.workspace_id,
        row.requested_by,
        row.run_id,
        row.step_id,
        row.id,
        row.attempt_number,
        row.fence,
        document.authority.authorization_epoch,
        document.authority.restore_epoch,
    )


def _attempt(session, handle, now):
    if type(handle) is not AttemptHandle:
        _deny()
    for value in (
        handle.project_id,
        handle.workspace_id,
        handle.attempt_number,
        handle.fence,
        handle.authorization_epoch,
        handle.restore_epoch,
    ):
        _counter(value)
    for value in (
        handle.principal_id,
        handle.run_id,
        handle.step_id,
        handle.attempt_id,
    ):
        if type(value) is not str:
            _deny()
    _coordinator(session, handle, now, allow_attempt=True)
    row = repo.get_attempt(session, handle.attempt_id)
    if row is None:
        _deny()
    run, document = _run(session, handle.run_id, now)
    stamp = document.authority
    if (
        (
            row.project_id,
            row.workspace_id,
            row.requested_by,
            row.run_id,
            row.step_id,
            row.id,
            row.attempt_number,
            row.fence,
            row.coordinator_generation,
            row.owner_id,
        )
        != (
            handle.project_id,
            handle.workspace_id,
            handle.principal_id,
            handle.run_id,
            handle.step_id,
            handle.attempt_id,
            handle.attempt_number,
            handle.fence,
            handle.generation,
            handle.owner_id,
        )
        or (stamp.authorization_epoch, stamp.restore_epoch)
        != (handle.authorization_epoch, handle.restore_epoch)
        or row.owner_hash is None
        or not hmac.compare_digest(row.owner_hash, _hash(handle.owner_secret))
        or row.lease_until is None
        or not repo.utc(row.last_observed_at) <= now < repo.utc(row.lease_until)
        or now >= repo.utc(row.deadline_at)
    ):
        _deny()
    _counter(row.version)
    _counter(row.fence)
    return row


def _write(session, row, expected_version, values, event, now, bounds=None):
    if type(expected_version) is not int or row.version != expected_version:
        _deny()
    payload_delta = sum(
        len(values[key].encode("utf-8"))
        - len((getattr(row, key) or "").encode("utf-8"))
        for key in ("logs_json", "uploads_json", "output_json")
        if key in values
    )
    before = repo._binding_digest(row)
    with repo._atomic(session):
        result = session.execute(
            update(type(row))
            .where(
                type(row).id == row.id,
                type(row).version == expected_version,
                type(row).fence == row.fence,
                type(row).coordinator_generation == row.coordinator_generation,
            )
            .values(**values, version=expected_version + 1, last_observed_at=now)
        )
        if result.rowcount != 1:
            _deny()
        if payload_delta:
            _charge(
                session, repo.get_run(session, row.run_id), payload_delta, now, bounds
            )
        repo._audit(
            session,
            row,
            engine_support.engine_actor(session),
            "Local engine attempt mutation.",
            event,
            before=before,
            now=now,
        )
        session.flush()
    return repo.get_attempt(session, row.id)


def start_attempt(session, handle, *, expected_version, now=None, bounds=None):
    timestamp = _now(now)
    row = _attempt(session, handle, timestamp)
    storage.ensure_capacity(session, bounds=bounds)
    if row.state != "claimed":
        _deny()
    return _write(
        session,
        row,
        expected_version,
        {"state": "running"},
        "engine.attempt_started",
        timestamp,
    )


def heartbeat_attempt(session, handle, *, expected_version, now=None):
    timestamp = _now(now)
    row = _attempt(session, handle, timestamp)
    if row.state not in ("claimed", "running"):
        _deny()
    return _write(
        session,
        row,
        expected_version,
        {
            "lease_until": min(
                timestamp + timedelta(seconds=LEASE_SECONDS), repo.utc(row.deadline_at)
            )
        },
        "engine.attempt_heartbeat",
        timestamp,
    )


def append_log(session, handle, *, expected_version, chunk, now=None, bounds=None):
    _counter(expected_version)
    bounds = (
        config.engine_bounds()
        if bounds is None
        else support.revalidate(bounds, EngineBounds)
    )
    chunk = support.revalidate(chunk, LogChunk)
    timestamp = _now(now)
    row = _attempt(session, handle, timestamp)
    if row.state != "running" or chunk.sequence != row.last_log_sequence + 1:
        _deny()
    support.screened_label(chunk.text)
    logs = json.loads(row.logs_json)
    logs.append(chunk.model_dump())
    encoded = support.canonical(logs).decode()
    size = len(encoded.encode("utf-8"))
    if (
        size > bounds.attempt_log_bytes
        or len(chunk.text.encode("utf-8")) > bounds.log_chunk_utf8_bytes
    ):
        raise LifecycleError(429)
    return _write(
        session,
        row,
        expected_version,
        {"logs_json": encoded, "log_bytes": size, "last_log_sequence": chunk.sequence},
        "engine.attempt_log",
        timestamp,
        bounds,
    )


def register_upload(
    session, handle, *, expected_version, reference, now=None, bounds=None
):
    _counter(expected_version)
    reference = support.revalidate(reference, OutputReference)
    timestamp = _now(now)
    row = _attempt(session, handle, timestamp)
    if row.state != "running" or reference.kind != STEP_CONTRACTS[row.step_kind].output:
        _deny()
    support.screened_label(reference.reference)
    uploads = json.loads(row.uploads_json)
    value = reference.model_dump()
    if value in uploads:
        return row
    if len(uploads) >= 50 or any(
        item["reference"] == reference.reference for item in uploads
    ):
        _deny()
    uploads.append(value)
    return _write(
        session,
        row,
        expected_version,
        {"uploads_json": support.canonical(uploads).decode()},
        "engine.attempt_upload_reference",
        timestamp,
        bounds,
    )


def commit_output(session, handle, *, expected_version, output, now=None, bounds=None):
    _counter(expected_version)
    output = support.revalidate(output, OutputReference)
    timestamp = _now(now)
    row = _attempt(session, handle, timestamp)
    encoded = support.canonical(output.model_dump()).decode()
    if row.output_json is not None:
        if row.output_json != encoded or row.output_digest != output.digest:
            _deny()
        return row
    if (
        row.state != "running"
        or output.kind != STEP_CONTRACTS[row.step_kind].output
        or output.model_dump() not in json.loads(row.uploads_json)
    ):
        _deny()
    return _write(
        session,
        row,
        expected_version,
        {"output_json": encoded, "output_digest": output.digest},
        "engine.attempt_output",
        timestamp,
        bounds,
    )


def complete_attempt(session, handle, *, expected_version, state, now=None):
    _counter(expected_version)
    timestamp = _now(now)
    row = _attempt(session, handle, timestamp)
    if state not in ("succeeded", "failed", "timed_out", "cancelled"):
        _deny()
    if row.state == state and row.state in (
        "succeeded",
        "failed",
        "timed_out",
        "cancelled",
    ):
        return row
    if row.state != "running":
        _deny()
    if state == "succeeded":
        if row.output_json is None:
            _deny()
        output = OutputReference.model_validate_json(row.output_json)
        if (
            output.kind != STEP_CONTRACTS[row.step_kind].output
            or output.digest != row.output_digest
            or output.model_dump() not in json.loads(row.uploads_json)
        ):
            _deny()
    return _write(
        session,
        row,
        expected_version,
        {"state": state},
        "engine.attempt_" + state,
        timestamp,
    )


def safety_cleanup(
    session, coordinator, *, attempt_id, expected_version, state, now=None
):
    timestamp = _now(now)
    _coordinator(session, coordinator, timestamp)
    if state not in ("failed", "timed_out", "cancelled"):
        _deny()
    row = repo.get_attempt(session, attempt_id)
    if (
        row is None
        or row.state not in ("pending", "claimed", "running")
        or timestamp < repo.utc(row.last_observed_at)
    ):
        _deny()
    run, _ = _run(session, row.run_id, timestamp, live=False, active=False)
    if (row.project_id, row.workspace_id, row.requested_by, row.input_digest) != (
        run.project_id,
        run.workspace_id,
        run.requested_by,
        run.input_digest,
    ):
        _deny()
    return _write(
        session,
        row,
        expected_version,
        {"state": state, "lease_until": None},
        "engine.attempt_" + state,
        timestamp,
    )


def stop_run(session, coordinator, *, run_id, expected_version, state, now=None):
    """Current owner may only stop evidence; this never accepts results/effects."""
    timestamp = _now(now)
    _counter(expected_version)
    _coordinator(session, coordinator, timestamp)
    run, _ = _run(session, run_id, timestamp, live=False, active=False)
    if state not in ("failed", "expired", "timed_out", "cancelled", "delivery_unknown"):
        _deny()
    if run.external_possible or run.state in (
        "handing_off",
        "external_running",
        "delivery_unknown",
    ):
        if state != "delivery_unknown":
            _deny()
    elif state == "delivery_unknown":
        _deny()
    if run.state == state:
        return run
    try:
        return repo.transition_run(
            session,
            run_id=run_id,
            expected_version=expected_version,
            state=state,
            audit_actor=engine_support.engine_actor(session),
            reason="Local engine safety stop.",
            now=timestamp,
        )
    except LifecycleError:
        raise
    except ValueError:
        raise LifecycleError(409) from None


def finish_run(session, coordinator, *, run_id, expected_version, state, now=None):
    """Accept an authenticated local outcome while captured authority stays live."""
    timestamp = _now(now)
    _counter(expected_version)
    _coordinator(session, coordinator, timestamp)
    run, _ = _run(session, run_id, timestamp, operation="consume")
    if (
        state not in ("succeeded", "stopped_by_gate", "rejected")
        or run.state != "running"
    ):
        _deny()
    try:
        return repo.transition_run(
            session,
            run_id=run_id,
            expected_version=expected_version,
            state=state,
            audit_actor=engine_support.engine_actor(session),
            reason="Local engine run outcome accepted.",
            now=timestamp,
        )
    except LifecycleError:
        raise
    except ValueError:
        raise LifecycleError(409) from None


def prepare_retry(
    session,
    coordinator,
    *,
    previous_attempt_id,
    expected_version,
    attempt_timeout_seconds=300,
    now=None,
    bounds=None,
):
    """Create a successor from unchanged local bindings; never reopen old work."""
    timestamp = _now(now)
    _counter(expected_version)
    _coordinator(session, coordinator, timestamp)
    previous = repo.get_attempt(session, previous_attempt_id)
    if previous is None or previous.version != expected_version:
        return None
    run, document = _run(session, previous.run_id, timestamp, operation="claim")
    attempts = [
        row
        for row in repo.list_attempts(session, run_id=run.id)
        if row.step_id == previous.step_id
    ]
    if (
        run.state != "running"
        or not attempts
        or attempts[-1].id != previous.id
        or previous.state not in ("failed", "timed_out")
        or not previous.retry_safe
        or previous.step_kind == "registered_github_handoff"
        or len(attempts) >= 3
        or previous.attempt_number >= 3
        or not _dependencies(session, run, document, previous.step_id)
    ):
        return None
    if (
        type(attempt_timeout_seconds) is not int
        or not 1 <= attempt_timeout_seconds <= MAX_ATTEMPT_SECONDS
    ):
        raise LifecycleError(422)
    if (
        previous.project_id,
        previous.workspace_id,
        previous.requested_by,
        previous.input_digest,
    ) != (
        run.project_id,
        run.workspace_id,
        run.requested_by,
        run.input_digest,
    ) or timestamp < repo.utc(previous.last_observed_at):
        _deny()
    _counter(previous.fence)
    with repo._atomic(session):
        row = repo.create_attempt(
            session,
            run_id=run.id,
            step_id=previous.step_id,
            handler_id=previous.handler_id,
            handler_version=previous.handler_version,
            retry_safe=previous.retry_safe,
            deadline_at=min(
                timestamp + timedelta(seconds=attempt_timeout_seconds),
                repo.utc(run.deadline_at),
            ),
            audit_actor=engine_support.engine_actor(session),
            reason="Safe local engine retry prepared.",
            now=timestamp,
        )
        _charge(session, run, 4, timestamp, bounds)
        return row


def adopt_committed_output(session, handle, *, expected_version, now=None, bounds=None):
    """Link a prior immutable result under fresh ownership without invoking a handler."""
    timestamp = _now(now)
    _counter(expected_version)
    row = _attempt(session, handle, timestamp)
    if row.state != "running":
        _deny()
    if row.output_json is not None:
        output = OutputReference.model_validate_json(row.output_json)
        return commit_output(
            session,
            handle,
            expected_version=expected_version,
            output=output,
            now=timestamp,
            bounds=bounds,
        )
    if row.version != expected_version:
        _deny()
    previous = [
        candidate
        for candidate in repo.list_attempts(session, run_id=row.run_id)
        if candidate.step_id == row.step_id
        and candidate.attempt_number < row.attempt_number
        and candidate.output_json is not None
    ]
    if not previous:
        return None
    source = previous[-1]
    if (
        not row.retry_safe
        or not source.retry_safe
        or source.state not in ("failed", "timed_out")
        or (
            source.project_id,
            source.workspace_id,
            source.requested_by,
            source.handler_id,
            source.handler_version,
            source.input_digest,
            source.step_kind,
        )
        != (
            row.project_id,
            row.workspace_id,
            row.requested_by,
            row.handler_id,
            row.handler_version,
            row.input_digest,
            row.step_kind,
        )
    ):
        _deny()
    try:
        output = OutputReference.model_validate_json(source.output_json)
        registered = json.loads(source.uploads_json)
    except (ValueError, TypeError):
        raise LifecycleError(503) from None
    if (
        output.kind != STEP_CONTRACTS[row.step_kind].output
        or output.digest != source.output_digest
        or output.model_dump() not in registered
    ):
        raise LifecycleError(503)
    with repo._atomic(session):
        row = register_upload(
            session,
            handle,
            expected_version=expected_version,
            reference=output,
            now=timestamp,
            bounds=bounds,
        )
        return commit_output(
            session,
            handle,
            expected_version=row.version,
            output=output,
            now=timestamp,
            bounds=bounds,
        )


def begin_external(session, handle, *, expected_version, now=None, bounds=None):
    """Persist uncertainty before the sole trusted external-capable local double."""
    timestamp = _now(now)
    _counter(expected_version)
    row = _attempt(session, handle, timestamp)
    storage.ensure_capacity(session, bounds=bounds)
    if (
        row.version != expected_version
        or row.state != "running"
        or row.step_kind != "registered_github_handoff"
        or row.retry_safe
        or row.output_json is not None
    ):
        _deny()
    run, document = _run(session, row.run_id, timestamp, operation="dispatch")
    if run.state != "running" or not _dependencies(session, run, document, row.step_id):
        _deny()
    return repo.transition_run(
        session,
        run_id=run.id,
        expected_version=run.version,
        state="handing_off",
        audit_actor=engine_support.engine_actor(session),
        reason="Trusted local external double invocation recorded.",
        now=timestamp,
    )
