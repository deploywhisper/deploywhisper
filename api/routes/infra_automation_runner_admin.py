"""Human administration for enrollment with transient one-time credential reveal."""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from pydantic import Field, StrictStr
from api.dependencies import require_human_principal
from api.routes.infra_automation import (
    AutomationRoute,
    ObjectId,
    ScopeId,
    PageLimit,
    PageCursor,
    _response,
)
from api.schemas import AutomationMeta
from infra_automation.contracts import ClosedModel
from services import infra_automation_runners as runners


class RunnerAdminRoute(AutomationRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            if request.url.scheme != "https":
                from api.routes.infra_automation import _error

                return _error(403)
            return await original(request)

        return handler


router = APIRouter(
    prefix="/api/v1/infra-automation/runners",
    route_class=RunnerAdminRoute,
    tags=["infra-automation"],
    dependencies=[Depends(require_human_principal)],
)


class ReasonRequest(ClosedModel):
    reason: Annotated[StrictStr, Field(min_length=1, max_length=500)]


def reveal(value):
    data = value.model_dump(mode="json")
    data["token"] = value.token.get_secret_value()
    return data


@router.post("/enrollments")
def enroll(payload: runners.EnrollmentRequest):
    return _response(reveal(runners.create_enrollment(payload)))


@router.post("/{runner_id}/rotate")
def rotate(runner_id: ObjectId, payload: ReasonRequest):
    return _response(reveal(runners.rotate(runner_id, reason=payload.reason)))


@router.post("/{runner_id}/revoke")
def revoke(runner_id: ObjectId, payload: ReasonRequest):
    return _response(runners.revoke(runner_id, reason=payload.reason))


class RunnerHealthResponse(ClosedModel):
    data: runners.RunnerHealthPage
    meta: AutomationMeta


@router.get("", response_model=RunnerHealthResponse)
def health(
    project_id: ScopeId,
    workspace_id: ScopeId,
    limit: PageLimit = 25,
    cursor: PageCursor = None,
):
    return _response(
        runners.health(
            project_id, workspace_id=workspace_id, limit=limit, cursor=cursor
        )
    )
