"""Shared transaction-local values for the scoped workflow lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

import config
from infra_automation.contracts import SAFE_INTEGER, RegistryContract
from infra_automation.lifecycle import AutomationSettings, LifecycleError
from infra_automation.workflow_schema import Identifier, Workflow
from infra_automation.workflow_validation import validate_workflow
from models.repositories import infra_automation_workflows as repository
from models.repositories.settings import get_setting
from models.tables import Project
from services.content_security import (
    BLOCKED_CONTENT,
    REDACTED,
    redact_reference,
    redact_value,
)
from services.policy_adapter_settings import PolicyAdapterSettings
from services import project_service as authorization

T = TypeVar("T", bound=BaseModel)


def canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def revalidate(value: T, model: type[T]) -> T:
    try:
        if type(value) is not model:
            raise ValueError
        return model.model_validate(value.model_dump(warnings="error"))
    except (ValueError, TypeError):
        raise LifecycleError(422) from None


def identifier(value: str) -> str:
    try:
        return TypeAdapter(Identifier).validate_python(value)
    except ValidationError:
        raise LifecycleError(422) from None


def screened(value):
    """Reject rather than rewrite typed content whose canonical identity matters."""
    wrapped = {"metadata": value}
    encoded = canonical(value)
    if redact_value(wrapped) != wrapped or any(
        marker.encode() in encoded for marker in (REDACTED, BLOCKED_CONTENT)
    ):
        raise LifecycleError(422)
    return value


def screened_label(value: str) -> str:
    if (
        redact_reference(value) != value
        or REDACTED in value
        or BLOCKED_CONTENT in value
    ):
        raise LifecycleError(422)
    return value


def bounded_payload(value: dict) -> dict:
    # Match the adapter's complete envelope before the service transaction commits.
    # Import lazily because API schemas also declare lifecycle response models.
    from api.schemas import build_meta

    envelope = {"data": value, "meta": build_meta(correlation_id="0" * 32)}
    if len(canonical(envelope)) > 131072:
        raise LifecycleError(429)
    return value


def scope(
    session: Session,
    project_id: int,
    workspace_id: int | None,
    capability: str,
    *,
    mutation: bool,
) -> authorization.TrustedProjectScope:
    if (
        type(project_id) is not int
        or not 1 <= project_id <= SAFE_INTEGER
        or (
            workspace_id is not None
            and (type(workspace_id) is not int or not 1 <= workspace_id <= SAFE_INTEGER)
        )
    ):
        raise authorization.TrustedAuthorizationError()
    resolved = authorization.guard_project(
        session, project_id, workspace_id, capability, mutation=mutation
    )
    if resolved is None:
        raise authorization.TrustedAuthorizationError()
    return resolved


def workflow(session: Session, workflow_id: str, capability: str, *, mutation: bool):
    row = repository.get_workflow(session, identifier(workflow_id))
    if row is None:
        raise authorization.TrustedAuthorizationError()
    grant = scope(
        session, row.project_id, row.workspace_id, capability, mutation=mutation
    )
    return row, grant


def validate_definition(
    raw: bytes,
    project_id: int,
    workspace_id: int | None,
    registry: RegistryContract | None = None,
):
    try:
        limits = config.workflow_validation_limits()
    except ValueError:
        raise LifecycleError(503) from None
    result = validate_workflow(raw, limits=limits, registry_contract=registry)
    if result.valid:
        definition = result.definition
        if definition is None:
            raise LifecycleError(503)
        if definition.project_id != str(project_id) or definition.workspace_id != (
            str(workspace_id) if workspace_id is not None else None
        ):
            raise authorization.TrustedAuthorizationError()
        screened(definition.model_dump(mode="json"))
    return result


def stored_definition(
    raw: bytes, expected_digest: str, project_id: int, workspace_id: int | None
) -> dict:
    try:
        if (
            type(raw) is not bytes
            or len(raw) > 131072
            or digest(raw) != expected_digest
        ):
            raise ValueError
        typed = Workflow.model_validate_json(raw)
        value = typed.model_dump(mode="json")
        if (
            canonical(value) != raw
            or typed.project_id != str(project_id)
            or typed.workspace_id
            != (str(workspace_id) if workspace_id is not None else None)
        ):
            raise ValueError
        return screened(value)
    except (ValueError, TypeError):
        raise LifecycleError(503) from None


def policy_state(session: Session, project_id: int):
    row = repository.get_policy(session, project_id=project_id)

    def unique_fields(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    def reject_constant(value):
        raise ValueError

    try:
        if row is None:
            return None, config.automation_settings_defaults()
        if (
            any(
                type(value) is not int or not 1 <= value <= SAFE_INTEGER
                for value in (row.version, row.authorization_epoch, row.restore_epoch)
            )
            or type(row.settings_json) is not str
            or len(row.settings_json) > 4096
        ):
            raise ValueError
        value = json.loads(
            row.settings_json,
            object_pairs_hook=unique_fields,
            parse_constant=reject_constant,
        )
        if type(value) is not dict or set(value) != set(
            AutomationSettings.model_fields
        ):
            raise ValueError
        settings = AutomationSettings.model_validate(value)
    except (ValueError, TypeError, RecursionError):
        raise LifecycleError(503) from None
    return row, settings


def policy_view(session: Session, project_id: int) -> dict:
    row, settings = policy_state(session, project_id)
    return {
        "project_id": project_id,
        "version": row.version if row else 0,
        "authorization_epoch": row.authorization_epoch if row else 1,
        "restore_epoch": row.restore_epoch if row else 1,
        "settings": settings.model_dump(mode="json"),
    }


def advisory_policy(session: Session, project_id: int) -> PolicyAdapterSettings:
    from services.settings_service import (
        _load_policy_adapter_settings,
        _policy_adapter_settings_key,
    )

    project = session.get(Project, project_id)
    if project is None:
        raise authorization.TrustedAuthorizationError()
    record = get_setting(
        session, _policy_adapter_settings_key(project_key=project.project_key)
    )
    try:
        value = (
            _load_policy_adapter_settings(
                record.value, project_key=project.project_key, integration=None
            )
            if record
            else PolicyAdapterSettings(
                project_key=project.project_key, source="built-in"
            )
        )
        screened(value.model_dump(mode="json"))
        return value
    except (ValueError, RuntimeError):
        raise LifecycleError(503) from None


def append_audit(
    session: Session,
    grant: authorization.TrustedProjectScope,
    *,
    workspace_id: int | None,
    event_type: str,
    target_id: str,
    reason: str,
    before_digest: str | None = None,
    after_digest: str | None = None,
) -> None:
    repository.append_audit(
        session,
        project_id=grant.project_id,
        workspace_id=workspace_id,
        actor_principal_id=grant.principal.principal_id,
        actor_type=grant.principal.principal_type,
        actor_role=grant.role,
        event_type=event_type,
        target_id=identifier(target_id),
        reason=screened_label(reason),
        before_digest=before_digest,
        after_digest=after_digest,
    )
