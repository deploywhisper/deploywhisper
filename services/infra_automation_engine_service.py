"""Human-authorized admission and scoped reads over immutable engine evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from infra_automation.contracts import RegistryContract, SAFE_INTEGER
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.state import AuditActor, EngineBounds, RunRequest, RunView
from models.repositories import infra_automation_runs as repository
from models.tables import InfraAutomationRun, InfraAutomationRunRequest
from services import infra_automation_engine_support as engine_support
from services import infra_automation_support as support
from services import project_service as authorization
from services.infra_automation_snapshots import export_run_snapshot as _export


def _document(row) -> SnapshotDocument:
    try:
        value = SnapshotDocument.model_validate_json(row.snapshot_bytes)
        if support.digest(row.snapshot_bytes) != row.snapshot_digest or (
            value.project_id,
            value.workspace_id,
            value.workflow_id,
            value.revision_id,
            value.authority.principal_id,
            value.definition_digest,
            value.input_digest,
        ) != (
            row.project_id,
            row.workspace_id,
            row.workflow_id,
            row.revision_id,
            row.requested_by,
            row.definition_digest,
            row.input_digest,
        ):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def _view(row) -> dict:
    try:
        value = RunView(
            id=row.id,
            workflow_id=row.workflow_id,
            revision_id=row.revision_id,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            requested_by=row.requested_by,
            state=row.state,
            version=row.version,
            snapshot_digest=row.snapshot_digest,
            definition_digest=row.definition_digest,
            input_digest=row.input_digest,
            created_at=support.utc(row.created_at),
            deadline_at=support.utc(row.deadline_at),
            cancel_requested=row.cancel_requested,
            cancellation_requested_at=(
                support.utc(row.cancellation_requested_at)
                if row.cancellation_requested_at is not None
                else None
            ),
        ).model_dump(mode="json")
    except (ValueError, TypeError):
        raise LifecycleError(503) from None
    return support.bounded_payload(value)


def _request_digest(request: RunRequest, document: SnapshotDocument) -> str:
    # Include the original typed request as well as its authoritative resolution.
    # Replays compare against the stored snapshot, never recapture time/policy.
    return support.digest(
        support.canonical(
            {
                "request": request.model_dump(mode="json", exclude={"idempotency_key"}),
                "project_id": document.project_id,
                "workspace_id": document.workspace_id,
                "definition_digest": document.definition_digest,
                "input_digest": document.input_digest,
                "sources": [item.model_dump(mode="json") for item in document.sources],
            }
        )
    )


def _require_handlers(document: SnapshotDocument, registry) -> None:
    if registry is None:
        from infra_automation.local_workers import DEFAULT_REGISTRY

        registry = DEFAULT_REGISTRY
    if not callable(getattr(registry, "get", None)) or any(
        registry.get(step.kind) is None for step in document.definition.steps
    ):
        raise LifecycleError(503)


def request_run(
    request: RunRequest,
    *,
    registry=None,
    registry_contract: RegistryContract | None = None,
    bounds: EngineBounds | None = None,
    now: datetime | None = None,
) -> dict:
    """Capture one publication atomically; registry injection is trusted code only."""
    from infra_automation import claims

    request = support.revalidate(request, RunRequest)
    bounds = (
        EngineBounds() if bounds is None else support.revalidate(bounds, EngineBounds)
    )
    timestamp = now or datetime.now(timezone.utc)
    if type(timestamp) is not datetime or timestamp.tzinfo is None:
        raise LifecycleError(503)
    timestamp = timestamp.astimezone(timezone.utc)
    with authorization.authorized_session() as session:
        workflow, _ = support.workflow(
            session, request.workflow_id, "automation.request", mutation=True
        )
        grant = support.scope(
            session,
            workflow.project_id,
            request.workspace_id,
            "automation.request",
            mutation=True,
        )
        if (
            grant.principal.principal_type != "human"
            or grant.principal.credential_audience != "human"
        ):
            raise authorization.TrustedAuthorizationError()
        support.screened_label(request.reason)
        key_digest = support.digest(request.idempotency_key.encode())
        existing = repository.get_request(
            session,
            project_id=workflow.project_id,
            workspace_id=request.workspace_id,
            requested_by=grant.principal.principal_id,
            key_digest=key_digest,
        )
        if existing is not None:
            row = repository.get_run(session, existing.run_id)
            if row is None:
                raise LifecycleError(503)
            document = _document(row)
            if existing.request_digest != _request_digest(request, document):
                raise LifecycleError(409)
            return _view(row)
        snapshot = _export(
            request.workflow_id,
            request.revision_id,
            request.inputs,
            request.workspace_id,
            registry_contract=registry_contract,
        )
        document = snapshot.snapshot
        _require_handlers(document, registry)
        for filters, maximum in (
            (
                (InfraAutomationRun.project_id == workflow.project_id,),
                document.policy.max_queued_runs,
            ),
            (
                (InfraAutomationRun.workflow_id == workflow.id,),
                bounds.workflow_queued_runs,
            ),
        ):
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(InfraAutomationRun)
                    .where(InfraAutomationRun.state == "queued", *filters)
                )
                or 0
            )
            if count >= maximum:
                raise LifecycleError(429)
        captured = datetime.strptime(
            document.captured_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)
        deadline = min(
            timestamp + timedelta(seconds=request.total_timeout_seconds),
            captured + timedelta(seconds=document.policy.evidence_ttl_seconds),
        )
        engine_support.ensure_engine_actor(session, grant)
        try:
            row = repository.create_run(
                session,
                snapshot=snapshot,
                request_digest=_request_digest(request, document),
                key_digest=key_digest,
                requested_by=grant.principal.principal_id,
                deadline_at=deadline,
                audit_actor=AuditActor(
                    grant.principal.principal_id,
                    grant.principal.principal_type,
                    grant.role,
                ),
                reason=request.reason,
                now=timestamp,
            )
        except ValueError:
            raise LifecycleError(409) from None
        # Reuse the worker accounting check after insertion; overflow rolls back the
        # run, idempotency binding, snapshot audit and lazy actor in this transaction.
        claims._charge(session, row, 0, timestamp, bounds)
        return _view(row)


def _authorized_run(session, run_id: str):
    row = repository.get_run(session, support.identifier(run_id))
    if row is None:
        raise authorization.TrustedAuthorizationError()
    grant = support.scope(
        session, row.project_id, row.workspace_id, "automation.read", mutation=False
    )
    return row, grant


def get_run(run_id: str) -> dict:
    with authorization.authorized_session() as session:
        row, _ = _authorized_run(session, run_id)
        _document(row)
        return _view(row)


def list_runs(
    project_id: int,
    workspace_id: int | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict:
    from services.infra_automation_service import _binding, _page

    with authorization.authorized_session() as session:
        grant = support.scope(
            session, project_id, workspace_id, "automation.read", mutation=False
        )
        return _page(
            binding=_binding(grant, workspace_id=workspace_id, family="runs"),
            limit=limit,
            cursor=cursor,
            maximum=repository.run_max_sequence(
                session, project_id=project_id, workspace_id=workspace_id
            ),
            fetch=lambda **values: repository.list_runs(
                session, project_id=project_id, workspace_id=workspace_id, **values
            ),
            render=_view,
        )


def _step_view(row) -> dict:
    from infra_automation.state import OutputReference, StepView
    import json

    try:
        if len(row.uploads_json.encode("utf-8")) > 65536:
            raise ValueError
        uploads = json.loads(row.uploads_json)
        if type(uploads) is not list:
            raise ValueError
        output = (
            OutputReference.model_validate_json(row.output_json)
            if row.output_json
            else None
        )
        if output is not None and output.digest != row.output_digest:
            raise ValueError
        value = StepView(
            id=row.id,
            run_id=row.run_id,
            step_id=row.step_id,
            attempt_number=row.attempt_number,
            state=row.state,
            version=row.version,
            fence=row.fence,
            generation=row.coordinator_generation,
            deadline_at=support.utc(row.deadline_at),
            lease_until=support.utc(row.lease_until) if row.lease_until else None,
            output=output,
            uploads=[OutputReference.model_validate(item) for item in uploads],
        ).model_dump(mode="json")
        support.screened(value)
    except (ValueError, TypeError):
        raise LifecycleError(503) from None
    return support.bounded_payload(value)


def list_steps(run_id: str, limit: int = 25, cursor: str | None = None) -> dict:
    from sqlalchemy import and_, or_
    from models.tables import InfraAutomationAttempt
    from services.infra_automation_service import _binding, _page

    with authorization.authorized_session() as session:
        run, grant = _authorized_run(session, run_id)
        maximum = (
            session.scalar(
                select(func.max(InfraAutomationAttempt.sequence)).where(
                    InfraAutomationAttempt.run_id == run.id
                )
            )
            or 0
        )

        def fetch(*, snapshot_sequence, before, limit):
            query = select(InfraAutomationAttempt).where(
                InfraAutomationAttempt.run_id == run.id,
                InfraAutomationAttempt.sequence <= snapshot_sequence,
            )
            if before is not None:
                query = query.where(
                    or_(
                        InfraAutomationAttempt.created_at < before[0],
                        and_(
                            InfraAutomationAttempt.created_at == before[0],
                            InfraAutomationAttempt.id < before[1],
                        ),
                    )
                )
            return list(
                session.scalars(
                    query.order_by(
                        InfraAutomationAttempt.created_at.desc(),
                        InfraAutomationAttempt.id.desc(),
                    ).limit(limit)
                )
            )

        return _page(
            binding={
                **_binding(grant, workspace_id=run.workspace_id, family="run-steps"),
                "run_id": run.id,
            },
            limit=limit,
            cursor=cursor,
            maximum=maximum,
            fetch=fetch,
            render=_step_view,
        )


def get_logs(
    run_id: str, attempt_id: str, limit: int = 25, cursor: str | None = None
) -> dict:
    import json
    from types import SimpleNamespace
    from infra_automation.state import LogChunk
    from services.infra_automation_service import _binding, _page

    with authorization.authorized_session() as session:
        run, grant = _authorized_run(session, run_id)
        attempt = repository.get_attempt(session, support.identifier(attempt_id))
        if attempt is None or attempt.run_id != run.id:
            raise authorization.TrustedAuthorizationError()
        try:
            if len(attempt.logs_json.encode("utf-8")) > 1048576:
                raise ValueError
            raw = json.loads(attempt.logs_json)
            if type(raw) is not list:
                raise ValueError
            chunks = [LogChunk.model_validate(item) for item in raw]
            support.screened(raw)
            sequences = [item.sequence for item in chunks]
            if any(left >= right for left, right in zip(sequences, sequences[1:])):
                raise ValueError
            if (
                type(attempt.last_log_sequence) is not int
                or not 0 <= attempt.last_log_sequence <= SAFE_INTEGER
                or attempt.last_log_sequence < (sequences[-1] if sequences else 0)
            ):
                raise ValueError
            gap = (
                bool(sequences)
                and sequences[0] != 1
                or any(
                    right != left + 1 for left, right in zip(sequences, sequences[1:])
                )
                or (sequences[-1] if sequences else 0) != attempt.last_log_sequence
            )
        except (ValueError, TypeError):
            raise LifecycleError(503) from None
        rows = [
            SimpleNamespace(
                created_at=attempt.created_at,
                id=f"log-{item.sequence:016d}",
                sequence=item.sequence,
                item=item,
            )
            for item in reversed(chunks)
        ]

        def fetch(*, snapshot_sequence, before, limit):
            return [
                row
                for row in rows
                if row.sequence <= snapshot_sequence
                and (before is None or (row.created_at, row.id) < before)
            ][:limit]

        result = _page(
            binding={
                **_binding(grant, workspace_id=run.workspace_id, family="run-logs"),
                "run_id": run.id,
                "attempt_id": attempt.id,
            },
            limit=limit,
            cursor=cursor,
            maximum=attempt.last_log_sequence,
            fetch=fetch,
            render=lambda row: row.item.model_dump(mode="json"),
        )
        result["cursor"]["gap"] = bool(gap)
        return support.bounded_payload(result)


def cancel_run(
    run_id: str, request, *, cancel_port=None, now: datetime | None = None
) -> dict:
    """Commit human cancellation evidence before signaling owned local processes."""
    from uuid import uuid4
    from infra_automation.coordinator import deadline_outcome
    from infra_automation.state import CancelRunRequest, TERMINAL_STATES

    request = support.revalidate(request, CancelRunRequest)
    support.screened_label(request.reason)
    failures = []
    with authorization.authorized_session() as session:
        row = repository.get_run(session, support.identifier(run_id))
        if row is None:
            raise authorization.TrustedAuthorizationError()
        grant = authorization.guard_project(
            session,
            row.project_id,
            row.workspace_id,
            "automation.cancel",
            owner_id=row.requested_by,
            mutation=True,
        )
        if grant is None or (
            grant.principal.principal_type != "human"
            or grant.principal.credential_audience != "human"
        ):
            raise authorization.TrustedAuthorizationError()
        _document(row)
        key_digest = support.digest(
            support.canonical(
                {
                    "run_id": row.id,
                    "actor": grant.principal.principal_id,
                    "expected_version": request.expected_version,
                }
            )
        )
        request_digest = support.digest(
            support.canonical(request.model_dump(mode="json"))
        )
        existing = repository.get_request(
            session,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            requested_by=row.requested_by,
            operation="cancel",
            key_digest=key_digest,
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise LifecycleError(409)
        elif row.cancel_requested:
            raise LifecycleError(409)
        else:
            if row.version != request.expected_version or row.state in TERMINAL_STATES:
                raise LifecycleError(409)
            timestamp = now or datetime.now(timezone.utc)
            if type(timestamp) is not datetime or timestamp.tzinfo is None:
                raise LifecycleError(503)
            timestamp = timestamp.astimezone(timezone.utc)
            if timestamp < repository.utc(row.last_observed_at):
                raise LifecycleError(503)
            before = repository._binding_digest(row)
            changed = session.execute(
                update(InfraAutomationRun)
                .where(
                    InfraAutomationRun.id == row.id,
                    InfraAutomationRun.version == request.expected_version,
                    InfraAutomationRun.cancel_requested.is_(False),
                )
                .values(
                    cancel_requested=True,
                    cancellation_requested_at=timestamp,
                    version=request.expected_version + 1,
                    updated_at=timestamp,
                    last_observed_at=timestamp,
                )
            )
            if changed.rowcount != 1:
                raise LifecycleError(409)
            row = repository.get_run(session, row.id)
            actor = AuditActor(grant.principal.principal_id, "human", grant.role)
            repository._audit(
                session,
                row,
                actor,
                request.reason,
                "engine.cancel_requested",
                before=before,
                now=timestamp,
            )
            target = (
                "delivery_unknown"
                if row.external_possible
                else deadline_outcome(row.snapshot_bytes, row.deadline_at)
                if timestamp >= repository.utc(row.deadline_at)
                else "cancelled"
            )
            if row.state != target:
                row = repository.transition_run(
                    session,
                    run_id=row.id,
                    expected_version=row.version,
                    state=target,
                    audit_actor=actor,
                    reason=request.reason,
                    now=timestamp,
                )
                if row is None:
                    raise LifecycleError(409)
        if existing is None:
            # Composite FK binds the original requester; actual cancelling actor
            # is independently bound in the key digest and verified human audit.
            session.add(
                InfraAutomationRunRequest(
                    id=uuid4().hex,
                    project_id=row.project_id,
                    workspace_id=row.workspace_id,
                    requested_by=row.requested_by,
                    operation="cancel",
                    key_digest=key_digest,
                    request_digest=request_digest,
                    run_id=row.id,
                    created_at=now or datetime.now(timezone.utc),
                )
            )
            session.flush()
        result = _view(row)
        if cancel_port is not None:

            def signal_after_commit(factory):
                try:
                    cancel_port(run_id)
                except Exception:
                    failures.append(True)

            authorization.register_operation_commit(session, signal_after_commit)
    if failures:
        raise LifecycleError(503)
    return result
