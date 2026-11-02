"""Flush-only durable handoff intent and one-use receipt compare-and-swap."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from infra_automation.lifecycle import LifecycleError
from models.tables import (
    InfraAutomationGrant,
    InfraAutomationHandoff,
    InfraAutomationOutbox,
)
from services import project_service as authorization


def get_operation(session, operation_id):
    return session.get(InfraAutomationHandoff, operation_id, populate_existing=True)


def by_key(session, project_id, workspace_id, prepared_by, key_digest):
    return session.scalar(
        select(InfraAutomationHandoff)
        .where(
            InfraAutomationHandoff.project_id == project_id,
            InfraAutomationHandoff.workspace_id == workspace_id,
            InfraAutomationHandoff.prepared_by == prepared_by,
            InfraAutomationHandoff.key_digest == key_digest,
        )
        .execution_options(populate_existing=True)
    )


def by_approval(session, approval_id):
    return session.scalar(
        select(InfraAutomationHandoff)
        .where(
            InfraAutomationHandoff.approval_id == approval_id,
        )
        .execution_options(populate_existing=True)
    )


def by_run_step(session, run_id, step_id):
    return session.scalar(
        select(InfraAutomationHandoff)
        .where(
            InfraAutomationHandoff.run_id == run_id,
            InfraAutomationHandoff.step_id == step_id,
        )
        .execution_options(populate_existing=True)
    )


def get_grant(session, operation_id):
    return session.scalar(
        select(InfraAutomationGrant)
        .where(InfraAutomationGrant.operation_id == operation_id)
        .execution_options(populate_existing=True)
    )


def get_outbox(session, operation_id):
    return session.get(InfraAutomationOutbox, operation_id, populate_existing=True)


def _insert(session, row):
    authorization._require_operation(session)
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        raise LifecycleError(409) from None
    return row


def create_operation(session, **values):
    return _insert(session, InfraAutomationHandoff(**values))


def create_outbox(session, **values):
    return _insert(session, InfraAutomationOutbox(**values))


def create_grant(session, **values):
    return _insert(session, InfraAutomationGrant(**values))


def transition(session, row, *, state, now):
    authorization._require_operation(session)
    changed = session.execute(
        update(InfraAutomationHandoff)
        .where(
            InfraAutomationHandoff.id == row.id,
            InfraAutomationHandoff.version == row.version,
            InfraAutomationHandoff.state == row.state,
            InfraAutomationHandoff.broken.is_(False),
            InfraAutomationHandoff.last_observed_at <= now,
        )
        .values(state=state, version=row.version + 1, last_observed_at=now)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise LifecycleError(409)
    session.flush()
    return get_operation(session, row.id)


def transition_outbox(session, row, *, state, now):
    authorization._require_operation(session)
    values = dict(state=state, version=row.version + 1, updated_at=now)
    if row.attempted_at is None:
        values["attempted_at"] = now
    changed = session.execute(
        update(InfraAutomationOutbox)
        .where(
            InfraAutomationOutbox.operation_id == row.operation_id,
            InfraAutomationOutbox.version == row.version,
            InfraAutomationOutbox.state == row.state,
            InfraAutomationOutbox.updated_at <= now,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise LifecycleError(409)
    session.flush()
    return get_outbox(session, row.operation_id)


def consume_grant(session, row, *, receipt_bytes, receipt_digest, now):
    authorization._require_operation(session)
    changed = session.execute(
        update(InfraAutomationGrant)
        .where(
            InfraAutomationGrant.id == row.id,
            InfraAutomationGrant.version == row.version,
            InfraAutomationGrant.status == "available",
            InfraAutomationGrant.deadline_at > now,
        )
        .values(
            status="consumed",
            version=row.version + 1,
            consumed_at=now,
            receipt_bytes=receipt_bytes,
            receipt_digest=receipt_digest,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise LifecycleError(409)
    session.flush()
    return get_grant(session, row.operation_id)
