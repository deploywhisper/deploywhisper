"""Read-only dashboard statistics API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from api.errors import ApiError, ApiRoute
from api.schemas import (
    StatsSummaryData,
    StatsSummaryResponse,
    VerdictDistributionData,
    VerdictDistributionResponse,
    build_meta,
)
from services.project_service import ProjectResolutionError
from services.stats_service import fetch_stats_summary, fetch_verdict_distribution

router = APIRouter(prefix="/api/v1/stats", tags=["stats"], route_class=ApiRoute)


def _project_api_error(exc: ValueError) -> ApiError:
    code = getattr(exc, "code", "invalid_project_request")
    status_code = 404 if code in {"project_not_found", "workspace_not_found"} else 400
    return ApiError(
        status_code=status_code,
        code=code,
        message=str(exc),
    )


@router.get("/summary", response_model=StatsSummaryResponse)
def get_stats_summary(
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> StatsSummaryResponse:
    try:
        summary = fetch_stats_summary(
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    except (ProjectResolutionError, ValueError) as exc:
        raise _project_api_error(exc) from exc
    return StatsSummaryResponse(
        data=StatsSummaryData.model_validate(summary),
        meta=build_meta(),
    )


@router.get("/verdict-distribution", response_model=VerdictDistributionResponse)
def get_verdict_distribution(
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> VerdictDistributionResponse:
    try:
        distribution = fetch_verdict_distribution(
            days=days,
            project_id=project_id,
            project_key=project_key,
            workspace_id=workspace_id,
            workspace_key=workspace_key,
        )
    except (ProjectResolutionError, ValueError) as exc:
        raise _project_api_error(exc) from exc
    return VerdictDistributionResponse(
        data=VerdictDistributionData.model_validate(distribution),
        meta=build_meta(),
    )
