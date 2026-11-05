"""Bounded human declarations and deterministic collection/review ordering.

Declarations never verify repository provenance, acquire locks or authorize work.
The planner requires an exact inventory of affected units and their prerequisites.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
)

from infra_automation.contracts import ClosedModel, CommitSha, Digest, Identifier

MAX_UNITS = 25
MAX_EDGES = 200
MAX_BYTES = 131072
MAX_ERRORS = 50
Version = Annotated[StrictInt, Field(ge=1, le=1)]


class _PathSource(ClosedModel):
    path: Annotated[StrictStr, Field(min_length=1, max_length=512)]

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        if value == ".":
            return value
        if (
            any(ord(char) < 32 or ord(char) == 127 for char in value)
            or "\\" in value
            or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("A normalized relative source path is required.")
        return value


class UnitSource(_PathSource):
    kind: Literal["declared_repository"]
    repository_id: Identifier
    commit_sha: CommitSha


class UploadedUnitSource(_PathSource):
    kind: Literal["uploaded"]
    repository_source: Literal["unavailable"] = "unavailable"


class DeclaredUnit(ClosedModel):
    id: Identifier
    source: Annotated[UnitSource | UploadedUnitSource, Field(discriminator="kind")]
    environment: Identifier
    target: Identifier
    prerequisites: Annotated[list[Identifier], Field(max_length=MAX_UNITS)]


class UnitMap(ClosedModel):
    version: Version = 1
    units: Annotated[list[DeclaredUnit], Field(min_length=1, max_length=MAX_UNITS)]
    affected: Annotated[list[Identifier], Field(min_length=1, max_length=MAX_UNITS)]


class UnitPlan(ClosedModel):
    version: Version = 1
    inventory: UnitMap
    waves: Annotated[list[list[Identifier]], Field(min_length=1, max_length=MAX_UNITS)]
    map_digest: Digest
    waves_digest: Digest
    order_kind: Literal["collection_review"] = "collection_review"


class UnitMapError(ValueError):
    """Located, bounded nonreflective diagnostics safe for an editor to render."""

    def __init__(self, errors):
        self.errors = tuple(errors[:MAX_ERRORS])
        super().__init__("Declared unit map is invalid.")


def _error(code, path, message):
    return {"code": code, "path": list(path), "message": message}


def _fail(code, path, message):
    raise UnitMapError([_error(code, path, message)])


def _canonical(value):
    # Keep this pure: target/decision helpers import lifecycle, whose snapshots
    # consume these models. Importing them here would introduce a cycle.
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(kind, value):
    return (
        "sha256:"
        + hashlib.sha256(
            _canonical({"version": 1, "kind": kind, "value": value})
        ).hexdigest()
    )


def _charge_text(value, budget):
    # Check characters before UTF-8 allocation, then account for multibyte text.
    if len(value) > budget[1]:
        _fail("resource_limit", (), "Unit map text exceeds its bound.")
    budget[1] -= len(value.encode("utf-8"))
    if budget[1] < 0:
        _fail("resource_limit", (), "Unit map text exceeds its bound.")


def _plain(value, depth=0, budget=None):
    if budget is None:
        budget = [10000, MAX_BYTES]
    budget[0] -= 1
    if budget[0] < 0:
        _fail("resource_limit", (), "Unit map node count exceeds its bound.")
    if depth > 16:
        _fail("resource_limit", (), "Unit map nesting exceeds its bound.")
    if isinstance(value, BaseModel):
        value = {**value.__dict__, **(value.__pydantic_extra__ or {})}
    if type(value) is dict:
        if len(value) > 64 or any(type(key) is not str for key in value):
            _fail("schema_field", (), "Unit map keys violate the closed schema.")
        for key in value:
            _charge_text(key, budget)
        return {key: _plain(child, depth + 1, budget) for key, child in value.items()}
    if type(value) is list:
        if len(value) > MAX_UNITS:
            _fail("resource_limit", (), "Unit map array exceeds its bound.")
        return [_plain(child, depth + 1, budget) for child in value]
    if type(value) is str:
        _charge_text(value, budget)
        return value
    if type(value) is int or value is None or type(value) is bool:
        return value
    _fail("schema_field", (), "Unsupported unit map value.")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail("duplicate_key", (), "Duplicate JSON object keys are forbidden.")
        result[key] = value
    return result


def _load(value):
    try:
        if type(value) in {str, bytes}:
            raw = value.encode("utf-8") if type(value) is str else value
            if len(raw) > MAX_BYTES:
                _fail("resource_limit", (), "Unit map exceeds 128 KiB.")
            # Bound syntactic nesting before JSON construction, ignoring strings.
            depth, quoted, escaped = 0, False, False
            for char in raw.decode("utf-8"):
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char in "[{":
                    depth += 1
                    if depth > 16:
                        _fail(
                            "resource_limit", (), "Unit map nesting exceeds its bound."
                        )
                elif char in "]}":
                    depth -= 1
            value = json.loads(raw, object_pairs_hook=_pairs)
        value = _plain(value)
        if len(_canonical(value)) > MAX_BYTES:
            _fail("resource_limit", (), "Unit map exceeds 128 KiB.")
        return UnitMap.model_validate(value)
    except UnitMapError:
        raise
    except ValidationError as exc:
        allowed = {
            "version",
            "units",
            "affected",
            "id",
            "source",
            "kind",
            "repository_id",
            "commit_sha",
            "path",
            "environment",
            "target",
            "prerequisites",
            "repository_source",
        }
        raise UnitMapError(
            [
                _error(
                    "schema_field",
                    tuple(
                        part if type(part) is int or part in allowed else "field"
                        for part in item["loc"]
                    ),
                    "Value does not satisfy the closed unit-map schema.",
                )
                for item in exc.errors(include_input=False, include_context=False)[
                    :MAX_ERRORS
                ]
            ]
        ) from None
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _fail("schema_field", (), "Unit map must be valid bounded JSON.")


def plan_unit_map(value: UnitMap | dict | str | bytes) -> UnitPlan:
    """Revalidate declarations, require exact scope, then canonicalize and order.

    The 25-unit/200-edge bounds are this planner's conservative v1 limits, not a
    claim of measured production throughput. No executable workflow is generated.
    """
    inventory = _load(value)
    errors = []
    by_id = {}
    for index, unit in enumerate(inventory.units):
        if unit.id in by_id:
            errors.append(
                _error(
                    "duplicate_identity",
                    ("units", index, "id"),
                    "Unit IDs must be unique.",
                )
            )
        by_id[unit.id] = unit
    if sum(len(unit.prerequisites) for unit in inventory.units) > MAX_EDGES:
        errors.append(
            _error(
                "resource_limit", ("units",), "Unit map exceeds 200 prerequisite edges."
            )
        )
    for index, unit in enumerate(inventory.units):
        seen = set()
        for edge_index, prerequisite in enumerate(unit.prerequisites):
            path = ("units", index, "prerequisites", edge_index)
            if prerequisite in seen:
                errors.append(
                    _error("duplicate_edge", path, "Prerequisites must be unique.")
                )
            if prerequisite not in by_id:
                errors.append(
                    _error(
                        "unknown_identity",
                        path,
                        "Prerequisite is not declared in the inventory.",
                    )
                )
            seen.add(prerequisite)
    seen = set()
    for index, unit_id in enumerate(inventory.affected):
        if unit_id in seen:
            errors.append(
                _error(
                    "duplicate_identity",
                    ("affected", index),
                    "Affected IDs must be unique.",
                )
            )
        if unit_id not in by_id:
            errors.append(
                _error(
                    "unknown_identity",
                    ("affected", index),
                    "Affected unit is not declared in the inventory.",
                )
            )
        seen.add(unit_id)
    if errors:
        raise UnitMapError(errors)
    covered = set(inventory.affected)
    pending = list(covered)
    while pending:
        unit_id = pending.pop()
        for prerequisite in by_id[unit_id].prerequisites:
            if prerequisite not in covered:
                covered.add(prerequisite)
                pending.append(prerequisite)
    for index, unit in enumerate(inventory.units):
        if unit.id not in covered:
            errors.append(
                _error(
                    "extra_scope",
                    ("units", index, "id"),
                    "Unit is neither affected nor a declared prerequisite.",
                )
            )
    remaining = set(by_id)
    waves = []
    while remaining:
        ready = sorted(
            unit_id
            for unit_id in remaining
            if not remaining.intersection(by_id[unit_id].prerequisites)
        )
        if not ready:
            errors.append(
                _error(
                    "graph_cycle", ("units",), "Declared prerequisites contain a cycle."
                )
            )
            break
        waves.append(ready)
        remaining.difference_update(ready)
    if errors:
        raise UnitMapError(errors)
    normalized = inventory.model_dump(mode="json")
    normalized["affected"].sort()
    normalized["units"].sort(key=lambda unit: unit["id"])
    for unit in normalized["units"]:
        unit["prerequisites"].sort()
    map_digest = _digest("declared-unit-map", normalized)
    return UnitPlan(
        inventory=UnitMap.model_validate(normalized),
        waves=waves,
        map_digest=map_digest,
        waves_digest=_digest(
            "declared-unit-waves", {"map_digest": map_digest, "waves": waves}
        ),
    )
