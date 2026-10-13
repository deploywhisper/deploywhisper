"""Project/workspace API routes."""

from __future__ import annotations

from typing import Annotated
import json
import secrets

from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from api.errors import ApiError, ApiRoute
from api.schemas import (
    ProjectCreateRequest,
    ProjectData,
    ProjectListResponse,
    ProjectRoleData,
    ProjectRoleListResponse,
    ProjectResponse,
    WorkspaceCreateRequest,
    WorkspaceData,
    WorkspaceListResponse,
    WorkspaceResponse,
    build_meta,
    ProjectMembershipRequest,
    ProjectMembershipResponse,
    ProjectMembershipListResponse,
)
from services.project_service import (
    ProjectResolutionError,
    create_project,
    create_workspace,
    filter_projects_by_authorization,
    list_project_role_definitions,
    list_projects,
    list_workspaces,
    require_project_permission,
    authorized_session,
    bootstrap_project_membership,
    assign_project_membership,
    revoke_project_membership,
    list_project_memberships,
    legacy_request_has_identity,
    TrustedAuthorizationError,
)
from models.tables import Project

router = APIRouter(prefix="/api/v1/projects", tags=["projects"], route_class=ApiRoute)


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
    if legacy_request_has_identity():
        return {"role": None, "allowed_project_keys": None}
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
def get_projects(
    authorization: dict[str, object] = Depends(_authorization_context),
) -> ProjectListResponse:
    try:
        projects = filter_projects_by_authorization(
            list_projects(),
            role=authorization["role"],
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    return ProjectListResponse(
        data=[ProjectData(**project.model_dump()) for project in projects],
        meta=build_meta(count=len(projects)),
    )


@router.get("/roles", response_model=ProjectRoleListResponse)
def get_project_roles() -> ProjectRoleListResponse:
    roles = list_project_role_definitions()
    return ProjectRoleListResponse(
        data=[ProjectRoleData(**role.model_dump()) for role in roles],
        meta=build_meta(count=len(roles)),
    )


@router.post("", response_model=ProjectResponse)
def create_project_route(
    payload: ProjectCreateRequest,
    authorization: dict[str, object] = Depends(_authorization_context),
) -> ProjectResponse:
    try:
        require_project_permission(
            role=authorization["role"],
            capability="project.manage",
            project_key=payload.project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        created = create_project(
            project_key=payload.project_key,
            display_name=payload.display_name,
            description=payload.description,
            repository_url=payload.repository_url,
            default_branch=payload.default_branch,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
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
def get_workspaces(
    project_key: str,
    authorization: dict[str, object] = Depends(_authorization_context),
) -> WorkspaceListResponse:
    try:
        require_project_permission(
            role=authorization["role"],
            capability="workspace.read",
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        workspaces = list_workspaces(project_key=project_key)
    except PermissionError as exc:
        _raise_authorization_error(exc)
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
    authorization: dict[str, object] = Depends(_authorization_context),
) -> WorkspaceResponse:
    try:
        require_project_permission(
            role=authorization["role"],
            capability="workspace.manage",
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        created = create_workspace(
            project_key=project_key,
            workspace_key=payload.workspace_key,
            display_name=payload.display_name,
            description=payload.description,
            environment=payload.environment,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except (ProjectResolutionError, ValueError) as exc:
        raise _project_api_error(exc, default_code="invalid_workspace_request") from exc
    return WorkspaceResponse(
        data=WorkspaceData(**created.model_dump()),
        meta=build_meta(id=created.id),
    )


def _membership_project_id(session, project_key: str) -> int:
    project_id = session.scalar(
        select(Project.id).where(Project.project_key == project_key)
    )
    if project_id is None:
        raise TrustedAuthorizationError()
    return project_id


def _membership_meta() -> dict:
    return build_meta(correlation_id=secrets.token_hex(16))


@router.post(
    "/{project_key}/memberships/bootstrap", response_model=ProjectMembershipResponse
)
def bootstrap_membership(project_key: str):
    with authorized_session() as session:
        result = bootstrap_project_membership(
            _membership_project_id(session, project_key)
        )
        return ProjectMembershipResponse(data=result, meta=_membership_meta())


@router.get("/{project_key}/memberships", response_model=ProjectMembershipListResponse)
def get_memberships(project_key: str):
    with authorized_session() as session:
        members = list_project_memberships(_membership_project_id(session, project_key))
        return ProjectMembershipListResponse(data=members, meta=_membership_meta())


async def _read_membership_request(request: Request) -> ProjectMembershipRequest:
    def invalid():
        return ApiError(
            400, "invalid_membership_request", "Invalid membership request."
        )

    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise invalid()
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > 4096:
            raise invalid()
        content.extend(chunk)
    try:

        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError
                value[key] = item
            return value

        return ProjectMembershipRequest.model_validate(
            json.loads(content.decode("utf-8"), object_pairs_hook=unique_object)
        )
    except (ValueError, TypeError, UnicodeError, RecursionError, ValidationError):
        raise invalid() from None


def _assign_membership(
    project_key: str, principal_id: str, payload: ProjectMembershipRequest
):
    with authorized_session() as session:
        result = assign_project_membership(
            _membership_project_id(session, project_key),
            principal_id,
            payload.role,
            payload.workspace_id,
        )
        return ProjectMembershipResponse(data=result, meta=_membership_meta())


@router.put(
    "/{project_key}/memberships/{principal_id}",
    response_model=ProjectMembershipResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": ProjectMembershipRequest.model_json_schema()
                }
            },
        }
    },
)
async def put_membership(project_key: str, principal_id: str, request: Request):
    payload = await _read_membership_request(request)
    return await run_in_threadpool(
        _assign_membership, project_key, principal_id, payload
    )


@router.delete(
    "/{project_key}/memberships/{principal_id}",
    response_model=ProjectMembershipResponse,
)
def delete_membership(project_key: str, principal_id: str):
    with authorized_session() as session:
        result = revoke_project_membership(
            _membership_project_id(session, project_key), principal_id
        )
        return ProjectMembershipResponse(data=result, meta=_membership_meta())
