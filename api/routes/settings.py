"""Project-scoped context API routes."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from api.errors import ApiError, ApiRoute
from api.schemas import (
    ProjectData,
    TopologyContextData,
    TopologyContextRequest,
    TopologyContextResponse,
    TopologyStatusData,
    build_meta,
)
from services.project_service import (
    has_restricted_project_scope,
    require_project_permission,
    resolve_project_reference,
)
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


def _split_project_scope_header(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _authorization_context(
    project_role: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Role"),
    ] = None,
    project_keys: Annotated[
        str | None,
        Header(alias="X-DeployWhisper-Project-Keys"),
    ] = None,
) -> dict[str, object]:
    return {
        "role": project_role,
        "allowed_project_keys": _split_project_scope_header(project_keys),
    }


def _raise_authorization_error(exc: PermissionError) -> ApiError:
    raise ApiError(
        status_code=403,
        code=getattr(exc, "code", "project_permission_denied"),
        message=getattr(exc, "message", str(exc)),
    ) from exc


def _project_scope_forbidden_error() -> ApiError:
    return ApiError(
        status_code=403,
        code="project_scope_forbidden",
        message="Caller is not authorized for the requested project.",
    )


def _resolve_authorized_topology_project(
    *,
    authorization: dict[str, object],
    capability: str,
    project_id: int | None = None,
    project_key: str | None = None,
):
    if project_key is not None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    if project_id is not None and project_key is None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    try:
        project = resolve_project_reference(
            project_id=project_id, project_key=project_key
        )
    except ValueError as exc:
        if (
            project_id is not None
            and project_key is None
            and has_restricted_project_scope(
                role=authorization["role"],
                allowed_project_keys=authorization["allowed_project_keys"],
            )
        ):
            raise _project_scope_forbidden_error() from exc
        raise
    if project_key is None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            project_key=project.project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    return project


def _build_topology_context_response(
    *,
    authorization: dict[str, object],
    capability: str = "topology.read",
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> TopologyContextResponse:
    try:
        project = _resolve_authorized_topology_project(
            authorization=authorization,
            capability=capability,
            project_id=project_id,
            project_key=project_key,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        raise _project_api_error(exc) from exc
    status = get_topology_status(
        project_id=project.id,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
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
    workspace_id: int | None = Query(default=None),
    workspace_key: str | None = Query(default=None),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> TopologyContextResponse:
    return _build_topology_context_response(
        authorization=authorization,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )


@router.post("/topology", response_model=TopologyContextResponse)
def save_project_topology(
    payload: TopologyContextRequest,
    authorization: dict[str, object] = Depends(_authorization_context),
) -> TopologyContextResponse:
    try:
        project = _resolve_authorized_topology_project(
            authorization=authorization,
            capability="topology.manage",
            project_id=payload.project_id,
            project_key=payload.project_key,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        raise _project_api_error(exc) from exc

    try:
        save_topology_definition(
            json.dumps(payload.topology),
            project_id=project.id,
            workspace_id=payload.workspace_id,
            workspace_key=payload.workspace_key,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="invalid_topology_definition",
            message=str(exc),
        ) from exc

    return _build_topology_context_response(
        authorization=authorization,
        capability="topology.read",
        project_id=project.id,
        workspace_id=payload.workspace_id,
        workspace_key=payload.workspace_key,
    )
