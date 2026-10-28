"""Scoped draft/publication lifecycle in existing live-authority transactions."""

from __future__ import annotations

from dataclasses import asdict

from infra_automation.contracts import RegistryContract
from infra_automation.lifecycle import (
    AdvanceEpochRequest,
    SnapshotExport,
    UpdateSettingsRequest,
    ArchiveWorkflowRequest,
    CreateWorkflowRequest,
    LifecycleError,
    PublishWorkflowRequest,
    RestoreWorkflowRequest,
    SaveDraftRequest,
    ValidateDraftRequest,
    ValidateWorkflowRequest,
)
from infra_automation.lifecycle_cursors import cursor_store
from infra_automation.state import CancelRunRequest, RunRequest
from models.repositories import infra_automation_workflows as repository
from services import infra_automation_support as support
from services.content_security import redact_reference
from services import project_service as authorization


def _view(row, *, definition=True) -> dict:
    value = {
        "id": row.id,
        "project_id": row.project_id,
        "workspace_id": row.workspace_id,
        "name": support.screened_label(row.name),
        "draft_version": row.draft_version,
        "archived": row.archived,
        "draft_digest": row.draft_digest,
        "created_by": row.created_by,
        "created_at": support.utc(row.created_at),
        "updated_at": support.utc(row.updated_at),
    }
    if definition:
        value["definition"] = support.stored_definition(
            row.draft_definition, row.draft_digest, row.project_id, row.workspace_id
        )
    return support.bounded_payload(value)


def _revision_view(row, *, definition=True) -> dict:
    value = {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "project_id": row.project_id,
        "workspace_id": row.workspace_id,
        "revision_number": row.revision_number,
        "digest": row.digest,
        "published_by": row.published_by,
        "created_at": support.utc(row.created_at),
    }
    if definition:
        value["definition"] = support.stored_definition(
            row.canonical_definition, row.digest, row.project_id, row.workspace_id
        )
    return support.bounded_payload(value)


def _revision(session, row, revision_id):
    revision = repository.get_revision(session, support.identifier(revision_id))
    if revision is None or (
        revision.workflow_id,
        revision.project_id,
        revision.workspace_id,
    ) != (row.id, row.project_id, row.workspace_id):
        raise authorization.TrustedAuthorizationError()
    return revision


def _validated(
    raw, project_id, workspace_id, registry_contract: RegistryContract | None = None
):
    result = support.validate_definition(
        raw, project_id, workspace_id, registry_contract
    )
    if not result.valid or result.canonical_bytes is None or result.digest is None:
        raise LifecycleError(422)
    return result.canonical_bytes, result.digest


def _version(row, expected_version, *, allow_archived=False):
    if row.draft_version != expected_version or (row.archived and not allow_archived):
        raise LifecycleError(409)


def create_workflow(
    request: CreateWorkflowRequest, *, registry_contract: RegistryContract | None = None
) -> dict:
    request = support.revalidate(request, CreateWorkflowRequest)
    with authorization.authorized_session() as session:
        grant = support.scope(
            session,
            request.project_id,
            request.workspace_id,
            "automation.draft",
            mutation=True,
        )
        support.screened_label(request.name)
        support.screened_label(request.reason)
        _, settings = support.policy_state(session, request.project_id)
        if (
            repository.count_workflows(session, project_id=request.project_id)
            >= settings.max_workflows
        ):
            raise LifecycleError(429)
        raw, digest = _validated(
            request.definition.encode(),
            request.project_id,
            request.workspace_id,
            registry_contract,
        )
        row = repository.create_workflow(
            session,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            name=request.name,
            canonical_definition=raw,
            digest=digest,
            created_by=grant.principal.principal_id,
        )
        support.append_audit(
            session,
            grant,
            workspace_id=row.workspace_id,
            event_type="workflow_created",
            target_id=row.id,
            reason=request.reason,
            after_digest=digest,
        )
        return _view(row)


def save_draft(
    workflow_id: str,
    request: SaveDraftRequest,
    *,
    registry_contract: RegistryContract | None = None,
) -> dict:
    request = support.revalidate(request, SaveDraftRequest)
    with authorization.authorized_session() as session:
        row, grant = support.workflow(
            session, workflow_id, "automation.draft", mutation=True
        )
        _version(row, request.expected_version)
        support.screened_label(request.reason)
        raw, digest = _validated(
            request.definition.encode(),
            row.project_id,
            row.workspace_id,
            registry_contract,
        )
        before = row.draft_digest
        changed = repository.update_workflow(
            session,
            workflow_id=row.id,
            expected_version=request.expected_version,
            canonical_definition=raw,
            digest=digest,
        )
        if changed is None:
            raise LifecycleError(409)
        support.append_audit(
            session,
            grant,
            workspace_id=row.workspace_id,
            event_type="draft_saved",
            target_id=row.id,
            reason=request.reason,
            before_digest=before,
            after_digest=digest,
        )
        return _view(changed)


def get_workflow(workflow_id: str) -> dict:
    with authorization.authorized_session() as session:
        row, _ = support.workflow(
            session, workflow_id, "automation.read", mutation=False
        )
        return _view(row)


def get_revision(workflow_id: str, revision_id: str) -> dict:
    with authorization.authorized_session() as session:
        row, _ = support.workflow(
            session, workflow_id, "automation.read", mutation=False
        )
        return _revision_view(_revision(session, row, revision_id))


def _validation(
    raw, project_id, workspace_id, registry_contract: RegistryContract | None = None
):
    try:
        result = support.validate_definition(
            raw, project_id, workspace_id, registry_contract
        )
    except LifecycleError as exc:
        if exc.status_code != 422:
            raise
        return {
            "valid": False,
            "digest": None,
            "truncated": False,
            "errors": [
                {
                    "code": "invalid_input",
                    "message": "Input does not satisfy the validation interface.",
                    "path": [],
                    "step_index": None,
                    "line": None,
                    "column": None,
                }
            ],
        }
    errors = [{**asdict(error), "path": list(error.path)} for error in result.errors]
    return {
        "valid": result.valid,
        "digest": result.digest,
        "errors": errors,
        "truncated": result.truncated,
    }


def validate_definition(
    request: ValidateWorkflowRequest,
    *,
    registry_contract: RegistryContract | None = None,
) -> dict:
    request = support.revalidate(request, ValidateWorkflowRequest)
    with authorization.authorized_session() as session:
        support.scope(
            session,
            request.project_id,
            request.workspace_id,
            "automation.draft",
            mutation=True,
        )
        return support.bounded_payload(
            _validation(
                request.definition.encode(),
                request.project_id,
                request.workspace_id,
                registry_contract,
            )
        )


def validate_draft(
    workflow_id: str,
    request: ValidateDraftRequest,
    *,
    registry_contract: RegistryContract | None = None,
) -> dict:
    request = support.revalidate(request, ValidateDraftRequest)
    with authorization.authorized_session() as session:
        row, grant = support.workflow(
            session, workflow_id, "automation.draft", mutation=True
        )
        _version(row, request.expected_version)
        raw = (
            request.definition.encode()
            if request.definition is not None
            else row.draft_definition
        )
        value = _validation(raw, row.project_id, row.workspace_id, registry_contract)
        support.append_audit(
            session,
            grant,
            workspace_id=row.workspace_id,
            event_type="draft_validated",
            target_id=row.id,
            reason="draft-validation",
            before_digest=row.draft_digest,
            after_digest=value["digest"],
        )
        return support.bounded_payload(value)


def _publication_digest(workflow_id, request, definition_digest):
    return support.digest(
        support.canonical(
            {
                "workflow_id": workflow_id,
                "expected_version": request.expected_version,
                "definition_digest": definition_digest,
                "reason": request.reason,
            }
        )
    )


def publish_workflow(
    workflow_id: str,
    request: PublishWorkflowRequest,
    *,
    registry_contract: RegistryContract | None = None,
) -> dict:
    request = support.revalidate(request, PublishWorkflowRequest)
    with authorization.authorized_session() as session:
        row, grant = support.workflow(
            session, workflow_id, "automation.publish", mutation=True
        )
        support.screened_label(request.reason)
        key_digest = support.digest(request.idempotency_key.encode())
        existing = repository.get_publication(
            session,
            published_by=grant.principal.principal_id,
            idempotency_key_digest=key_digest,
        )
        if existing is not None:
            if (
                existing.workflow_id != row.id
                or existing.request_digest
                != _publication_digest(row.id, request, existing.digest)
            ):
                raise LifecycleError(409)
            return _revision_view(existing)
        _version(row, request.expected_version)
        support.stored_definition(
            row.draft_definition, row.draft_digest, row.project_id, row.workspace_id
        )
        raw, digest = _validated(
            row.draft_definition, row.project_id, row.workspace_id, registry_contract
        )
        _, settings = support.policy_state(session, row.project_id)
        if (
            repository.count_revisions(session, workflow_id=row.id)
            >= settings.max_revisions_per_workflow
        ):
            raise LifecycleError(429)
        changed = repository.update_workflow(
            session, workflow_id=row.id, expected_version=request.expected_version
        )
        if changed is None:
            raise LifecycleError(409)
        # The revision response is smaller; a version digit must not make the
        # updated draft unreadable after an otherwise successful publication.
        _view(changed)
        revision = repository.append_revision(
            session,
            workflow_id=row.id,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            revision_number=repository.max_revision_number(session, workflow_id=row.id)
            + 1,
            canonical_definition=raw,
            digest=digest,
            published_by=grant.principal.principal_id,
            idempotency_key_digest=key_digest,
            request_digest=_publication_digest(row.id, request, digest),
        )
        support.append_audit(
            session,
            grant,
            workspace_id=row.workspace_id,
            event_type="workflow_published",
            target_id=row.id,
            reason=request.reason,
            before_digest=row.draft_digest,
            after_digest=digest,
        )
        return _revision_view(revision)


def archive_workflow(workflow_id: str, request: ArchiveWorkflowRequest) -> dict:
    request = support.revalidate(request, ArchiveWorkflowRequest)
    with authorization.authorized_session() as session:
        row, grant = support.workflow(
            session, workflow_id, "automation.admin", mutation=True
        )
        _version(row, request.expected_version)
        support.screened_label(request.reason)
        changed = repository.update_workflow(
            session,
            workflow_id=row.id,
            expected_version=request.expected_version,
            archived=True,
        )
        if changed is None:
            raise LifecycleError(409)
        support.append_audit(
            session,
            grant,
            workspace_id=row.workspace_id,
            event_type="workflow_archived",
            target_id=row.id,
            reason=request.reason,
            before_digest=row.draft_digest,
            after_digest=row.draft_digest,
        )
        return _view(changed)


def restore_workflow(
    workflow_id: str,
    request: RestoreWorkflowRequest,
    *,
    registry_contract: RegistryContract | None = None,
) -> dict:
    request = support.revalidate(request, RestoreWorkflowRequest)
    with authorization.authorized_session() as session:
        row, grant = support.workflow(
            session, workflow_id, "automation.admin", mutation=True
        )
        _version(row, request.expected_version, allow_archived=True)
        support.screened_label(request.reason)
        old_digest = row.draft_digest
        revision = (
            _revision(session, row, request.revision_id)
            if request.revision_id is not None
            else None
        )
        raw = revision.canonical_definition if revision else row.draft_definition
        stored_digest = revision.digest if revision else row.draft_digest
        support.stored_definition(raw, stored_digest, row.project_id, row.workspace_id)
        raw, digest = _validated(
            raw, row.project_id, row.workspace_id, registry_contract
        )
        changed = repository.update_workflow(
            session,
            workflow_id=row.id,
            expected_version=request.expected_version,
            canonical_definition=raw,
            digest=digest,
            archived=False,
        )
        if changed is None:
            raise LifecycleError(409)
        support.append_audit(
            session,
            grant,
            workspace_id=row.workspace_id,
            event_type="workflow_restored",
            target_id=row.id,
            reason=request.reason,
            before_digest=old_digest,
            after_digest=digest,
        )
        return _view(changed)


def _binding(grant, *, workspace_id, family, workflow_id=None):
    return {
        "principal": grant.principal.principal_id,
        "authentication_version": grant.principal.authentication_version,
        "membership_version": grant.authorization_version,
        "project_id": grant.project_id,
        "workspace_id": workspace_id,
        "family": family,
        "workflow_id": workflow_id,
    }


def _page(*, binding, limit, cursor, maximum, fetch, render):
    state = cursor_store.begin(
        binding=binding, limit=limit, cursor=cursor, snapshot_sequence=maximum
    )
    rows = fetch(
        snapshot_sequence=state.snapshot_sequence, before=state.before, limit=limit
    )
    items = []
    chosen = []
    for row in rows:
        candidate = render(row)
        if len(support.canonical(items + [candidate])) > 120000:
            break
        items.append(candidate)
        chosen.append(row)
    if rows and not chosen:
        raise LifecycleError(429)
    last = (chosen[-1].created_at, chosen[-1].id) if chosen else None
    has_more = bool(chosen) and (
        len(chosen) < len(rows)
        or bool(fetch(snapshot_sequence=state.snapshot_sequence, before=last, limit=1))
    )
    page = cursor_store.finish(
        state,
        position=last,
        last_sequence=chosen[-1].sequence if chosen else 0,
        has_more=has_more,
    )
    return support.bounded_payload(
        {"items": items, "cursor": page.model_dump(mode="json")}
    )


def list_workflows(
    project_id: int,
    workspace_id: int | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict:
    with authorization.authorized_session() as session:
        grant = support.scope(
            session, project_id, workspace_id, "automation.read", mutation=False
        )
        return _page(
            binding=_binding(grant, workspace_id=workspace_id, family="workflows"),
            limit=limit,
            cursor=cursor,
            maximum=repository.workflow_max_sequence(
                session, project_id=project_id, workspace_id=workspace_id
            ),
            fetch=lambda **kw: repository.list_workflows(
                session, project_id=project_id, workspace_id=workspace_id, **kw
            ),
            render=lambda row: _view(row, definition=False),
        )


def list_revisions(
    workflow_id: str, limit: int = 25, cursor: str | None = None
) -> dict:
    with authorization.authorized_session() as session:
        row, grant = support.workflow(
            session, workflow_id, "automation.read", mutation=False
        )
        return _page(
            binding=_binding(
                grant,
                workspace_id=row.workspace_id,
                family="revisions",
                workflow_id=row.id,
            ),
            limit=limit,
            cursor=cursor,
            maximum=repository.revision_max_sequence(session, workflow_id=row.id),
            fetch=lambda **kw: repository.list_revisions(
                session, workflow_id=row.id, **kw
            ),
            render=lambda row: _revision_view(row, definition=False),
        )


def _audit_view(row):
    return {
        "id": row.id,
        "project_id": row.project_id,
        "workspace_id": row.workspace_id,
        "actor_principal_id": row.actor_principal_id,
        "actor_type": row.actor_type,
        "actor_role": row.actor_role,
        "event_type": row.event_type,
        "target_id": row.target_id,
        "reason": redact_reference(row.reason),
        "before_digest": row.before_digest,
        "after_digest": row.after_digest,
        "created_at": support.utc(row.created_at),
    }


def export_audit(
    project_id: int,
    workspace_id: int | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict:
    with authorization.authorized_session() as session:
        grant = support.scope(
            session, project_id, workspace_id, "automation.admin", mutation=False
        )
        return _page(
            binding=_binding(grant, workspace_id=workspace_id, family="audit"),
            limit=limit,
            cursor=cursor,
            maximum=repository.audit_max_sequence(
                session, project_id=project_id, workspace_id=workspace_id
            ),
            fetch=lambda **kw: repository.list_audit(
                session, project_id=project_id, workspace_id=workspace_id, **kw
            ),
            render=_audit_view,
        )


def get_capabilities(project_id: int, workspace_id: int | None = None) -> dict:
    from services.infra_automation_policy import get_capabilities as operation

    return operation(project_id, workspace_id=workspace_id)


def get_settings(project_id: int) -> dict:
    from services.infra_automation_policy import get_settings as operation

    return operation(project_id)


def update_settings(request: UpdateSettingsRequest) -> dict:
    from services.infra_automation_policy import update_settings as operation

    return operation(request)


def advance_epoch(request: AdvanceEpochRequest, *, restore: bool = False) -> dict:
    from services.infra_automation_policy import advance_epoch as operation

    return operation(request, restore=restore)


def export_run_snapshot(
    workflow_id: str,
    revision_id: str,
    inputs: dict,
    workspace_id: int,
    *,
    registry_contract: RegistryContract | None = None,
) -> SnapshotExport:
    from services.infra_automation_snapshots import export_run_snapshot as operation

    return operation(
        workflow_id,
        revision_id,
        inputs,
        workspace_id,
        registry_contract=registry_contract,
    )


def request_run(request: RunRequest) -> dict:
    from services.infra_automation_engine_service import request_run as operation

    return operation(request)


def get_run(run_id: str) -> dict:
    from services.infra_automation_engine_service import get_run as operation

    return operation(run_id)


def list_runs(
    project_id: int,
    workspace_id: int | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict:
    from services.infra_automation_engine_service import list_runs as operation

    return operation(project_id, workspace_id=workspace_id, limit=limit, cursor=cursor)


def list_steps(run_id: str, limit: int = 25, cursor: str | None = None) -> dict:
    from services.infra_automation_engine_service import list_steps as operation

    return operation(run_id, limit=limit, cursor=cursor)


def get_logs(
    run_id: str, attempt_id: str, limit: int = 25, cursor: str | None = None
) -> dict:
    from services.infra_automation_engine_service import get_logs as operation

    return operation(run_id, attempt_id, limit=limit, cursor=cursor)


def cancel_run(run_id: str, request: CancelRunRequest, *, cancel_port=None) -> dict:
    from services.infra_automation_engine_service import cancel_run as operation

    return operation(run_id, request, cancel_port=cancel_port)


def request_preflight(request) -> dict:
    from services.infra_automation_preflight import request_preflight as operation

    return operation(request)


def list_run_reports(run_id: str) -> dict:
    from services.infra_automation_preflight import list_run_reports as operation

    return operation(run_id)
