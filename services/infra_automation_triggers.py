"""Scoped signed intake and immutable server-selected run origins."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets
from typing import Annotated, Literal

from pydantic import Field, StrictStr
from sqlalchemy import inspect
from sqlalchemy.orm import object_session

from infra_automation.contracts import Identifier, ClosedModel
from infra_automation.lifecycle import (
    LifecycleError,
    MutationRequest,
    Positive,
    ValidateWorkflowRequest,
)
from infra_automation.state import RunOrigin, RunRequest
from infra_automation.trigger_contracts import (
    TriggerRequest,
    TriggerStatusRequest,
    TriggerListRequest,
)
from models.repositories import infra_automation_runs as runs
from models.repositories import infra_automation_workflows as workflows
from models.tables import IdentityAccount, InfraAutomationRunOrigin
from services import project_service as auth
from services import infra_automation_support as support
from services import infra_automation_engine_service as engine
from services import infra_automation_trigger_authority as authority
from services.identity_service import validate_username


# Deliberately outside IdentityService's accepted PBKDF2 verifier grammar.
_INERT_MACHINE_VERIFIER = "!no-human-credential"


class ProvisionPrincipalRequest(MutationRequest):
    project_id: Positive
    workspace_id: Positive
    username: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    principal_type: Literal["service", "agent"]
    role: Literal["contributor", "read-only"] = "contributor"


class ProvisionedPrincipal(ClosedModel):
    principal_id: Identifier
    username: StrictStr
    principal_type: Literal["service", "agent"]
    project_id: Positive
    workspace_id: Positive
    role: Literal["contributor", "read-only"]
    authentication_version: Positive
    membership_version: Positive
    restore_epoch: Positive


@dataclass(frozen=True)
class _Origin:
    kind: str
    key_id: str | None = None
    pr_ref: str | None = None
    operation_digest: str | None = None


_ORIGIN: ContextVar[_Origin | None] = ContextVar("automation_origin", default=None)


@contextmanager
def cli_origin():
    token = _ORIGIN.set(_Origin("cli"))
    try:
        yield
    finally:
        _ORIGIN.reset(token)


def provision_principal(request):
    request = support.revalidate(request, ProvisionPrincipalRequest)
    try:
        username = validate_username(request.username)
    except ValueError:
        raise LifecycleError(422) from None
    with auth.authorized_session() as session:
        grant = support.scope(
            session, request.project_id, None, "automation.admin", mutation=True
        )
        if (
            grant.principal.principal_type != "human"
            or grant.principal.credential_audience != "human"
            or not grant.principal.is_admin
        ):
            raise auth.TrustedAuthorizationError()
        support.scope(
            session,
            request.project_id,
            request.workspace_id,
            "automation.admin",
            mutation=True,
        )
        support.screened_label(username)
        support.screened_label(request.reason)
        from sqlalchemy import select, func

        if (
            session.scalar(
                select(IdentityAccount.id).where(IdentityAccount.username == username)
            )
            is not None
        ):
            raise LifecycleError(409)
        if (
            session.scalar(
                select(func.count())
                .select_from(IdentityAccount)
                .where(IdentityAccount.principal_type.in_(("service", "agent")))
            )
            or 0
        ) >= 128:
            raise LifecycleError(429)
        account = IdentityAccount(
            id=secrets.token_hex(24),
            username=username,
            principal_type=request.principal_type,
            password_verifier=_INERT_MACHINE_VERIFIER,
            is_admin=False,
            enabled=True,
            authentication_version=1,
            created_at=datetime.now(timezone.utc),
        )
        session.add(account)
        session.flush()
        membership = auth.assign_project_membership(
            request.project_id,
            account.id,
            request.role,
            workspace_id=request.workspace_id,
        )
        from services.infra_automation_engine_support import ensure_engine_actor

        ensure_engine_actor(session, grant)
        policy, _ = support.policy_state(session, request.project_id)
        if policy is None:
            raise LifecycleError(409)
        support.append_audit(
            session,
            grant,
            workspace_id=request.workspace_id,
            event_type="machine_principal_created",
            target_id=account.id,
            reason=request.reason,
        )
        support.scope(
            session, request.project_id, None, "automation.admin", mutation=True
        )
        return support.bounded_payload(
            ProvisionedPrincipal(
                principal_id=account.id,
                username=account.username,
                principal_type=account.principal_type,
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                role=request.role,
                authentication_version=account.authentication_version,
                membership_version=membership.authorization_version,
                restore_epoch=policy.restore_epoch,
            ).model_dump(mode="json")
        )


def capture_origin(session, run, document, grant, *, now, bounds=None):
    """Persist a channel supplied by an authenticated server entrypoint only."""
    if not inspect(session.connection()).has_table("infra_automation_run_origins"):
        if grant.principal.principal_type != "human":
            raise LifecycleError(503)
        return
    selected = _ORIGIN.get() or _Origin("manual")
    value = RunOrigin(
        kind=selected.kind,
        principal_id=grant.principal.principal_id,
        principal_type=grant.principal.principal_type,
        key_id=selected.key_id,
        pr_ref=selected.pr_ref,
        sources=document.sources,
    )
    if (grant.principal.principal_type == "human") != (selected.key_id is None):
        raise LifecycleError(503)
    raw = support.canonical(value.model_dump(mode="json"))
    support.screened(value.model_dump(mode="json"))
    if len(raw) > 32768:
        raise LifecycleError(429)
    from infra_automation.claims import _charge

    _charge(session, run, len(raw) + 512, now, bounds)
    session.add(
        InfraAutomationRunOrigin(
            run_id=run.id,
            origin_bytes=raw,
            origin_digest=support.digest(raw),
            operation_digest=selected.operation_digest,
            key_id=selected.key_id,
            source_repository_id=document.sources[0].repository_id
            if selected.key_id
            and document.sources
            and document.sources[0].kind == "collected"
            else None,
            source_commit_sha=document.sources[0].commit_sha
            if selected.key_id
            and document.sources
            and document.sources[0].kind == "collected"
            else None,
        )
    )
    session.flush()


def origin_view(run):
    session = object_session(run)
    if session is None or not inspect(session.connection()).has_table(
        "infra_automation_run_origins"
    ):
        return None
    row = session.get(InfraAutomationRunOrigin, run.id)
    if row is None:
        return None
    try:
        value = RunOrigin.model_validate_json(row.origin_bytes)
        if (
            support.digest(row.origin_bytes) != row.origin_digest
            or value.principal_id != run.requested_by
        ):
            raise ValueError
        document = engine._document(run)
        if value.sources != document.sources or value.key_id != row.key_id:
            raise ValueError
        from infra_automation.lifecycle import MachineAuthorityStamp

        if value.key_id is not None:
            if (
                not isinstance(document.authority, MachineAuthorityStamp)
                or document.authority.principal_type != value.principal_type
                or document.authority.key_id != value.key_id
                or not row.operation_digest
                or not document.sources
                or any(
                    source.kind != "collected"
                    or (source.repository_id, source.commit_sha)
                    != (row.source_repository_id, row.source_commit_sha)
                    for source in document.sources
                )
            ):
                raise ValueError
        elif (
            row.operation_digest is not None
            or row.source_repository_id is not None
            or row.source_commit_sha is not None
        ):
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def _signed():
    value = authority.current()
    if value is None or not value.reserved:
        raise LifecycleError(401)
    return value


def _scope(session, capability, *, mutation=False):
    value = _signed()
    return support.scope(
        session,
        value.definition.project_id,
        value.definition.workspace_id,
        capability,
        mutation=mutation,
    )


def request_trigger(payload, *, registry=None, registry_contract=None):
    credential = _signed()
    payload = credential.bind_model(
        payload,
        TriggerRequest,
        {
            "/api/v1/infra-automation/triggers/webhook",
            "/api/v1/infra-automation/triggers/cli/run",
        },
    )
    definition = credential.definition
    if (payload.project_id, payload.workspace_id) != (
        definition.project_id,
        definition.workspace_id,
    ):
        raise auth.TrustedAuthorizationError()
    expected = "cli" if credential.fields["path"].endswith("/cli/run") else None
    if (expected and payload.source.origin != expected) or (
        not expected and payload.source.origin not in {"webhook", "pull_request"}
    ):
        raise LifecycleError(422)
    operation = support.digest(
        support.canonical(
            {
                "key_id": definition.key_id,
                "principal_id": definition.principal_id,
                "path": credential.fields["path"],
                "body_digest": credential.proof.body_digest,
            }
        )
    )
    internal_key = (
        "signed-"
        + hashlib.sha256(
            support.canonical(
                [definition.key_id, credential.fields["path"], payload.idempotency_key]
            )
        ).hexdigest()
    )
    with auth.authorized_session() as session:
        grant = _scope(session, "automation.request", mutation=True)
        revision = workflows.get_revision(session, payload.workflow_revision_id)
        if (
            revision is None
            or revision.project_id != payload.project_id
            or revision.workspace_id not in {None, payload.workspace_id}
        ):
            raise auth.TrustedAuthorizationError()
        request = RunRequest(
            workflow_id=revision.workflow_id,
            revision_id=revision.id,
            workspace_id=payload.workspace_id,
            inputs=payload.inputs,
            idempotency_key=internal_key,
            total_timeout_seconds=3600,
            reason="Authenticated signed trigger request.",
        )
        if (
            payload.workflow_revision_id not in definition.allowed_revision_ids
            or payload.source.origin not in definition.allowed_origins
            or (payload.source.repository_id, payload.source.commit_sha)
            not in {(s.repository_id, s.commit_sha) for s in definition.allowed_sources}
        ):
            raise auth.TrustedAuthorizationError()
        existing = runs.get_request(
            session,
            project_id=payload.project_id,
            workspace_id=payload.workspace_id,
            requested_by=grant.principal.principal_id,
            key_digest=support.digest(internal_key.encode()),
        )
        if existing is not None:
            origin = session.get(InfraAutomationRunOrigin, existing.run_id)
            if origin is None or origin.operation_digest != operation:
                raise LifecycleError(409)
            result = engine.request_run(
                request, registry=registry, registry_contract=registry_contract
            )
            credential.protect(result)
            _scope(session, "automation.request", mutation=True)
            return result
        token = _ORIGIN.set(
            _Origin(
                payload.source.origin,
                definition.key_id,
                payload.source.pr_ref,
                operation,
            )
        )
        try:
            result = engine.request_run(
                request, registry=registry, registry_contract=registry_contract
            )
        finally:
            _ORIGIN.reset(token)
        run = runs.get_run(session, result["id"])
        document = engine._document(run)
        if not document.sources or any(
            s.kind != "collected"
            or (s.repository_id, s.commit_sha)
            != (payload.source.repository_id, payload.source.commit_sha)
            for s in document.sources
        ):
            raise LifecycleError(422)
        credential.protect(result)
        _scope(session, "automation.request", mutation=True)
        return result


def validate_signed(payload):
    value = _signed()
    payload = value.bind_model(
        payload, ValidateWorkflowRequest, {"/api/v1/infra-automation/triggers/validate"}
    )
    if (payload.project_id, payload.workspace_id) != (
        value.definition.project_id,
        value.definition.workspace_id,
    ):
        raise auth.TrustedAuthorizationError()
    with auth.authorized_session() as session:
        _scope(session, "automation.read")
        from services.infra_automation_service import _validation

        validation = support.validate_definition(
            payload.definition.encode(), payload.project_id, payload.workspace_id
        )
        if validation.definition is not None:
            value.protect(validation.definition.model_dump(mode="json"))
        result = support.bounded_payload(
            _validation(
                payload.definition.encode(),
                payload.project_id,
                payload.workspace_id,
                None,
            )
        )
        value.protect(result)
        _scope(session, "automation.read")
        return result


def signed_status(payload):
    value = _signed()
    payload = value.bind_model(
        payload, TriggerStatusRequest, {"/api/v1/infra-automation/triggers/status"}
    )
    with auth.authorized_session() as session:
        _scope(session, "automation.read")
        result = engine.get_run(payload.run_id)
        value.protect(result)
        _scope(session, "automation.read")
        return result


def signed_list(payload):
    value = _signed()
    payload = value.bind_model(
        payload, TriggerListRequest, {"/api/v1/infra-automation/triggers/list"}
    )
    with auth.authorized_session() as session:
        _scope(session, "automation.read")
        if payload.workflow_id is not None:
            workflow = workflows.get_workflow(
                session, support.identifier(payload.workflow_id)
            )
            if (
                workflow is None
                or workflow.project_id != value.definition.project_id
                or workflow.workspace_id not in {None, value.definition.workspace_id}
            ):
                raise auth.TrustedAuthorizationError()
        result = engine.list_runs(
            value.definition.project_id,
            value.definition.workspace_id,
            payload.limit,
            payload.cursor,
            workflow_id=payload.workflow_id,
        )
        value.protect(result)
        _scope(session, "automation.read")
        return result
