"""Cross-tool interaction risk detection."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from parsers.base import UnifiedChange


class InteractionRisk(BaseModel):
    key: str = Field(..., description="Stable identifier for the interaction pattern")
    summary: str = Field(..., description="User-facing explanation of the interaction")
    contributing_files: list[str] = Field(default_factory=list, description="Files involved")
    contributing_resources: list[str] = Field(default_factory=list, description="Resources involved")
    contribution_bonus: int = Field(..., description="Additional score contribution")


def _collect_groups(changes: list[UnifiedChange]) -> dict[str, list[UnifiedChange]]:
    grouped: dict[str, list[UnifiedChange]] = defaultdict(list)
    for change in changes:
        grouped[change.tool].append(change)
    return grouped


def detect_interaction_risks(changes: list[UnifiedChange]) -> list[InteractionRisk]:
    grouped = _collect_groups(changes)
    findings: list[InteractionRisk] = []

    if {"terraform", "kubernetes"} <= set(grouped.keys()):
        findings.append(
            InteractionRisk(
                key="terraform-kubernetes",
                summary=(
                    "Terraform and Kubernetes changes are landing together; infrastructure and runtime shifts may "
                    "amplify each other during deployment."
                ),
                contributing_files=sorted({change.source_file for tool in ("terraform", "kubernetes") for change in grouped[tool]}),
                contributing_resources=sorted(
                    {change.resource_id for tool in ("terraform", "kubernetes") for change in grouped[tool]}
                ),
                contribution_bonus=12,
            )
        )

    if {"kubernetes", "ansible"} <= set(grouped.keys()):
        findings.append(
            InteractionRisk(
                key="kubernetes-ansible",
                summary=(
                    "Kubernetes and Ansible changes suggest runtime and configuration drift happening together; "
                    "validate rollout safety and operational guardrails before shipping."
                ),
                contributing_files=sorted({change.source_file for tool in ("kubernetes", "ansible") for change in grouped[tool]}),
                contributing_resources=sorted(
                    {change.resource_id for tool in ("kubernetes", "ansible") for change in grouped[tool]}
                ),
                contribution_bonus=10,
            )
        )

    if {"terraform", "jenkins"} <= set(grouped.keys()):
        findings.append(
            InteractionRisk(
                key="terraform-jenkins",
                summary=(
                    "Terraform infrastructure changes and Jenkins pipeline changes appear in the same deployment set; "
                    "review delivery controls and environment exposure together."
                ),
                contributing_files=sorted({change.source_file for tool in ("terraform", "jenkins") for change in grouped[tool]}),
                contributing_resources=sorted(
                    {change.resource_id for tool in ("terraform", "jenkins") for change in grouped[tool]}
                ),
                contribution_bonus=11,
            )
        )

    return findings
