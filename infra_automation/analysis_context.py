"""Private wrapper-owned analysis authority; never a human or machine issuer."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone

from infra_automation.state import AttemptHandle


@dataclass(frozen=True, repr=False)
class _WorkerOperation:
    handle: AttemptHandle
    factory: object


@dataclass(frozen=True)
class _Attribution:
    principal_id: str


@dataclass(frozen=True)
class _AnalysisScope:
    principal: _Attribution
    project_id: int
    workspace_id: int
    role: str
    authorization_version: int


_operation: ContextVar[_WorkerOperation | None] = ContextVar(
    "private_analysis_operation", default=None
)
_ALLOWED = frozenset(
    {
        "project.read",
        "workspace.read",
        "report.read",
        "topology.read",
        "analysis.submit",
    }
)


def current():
    return _operation.get()


@contextmanager
def _bind_worker(handle, factory):
    """Called only by the fixed local preflight wrapper; no serialized credential."""
    if type(handle) is not AttemptHandle or not callable(factory):
        raise ValueError("Invalid internal worker operation.")
    token = _operation.set(_WorkerOperation(handle, factory))
    try:
        yield
    finally:
        _operation.reset(token)


def validate(session):
    from infra_automation import claims
    from models.repositories import project_memberships
    from services import project_service as auth

    operation = current()
    if operation is None:
        raise auth.TrustedAuthorizationError()
    auth._require_operation(session)
    attempt = claims._attempt(session, operation.handle, datetime.now(timezone.utc))
    if attempt.state != "running" or attempt.step_kind not in {
        "uploaded_intake",
        "shared_analysis",
    }:
        raise auth.TrustedAuthorizationError()
    member = project_memberships.get_membership(
        session,
        principal_id=operation.handle.principal_id,
        project_id=operation.handle.project_id,
    )
    if (
        member is None
        or not member.enabled
        or "analysis.submit" not in auth.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
    ):
        raise auth.TrustedAuthorizationError()
    return operation.handle, member


def guard_scope(session, project_id, workspace_id, capability):
    from services import project_service as auth

    handle, member = validate(session)
    if (
        capability not in _ALLOWED
        or capability not in auth.PROJECT_ROLE_CAPABILITIES.get(member.role, ())
        or project_id != handle.project_id
        or (
            workspace_id != handle.workspace_id
            and not (workspace_id is None and capability == "project.read")
        )
    ):
        raise auth.TrustedAuthorizationError()
    return _AnalysisScope(
        _Attribution(handle.principal_id),
        handle.project_id,
        handle.workspace_id,
        member.role,
        member.authorization_version,
    )
