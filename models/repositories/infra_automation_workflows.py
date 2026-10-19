"""Scoped automation storage; authorization and commit belong to the caller."""

from __future__ import annotations

from datetime import datetime, timezone
import secrets
from typing import Any, cast

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from models.tables import (
    InfraAutomationAudit,
    InfraAutomationPolicy,
    InfraWorkflow,
    InfraWorkflowRevision,
)


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(timezone.utc)


def get_workflow(session: Session, workflow_id: str) -> InfraWorkflow | None:
    return session.scalar(
        select(InfraWorkflow)
        .where(InfraWorkflow.id == workflow_id)
        .execution_options(populate_existing=True)
    )


def create_workflow(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
    name: str,
    canonical_definition: bytes,
    digest: str,
    created_by: str,
    now: datetime | None = None,
) -> InfraWorkflow:
    timestamp = _now(now)
    row = InfraWorkflow(
        id=secrets.token_hex(24),
        project_id=project_id,
        workspace_id=workspace_id,
        name=name,
        draft_definition=canonical_definition,
        draft_digest=digest,
        draft_version=1,
        archived=False,
        created_by=created_by,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(row)
    session.flush()
    return row


def update_workflow(
    session: Session,
    *,
    workflow_id: str,
    expected_version: int,
    canonical_definition: bytes | None = None,
    digest: str | None = None,
    archived: bool | None = None,
    now: datetime | None = None,
) -> InfraWorkflow | None:
    """CAS also advances version for a publication that retains the same draft."""
    if (canonical_definition is None) != (digest is None):
        raise ValueError("Definition and digest must be supplied together")
    values = {"draft_version": InfraWorkflow.draft_version + 1, "updated_at": _now(now)}
    if canonical_definition is not None:
        values.update(draft_definition=canonical_definition, draft_digest=digest)
    if archived is not None:
        values["archived"] = archived
    result = session.execute(
        update(InfraWorkflow)
        .where(
            InfraWorkflow.id == workflow_id,
            InfraWorkflow.draft_version == expected_version,
        )
        .values(**values)
    )
    session.flush()
    return (
        get_workflow(session, workflow_id)
        if cast(CursorResult[Any], result).rowcount == 1
        else None
    )


def get_revision(session: Session, revision_id: str) -> InfraWorkflowRevision | None:
    return session.scalar(
        select(InfraWorkflowRevision)
        .where(InfraWorkflowRevision.id == revision_id)
        .execution_options(populate_existing=True)
    )


def get_publication(
    session: Session, *, published_by: str, idempotency_key_digest: str
) -> InfraWorkflowRevision | None:
    return session.scalar(
        select(InfraWorkflowRevision)
        .where(
            InfraWorkflowRevision.published_by == published_by,
            InfraWorkflowRevision.idempotency_key_digest == idempotency_key_digest,
        )
        .execution_options(populate_existing=True)
    )


def append_revision(
    session: Session,
    *,
    workflow_id: str,
    project_id: int,
    workspace_id: int | None,
    revision_number: int,
    canonical_definition: bytes,
    digest: str,
    published_by: str,
    idempotency_key_digest: str,
    request_digest: str,
    now: datetime | None = None,
) -> InfraWorkflowRevision:
    row = InfraWorkflowRevision(
        id=secrets.token_hex(24),
        workflow_id=workflow_id,
        project_id=project_id,
        workspace_id=workspace_id,
        revision_number=revision_number,
        canonical_definition=canonical_definition,
        digest=digest,
        published_by=published_by,
        idempotency_key_digest=idempotency_key_digest,
        request_digest=request_digest,
        created_at=_now(now),
    )
    session.add(row)
    session.flush()
    return row


def get_policy(session: Session, *, project_id: int) -> InfraAutomationPolicy | None:
    return session.scalar(
        select(InfraAutomationPolicy)
        .where(InfraAutomationPolicy.project_id == project_id)
        .execution_options(populate_existing=True)
    )


def save_policy(
    session: Session,
    *,
    project_id: int,
    expected_version: int,
    settings_json: str,
    restore: bool = False,
    now: datetime | None = None,
) -> InfraAutomationPolicy | None:
    row = get_policy(session, project_id=project_id)
    timestamp = _now(now)
    if row is None:
        if expected_version != 0:
            return None
        row = InfraAutomationPolicy(
            project_id=project_id,
            settings_json=settings_json,
            version=1,
            authorization_epoch=1,
            restore_epoch=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(row)
        session.flush()
        return row
    result = session.execute(
        update(InfraAutomationPolicy)
        .where(
            InfraAutomationPolicy.project_id == project_id,
            InfraAutomationPolicy.version == expected_version,
        )
        .values(
            settings_json=settings_json,
            version=InfraAutomationPolicy.version + 1,
            authorization_epoch=InfraAutomationPolicy.authorization_epoch + 1,
            restore_epoch=InfraAutomationPolicy.restore_epoch + int(restore),
            updated_at=timestamp,
        )
    )
    session.flush()
    return (
        get_policy(session, project_id=project_id)
        if cast(CursorResult[Any], result).rowcount == 1
        else None
    )


def bump_policy_epoch(
    session: Session,
    *,
    project_id: int,
    expected_version: int,
    restore: bool = False,
    now: datetime | None = None,
) -> InfraAutomationPolicy | None:
    row = get_policy(session, project_id=project_id)
    if row is None:
        return None
    return save_policy(
        session,
        project_id=project_id,
        expected_version=expected_version,
        settings_json=row.settings_json,
        restore=restore,
        now=now,
    )


def append_audit(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None,
    actor_principal_id: str,
    actor_type: str,
    actor_role: str,
    event_type: str,
    target_id: str,
    reason: str,
    before_digest: str | None = None,
    after_digest: str | None = None,
    now: datetime | None = None,
) -> InfraAutomationAudit:
    row = InfraAutomationAudit(
        id=secrets.token_hex(24),
        project_id=project_id,
        workspace_id=workspace_id,
        actor_principal_id=actor_principal_id,
        actor_type=actor_type,
        actor_role=actor_role,
        event_type=event_type,
        target_id=target_id,
        reason=reason,
        before_digest=before_digest,
        after_digest=after_digest,
        created_at=_now(now),
    )
    session.add(row)
    session.flush()
    return row


def _query(
    model,
    *,
    project_id: int | None = None,
    workspace_id: int | None = None,
    workflow_id: str | None = None,
    snapshot_sequence: int | None = None,
    before: tuple[datetime, str] | None = None,
):
    query = select(model)
    if project_id is not None:
        query = query.where(model.project_id == project_id)
    if workspace_id is not None:
        query = query.where(model.workspace_id == workspace_id)
    if workflow_id is not None:
        query = query.where(model.workflow_id == workflow_id)
    if snapshot_sequence is not None:
        query = query.where(model.sequence <= snapshot_sequence)
    if before is not None:
        query = query.where(
            or_(
                model.created_at < before[0],
                and_(model.created_at == before[0], model.id < before[1]),
            )
        )
    return query


def _page(session, model, *, limit=25, **filters):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Page limit must be between 1 and 100")
    return list(
        session.scalars(
            _query(model, **filters)
            .order_by(model.created_at.desc(), model.id.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
    )


def list_workflows(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    snapshot_sequence: int | None = None,
    before: tuple[datetime, str] | None = None,
    limit: int = 25,
) -> list[InfraWorkflow]:
    return _page(
        session,
        InfraWorkflow,
        project_id=project_id,
        workspace_id=workspace_id,
        snapshot_sequence=snapshot_sequence,
        before=before,
        limit=limit,
    )


def list_revisions(
    session: Session,
    *,
    workflow_id: str,
    snapshot_sequence: int | None = None,
    before: tuple[datetime, str] | None = None,
    limit: int = 25,
) -> list[InfraWorkflowRevision]:
    return _page(
        session,
        InfraWorkflowRevision,
        workflow_id=workflow_id,
        snapshot_sequence=snapshot_sequence,
        before=before,
        limit=limit,
    )


def list_audit(
    session: Session,
    *,
    project_id: int,
    workspace_id: int | None = None,
    snapshot_sequence: int | None = None,
    before: tuple[datetime, str] | None = None,
    limit: int = 25,
) -> list[InfraAutomationAudit]:
    return _page(
        session,
        InfraAutomationAudit,
        project_id=project_id,
        workspace_id=workspace_id,
        snapshot_sequence=snapshot_sequence,
        before=before,
        limit=limit,
    )


def maximum_sequence(session: Session, family: str, **filters) -> int:
    models: dict[
        str,
        type[InfraWorkflow] | type[InfraWorkflowRevision] | type[InfraAutomationAudit],
    ] = {
        "workflows": InfraWorkflow,
        "revisions": InfraWorkflowRevision,
        "audit": InfraAutomationAudit,
    }
    model = models[family]
    return (
        session.scalar(
            _query(model, **filters).with_only_columns(func.max(model.sequence))
        )
        or 0
    )


def workflow_max_sequence(
    session: Session, *, project_id: int, workspace_id: int | None = None
) -> int:
    return maximum_sequence(
        session, "workflows", project_id=project_id, workspace_id=workspace_id
    )


def revision_max_sequence(session: Session, *, workflow_id: str) -> int:
    return maximum_sequence(session, "revisions", workflow_id=workflow_id)


def audit_max_sequence(
    session: Session, *, project_id: int, workspace_id: int | None = None
) -> int:
    return maximum_sequence(
        session, "audit", project_id=project_id, workspace_id=workspace_id
    )


def count_workflows(session: Session, *, project_id: int) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(InfraWorkflow)
            .where(InfraWorkflow.project_id == project_id)
        )
        or 0
    )


def count_revisions(session: Session, *, workflow_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(InfraWorkflowRevision)
            .where(InfraWorkflowRevision.workflow_id == workflow_id)
        )
        or 0
    )


def max_revision_number(session: Session, *, workflow_id: str) -> int:
    return (
        session.scalar(
            select(func.max(InfraWorkflowRevision.revision_number)).where(
                InfraWorkflowRevision.workflow_id == workflow_id
            )
        )
        or 0
    )
