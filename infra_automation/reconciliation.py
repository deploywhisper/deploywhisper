"""Persisted carrier facts and receiver-only completion reconciliation."""

from __future__ import annotations
import json
from uuid import uuid4
from sqlalchemy import select, update
from infra_automation import claims
from infra_automation.lifecycle import LifecycleError
from infra_automation.state import AuditActor, OutputReference
from infra_automation.contracts import STEP_CONTRACTS
from infra_automation.targets import canonical
from models.tables import (
    InfraAutomationExternalFact,
    InfraAutomationRun,
    InfraAutomationAttempt,
)
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_handoffs as handoffs


def facts(session, operation_id, kind):
    return list(
        session.scalars(
            select(InfraAutomationExternalFact)
            .where(
                InfraAutomationExternalFact.operation_id == operation_id,
                InfraAutomationExternalFact.kind == kind,
            )
            .order_by(InfraAutomationExternalFact.sequence)
        )
    )


def latest(session, operation_id, kind):
    rows = facts(session, operation_id, kind)
    return json.loads(rows[-1].payload_bytes) if rows else None


def callback_states(session, operation_id):
    """Retained history is the monotonic action fence, never the latest projection."""
    return frozenset(
        json.loads(row.payload_bytes)["message"]["state"]
        for row in facts(session, operation_id, "callback")
    )


def retain(session, row, kind, value, now, *, sequence=None, nonce=None):
    rows = facts(session, row.id, kind)
    number = (
        sequence if sequence is not None else (rows[-1].sequence + 1 if rows else 1)
    )
    if number != (rows[-1].sequence + 1 if rows else 1) or session.scalar(
        select(InfraAutomationExternalFact.id).where(
            InfraAutomationExternalFact.operation_id == row.id,
            InfraAutomationExternalFact.nonce == (nonce or f"{kind}-{number}"),
        )
    ):
        raise LifecycleError(409)
    raw = canonical(value)
    run = runs.get_run(session, row.run_id)
    claims._charge(session, run, len(raw) + 512, now)
    return handoffs._insert(
        session,
        InfraAutomationExternalFact(
            id=uuid4().hex,
            operation_id=row.id,
            kind=kind,
            sequence=number,
            nonce=nonce or f"{kind}-{number}",
            payload_bytes=raw,
            created_at=now,
        ),
    )


def reconcile_parent(session, operation, now):
    """Only authenticated receiver completion calls this path, never generic claims."""
    run = runs.get_run(session, operation.run_id)
    if run is None or run.state not in {
        "handing_off",
        "external_running",
        "delivery_unknown",
    }:
        return
    callback = latest(session, operation.id, "callback")
    if (
        callback is None
        or callback["message"]["state"] != operation.state
        or operation.state not in {"succeeded", "failed"}
    ):
        return
    attempts = runs.list_attempts(session, run_id=run.id)
    for attempt in attempts:
        if (
            attempt.step_id == operation.step_id
            and attempt.step_kind == "registered_github_handoff"
            and attempt.state in {"pending", "claimed", "running"}
        ):
            changed_attempt = session.execute(
                update(InfraAutomationAttempt)
                .where(
                    InfraAutomationAttempt.id == attempt.id,
                    InfraAutomationAttempt.version == attempt.version,
                    InfraAutomationAttempt.last_observed_at <= now,
                )
                .values(
                    state=operation.state,
                    version=attempt.version + 1,
                    last_observed_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if changed_attempt.rowcount != 1:
                raise LifecycleError(409)
    from services.infra_automation_engine_service import _document

    document = _document(run)
    external = [
        step
        for step in document.definition.steps
        if step.kind == "registered_github_handoff"
    ]
    operations = [handoffs.by_run_step(session, run.id, step.id) for step in external]
    if not operations or any(
        row is None
        or row.broken
        or row.state not in {"succeeded", "failed"}
        or latest(session, row.id, "callback") is None
        for row in operations
    ):
        return
    attempts = runs.list_attempts(session, run_id=run.id)
    # All local prerequisites must already have durable typed completion. A
    # receiver cannot fill missing local evidence or advance unrelated siblings.
    local = [
        step
        for step in document.definition.steps
        if step.kind != "registered_github_handoff"
    ]
    for step in local:
        matches = [
            a
            for a in attempts
            if a.step_id == step.id
            and a.state == "succeeded"
            and a.output_json is not None
        ]
        if not matches:
            return
        output = OutputReference.model_validate_json(matches[-1].output_json)
        if (
            output.kind != STEP_CONTRACTS[step.kind].output
            or output.digest != matches[-1].output_digest
        ):
            return
    state = (
        "failed" if any(row.state == "failed" for row in operations) else "succeeded"
    )
    actor = AuditActor(operation.receiver_principal_id, "service", "coordinator")
    changed = session.execute(
        update(InfraAutomationRun)
        .where(
            InfraAutomationRun.id == run.id,
            InfraAutomationRun.version == run.version,
            InfraAutomationRun.last_observed_at <= now,
        )
        .values(
            state=state, version=run.version + 1, last_observed_at=now, updated_at=now
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise LifecycleError(409)
    runs._audit(
        session,
        run,
        actor,
        "Verified all receiver outcomes and local prerequisites",
        "engine.receiver_reconciled",
        now=now,
    )
