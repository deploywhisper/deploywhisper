"""Transaction-local durable decision generations; callers own live authorization."""

from __future__ import annotations

from uuid import uuid4
from sqlalchemy import select, update, func, and_, or_
from sqlalchemy.exc import IntegrityError

from infra_automation.decisions import (
    DecisionBinding,
    binding_bytes,
    content_digest,
    effective_deadline,
    utc_now,
)
from infra_automation.lifecycle import LifecycleError
from models.tables import InfraAutomationDecision
from services import project_service as authorization


def get_request(session, decision_id):
    return session.scalar(
        select(InfraAutomationDecision)
        .where(InfraAutomationDecision.id == decision_id)
        .execution_options(populate_existing=True)
    )


def max_sequence(session, project_id, workspace_id=None):
    query = select(func.max(InfraAutomationDecision.sequence)).where(
        InfraAutomationDecision.project_id == project_id
    )
    if workspace_id is not None:
        query = query.where(InfraAutomationDecision.workspace_id == workspace_id)
    return session.scalar(query) or 0


def list_requests(
    session,
    project_id,
    workspace_id=None,
    *,
    snapshot_sequence=None,
    before=None,
    limit=100,
):
    statement = select(InfraAutomationDecision).where(
        InfraAutomationDecision.project_id == project_id
    )
    if workspace_id is not None:
        statement = statement.where(
            InfraAutomationDecision.workspace_id == workspace_id
        )
    if snapshot_sequence is not None:
        statement = statement.where(
            InfraAutomationDecision.sequence <= snapshot_sequence
        )
    if before is not None:
        statement = statement.where(
            or_(
                InfraAutomationDecision.created_at < before[0],
                and_(
                    InfraAutomationDecision.created_at == before[0],
                    InfraAutomationDecision.id < before[1],
                ),
            )
        )
    return list(
        session.scalars(
            statement.order_by(
                InfraAutomationDecision.created_at.desc(),
                InfraAutomationDecision.id.desc(),
            ).limit(min(limit, 100))
        )
    )


def list_latest_for_run(session, run_id):
    """Resolve each required action without applying an inbox page limit."""
    latest = (
        select(
            InfraAutomationDecision.step_id.label("step_id"),
            func.max(InfraAutomationDecision.generation).label("generation"),
        )
        .where(InfraAutomationDecision.run_id == run_id)
        .group_by(InfraAutomationDecision.step_id)
        .subquery()
    )
    return list(
        session.scalars(
            select(InfraAutomationDecision)
            .join(
                latest,
                and_(
                    InfraAutomationDecision.step_id == latest.c.step_id,
                    InfraAutomationDecision.generation == latest.c.generation,
                ),
            )
            .where(InfraAutomationDecision.run_id == run_id)
        )
    )


def _create_request(
    session,
    binding,
    *,
    run_id,
    step_id,
    requested_by,
    report_bytes,
    now=None,
    allow_expired=False,
):
    authorization._require_operation(session)
    raw = binding_bytes(binding)
    binding = DecisionBinding.model_validate_json(raw)
    timestamp = utc_now(now)
    if not allow_expired and timestamp >= effective_deadline(binding):
        raise LifecycleError(409)
    if (
        type(report_bytes) is not bytes
        or not 0 < len(report_bytes) <= 8388608
        or content_digest(report_bytes) != binding.report_bytes_digest
    ):
        raise LifecycleError(409)
    if len(raw) > 131072:
        raise LifecycleError(422)
    existing = session.scalar(
        select(InfraAutomationDecision).where(
            InfraAutomationDecision.run_id == run_id,
            InfraAutomationDecision.step_id == step_id,
            InfraAutomationDecision.status == "pending",
        )
    )
    if existing:
        if (
            existing.binding_bytes == raw
            and existing.requested_by == requested_by
            and existing.report_bytes == report_bytes
        ):
            return existing
        raise LifecycleError(409)
    generation = (
        session.scalar(
            select(func.max(InfraAutomationDecision.generation)).where(
                InfraAutomationDecision.run_id == run_id,
                InfraAutomationDecision.step_id == step_id,
            )
        )
        or 0
    ) + 1
    row = InfraAutomationDecision(
        id=uuid4().hex,
        run_id=run_id,
        step_id=step_id,
        project_id=binding.project_id,
        workspace_id=binding.workspace_id,
        requested_by=requested_by,
        report_id=binding.report_id,
        generation=generation,
        version=1,
        status="pending",
        binding_bytes=raw,
        binding_digest=content_digest(raw),
        report_bytes=report_bytes,
        report_digest=binding.report_bytes_digest,
        reviewer_id=None,
        reason=None,
        created_at=timestamp,
        deadline_at=effective_deadline(binding),
        decided_at=None,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        raise LifecycleError(409) from None
    return row


def create_request(
    session, binding, *, run_id, step_id, requested_by, report_bytes, now=None
):
    return _create_request(
        session,
        binding,
        run_id=run_id,
        step_id=step_id,
        requested_by=requested_by,
        report_bytes=report_bytes,
        now=now,
    )


def create_denied_request(
    session,
    binding,
    *,
    run_id,
    step_id,
    requested_by,
    report_bytes,
    reason_codes,
    now=None,
):
    """Retain failed policy evaluation without ever returning pending authority."""
    import json
    from infra_automation.approval_eligibility import eligibility_from_reasons

    projection = eligibility_from_reasons(reason_codes)
    if projection.eligible:
        raise LifecycleError(422)
    row = _create_request(
        session,
        binding,
        run_id=run_id,
        step_id=step_id,
        requested_by=requested_by,
        report_bytes=report_bytes,
        now=now,
        allow_expired=True,
    )
    status = (
        "expired"
        if any(
            code in projection.reasons
            for code in (
                "stale_evidence",
                "approval_expired",
                "source_expired",
                "custody_expired",
            )
        )
        else "invalidated"
    )
    return invalidate(
        session,
        row.id,
        expected_version=row.version,
        status=status,
        reason=json.dumps(projection.reasons, separators=(",", ":")),
        now=now,
    )


def invalidate(
    session, decision_id, *, expected_version, status="invalidated", reason, now=None
):
    authorization._require_operation(session)
    if status not in ("invalidated", "expired", "superseded"):
        raise LifecycleError(422)
    return _transition(
        session, decision_id, expected_version, status, None, reason, utc_now(now)
    )


def _transition(
    session,
    decision_id,
    version,
    status,
    reviewer,
    reason,
    timestamp,
    authentication_version=None,
    authorization_version=None,
    decision_kind=None,
):
    if (
        type(version) is not int
        or version < 1
        or type(reason) is not str
        or not 1 <= len(reason) <= 2048
    ):
        raise LifecycleError(422)
    result = session.execute(
        update(InfraAutomationDecision)
        .where(
            InfraAutomationDecision.id == decision_id,
            InfraAutomationDecision.version == version,
            InfraAutomationDecision.status == "pending",
        )
        .values(
            status=status,
            version=version + 1,
            decision_kind=decision_kind,
            reviewer_id=reviewer,
            reviewer_authentication_version=authentication_version,
            reviewer_authorization_version=authorization_version,
            reason=reason,
            decided_at=timestamp,
        )
    )
    if result.rowcount != 1:
        raise LifecycleError(409)
    session.flush()
    return get_request(session, decision_id)


def decide(
    session,
    decision_id,
    *,
    expected_version,
    binding_digest,
    reviewer_id,
    reviewer_authentication_version,
    reviewer_authorization_version,
    decision_kind,
    outcome,
    reason,
    now=None,
):
    authorization._require_operation(session)
    if any(
        type(value) is not int or value < 1
        for value in (reviewer_authentication_version, reviewer_authorization_version)
    ):
        raise LifecycleError(422)
    if decision_kind not in ("independent-approval", "acknowledgement"):
        raise LifecycleError(422)
    row = get_request(session, decision_id)
    timestamp = utc_now(now)
    if row is None or row.binding_digest != binding_digest:
        raise LifecycleError(409)
    binding = DecisionBinding.model_validate_json(row.binding_bytes)
    if (
        content_digest(row.binding_bytes) != row.binding_digest
        or content_digest(row.report_bytes) != binding.report_bytes_digest
        or timestamp >= effective_deadline(binding)
    ):
        raise LifecycleError(409)
    if (
        outcome not in ("approve", "reject")
        or type(reviewer_id) is not str
        or not reviewer_id
    ):
        raise LifecycleError(422)
    return _transition(
        session,
        decision_id,
        expected_version,
        {"approve": "approved", "reject": "rejected"}[outcome],
        reviewer_id,
        reason,
        timestamp,
        reviewer_authentication_version,
        reviewer_authorization_version,
        decision_kind,
    )
