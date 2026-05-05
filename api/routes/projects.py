"""Project/workspace API routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.errors import ApiError, ApiRoute
from api.schemas import (
    ProjectCreateRequest,
    ProjectData,
    ProjectListResponse,
    ProjectResponse,
    WorkspaceCreateRequest,
    WorkspaceData,
    WorkspaceListResponse,
    WorkspaceResponse,
    build_meta,
)
from services.project_service import (
    ProjectResolutionError,
    create_project,
    create_workspace,
    list_projects,
    list_workspaces,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"], route_class=ApiRoute)


def _project_api_error(
    exc: ValueError,
    *,
    default_code: str = "invalid_project_request",
) -> ApiError:
    code = getattr(exc, "code", default_code)
    status_code = 404 if code == "project_not_found" else 400
    return ApiError(
        status_code=status_code,
        code=code,
        message=str(exc),
    )


@router.get("", response_model=ProjectListResponse)
def get_projects() -> ProjectListResponse:
    projects = list_projects()
    return ProjectListResponse(
        data=[ProjectData(**project.model_dump()) for project in projects],
        meta=build_meta(count=len(projects)),
    )


@router.post("", response_model=ProjectResponse)
def create_project_route(payload: ProjectCreateRequest) -> ProjectResponse:
    try:
        created = create_project(
            project_key=payload.project_key,
            display_name=payload.display_name,
            description=payload.description,
            repository_url=payload.repository_url,
            default_branch=payload.default_branch,
        )
    except (ProjectResolutionError, ValueError) as exc:
        raise ApiError(
            status_code=400,
            code=getattr(exc, "code", "invalid_project_request"),
            message=str(exc),
        ) from exc
    return ProjectResponse(
        data=ProjectData(**created.model_dump()),
        meta=build_meta(id=created.id),
    )


@router.get("/{project_key}/workspaces", response_model=WorkspaceListResponse)
def get_workspaces(project_key: str) -> WorkspaceListResponse:
    try:
        workspaces = list_workspaces(project_key=project_key)
    except (ProjectResolutionError, ValueError) as exc:
        raise _project_api_error(exc, default_code="invalid_workspace_request") from exc
    return WorkspaceListResponse(
        data=[WorkspaceData(**workspace.model_dump()) for workspace in workspaces],
        meta=build_meta(count=len(workspaces)),
    )


@router.post("/{project_key}/workspaces", response_model=WorkspaceResponse)
def create_workspace_route(
    project_key: str,
    payload: WorkspaceCreateRequest,
) -> WorkspaceResponse:
    try:
        created = create_workspace(
            project_key=project_key,
            workspace_key=payload.workspace_key,
            display_name=payload.display_name,
            description=payload.description,
            environment=payload.environment,
        )
    except (ProjectResolutionError, ValueError) as exc:
        raise _project_api_error(exc, default_code="invalid_workspace_request") from exc
    return WorkspaceResponse(
        data=WorkspaceData(**created.model_dump()),
        meta=build_meta(id=created.id),
    )
