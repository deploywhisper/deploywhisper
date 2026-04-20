"""Terraform parser."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import hcl2

from parsers.base import UnifiedChange, build_change_id


def _terraform_summary(address: str, action: str) -> str:
    normalized = address.lower()
    if normalized.startswith("aws_security_group."):
        return f"Security group {address} changes network access rules and should be reviewed for exposure before deploy."
    if normalized.startswith("aws_vpc."):
        return f"VPC {address} changes network boundaries and may affect connected routing or segmentation."
    if (
        normalized.startswith("aws_iam_role.")
        or normalized.startswith("aws_iam_policy.")
        or normalized.startswith("aws_iam_role_policy_attachment.")
    ):
        return f"IAM resource {address} changes access permissions and should be reviewed for privilege impact."
    if normalized.startswith("aws_eks_cluster.") or normalized.startswith(
        "aws_eks_node_group."
    ):
        return f"EKS resource {address} changes cluster or node-group behavior and may affect workload availability."
    if normalized.startswith("module."):
        return f"Terraform module {address} updated in configuration and may affect multiple downstream resources."
    return f"Terraform resource {address} marked for {action}."


def _parse_terraform_plan_json(name: str, raw_content: bytes) -> list[UnifiedChange]:
    payload = json.loads(raw_content.decode("utf-8"))
    resource_changes = payload.get("resource_changes", [])
    changes: list[UnifiedChange] = []
    for index, resource in enumerate(resource_changes):
        address = resource.get("address", "unknown")
        actions = resource.get("change", {}).get("actions", [])
        action = "+".join(actions) if actions else "modify"
        changes.append(
            UnifiedChange(
                change_id=build_change_id(name, "terraform", address, action, index),
                source_file=name,
                tool="terraform",
                resource_id=address,
                action=action,
                summary=_terraform_summary(address, action),
            )
        )
    return changes


def _parse_terraform_hcl(name: str, raw_content: bytes) -> list[UnifiedChange]:
    payload = hcl2.load(StringIO(raw_content.decode("utf-8")))
    changes: list[UnifiedChange] = []

    occurrence = 0

    for resource_block in payload.get("resource", []):
        for resource_type, resources in resource_block.items():
            for resource_name in resources.keys():
                address = f"{resource_type}.{resource_name}"
                changes.append(
                    UnifiedChange(
                        change_id=build_change_id(
                            name, "terraform", address, "modify", occurrence
                        ),
                        source_file=name,
                        tool="terraform",
                        resource_id=address,
                        action="modify",
                        summary=_terraform_summary(address, "modify"),
                    )
                )
                occurrence += 1

    for module_block in payload.get("module", []):
        for module_name in module_block.keys():
            address = f"module.{module_name}"
            changes.append(
                UnifiedChange(
                    change_id=build_change_id(
                        name, "terraform", address, "modify", occurrence
                    ),
                    source_file=name,
                    tool="terraform",
                    resource_id=address,
                    action="modify",
                    summary=_terraform_summary(address, "modify"),
                )
            )
            occurrence += 1

    return changes


def parse_terraform(name: str, raw_content: bytes | None) -> list[UnifiedChange]:
    if not raw_content:
        return []

    suffix = Path(name.lower()).suffix
    if suffix == ".json":
        return _parse_terraform_plan_json(name, raw_content)
    return _parse_terraform_hcl(name, raw_content)
