"""Blast radius analysis."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from parsers.base import UnifiedChange, is_non_mutating_action


class ImpactNode(BaseModel):
    service_id: str = Field(..., description="Stable service identifier")
    label: str = Field(..., description="Human-readable service label")
    depth: int = Field(..., description="0 for direct impact, 1+ for transitive impact")
    dependencies: list[str] = Field(
        default_factory=list,
        description="Upstream service ids this service depends on in topology context",
    )
    owners: list[str] = Field(
        default_factory=list,
        description="Owner labels declared for this topology service",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["dependencies"] = _text_list(normalized.get("dependencies"))
        normalized["owners"] = _text_list(normalized.get("owners"))
        return normalized


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
    context_source: dict[str, str | None] = Field(
        default_factory=lambda: {"type": None, "ref": None},
        description="Topology source metadata used for this blast-radius result",
    )
    freshness: dict[str, int | str | None] = Field(
        default_factory=lambda: {"updated_at": None, "age_days": None},
        description="Topology freshness metadata used for this blast-radius result",
    )
    context_state: str | None = Field(
        default="unknown",
        description="Topology context state: current, stale, missing, incomplete, conflicting, or unknown",
    )
    context_limitations: list[str] = Field(
        default_factory=list,
        description="Machine-readable topology context limitation labels",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_context(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if not isinstance(normalized.get("affected"), list):
            normalized["affected"] = []
        if not isinstance(normalized.get("context_source"), dict):
            normalized["context_source"] = {"type": None, "ref": None}
        if not isinstance(normalized.get("freshness"), dict):
            normalized["freshness"] = {"updated_at": None, "age_days": None}
        else:
            freshness = normalized["freshness"]
            updated_at = freshness.get("updated_at")
            age_days = freshness.get("age_days")
            normalized["freshness"] = {
                "updated_at": updated_at if isinstance(updated_at, str) else None,
                "age_days": age_days if isinstance(age_days, int | str) else None,
            }
        context_source = normalized.get("context_source")
        if isinstance(context_source, dict):
            normalized["context_source"] = {
                "type": _scalar_text_or_none(context_source.get("type")),
                "ref": _scalar_text_or_none(context_source.get("ref")),
            }
        context_state = normalized.get("context_state")
        if context_state is None or not isinstance(context_state, str):
            normalized["context_state"] = "unknown"
        normalized["context_limitations"] = _text_list(
            normalized.get("context_limitations")
        )
        return normalized


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _scalar_text_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int | float | bool):
        return str(value)
    return None


def _metadata_text(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _has_invalid_source_metadata(import_metadata: dict) -> bool:
    return any(
        key in import_metadata
        and import_metadata.get(key) is not None
        and not isinstance(import_metadata.get(key), str)
        for key in ("source_type", "source_ref")
    )


def _topology_import_metadata(topology: dict | None) -> dict:
    metadata = topology.get("metadata") if isinstance(topology, dict) else None
    if not isinstance(metadata, dict):
        return {}
    import_metadata = metadata.get("import")
    return import_metadata if isinstance(import_metadata, dict) else {}


def _context_source(topology: dict | None) -> dict[str, str | None]:
    import_metadata = _topology_import_metadata(topology)
    source_type = _metadata_text(import_metadata, "source_type")
    source_ref = _metadata_text(import_metadata, "source_ref")
    return {"type": source_type, "ref": source_ref}


def _topology_updated_at(topology: dict | None) -> str:
    return (
        str(topology.get("updated_at") or "").strip()
        if isinstance(topology, dict)
        else ""
    )


def _parse_topology_updated_at(updated_at_raw: str) -> datetime | None:
    if not updated_at_raw:
        return None
    try:
        updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return updated_at


def _freshness_payload(
    topology: dict | None, *, now: datetime | None = None
) -> dict[str, int | str | None]:
    updated_at_raw = _topology_updated_at(topology)
    if not updated_at_raw:
        return {"updated_at": None, "age_days": None}
    updated_at = _parse_topology_updated_at(updated_at_raw)
    if updated_at is None:
        return {"updated_at": updated_at_raw, "age_days": None}
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if updated_at > now:
        return {"updated_at": updated_at_raw, "age_days": None}
    age_days = (now - updated_at).days
    return {"updated_at": updated_at_raw, "age_days": age_days}


def _warning_text(warning: str | None) -> str:
    return str(warning or "").strip().lower()


def _base_context_limitations(
    topology: dict | None, warning: str | None, *, now: datetime | None = None
) -> list[str]:
    text = _warning_text(warning)
    limitations: list[str] = []
    if not topology:
        if any(
            token in text for token in ("validation failed", "circular", "duplicate")
        ):
            limitations.append("conflicting_topology")
        else:
            limitations.append("missing_topology")
    if any(token in text for token in ("stale", "last updated more than")):
        limitations.append("stale_topology")
    if any(
        token in text
        for token in (
            "validation failed",
            "circular",
            "duplicate",
            "conflict",
        )
    ):
        limitations.append("conflicting_topology")
    if topology and text:
        limitations.append("incomplete_topology")
    if topology:
        import_metadata = _topology_import_metadata(topology)
        context_source = _context_source(topology)
        if _has_invalid_source_metadata(import_metadata):
            limitations.append("invalid_topology_source")
        if not context_source["type"] or not context_source["ref"]:
            limitations.append("missing_topology_source")
        updated_at_raw = _topology_updated_at(topology)
        if not updated_at_raw:
            limitations.append("missing_topology_freshness")
        else:
            updated_at = _parse_topology_updated_at(updated_at_raw)
            comparison_now = now or datetime.now(UTC)
            if comparison_now.tzinfo is None:
                comparison_now = comparison_now.replace(tzinfo=UTC)
            if updated_at is None or updated_at > comparison_now:
                limitations.append("invalid_topology_freshness")
    import_warnings = _topology_import_metadata(topology).get("warnings", [])
    if isinstance(import_warnings, list) and import_warnings:
        limitations.append("incomplete_topology")
    seen: set[str] = set()
    unique: list[str] = []
    for limitation in limitations:
        if limitation in seen:
            continue
        seen.add(limitation)
        unique.append(limitation)
    return unique


def _context_state(limitations: list[str]) -> str:
    if "conflicting_topology" in limitations:
        return "conflicting"
    if "missing_topology" in limitations:
        return "missing"
    if "stale_topology" in limitations:
        return "stale"
    if (
        "incomplete_topology" in limitations
        or "missing_resource_mapping" in limitations
    ):
        return "incomplete"
    if limitations:
        return "incomplete"
    return "current"


def _service_owners(service: dict) -> list[str]:
    owners: list[str] = []
    owner_raw = service.get("owner")
    if isinstance(owner_raw, str):
        owner = owner_raw.strip()
        if owner:
            owners.append(owner)
    owners_raw = service.get("owners", [])
    owners.extend(_text_list(owners_raw))
    seen: set[str] = set()
    unique: list[str] = []
    for item in owners:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _service_id(service: dict) -> str:
    return str(service.get("id") or "").strip()


def _service_downstream_ids(service: dict) -> list[str]:
    downstream_raw = service.get("downstream", [])
    if not isinstance(downstream_raw, list):
        return []
    downstream_ids: list[str] = []
    seen: set[str] = set()
    for item in downstream_raw:
        downstream_id = str(item).strip()
        if not downstream_id or downstream_id in seen:
            continue
        seen.add(downstream_id)
        downstream_ids.append(downstream_id)
    return downstream_ids


def _service_resource_keys(service: dict) -> list[str]:
    resource_keys_raw = service.get("resource_keys", [])
    if not isinstance(resource_keys_raw, list):
        return []
    return [
        resource_key
        for resource_key in (str(item).strip() for item in resource_keys_raw)
        if resource_key
    ]


def compute_blast_radius(
    changes: list[UnifiedChange],
    topology: dict | None,
    warning: str | None = None,
    *,
    now: datetime | None = None,
) -> BlastRadiusResult:
    base_limitations = _base_context_limitations(topology, warning, now=now)
    context_source = _context_source(topology)
    freshness = _freshness_payload(topology, now=now)
    mutating_changes = [
        change for change in changes if not is_non_mutating_action(change.action)
    ]
    if not mutating_changes:
        return BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=warning,
            context_source=context_source,
            freshness=freshness,
            context_state=_context_state(base_limitations),
            context_limitations=base_limitations,
        )

    if not topology:
        return BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=warning or "Blast radius may be incomplete.",
            context_source=context_source,
            freshness=freshness,
            context_state=_context_state(base_limitations),
            context_limitations=base_limitations,
        )

    services_raw = topology.get("services", []) if isinstance(topology, dict) else []
    services = [
        service
        for service in services_raw
        if isinstance(service, dict) and _service_id(service)
    ]
    if not services:
        return BlastRadiusResult(
            affected=[],
            direct_count=0,
            transitive_count=0,
            warning=warning or "No topology services available.",
            context_source=context_source,
            freshness=freshness,
            context_state=_context_state(base_limitations or ["incomplete_topology"]),
            context_limitations=base_limitations or ["incomplete_topology"],
        )

    resource_to_service_ids: dict[str, list[str]] = {}
    service_by_id = {_service_id(service): service for service in services}
    upstream_by_service_id: dict[str, list[str]] = {
        service_id: [] for service_id in service_by_id
    }
    for service in services:
        source_service_id = _service_id(service)
        for downstream_id in _service_downstream_ids(service):
            if downstream_id in upstream_by_service_id:
                upstream_by_service_id[downstream_id].append(source_service_id)
    for service in services:
        service_id = _service_id(service)
        for resource_key in _service_resource_keys(service):
            resource_to_service_ids.setdefault(resource_key, []).append(service_id)

    queue: deque[tuple[str, int]] = deque()
    seen: set[str] = set()
    unmatched_resources: list[str] = []

    for change in mutating_changes:
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
                dependencies=upstream_by_service_id.get(service_id, []),
                owners=_service_owners(service),
            )
        )
        for downstream_id in _service_downstream_ids(service):
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
    limitations = list(base_limitations)
    if unmatched_resources and "missing_resource_mapping" not in limitations:
        limitations.append("missing_resource_mapping")

    return BlastRadiusResult(
        affected=affected,
        direct_count=direct_count,
        transitive_count=transitive_count,
        warning=warning,
        unmatched_resources=sorted(set(unmatched_resources)),
        context_source=context_source,
        freshness=freshness,
        context_state=_context_state(limitations),
        context_limitations=limitations,
    )
