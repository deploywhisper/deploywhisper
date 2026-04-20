"""Kubernetes parser."""

from __future__ import annotations

import yaml

from parsers.base import UnifiedChange, build_change_id


def parse_kubernetes(name: str, raw_content: bytes | None) -> list[UnifiedChange]:
    if not raw_content:
        return []

    documents = [doc for doc in yaml.safe_load_all(raw_content.decode("utf-8")) if doc]
    changes: list[UnifiedChange] = []
    for index, document in enumerate(documents):
        kind = document.get("kind", "Resource")
        metadata = document.get("metadata", {}) or {}
        resource_name = metadata.get("name", "unnamed")
        resource_id = f"{kind}/{resource_name}"
        changes.append(
            UnifiedChange(
                change_id=build_change_id(
                    name, "kubernetes", resource_id, "apply", index
                ),
                source_file=name,
                tool="kubernetes",
                resource_id=resource_id,
                action="apply",
                summary=(
                    f"Kubernetes {kind} {resource_name} supplied as a standalone manifest; "
                    "previous cluster state is unknown, so the delta cannot be confirmed."
                ),
            )
        )
    return changes
