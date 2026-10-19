"""Human-authorized admission and scoped reads over immutable engine evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from infra_automation.contracts import RegistryContract
from infra_automation.lifecycle import LifecycleError, SnapshotDocument
from infra_automation.state import AuditActor, EngineBounds, RunRequest, RunView
from models.repositories import infra_automation_runs as repository
from models.tables import InfraAutomationRun
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
