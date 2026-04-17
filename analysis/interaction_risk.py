"""Cross-tool interaction risk detection."""

from __future__ import annotations

from collections import defaultdict
import re

from pydantic import BaseModel, Field

from parsers.base import UnifiedChange


class InteractionRisk(BaseModel):
    key: str = Field(..., description="Stable identifier for the interaction pattern")
    summary: str = Field(..., description="User-facing explanation of the interaction")
    contributing_files: list[str] = Field(default_factory=list, description="Files involved")
    contributing_resources: list[str] = Field(default_factory=list, description="Resources involved")
    contribution_bonus: int = Field(..., description="Additional score contribution")


TOKEN_PATTERN = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)
STOP_WORDS = {
    "terraform",
    "kubernetes",
    "ansible",
    "jenkins",
    "cloudformation",
    "deployment",
    "resource",
    "resources",
    "change",
    "changes",
    "changed",
    "modify",
    "modified",
    "create",
    "created",
    "destroy",
    "deleted",
    "apply",
    "yaml",
    "json",
    "plan",
    "stack",
    "main",
    "api",
    "app",
    "prod",
    "production",
    "staging",
    "stage",
    "dev",
    "development",
    "worker",
    "service",
    "primary",
    "default",
    "backend",
    "frontend",
    "jobs",
}


def _collect_groups(changes: list[UnifiedChange]) -> dict[str, list[UnifiedChange]]:
    grouped: dict[str, list[UnifiedChange]] = defaultdict(list)
    for change in changes:
        grouped[change.tool].append(change)
    return grouped


def _tool_tokens(changes: list[UnifiedChange]) -> set[str]:
    tokens: set[str] = set()
    for change in changes:
        blob = " ".join([change.source_file, change.resource_id, change.summary]).lower()
        for token in TOKEN_PATTERN.findall(blob):
            fragments = [fragment for fragment in re.split(r"[^a-z0-9]+", token) if fragment]
            for fragment in fragments:
                if len(fragment) <= 2 or fragment in STOP_WORDS:
                    continue
                tokens.add(fragment)
    return tokens


def _shared_context_tokens(grouped: dict[str, list[UnifiedChange]], tools: tuple[str, str]) -> list[str]:
    left_tokens = _tool_tokens(grouped[tools[0]])
    right_tokens = _tool_tokens(grouped[tools[1]])
    return sorted(left_tokens & right_tokens)


def _shared_context_summary(
    *,
    left_tool: str,
    right_tool: str,
    shared_tokens: list[str],
    description: str,
) -> str:
    highlighted = ", ".join(shared_tokens[:3])
    return (
        f"{left_tool.title()} and {right_tool.title()} changes both reference {highlighted}; "
        f"{description}"
    )


def detect_interaction_risks(changes: list[UnifiedChange]) -> list[InteractionRisk]:
    grouped = _collect_groups(changes)
    findings: list[InteractionRisk] = []

    if {"terraform", "kubernetes"} <= set(grouped.keys()):
        shared_tokens = _shared_context_tokens(grouped, ("terraform", "kubernetes"))
        if shared_tokens:
            findings.append(
                InteractionRisk(
                    key="terraform-kubernetes",
                    summary=_shared_context_summary(
                        left_tool="terraform",
                        right_tool="kubernetes",
                        shared_tokens=shared_tokens,
                        description="infrastructure and runtime shifts may amplify each other during deployment.",
                    ),
                    contributing_files=sorted({change.source_file for tool in ("terraform", "kubernetes") for change in grouped[tool]}),
                    contributing_resources=sorted(
                        {change.resource_id for tool in ("terraform", "kubernetes") for change in grouped[tool]}
                    ),
                    contribution_bonus=12,
                ),
            )

    if {"kubernetes", "ansible"} <= set(grouped.keys()):
        shared_tokens = _shared_context_tokens(grouped, ("kubernetes", "ansible"))
        if shared_tokens:
            findings.append(
                InteractionRisk(
                    key="kubernetes-ansible",
                    summary=_shared_context_summary(
                        left_tool="kubernetes",
                        right_tool="ansible",
                        shared_tokens=shared_tokens,
                        description="runtime and configuration drift may be happening together; validate rollout safety before shipping.",
                    ),
                    contributing_files=sorted({change.source_file for tool in ("kubernetes", "ansible") for change in grouped[tool]}),
                    contributing_resources=sorted(
                        {change.resource_id for tool in ("kubernetes", "ansible") for change in grouped[tool]}
                    ),
                    contribution_bonus=10,
                ),
            )

    if {"terraform", "jenkins"} <= set(grouped.keys()):
        shared_tokens = _shared_context_tokens(grouped, ("terraform", "jenkins"))
        if shared_tokens:
            findings.append(
                InteractionRisk(
                    key="terraform-jenkins",
                    summary=_shared_context_summary(
                        left_tool="terraform",
                        right_tool="jenkins",
                        shared_tokens=shared_tokens,
                        description="delivery controls and infrastructure exposure should be reviewed together.",
                    ),
                    contributing_files=sorted({change.source_file for tool in ("terraform", "jenkins") for change in grouped[tool]}),
                    contributing_resources=sorted(
                        {change.resource_id for tool in ("terraform", "jenkins") for change in grouped[tool]}
                    ),
                    contribution_bonus=11,
                ),
            )

    return findings
