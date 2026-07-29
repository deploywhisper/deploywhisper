"""Bounded agent-callable analysis and report routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from api.errors import ApiError, ApiRoute
from api.routes.analyses import (
    _authorization_context,
    create_analysis,
)
from api.schemas import ErrorResponse
from services.agent_interface_service import (
    AgentInterfaceResponse,
    build_agent_analysis_data,
    build_agent_interface_response,
    build_agent_report_data,
)
from services.project_service import (
    has_restricted_project_scope,
    require_project_permission,
)
from services.report_service import (
    fetch_analysis_report,
    fetch_analysis_report_for_project_keys,
)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"], route_class=ApiRoute)


def _agent_scope_forbidden_error() -> ApiError:
    return ApiError(
        status_code=403,
        code="agent_scope_forbidden",
        message="Caller is not authorized for the requested agent resource.",
    )


def _raise_bounded_agent_error(
    exc: ApiError,
    *,
    authorization: dict[str, object],
) -> None:
    restricted_scope = has_restricted_project_scope(
        role=authorization["role"],
        allowed_project_keys=authorization["allowed_project_keys"],
    )
    if exc.status_code == 403 or (exc.status_code == 404 and restricted_scope):
        raise _agent_scope_forbidden_error() from exc
    raise exc


@router.post(
    "/analyses",
    response_model=AgentInterfaceResponse,
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_agent_analysis(
    files: list[UploadFile] | None = File(
        default=None,
        description="Supported deployment artifacts to analyze.",
    ),
    project_id: int | None = Form(default=None),
    project_key: str | None = Form(default=None),
    workspace_id: int | None = Form(default=None),
    workspace_key: str | None = Form(default=None),
    artifact_paths: list[str] | None = Form(default=None),
    trigger_type: str | None = Header(
        default=None,
        alias="X-DeployWhisper-Trigger-Type",
    ),
    trigger_id: str | None = Header(
        default=None,
        alias="X-DeployWhisper-Trigger-Id",
    ),
    actor: str | None = Header(default=None, alias="X-DeployWhisper-Actor"),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> AgentInterfaceResponse:
    """Run the canonical analysis path and return the bounded agent contract."""
    try:
        analysis_response = await create_analysis(
            files=files,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
            artifact_paths=artifact_paths,
            trigger_type=trigger_type or "agent_request",
            trigger_id=trigger_id,
            actor=actor or "agent_client",
            authorization=authorization,
        )
    except ApiError as exc:
        _raise_bounded_agent_error(exc, authorization=authorization)
    return build_agent_interface_response(
        build_agent_analysis_data(analysis_response.data),
        operation="analysis.submit",
    )


@router.get(
    "/reports/{report_id}",
    response_model=AgentInterfaceResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_agent_report(
    report_id: int,
    authorization: dict[str, object] = Depends(_authorization_context),
) -> AgentInterfaceResponse:
    """Return one scoped persisted report through the bounded agent contract."""
    try:
        require_project_permission(
            role=authorization["role"],
            capability="report.read",
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    except PermissionError as exc:
        raise _agent_scope_forbidden_error() from exc

    restricted_scope = has_restricted_project_scope(
        role=authorization["role"],
        allowed_project_keys=authorization["allowed_project_keys"],
    )
    if restricted_scope:
        report = fetch_analysis_report_for_project_keys(
            report_id,
            project_keys=list(authorization["allowed_project_keys"] or []),
        )
    else:
        report = fetch_analysis_report(report_id)
    if report is None:
        if restricted_scope:
            raise _agent_scope_forbidden_error()
        raise ApiError(
            status_code=404,
            code="agent_report_not_found",
            message="Agent report not found.",
        )

    try:
        require_project_permission(
            role=authorization["role"],
            capability="report.read",
            project_key=str((report.get("project") or {}).get("project_key") or ""),
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    except (PermissionError, ValueError) as exc:
        raise _agent_scope_forbidden_error() from exc

    try:
        data = build_agent_report_data(report)
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            status_code=500,
            code="agent_report_contract_invalid",
            message="Agent report contract validation failed.",
        ) from exc
    return build_agent_interface_response(data, operation="report.read")
