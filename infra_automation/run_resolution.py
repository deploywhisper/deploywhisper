"""Derived execution views over already validated immutable run snapshots.

The original workflow/snapshot bytes and their digests never change. This only
interprets declared whole-value references using captured inputs and run scope;
it neither admits profiles nor creates authorization from a resolved value.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from infra_automation.contracts import Identifier, STEP_CONTRACTS
from infra_automation.lifecycle import SnapshotDocument
from infra_automation.workflow_schema import (
    Workflow,
    PolicyEvaluationStep,
    RegisteredGithubHandoffStep,
)
from infra_automation.workflow_validation import ResolutionContext, resolve_value


def resolve_target_value(document: SnapshotDocument, value: Any) -> str:
    context = ResolutionContext(
        inputs=tuple(document.inputs.items()),
        metadata=(
            ("project_id", str(document.project_id)),
            ("workspace_id", str(document.workspace_id)),
            ("environment", document.environment),
        ),
        outputs=(),
        producers=tuple(
            (step.id, STEP_CONTRACTS[step.kind].output)
            for step in document.definition.steps
        ),
    )
    resolved = resolve_value(value, context)
    return TypeAdapter(Identifier).validate_python(resolved)


def runtime_workflow(document: SnapshotDocument) -> Workflow:
    """Materialize only execution scope; immutable publication remains the identity."""
    data = document.definition.model_dump(mode="json")
    data.update(
        project_id=str(document.project_id),
        workspace_id=str(document.workspace_id),
        environment=document.environment,
    )
    for step, raw in zip(document.definition.steps, data["steps"]):
        if isinstance(step, (PolicyEvaluationStep, RegisteredGithubHandoffStep)):
            raw["target_id"] = resolve_target_value(document, step.target_id)
            raw["environment"] = resolve_target_value(document, step.environment)
    return Workflow.model_validate(data)
