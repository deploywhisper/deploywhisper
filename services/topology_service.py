"""Topology workflow orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError
from pathlib import Path

from pydantic import BaseModel, Field

from config import settings

STALE_AFTER_DAYS = 30


class TopologyStatus(BaseModel):
    """Summary of the active topology context."""

    payload: dict | None = Field(default=None, description="Active topology payload when available")
    path: str = Field(..., description="Configured topology file path")
    exists: bool = Field(default=False, description="Whether the configured file exists")
    updated_at: str | None = Field(default=None, description="ISO timestamp describing the active topology recency")
    service_count: int = Field(default=0, description="Number of services in the active topology")
    dependency_count: int = Field(default=0, description="Number of downstream edges in the topology")
    resource_key_count: int = Field(default=0, description="Number of mapped resource keys across services")
    preview_services: list[str] = Field(default_factory=list, description="Short label preview for admin confirmation")
    warnings: list[str] = Field(default_factory=list, description="Warnings describing stale or incomplete topology context")
    blocking_errors: list[str] = Field(default_factory=list, description="Validation errors that make the topology unsafe to activate")


def _topology_path() -> Path:
    return Path(settings.topology_path)


def _parse_updated_at(updated_at_raw: str | None, warnings: list[str]) -> str | None:
    if not updated_at_raw:
        warnings.append("Blast radius may be incomplete — topology update timestamp is missing.")
        return None

    try:
        updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
    except ValueError:
        warnings.append("Blast radius may be incomplete — topology update timestamp is invalid.")
        return None

    if datetime.now(UTC) - updated_at > timedelta(days=STALE_AFTER_DAYS):
        warnings.append(
            f"Blast radius may be incomplete — service topology was last updated more than {STALE_AFTER_DAYS} days ago."
        )
    return updated_at_raw


def _find_cycle(service_graph: dict[str, list[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    trail: list[str] = []

    def visit(service_id: str) -> list[str]:
        visiting.add(service_id)
        trail.append(service_id)
        for downstream_id in service_graph.get(service_id, []):
            if downstream_id not in service_graph:
                continue
            if downstream_id in visiting:
                cycle_start = trail.index(downstream_id)
                return trail[cycle_start:] + [downstream_id]
            if downstream_id in visited:
                continue
            cycle = visit(downstream_id)
            if cycle:
                return cycle
        trail.pop()
        visiting.remove(service_id)
        visited.add(service_id)
        return []

    for service_id in service_graph:
        if service_id in visited:
            continue
        cycle = visit(service_id)
        if cycle:
            return cycle
    return []


def _build_topology_status(payload: dict, *, path: Path, exists: bool) -> TopologyStatus:
    warnings: list[str] = []
    blocking_errors: list[str] = []
    services_raw = payload.get("services", [])
    if not isinstance(services_raw, list):
        blocking_errors.append("Topology validation failed — services must be a list.")
        services_raw = []

    preview_services: list[str] = []
    seen_ids: set[str] = set()
    inbound_service_ids: set[str] = set()
    missing_refs: set[str] = set()
    service_graph: dict[str, list[str]] = {}
    dependency_count = 0
    resource_key_count = 0

    for index, service in enumerate(services_raw, start=1):
        if not isinstance(service, dict):
            blocking_errors.append(f"Topology validation failed — service entry {index} is not a JSON object.")
            continue

        service_id = str(service.get("id", "")).strip()
        if not service_id:
            blocking_errors.append(f"Topology validation failed — service entry {index} is missing an id.")
            continue
        if service_id in seen_ids:
            blocking_errors.append(f"Topology validation failed — duplicate service id '{service_id}' was provided.")
            continue

        seen_ids.add(service_id)
        preview_services.append(str(service.get("label") or service_id))

        resource_keys = service.get("resource_keys", [])
        if not isinstance(resource_keys, list):
            blocking_errors.append(f"Topology validation failed — service '{service_id}' has non-list resource_keys.")
            resource_keys = []
        valid_resource_keys = [str(resource_key).strip() for resource_key in resource_keys if str(resource_key).strip()]
        resource_key_count += len(valid_resource_keys)

        downstream = service.get("downstream", [])
        if not isinstance(downstream, list):
            blocking_errors.append(f"Topology validation failed — service '{service_id}' has non-list downstream targets.")
            downstream = []
        valid_downstream = [str(target).strip() for target in downstream if str(target).strip()]
        service_graph[service_id] = valid_downstream
        dependency_count += len(valid_downstream)
        for downstream_id in valid_downstream:
            inbound_service_ids.add(downstream_id)

    missing_refs = {downstream_id for downstream in service_graph.values() for downstream_id in downstream if downstream_id not in seen_ids}
    if missing_refs:
        blocking_errors.append(
            "Topology validation failed — missing downstream services referenced by topology: "
            + ", ".join(sorted(missing_refs))
            + "."
        )

    orphaned = sorted(
        service_id
        for service_id, downstream in service_graph.items()
        if len(service_graph) > 1 and not downstream and service_id not in inbound_service_ids
    )
    if orphaned:
        warnings.append(
            "Topology validation warning — orphaned services with no upstream or downstream links: "
            + ", ".join(orphaned)
            + "."
        )

    cycle = _find_cycle(service_graph)
    if cycle:
        blocking_errors.append("Topology validation failed — circular dependency detected: " + " -> ".join(cycle) + ".")

    updated_at = _parse_updated_at(payload.get("updated_at"), warnings)

    return TopologyStatus(
        payload=payload,
        path=str(path),
        exists=exists,
        updated_at=updated_at,
        service_count=len(seen_ids),
        dependency_count=dependency_count,
        resource_key_count=resource_key_count,
        preview_services=preview_services[:5],
        warnings=warnings,
        blocking_errors=blocking_errors,
    )


def get_topology_status() -> TopologyStatus:
    """Return the active topology context with validation details for admin workflows."""
    topology_path = _topology_path()
    if not topology_path.exists():
        return TopologyStatus(
            path=str(topology_path),
            exists=False,
            warnings=["Blast radius may be incomplete — service topology is not configured."],
        )

    try:
        payload = json.loads(topology_path.read_text(encoding="utf-8"))
    except JSONDecodeError:
        return TopologyStatus(
            path=str(topology_path),
            exists=True,
            blocking_errors=["Topology validation failed — active topology JSON is invalid."],
        )

    if not isinstance(payload, dict):
        return TopologyStatus(
            path=str(topology_path),
            exists=True,
            blocking_errors=["Topology validation failed — active topology must be a JSON object."],
        )
    return _build_topology_status(payload, path=topology_path, exists=True)


def save_topology_definition(raw_text: str) -> TopologyStatus:
    """Persist topology input as the active blast-radius context and return validation feedback."""
    try:
        payload = json.loads(raw_text)
    except JSONDecodeError as exc:
        raise ValueError("Topology definition must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Topology definition must be a JSON object.")

    topology_path = _topology_path()
    payload["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    candidate_status = _build_topology_status(payload, path=topology_path, exists=False)
    if candidate_status.blocking_errors:
        raise ValueError(" ".join(candidate_status.blocking_errors))
    topology_path.parent.mkdir(parents=True, exist_ok=True)
    topology_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return get_topology_status()


def _join_warnings(warnings: list[str]) -> str | None:
    if not warnings:
        return None
    return " ".join(warnings)


def load_topology() -> tuple[dict | None, str | None]:
    """Load topology context and return an optional warning."""
    status = get_topology_status()
    messages = status.blocking_errors + status.warnings
    return status.payload, _join_warnings(messages)
