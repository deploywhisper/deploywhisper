"""Human-authorized declared inventories and immutable preflight run snapshots."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import require_human_principal
from api.routes.infra_automation import AutomationRoute, ObjectId, ScopeId, _response
from api.schemas import AutomationErrorResponse, AutomationMeta, AutomationRunResponse
from infra_automation.contracts import ClosedModel
from infra_automation.unit_contracts import (
    SaveUnitsRequest,
    UnitRevisionPage,
    UnitRevisionHistory,
    UnitRevisionView,
    UnitRunRequest,
    UnitRunView,
    UnitValidation,
    ValidateUnitsRequest,
)
from services import infra_automation_units as service

router = APIRouter(
    prefix="/api/v1/infra-automation",
    route_class=AutomationRoute,
    tags=["infra-automation"],
    dependencies=[Depends(require_human_principal)],
    responses={
        status: {"model": AutomationErrorResponse}
        for status in (401, 403, 409, 422, 429, 503)
    },
)


class UnitRevisionResponse(ClosedModel):
    data: UnitRevisionView
    meta: AutomationMeta


class UnitRevisionListResponse(ClosedModel):
    data: UnitRevisionPage
    meta: AutomationMeta


class UnitRevisionHistoryResponse(ClosedModel):
    data: UnitRevisionHistory
    meta: AutomationMeta


class UnitValidationResponse(ClosedModel):
    data: UnitValidation
    meta: AutomationMeta


class UnitRunResponse(ClosedModel):
    data: UnitRunView
    meta: AutomationMeta


@router.get("/units", response_model=UnitRevisionListResponse)
def list_units(project_id: ScopeId, workspace_id: ScopeId):
    return _response(service.list_units(project_id, workspace_id))


@router.post("/units", response_model=UnitRevisionResponse)
def save_units(payload: SaveUnitsRequest):
    return _response(service.save_units(payload))


@router.post("/units/validate", response_model=UnitValidationResponse)
def validate_units(payload: ValidateUnitsRequest):
    return _response(service.validate_units(payload))


@router.get(
    "/units/{inventory_id}/revisions", response_model=UnitRevisionHistoryResponse
)
def revision_history(
    inventory_id: ObjectId, project_id: ScopeId, workspace_id: ScopeId
):
    return _response(
        service.list_revisions(
            inventory_id, project_id=project_id, workspace_id=workspace_id
        )
    )


@router.get(
    "/units/{inventory_id}/revisions/{revision_id}", response_model=UnitRevisionResponse
)
def get_revision(
    inventory_id: ObjectId,
    revision_id: ObjectId,
    project_id: ScopeId,
    workspace_id: ScopeId,
):
    return _response(
        service.get_revision(
            inventory_id, revision_id, project_id=project_id, workspace_id=workspace_id
        )
    )


@router.post("/units/runs", response_model=AutomationRunResponse)
def request_unit_run(payload: UnitRunRequest):
    return _response(service.request_unit_run(payload))


@router.get("/runs/{run_id}/units", response_model=UnitRunResponse)
def get_run_units(run_id: ObjectId, project_id: ScopeId, workspace_id: ScopeId):
    return _response(
        service.get_run_units(run_id, project_id=project_id, workspace_id=workspace_id)
    )
