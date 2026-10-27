"""Bounded human-only adapters for scoped workflow lifecycle operations."""

from __future__ import annotations

import json
import math
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from api.dependencies import bind_project_credentials, require_human_principal
from api.errors import ApiError, ApiRoute, build_error_response
from api.schemas import (
    build_meta,
    AutomationWorkflowResponse,
    AutomationRevisionResponse,
    AutomationValidationResponse,
    AutomationPolicyResponse,
    AutomationWorkflowListResponse,
    AutomationRevisionListResponse,
    AutomationAuditResponse,
    AutomationErrorResponse,
    AutomationRunResponse,
    AutomationRunListResponse,
    AutomationStepListResponse,
    AutomationLogListResponse,
    AutomationPreflightLinksResponse,
)
from infra_automation.state import CancelRunRequest, RunRequest
from infra_automation.preflight_contracts import PreflightRequest
from infra_automation.contracts import SAFE_INTEGER
from infra_automation.lifecycle import (
    AdvanceEpochRequest,
    ArchiveWorkflowRequest,
    CreateWorkflowRequest,
    LifecycleError,
    PublishWorkflowRequest,
    RestoreWorkflowRequest,
    SaveDraftRequest,
    UpdateSettingsRequest,
    ValidateDraftRequest,
    ValidateWorkflowRequest,
)
from services import infra_automation_service as service
from services.identity_service import IdentityError
from services import project_service as authorization

MAX_BODY_BYTES = 131072
MAX_PREFLIGHT_BODY_BYTES = 12582912
MAX_BODY_DEPTH = 16
ObjectId = Annotated[
    str, Path(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
]
ScopeId = Annotated[int, Query(ge=1, le=SAFE_INTEGER)]
OptionalScopeId = Annotated[int | None, Query(ge=1, le=SAFE_INTEGER)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageCursor = Annotated[
    str | None,
    Query(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$"),
]
AttemptId = Annotated[
    str, Query(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
]


def _error(status: int) -> JSONResponse:
    error = LifecycleError(status if status in LifecycleError._ERRORS else 503)
    response = build_error_response(
        error.status_code,
        error.code,
        error.message,
        {"retryable": error.retryable, "correlation_id": secrets.token_hex(16)},
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _integer(value: str) -> int:
    if len(value.lstrip("-")) > 16:
        raise ValueError
    result = int(value)
    if abs(result) > SAFE_INTEGER:
        raise ValueError
    return result


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError
    return result


def _invalid_constant(value: str):
    raise ValueError


async def _bounded_body(request: Request, *, maximum: int = MAX_BODY_BYTES) -> None:
    """Bound bytes and nesting before JSON or request-model construction."""
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        raise LifecycleError()
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > maximum:
            raise LifecycleError(429)
        body.extend(chunk)
    try:
        text = body.decode("utf-8", errors="strict")
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "{[":
                depth += 1
                if depth > MAX_BODY_DEPTH:
                    raise ValueError
            elif char in "}]":
                depth -= 1
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_int=_integer,
            parse_float=_float,
            parse_constant=_invalid_constant,
        )
        if not isinstance(payload, dict):
            raise ValueError
        request._body = bytes(body)
        request._json = payload
    except (ValueError, UnicodeError, RecursionError):
        raise LifecycleError() from None


class AutomationRoute(ApiRoute):
    """Keep lifecycle errors closed, including dependency and transport failures."""

    def get_route_handler(self):
        original = APIRoute.get_route_handler(self)
        query_fields = {field.alias for field in self.dependant.query_params}

        async def handler(request: Request):
            try:
                with bind_project_credentials(request):
                    if any(
                        key not in query_fields
                        or len(request.query_params.getlist(key)) != 1
                        for key in request.query_params
                    ):
                        raise LifecycleError()
                    cursor = request.query_params.get("cursor")
                    if cursor is not None and (
                        not 1 <= len(cursor) <= 128
                        or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", cursor) is None
                    ):
                        raise LifecycleError(409)
                    if request.method in {"POST", "PUT", "PATCH"}:
                        await _bounded_body(
                            request,
                            maximum=MAX_PREFLIGHT_BODY_BYTES
                            if self.path.endswith("/preflights")
                            else MAX_BODY_BYTES,
                        )
                    response = await original(request)
                    response.headers["Cache-Control"] = "no-store"
                    return response
            except LifecycleError as exc:
                return _error(exc.status_code)
            except (
                ApiError,
                IdentityError,
                authorization.TrustedAuthorizationError,
            ) as exc:
                return _error(exc.status_code)
            except RequestValidationError:
                return _error(422)
            except HTTPException as exc:
                return _error(exc.status_code)
            except Exception:  # noqa: BLE001
                return _error(503)

        return handler


router = APIRouter(
    prefix="/api/v1/infra-automation",
    tags=["infra-automation"],
    route_class=AutomationRoute,
    dependencies=[Depends(require_human_principal)],
    responses={
        status: {"model": AutomationErrorResponse}
        for status in (401, 403, 409, 422, 429, 503)
    },
)


def _response(data):
    return {"data": data, "meta": build_meta(correlation_id=secrets.token_hex(16))}


@router.post("/runs", response_model=AutomationRunResponse)
def request_run(payload: RunRequest):
    return _response(service.request_run(payload))


@router.get("/runs", response_model=AutomationRunListResponse)
def list_runs(
    project_id: ScopeId,
    workspace_id: OptionalScopeId = None,
    limit: PageLimit = 25,
    cursor: PageCursor = None,
):
    return _response(
        service.list_runs(
            project_id, workspace_id=workspace_id, limit=limit, cursor=cursor
        )
    )


@router.get("/runs/{run_id}", response_model=AutomationRunResponse)
def get_run(run_id: ObjectId):
    return _response(service.get_run(run_id))


@router.get("/runs/{run_id}/steps", response_model=AutomationStepListResponse)
def list_steps(run_id: ObjectId, limit: PageLimit = 25, cursor: PageCursor = None):
    return _response(service.list_steps(run_id, limit=limit, cursor=cursor))


@router.get("/runs/{run_id}/logs", response_model=AutomationLogListResponse)
def get_logs(
    run_id: ObjectId,
    attempt_id: AttemptId,
    limit: PageLimit = 25,
    cursor: PageCursor = None,
):
    return _response(service.get_logs(run_id, attempt_id, limit=limit, cursor=cursor))


@router.post("/runs/{run_id}/cancel", response_model=AutomationRunResponse)
def cancel_run(run_id: ObjectId, payload: CancelRunRequest, request: Request):
    coordinator = getattr(request.app.state, "infra_automation_coordinator", None)
    cancel_port = getattr(coordinator, "cancel_run", None)
    return _response(service.cancel_run(run_id, payload, cancel_port=cancel_port))


@router.post("/workflows", response_model=AutomationWorkflowResponse)
def create_workflow(payload: CreateWorkflowRequest):
    return _response(service.create_workflow(payload))


@router.get("/workflows", response_model=AutomationWorkflowListResponse)
def list_workflows(
    project_id: ScopeId,
    workspace_id: OptionalScopeId = None,
    limit: PageLimit = 25,
    cursor: PageCursor = None,
):
    return _response(
        service.list_workflows(
            project_id, workspace_id=workspace_id, limit=limit, cursor=cursor
        )
    )


@router.post("/workflows/validate", response_model=AutomationValidationResponse)
def validate_definition(payload: ValidateWorkflowRequest):
    return _response(service.validate_definition(payload))


@router.get("/workflows/{workflow_id}", response_model=AutomationWorkflowResponse)
def get_workflow(workflow_id: ObjectId):
    return _response(service.get_workflow(workflow_id))


@router.put("/workflows/{workflow_id}/draft", response_model=AutomationWorkflowResponse)
def save_draft(workflow_id: ObjectId, payload: SaveDraftRequest):
    return _response(service.save_draft(workflow_id, payload))


@router.post(
    "/workflows/{workflow_id}/validate", response_model=AutomationValidationResponse
)
def validate_draft(workflow_id: ObjectId, payload: ValidateDraftRequest):
    return _response(service.validate_draft(workflow_id, payload))


@router.post(
    "/workflows/{workflow_id}/revisions", response_model=AutomationRevisionResponse
)
def publish_workflow(workflow_id: ObjectId, payload: PublishWorkflowRequest):
    return _response(service.publish_workflow(workflow_id, payload))


@router.get(
    "/workflows/{workflow_id}/revisions", response_model=AutomationRevisionListResponse
)
def list_revisions(
    workflow_id: ObjectId, limit: PageLimit = 25, cursor: PageCursor = None
):
    return _response(service.list_revisions(workflow_id, limit=limit, cursor=cursor))


@router.get(
    "/workflows/{workflow_id}/revisions/{revision_id}",
    response_model=AutomationRevisionResponse,
)
def get_revision(workflow_id: ObjectId, revision_id: ObjectId):
    return _response(service.get_revision(workflow_id, revision_id))


@router.post(
    "/workflows/{workflow_id}/archive", response_model=AutomationWorkflowResponse
)
def archive_workflow(workflow_id: ObjectId, payload: ArchiveWorkflowRequest):
    return _response(service.archive_workflow(workflow_id, payload))


@router.post(
    "/workflows/{workflow_id}/restore", response_model=AutomationWorkflowResponse
)
def restore_workflow(workflow_id: ObjectId, payload: RestoreWorkflowRequest):
    return _response(service.restore_workflow(workflow_id, payload))


@router.get("/settings", response_model=AutomationPolicyResponse)
def get_settings(project_id: ScopeId):
    return _response(service.get_settings(project_id))


@router.patch("/settings", response_model=AutomationPolicyResponse)
def update_settings(payload: UpdateSettingsRequest):
    return _response(service.update_settings(payload))


@router.post("/settings/revoke", response_model=AutomationPolicyResponse)
def revoke_epoch(payload: AdvanceEpochRequest):
    return _response(service.advance_epoch(payload))


@router.post("/settings/restore-epoch", response_model=AutomationPolicyResponse)
def restore_epoch(payload: AdvanceEpochRequest):
    return _response(service.advance_epoch(payload, restore=True))


@router.get("/audit", response_model=AutomationAuditResponse)
def export_audit(
    project_id: ScopeId,
    workspace_id: OptionalScopeId = None,
    limit: PageLimit = 25,
    cursor: PageCursor = None,
):
    return _response(
        service.export_audit(
            project_id, workspace_id=workspace_id, limit=limit, cursor=cursor
        )
    )


@router.post("/preflights", response_model=AutomationRunResponse)
def request_preflight(payload: PreflightRequest):
    return _response(service.request_preflight(payload))


@router.get("/runs/{run_id}/reports", response_model=AutomationPreflightLinksResponse)
def list_run_reports(run_id: ObjectId):
    return _response(service.list_run_reports(run_id))
