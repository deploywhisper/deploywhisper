"""CloudFormation parser."""

from __future__ import annotations

import json
import yaml

from parsers.base import UnifiedChange, build_change_id


class _CloudFormationLoader(yaml.SafeLoader):
    """Safe loader that tolerates CloudFormation intrinsic tags."""


def _construct_cloudformation_tag(loader: _CloudFormationLoader, tag_suffix: str, node):  # noqa: ARG001
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CloudFormationLoader.add_multi_constructor("!", _construct_cloudformation_tag)


def parse_cloudformation(name: str, raw_content: bytes | None) -> list[UnifiedChange]:
    if not raw_content:
        return []

    text = raw_content.decode("utf-8", errors="ignore")
    payload: dict
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = yaml.load(text, Loader=_CloudFormationLoader) or {}

    resources = payload.get("Resources", {}) if isinstance(payload, dict) else {}
    return [
        UnifiedChange(
            change_id=build_change_id(
                name, "cloudformation", f"resource/{resource_name}", "apply", index
            ),
            source_file=name,
            tool="cloudformation",
            resource_id=f"resource/{resource_name}",
            action="apply",
            summary=(
                f"CloudFormation resource {resource_name} supplied as a standalone template; "
                "previous stack state is unknown, so the delta cannot be confirmed."
            ),
        )
        for index, resource_name in enumerate(resources.keys())
    ]
