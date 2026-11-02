"""Verified registry administration and transaction-bound canonical run locks."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import secrets
from typing import Any, cast
from infra_automation.run_resolution import resolve_target_value

from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError

import config
from infra_automation.decisions import content_digest, utc_now
from infra_automation.lifecycle import (
    LifecycleError,
    SnapshotDocument,
    REASON_MAX_LENGTH,
)
from infra_automation.lifecycle_cursors import cursor_store
from infra_automation.state import EngineBounds
from infra_automation.targets import (
    BreakLockRequest,
    RegisterTargetRequest,
    TargetDefinition,
    TargetPage,
    TargetSnapshot,
    TargetSummary,
    TargetView,
    TargetLockView,
    canonical,
    checked,
    target_definition_bytes,
    target_snapshot_bytes,
)
from models.repositories import infra_automation_targets as repository
from models.tables import (
    IdentityAccount,
    InfraAutomationTarget,
    InfraAutomationTargetScope,
    ProjectWorkspace,
    Project,
    InfraAutomationHandoff,
    InfraAutomationGrant,
    InfraAutomationRun,
    InfraAutomationRunTarget,
)
from services import infra_automation_support as support
from services import project_service as authorization


def _instant(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _now(now: datetime | None = None) -> datetime:
    try:
        return utc_now(now)
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def _admin(
    session: Session, project_id: int, workspace_id: int, *, mutation: bool
) -> authorization.TrustedProjectScope:
    grant = support.scope(
        session, project_id, workspace_id, "automation.admin", mutation=mutation
    )
    if grant.principal.principal_type != "human" or not grant.principal.is_admin:
        raise authorization.TrustedAuthorizationError()
    authorization.guard_global_configuration(session, mutation=mutation)
    return grant


def _screen(value: Any) -> None:
    if isinstance(value, str):
        support.screened_label(value)
    elif isinstance(value, dict):
        for child in value.values():
            _screen(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _screen(child)


def _definition(row: InfraAutomationTarget) -> TargetDefinition:
    try:
        value = TargetDefinition.model_validate_json(row.definition_bytes)
        if (
            target_definition_bytes(value) != row.definition_bytes
            or content_digest(row.definition_bytes) != row.definition_digest
            or value.canonical_target != row.id
            or value.enabled != row.enabled
        ):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def _receiver_id(receiver_id: str) -> str:
    return "iarecv-" + hashlib.sha256(receiver_id.encode()).hexdigest()[:48]


def _receiver_actor(
    session: Session, receiver_id: str, now: datetime
) -> IdentityAccount:
    actor_id = _receiver_id(receiver_id)
    row = session.get(IdentityAccount, actor_id, populate_existing=True)
    if row is None:
        username = "infra-receiver-" + actor_id[7:]
        if session.scalar(
            select(IdentityAccount.id).where(IdentityAccount.username == username)
        ):
            raise LifecycleError(503)
        row = IdentityAccount(
            id=actor_id,
            username=username,
            principal_type="service",
            enabled=True,
            is_admin=False,
            authentication_version=1,
            password_verifier="unusable:" + secrets.token_hex(32),
            created_at=now,
        )
        session.add(row)
        session.flush()
    if row.principal_type != "service" or not row.enabled or row.is_admin:
        raise LifecycleError(503)
    return row


def _view(
    row: InfraAutomationTarget, project_id: int, workspace_id: int, session: Session
) -> dict[str, Any]:
    lock = repository.get_held_lock(session, row.id)
    lock_view = None
    if lock is not None:
        _admin(session, lock.project_id, lock.workspace_id, mutation=False)
        lock_view = TargetLockView(
            id=lock.id,
            target_id=lock.target_id,
            run_id=lock.run_id,
            project_id=lock.project_id,
            workspace_id=lock.workspace_id,
            version=lock.version,
            status=lock.status,
            created_at=support.utc(lock.created_at),
            updated_at=support.utc(lock.updated_at),
        )
    return TargetView(
        lock=lock_view,
        id=row.id,
        version=row.version,
        epoch=row.epoch,
        project_id=project_id,
        workspace_id=workspace_id,
        definition=_definition(row),
        definition_digest=row.definition_digest,
        receiver_principal_id=row.receiver_principal_id,
        created_at=support.utc(row.created_at),
        updated_at=support.utc(row.updated_at),
    ).model_dump(mode="json")


def _state(row: InfraAutomationTarget) -> str:
    return content_digest(
        canonical(
            {
                "id": row.id,
                "version": row.version,
                "epoch": row.epoch,
                "definition_digest": row.definition_digest,
                "enabled": row.enabled,
                "receiver": row.receiver_principal_id,
            }
        )
    )


def register_target(
    request: RegisterTargetRequest, *, now: datetime | None = None
) -> dict[str, Any]:
    try:
        request = checked(request, RegisterTargetRequest)
    except (ValueError, TypeError):
        raise LifecycleError(422) from None
    timestamp = _now(now)
    try:
        with authorization.authorized_session() as session:
            grant = _admin(
                session, request.project_id, request.workspace_id, mutation=True
            )
            support.screened_label(request.reason)
            _screen(request.definition.model_dump(mode="json"))
            definition = request.definition
            scopes = {
                (scope.project_id, scope.workspace_id)
                for scope in definition.allowed_scopes
            }
            if (request.project_id, request.workspace_id) not in scopes:
                raise authorization.TrustedAuthorizationError()
            for project_id, workspace_id in sorted(scopes):
                _admin(session, project_id, workspace_id, mutation=True)
                workspace = session.get(ProjectWorkspace, workspace_id)
                if workspace is None or workspace.project_id != project_id:
                    raise authorization.TrustedAuthorizationError()
                project = session.get(Project, project_id)
                if project is None:
                    raise authorization.TrustedAuthorizationError()
                project.authorization_required = True
            try:
                allowed = config.handoff_allowed_origins()
            except (ValueError, TypeError):
                raise LifecycleError(503) from None
            if definition.api_origin not in allowed:
                raise LifecycleError(422)
            current = repository.get_target(session, definition.canonical_target)
            if current is None:
                if request.expected_version != 0:
                    raise LifecycleError(409)
                count = (
                    session.scalar(
                        select(func.count()).select_from(InfraAutomationTarget)
                    )
                    or 0
                )
                if count >= 1000:
                    raise LifecycleError(429)
            elif request.expected_version != current.version:
                raise LifecycleError(409)
            if current is not None and timestamp < _instant(current.last_observed_at):
                raise LifecycleError(503)
            raw = target_definition_bytes(definition)
            if len(raw) > 32768:
                raise LifecycleError(429)
            from infra_automation.storage import ensure_capacity

            ensure_capacity(
                session,
                additional_bytes=len(raw)
                + len(
                    canonical({"aliases": definition.aliases, "scopes": list(scopes)})
                ),
            )
            actor = _receiver_actor(session, definition.receiver_id, timestamp)
            before = _state(current) if current is not None else None
            values: dict[str, Any] = dict(
                target_id=definition.canonical_target,
                definition_bytes=raw,
                definition_digest=content_digest(raw),
                enabled=definition.enabled,
                receiver_principal_id=actor.id,
                aliases=definition.aliases,
                scopes=scopes,
                now=timestamp,
            )
            if current is None:
                row = repository.create_target(
                    session, created_by=grant.principal.principal_id, **values
                )
            else:
                updated = repository.update_target(
                    session, expected_version=request.expected_version, **values
                )
                if updated is None:
                    raise LifecycleError(409)
                row = updated
            support.append_audit(
                session,
                grant,
                workspace_id=request.workspace_id,
                event_type="target_registered" if before is None else "target_updated",
                target_id=row.id,
                reason=request.reason,
                before_digest=before,
                after_digest=_state(row),
            )
            return support.bounded_payload(
                _view(row, request.project_id, request.workspace_id, session)
            )
    except LifecycleError:
        raise
    except (IntegrityError, ValueError):
        raise LifecycleError(409) from None


def get_target(target_id: str, project_id: int, workspace_id: int) -> dict[str, Any]:
    with authorization.authorized_session() as session:
        _admin(session, project_id, workspace_id, mutation=False)
        row = repository.resolve_alias(session, support.identifier(target_id).lower())
        if row is None or (project_id, workspace_id) not in repository.list_scopes(
            session, row.id
        ):
            raise authorization.TrustedAuthorizationError()
        return support.bounded_payload(_view(row, project_id, workspace_id, session))


def list_targets(
    project_id: int, workspace_id: int, *, limit: int = 25, cursor: str | None = None
) -> dict[str, Any]:
    with authorization.authorized_session() as session:
        grant = _admin(session, project_id, workspace_id, mutation=False)
        query = select(InfraAutomationTarget).where(
            InfraAutomationTarget.id.in_(
                select(InfraAutomationTargetScope.target_id).where(
                    InfraAutomationTargetScope.project_id == project_id,
                    InfraAutomationTargetScope.workspace_id == workspace_id,
                )
            )
        )
        maximum = session.scalar(select(func.max(InfraAutomationTarget.sequence))) or 0
        state = cursor_store.begin(
            binding={
                "resource": "targets",
                "principal": grant.principal.principal_id,
                "session": grant.principal.session_id,
                "project": project_id,
                "workspace": workspace_id,
            },
            limit=limit,
            cursor=cursor,
            snapshot_sequence=maximum,
        )
        query = query.where(InfraAutomationTarget.sequence <= state.snapshot_sequence)
        if state.before:
            created, identity = state.before
            query = query.where(
                or_(
                    InfraAutomationTarget.created_at < created,
                    and_(
                        InfraAutomationTarget.created_at == created,
                        InfraAutomationTarget.id < identity,
                    ),
                )
            )
        rows = list(
            session.scalars(
                query.order_by(
                    InfraAutomationTarget.created_at.desc(),
                    InfraAutomationTarget.id.desc(),
                ).limit(limit + 1)
            )
        )
        more = len(rows) > limit
        rows = rows[:limit]
        envelope = cursor_store.finish(
            state,
            position=(rows[-1].created_at, rows[-1].id) if rows else None,
            last_sequence=min((row.sequence for row in rows), default=0),
            has_more=more,
        )
        items = []
        for row in rows:
            definition = _definition(row)
            items.append(
                TargetSummary(
                    id=row.id,
                    version=row.version,
                    epoch=row.epoch,
                    enabled=row.enabled,
                    environment=definition.environment,
                    receiver_id=definition.receiver_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    created_at=support.utc(row.created_at),
                )
            )
        return support.bounded_payload(
            TargetPage(items=tuple(items), cursor=envelope).model_dump(mode="json")
        )


def capture_run_targets(
    session: Session,
    run: InfraAutomationRun,
    document: SnapshotDocument,
    *,
    now: datetime,
    bounds: EngineBounds | None = None,
) -> None:
    """Called inside admission after insertion, before any queued run is visible."""
    authorization._require_operation(session)
    handoffs = [
        step
        for step in document.definition.steps
        if step.kind == "registered_github_handoff"
    ]
    if not handoffs:
        return
    if (
        run.state != "queued"
        or run.cancel_requested
        or run.external_possible
        or repository.list_run_targets(session, run.id)
    ):
        raise LifecycleError(409)
    timestamp = _now(now)
    resolved = []
    for step in handoffs:
        alias = resolve_target_value(document, step.target_id)
        row = repository.resolve_alias(session, alias.lower())
        if row is None or not row.enabled:
            raise LifecycleError(409)
        definition = _definition(row)
        if definition.environment != document.environment or (
            run.project_id,
            run.workspace_id,
        ) not in repository.list_scopes(session, row.id):
            raise authorization.TrustedAuthorizationError()
        if timestamp < _instant(row.last_observed_at):
            raise LifecycleError(503)
        actor = session.get(
            IdentityAccount, row.receiver_principal_id, populate_existing=True
        )
        if (
            actor is None
            or not actor.enabled
            or actor.principal_type != "service"
            or actor.is_admin
        ):
            raise LifecycleError(503)
        snapshot = TargetSnapshot(
            definition=definition,
            target_version=row.version,
            target_epoch=row.epoch,
            receiver_principal_id=actor.id,
            receiver_authentication_version=actor.authentication_version,
            captured_at=support.utc(timestamp),
        )
        resolved.append((step, row, snapshot))
    lock_ids = {
        target_id: secrets.token_hex(24)
        for target_id in sorted({row.id for _, row, _ in resolved})
    }
    for target_id in lock_ids:
        if repository.get_held_lock(session, target_id) is not None:
            raise LifecycleError(409)
    captures = []
    delta = 0
    for step, row, snapshot in resolved:
        raw = target_snapshot_bytes(snapshot)
        values: dict[str, Any] = dict(
            run_id=run.id,
            handoff_step_id=step.id,
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            target_id=row.id,
            target_epoch=row.epoch,
            requested_alias=resolve_target_value(document, step.target_id),
            lock_id=lock_ids[row.id],
            snapshot_digest=content_digest(raw),
        )
        delta += len(raw) + len(
            canonical({**values, "created_at": support.utc(timestamp)})
        )
        captures.append((values, raw))
    for target_id, lock_id in lock_ids.items():
        # Locks have one terminal transition (version1 -> version2). Reserve
        # its longest status and printable reason now. Controls are forbidden by
        # MutationRequest, so four UTF8 bytes/character also bounds JSON escapes.
        delta += 4 * REASON_MAX_LENGTH + len(
            canonical(
                {
                    "id": lock_id,
                    "target_id": target_id,
                    "run_id": run.id,
                    "project_id": run.project_id,
                    "workspace_id": run.workspace_id,
                    "version": 2,
                    "status": "resolved",
                    "reason": "",
                    "created_at": support.utc(timestamp),
                    "updated_at": support.utc(timestamp),
                }
            )
        )
    from infra_automation import claims

    claims._charge(session, run, delta, timestamp, bounds)
    for target_id, lock_id in lock_ids.items():
        repository.acquire_lock(
            session,
            lock_id=lock_id,
            target_id=target_id,
            run_id=run.id,
            project_id=run.project_id,
            workspace_id=run.workspace_id,
            now=timestamp,
        )
    for values, raw in captures:
        repository.capture_run_target(
            session, snapshot_bytes=raw, now=timestamp, **values
        )


def captured_target(
    session: Session, run_id: str, handoff_step_id: str, *, live: bool = True
) -> tuple[InfraAutomationRunTarget, TargetSnapshot]:
    authorization._require_operation(session)
    capture = repository.get_run_target(session, run_id, handoff_step_id)
    if capture is None:
        raise LifecycleError(409)
    try:
        snapshot = TargetSnapshot.model_validate_json(capture.snapshot_bytes)
        if (
            content_digest(capture.snapshot_bytes) != capture.snapshot_digest
            or target_snapshot_bytes(snapshot) != capture.snapshot_bytes
            or snapshot.definition.canonical_target != capture.target_id
            or snapshot.target_epoch != capture.target_epoch
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise LifecycleError(503) from None
    if live:
        try:
            allowed_origins = config.handoff_allowed_origins()
        except (ValueError, TypeError):
            raise LifecycleError(503) from None
        if snapshot.definition.api_origin not in allowed_origins:
            raise LifecycleError(409)
        row = repository.get_target(session, capture.target_id)
        lock = repository.get_lock(session, capture.lock_id)
        actor = session.get(
            IdentityAccount, snapshot.receiver_principal_id, populate_existing=True
        )
        if (
            row is None
            or lock is None
            or not row.enabled
            or lock.status != "held"
            or lock.run_id != run_id
            or row.epoch != snapshot.target_epoch
            or row.version != snapshot.target_version
            or row.definition_bytes != target_definition_bytes(snapshot.definition)
            or row.receiver_principal_id != snapshot.receiver_principal_id
            or actor is None
            or not actor.enabled
            or actor.principal_type != "service"
            or actor.authentication_version != snapshot.receiver_authentication_version
            or (capture.project_id, capture.workspace_id)
            not in repository.list_scopes(session, row.id)
        ):
            raise LifecycleError(409)
    return capture, snapshot


def check_run_targets(
    session: Session, run: InfraAutomationRun, document: SnapshotDocument
) -> None:
    for step in document.definition.steps:
        if step.kind == "registered_github_handoff":
            captured_target(session, run.id, step.id)


def resolved_target_pairs(
    session: Session, run: InfraAutomationRun, document: SnapshotDocument
) -> tuple[tuple[str, str], ...]:
    """Preserve original workflow aliases and independently retained canonical IDs."""
    pairs = {}
    for step in document.definition.steps:
        if step.kind == "registered_github_handoff":
            capture = repository.get_run_target(session, run.id, step.id)
            if capture is not None:
                _, snapshot = captured_target(session, run.id, step.id, live=False)
                alias = resolve_target_value(document, step.target_id)
                if capture.requested_alias != alias:
                    raise LifecycleError(409)
                pairs[alias] = snapshot.definition.canonical_target
    return tuple(pairs.items())


def target_for_decision(
    session: Session,
    run: InfraAutomationRun,
    document: SnapshotDocument,
    decision_step_id: str,
) -> TargetSnapshot | None:
    """Only the selected action's registry facts can invalidate its material."""
    candidates = [
        step
        for step in document.definition.steps
        if step.kind == "registered_github_handoff"
        and step.decision.step_id == decision_step_id
    ]
    snapshots = []
    for step in candidates:
        capture = repository.get_run_target(session, run.id, step.id)
        if capture is not None:
            _, snapshot = captured_target(session, run.id, step.id)
            snapshots.append(snapshot)
    if not snapshots:
        return None
    if any(
        target_snapshot_bytes(item) != target_snapshot_bytes(snapshots[0])
        for item in snapshots
    ):
        raise LifecycleError(409)
    return snapshots[0]


def break_lock(
    target_id: str, request: BreakLockRequest, *, now: datetime | None = None
) -> dict[str, Any]:
    request = checked(request, BreakLockRequest)
    timestamp = _now(now)
    with authorization.authorized_session() as session:
        grant = _admin(session, request.project_id, request.workspace_id, mutation=True)
        support.screened_label(request.reason)
        target = repository.resolve_alias(
            session, support.identifier(target_id).lower()
        )
        lock = repository.get_lock(session, request.expected_lock_id)
        if (
            target is None
            or lock is None
            or lock.target_id != target.id
            or (lock.project_id, lock.workspace_id)
            != (request.project_id, request.workspace_id)
        ):
            raise authorization.TrustedAuthorizationError()
        if timestamp < _instant(lock.updated_at):
            raise LifecycleError(503)
        before_digest = content_digest(
            canonical(
                {
                    "lock": lock.id,
                    "run": lock.run_id,
                    "version": lock.version,
                    "status": lock.status,
                }
            )
        )
        operations = list(
            session.scalars(
                select(InfraAutomationHandoff).where(
                    InfraAutomationHandoff.run_id == lock.run_id,
                    InfraAutomationHandoff.target_id == lock.target_id,
                )
            )
        )
        for operation in operations:
            if timestamp < _instant(operation.last_observed_at):
                raise LifecycleError(503)
        from services import infra_automation_handoffs as handoff_service
        from models.repositories import infra_automation_handoffs as handoff_repository

        operation_before = {
            operation.id: handoff_service._default_service._state_digest(
                session, operation
            )
            for operation in operations
        }
        row = repository.resolve_lock(
            session,
            lock_id=lock.id,
            expected_version=request.expected_version,
            status="broken",
            reason=request.reason,
            now=timestamp,
        )
        if row is None:
            raise LifecycleError(409)
        for operation in operations:
            if not operation.broken:
                changed = session.execute(
                    update(InfraAutomationHandoff)
                    .where(
                        InfraAutomationHandoff.id == operation.id,
                        InfraAutomationHandoff.version == operation.version,
                        InfraAutomationHandoff.broken.is_(False),
                    )
                    .values(
                        broken=True,
                        version=operation.version + 1,
                        last_observed_at=timestamp,
                    )
                    .execution_options(synchronize_session=False)
                )
                if cast(CursorResult, changed).rowcount != 1:
                    raise LifecycleError(409)
                session.execute(
                    update(InfraAutomationGrant)
                    .where(
                        InfraAutomationGrant.operation_id == operation.id,
                        InfraAutomationGrant.status == "available",
                    )
                    .values(
                        status="invalidated", version=InfraAutomationGrant.version + 1
                    )
                    .execution_options(synchronize_session=False)
                )
        session.flush()
        for operation in operations:
            current = handoff_repository.get_operation(session, operation.id)
            if current is None:
                raise LifecycleError(503)
            handoff_service._default_service._audit(
                session,
                current,
                event="handoff_authority_broken",
                reason=request.reason,
                human=grant,
                before_digest=operation_before[operation.id],
            )
        support.append_audit(
            session,
            grant,
            before_digest=before_digest,
            workspace_id=lock.workspace_id,
            event_type="target_lock_broken",
            target_id=lock.id,
            reason=request.reason,
            after_digest=content_digest(
                canonical(
                    {
                        "lock": lock.id,
                        "run": lock.run_id,
                        "version": row.version,
                        "status": "broken",
                    }
                )
            ),
        )
        return support.bounded_payload(
            {
                "id": row.id,
                "target_id": row.target_id,
                "run_id": row.run_id,
                "project_id": row.project_id,
                "workspace_id": row.workspace_id,
                "version": row.version,
                "status": row.status,
            }
        )
