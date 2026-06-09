"""Topology workflow orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from config import settings
from models.database import SessionLocal
from models.repositories.settings import get_setting, upsert_setting
from models.tables import TopologyVersion
from services.project_service import (
    build_project_payload,
    build_workspace_payload,
    list_projects,
    resolve_project_reference,
    resolve_workspace_reference,
)
from services.settings_service import get_topology_drift_check_interval_hours

STALE_AFTER_DAYS = 30
TOPOLOGY_DRIFT_ALERT_THRESHOLD_PERCENT = 10.0


class TopologyImportError(ValueError):
    """Raised when a topology import cannot proceed."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class TopologyDriftStatus(BaseModel):
    """Summary of the latest topology drift check for one project."""

    status: Literal["up_to_date", "drifted", "unsupported", "unavailable"] = Field(
        default="unavailable"
    )
    checked_at: str | None = Field(
        default=None, description="ISO timestamp for the latest drift check"
    )
    next_check_at: str | None = Field(
        default=None, description="ISO timestamp for the next scheduled drift check"
    )
    interval_hours: int = Field(
        default=24, description="Configured drift check cadence in hours"
    )
    source_type: str | None = Field(
        default=None, description="Imported topology source identifier when available"
    )
    source_ref: str | None = Field(
        default=None, description="Imported topology source reference when available"
    )
    total_resource_count: int = Field(
        default=0, description="Total resources considered during the drift check"
    )
    changed_resource_count: int = Field(
        default=0, description="Number of changed resources in the latest drift check"
    )
    change_percent: float = Field(
        default=0.0, description="Percentage of changed resources"
    )
    alert: bool = Field(
        default=False,
        description="Whether the drift report exceeds the alert threshold",
    )
    added_resources: list[str] = Field(default_factory=list)
    removed_resources: list[str] = Field(default_factory=list)
    modified_resources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TopologyDriftData(BaseModel):
    """API/UI-facing drift payload nested under topology status."""

    status: str = Field(..., description="Current drift state label")
    checked_at: str | None = Field(
        default=None, description="ISO timestamp for the latest drift check"
    )
    next_check_at: str | None = Field(
        default=None, description="ISO timestamp for the next scheduled drift check"
    )
    interval_hours: int = Field(
        default=24, description="Configured drift check cadence in hours"
    )
    source_type: str | None = Field(
        default=None, description="Imported topology source identifier when available"
    )
    source_ref: str | None = Field(
        default=None, description="Imported topology source reference when available"
    )
    total_resource_count: int = Field(
        default=0, description="Total resources considered during the drift check"
    )
    changed_resource_count: int = Field(
        default=0, description="Number of changed resources in the latest drift check"
    )
    change_percent: float = Field(
        default=0.0, description="Percentage of changed resources"
    )
    alert: bool = Field(
        default=False,
        description="Whether the drift report exceeds the alert threshold",
    )
    added_resources: list[str] = Field(default_factory=list)
    removed_resources: list[str] = Field(default_factory=list)
    modified_resources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TopologyStatus(BaseModel):
    """Summary of the active topology context."""

    payload: dict | None = Field(
        default=None, description="Active topology payload when available"
    )
    path: str = Field(..., description="Configured topology file path")
    exists: bool = Field(
        default=False, description="Whether the configured file exists"
    )
    updated_at: str | None = Field(
        default=None, description="ISO timestamp describing the active topology recency"
    )
    service_count: int = Field(
        default=0, description="Number of services in the active topology"
    )
    dependency_count: int = Field(
        default=0, description="Number of downstream edges in the topology"
    )
    resource_key_count: int = Field(
        default=0, description="Number of mapped resource keys across services"
    )
    preview_services: list[str] = Field(
        default_factory=list, description="Short label preview for admin confirmation"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings describing stale or incomplete topology context",
    )
    blocking_errors: list[str] = Field(
        default_factory=list,
        description="Validation errors that make the topology unsafe to activate",
    )
    drift: TopologyDriftStatus | None = Field(
        default=None, description="Latest topology drift check summary when available"
    )


class TopologyImportResource(BaseModel):
    """One normalized resource outcome produced during topology import."""

    resource_ref: str = Field(..., description="Stable resource or service reference")
    service_id: str | None = Field(
        default=None, description="Owning service id when available"
    )
    message: str = Field(..., description="Operator-facing import note")


class TopologyImportDiff(BaseModel):
    """Normalized topology diff for one import run."""

    added_services: list[str] = Field(default_factory=list)
    removed_services: list[str] = Field(default_factory=list)
    changed_services: list[str] = Field(default_factory=list)


class TopologyImportResult(BaseModel):
    """Typed import result returned to CLI and future integrations."""

    source_type: str = Field(..., description="Selected topology source identifier")
    source_ref: str = Field(..., description="Source path or URI reference")
    applied: bool = Field(
        default=False,
        description="Whether the import updated the active topology graph",
    )
    warnings: list[str] = Field(default_factory=list)
    accepted_resources: list[TopologyImportResource] = Field(default_factory=list)
    skipped_resources: list[TopologyImportResource] = Field(default_factory=list)
    partially_parsed_resources: list[TopologyImportResource] = Field(
        default_factory=list
    )
    unsupported_resources: list[TopologyImportResource] = Field(default_factory=list)
    diff: TopologyImportDiff = Field(default_factory=TopologyImportDiff)


class TopologyChangeSet(BaseModel):
    """Normalized topology update contract shared across source handlers."""

    operation: Literal["noop", "replace"] = Field(default="replace")
    services: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    accepted_resources: list[TopologyImportResource] = Field(default_factory=list)
    skipped_resources: list[TopologyImportResource] = Field(default_factory=list)
    partially_parsed_resources: list[TopologyImportResource] = Field(
        default_factory=list
    )
    unsupported_resources: list[TopologyImportResource] = Field(default_factory=list)


TopologySourceHandler = Callable[[str], TopologyChangeSet]


def _topology_path() -> Path:
    return Path(settings.topology_path)


def _topology_scope_path(project: dict, workspace: dict | None = None) -> Path:
    if workspace is None:
        return Path(f"project://{project['project_key']}/topology/latest")
    return Path(
        f"project://{project['project_key']}/{workspace['workspace_key']}/topology/latest"
    )


def _invalid_stored_topology_status(path: Path, message: str) -> TopologyStatus:
    return TopologyStatus(
        path=str(path),
        exists=True,
        blocking_errors=[message],
    )


def _unique_messages(messages: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for message in messages:
        normalized = str(message or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _import_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    import_metadata = metadata.get("import")
    if not isinstance(import_metadata, dict):
        return {}
    return import_metadata


def _extract_import_warnings(payload: dict[str, Any]) -> list[str]:
    import_metadata = _import_metadata(payload)
    warnings = import_metadata.get("warnings", [])
    if not isinstance(warnings, list):
        return []
    return _unique_messages([str(item) for item in warnings])


def _owner_labels(raw_owners: Any) -> tuple[list[str], bool]:
    if raw_owners is None:
        return [], False
    if not isinstance(raw_owners, list):
        return [], True
    labels: list[str] = []
    malformed = False
    for owner in raw_owners:
        if isinstance(owner, str):
            label = owner.strip()
            if label:
                labels.append(label)
        elif owner is not None:
            malformed = True
    return labels, malformed


def _resource_snapshot(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not payload:
        return {}
    snapshot: dict[str, dict[str, Any]] = {}
    services_raw = payload.get("services", [])
    if not isinstance(services_raw, list):
        return {}
    for service in services_raw:
        if not isinstance(service, dict):
            continue
        service_id = str(service.get("id") or "").strip()
        if not service_id:
            continue
        resource_keys_raw = service.get("resource_keys", [])
        resource_keys = [
            str(resource_key).strip()
            for resource_key in resource_keys_raw
            if str(resource_key).strip()
        ]
        if not resource_keys:
            resource_keys = [f"service:{service_id}"]
        owners, _ = _owner_labels(service.get("owners", []))
        signature = {
            "service_id": service_id,
            "label": str(service.get("label") or service_id),
            "owner": str(service.get("owner") or ""),
            "owners": sorted(owners),
            "downstream": sorted(
                str(target).strip()
                for target in service.get("downstream", [])
                if str(target).strip()
            ),
        }
        for resource_key in resource_keys:
            snapshot[resource_key] = signature
    return snapshot


def _drift_setting_key(
    project: dict[str, Any], workspace: dict[str, Any] | None = None
) -> str:
    if workspace is None:
        return f"topology_drift_status::{project['id']}"
    return f"topology_drift_status::{project['id']}::{workspace['id']}"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_next_check_at(checked_at: str | None, interval_hours: int) -> str | None:
    checked_at_dt = _parse_iso_datetime(checked_at)
    if checked_at_dt is None:
        return None
    return (
        (checked_at_dt + timedelta(hours=interval_hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_cached_topology_drift(
    project: dict[str, Any], workspace: dict[str, Any] | None = None
) -> TopologyDriftStatus | None:
    with SessionLocal() as session:
        record = get_setting(session, _drift_setting_key(project, workspace))
    if record is None:
        return None
    try:
        payload = json.loads(record.value)
    except JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return TopologyDriftStatus(**payload)


def _save_topology_drift(
    project: dict[str, Any],
    drift_status: TopologyDriftStatus,
    workspace: dict[str, Any] | None = None,
) -> TopologyDriftStatus:
    with SessionLocal() as session:
        upsert_setting(
            session,
            key=_drift_setting_key(project, workspace),
            value=json.dumps(drift_status.model_dump()),
        )
    return drift_status


def _is_drift_check_due(
    cached_status: TopologyDriftStatus | None, interval_hours: int
) -> bool:
    if cached_status is None:
        return True
    checked_at = _parse_iso_datetime(cached_status.checked_at)
    if checked_at is None:
        return True
    return datetime.now(UTC) >= checked_at + timedelta(hours=interval_hours)


def _build_drift_status(
    *,
    status: Literal["up_to_date", "drifted", "unsupported", "unavailable"],
    interval_hours: int,
    source_type: str | None,
    source_ref: str | None,
    total_resource_count: int = 0,
    added_resources: list[str] | None = None,
    removed_resources: list[str] | None = None,
    modified_resources: list[str] | None = None,
    warnings: list[str] | None = None,
) -> TopologyDriftStatus:
    checked_at = _current_timestamp()
    added = sorted(added_resources or [])
    removed = sorted(removed_resources or [])
    modified = sorted(modified_resources or [])
    changed_count = len(added) + len(removed) + len(modified)
    total = max(total_resource_count, len(added) + len(removed) + len(modified))
    change_percent = 0.0 if total == 0 else (changed_count / total) * 100.0
    alert = change_percent > TOPOLOGY_DRIFT_ALERT_THRESHOLD_PERCENT
    drift_warnings = list(warnings or [])
    if status == "drifted":
        threshold_text = "above" if alert else "within"
        drift_warnings.append(
            f"Topology drift detected — {change_percent:.1f}% of resources changed since the last import, {threshold_text} the {TOPOLOGY_DRIFT_ALERT_THRESHOLD_PERCENT:.0f}% alert threshold."
        )
    return TopologyDriftStatus(
        status=status,
        checked_at=checked_at,
        next_check_at=_build_next_check_at(checked_at, interval_hours),
        interval_hours=interval_hours,
        source_type=source_type,
        source_ref=source_ref,
        total_resource_count=total_resource_count,
        changed_resource_count=changed_count,
        change_percent=round(change_percent, 2),
        alert=alert,
        added_resources=added,
        removed_resources=removed,
        modified_resources=modified,
        warnings=_unique_messages(drift_warnings),
    )


def run_due_topology_drift_checks() -> list[TopologyDriftStatus]:
    """Run due topology drift checks for every known project."""
    drift_statuses: list[TopologyDriftStatus] = []
    for project in list_projects():
        drift_statuses.append(check_topology_drift(project_id=project.id))
    return drift_statuses


def _load_latest_topology_payload(
    project: dict,
    workspace: dict | None = None,
) -> tuple[dict | None, Path, TopologyStatus | None]:
    topology_path = _topology_scope_path(project, workspace)
    with SessionLocal() as session:
        stmt = session.query(TopologyVersion).filter(
            TopologyVersion.project_id == int(project["id"])
        )
        if workspace is None:
            stmt = stmt.filter(TopologyVersion.workspace_id.is_(None))
        else:
            stmt = stmt.filter(TopologyVersion.workspace_id == int(workspace["id"]))
        record = stmt.order_by(TopologyVersion.id.desc()).first()
        if record is None:
            if bool(project.get("is_default")):
                legacy_status = _read_legacy_topology_status()
                if legacy_status is not None:
                    return (
                        legacy_status.payload,
                        Path(legacy_status.path),
                        legacy_status,
                    )
            return None, topology_path, None
        try:
            payload = json.loads(record.payload_json or "{}")
        except JSONDecodeError:
            return (
                None,
                topology_path,
                _invalid_stored_topology_status(
                    topology_path,
                    "Topology validation failed — stored topology JSON is invalid.",
                ),
            )
        if not isinstance(payload, dict):
            return (
                None,
                topology_path,
                _invalid_stored_topology_status(
                    topology_path,
                    "Topology validation failed — stored topology must be a JSON object.",
                ),
            )
        return payload, topology_path, None


def _read_legacy_topology_status() -> TopologyStatus | None:
    legacy_path = _topology_path()
    if not legacy_path.exists():
        return None
    try:
        payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError):
        return TopologyStatus(
            path=str(legacy_path),
            exists=legacy_path.exists(),
            blocking_errors=[
                "Topology validation failed — active topology JSON is invalid."
            ],
        )
    if not isinstance(payload, dict):
        return TopologyStatus(
            path=str(legacy_path),
            exists=True,
            blocking_errors=[
                "Topology validation failed — active topology must be a JSON object."
            ],
        )
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    import_metadata = metadata.get("import")
    if not isinstance(import_metadata, dict):
        import_metadata = {}
    import_metadata.setdefault("source_type", "legacy-file")
    import_metadata.setdefault("source_ref", str(legacy_path))
    metadata["import"] = import_metadata
    payload = {**payload, "metadata": metadata}
    return _build_topology_status(payload, path=legacy_path, exists=True)


def _parse_updated_at(updated_at_raw: str | None, warnings: list[str]) -> str | None:
    if not updated_at_raw:
        warnings.append(
            "Blast radius may be incomplete — topology update timestamp is missing."
        )
        return None

    try:
        updated_at = datetime.fromisoformat(updated_at_raw.replace("Z", "+00:00"))
    except ValueError:
        warnings.append(
            "Blast radius may be incomplete — topology update timestamp is invalid."
        )
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


def _build_topology_status(
    payload: dict[str, Any], *, path: Path, exists: bool
) -> TopologyStatus:
    warnings = list(_extract_import_warnings(payload))
    blocking_errors: list[str] = []
    services_raw = payload.get("services", [])
    if not isinstance(services_raw, list):
        blocking_errors.append("Topology validation failed — services must be a list.")
        services_raw = []

    preview_services: list[str] = []
    seen_ids: set[str] = set()
    inbound_service_ids: set[str] = set()
    service_graph: dict[str, list[str]] = {}
    dependency_count = 0
    resource_key_count = 0

    for index, service in enumerate(services_raw, start=1):
        if not isinstance(service, dict):
            blocking_errors.append(
                f"Topology validation failed — service entry {index} is not a JSON object."
            )
            continue

        service_id = str(service.get("id", "")).strip()
        if not service_id:
            blocking_errors.append(
                f"Topology validation failed — service entry {index} is missing an id."
            )
            continue
        if service_id in seen_ids:
            blocking_errors.append(
                f"Topology validation failed — duplicate service id '{service_id}' was provided."
            )
            continue

        seen_ids.add(service_id)
        preview_services.append(str(service.get("label") or service_id))

        resource_keys = service.get("resource_keys", [])
        if not isinstance(resource_keys, list):
            blocking_errors.append(
                f"Topology validation failed — service '{service_id}' has non-list resource_keys."
            )
            resource_keys = []
        valid_resource_keys = [
            str(resource_key).strip()
            for resource_key in resource_keys
            if str(resource_key).strip()
        ]
        resource_key_count += len(valid_resource_keys)

        downstream = service.get("downstream", [])
        if not isinstance(downstream, list):
            blocking_errors.append(
                f"Topology validation failed — service '{service_id}' has non-list downstream targets."
            )
            downstream = []
        valid_downstream = [
            str(target).strip() for target in downstream if str(target).strip()
        ]
        service_graph[service_id] = valid_downstream
        dependency_count += len(valid_downstream)
        for downstream_id in valid_downstream:
            inbound_service_ids.add(downstream_id)

    missing_refs = {
        downstream_id
        for downstream in service_graph.values()
        for downstream_id in downstream
        if downstream_id not in seen_ids
    }
    if missing_refs:
        blocking_errors.append(
            "Topology validation failed — missing downstream services referenced by topology: "
            + ", ".join(sorted(missing_refs))
            + "."
        )

    orphaned = sorted(
        service_id
        for service_id, downstream in service_graph.items()
        if len(service_graph) > 1
        and not downstream
        and service_id not in inbound_service_ids
    )
    if orphaned:
        warnings.append(
            "Topology validation warning — orphaned services with no upstream or downstream links: "
            + ", ".join(orphaned)
            + "."
        )

    cycle = _find_cycle(service_graph)
    if cycle:
        blocking_errors.append(
            "Topology validation failed — circular dependency detected: "
            + " -> ".join(cycle)
            + "."
        )

    updated_at = _parse_updated_at(str(payload.get("updated_at") or ""), warnings)

    return TopologyStatus(
        payload=payload,
        path=str(path),
        exists=exists,
        updated_at=updated_at,
        service_count=len(seen_ids),
        dependency_count=dependency_count,
        resource_key_count=resource_key_count,
        preview_services=preview_services[:5],
        warnings=_unique_messages(warnings),
        blocking_errors=blocking_errors,
    )


def _join_warnings(warnings: list[str]) -> str | None:
    if not warnings:
        return None
    return " ".join(warnings)


def _resource_ref_from_service(service_id: str, resource_keys: list[str]) -> str:
    if resource_keys:
        return resource_keys[0]
    return f"service:{service_id}"


def _parse_custom_source(source_ref: str) -> TopologyChangeSet:
    path = Path(source_ref)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TopologyImportError(
            "topology_read_failed",
            "Topology source could not be read.",
            details={"path": str(path), "reason": str(exc)},
        ) from exc
    except JSONDecodeError as exc:
        raise TopologyImportError(
            "invalid_topology_definition",
            "Topology source must be valid JSON.",
            details={"path": str(path)},
        ) from exc

    if not isinstance(payload, dict):
        raise TopologyImportError(
            "invalid_topology_definition",
            "Topology source must be a JSON object.",
            details={"path": str(path)},
        )
    return _build_custom_change_set(payload)


def _terraform_state_unavailable_change_set(
    source_ref: str, message: str
) -> TopologyChangeSet:
    return TopologyChangeSet(
        operation="noop",
        warnings=[message],
        unsupported_resources=[
            TopologyImportResource(
                resource_ref=source_ref,
                message=message,
            )
        ],
    )


def _terraform_state_resource_address(resource: dict[str, Any]) -> str:
    address = str(resource.get("address") or "").strip()
    if address:
        return address
    resource_type = str(resource.get("type") or "").strip()
    resource_name = str(resource.get("name") or "").strip()
    if not resource_type or not resource_name:
        return ""
    prefix = str(resource.get("module") or "").strip()
    if str(resource.get("mode") or "").strip() == "data":
        resource_ref = f"data.{resource_type}.{resource_name}"
    else:
        resource_ref = f"{resource_type}.{resource_name}"
    if prefix:
        return f"{prefix}.{resource_ref}"
    return resource_ref


def _terraform_state_identity_keys(
    address: str, resource: dict[str, Any], instances: list[Any]
) -> list[str]:
    keys = [address]
    for field in ("provider", "type"):
        value = str(resource.get(field) or "").strip()
        if value:
            keys.append(value)
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        index_key = instance.get("index_key")
        if index_key is not None:
            if isinstance(index_key, str):
                keys.append(f"{address}[{json.dumps(index_key)}]")
            else:
                keys.append(f"{address}[{index_key}]")
        attributes = instance.get("attributes")
        if not isinstance(attributes, dict):
            continue
        for field in ("id", "arn", "name", "resource_id", "self_link"):
            value = attributes.get(field)
            if isinstance(value, str) and value.strip():
                keys.append(value.strip())
    seen: set[str] = set()
    unique: list[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        unique.append(key)
    return unique


def _terraform_state_dependency_refs(instances: list[Any]) -> list[str]:
    dependencies: list[str] = []
    for instance in instances:
        if not isinstance(instance, dict):
            continue
        raw_dependencies = instance.get("dependencies", [])
        if not isinstance(raw_dependencies, list):
            continue
        for dependency in raw_dependencies:
            dependency_ref = str(dependency or "").strip()
            if dependency_ref:
                dependencies.append(dependency_ref)
    return sorted(set(dependencies))


def _terraform_state_staleness_warning(path: Path) -> str | None:
    try:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return None
    if datetime.now(UTC) - modified_at <= timedelta(days=STALE_AFTER_DAYS):
        return None
    return f"Terraform state context is stale — state file was last modified more than {STALE_AFTER_DAYS} days ago."


def _parse_terraform_state_source(source_ref: str) -> TopologyChangeSet:
    path = Path(source_ref)
    if not path.is_file():
        return _terraform_state_unavailable_change_set(
            source_ref,
            "Terraform state context is unavailable because the source is not a readable local state file; no topology changes were applied.",
        )
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError:
        return _terraform_state_unavailable_change_set(
            source_ref,
            "Terraform state context is unavailable; no topology changes were applied.",
        )
    try:
        payload = json.loads(raw_text)
    except JSONDecodeError:
        return _terraform_state_unavailable_change_set(
            source_ref,
            "Terraform state context is unavailable because the state file is not valid JSON; no topology changes were applied.",
        )
    if not isinstance(payload, dict):
        return _terraform_state_unavailable_change_set(
            source_ref,
            "Terraform state context is unavailable because the state file is not a JSON object; no topology changes were applied.",
        )
    if "resources" not in payload:
        return _terraform_state_unavailable_change_set(
            source_ref,
            "Terraform state context is unavailable because resources are missing; no topology changes were applied.",
        )
    resources_raw = payload.get("resources")
    if not isinstance(resources_raw, list):
        return _terraform_state_unavailable_change_set(
            source_ref,
            "Terraform state context is unavailable because resources are missing or malformed; no topology changes were applied.",
        )

    warnings: list[str] = []
    stale_warning = _terraform_state_staleness_warning(path)
    if stale_warning:
        warnings.append(stale_warning)
    services_by_id: dict[str, dict[str, Any]] = {}
    dependency_refs_by_service: dict[str, list[str]] = {}
    accepted_resources: list[TopologyImportResource] = []
    partially_parsed_resources: list[TopologyImportResource] = []
    skipped_resources: list[TopologyImportResource] = []

    for index, resource in enumerate(resources_raw, start=1):
        resource_ref = f"resources[{index}]"
        if not isinstance(resource, dict):
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=resource_ref,
                    message="Terraform state resource entry was not a JSON object and was ignored.",
                )
            )
            continue
        if str(resource.get("mode") or "managed").strip() == "data":
            skipped_resources.append(
                TopologyImportResource(
                    resource_ref=_terraform_state_resource_address(resource)
                    or resource_ref,
                    message="Terraform data source was skipped because it is not a managed infrastructure resource.",
                )
            )
            continue
        address = _terraform_state_resource_address(resource)
        if not address:
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=resource_ref,
                    message="Terraform state resource is missing type/name identity and was ignored.",
                )
            )
            continue
        if address in services_by_id:
            skipped_resources.append(
                TopologyImportResource(
                    resource_ref=address,
                    service_id=address,
                    message="Duplicate Terraform state resource address was skipped.",
                )
            )
            continue
        instances = resource.get("instances", [])
        if not isinstance(instances, list):
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=address,
                    service_id=address,
                    message="Terraform state resource instances were malformed and were ignored.",
                )
            )
            instances = []
        resource_keys = _terraform_state_identity_keys(address, resource, instances)
        services_by_id[address] = {
            "id": address,
            "label": address,
            "resource_keys": resource_keys,
            "downstream": [],
        }
        dependency_refs_by_service[address] = _terraform_state_dependency_refs(
            instances
        )
        accepted_resources.append(
            TopologyImportResource(
                resource_ref=address,
                service_id=address,
                message="Terraform state resource was mapped into the topology graph.",
            )
        )

    service_ids = set(services_by_id)
    for service_id, dependency_refs in dependency_refs_by_service.items():
        for dependency_ref in dependency_refs:
            if dependency_ref not in service_ids:
                partially_parsed_resources.append(
                    TopologyImportResource(
                        resource_ref=f"{service_id}->{dependency_ref}",
                        service_id=service_id,
                        message=(
                            f"Terraform dependency '{dependency_ref}' could not be resolved "
                            "inside the state and was dropped."
                        ),
                    )
                )
                continue
            services_by_id[dependency_ref]["downstream"].append(service_id)

    services = []
    for service_id in sorted(services_by_id):
        service = dict(services_by_id[service_id])
        service["downstream"] = sorted(set(service["downstream"]))
        services.append(service)

    if partially_parsed_resources:
        warnings.append(
            "Terraform state import partially parsed one or more resources; malformed entries or unresolved relationships were skipped."
        )
    if skipped_resources:
        warnings.append(
            "Terraform state import skipped data sources or duplicate resources while preserving managed infrastructure context."
        )
    if not accepted_resources and resources_raw:
        warnings.append(
            "Terraform state import did not produce any valid managed resources to apply."
        )
        return TopologyChangeSet(
            operation="noop",
            warnings=warnings,
            skipped_resources=skipped_resources,
            partially_parsed_resources=partially_parsed_resources,
        )

    return TopologyChangeSet(
        operation="replace",
        services=services,
        warnings=warnings,
        accepted_resources=accepted_resources,
        skipped_resources=skipped_resources,
        partially_parsed_resources=partially_parsed_resources,
    )


def _build_custom_change_set(payload: dict[str, Any]) -> TopologyChangeSet:
    services_raw = payload.get("services", [])
    if not isinstance(services_raw, list):
        raise TopologyImportError(
            "invalid_topology_definition",
            "Topology definition must provide services as a list.",
        )

    services: list[dict[str, Any]] = []
    seen_service_ids: set[str] = set()
    accepted_resources: list[TopologyImportResource] = []
    skipped_resources: list[TopologyImportResource] = []
    partially_parsed_resources: list[TopologyImportResource] = []

    for index, service in enumerate(services_raw, start=1):
        entry_ref = f"service[{index}]"
        if not isinstance(service, dict):
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=entry_ref,
                    message="Service entry was not a JSON object and was ignored.",
                )
            )
            continue

        service_id = str(service.get("id", "")).strip()
        if not service_id:
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=entry_ref,
                    message="Service entry is missing an id and was ignored.",
                )
            )
            continue

        resource_keys_raw = service.get("resource_keys", [])
        if not isinstance(resource_keys_raw, list):
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=service_id,
                    service_id=service_id,
                    message="Resource keys were malformed and were dropped.",
                )
            )
            resource_keys_raw = []
        resource_keys = [
            str(resource_key).strip()
            for resource_key in resource_keys_raw
            if str(resource_key).strip()
        ]

        if service_id in seen_service_ids:
            skipped_resources.append(
                TopologyImportResource(
                    resource_ref=_resource_ref_from_service(service_id, resource_keys),
                    service_id=service_id,
                    message="Duplicate service id was skipped.",
                )
            )
            continue

        downstream_raw = service.get("downstream", [])
        if not isinstance(downstream_raw, list):
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=service_id,
                    service_id=service_id,
                    message="Downstream targets were malformed and were dropped.",
                )
            )
            downstream_raw = []
        downstream = [
            str(target).strip() for target in downstream_raw if str(target).strip()
        ]
        owner_raw = service.get("owner")
        owner = ""
        if owner_raw is not None:
            if isinstance(owner_raw, str):
                owner = owner_raw.strip()
            else:
                partially_parsed_resources.append(
                    TopologyImportResource(
                        resource_ref=service_id,
                        service_id=service_id,
                        message="Owner label was malformed and was dropped.",
                    )
                )
        owners, malformed_owners = _owner_labels(service.get("owners", []))
        if malformed_owners:
            partially_parsed_resources.append(
                TopologyImportResource(
                    resource_ref=service_id,
                    service_id=service_id,
                    message="Owner labels were malformed and were dropped.",
                )
            )

        seen_service_ids.add(service_id)
        normalized_service = {
            "id": service_id,
            "label": str(service.get("label") or service_id),
            "resource_keys": resource_keys,
            "downstream": downstream,
        }
        if owner:
            normalized_service["owner"] = owner
        if owners:
            normalized_service["owners"] = owners
        services.append(normalized_service)

        if resource_keys:
            for resource_key in resource_keys:
                accepted_resources.append(
                    TopologyImportResource(
                        resource_ref=resource_key,
                        service_id=service_id,
                        message="Resource was mapped into the topology graph.",
                    )
                )
        else:
            accepted_resources.append(
                TopologyImportResource(
                    resource_ref=f"service:{service_id}",
                    service_id=service_id,
                    message="Service was mapped into the topology graph.",
                )
            )

    valid_service_ids = {service["id"] for service in services}
    normalized_services: list[dict[str, Any]] = []
    for service in services:
        valid_downstream: list[str] = []
        for downstream_id in service["downstream"]:
            if downstream_id not in valid_service_ids:
                partially_parsed_resources.append(
                    TopologyImportResource(
                        resource_ref=f"{service['id']}->{downstream_id}",
                        service_id=service["id"],
                        message=(
                            f"Downstream service '{downstream_id}' could not be resolved "
                            "and was dropped."
                        ),
                    )
                )
                continue
            valid_downstream.append(downstream_id)
        normalized_services.append({**service, "downstream": valid_downstream})

    warnings: list[str] = []
    if partially_parsed_resources:
        warnings.append(
            "Topology import partially parsed one or more resources; malformed entries or unresolved relationships were skipped."
        )
    if skipped_resources:
        warnings.append(
            "Topology import skipped duplicate services while preserving the first valid definition."
        )

    if not accepted_resources and services_raw:
        warnings.append("Topology import did not produce any valid services to apply.")
        return TopologyChangeSet(
            operation="noop",
            warnings=warnings,
            skipped_resources=skipped_resources,
            partially_parsed_resources=partially_parsed_resources,
        )

    return TopologyChangeSet(
        operation="replace",
        services=normalized_services,
        warnings=warnings,
        accepted_resources=accepted_resources,
        skipped_resources=skipped_resources,
        partially_parsed_resources=partially_parsed_resources,
    )


def _build_unimplemented_source_handler(source_type: str) -> TopologySourceHandler:
    def handler(source_ref: str) -> TopologyChangeSet:
        message = (
            f"Topology source '{source_type}' is registered but its connector is not implemented yet; "
            "no topology changes were applied."
        )
        return TopologyChangeSet(
            operation="noop",
            warnings=[message],
            unsupported_resources=[
                TopologyImportResource(
                    resource_ref=source_ref,
                    message=message,
                )
            ],
        )

    return handler


TOPOLOGY_SOURCE_REGISTRY: dict[str, TopologySourceHandler] = {
    "custom": _parse_custom_source,
    "terraform": _parse_terraform_state_source,
    "cloudformation": _build_unimplemented_source_handler("cloudformation"),
    "kubernetes": _build_unimplemented_source_handler("kubernetes"),
    "ansible": _build_unimplemented_source_handler("ansible"),
}


def _lookup_source_handler(source_type: str) -> TopologySourceHandler:
    normalized = str(source_type or "").strip().lower()
    handler = TOPOLOGY_SOURCE_REGISTRY.get(normalized)
    if handler is not None:
        return handler

    def unsupported_handler(source_ref: str) -> TopologyChangeSet:
        message = (
            f"Topology source '{normalized or 'unknown'}' is unsupported; "
            "no topology changes were applied."
        )
        return TopologyChangeSet(
            operation="noop",
            warnings=[message],
            unsupported_resources=[
                TopologyImportResource(
                    resource_ref=source_ref,
                    message=message,
                )
            ],
        )

    return unsupported_handler


def _current_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_payload_from_change_set(
    *,
    change_set: TopologyChangeSet,
    source_type: str,
    source_ref: str,
) -> dict[str, Any]:
    return {
        "updated_at": _current_timestamp(),
        "services": change_set.services,
        "metadata": {
            "import": {
                "source_type": source_type,
                "source_ref": source_ref,
                "warnings": change_set.warnings,
                "accepted_resources": [
                    item.model_dump() for item in change_set.accepted_resources
                ],
                "skipped_resources": [
                    item.model_dump() for item in change_set.skipped_resources
                ],
                "partially_parsed_resources": [
                    item.model_dump() for item in change_set.partially_parsed_resources
                ],
                "unsupported_resources": [
                    item.model_dump() for item in change_set.unsupported_resources
                ],
            }
        },
    }


def _build_legacy_mirror_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "metadata"}


def _persist_topology_payload(
    payload: dict[str, Any],
    *,
    project: dict[str, Any],
    workspace: dict[str, Any] | None,
    source_type: str,
) -> TopologyStatus:
    topology_path = _topology_scope_path(project, workspace)
    candidate_status = _build_topology_status(payload, path=topology_path, exists=False)
    if candidate_status.blocking_errors:
        raise TopologyImportError(
            "invalid_topology_definition",
            " ".join(candidate_status.blocking_errors),
            details={"path": str(topology_path)},
        )

    with SessionLocal() as session:
        if bool(project.get("is_default")) and workspace is None:
            legacy_path = _topology_path()
            try:
                legacy_path.parent.mkdir(parents=True, exist_ok=True)
                legacy_path.write_text(
                    json.dumps(_build_legacy_mirror_payload(payload), indent=2),
                    encoding="utf-8",
                )
            except OSError as exc:
                raise TopologyImportError(
                    "topology_write_failed",
                    "Topology definition could not be mirrored to the legacy topology file.",
                    details={"path": str(legacy_path), "reason": str(exc)},
                ) from exc
        session.add(
            TopologyVersion(
                project_id=int(project["id"]),
                workspace_id=int(workspace["id"]) if workspace is not None else None,
                source_type=source_type,
                payload_json=json.dumps(payload),
            )
        )
        session.commit()
    return get_topology_status(
        project_id=int(project["id"]),
        workspace_id=int(workspace["id"]) if workspace is not None else None,
    )


def _canonical_service(service: dict[str, Any]) -> dict[str, Any]:
    canonical = {
        "id": str(service.get("id") or "").strip(),
        "label": str(service.get("label") or "").strip(),
        "resource_keys": sorted(
            str(item).strip()
            for item in service.get("resource_keys", [])
            if str(item).strip()
        ),
        "downstream": sorted(
            str(item).strip()
            for item in service.get("downstream", [])
            if str(item).strip()
        ),
    }
    owner = str(service.get("owner") or "").strip()
    owners, _ = _owner_labels(service.get("owners", []))
    owners = sorted(owners)
    if owner:
        canonical["owner"] = owner
    if owners:
        canonical["owners"] = owners
    return canonical


def _build_topology_diff(
    before_payload: dict[str, Any] | None,
    after_payload: dict[str, Any] | None,
) -> TopologyImportDiff:
    before_services = before_payload.get("services", []) if before_payload else []
    after_services = after_payload.get("services", []) if after_payload else []

    before_map = {
        service["id"]: _canonical_service(service)
        for service in before_services
        if isinstance(service, dict) and str(service.get("id") or "").strip()
    }
    after_map = {
        service["id"]: _canonical_service(service)
        for service in after_services
        if isinstance(service, dict) and str(service.get("id") or "").strip()
    }

    added = sorted(
        service_id for service_id in after_map if service_id not in before_map
    )
    removed = sorted(
        service_id for service_id in before_map if service_id not in after_map
    )
    changed = sorted(
        service_id
        for service_id in before_map.keys() & after_map.keys()
        if before_map[service_id] != after_map[service_id]
    )
    return TopologyImportDiff(
        added_services=added,
        removed_services=removed,
        changed_services=changed,
    )


def _build_import_result(
    *,
    source_type: str,
    source_ref: str,
    applied: bool,
    change_set: TopologyChangeSet,
    before_payload: dict[str, Any] | None,
    after_payload: dict[str, Any] | None,
    warnings: list[str],
) -> TopologyImportResult:
    return TopologyImportResult(
        source_type=source_type,
        source_ref=source_ref,
        applied=applied,
        warnings=_unique_messages(warnings),
        accepted_resources=change_set.accepted_resources,
        skipped_resources=change_set.skipped_resources,
        partially_parsed_resources=change_set.partially_parsed_resources,
        unsupported_resources=change_set.unsupported_resources,
        diff=_build_topology_diff(before_payload, after_payload),
    )


def check_topology_drift(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
    force: bool = False,
) -> TopologyDriftStatus:
    """Run or reuse a scheduled topology drift check for one project."""
    interval_hours = get_topology_drift_check_interval_hours()
    project = build_project_payload(
        resolve_project_reference(project_id=project_id, project_key=project_key)
    )
    workspace_record = resolve_workspace_reference(
        project_id=int(project["id"]),
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    workspace = (
        build_workspace_payload(workspace_record)
        if workspace_record is not None
        else None
    )
    payload, _, status_override = _load_latest_topology_payload(project, workspace)
    import_metadata = _import_metadata(payload or {})
    source_type = str(import_metadata.get("source_type") or "").strip() or None
    source_ref = str(import_metadata.get("source_ref") or "").strip() or None
    cached_status = _load_cached_topology_drift(project, workspace)

    if not force and not _is_drift_check_due(cached_status, interval_hours):
        return cached_status or _build_drift_status(
            status="unavailable",
            interval_hours=interval_hours,
            source_type=source_type,
            source_ref=source_ref,
            warnings=["Topology drift check is unavailable."],
        )

    if payload is None or status_override is not None:
        return _save_topology_drift(
            project,
            _build_drift_status(
                status="unavailable",
                interval_hours=interval_hours,
                source_type=source_type,
                source_ref=source_ref,
                warnings=[
                    "Topology drift is unavailable because no valid topology import is active."
                ],
            ),
            workspace,
        )

    if not source_type or not source_ref:
        return _save_topology_drift(
            project,
            _build_drift_status(
                status="unavailable",
                interval_hours=interval_hours,
                source_type=source_type,
                source_ref=source_ref,
                warnings=[
                    "Topology drift is unavailable because the active topology does not include an import source reference."
                ],
            ),
            workspace,
        )

    if source_type == "manual":
        return _save_topology_drift(
            project,
            _build_drift_status(
                status="unavailable",
                interval_hours=interval_hours,
                source_type=source_type,
                source_ref=source_ref,
                warnings=[
                    "Topology drift is unavailable for manual topology uploads because there is no source connector to re-evaluate."
                ],
            ),
            workspace,
        )

    try:
        change_set = _lookup_source_handler(source_type)(source_ref)
    except TopologyImportError as exc:
        return _save_topology_drift(
            project,
            _build_drift_status(
                status="unavailable",
                interval_hours=interval_hours,
                source_type=source_type,
                source_ref=source_ref,
                warnings=[str(exc)],
            ),
            workspace,
        )

    if change_set.operation != "replace":
        return _save_topology_drift(
            project,
            _build_drift_status(
                status="unsupported",
                interval_hours=interval_hours,
                source_type=source_type,
                source_ref=source_ref,
                warnings=change_set.warnings
                or [
                    "Topology drift is not supported for the active source connector yet."
                ],
            ),
            workspace,
        )

    current_resources = _resource_snapshot(payload)
    candidate_payload = {"services": change_set.services}
    candidate_resources = _resource_snapshot(candidate_payload)
    added_resources = sorted(
        resource_ref
        for resource_ref in candidate_resources
        if resource_ref not in current_resources
    )
    removed_resources = sorted(
        resource_ref
        for resource_ref in current_resources
        if resource_ref not in candidate_resources
    )
    modified_resources = sorted(
        resource_ref
        for resource_ref in current_resources.keys() & candidate_resources.keys()
        if current_resources[resource_ref] != candidate_resources[resource_ref]
    )
    drift_status = _build_drift_status(
        status=(
            "drifted"
            if added_resources or removed_resources or modified_resources
            else "up_to_date"
        ),
        interval_hours=interval_hours,
        source_type=source_type,
        source_ref=source_ref,
        total_resource_count=max(len(current_resources), len(candidate_resources)),
        added_resources=added_resources,
        removed_resources=removed_resources,
        modified_resources=modified_resources,
        warnings=change_set.warnings,
    )
    return _save_topology_drift(project, drift_status, workspace)


def get_topology_status(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> TopologyStatus:
    """Return the active topology context with validation details for admin workflows."""
    project = build_project_payload(
        resolve_project_reference(project_id=project_id, project_key=project_key)
    )
    workspace_record = resolve_workspace_reference(
        project_id=int(project["id"]),
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    workspace = (
        build_workspace_payload(workspace_record)
        if workspace_record is not None
        else None
    )
    payload, topology_path, status_override = _load_latest_topology_payload(
        project, workspace
    )
    if status_override is not None and payload is None:
        return status_override
    if payload is None:
        if bool(project.get("is_default")):
            legacy_status = _read_legacy_topology_status()
            if legacy_status is not None:
                return legacy_status
        return TopologyStatus(
            path=str(topology_path),
            exists=False,
            warnings=[
                "Blast radius may be incomplete — service topology is not configured."
            ],
        )
    status = _build_topology_status(payload, path=topology_path, exists=True)
    status.drift = check_topology_drift(
        project_id=int(project["id"]),
        workspace_id=int(workspace["id"]) if workspace is not None else None,
    )
    return status


def import_topology_source(
    source_type: str,
    source_ref: str,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> TopologyImportResult:
    """Import topology through the shared source registry."""
    normalized_source_type = str(source_type or "").strip().lower()
    if not normalized_source_type:
        raise TopologyImportError(
            "invalid_topology_source",
            "Topology source type is required.",
        )

    project = build_project_payload(
        resolve_project_reference(project_id=project_id, project_key=project_key)
    )
    workspace_record = resolve_workspace_reference(
        project_id=int(project["id"]),
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    workspace = (
        build_workspace_payload(workspace_record)
        if workspace_record is not None
        else None
    )
    previous_payload, _, _ = _load_latest_topology_payload(project, workspace)
    change_set = _lookup_source_handler(normalized_source_type)(source_ref)
    warnings = list(change_set.warnings)

    if change_set.operation == "noop":
        return _build_import_result(
            source_type=normalized_source_type,
            source_ref=source_ref,
            applied=False,
            change_set=change_set,
            before_payload=previous_payload,
            after_payload=previous_payload,
            warnings=warnings,
        )

    payload = _build_payload_from_change_set(
        change_set=change_set,
        source_type=normalized_source_type,
        source_ref=source_ref,
    )
    status = _persist_topology_payload(
        payload,
        project=project,
        workspace=workspace,
        source_type=normalized_source_type,
    )
    warnings.extend(status.warnings)
    return _build_import_result(
        source_type=normalized_source_type,
        source_ref=source_ref,
        applied=True,
        change_set=change_set,
        before_payload=previous_payload,
        after_payload=status.payload,
        warnings=warnings,
    )


def save_topology_definition(
    raw_text: str,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> TopologyStatus:
    """Persist topology input as the active blast-radius context and return validation feedback."""
    validation_status = validate_topology_definition(
        raw_text,
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    if validation_status.blocking_errors:
        raise ValueError(" ".join(validation_status.blocking_errors))

    payload = dict(validation_status.payload or {})
    project = build_project_payload(
        resolve_project_reference(project_id=project_id, project_key=project_key)
    )
    workspace_record = resolve_workspace_reference(
        project_id=int(project["id"]),
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    workspace = (
        build_workspace_payload(workspace_record)
        if workspace_record is not None
        else None
    )
    change_set = _build_custom_change_set(payload)

    try:
        return _persist_topology_payload(
            _build_payload_from_change_set(
                change_set=change_set,
                source_type="manual",
                source_ref="inline://manual-topology",
            ),
            project=project,
            workspace=workspace,
            source_type="manual",
        )
    except TopologyImportError as exc:
        raise ValueError(exc.message) from exc


def validate_topology_definition(
    raw_text: str,
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> TopologyStatus:
    """Validate topology input without persisting it."""
    try:
        payload = json.loads(raw_text)
    except JSONDecodeError as exc:
        raise ValueError("Topology definition must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Topology definition must be a JSON object.")

    project = build_project_payload(
        resolve_project_reference(project_id=project_id, project_key=project_key)
    )
    workspace_record = resolve_workspace_reference(
        project_id=int(project["id"]),
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    workspace = (
        build_workspace_payload(workspace_record)
        if workspace_record is not None
        else None
    )
    validation_payload = dict(payload)
    validation_payload["updated_at"] = _current_timestamp()
    validation_status = _build_topology_status(
        validation_payload,
        path=_topology_scope_path(project, workspace),
        exists=False,
    )

    change_set = _build_custom_change_set(payload)
    if change_set.operation == "noop" and payload.get("services"):
        message = _join_warnings(change_set.warnings) or (
            "Topology import did not produce any valid services to apply."
        )
        validation_status.blocking_errors.append(message)
    validation_status.warnings = _unique_messages(
        list(validation_status.warnings) + list(change_set.warnings)
    )
    return validation_status


def load_topology(
    *,
    project_id: int | None = None,
    project_key: str | None = None,
    workspace_id: int | None = None,
    workspace_key: str | None = None,
) -> tuple[dict | None, str | None]:
    """Load topology context and return an optional warning."""
    status = get_topology_status(
        project_id=project_id,
        project_key=project_key,
        workspace_id=workspace_id,
        workspace_key=workspace_key,
    )
    messages = status.blocking_errors + status.warnings
    return status.payload, _join_warnings(messages)
