"""Shared project/workspace service helpers."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, exists, false, func, or_, select, true
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, aliased

import config

from models.database import SessionLocal, init_db
from models.repositories.projects import (
    create_project as create_project_record,
    create_workspace as create_workspace_record,
    get_default_project,
    get_project,
    get_project_by_key,
    get_workspace,
    get_workspace_by_key,
    list_projects as list_project_records,
)
from models.repositories.settings import delete_setting, get_setting, upsert_setting
from models.repositories import project_memberships as membership_repository
from models.repositories.identity import revoke_sessions
from models.tables import (
    AnalysisReport,
    IdentityAccount,
    Project,
    ProjectAuthorizationAudit,
    ProjectMembership,
    ProjectWorkspace,
)
from services.identity_service import IdentityError, IdentityService, VerifiedPrincipal

DEFAULT_PROJECT_KEY = "unassigned"
DEFAULT_PROJECT_NAME = "Unassigned"
ACTIVE_PROJECT_SETTING_KEY = "active_project_id"
_PROJECT_KEY_PATTERN = re.compile(r"[^a-z0-9]+")


class ProjectResolutionError(ValueError):
    """Raised when a project reference is invalid or ambiguous."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ProjectAuthorizationError(PermissionError):
    """Raised when an actor is not authorized for a project action."""

    def __init__(self, result: "ProjectAuthorizationResult") -> None:
        super().__init__(result.message)
        self.result = result
        self.code = result.code
        self.message = result.message


class ProjectRecord(BaseModel):
    id: int
    project_key: str
    display_name: str
    description: str | None = None
    repository_url: str | None = None
    default_branch: str | None = None
    is_default: bool = False
    created_at: str
    updated_at: str


class WorkspaceRecord(BaseModel):
    id: int
    project_id: int
    project_key: str
    workspace_key: str
    display_name: str
    description: str | None = None
    environment: str | None = None
    created_at: str
    updated_at: str


class ProjectRoleDefinition(BaseModel):
    role: str
    display_name: str
    description: str
    capabilities: list[str]


class ProjectAuthorizationResult(BaseModel):
    allowed: bool
    code: str
    message: str
    role: str
    capability: str
    project_key: str | None = None


PROJECT_ROLE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "admin": (
        "project.read",
        "project.manage",
        "workspace.read",
        "workspace.manage",
        "analysis.submit",
        "report.read",
        "report.review",
        "report.share.manage",
        "feedback.create",
        "outcome.read",
        "outcome.manage",
        "incident.manage",
        "topology.read",
        "topology.manage",
        "scanner.manage",
        "settings.manage",
        "role.manage",
    ),
    "maintainer": (
        "project.read",
        "workspace.read",
        "workspace.manage",
        "analysis.submit",
        "report.read",
        "report.review",
        "report.share.manage",
        "feedback.create",
        "outcome.read",
        "outcome.manage",
        "incident.manage",
        "topology.read",
        "topology.manage",
        "scanner.manage",
    ),
    "reviewer": (
        "project.read",
        "workspace.read",
        "report.read",
        "report.review",
        "feedback.create",
        "outcome.read",
        "topology.read",
    ),
    "contributor": (
        "project.read",
        "workspace.read",
        "analysis.submit",
        "report.read",
        "feedback.create",
        "topology.read",
    ),
    "read-only": (
        "project.read",
        "workspace.read",
        "report.read",
        "topology.read",
    ),
}

_AUTOMATION_CAPABILITIES = {
    "admin": ("read", "request", "draft", "publish", "decision", "cancel", "admin"),
    "maintainer": ("read", "request", "draft", "decision", "cancel"),
    "reviewer": ("read", "decision"),
    "contributor": ("read", "request", "cancel"),
    "read-only": ("read",),
}
for _role, _actions in _AUTOMATION_CAPABILITIES.items():
    PROJECT_ROLE_CAPABILITIES[_role] += tuple(
        f"automation.{action}" for action in _actions
    )

PROJECT_ROLE_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "admin": (
        "Admin",
        "Full project administration, settings, role, and data-management access.",
    ),
    "maintainer": (
        "Maintainer",
        "Operational ownership for project context, analysis, reports, and imports.",
    ),
    "reviewer": (
        "Reviewer",
        "Review-focused access for reports and finding feedback.",
    ),
    "contributor": (
        "Contributor",
        "Submission access for analyses plus report and feedback participation.",
    ),
    "read-only": (
        "Read-only",
        "Read access to project, workspace, and report metadata.",
    ),
}


def list_project_role_definitions() -> list[ProjectRoleDefinition]:
    return [
        ProjectRoleDefinition(
            role=role,
            display_name=PROJECT_ROLE_DESCRIPTIONS[role][0],
            description=PROJECT_ROLE_DESCRIPTIONS[role][1],
            capabilities=list(capabilities),
        )
        for role, capabilities in PROJECT_ROLE_CAPABILITIES.items()
    ]


def _serialize(record) -> ProjectRecord:
    created_at = record.created_at.isoformat()
    updated_at = record.updated_at.isoformat()
    return ProjectRecord(
        id=record.id,
        project_key=record.project_key,
        display_name=record.display_name,
        description=record.description,
        repository_url=record.repository_url,
        default_branch=record.default_branch,
        is_default=record.is_default,
        created_at=created_at,
        updated_at=updated_at,
    )


def _serialize_workspace(record) -> WorkspaceRecord:
    project_key = record.project.project_key if record.project is not None else ""
    return WorkspaceRecord(
        id=record.id,
        project_id=record.project_id,
        project_key=project_key,
        workspace_key=record.workspace_key,
        display_name=record.display_name,
        description=record.description,
        environment=record.environment,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def normalize_project_key(value: str) -> str:
    normalized = _PROJECT_KEY_PATTERN.sub("-", value.strip().lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    if not normalized:
        raise ValueError("Project key must contain at least one letter or number.")
    return normalized


def normalize_workspace_key(value: str) -> str:
    try:
        return normalize_project_key(value)
    except ValueError as exc:
        raise ValueError(
            "Workspace key must contain at least one letter or number."
        ) from exc


def normalize_project_role(value: str | None) -> str:
    if value is None:
        return "admin"
    role = str(value).strip().lower().replace("_", "-")
    if not role:
        raise ValueError("Project role must contain at least one letter or number.")
    if role not in PROJECT_ROLE_CAPABILITIES:
        raise ValueError(f"Unknown project role: {role}")
    return role


def _normalize_allowed_project_keys(
    allowed_project_keys: list[str] | tuple[str, ...] | set[str] | None,
) -> set[str] | None:
    if allowed_project_keys is None:
        return None
    normalized_keys: set[str] = set()
    for project_key in allowed_project_keys:
        if not str(project_key or "").strip():
            continue
        try:
            normalized_keys.add(normalize_project_key(project_key))
        except ValueError:
            continue
    return normalized_keys


def authorize_project_action(
    *,
    role: str | None = None,
    capability: str,
    project_key: str | None = None,
    allowed_project_keys: list[str] | tuple[str, ...] | set[str] | None = None,
) -> ProjectAuthorizationResult:
    try:
        normalized_role = normalize_project_role(role)
    except ValueError:
        return ProjectAuthorizationResult(
            allowed=False,
            code="invalid_project_role",
            message="Caller supplied an unknown project role.",
            role=str(role or ""),
            capability=capability,
        )

    if (
        capability.startswith("automation.")
        or capability not in PROJECT_ROLE_CAPABILITIES[normalized_role]
    ):
        return ProjectAuthorizationResult(
            allowed=False,
            code="project_permission_denied",
            message="Caller role is not authorized for this project action.",
            role=normalized_role,
            capability=capability,
            project_key=None,
        )

    normalized_project_key = normalize_project_key(project_key) if project_key else None
    allowed_keys = _normalize_allowed_project_keys(allowed_project_keys)
    if normalized_role != "admin" and not allowed_keys:
        return ProjectAuthorizationResult(
            allowed=False,
            code="project_scope_required",
            message="Caller role requires an explicit project scope.",
            role=normalized_role,
            capability=capability,
            project_key=None,
        )
    if normalized_project_key is not None and allowed_keys is not None:
        if normalized_project_key not in allowed_keys:
            return ProjectAuthorizationResult(
                allowed=False,
                code="project_scope_forbidden",
                message="Caller is not authorized for the requested project.",
                role=normalized_role,
                capability=capability,
                project_key=None,
            )

    return ProjectAuthorizationResult(
        allowed=True,
        code="project_authorized",
        message="Caller is authorized for this project action.",
        role=normalized_role,
        capability=capability,
        project_key=normalized_project_key,
    )


def require_project_permission(
    *,
    role: str | None = None,
    capability: str,
    project_key: str | None = None,
    allowed_project_keys: list[str] | tuple[str, ...] | set[str] | None = None,
) -> ProjectAuthorizationResult:
    result = authorize_project_action(
        role=role,
        capability=capability,
        project_key=project_key,
        allowed_project_keys=allowed_project_keys,
    )
    if not result.allowed:
        raise ProjectAuthorizationError(result)
    return result


def filter_projects_by_authorization(
    projects: list[ProjectRecord],
    *,
    role: str | None = None,
    allowed_project_keys: list[str] | tuple[str, ...] | set[str] | None = None,
) -> list[ProjectRecord]:
    require_project_permission(
        role=role,
        capability="project.read",
        allowed_project_keys=allowed_project_keys,
    )
    allowed_keys = _normalize_allowed_project_keys(allowed_project_keys)
    if allowed_keys is None:
        return projects
    return [project for project in projects if project.project_key in allowed_keys]


def has_restricted_project_scope(
    *,
    role: str | None = None,
    allowed_project_keys: list[str] | tuple[str, ...] | set[str] | None = None,
) -> bool:
    """Return whether an actor should not receive project existence details."""
    allowed_keys = _normalize_allowed_project_keys(allowed_project_keys)
    if allowed_keys is not None:
        return True
    try:
        return normalize_project_role(role) != "admin"
    except ValueError:
        return True


def _is_workspace_unique_integrity_error(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
    if constraint_name == "uq_project_workspaces_project_key":
        return True
    message = str(exc.orig).lower()
    return (
        "uq_project_workspaces_project_key" in message
        or (
            "unique constraint failed" in message
            and "project_workspaces.project_id" in message
            and "project_workspaces.workspace_key" in message
        )
        or (
            "duplicate key" in message
            and "project_workspaces" in message
            and "workspace_key" in message
        )
    )


def _is_project_unique_integrity_error(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
    if constraint_name in {"uq_projects_project_key", "projects_project_key_key"}:
        return True
    message = str(exc.orig).lower()
    return (
        "uq_projects_project_key" in message
        or ("unique constraint failed" in message and "projects.project_key" in message)
        or (
            "duplicate key" in message
            and "projects" in message
            and "project_key" in message
        )
    )


def _is_workspace_project_fk_integrity_error(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
    if constraint_name in {
        "project_workspaces_project_id_fkey",
        "fk_project_workspaces_project_id_projects",
    }:
        return True
    message = str(exc.orig).lower()
    return "foreign key constraint failed" in message or (
        "violates foreign key constraint" in message
        and "project_workspaces" in message
        and "project_id" in message
    )


def _display_name_from_key(project_key: str) -> str:
    parts = [part for part in project_key.replace("_", "-").split("-") if part]
    if not parts:
        return DEFAULT_PROJECT_NAME
    words: list[str] = []
    for part in parts:
        if len(part) <= 3:
            words.append(part.upper())
        else:
            words.append(part.capitalize())
    return " ".join(words)


def derive_project_key_from_repository(repository_name: str) -> str:
    _, repository_path = _parse_repository_reference(repository_name)
    trimmed = repository_path or str(repository_name or "").strip().rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[:-4]
    if "/" not in trimmed:
        return normalize_project_key(trimmed)
    owner, leaf = trimmed.split("/", maxsplit=1)
    return normalize_project_key(f"{owner}-{leaf}")


def _parse_repository_reference(
    repository_name: str | None,
) -> tuple[str | None, str | None]:
    trimmed = str(repository_name or "").strip().rstrip("/")
    if not trimmed:
        return None, None
    parsed = urlparse(trimmed)
    host: str | None = None
    path = trimmed
    if parsed.scheme or parsed.netloc:
        host = parsed.netloc.rsplit("@", maxsplit=1)[-1].lower() or None
        path = parsed.path
    elif ":" in trimmed:
        host_part, path_part = trimmed.split(":", maxsplit=1)
        if "@" in host_part or "." in host_part:
            host = host_part.rsplit("@", maxsplit=1)[-1].lower() or None
            path = path_part
    else:
        parts = trimmed.split("/", maxsplit=1)
        if len(parts) == 2 and "." in parts[0]:
            host = parts[0].lower() or None
            path = parts[1]
    canonical_path = path.strip("/")
    if canonical_path.endswith(".git"):
        canonical_path = canonical_path[:-4]
    return host, canonical_path.lower() or None


def _canonical_repository_name(repository_name: str | None) -> str | None:
    host, repository_path = _parse_repository_reference(repository_name)
    if repository_path is None:
        return None
    if host is None:
        return repository_path
    return f"{host}/{repository_path}"


def _repository_project_key(repository_name: str) -> str:
    canonical = _canonical_repository_name(repository_name) or str(repository_name)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
    return f"{derive_project_key_from_repository(repository_name)}-{digest}"


def _repository_matches_project(record, repository_name: str | None) -> bool:
    record_repository = _canonical_repository_name(
        getattr(record, "repository_url", None)
    )
    requested_repository = _canonical_repository_name(repository_name)
    if requested_repository is None:
        return True
    if record_repository is None:
        return False
    return record_repository == requested_repository


def _repository_storage_value(repository_name: str | None) -> str | None:
    return _canonical_repository_name(repository_name) or (
        str(repository_name).strip() if repository_name is not None else None
    )


def _find_project_by_repository(session, repository_name: str | None):
    requested_repository = _canonical_repository_name(repository_name)
    if requested_repository is None:
        return None
    for record in list_project_records(session):
        if _canonical_repository_name(getattr(record, "repository_url", None)) == (
            requested_repository
        ):
            return record
    return None


def display_name_from_repository(repository_name: str) -> str:
    trimmed = str(repository_name or "").strip().rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[:-4]
    leaf = trimmed.split("/")[-1]
    return _display_name_from_key(leaf or trimmed)


def ensure_default_project() -> ProjectRecord:
    try:
        with authorized_session(SessionLocal) as session:
            default_project = get_default_project(session)
            if default_project is None:
                default_project = create_project_record(
                    session,
                    project_key=DEFAULT_PROJECT_KEY,
                    display_name=DEFAULT_PROJECT_NAME,
                    description="Legacy and unassigned analyses.",
                    is_default=True,
                    commit=False,
                )
            return _serialize(default_project)
    except OperationalError as exc:
        if "no such table: projects" not in str(exc).lower():
            raise
        if _operation_session.get() is not None:
            raise
        init_db()
        with authorized_session(SessionLocal) as session:
            default_project = get_default_project(session)
            if default_project is None:
                default_project = create_project_record(
                    session,
                    project_key=DEFAULT_PROJECT_KEY,
                    display_name=DEFAULT_PROJECT_NAME,
                    description="Legacy and unassigned analyses.",
                    is_default=True,
                    commit=False,
                )
            return _serialize(default_project)


def create_project(
    *,
    project_key: str,
    display_name: str,
    description: str | None = None,
    repository_url: str | None = None,
    default_branch: str | None = None,
) -> ProjectRecord:
    normalized_key = normalize_project_key(project_key)
    normalized_display_name = str(display_name or "").strip()
    if not normalized_display_name:
        raise ValueError("Display name is required.")
    with authorized_session(SessionLocal) as session:
        if _profile() == "verified":
            principal = _verified_principal(session, mutation=True)
            if not principal.is_admin:
                raise TrustedAuthorizationError()
        existing = get_project_by_key(session, normalized_key)
        if existing is not None:
            _guard_project_metadata(session, existing)
            raise ValueError(f"Project key already exists: {normalized_key}")
        try:
            created = create_project_record(
                session,
                project_key=normalized_key,
                display_name=normalized_display_name,
                description=(description or None),
                repository_url=(repository_url or None),
                default_branch=(default_branch or None),
                is_default=False,
                commit=False,
            )
        except IntegrityError as exc:
            session.rollback()
            if not _is_project_unique_integrity_error(exc):
                raise
            raise ValueError(f"Project key already exists: {normalized_key}") from exc
        return _serialize(created)


def create_workspace(
    *,
    project_key: str,
    workspace_key: str,
    display_name: str,
    description: str | None = None,
    environment: str | None = None,
) -> WorkspaceRecord:
    normalized_project_key = normalize_project_key(project_key)
    normalized_workspace_key = normalize_workspace_key(workspace_key)
    normalized_display_name = str(display_name or "").strip()
    if not normalized_display_name:
        raise ValueError("Display name is required.")
    with authorized_session(SessionLocal) as session:
        project = get_project_by_key(session, normalized_project_key)
        if project is None:
            _mask_missing_scope(session)
            raise ProjectResolutionError(
                "project_not_found",
                f"Unknown project reference: project_key={normalized_project_key}.",
            )
        guard_project(session, project.id, capability="workspace.manage", mutation=True)
        existing = get_workspace_by_key(
            session,
            project_id=project.id,
            workspace_key=normalized_workspace_key,
        )
        if existing is not None:
            raise ValueError(
                f"Workspace key already exists for project "
                f"{normalized_project_key}: {normalized_workspace_key}"
            )
        try:
            created = create_workspace_record(
                session,
                project_id=project.id,
                workspace_key=normalized_workspace_key,
                display_name=normalized_display_name,
                description=(description or None),
                environment=(environment or None),
                commit=False,
            )
        except IntegrityError as exc:
            session.rollback()
            if _is_workspace_unique_integrity_error(exc):
                raise ValueError(
                    f"Workspace key already exists for project "
                    f"{normalized_project_key}: {normalized_workspace_key}"
                ) from exc
            if _is_workspace_project_fk_integrity_error(exc):
                raise ProjectResolutionError(
                    "project_not_found",
                    f"Unknown project reference: project_key={normalized_project_key}.",
                ) from exc
            raise
        created.project = project
        return _serialize_workspace(created)


def list_projects() -> list[ProjectRecord]:
    ensure_default_project()
    with authorized_session(SessionLocal) as session:
        return [
            _serialize(record)
            for record in session.scalars(
                select(Project)
                .where(visible_project_predicate(session))
                .order_by(Project.is_default.desc(), Project.project_key.asc())
            )
        ]


def list_workspaces(*, project_key: str | None = None) -> list[WorkspaceRecord]:
    if project_key is None:
        normalized_project_key = ensure_default_project().project_key
    else:
        normalized_project_key = normalize_project_key(project_key)
    with authorized_session(SessionLocal) as session:
        project = get_project_by_key(session, normalized_project_key)
        if project is None:
            _mask_missing_scope(session)
            raise ProjectResolutionError(
                "project_not_found",
                f"Unknown project reference: project_key={normalized_project_key}.",
            )
        _guard_project_metadata(session, project)
        return [
            _serialize_workspace(record)
            for record in session.scalars(
                select(ProjectWorkspace)
                .where(
                    ProjectWorkspace.project_id == project.id,
                    visible_context_predicate(
                        session,
                        ProjectWorkspace.project_id,
                        ProjectWorkspace.id,
                        "workspace.read",
                    ),
                )
                .order_by(ProjectWorkspace.workspace_key)
            )
        ]


def get_project_by_id(project_id: int) -> ProjectRecord | None:
    with authorized_session(SessionLocal) as session:
        record = get_project(session, project_id)
        _guard_project_metadata(session, record)
        return _serialize(record) if record is not None else None


def get_project_by_project_key(project_key: str) -> ProjectRecord | None:
    with authorized_session(SessionLocal) as session:
        record = get_project_by_key(session, normalize_project_key(project_key))
        _guard_project_metadata(session, record)
        return _serialize(record) if record is not None else None


def resolve_project_reference(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    repository_name: str | None = None,
    allow_create: bool = False,
) -> ProjectRecord:
    raw_project_key = str(project_key) if project_key is not None else None
    project_key = raw_project_key.strip() if raw_project_key is not None else None
    if project_id is None and raw_project_key is not None and not project_key:
        raise ProjectResolutionError(
            "invalid_project_reference",
            "Project key must contain at least one letter or number.",
        )
    ensure_default_project()
    normalized_key = normalize_project_key(project_key) if project_key else None
    derived_key = (
        derive_project_key_from_repository(repository_name) if repository_name else None
    )
    with authorized_session(SessionLocal) as session:
        record_by_id = (
            get_project(session, project_id) if project_id is not None else None
        )
        record_by_key = (
            get_project_by_key(session, normalized_key)
            if normalized_key is not None
            else None
        )
        for candidate in (record_by_id, record_by_key):
            if candidate is not None:
                _guard_project_metadata(session, candidate)
        if project_id is not None and record_by_id is None:
            _mask_missing_scope(session)
            detail = (
                f"project_id={project_id}, project_key={normalized_key}"
                if normalized_key is not None
                else f"project_id={project_id}"
            )
            raise ProjectResolutionError(
                "project_not_found",
                f"Unknown project reference: {detail}.",
            )
        if (
            normalized_key is not None
            and record_by_key is None
            and project_id is not None
        ):
            raise ProjectResolutionError(
                "project_not_found",
                f"Unknown project reference: project_id={project_id}, project_key={normalized_key}.",
            )
        if (
            record_by_id is not None
            and record_by_key is not None
            and record_by_id.id != record_by_key.id
        ):
            raise ProjectResolutionError(
                "conflicting_project_reference",
                "The supplied project_id and project_key refer to different projects.",
            )

        record = record_by_id or record_by_key
        if record is None and derived_key is not None:
            record = _find_project_by_repository(session, repository_name)
            if record is None:
                record = get_project_by_key(session, derived_key)
                if record is not None and not _repository_matches_project(
                    record, repository_name
                ):
                    derived_key = _repository_project_key(str(repository_name))
                    record = get_project_by_key(session, derived_key)

        if record is None and allow_create:
            if _profile() != "legacy-evaluation":
                principal = _verified_principal(session, mutation=True)
                if not principal.is_admin:
                    raise TrustedAuthorizationError()
            if normalized_key is not None:
                record = create_project_record(
                    session,
                    project_key=normalized_key,
                    display_name=_display_name_from_key(normalized_key),
                    commit=False,
                )
            elif derived_key is not None:
                record = create_project_record(
                    session,
                    project_key=derived_key,
                    display_name=display_name_from_repository(
                        repository_name or derived_key
                    ),
                    repository_url=_repository_storage_value(repository_name),
                    commit=False,
                )
        elif record is None and (project_id is not None or normalized_key is not None):
            _mask_missing_scope(session)
            detail = (
                f"project_id={project_id}"
                if project_id is not None and normalized_key is None
                else f"project_key={normalized_key}"
                if normalized_key is not None and project_id is None
                else f"project_id={project_id}, project_key={normalized_key}"
            )
            raise ProjectResolutionError(
                "project_not_found",
                f"Unknown project reference: {detail}.",
            )
        if record is None:
            default_record = get_default_project(session)
            if default_record is None:
                raise RuntimeError("Default project could not be resolved.")
            record = default_record
        _guard_project_metadata(session, record)
        return _serialize(record)


def resolve_workspace_reference(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> WorkspaceRecord | None:
    raw_workspace_key = str(workspace_key) if workspace_key is not None else None
    cleaned_workspace_key = (
        raw_workspace_key.strip() if raw_workspace_key is not None else None
    )
    if (
        workspace_id is None
        and raw_workspace_key is not None
        and not cleaned_workspace_key
    ):
        raise ProjectResolutionError(
            "invalid_workspace_reference",
            "Workspace key must contain at least one letter or number.",
        )
    if workspace_id is None and not cleaned_workspace_key:
        return None
    if cleaned_workspace_key and project_id is None and project_key is None:
        raise ProjectResolutionError(
            "missing_project_scope",
            "Project scope is required when resolving workspace_key.",
        )

    resolved_project = (
        resolve_project_reference(project_id=project_id, project_key=project_key)
        if project_id is not None or project_key is not None or cleaned_workspace_key
        else None
    )
    normalized_workspace_key = (
        normalize_workspace_key(cleaned_workspace_key)
        if cleaned_workspace_key
        else None
    )
    with authorized_session(SessionLocal) as session:
        record_by_id = (
            get_workspace(session, workspace_id) if workspace_id is not None else None
        )
        record_by_key = (
            get_workspace_by_key(
                session,
                project_id=resolved_project.id,
                workspace_key=normalized_workspace_key,
            )
            if resolved_project is not None and normalized_workspace_key is not None
            else None
        )
        for candidate in (record_by_id, record_by_key):
            if candidate is not None:
                guard_project(
                    session, candidate.project_id, candidate.id, "workspace.read"
                )
        if workspace_id is not None and record_by_id is None:
            _mask_missing_scope(session)
            raise ProjectResolutionError(
                "workspace_not_found",
                f"Unknown workspace reference: workspace_id={workspace_id}.",
            )
        if (
            normalized_workspace_key is not None
            and resolved_project is not None
            and record_by_key is None
        ):
            _mask_missing_scope(session)
            raise ProjectResolutionError(
                "workspace_not_found",
                (
                    "Unknown workspace reference: "
                    f"project_key={resolved_project.project_key}, "
                    f"workspace_key={normalized_workspace_key}."
                ),
            )
        if (
            record_by_id is not None
            and resolved_project is not None
            and record_by_id.project_id != resolved_project.id
        ):
            raise ProjectResolutionError(
                "conflicting_workspace_reference",
                "The supplied workspace_id does not belong to the supplied project.",
            )
        if (
            record_by_id is not None
            and record_by_key is not None
            and record_by_id.id != record_by_key.id
        ):
            raise ProjectResolutionError(
                "conflicting_workspace_reference",
                "The supplied workspace_id and workspace_key refer to different workspaces.",
            )
        record = record_by_id or record_by_key
        if record is None:
            return None
        return _serialize_workspace(record)


def set_active_project(project_id: int) -> ProjectRecord:
    with authorized_session(SessionLocal) as session:
        project = resolve_project_reference(project_id=project_id)
        guard_global_configuration(session, mutation=True)
        upsert_setting(
            session, key=ACTIVE_PROJECT_SETTING_KEY, value=str(project.id), commit=False
        )
    return project


def clear_active_project_selection() -> None:
    """Clear the saved active-project selection for UI surfaces."""
    with authorized_session(SessionLocal) as session:
        guard_global_configuration(session, mutation=True)
        delete_setting(session, ACTIVE_PROJECT_SETTING_KEY, commit=False)


def get_active_project() -> ProjectRecord | None:
    ensure_default_project()
    with authorized_session(SessionLocal) as session:
        setting = get_setting(session, ACTIVE_PROJECT_SETTING_KEY)
        if setting is None:
            record = get_default_project(session)
            try:
                _guard_project_metadata(session, record)
            except TrustedAuthorizationError:
                return None
            return _serialize(record)
        try:
            project_id = int(setting.value)
        except (TypeError, ValueError):
            project_id = 0
        record = get_project(session, project_id)
        if record is None:
            record = get_default_project(session)
        try:
            _guard_project_metadata(session, record)
        except TrustedAuthorizationError:
            return None
        return _serialize(record)


def has_active_project_selection() -> bool:
    ensure_default_project()
    with authorized_session(SessionLocal) as session:
        setting = get_setting(session, ACTIVE_PROJECT_SETTING_KEY)
        if setting is None:
            return False
        try:
            project_id = int(setting.value)
        except (TypeError, ValueError):
            return False
        record = get_project(session, project_id)
        try:
            _guard_project_metadata(session, record)
        except TrustedAuthorizationError:
            return False
        return record is not None


def build_project_payload(project: ProjectRecord | dict[str, Any]) -> dict[str, Any]:
    if isinstance(project, ProjectRecord):
        return project.model_dump()
    return dict(project)


def build_workspace_payload(
    workspace: WorkspaceRecord | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(workspace, WorkspaceRecord):
        return workspace.model_dump()
    return dict(workspace)


class TrustedAuthorizationError(PermissionError):
    """Uniform denial with no principal, object or scope existence details."""

    code = "operation_unavailable"
    message = "Operation unavailable."
    status_code = 403

    def __init__(self):
        super().__init__(self.message)


@dataclass(frozen=True, repr=False)
class _CredentialContext:
    service: IdentityService
    token: str
    csrf_token: str | None
    mutation: bool
    transport_check: Callable[[], None] | None


@dataclass(frozen=True)
class TrustedProjectScope:
    principal: VerifiedPrincipal
    project_id: int
    workspace_id: int | None
    role: str
    authorization_version: int


class MembershipView(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)
    principal_id: str
    project_id: int
    workspace_id: int | None
    role: str
    enabled: bool
    authorization_version: int


@dataclass(frozen=True)
class DecisionContext:
    """Server-owned seeded integration port; never construct from HTTP claims."""

    project_id: int
    workspace_id: int | None
    report_id: int
    requester_principal_id: str
    object_id: str


_credentials: ContextVar[_CredentialContext | None] = ContextVar(
    "project_credentials", default=None
)
_operation_session: ContextVar[Session | None] = ContextVar(
    "project_operation_session", default=None
)
_operation_transaction: ContextVar[object | None] = ContextVar(
    "project_operation_transaction", default=None
)


@contextmanager
def credential_context(
    service: IdentityService,
    token: str,
    *,
    csrf_token: str | None = None,
    mutation: bool = False,
    transport_check: Callable[[], None] | None = None,
) -> Iterator[None]:
    """Bind credentials only; every protected operation re-resolves authority."""
    context_token = _credentials.set(
        _CredentialContext(service, token, csrf_token, mutation, transport_check)
    )
    try:
        yield
    finally:
        _credentials.reset(context_token)


def has_authorized_session() -> bool:
    """Whether this caller already owns an authorization transaction."""
    return _operation_session.get() is not None


@contextmanager
def authorized_session(session_factory=None) -> Iterator[Session]:
    """Reserve SQLite before any object/authority read; nested services reuse it.

    Repositories called inside this boundary must flush, never commit. Only the
    outermost operation owns commit/rollback and materializes its response.
    """
    active = _operation_session.get()
    if active is not None:
        _require_operation(active)
        yield active
        return
    from infra_automation.analysis_context import current as worker_operation

    worker = worker_operation()
    credentials = _credentials.get()
    factory = (
        worker.factory
        if worker is not None
        else session_factory
        or (credentials.service.session_factory if credentials else SessionLocal)
    )
    commit_callbacks: list[Callable[[Callable[[], Session]], None]] = []
    with factory() as session:
        if session.get_bind().dialect.name != "sqlite":
            raise TrustedAuthorizationError()
        context_token = _operation_session.set(session)
        rollback_callbacks = ExitStack()
        session.info["project_operation_rollback"] = rollback_callbacks
        session.info["project_operation_commit"] = commit_callbacks
        transaction_token = None
        connection = None
        try:
            connection = session.connection().connection.driver_connection
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            transaction_token = _operation_transaction.set(session.get_transaction())
            yield session
            _require_operation(session)
            session.commit()
        except BaseException:
            # Compensate filesystem writes while SQLite still reserves the
            # report IDs. Cleanup after rollback could erase a newer writer's
            # artifacts when SQLite reuses an uncommitted integer primary key.
            try:
                if connection is not None and connection.in_transaction:
                    rollback_callbacks.close()
            finally:
                session.rollback()
            raise
        finally:
            session.info.pop("project_operation_rollback", None)
            session.info.pop("project_operation_commit", None)
            if transaction_token is not None:
                _operation_transaction.reset(transaction_token)
            _operation_session.reset(context_token)
    # The original transaction has committed and its context is gone. Deferred
    # filesystem cleanup must reserve a fresh transaction from this same factory
    # before deciding whether an ID is still absent or has been reused.
    for callback in commit_callbacks:
        try:
            callback(factory)
        except Exception:
            # Database deletion already succeeded. An orphan is safer than
            # claiming rollback or retrying cleanup without the reservation.
            logging.getLogger(__name__).warning(
                "Deferred operation cleanup failed; retained artifacts may remain."
            )


def register_operation_rollback(session: Session, callback: Callable[[], None]) -> None:
    """Compensate an authorized side effect if the outer operation cannot commit."""
    _require_operation(session)
    session.info["project_operation_rollback"].callback(callback)


def register_operation_commit(
    session: Session, callback: Callable[[Callable[[], Session]], None]
) -> None:
    """Run cleanup after the outer commit, passing its captured session factory."""
    _require_operation(session)
    session.info["project_operation_commit"].append(callback)


def _require_operation(session: Session) -> None:
    if (
        _operation_session.get() is not session
        or not session.in_transaction()
        or session.get_transaction() is not _operation_transaction.get()
    ):
        raise TrustedAuthorizationError()


def _profile() -> str:
    profile = getattr(config.settings, "authorization_profile", "legacy-evaluation")
    if profile not in {"legacy-evaluation", "verified"}:
        raise TrustedAuthorizationError()
    return profile


def _verified_principal(
    session: Session, *, mutation: bool = False
) -> VerifiedPrincipal:
    _require_operation(session)
    context = _credentials.get()
    if context is None or (mutation and not context.mutation):
        raise TrustedAuthorizationError()
    if context.transport_check is not None:
        context.transport_check()
    try:
        return context.service.resolve_session_in_transaction(
            session,
            context.token,
            csrf_token=(context.csrf_token or "")
            if context.mutation or mutation
            else None,
        )
    except IdentityError:
        raise TrustedAuthorizationError() from None


def _protected_project_predicate(project_id):
    marked_report = aliased(AnalysisReport)
    protected_project = aliased(Project)
    return or_(
        exists(
            select(protected_project.id).where(
                protected_project.id == project_id,
                protected_project.authorization_required.is_(True),
            )
        ),
        exists(
            select(marked_report.id).where(
                marked_report.project_id == project_id,
                marked_report.authorization_required.is_(True),
            )
        ),
    )


def _is_protected(session: Session, project_id: int) -> bool:
    return _profile() == "verified" or bool(
        session.scalar(select(_protected_project_predicate(project_id)))
    )


def project_requires_authorization(session: Session, project_id: int) -> bool:
    """Resolve protection from live server state, including marked child reports."""
    _require_operation(session)
    return _is_protected(session, project_id)


def legacy_request_has_identity() -> bool:
    """Whether credentials were supplied, never proof they are valid authority."""
    context = _credentials.get()
    return context is not None and bool(context.token)


def trusted_capability_allowed(
    principal: VerifiedPrincipal, role: str, capability: str
) -> bool:
    """Pure policy for already verified principals; does not authenticate claims.

    Service/agent audience issuance belongs to 16.17. Its synthetic qualification
    port is restricted to read/request and cannot enter the human HTTP resolver.
    """
    if not principal.enabled or capability not in PROJECT_ROLE_CAPABILITIES.get(
        role, ()
    ):
        return False
    if principal.principal_type == "human":
        return principal.credential_audience == "human"
    return (
        principal.principal_type in {"service", "agent"}
        and principal.credential_audience == "service-request-v1"
        and capability in {"automation.read", "automation.request"}
    )


def guard_project(
    session: Session,
    project_id: int,
    workspace_id: int | None = None,
    capability: str = "report.read",
    expected_version: int | None = None,
    owner_id: str | None = None,
    *,
    mutation: bool | None = None,
) -> TrustedProjectScope | None:
    _require_operation(session)
    from infra_automation.analysis_context import current, guard_scope

    if current() is not None:
        return guard_scope(session, project_id, workspace_id, capability)
    project = session.get(Project, project_id)
    workspace = (
        session.get(ProjectWorkspace, workspace_id)
        if workspace_id is not None
        else None
    )
    if project is None or (
        workspace_id is not None
        and (workspace is None or workspace.project_id != project_id)
    ):
        raise TrustedAuthorizationError()
    if (
        not _is_protected(session, project_id)
        and not capability.startswith("automation.")
        and capability != "role.manage"
    ):
        return None
    principal = _verified_principal(
        session,
        mutation=mutation
        if mutation is not None
        else capability
        not in {
            "project.read",
            "workspace.read",
            "report.read",
            "report.review",
            "outcome.read",
            "topology.read",
            "automation.read",
            "role.manage",
        },
    )
    member = membership_repository.get_membership(
        session, principal_id=principal.principal_id, project_id=project_id
    )
    if (
        member is None
        or not member.enabled
        or (member.workspace_id is not None and member.workspace_id != workspace_id)
        or (
            expected_version is not None
            and member.authorization_version != expected_version
        )
        or not trusted_capability_allowed(principal, member.role, capability)
        or (
            capability == "automation.cancel"
            and member.role != "admin"
            and owner_id != principal.principal_id
        )
    ):
        raise TrustedAuthorizationError()
    return TrustedProjectScope(
        principal,
        project_id,
        member.workspace_id,
        member.role,
        member.authorization_version,
    )


def guard_report(
    session: Session,
    report_id: int,
    capability: str = "report.read",
    *,
    mutation: bool | None = None,
) -> AnalysisReport | None:
    _require_operation(session)
    report = session.get(AnalysisReport, report_id)
    if report is None:
        _mask_missing_scope(session)
        return None
    guard_project(
        session, report.project_id, report.workspace_id, capability, mutation=mutation
    )
    return report


def _visible_scope_predicate(
    session: Session,
    project_id,
    workspace_id,
    capability: str,
    *,
    project_metadata: bool = False,
):
    _require_operation(session)
    from infra_automation.analysis_context import current, guard_scope

    operation = current()
    if operation is not None:
        handle = operation.handle
        guard_scope(session, handle.project_id, handle.workspace_id, capability)
        return and_(
            project_id == handle.project_id,
            true() if project_metadata else workspace_id == handle.workspace_id,
        )
    profile = _profile()
    legacy = (
        ~_protected_project_predicate(project_id)
        if profile == "legacy-evaluation" and not capability.startswith("automation.")
        else false()
    )
    if _credentials.get() is None:
        return legacy
    try:
        principal = _verified_principal(session)
    except TrustedAuthorizationError:
        return legacy
    roles = [
        role
        for role in PROJECT_ROLE_CAPABILITIES
        if trusted_capability_allowed(principal, role, capability)
    ]
    workspace_match = (
        true()
        if project_metadata
        else or_(
            ProjectMembership.workspace_id.is_(None),
            ProjectMembership.workspace_id == workspace_id,
        )
    )
    grant = exists(
        select(ProjectMembership.id).where(
            ProjectMembership.principal_id == principal.principal_id,
            ProjectMembership.project_id == project_id,
            ProjectMembership.enabled.is_(True),
            ProjectMembership.role.in_(roles),
            workspace_match,
        )
    )
    return or_(legacy, grant)


def visible_project_predicate(session: Session, capability: str = "project.read"):
    return _visible_scope_predicate(
        session, Project.id, None, capability, project_metadata=True
    )


def visible_context_predicate(
    session: Session, project_id, workspace_id, capability: str = "report.read"
):
    """Filter scoped context records using the same live membership predicate."""
    return _visible_scope_predicate(session, project_id, workspace_id, capability)


def _mask_missing_scope(session: Session) -> None:
    """Avoid using legacy resolution errors as a protected-object existence oracle."""
    if (
        _profile() == "verified"
        or legacy_request_has_identity()
        or session.scalar(
            select(Project.id).where(_protected_project_predicate(Project.id)).limit(1)
        )
    ):
        raise TrustedAuthorizationError()


def _guard_project_metadata(session: Session, record: Project | None) -> None:
    if record is None:
        _mask_missing_scope(session)
        return
    if (
        session.scalar(
            select(Project.id).where(
                Project.id == record.id, visible_project_predicate(session)
            )
        )
        is None
    ):
        raise TrustedAuthorizationError()


def guard_global_configuration(
    session: Session, *, mutation: bool = False
) -> VerifiedPrincipal | None:
    """Global administration must not change protected projects through defaults."""
    from infra_automation.analysis_context import current

    if current() is not None:
        raise TrustedAuthorizationError()
    _require_operation(session)
    profile = _profile()
    projects = select(Project.id)
    if profile == "legacy-evaluation":
        projects = projects.where(_protected_project_predicate(Project.id))
    protected_ids = list(session.scalars(projects))
    if profile == "legacy-evaluation" and not protected_ids:
        return None
    principal = _verified_principal(session, mutation=mutation)
    if not principal.is_admin:
        raise TrustedAuthorizationError()
    for project_id in protected_ids:
        guard_project(
            session, project_id, capability="settings.manage", mutation=mutation
        )
    return principal


def visible_report_predicate(session: Session, capability: str = "report.read"):
    return _visible_scope_predicate(
        session, AnalysisReport.project_id, AnalysisReport.workspace_id, capability
    )


def _invalidate_principal(session: Session, account: IdentityAccount) -> None:
    account.authentication_version += 1
    revoke_sessions(session, account.id, datetime.now(UTC))


def _membership_view(member: ProjectMembership) -> MembershipView:
    return MembershipView.model_validate(member)


def bootstrap_project_membership(project_id: int) -> MembershipView:
    with authorized_session() as session:
        _profile()
        principal = _verified_principal(session, mutation=True)
        project = session.get(Project, project_id)
        account = session.get(IdentityAccount, principal.principal_id)
        if (
            not principal.is_admin
            or project is None
            or account is None
            or session.scalar(
                select(ProjectMembership.id)
                .where(ProjectMembership.project_id == project_id)
                .limit(1)
            )
            is not None
            or session.scalar(
                select(ProjectAuthorizationAudit.id)
                .where(ProjectAuthorizationAudit.project_id == project_id)
                .limit(1)
            )
            is not None
        ):
            raise TrustedAuthorizationError()
        member = membership_repository.upsert_membership(
            session,
            principal_id=principal.principal_id,
            project_id=project_id,
            role="admin",
        )
        project.authorization_required = True
        view = _membership_view(member)
        membership_repository.append_audit(
            session,
            actor_principal_id=principal.principal_id,
            project_id=project_id,
            target_principal_id=principal.principal_id,
            action="membership.bootstrap",
            after=view.model_dump(),
        )
        _invalidate_principal(session, account)
        return view


def assign_project_membership(
    project_id: int, principal_id: str, role: str, workspace_id: int | None = None
) -> MembershipView:
    with authorized_session() as session:
        _verified_principal(session, mutation=True)
        scope = guard_project(session, project_id, capability="role.manage")
        account = session.get(IdentityAccount, principal_id)
        project = session.get(Project, project_id)
        workspace = (
            session.get(ProjectWorkspace, workspace_id)
            if workspace_id is not None
            else None
        )
        if (
            scope is None
            or project is None
            or scope.workspace_id is not None
            or account is None
            or not account.enabled
            or role not in membership_repository.ROLES
            or (
                workspace_id is not None
                and (workspace is None or workspace.project_id != project_id)
            )
        ):
            raise TrustedAuthorizationError()
        old = membership_repository.get_membership(
            session, principal_id=principal_id, project_id=project_id
        )
        before = _membership_view(old).model_dump() if old else {}
        member = membership_repository.upsert_membership(
            session,
            principal_id=principal_id,
            project_id=project_id,
            role=role,
            workspace_id=workspace_id,
        )
        project.authorization_required = True
        view = _membership_view(member)
        membership_repository.append_audit(
            session,
            actor_principal_id=scope.principal.principal_id,
            project_id=project_id,
            target_principal_id=principal_id,
            workspace_id=workspace_id,
            action="membership.assign",
            before=before,
            after=view.model_dump(),
        )
        _invalidate_principal(session, account)
        return view


def revoke_project_membership(project_id: int, principal_id: str) -> MembershipView:
    with authorized_session() as session:
        _verified_principal(session, mutation=True)
        scope = guard_project(session, project_id, capability="role.manage")
        member = membership_repository.get_membership(
            session, principal_id=principal_id, project_id=project_id
        )
        account = session.get(IdentityAccount, principal_id)
        if (
            scope is None
            or scope.workspace_id is not None
            or member is None
            or account is None
        ):
            raise TrustedAuthorizationError()
        before = _membership_view(member).model_dump()
        member = membership_repository.revoke_membership(
            session, principal_id=principal_id, project_id=project_id
        )
        if member is None:
            raise TrustedAuthorizationError()
        view = _membership_view(member)
        membership_repository.append_audit(
            session,
            actor_principal_id=scope.principal.principal_id,
            project_id=project_id,
            target_principal_id=principal_id,
            workspace_id=member.workspace_id,
            action="membership.revoke",
            before=before,
            after=view.model_dump(),
        )
        _invalidate_principal(session, account)
        return view


def list_project_memberships(project_id: int) -> list[MembershipView]:
    with authorized_session() as session:
        scope = guard_project(session, project_id, capability="role.manage")
        if scope is None or scope.workspace_id is not None:
            raise TrustedAuthorizationError()
        return [
            _membership_view(member)
            for member in membership_repository.list_memberships(
                session, project_id=project_id
            )
        ]


def check_automation_decision(
    context: DecisionContext, *, mutation: bool = False
) -> dict[str, Any]:
    """Read-safe current decision authority; the result is not a credential."""
    with authorized_session() as session:
        _verified_principal(session, mutation=mutation)
        scope = guard_project(
            session,
            context.project_id,
            context.workspace_id,
            "automation.decision",
            mutation=mutation,
        )
        report = guard_report(
            session, context.report_id, "report.review", mutation=mutation
        )
        if (
            scope is None
            or report is None
            or report.project_id != context.project_id
            or report.workspace_id != context.workspace_id
        ):
            raise TrustedAuthorizationError()
        requester = session.get(IdentityAccount, context.requester_principal_id)
        if requester is None:
            raise TrustedAuthorizationError()
        mode = getattr(config.settings, "identity_decision_mode", "shared")
        if mode == "shared":
            if scope.principal.principal_id == context.requester_principal_id:
                raise TrustedAuthorizationError()
            kind = "independent-approval"
        elif mode == "single-operator":
            humans = session.scalar(
                select(func.count())
                .select_from(IdentityAccount)
                .where(
                    IdentityAccount.enabled.is_(True),
                    IdentityAccount.principal_type == "human",
                )
            )
            if humans != 1:
                raise TrustedAuthorizationError()
            kind = "acknowledgement"
        else:
            raise TrustedAuthorizationError()
        result = {
            "decision_kind": kind,
            "actor_principal_id": scope.principal.principal_id,
            "authorization_version": scope.authorization_version,
        }
        return result


def authorize_automation_decision(context: DecisionContext) -> dict[str, Any]:
    """Authorize a mutation and retain the existing append-only attribution."""
    with authorized_session() as session:
        result = check_automation_decision(context, mutation=True)
        membership_repository.append_audit(
            session,
            actor_principal_id=result["actor_principal_id"],
            project_id=context.project_id,
            workspace_id=context.workspace_id,
            object_id=context.object_id,
            action=f"automation.{result['decision_kind']}",
            after=result,
        )
        return result
