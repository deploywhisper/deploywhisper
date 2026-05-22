"""Deployment outcome API routes."""

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from api.errors import ApiError, ApiRoute
from api.schemas import (
    DeploymentOutcomeCreateRequest,
    DeploymentOutcomeData,
    DeploymentOutcomeListResponse,
    DeploymentOutcomeResponse,
    ErrorResponse,
    build_meta,
)
from config import settings
from services.deployment_outcome_service import (
    list_deployment_outcomes,
    record_deployment_outcome,
)
from services.project_service import (
    has_restricted_project_scope,
    require_project_permission,
    resolve_project_reference,
)
from services.report_service import fetch_analysis_report

router = APIRouter(
    prefix="/api/v1/deployments",
    tags=["deployments"],
    route_class=ApiRoute,
)


def require_deployment_outcome_token(
    outcome_token: str | None = Header(
        default=None,
        alias="X-DeployWhisper-Outcome-Token",
    ),
) -> None:
    configured_token = (
        os.getenv("DEPLOYWHISPER_OUTCOME_TOKEN")
        or os.getenv("APP_DEPLOYMENT_OUTCOME_TOKEN")
        or settings.deployment_outcome_token
        or ""
    ).strip()
    if not configured_token:
        raise ApiError(
            status_code=405,
            code="deployment_outcome_ingest_disabled",
            message=(
                "Deployment outcome ingestion is disabled. Set "
                "DEPLOYWHISPER_OUTCOME_TOKEN to enable it."
            ),
        )
    if not outcome_token or not hmac.compare_digest(outcome_token, configured_token):
        raise ApiError(
            status_code=403,
            code="deployment_outcome_ingest_forbidden",
            message="Deployment outcome ingestion requires a valid management token.",
        )


def _deployment_api_error(exc: ValueError) -> ApiError:
    code = getattr(exc, "code", "invalid_deployment_request")
    status_code = (
        404
        if code in {"analysis_not_found", "project_not_found", "incident_not_found"}
        else 400
    )
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


def _should_mask_project_reference_error(
    *,
    authorization: dict[str, object],
    project_id: int | None,
    exc: ValueError,
) -> bool:
    return (
        project_id is not None
        and getattr(exc, "code", None)
        in {"project_not_found", "conflicting_project_reference"}
        and has_restricted_project_scope(
            role=authorization["role"],
            allowed_project_keys=authorization["allowed_project_keys"],
        )
    )


def _reject_unscoped_workspace_id(
    *,
    analysis_id: int | None,
    project_id: int | None,
    project_key: str | None,
    workspace_id: int | None,
) -> None:
    if (
        workspace_id is None
        or analysis_id is not None
        or project_id is not None
        or project_key is not None
    ):
        return
    raise ApiError(
        status_code=400,
        code="missing_project_scope",
        message="Project scope is required when resolving workspace_id.",
    )


def _require_deployment_project_permission(
    *,
    authorization: dict[str, object],
    capability: str,
    project_id: int | None = None,
    project_key: str | None = None,
) -> None:
    if project_key is not None:
        require_project_permission(
            role=authorization["role"],
            capability=capability,
            project_key=project_key,
            allowed_project_keys=authorization["allowed_project_keys"],
        )
        if project_id is not None:
            try:
                resolve_project_reference(
                    project_id=project_id, project_key=project_key
                )
            except ValueError as exc:
                if _should_mask_project_reference_error(
                    authorization=authorization,
                    project_id=project_id,
                    exc=exc,
                ):
                    raise _project_scope_forbidden_error() from exc
                raise
        return
    require_project_permission(
        role=authorization["role"],
        capability=capability,
        allowed_project_keys=authorization["allowed_project_keys"],
    )
    try:
        project = resolve_project_reference(project_id=project_id)
    except ValueError as exc:
        if _should_mask_project_reference_error(
            authorization=authorization,
            project_id=project_id,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise
    require_project_permission(
        role=authorization["role"],
        capability=capability,
        project_key=project.project_key,
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _require_deployment_analysis_permission(
    *,
    authorization: dict[str, object],
    capability: str,
    analysis_id: int,
) -> None:
    require_project_permission(
        role=authorization["role"],
        capability=capability,
        allowed_project_keys=authorization["allowed_project_keys"],
    )
    report = fetch_analysis_report(analysis_id)
    if report is None:
        if _is_restricted_project_actor(authorization):
            raise _project_scope_forbidden_error()
        raise ApiError(
            status_code=404,
            code="analysis_not_found",
            message="Analysis report not found.",
        )
    project = report.get("project") or {}
    require_project_permission(
        role=authorization["role"],
        capability=capability,
        project_key=project.get("project_key"),
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _is_restricted_project_actor(authorization: dict[str, object]) -> bool:
    return has_restricted_project_scope(
        role=authorization["role"],
        allowed_project_keys=authorization["allowed_project_keys"],
    )


def _should_mask_scope_reference_error(
    *,
    authorization: dict[str, object],
    exc: ValueError,
) -> bool:
    return _is_restricted_project_actor(authorization) and getattr(
        exc, "code", None
    ) in {
        "analysis_not_found",
        "conflicting_project_reference",
        "project_not_found",
        "workspace_not_found",
        "conflicting_workspace_reference",
    }


@router.post(
    "/outcomes",
    response_model=DeploymentOutcomeResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_deployment_outcome_route(
    payload: DeploymentOutcomeCreateRequest,
    _: None = Depends(require_deployment_outcome_token),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> DeploymentOutcomeResponse:
    try:
        if payload.analysis_id is not None:
            _require_deployment_analysis_permission(
                authorization=authorization,
                capability="outcome.manage",
                analysis_id=payload.analysis_id,
            )
        elif payload.project_key is not None or payload.project_id is not None:
            _require_deployment_project_permission(
                authorization=authorization,
                capability="outcome.manage",
                project_id=payload.project_id,
                project_key=payload.project_key,
            )
        recorded = record_deployment_outcome(
            analysis_id=payload.analysis_id,
            outcome=payload.outcome,
            deployed_at=payload.deployed_at,
            linked_incident_id=payload.linked_incident_id,
            environment=payload.environment,
            summary=payload.summary,
            notes=payload.notes,
            project_id=payload.project_id,
            project_key=payload.project_key,
            workspace_id=payload.workspace_id,
            workspace_key=payload.workspace_key,
            source_interface="api",
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        if _should_mask_project_reference_error(
            authorization=authorization,
            project_id=payload.project_id,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise _deployment_api_error(exc) from exc
    return DeploymentOutcomeResponse(
        data=DeploymentOutcomeData(**recorded),
        meta=build_meta(id=recorded["id"]),
    )


@router.get(
    "/outcomes",
    response_model=DeploymentOutcomeListResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def get_deployment_outcomes(
    analysis_id: int | None = Query(default=None),
    outcome: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    project_key: str | None = Query(default=None),
    workspace_id: int | None = Query(default=None),
    workspace_key: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    authorization: dict[str, object] = Depends(_authorization_context),
) -> DeploymentOutcomeListResponse:
    try:
        _reject_unscoped_workspace_id(
            analysis_id=analysis_id,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
        )
        if analysis_id is not None:
            _require_deployment_analysis_permission(
                authorization=authorization,
                capability="outcome.read",
                analysis_id=analysis_id,
            )
        elif project_key is not None or project_id is not None:
            _require_deployment_project_permission(
                authorization=authorization,
                capability="outcome.read",
                project_id=project_id,
                project_key=project_key,
            )
        else:
            _require_deployment_project_permission(
                authorization=authorization,
                capability="outcome.read",
            )
        outcomes = list_deployment_outcomes(
            analysis_id=analysis_id,
            outcome=outcome,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
            limit=limit,
        )
    except PermissionError as exc:
        _raise_authorization_error(exc)
    except ValueError as exc:
        if _should_mask_scope_reference_error(
            authorization=authorization,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        if _should_mask_project_reference_error(
            authorization=authorization,
            project_id=project_id,
            exc=exc,
        ):
            raise _project_scope_forbidden_error() from exc
        raise _deployment_api_error(exc) from exc
    return DeploymentOutcomeListResponse(
        data=[DeploymentOutcomeData(**item) for item in outcomes],
        meta=build_meta(count=len(outcomes)),
    )
