"""Rollback planning and complexity scoring."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from parsers.base import UnifiedChange

RollbackComplexity = Literal["low", "medium", "high"]


class RollbackStep(BaseModel):
    order: int = Field(..., description="Execution order")
    title: str = Field(..., description="Short rollback step title")
    detail: str = Field(..., description="Operational rollback instruction")
    critical: bool = Field(
        ..., description="Whether this step is critical to safe recovery"
    )


class RollbackPlan(BaseModel):
    steps: list[RollbackStep] = Field(
        default_factory=list, description="Ordered rollback steps"
    )
    complexity: RollbackComplexity = Field(
        ..., description="Rollback complexity classification"
    )
    warning: str | None = Field(
        default=None, description="Warning if context is incomplete"
    )


def _rollback_priority(change: UnifiedChange) -> tuple[int, str]:
    if change.action in {"destroy", "delete", "destroy+modify"}:
        priority = 0
    elif change.tool in {"terraform", "cloudformation"}:
        priority = 1
    elif change.tool in {"kubernetes", "ansible", "jenkins"}:
        priority = 2
    else:
        priority = 3
    return (priority, change.resource_id)


def _complexity_for_changes(changes: list[UnifiedChange]) -> RollbackComplexity:
    destructive_count = sum(
        1
        for change in changes
        if change.action in {"destroy", "delete", "destroy+modify"}
    )
    if destructive_count >= 2 or len(changes) >= 6:
        return "high"
    if destructive_count == 1 or len(changes) >= 3:
        return "medium"
    return "low"


def generate_rollback_plan(
    changes: list[UnifiedChange], partial_context: bool = False
) -> RollbackPlan:
    ordered_changes = sorted(changes, key=_rollback_priority)
    steps: list[RollbackStep] = []
    for index, change in enumerate(ordered_changes, start=1):
        steps.append(
            RollbackStep(
                order=index,
                title=f"Revert {change.resource_id}",
                detail=(
                    f"Rollback the {change.tool} change for {change.resource_id} from {change.source_file} "
                    f"and verify the prior stable state is restored."
                ),
                critical=index == 1
                or change.action in {"destroy", "delete", "destroy+modify"},
            )
        )

    if not steps:
        steps.append(
            RollbackStep(
                order=1,
                title="No rollback steps generated",
                detail="No parsed changes were available to build rollback guidance.",
                critical=False,
            )
        )

    warning = None
    if partial_context:
        warning = (
            "Rollback plan may be incomplete because one or more files failed to parse."
        )

    return RollbackPlan(
        steps=steps,
        complexity=_complexity_for_changes(changes),
        warning=warning,
    )
