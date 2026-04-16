"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.errors import ApiRoute
from api.schemas import HealthData, HealthResponse, MetaPayload
from config import settings

router = APIRouter(prefix="/api/v1", tags=["health"], route_class=ApiRoute)


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        data=HealthData(status="ok", mode="foundation"),
        meta=MetaPayload(app=settings.app_name, version=settings.app_version),
    )
