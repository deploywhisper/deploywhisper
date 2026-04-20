"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from api.errors import ApiRoute
from api.schemas import HealthData, HealthResponse, LlmHealthData, MetaPayload
from config import settings
from services.settings_service import get_provider_health_snapshot

router = APIRouter(prefix="/api/v1", tags=["health"], route_class=ApiRoute)


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    readiness = get_provider_health_snapshot()
    return HealthResponse(
        data=HealthData(
            status="ok",
            mode="foundation",
            core_status="ok",
            llm=LlmHealthData(
                status="ok" if readiness.ready else "degraded",
                ready=readiness.ready,
                provider=readiness.provider,
                model=readiness.model,
                local_mode=readiness.local_mode,
                requires_api_key=readiness.requires_api_key,
                has_api_key=readiness.has_api_key,
                message=readiness.message,
                source=readiness.source,
            ),
        ),
        meta=MetaPayload(app=settings.app_name, version=settings.app_version),
    )
