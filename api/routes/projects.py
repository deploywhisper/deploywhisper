"""Project/workspace API routes."""

from __future__ import annotations

from fastapi import APIRouter

from api.errors import ApiError, ApiRoute
from api.schemas import (
    ProjectCreateRequest,
    ProjectData,
    ProjectListResponse,
    ProjectResponse,
    build_meta,
)
from services.project_service import (
    ProjectResolutionError,
    create_project,
    list_projects,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"], route_class=ApiRoute)


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
