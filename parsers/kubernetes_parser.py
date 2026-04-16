"""Kubernetes parser."""

from __future__ import annotations

import yaml

from parsers.base import UnifiedChange


def parse_kubernetes(name: str, raw_content: bytes | None) -> list[UnifiedChange]:
    if not raw_content:
        return []

    documents = [doc for doc in yaml.safe_load_all(raw_content.decode("utf-8")) if doc]
    changes: list[UnifiedChange] = []
    for document in documents:
        kind = document.get("kind", "Resource")
        metadata = document.get("metadata", {}) or {}
        resource_name = metadata.get("name", "unnamed")
        changes.append(
            UnifiedChange(
                source_file=name,
                tool="kubernetes",
                resource_id=f"{kind}/{resource_name}",
                action="apply",
                summary=(
                    f"Kubernetes {kind} {resource_name} supplied as a standalone manifest; "
                    "previous cluster state is unknown, so the delta cannot be confirmed."
                ),
            )
        )
    return changes
