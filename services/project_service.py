"""Shared project/workspace service helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError

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
    list_workspaces as list_workspace_records,
)
from models.repositories.settings import delete_setting, get_setting, upsert_setting

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

    if capability not in PROJECT_ROLE_CAPABILITIES[normalized_role]:
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
        with SessionLocal() as session:
            default_project = get_default_project(session)
            if default_project is None:
                default_project = create_project_record(
                    session,
                    project_key=DEFAULT_PROJECT_KEY,
                    display_name=DEFAULT_PROJECT_NAME,
                    description="Legacy and unassigned analyses.",
                    is_default=True,
                )
            return _serialize(default_project)
    except OperationalError as exc:
        if "no such table: projects" not in str(exc).lower():
            raise
        init_db()
        with SessionLocal() as session:
            default_project = get_default_project(session)
            if default_project is None:
                default_project = create_project_record(
                    session,
                    project_key=DEFAULT_PROJECT_KEY,
                    display_name=DEFAULT_PROJECT_NAME,
                    description="Legacy and unassigned analyses.",
                    is_default=True,
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
    with SessionLocal() as session:
        existing = get_project_by_key(session, normalized_key)
        if existing is not None:
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
    with SessionLocal() as session:
        project = get_project_by_key(session, normalized_project_key)
        if project is None:
            raise ProjectResolutionError(
                "project_not_found",
                f"Unknown project reference: project_key={normalized_project_key}.",
            )
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
    with SessionLocal() as session:
        return [_serialize(record) for record in list_project_records(session)]


def list_workspaces(*, project_key: str | None = None) -> list[WorkspaceRecord]:
    if project_key is None:
        normalized_project_key = ensure_default_project().project_key
    else:
        normalized_project_key = normalize_project_key(project_key)
    with SessionLocal() as session:
        project = get_project_by_key(session, normalized_project_key)
        if project is None:
            raise ProjectResolutionError(
                "project_not_found",
                f"Unknown project reference: project_key={normalized_project_key}.",
            )
        return [
            _serialize_workspace(record)
            for record in list_workspace_records(session, project_id=project.id)
        ]


def get_project_by_id(project_id: int) -> ProjectRecord | None:
    with SessionLocal() as session:
        record = get_project(session, project_id)
        return _serialize(record) if record is not None else None


def get_project_by_project_key(project_key: str) -> ProjectRecord | None:
    with SessionLocal() as session:
        record = get_project_by_key(session, normalize_project_key(project_key))
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
    with SessionLocal() as session:
        record_by_id = (
            get_project(session, project_id) if project_id is not None else None
        )
        record_by_key = (
            get_project_by_key(session, normalized_key)
            if normalized_key is not None
            else None
        )
        if project_id is not None and record_by_id is None:
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
            if normalized_key is not None:
                record = create_project_record(
                    session,
                    project_key=normalized_key,
                    display_name=_display_name_from_key(normalized_key),
                )
            elif derived_key is not None:
                record = create_project_record(
                    session,
                    project_key=derived_key,
                    display_name=display_name_from_repository(
                        repository_name or derived_key
                    ),
                    repository_url=_repository_storage_value(repository_name),
                )
        elif record is None and (project_id is not None or normalized_key is not None):
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
    with SessionLocal() as session:
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
        if workspace_id is not None and record_by_id is None:
            raise ProjectResolutionError(
                "workspace_not_found",
                f"Unknown workspace reference: workspace_id={workspace_id}.",
            )
        if (
            normalized_workspace_key is not None
            and resolved_project is not None
            and record_by_key is None
        ):
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
    project = resolve_project_reference(project_id=project_id)
    with SessionLocal() as session:
        upsert_setting(session, key=ACTIVE_PROJECT_SETTING_KEY, value=str(project.id))
    return project


def clear_active_project_selection() -> None:
    """Clear the saved active-project selection for UI surfaces."""
    with SessionLocal() as session:
        delete_setting(session, ACTIVE_PROJECT_SETTING_KEY)


def get_active_project() -> ProjectRecord | None:
    ensure_default_project()
    with SessionLocal() as session:
        setting = get_setting(session, ACTIVE_PROJECT_SETTING_KEY)
        if setting is None:
            return _serialize(get_default_project(session))
        try:
            project_id = int(setting.value)
        except (TypeError, ValueError):
            project_id = 0
        record = get_project(session, project_id)
        if record is None:
            return _serialize(get_default_project(session))
        return _serialize(record)


def has_active_project_selection() -> bool:
    ensure_default_project()
    with SessionLocal() as session:
        setting = get_setting(session, ACTIVE_PROJECT_SETTING_KEY)
        if setting is None:
            return False
        try:
            project_id = int(setting.value)
        except (TypeError, ValueError):
            return False
        return get_project(session, project_id) is not None


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
