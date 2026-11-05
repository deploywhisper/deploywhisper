"""Human administration for enrollment with transient one-time credential reveal."""

from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, Request
from pydantic import Field, StrictStr, field_serializer
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


class EnrollmentReveal(runners.EnrollmentIssued):
    @field_serializer("token", when_used="json")
    def serialize_token(self, value):
        # The sole uncached response reveals it; normal model repr remains masked.
        return value.get_secret_value()


class CredentialReveal(runners.CredentialIssued):
    @field_serializer("token", when_used="json")
    def serialize_token(self, value):
        return value.get_secret_value()


class RunnerEnrollmentResponse(ClosedModel):
    data: EnrollmentReveal
    meta: AutomationMeta


class RunnerCredentialResponse(ClosedModel):
    data: CredentialReveal
    meta: AutomationMeta


class RunnerRegistrationResponse(ClosedModel):
    data: runners.RunnerRegistrationView
    meta: AutomationMeta


@router.post("/enrollments", response_model=RunnerEnrollmentResponse)
def enroll(payload: runners.EnrollmentRequest):
    return _response(reveal(runners.create_enrollment(payload)))


@router.post("/{runner_id}/rotate", response_model=RunnerCredentialResponse)
def rotate(runner_id: ObjectId, payload: ReasonRequest):
    return _response(reveal(runners.rotate(runner_id, reason=payload.reason)))


@router.post("/{runner_id}/revoke", response_model=RunnerRegistrationResponse)
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
