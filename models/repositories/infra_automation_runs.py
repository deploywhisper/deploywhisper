"""Engine persistence; caller supplies live authorization and commits transactions."""

from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.orm import Session
from infra_automation.contracts import STEP_CONTRACTS
from infra_automation.lifecycle import SnapshotExport, SnapshotDocument
from infra_automation.state import (
    AuditActor,
    OutputReference,
    TERMINAL_STATES,
    require_attempt_transition,
    require_run_transition,
)
from models.tables import (
    InfraAutomationRun,
    InfraAutomationAttempt,
    InfraAutomationRunRequest,
)
from models.repositories.infra_automation_workflows import append_audit
from services.infra_automation_support import canonical, digest


@contextmanager
def _atomic(session: Session):
    """A savepoint must never become SQLite's outermost committing transaction."""
    connection = session.connection()
    if (
        connection.dialect.name == "sqlite"
        and not connection.connection.driver_connection.in_transaction
    ):
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    with session.begin_nested():
        yield


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _binding_digest(row):
    fields = (
        "id",
        "run_id",
        "step_id",
        "state",
        "version",
        "snapshot_digest",
        "input_digest",
        "request_digest",
        "output_digest",
        "cancel_requested",
        "external_possible",
        "owner_id",
        "coordinator_generation",
        "fence",
        "attempt_number",
        "lease_until",
        "last_observed_at",
        "log_bytes",
        "last_log_sequence",
        "retained_bytes",
    )
    values = {}
    for key in fields:
        if hasattr(row, key):
            value = getattr(row, key)
            values[key] = (
                utc(value).isoformat() if isinstance(value, datetime) else value
            )
    for key in ("logs_json", "uploads_json"):
        if hasattr(row, key):
            values[key + "_digest"] = digest(getattr(row, key).encode("utf-8"))
    return digest(canonical(values))


def _audit(session, row, actor, reason, event, before=None, now=None):
    append_audit(
        session,
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        actor_principal_id=actor.principal_id,
        actor_type=actor.principal_type,
        actor_role=actor.role,
        event_type=event,
        target_id=row.id,
        reason=reason,
        before_digest=before,
        after_digest=_binding_digest(row),
        now=now,
    )


def get_run(session: Session, run_id: str) -> InfraAutomationRun | None:
    return session.scalar(
        select(InfraAutomationRun)
        .where(InfraAutomationRun.id == run_id)
        .execution_options(populate_existing=True)
    )


def get_attempt(session: Session, attempt_id: str) -> InfraAutomationAttempt | None:
    return session.scalar(
        select(InfraAutomationAttempt)
        .where(InfraAutomationAttempt.id == attempt_id)
        .execution_options(populate_existing=True)
    )


def get_request(
    session: Session,
    *,
    project_id: int,
    workspace_id: int,
    requested_by: str,
    key_digest: str,
    operation: str = "request",
) -> InfraAutomationRunRequest | None:
    return session.scalar(
        select(InfraAutomationRunRequest).where(
            InfraAutomationRunRequest.project_id == project_id,
            InfraAutomationRunRequest.workspace_id == workspace_id,
            InfraAutomationRunRequest.requested_by == requested_by,
            InfraAutomationRunRequest.operation == operation,
            InfraAutomationRunRequest.key_digest == key_digest,
        )
    )


def create_run(
    session: Session,
    *,
    snapshot: SnapshotExport,
    request_digest: str,
    key_digest: str,
    requested_by: str,
    deadline_at: datetime,
    audit_actor: AuditActor,
    reason: str,
    now: datetime | None = None,
) -> InfraAutomationRun:
    timestamp = utc(now or datetime.now(timezone.utc))
    document = SnapshotDocument.model_validate_json(snapshot.canonical_bytes)
    actual = "sha256:" + hashlib.sha256(snapshot.canonical_bytes).hexdigest()
    if (
        actual != snapshot.digest
        or document.definition_digest != snapshot.definition_digest
        or document.input_digest != snapshot.input_digest
        or document.authority.principal_id != requested_by
        or not timestamp < utc(deadline_at)
        or utc(deadline_at)
        > datetime.strptime(document.captured_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        + timedelta(seconds=document.policy.evidence_ttl_seconds)
        or len(snapshot.canonical_bytes) > 524288
    ):
        raise ValueError("Invalid immutable snapshot binding.")
    existing = get_request(
        session,
        project_id=document.project_id,
        workspace_id=document.workspace_id,
        requested_by=requested_by,
        key_digest=key_digest,
    )
    if existing:
        if existing.request_digest != request_digest:
            raise ValueError("Request key binding conflict.")
        return get_run(session, existing.run_id)
    with _atomic(session):
        row = InfraAutomationRun(
            id=secrets.token_hex(24),
            project_id=document.project_id,
            workspace_id=document.workspace_id,
            requested_by=requested_by,
            workflow_id=document.workflow_id,
            revision_id=document.revision_id,
            snapshot_bytes=snapshot.canonical_bytes,
            snapshot_digest=snapshot.digest,
            definition_digest=snapshot.definition_digest,
            input_digest=snapshot.input_digest,
            request_digest=request_digest,
            created_at=timestamp,
            deadline_at=utc(deadline_at),
            state="queued",
            version=1,
            updated_at=timestamp,
            last_observed_at=timestamp,
            cancel_requested=False,
            cancellation_requested_at=None,
            retained_bytes=len(snapshot.canonical_bytes),
            external_possible=False,
        )
        session.add(row)
        session.flush()
        session.add(
            InfraAutomationRunRequest(
                id=secrets.token_hex(24),
                project_id=row.project_id,
                workspace_id=row.workspace_id,
                requested_by=requested_by,
                operation="request",
                key_digest=key_digest,
                request_digest=request_digest,
                run_id=row.id,
                created_at=timestamp,
            )
        )
        _audit(session, row, audit_actor, reason, "engine.run_admitted", now=timestamp)
        session.flush()
    return row


def list_runs(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    workflow_id: str | None = None,
    snapshot_sequence: int | None = None,
    before: tuple[datetime, str] | None = None,
    limit: int = 25,
) -> list[InfraAutomationRun]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid page size.")
    query = select(InfraAutomationRun).where(
        InfraAutomationRun.project_id == project_id
    )
    if workspace_id is not None:
        query = query.where(InfraAutomationRun.workspace_id == workspace_id)
    if workflow_id is not None:
        query = query.where(InfraAutomationRun.workflow_id == workflow_id)
    if snapshot_sequence is not None:
        query = query.where(InfraAutomationRun.sequence <= snapshot_sequence)
    if before is not None:
        query = query.where(
            or_(
                InfraAutomationRun.created_at < before[0],
                and_(
                    InfraAutomationRun.created_at == before[0],
                    InfraAutomationRun.id < before[1],
                ),
            )
        )
    return list(
        session.scalars(
            query.order_by(
                InfraAutomationRun.created_at.desc(), InfraAutomationRun.id.desc()
            )
            .limit(limit)
            .execution_options(populate_existing=True)
        )
    )


def run_max_sequence(
    session: Session, *, project_id: int, workspace_id: int | None = None
) -> int:
    query = select(func.max(InfraAutomationRun.sequence)).where(
        InfraAutomationRun.project_id == project_id
    )
    if workspace_id is not None:
        query = query.where(InfraAutomationRun.workspace_id == workspace_id)
    return session.scalar(query) or 0


def list_attempts(session: Session, *, run_id: str) -> list[InfraAutomationAttempt]:
    return list(
        session.scalars(
            select(InfraAutomationAttempt)
            .where(InfraAutomationAttempt.run_id == run_id)
            .order_by(InfraAutomationAttempt.sequence)
            .execution_options(populate_existing=True)
        )
    )


def create_attempt(
    session: Session,
    *,
    run_id: str,
    step_id: str,
    handler_id: str,
    handler_version: str,
    retry_safe: bool,
    deadline_at: datetime,
    audit_actor: AuditActor,
    reason: str,
    now: datetime | None = None,
) -> InfraAutomationAttempt:
    run = get_run(session, run_id)
    timestamp = utc(now or datetime.now(timezone.utc))
    if (
        run is None
        or run.state not in ("queued", "running")
        or run.cancel_requested
        or not utc(run.last_observed_at) <= timestamp < utc(run.deadline_at)
        or not timestamp < utc(deadline_at) <= utc(run.deadline_at)
    ):
        raise ValueError("Attempt unavailable.")
    document = SnapshotDocument.model_validate_json(run.snapshot_bytes)
    step = next(
        (step for step in document.definition.steps if step.id == step_id), None
    )
    previous = [
        a for a in list_attempts(session, run_id=run_id) if a.step_id == step_id
    ]
    if (
        step is None
        or len(previous) >= 3
        or previous
        and (
            not previous[-1].retry_safe
            or previous[-1].state not in ("failed", "timed_out")
            or previous[-1].handler_id != handler_id
            or previous[-1].handler_version != handler_version
            or previous[-1].retry_safe != retry_safe
        )
    ):
        raise ValueError("Attempt binding unavailable.")
    with _atomic(session):
        row = InfraAutomationAttempt(
            id=secrets.token_hex(24),
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            requested_by=run.requested_by,
            run_id=run.id,
            step_id=step_id,
            step_kind=step.kind,
            attempt_number=max((a.attempt_number for a in previous), default=0) + 1,
            fence=max((a.fence for a in previous), default=0) + 1,
            handler_id=handler_id,
            handler_version=handler_version,
            retry_safe=retry_safe,
            input_digest=run.input_digest,
            created_at=timestamp,
            deadline_at=utc(deadline_at),
            state="pending",
            version=1,
            owner_id=None,
            owner_hash=None,
            coordinator_generation=0,
            lease_until=None,
            last_observed_at=timestamp,
            logs_json="[]",
            uploads_json="[]",
            output_json=None,
            output_digest=None,
            log_bytes=0,
            last_log_sequence=0,
        )
        session.add(row)
        session.flush()
        _audit(
            session, row, audit_actor, reason, "engine.attempt_created", now=timestamp
        )
    return row


def _successful(run, attempts):
    if run.external_possible:
        return False
    document = SnapshotDocument.model_validate_json(run.snapshot_bytes)
    for step in document.definition.steps:
        kind = STEP_CONTRACTS[step.kind].output
        if kind is None:
            return False
        matches = [
            a
            for a in attempts
            if a.step_id == step.id
            and a.state == "succeeded"
            and a.output_json is not None
        ]
        if not matches:
            return False
        output = OutputReference.model_validate_json(matches[-1].output_json)
        if output.kind != kind or output.digest != matches[-1].output_digest:
            return False
    return True


def transition_run(
    session: Session,
    *,
    run_id: str,
    expected_version: int,
    state: str,
    audit_actor: AuditActor,
    reason: str,
    now: datetime | None = None,
) -> InfraAutomationRun | None:
    row = get_run(session, run_id)
    timestamp = utc(now or datetime.now(timezone.utc))
    if row is None or row.version != expected_version:
        return None
    require_run_transition(row.state, state)
    if timestamp < utc(row.last_observed_at):
        raise ValueError("Clock moved backwards.")
    if state == "succeeded" and not _successful(
        row, list_attempts(session, run_id=run_id)
    ):
        raise ValueError("Success requires committed typed outputs.")
    before = _binding_digest(row)
    with _atomic(session):
        values = dict(
            state=state,
            version=expected_version + 1,
            updated_at=timestamp,
            last_observed_at=timestamp,
        )
        if state in ("handing_off", "external_running", "delivery_unknown"):
            values["external_possible"] = True
        if state == "cancelled":
            values.update(cancel_requested=True, cancellation_requested_at=timestamp)
        result = session.execute(
            update(InfraAutomationRun)
            .where(
                InfraAutomationRun.id == run_id,
                InfraAutomationRun.version == expected_version,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            return None
        _audit(
            session,
            row,
            audit_actor,
            reason,
            "engine.run_" + state,
            before=before,
            now=timestamp,
        )
        if state in TERMINAL_STATES or state == "delivery_unknown":
            for attempt in list_attempts(session, run_id=run_id):
                if attempt.state in ("pending", "claimed", "running"):
                    transition_attempt(
                        session,
                        attempt_id=attempt.id,
                        expected_version=attempt.version,
                        state="timed_out" if state == "timed_out" else "cancelled",
                        audit_actor=audit_actor,
                        reason=reason,
                        now=timestamp,
                    )
        session.flush()
    return get_run(session, run_id)


def transition_attempt(
    session: Session,
    *,
    attempt_id: str,
    expected_version: int,
    state: str,
    audit_actor: AuditActor,
    reason: str,
    now: datetime | None = None,
) -> InfraAutomationAttempt | None:
    row = get_attempt(session, attempt_id)
    timestamp = utc(now or datetime.now(timezone.utc))
    if row is None or row.version != expected_version:
        return None
    require_attempt_transition(row.state, state)
    if timestamp < utc(row.last_observed_at):
        raise ValueError("Clock moved backwards.")
    if state == "succeeded":
        required = STEP_CONTRACTS[row.step_kind].output
        if (
            required is None
            or row.output_json is None
            or OutputReference.model_validate_json(row.output_json).kind != required
        ):
            raise ValueError("Missing committed output.")
    before = _binding_digest(row)
    with _atomic(session):
        result = session.execute(
            update(InfraAutomationAttempt)
            .where(
                InfraAutomationAttempt.id == attempt_id,
                InfraAutomationAttempt.version == expected_version,
            )
            .values(
                state=state, version=expected_version + 1, last_observed_at=timestamp
            )
        )
        if result.rowcount != 1:
            return None
        _audit(
            session,
            row,
            audit_actor,
            reason,
            "engine.attempt_" + state,
            before=before,
            now=timestamp,
        )
        session.flush()
    return get_attempt(session, attempt_id)


def commit_output(
    session: Session,
    *,
    attempt_id: str,
    expected_version: int,
    output: OutputReference,
    audit_actor: AuditActor,
    reason: str,
    now: datetime | None = None,
) -> InfraAutomationAttempt | None:
    row = get_attempt(session, attempt_id)
    timestamp = utc(now or datetime.now(timezone.utc))
    if row is None:
        return None
    canonical = json.dumps(output.model_dump(), sort_keys=True, separators=(",", ":"))
    if row.output_json is not None:
        if row.output_json != canonical or row.output_digest != output.digest:
            raise ValueError("Output replay conflict.")
        return row
    if row.version != expected_version:
        return None
    if (
        row.state != "running"
        or output.kind != STEP_CONTRACTS[row.step_kind].output
        or timestamp < utc(row.last_observed_at)
        or timestamp >= utc(row.deadline_at)
    ):
        raise ValueError("Output unavailable.")
    before = _binding_digest(row)
    with _atomic(session):
        result = session.execute(
            update(InfraAutomationAttempt)
            .where(
                InfraAutomationAttempt.id == attempt_id,
                InfraAutomationAttempt.version == expected_version,
                InfraAutomationAttempt.output_json.is_(None),
            )
            .values(
                output_json=canonical,
                output_digest=output.digest,
                version=expected_version + 1,
                last_observed_at=timestamp,
            )
        )
        if result.rowcount != 1:
            return None
        _audit(
            session,
            row,
            audit_actor,
            reason,
            "engine.attempt_output",
            before=before,
            now=timestamp,
        )
    return get_attempt(session, attempt_id)
