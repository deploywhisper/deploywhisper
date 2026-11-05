"""Human-authorized collection observation adapters; no execution authority."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from api.dependencies import require_human_principal
from api.routes.infra_automation import AutomationRoute, ObjectId, ScopeId, _response
from api.schemas import AutomationMeta
from infra_automation.contracts import ClosedModel
from services import infra_automation_collection_views as views

router = APIRouter(
    prefix="/api/v1/infra-automation",
    route_class=AutomationRoute,
    tags=["infra-automation"],
    dependencies=[Depends(require_human_principal)],
)


class CollectionViewResponse(ClosedModel):
    data: views.CollectionView
    meta: AutomationMeta


class CollectionReadinessResponse(ClosedModel):
    data: views.CollectionReadiness
    meta: AutomationMeta


@router.get("/runs/{run_id}/collection", response_model=CollectionViewResponse)
def collection(run_id: ObjectId, project_id: ScopeId, workspace_id: ScopeId):
    return _response(
        views.get_collection(run_id, project_id=project_id, workspace_id=workspace_id)
    )


@router.get(
    "/workflows/{workflow_id}/revisions/{revision_id}/collection",
    response_model=CollectionReadinessResponse,
)
def readiness(
    workflow_id: ObjectId,
    revision_id: ObjectId,
    project_id: ScopeId,
    workspace_id: ScopeId,
):
    return _response(
        views.get_readiness(
            workflow_id, revision_id, project_id=project_id, workspace_id=workspace_id
        )
    )
