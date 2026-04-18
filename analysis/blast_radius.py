"""Blast radius analysis."""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel, Field

from parsers.base import UnifiedChange


class ImpactNode(BaseModel):
    service_id: str = Field(..., description="Stable service identifier")
    label: str = Field(..., description="Human-readable service label")
    depth: int = Field(..., description="0 for direct impact, 1+ for transitive impact")


class BlastRadiusResult(BaseModel):
    affected: list[ImpactNode] = Field(
        default_factory=list, description="Affected services"
    )
    direct_count: int = Field(..., description="Count of directly affected services")
    transitive_count: int = Field(
        ..., description="Count of transitively affected services"
    )
    warning: str | None = Field(
        default=None, description="Warning when impact may be incomplete"
    )
    unmatched_resources: list[str] = Field(
        default_factory=list, description="Resources not found in topology context"
    )


def compute_blast_radius(
    changes: list[UnifiedChange], topology: dict | None, warning: str | None = None
) -> BlastRadiusResult:
    if not topology:
        return BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=warning or "Blast radius may be incomplete.",
        )

    services = topology.get("services", []) if isinstance(topology, dict) else []
    if not services:
        return BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=warning or "No topology services available.",
        )

    resource_to_service_ids: dict[str, list[str]] = {}
    service_by_id = {service["id"]: service for service in services}
    for service in services:
        for resource_key in service.get("resource_keys", []):
            resource_to_service_ids.setdefault(resource_key, []).append(service["id"])

    queue: deque[tuple[str, int]] = deque()
    seen: set[str] = set()
    unmatched_resources: list[str] = []

    for change in changes:
        matched_service_ids = resource_to_service_ids.get(change.resource_id, [])
        if not matched_service_ids:
            unmatched_resources.append(change.resource_id)
        for service_id in matched_service_ids:
            if service_id not in seen:
                seen.add(service_id)
                queue.append((service_id, 0))

    affected: list[ImpactNode] = []
    while queue:
        service_id, depth = queue.popleft()
        service = service_by_id.get(service_id)
        if service is None:
            continue
        affected.append(
            ImpactNode(
                service_id=service_id,
                label=service.get("label", service_id),
                depth=depth,
            )
        )
        for downstream_id in service.get("downstream", []):
            if downstream_id in seen:
                continue
            seen.add(downstream_id)
            queue.append((downstream_id, depth + 1))

    direct_count = sum(1 for node in affected if node.depth == 0)
    transitive_count = sum(1 for node in affected if node.depth > 0)

    if unmatched_resources:
        unmatched_summary = ", ".join(sorted(set(unmatched_resources)))
        missing_context_warning = f"Blast radius may be incomplete — no topology mapping found for: {unmatched_summary}."
        if warning:
            warning = f"{warning} {missing_context_warning}"
        else:
            warning = missing_context_warning
    elif not affected and warning is None:
        warning = "No downstream dependencies found for the analyzed resources."

    return BlastRadiusResult(
        affected=affected,
        direct_count=direct_count,
        transitive_count=transitive_count,
        warning=warning,
        unmatched_resources=sorted(set(unmatched_resources)),
    )
