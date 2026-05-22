"""Lightweight project authorization helpers for UI surfaces."""

from __future__ import annotations

import os

from services.project_service import (
    ProjectRecord,
    ProjectAuthorizationError,
    ProjectAuthorizationResult,
    clear_active_project_selection,
    create_project,
    authorize_project_action,
    filter_projects_by_authorization,
    get_active_project,
    has_active_project_selection,
    list_projects,
    require_project_permission,
    set_active_project,
)


def _split_env_project_keys(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def ui_project_authorization_from_env() -> dict[str, object]:
    """Resolve the lightweight UI actor contract from the local process env."""
    return {
        "role": os.environ.get("DEPLOYWHISPER_PROJECT_ROLE"),
        "allowed_project_keys": _split_env_project_keys(
            os.environ.get("DEPLOYWHISPER_PROJECT_KEYS")
        ),
    }


def list_authorized_ui_projects() -> list[ProjectRecord]:
    authorization = ui_project_authorization_from_env()
    return filter_projects_by_authorization(
        list_projects(),
        role=authorization["role"],
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def load_authorized_ui_projects() -> tuple[list[ProjectRecord], str | None]:
    try:
        return list_authorized_ui_projects(), None
    except ProjectAuthorizationError as exc:
        return [], exc.message


def is_ui_project_visible(
    project: ProjectRecord | None,
    projects: list[ProjectRecord],
) -> bool:
    if project is None:
        return False
    visible_ids = {int(candidate.id) for candidate in projects}
    return int(project.id) in visible_ids


def clear_unauthorized_active_project(
    project: ProjectRecord | None,
    projects: list[ProjectRecord],
    *,
    authorization_error: str | None = None,
) -> bool:
    if authorization_error is not None:
        return False
    if project is None or is_ui_project_visible(project, projects):
        return False
    clear_active_project_selection()
    return True


def resolve_authorized_active_project_selection(
    *,
    has_saved_selection: bool,
    active_project: ProjectRecord | None,
    projects: list[ProjectRecord],
    authorization_error: str | None = None,
) -> tuple[bool, ProjectRecord | None]:
    """Resolve effective UI project selection without destructive auth-error clears."""
    if active_project is None:
        return False, None
    if authorization_error is not None:
        return False, None
    if not is_ui_project_visible(active_project, projects):
        if has_saved_selection:
            clear_active_project_selection()
        return False, None
    return has_saved_selection, active_project


def resolve_authorized_ui_active_project() -> tuple[
    bool,
    ProjectRecord | None,
    str | None,
]:
    """Return the effective active project allowed for current UI actor settings."""
    projects, authorization_error = load_authorized_ui_projects()
    has_saved_selection = has_active_project_selection()
    active_project = get_active_project()
    has_saved_selection, active_project = resolve_authorized_active_project_selection(
        has_saved_selection=has_saved_selection,
        active_project=active_project,
        projects=projects,
        authorization_error=authorization_error,
    )
    return has_saved_selection, active_project, authorization_error


def set_authorized_ui_project(
    project_id: int,
    projects: list[ProjectRecord],
) -> ProjectRecord:
    visible = {int(project.id): project for project in projects}
    selected = visible.get(int(project_id))
    if selected is None:
        raise PermissionError("Caller is not authorized for the requested project.")
    try:
        return set_active_project(selected.id)
    except ValueError as exc:
        clear_active_project_selection()
        raise PermissionError("Selected project is no longer available.") from exc


def create_authorized_ui_project(
    *,
    project_key: str,
    display_name: str,
    description: str | None = None,
    repository_url: str | None = None,
    default_branch: str | None = None,
) -> ProjectRecord:
    authorization = ui_project_authorization_from_env()
    require_project_permission(
        role=authorization["role"],
        capability="project.manage",
        project_key=project_key,
        allowed_project_keys=authorization["allowed_project_keys"],
    )
    return create_project(
        project_key=project_key,
        display_name=display_name,
        description=description,
        repository_url=repository_url,
        default_branch=default_branch,
    )


def authorize_ui_project_capability(
    *,
    capability: str,
    project_key: str | None = None,
) -> ProjectAuthorizationResult:
    """Check a UI actor capability using the local process actor contract."""
    authorization = ui_project_authorization_from_env()
    return authorize_project_action(
        role=authorization["role"],
        capability=capability,
        project_key=project_key,
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def require_ui_project_capability(
    *,
    capability: str,
    project_key: str | None = None,
) -> ProjectAuthorizationResult:
    """Require a UI actor capability using the local process actor contract."""
    authorization = ui_project_authorization_from_env()
    return require_project_permission(
        role=authorization["role"],
        capability=capability,
        project_key=project_key,
        allowed_project_keys=authorization["allowed_project_keys"],
    )
