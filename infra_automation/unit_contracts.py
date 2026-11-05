"""Scoped declared-inventory requests and read-only run evidence views."""

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictInt, StrictStr
from infra_automation.contracts import ClosedModel, Digest, Identifier
from infra_automation.lifecycle import MutationRequest, Positive
from infra_automation.preflight_contracts import ArtifactUpload
from infra_automation.state import RunRequest, UTCText
from infra_automation.unit_map import UnitMap, UnitPlan


class ValidateUnitsRequest(ClosedModel):
    project_id: Positive
    workspace_id: Positive
    map: dict


class UnitValidationError(ClosedModel):
    code: StrictStr
    message: StrictStr
    path: list[StrictStr | StrictInt]


class UnitValidation(ClosedModel):
    valid: StrictBool
    plan: UnitPlan | None
    errors: list[UnitValidationError]


class SaveUnitsRequest(MutationRequest):
    project_id: Positive
    workspace_id: Positive
    inventory_id: Identifier | None = None
    expected_version: Annotated[StrictInt, Field(ge=0, le=32)]
    map: UnitMap


class UnitStepBinding(ClosedModel):
    unit_id: Identifier
    intake_step_id: Identifier
    analysis_step_id: Identifier


class UnitInputBinding(UnitStepBinding):
    artifacts: Annotated[list[ArtifactUpload], Field(max_length=32)] = Field(
        default_factory=list
    )


class UnitRunRequest(ClosedModel):
    run: RunRequest
    revision_id: Identifier
    confirmed_map_digest: Digest
    bindings: Annotated[list[UnitInputBinding], Field(min_length=1, max_length=25)]


class UnitRevisionSummary(ClosedModel):
    inventory_id: Identifier
    revision_id: Identifier
    version: Positive
    project_id: Positive
    workspace_id: Positive
    map_digest: Digest
    waves_digest: Digest
    created_by: Identifier
    created_at: UTCText


class UnitRevisionView(UnitRevisionSummary):
    plan: UnitPlan


class UnitRevisionPage(ClosedModel):
    items: Annotated[list[UnitRevisionSummary], Field(max_length=25)]
    truncated: Literal[False] = False


class UnitRunSnapshot(ClosedModel):
    revision: UnitRevisionView
    bindings: Annotated[list[UnitStepBinding], Field(min_length=1, max_length=25)]
    snapshot_digest: Digest


class UnitEvidenceItem(ClosedModel):
    unit_id: Identifier
    manifest_digest: Digest
    report_id: Positive
    report_digest: Digest
    source_digest: Digest


class UnitEvidenceView(ClosedModel):
    status: Literal["pending", "available", "changed"]
    combined_digest: Digest | None
    items: Annotated[list[UnitEvidenceItem], Field(max_length=25)]


class UnitLockView(ClosedModel):
    unit_id: Identifier
    canonical_target: Identifier
    status: Literal["held", "resolved", "broken", "not_requested"]


class UnitRunView(ClosedModel):
    run_id: Identifier
    project_id: Positive
    workspace_id: Positive
    run_version: Positive
    available: StrictBool
    snapshot: UnitRunSnapshot | None
    evidence: UnitEvidenceView | None
    locks: Annotated[list[UnitLockView], Field(max_length=25)]
