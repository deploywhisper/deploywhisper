"""Deployment outcome API routes."""

from __future__ import annotations

import hmac
import os

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
) -> DeploymentOutcomeResponse:
    try:
        recorded = record_deployment_outcome(
            analysis_id=payload.analysis_id,
            outcome=payload.outcome,
            deployed_at=payload.deployed_at,
            linked_incident_id=payload.linked_incident_id,
            environment=payload.environment,
            summary=payload.summary,
            project_id=payload.project_id,
            project_key=payload.project_key,
            source_interface="api",
        )
    except ValueError as exc:
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
    limit: int = Query(default=100, ge=1, le=200),
) -> DeploymentOutcomeListResponse:
    try:
        outcomes = list_deployment_outcomes(
            analysis_id=analysis_id,
            outcome=outcome,
            project_id=project_id,
            project_key=project_key,
            limit=limit,
        )
    except ValueError as exc:
        raise _deployment_api_error(exc) from exc
    return DeploymentOutcomeListResponse(
        data=[DeploymentOutcomeData(**item) for item in outcomes],
        meta=build_meta(count=len(outcomes)),
    )
