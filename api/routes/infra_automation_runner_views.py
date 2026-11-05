"""Read-only runner UI capabilities; runner administration remains HTTPS-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from api.dependencies import require_human_principal
from api.routes.infra_automation import AutomationRoute, ScopeId, _response
from api.schemas import AutomationMeta
from infra_automation.contracts import ClosedModel
from services import infra_automation_runners as runners


router = APIRouter(
    prefix="/api/v1/infra-automation",
    route_class=AutomationRoute,
    tags=["infra-automation"],
    dependencies=[Depends(require_human_principal)],
)


class RunnerCapabilitiesResponse(ClosedModel):
    data: runners.RunnerCapabilities
    meta: AutomationMeta


@router.get("/runner-capabilities", response_model=RunnerCapabilitiesResponse)
def runner_capabilities(project_id: ScopeId, workspace_id: ScopeId):
    return _response(runners.capabilities(project_id, workspace_id))
