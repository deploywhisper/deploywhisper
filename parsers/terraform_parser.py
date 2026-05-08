"""Terraform parser."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import hcl2

from parsers.base import (
    UnifiedChange,
    build_change_id,
    is_non_mutating_action,
    normalize_change_action,
)

SUPPORTED_PLAN_FIELDS = {
    "format_version",
    "resource_changes",
    "terraform_version",
}
PLAN_LEVEL_RESOURCE_ID = "terraform-plan"
SUPPORTED_PLAN_ACTIONS = {
    "create",
    "delete",
    "no-op",
    "read",
    "update",
}
SUPPORTED_PLAN_ACTION_SETS = {
    frozenset({"no-op"}),
    frozenset({"read"}),
    frozenset({"create"}),
    frozenset({"update"}),
    frozenset({"delete"}),
    frozenset({"create", "delete"}),
}


def _normalize_hcl_label(label: object) -> str:
    """Return Terraform block labels without parser-preserved quote delimiters."""
    normalized = str(label)
    if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
        return normalized[1:-1]
    return normalized


def _address_matches_type(
    address: str, *, actual_type: str | None, expected_type: str
) -> bool:
    normalized = address.lower()
    expected_type = expected_type.lower()
    return (
        (actual_type or "").lower() == expected_type
        or normalized.startswith(f"{expected_type}.")
        or f".{expected_type}." in normalized
    )


def _terraform_summary(
    address: str, action: str, *, resource_type: str | None = None
) -> str:
    normalized = address.lower()
    if action == "no-op":
        return f"Terraform resource {address} has no planned changes."
    if action == "read":
        return f"Terraform resource {address} is read-only; no infrastructure mutation planned."
    if _address_matches_type(
        normalized, actual_type=resource_type, expected_type="aws_security_group"
    ):
        return f"Security group {address} changes network access rules and should be reviewed for exposure before deploy."
    if _address_matches_type(
        normalized, actual_type=resource_type, expected_type="aws_vpc"
    ):
        return f"VPC {address} changes network boundaries and may affect connected routing or segmentation."
    if (
        _address_matches_type(
            normalized, actual_type=resource_type, expected_type="aws_iam_role"
        )
        or _address_matches_type(
            normalized, actual_type=resource_type, expected_type="aws_iam_policy"
        )
        or _address_matches_type(
            normalized,
            actual_type=resource_type,
            expected_type="aws_iam_role_policy_attachment",
        )
    ):
        return f"IAM resource {address} changes access permissions and should be reviewed for privilege impact."
    if _address_matches_type(
        normalized,
        actual_type=resource_type,
        expected_type="aws_eks_cluster",
    ) or _address_matches_type(
        normalized,
        actual_type=resource_type,
        expected_type="aws_eks_node_group",
    ):
        return f"EKS resource {address} changes cluster or node-group behavior and may affect workload availability."
    if normalized.startswith("module.") and resource_type is None:
        return f"Terraform module {address} updated in configuration and may affect multiple downstream resources."
    return f"Terraform resource {address} marked for {action}."


def _path_to_string(path: list[Any]) -> str:
    return ".".join(str(part) for part in path)


def _valid_marker_tree(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, dict):
        return all(_valid_marker_tree(nested) for nested in value.values())
    if isinstance(value, list):
        return all(_valid_marker_tree(nested) for nested in value)
    return False


def _true_value_paths(value: Any, prefix: list[Any] | None = None) -> list[str]:
    path = prefix or []
    if value is True:
        return [_path_to_string(path)] if path else ["<root>"]
    if isinstance(value, dict):
        paths: list[str] = []
        for key, nested in value.items():
            paths.extend(_true_value_paths(nested, [*path, key]))
        return paths
    if isinstance(value, list):
        paths: list[str] = []
        for index, nested in enumerate(value):
            paths.extend(_true_value_paths(nested, [*path, index]))
        return paths
    return []


def _replace_paths(change: dict[str, Any]) -> list[str]:
    paths = change.get("replace_paths")
    if not isinstance(paths, list):
        return []
    normalized: list[str] = []
    for path in paths:
        if isinstance(path, list):
            normalized.append(_path_to_string(path))
    return normalized


def _action_list(change: dict[str, Any], *, address: str) -> list[str]:
    actions = change.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError(
            f"Terraform plan resource {address} is missing required change.actions."
        )
    normalized = [str(action).strip() for action in actions]
    if len(set(normalized)) != len(normalized):
        raise ValueError(
            f"Duplicate Terraform action(s) for {address}: {', '.join(normalized)}."
        )
    invalid_actions = [
        action
        for action in normalized
        if not action or action not in SUPPORTED_PLAN_ACTIONS
    ]
    if invalid_actions:
        raise ValueError(
            f"Unsupported Terraform action(s) for {address}: {', '.join(invalid_actions)}."
        )
    if frozenset(normalized) not in SUPPORTED_PLAN_ACTION_SETS:
        raise ValueError(
            f"Unsupported Terraform action combination for {address}: {', '.join(normalized)}."
        )
    return normalized


def _resource_address(resource: dict[str, Any], *, index: int) -> str:
    address = resource.get("address")
    if not isinstance(address, str) or not address.strip():
        raise ValueError(
            f"Terraform plan resource change at index {index} is missing required address."
        )
    return address.strip()


def _invalid_metadata_fields(change: dict[str, Any]) -> list[str]:
    invalid: list[str] = []
    if "replace_paths" in change:
        paths = change.get("replace_paths")
        if not isinstance(paths, list) or any(
            not isinstance(path, list) for path in paths
        ):
            invalid.append("change.replace_paths.invalid")
    for field in ("after_unknown", "after_sensitive", "before_sensitive"):
        if field in change and not _valid_marker_tree(change.get(field)):
            invalid.append(f"change.{field}.invalid")
    return invalid


def _unsupported_plan_fields(payload: dict[str, Any]) -> list[str]:
    return [
        f"plan.{field}"
        for field in sorted(payload)
        if field not in SUPPORTED_PLAN_FIELDS
    ]


def _unsupported_fields(resource: dict[str, Any], change: dict[str, Any]) -> list[str]:
    supported_resource_fields = {
        "address",
        "change",
        "index",
        "mode",
        "module_address",
        "name",
        "provider_name",
        "type",
    }
    supported_change_fields = {
        "actions",
        "after",
        "after_sensitive",
        "after_unknown",
        "before",
        "before_sensitive",
        "replace_paths",
    }
    resource_fields = [
        f"resource_change.{field}"
        for field in sorted(resource)
        if field not in supported_resource_fields
    ]
    change_fields = [
        f"change.{field}"
        for field in sorted(change)
        if field not in supported_change_fields
    ]
    return [
        *change_fields,
        *_invalid_metadata_fields(change),
        *resource_fields,
    ]


def _plan_metadata(
    resource: dict[str, Any],
    change: dict[str, Any],
    payload: dict[str, Any],
    *,
    actions: list[str],
    include_plan_unsupported_fields: bool = False,
) -> dict[str, Any]:
    metadata = {
        "source_format": "terraform_plan_json",
        "plan_format_version": payload.get("format_version"),
        "terraform_version": payload.get("terraform_version"),
        "resource_change_count": len(payload.get("resource_changes", []) or []),
        "module_address": resource.get("module_address"),
        "mode": resource.get("mode"),
        "resource_type": resource.get("type"),
        "resource_name": resource.get("name"),
        "provider_name": resource.get("provider_name"),
        "actions": actions,
        "replace_paths": _replace_paths(change),
        "unknown_after_apply": _true_value_paths(change.get("after_unknown") or {}),
        "redacted_fields": sorted(
            {
                *_true_value_paths(change.get("before_sensitive") or {}),
                *_true_value_paths(change.get("after_sensitive") or {}),
            }
        ),
        "unsupported_fields": _unsupported_fields(resource, change),
    }
    if include_plan_unsupported_fields:
        metadata["plan_unsupported_fields"] = _unsupported_plan_fields(payload)
    return metadata


def _parse_terraform_plan_json(name: str, raw_content: bytes) -> list[UnifiedChange]:
    payload = json.loads(raw_content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Terraform plan JSON must be an object.")
    if "resource_changes" not in payload:
        raise ValueError("Terraform plan JSON is missing required resource_changes.")
    resource_changes = payload.get("resource_changes", [])
    if not isinstance(resource_changes, list):
        raise ValueError("Terraform plan resource_changes must be a list.")
    if not resource_changes:
        actions = ["no-op"]
        metadata = _plan_metadata(
            {},
            {"actions": actions},
            payload,
            actions=actions,
            include_plan_unsupported_fields=True,
        )
        return [
            UnifiedChange(
                change_id=build_change_id(
                    name, "terraform", PLAN_LEVEL_RESOURCE_ID, "no-op", 0
                ),
                source_file=name,
                tool="terraform",
                resource_id=PLAN_LEVEL_RESOURCE_ID,
                action="no-op",
                summary=f"Terraform plan {name} has no planned resource changes.",
                metadata=metadata,
            )
        ]
    parsed_resources: list[
        tuple[int, dict[str, Any], dict[str, Any], str, list[str], str]
    ] = []
    for index, resource in enumerate(resource_changes):
        if not isinstance(resource, dict):
            raise ValueError(
                f"Terraform plan resource change at index {index} must be an object."
            )
        change = resource.get("change", {})
        if not isinstance(change, dict):
            raise ValueError(
                f"Terraform plan resource change at index {index} has invalid change payload."
            )
        address = _resource_address(resource, index=index)
        actions = _action_list(change, address=address)
        action = normalize_change_action(actions)
        parsed_resources.append((index, resource, change, address, actions, action))

    plan_metadata_index = next(
        (
            index
            for index, *_rest, action in parsed_resources
            if not is_non_mutating_action(action)
        ),
        parsed_resources[0][0],
    )
    changes: list[UnifiedChange] = []
    for index, resource, change, address, actions, action in parsed_resources:
        metadata = _plan_metadata(
            resource,
            change,
            payload,
            actions=actions,
            include_plan_unsupported_fields=index == plan_metadata_index,
        )
        changes.append(
            UnifiedChange(
                change_id=build_change_id(name, "terraform", address, action, index),
                source_file=name,
                tool="terraform",
                resource_id=address,
                action=action,
                summary=_terraform_summary(
                    address,
                    action,
                    resource_type=metadata["resource_type"],
                ),
                metadata=metadata,
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
                address = (
                    f"{_normalize_hcl_label(resource_type)}."
                    f"{_normalize_hcl_label(resource_name)}"
                )
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
            address = f"module.{_normalize_hcl_label(module_name)}"
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
