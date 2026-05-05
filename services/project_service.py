"""Shared project/workspace service helpers."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, OperationalError

from models.database import SessionLocal, init_db
from models.repositories.projects import (
    create_project as create_project_record,
    create_workspace as create_workspace_record,
    get_default_project,
    get_project,
    get_project_by_key,
    get_workspace_by_key,
    list_projects as list_project_records,
    list_workspaces as list_workspace_records,
)
from models.repositories.settings import get_setting, upsert_setting

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
    trimmed = str(repository_name or "").strip().rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[:-4]
    if "/" not in trimmed:
        return normalize_project_key(trimmed)
    owner, leaf = trimmed.split("/", maxsplit=1)
    return normalize_project_key(f"{owner}-{leaf}")


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
                    repository_url=repository_name,
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


def set_active_project(project_id: int) -> ProjectRecord:
    project = resolve_project_reference(project_id=project_id)
    with SessionLocal() as session:
        upsert_setting(session, key=ACTIVE_PROJECT_SETTING_KEY, value=str(project.id))
    return project


def get_active_project() -> ProjectRecord | None:
    ensure_default_project()
    with SessionLocal() as session:
        setting = get_setting(session, ACTIVE_PROJECT_SETTING_KEY)
        if setting is None:
            return _serialize(get_default_project(session))
        record = get_project(session, int(setting.value))
        if record is None:
            return _serialize(get_default_project(session))
        return _serialize(record)


def has_active_project_selection() -> bool:
    ensure_default_project()
    with SessionLocal() as session:
        return get_setting(session, ACTIVE_PROJECT_SETTING_KEY) is not None


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
