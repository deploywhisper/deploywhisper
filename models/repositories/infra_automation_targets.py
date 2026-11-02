"""Transaction-owned canonical target registry and retained admission primitives.

Callers authenticate, validate exact definition bytes and hold their reserved
operation transaction. These helpers flush; they never commit caller work.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from models.tables import (
    InfraAutomationRunTarget,
    InfraAutomationTarget,
    InfraAutomationTargetAlias,
    InfraAutomationTargetLock,
    InfraAutomationTargetScope,
)


def get_target(session: Session, target_id: str) -> InfraAutomationTarget | None:
    return session.scalar(
        select(InfraAutomationTarget)
        .where(InfraAutomationTarget.id == target_id)
        .execution_options(populate_existing=True)
    )


def resolve_alias(session: Session, alias: str) -> InfraAutomationTarget | None:
    return session.scalar(
        select(InfraAutomationTarget)
        .join(
            InfraAutomationTargetAlias,
            InfraAutomationTargetAlias.target_id == InfraAutomationTarget.id,
        )
        .where(
            InfraAutomationTargetAlias.alias == alias,
            InfraAutomationTargetAlias.active.is_(True),
        )
        .execution_options(populate_existing=True)
    )


def list_aliases(session: Session, target_id: str) -> list[InfraAutomationTargetAlias]:
    """Include retired reservations so consumers cannot mistake them as available."""
    return list(
        session.scalars(
            select(InfraAutomationTargetAlias)
            .where(InfraAutomationTargetAlias.target_id == target_id)
            .order_by(InfraAutomationTargetAlias.alias)
            .execution_options(populate_existing=True)
        )
    )


def list_scopes(session: Session, target_id: str) -> list[tuple[int, int]]:
    return [
        tuple(row)
        for row in session.execute(
            select(
                InfraAutomationTargetScope.project_id,
                InfraAutomationTargetScope.workspace_id,
            )
            .where(InfraAutomationTargetScope.target_id == target_id)
            .order_by(
                InfraAutomationTargetScope.project_id,
                InfraAutomationTargetScope.workspace_id,
            )
        )
    ]


def list_targets(
    session: Session, *, project_id: int, workspace_id: int
) -> list[InfraAutomationTarget]:
    return list(
        session.scalars(
            select(InfraAutomationTarget)
            .join(
                InfraAutomationTargetScope,
                InfraAutomationTargetScope.target_id == InfraAutomationTarget.id,
            )
            .where(
                InfraAutomationTargetScope.project_id == project_id,
                InfraAutomationTargetScope.workspace_id == workspace_id,
            )
            .order_by(InfraAutomationTarget.id)
            .execution_options(populate_existing=True)
        )
    )


def _assign(
    session: Session,
    *,
    target_id: str,
    aliases: Iterable[str],
    scopes: Iterable[tuple[int, int]],
    now: datetime,
) -> None:
    desired = set(aliases) | {target_id}
    existing = {row.alias: row for row in list_aliases(session, target_id)}
    for alias, row in existing.items():
        active = alias in desired
        if row.active != active:
            row.active = active
            row.version += 1
            row.updated_at = now
    for alias in sorted(desired - existing.keys()):
        session.add(
            InfraAutomationTargetAlias(
                alias=alias,
                target_id=target_id,
                active=True,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
    session.execute(
        delete(InfraAutomationTargetScope).where(
            InfraAutomationTargetScope.target_id == target_id
        )
    )
    session.add_all(
        InfraAutomationTargetScope(
            target_id=target_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        for project_id, workspace_id in sorted(set(scopes))
    )
    session.flush()


def create_target(
    session: Session,
    *,
    target_id: str,
    definition_bytes: bytes,
    definition_digest: str,
    enabled: bool,
    receiver_principal_id: str,
    created_by: str,
    aliases: Iterable[str],
    scopes: Iterable[tuple[int, int]],
    now: datetime,
) -> InfraAutomationTarget:
    row = InfraAutomationTarget(
        id=target_id,
        definition_bytes=definition_bytes,
        definition_digest=definition_digest,
        version=1,
        epoch=1,
        enabled=enabled,
        receiver_principal_id=receiver_principal_id,
        created_by=created_by,
        created_at=now,
        updated_at=now,
        last_observed_at=now,
    )
    session.add(row)
    session.flush()
    _assign(session, target_id=target_id, aliases=aliases, scopes=scopes, now=now)
    return row


def update_target(
    session: Session,
    *,
    target_id: str,
    expected_version: int,
    definition_bytes: bytes,
    definition_digest: str,
    enabled: bool,
    receiver_principal_id: str,
    aliases: Iterable[str],
    scopes: Iterable[tuple[int, int]],
    now: datetime,
) -> InfraAutomationTarget | None:
    changed = session.execute(
        update(InfraAutomationTarget)
        .where(
            InfraAutomationTarget.id == target_id,
            InfraAutomationTarget.version == expected_version,
            InfraAutomationTarget.last_observed_at <= now,
        )
        .values(
            definition_bytes=definition_bytes,
            definition_digest=definition_digest,
            enabled=enabled,
            receiver_principal_id=receiver_principal_id,
            version=InfraAutomationTarget.version + 1,
            epoch=InfraAutomationTarget.epoch + 1,
            updated_at=now,
            last_observed_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if cast(CursorResult, changed).rowcount != 1:
        return None
    _assign(session, target_id=target_id, aliases=aliases, scopes=scopes, now=now)
    return get_target(session, target_id)


def get_lock(session: Session, lock_id: str) -> InfraAutomationTargetLock | None:
    return session.scalar(
        select(InfraAutomationTargetLock)
        .where(InfraAutomationTargetLock.id == lock_id)
        .execution_options(populate_existing=True)
    )


def get_held_lock(session: Session, target_id: str) -> InfraAutomationTargetLock | None:
    return session.scalar(
        select(InfraAutomationTargetLock)
        .where(
            InfraAutomationTargetLock.target_id == target_id,
            InfraAutomationTargetLock.status == "held",
        )
        .execution_options(populate_existing=True)
    )


def acquire_lock(
    session: Session,
    *,
    lock_id: str,
    target_id: str,
    run_id: str,
    project_id: int,
    workspace_id: int,
    now: datetime,
    reason: str = "Run admission",
) -> InfraAutomationTargetLock:
    row = InfraAutomationTargetLock(
        id=lock_id,
        target_id=target_id,
        run_id=run_id,
        project_id=project_id,
        workspace_id=workspace_id,
        version=1,
        status="held",
        created_at=now,
        updated_at=now,
        reason=reason,
    )
    session.add(row)
    session.flush()
    return row


def resolve_lock(
    session: Session,
    *,
    lock_id: str,
    expected_version: int,
    status: str,
    reason: str,
    now: datetime,
) -> InfraAutomationTargetLock | None:
    if status not in {"resolved", "broken"}:
        raise ValueError("Lock resolution must be resolved or broken")
    changed = session.execute(
        update(InfraAutomationTargetLock)
        .where(
            InfraAutomationTargetLock.id == lock_id,
            InfraAutomationTargetLock.version == expected_version,
            InfraAutomationTargetLock.status == "held",
        )
        .values(
            status=status,
            reason=reason,
            version=InfraAutomationTargetLock.version + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    session.flush()
    return (
        get_lock(session, lock_id)
        if cast(CursorResult, changed).rowcount == 1
        else None
    )


def capture_run_target(
    session: Session,
    *,
    run_id: str,
    handoff_step_id: str,
    project_id: int,
    workspace_id: int,
    target_id: str,
    target_epoch: int,
    requested_alias: str,
    lock_id: str,
    snapshot_bytes: bytes,
    snapshot_digest: str,
    now: datetime,
) -> InfraAutomationRunTarget:
    row = InfraAutomationRunTarget(
        run_id=run_id,
        handoff_step_id=handoff_step_id,
        project_id=project_id,
        workspace_id=workspace_id,
        target_id=target_id,
        target_epoch=target_epoch,
        requested_alias=requested_alias,
        lock_id=lock_id,
        snapshot_bytes=snapshot_bytes,
        snapshot_digest=snapshot_digest,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def get_run_target(
    session: Session, run_id: str, handoff_step_id: str
) -> InfraAutomationRunTarget | None:
    return session.get(
        InfraAutomationRunTarget, (run_id, handoff_step_id), populate_existing=True
    )


def list_run_targets(session: Session, run_id: str) -> list[InfraAutomationRunTarget]:
    return list(
        session.scalars(
            select(InfraAutomationRunTarget)
            .where(InfraAutomationRunTarget.run_id == run_id)
            .order_by(InfraAutomationRunTarget.handoff_step_id)
            .execution_options(populate_existing=True)
        )
    )
