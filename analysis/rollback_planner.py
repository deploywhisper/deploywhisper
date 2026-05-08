"""Rollback planning and complexity scoring."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from parsers.base import UnifiedChange, is_non_mutating_action, normalize_change_action

RollbackComplexity = Literal["low", "medium", "high"]


class RollbackStep(BaseModel):
    order: int = Field(..., description="Execution order")
    title: str = Field(..., description="Short rollback step title")
    detail: str = Field(..., description="Operational rollback instruction")
    estimated_minutes: int = Field(
        default=5, description="Estimated number of minutes for this rollback step"
    )
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
    complexity_score: int = Field(
        default=1, description="Rollback complexity score on a 1-5 scale"
    )
    complexity_explanation: str = Field(
        default="Minimal rollback effort based on the available change set.",
        description="Human-readable explanation for the complexity score",
    )
    warning: str | None = Field(
        default=None, description="Warning if context is incomplete"
    )


def _rollback_priority(change: UnifiedChange) -> tuple[int, str]:
    normalized_action = normalize_change_action(change.action)
    if normalized_action in {"destroy", "replace"}:
        priority = 0
    elif change.tool in {"terraform", "cloudformation"}:
        priority = 1
    elif change.tool in {"kubernetes", "ansible", "jenkins"}:
        priority = 2
    else:
        priority = 3
    return (priority, change.resource_id)


def _complexity_for_changes(
    changes: list[UnifiedChange], *, partial_context: bool
) -> RollbackComplexity:
    score, _ = _complexity_details(changes, partial_context=partial_context)
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _estimate_step_minutes(change: UnifiedChange) -> int:
    base_minutes = {
        "terraform": 10,
        "cloudformation": 12,
        "kubernetes": 8,
        "ansible": 7,
        "jenkins": 6,
    }.get(change.tool, 5)
    normalized_action = normalize_change_action(change.action)
    if normalized_action in {"destroy", "replace"}:
        base_minutes += 5
    elif normalized_action == "modify" or change.action == "patch":
        base_minutes += 2
    return base_minutes


def _complexity_details(
    changes: list[UnifiedChange], *, partial_context: bool
) -> tuple[int, str]:
    if not changes:
        return (
            1,
            "No mutating parsed changes were available, so rollback effort is minimal.",
        )

    destructive_count = sum(
        1
        for change in changes
        if normalize_change_action(change.action) in {"destroy", "replace"}
    )
    tool_count = len({change.tool for change in changes})

    score = 1
    reasons: list[str] = []

    if destructive_count:
        score += min(destructive_count, 2)
        change_label = "change" if destructive_count == 1 else "changes"
        reasons.append(f"{destructive_count} destructive {change_label}")
    if len(changes) >= 3:
        score += 1
        reasons.append(f"{len(changes)} rollback steps")
    if tool_count >= 2:
        score += 1
        reasons.append(f"{tool_count} tool types")
    if partial_context:
        score += 1
        reasons.append("partial parser context")

    score = min(score, 5)
    tool_counts = Counter(change.tool for change in changes)
    dominant_tool = max(tool_counts.items(), key=lambda item: (item[1], item[0]))[0]
    if not reasons:
        reasons.append(f"single {dominant_tool} change")
    explanation = f"Score {score}/5 because the plan covers " + ", ".join(reasons) + "."
    return (score, explanation)


def build_rollback_copy_text(plan: RollbackPlan) -> str:
    """Build a clipboard-friendly rollback plan summary."""
    lines = [
        "Rollback plan",
        (
            f"Complexity: {plan.complexity_score}/5 ({plan.complexity}) - "
            f"{plan.complexity_explanation}"
        ),
    ]
    if plan.warning:
        lines.append(f"Warning: {plan.warning}")
    for step in plan.steps:
        critical_label = " [Critical path]" if step.critical else ""
        lines.append(
            f"{step.order}. {step.title}{critical_label} (~{step.estimated_minutes} min)"
        )
        lines.append(f"   {step.detail}")
    return "\n".join(lines)


def generate_rollback_plan(
    changes: list[UnifiedChange], partial_context: bool = False
) -> RollbackPlan:
    mutating_changes = [
        change for change in changes if not is_non_mutating_action(change.action)
    ]
    ordered_changes = sorted(mutating_changes, key=_rollback_priority)
    steps: list[RollbackStep] = []
    for index, change in enumerate(ordered_changes, start=1):
        steps.append(
            RollbackStep(
                order=index,
                title=f"Revert {change.resource_id}",
                detail=(
                    f"Rollback the {change.tool} {normalize_change_action(change.action)} change for {change.resource_id} from {change.source_file} "
                    f"and verify the prior stable state is restored."
                ),
                estimated_minutes=_estimate_step_minutes(change),
                critical=index == 1
                or normalize_change_action(change.action) in {"destroy", "replace"},
            )
        )

    if not steps:
        steps.append(
            RollbackStep(
                order=1,
                title="No rollback steps generated",
                detail="No mutating parsed changes were available to build rollback guidance.",
                estimated_minutes=0,
                critical=False,
            )
        )

    warning = None
    if partial_context:
        warning = (
            "Rollback plan may be incomplete because one or more files failed to parse."
        )
    complexity_score, complexity_explanation = _complexity_details(
        mutating_changes, partial_context=partial_context
    )

    return RollbackPlan(
        steps=steps,
        complexity=_complexity_for_changes(
            mutating_changes, partial_context=partial_context
        ),
        complexity_score=complexity_score,
        complexity_explanation=complexity_explanation,
        warning=warning,
    )
