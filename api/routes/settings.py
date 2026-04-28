"""Project-scoped context API routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query

from api.errors import ApiError, ApiRoute
from api.schemas import (
    ProjectData,
    TopologyContextData,
    TopologyContextRequest,
    TopologyContextResponse,
    TopologyStatusData,
    build_meta,
)
from services.project_service import resolve_project_reference
from services.topology_service import get_topology_status, save_topology_definition

router = APIRouter(prefix="/api/v1/context", tags=["context"], route_class=ApiRoute)


def _project_api_error(exc: ValueError) -> ApiError:
    code = getattr(exc, "code", "invalid_project_request")
    status_code = 404 if code == "project_not_found" else 400
    return ApiError(
        status_code=status_code,
        code=code,
        message=str(exc),
    )


def _build_topology_context_response(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
) -> TopologyContextResponse:
    try:
        project = resolve_project_reference(
            project_id=project_id, project_key=project_key
        )
    except ValueError as exc:
        raise _project_api_error(exc) from exc
    status = get_topology_status(project_id=project.id)
    return TopologyContextResponse(
        data=TopologyContextData(
            project=ProjectData(**project.model_dump()),
            topology=TopologyStatusData(**status.model_dump(exclude={"payload"})),
        ),
        meta=build_meta(),
    )


@router.get("/topology", response_model=TopologyContextResponse)
def get_project_topology(
    project_id: int | None = Query(default=None),
    project_key: str | None = Query(default=None),
) -> TopologyContextResponse:
    return _build_topology_context_response(
        project_id=project_id,
        project_key=project_key,
    )


@router.post("/topology", response_model=TopologyContextResponse)
def save_project_topology(payload: TopologyContextRequest) -> TopologyContextResponse:
    try:
        project = resolve_project_reference(
            project_id=payload.project_id,
            project_key=payload.project_key,
        )
    except ValueError as exc:
        raise _project_api_error(exc) from exc

    try:
        save_topology_definition(
            json.dumps(payload.topology),
            project_id=project.id,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="invalid_topology_definition",
            message=str(exc),
        ) from exc

    return _build_topology_context_response(project_id=project.id)
