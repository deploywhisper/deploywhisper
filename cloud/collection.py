"""Plan-bound collection outcomes, independent of retained snapshot-v1 bytes."""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
import math
from typing import Literal

from pydantic import (
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from cloud.base import (
    FrozenModel,
    LiveContextSnapshot,
    ResourceRead,
    ReadStatus,
    build_snapshot,
    validate_snapshot,
)
from cloud.aws.allowlist import _CATALOG
from cloud.aws.client import AwsReader, ExecutionProgress, Limits
from cloud.reflection import ReflectionTarget, guard_manifest
from cloud.redaction import redact_snapshot
from evidence.models import ContextSourceMetadata

_MAX_FACTS = 4096
_MAX_FACT_BYTES = 1024 * 1024
_MAX_IDENTITY_BYTES = 4 * 1024 * 1024


class CollectionBudget(FrozenModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    version: Literal[1] = 1
    planned_calls: StrictInt = Field(ge=0)
    attempted_calls: StrictInt = Field(ge=0)
    actual_call_count: StrictInt = Field(ge=0)
    call_budget: StrictInt = Field(ge=1, le=100)
    budget_consumed: StrictInt = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)
    cancelled: StrictBool = False

    @model_validator(mode="after")
    def _counts(self):
        if (
            not self.actual_call_count <= self.attempted_calls <= self.call_budget
            or self.attempted_calls > self.planned_calls
            or self.budget_consumed != self.attempted_calls
        ):
            raise ValueError("invalid_collection_counters")
        return self


class PermissionDenial(FrozenModel):
    """Exact denied capability, independent of legacy snapshot-v1 fields."""

    model_config = ConfigDict(hide_input_in_errors=True)
    address: StrictStr = Field(min_length=1, max_length=2048)
    capability: StrictStr
    action: StrictStr

    @model_validator(mode="after")
    def _permission(self):
        row = _CATALOG["operations"].get(self.capability)
        if row is None or row["iam_action"] != self.action:
            raise ValueError("invalid_permission_diagnostic")
        return self


class PlanGroundingOutcome(FrozenModel):
    """Service outcome; only its operational budget enters analysis surfaces."""

    model_config = ConfigDict(hide_input_in_errors=True)
    state: Literal["disabled", "snapshot", "unavailable"]
    project_id: StrictInt = Field(ge=1)
    snapshot: LiveContextSnapshot | None = None
    context: ContextSourceMetadata | None = None
    budget: CollectionBudget | None = None
    permission_denials: tuple[PermissionDenial, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def _state(self):
        if self.state == "disabled":
            if self.permission_denials or any(
                value is not None
                for value in (self.snapshot, self.context, self.budget)
            ):
                raise ValueError("disabled_collection_has_output")
        elif self.budget is None or (self.state == "snapshot" and self.context is None):
            raise ValueError("collection_output_missing")
        if (self.state == "snapshot") != (self.snapshot is not None):
            raise ValueError("collection_snapshot_state_mismatch")
        if self.snapshot is not None:
            snapshot = validate_snapshot(self.snapshot)
            if snapshot.project_id != self.project_id:
                raise ValueError("collection_project_mismatch")
            object.__setattr__(self, "snapshot", snapshot)
        return self


class CollectedPlan(FrozenModel):
    snapshot: LiveContextSnapshot
    budget: CollectionBudget
    permission_denials: tuple[PermissionDenial, ...] = Field(default=(), max_length=100)


class AwsPlanCollector:
    """Trusted constructor target/session; input plans cannot retarget clients."""

    provider = "aws"

    def __init__(self, *, target: ReflectionTarget, session, clock=None):
        self._target = ReflectionTarget.model_validate(target.model_dump())
        self._session = session
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def target(self):
        return self._target

    def collect_manifest(
        self,
        manifest,
        *,
        resources,
        project_id,
        scope_id,
        limits=None,
        cancel=None,
        deadline=None,
        sensitive_values=(),
        progress: ExecutionProgress | None = None,
    ) -> CollectedPlan:
        started = time.monotonic()
        limits = Limits.model_validate((limits or Limits()).model_dump())
        if deadline is not None and (
            type(deadline) not in (int, float) or not math.isfinite(deadline)
        ):
            raise ValueError("invalid_collection_deadline")
        deadline = (
            min(started + limits.total_deadline, deadline)
            if deadline is not None
            else started + limits.total_deadline
        )
        approved = guard_manifest(manifest, target=self._target, resources=resources)
        if (
            sum(
                len(row.identity.model_dump_json().encode())
                for row in approved.resources
            )
            > _MAX_IDENTITY_BYTES
        ):
            raise ValueError("collection_identity_bound")
        cancel = cancel or threading.Event()
        sensitive_values = tuple(sensitive_values)
        read_start = self._clock()
        indices = tuple(
            sorted(
                range(len(approved.entries)), key=lambda i: approved.entries[i].region
            )
        )
        execution = AwsReader(self._session).execute_selected(
            approved,
            indices=indices,
            target=self._target,
            resources=resources,
            limits=limits,
            cancel=cancel,
            deadline=deadline,
            all_regions=True,
            sensitive_values=sensitive_values,
            progress=progress,
        )
        results_by_address = {}
        for i, result in zip(indices, execution.items):
            entry = approved.entries[i]
            results_by_address.setdefault(entry.address, []).append((entry, result))
        causes_by_address = {}
        for issue in approved.issues:
            causes_by_address.setdefault(issue.address, []).append(issue.cause)
        observations = []
        permission_denials = []
        actions = {execution.items[i].capability for i in execution.issued_indices}
        fact_count = fact_bytes = 0
        for row in approved.resources:
            if row.state == "no_live_counterpart":
                observations.append(
                    ResourceRead(
                        identity=row.identity, status=ReadStatus.NO_LIVE_COUNTERPART
                    )
                )
                continue
            address = row.identity.address
            entries = results_by_address.get(address, ())
            facts = {}
            missing = []
            causes = list(causes_by_address.get(address, ()))
            for entry, result in entries:
                for fact in getattr(result, "facts", ()):
                    size = len(fact.model_dump_json().encode())
                    if fact_count >= _MAX_FACTS or fact_bytes + size > _MAX_FACT_BYTES:
                        causes.append("output_bound")
                        continue
                    facts[fact.name] = fact
                    fact_count += 1
                    fact_bytes += size
                if result.status != "recorded":
                    causes.append(result.cause or result.status)
                if result.missing_permission:
                    missing.append(result.missing_permission)
                    permission_denials.append(
                        PermissionDenial(
                            address=address,
                            capability=entry.capability,
                            action=result.missing_permission,
                        )
                    )
            if row.state == "unknown":
                causes.append(row.cause or "recorded_identity_missing")
            if not entries and not causes:
                causes.append("recorded_identity_missing")
            incomplete = bool(causes)
            status = (
                ReadStatus.UNKNOWN
                if not entries
                else ReadStatus.PARTIAL
                if incomplete and facts
                else ReadStatus.UNREADABLE
                if incomplete
                else ReadStatus.READ
            )
            observations.append(
                ResourceRead(
                    identity=row.identity,
                    status=status,
                    cause=sorted(set(causes))[0] if causes else None,
                    missing_permission=sorted(set(missing))[0] if missing else None,
                    facts=tuple(facts[k] for k in sorted(facts)),
                )
            )
        snapshot = build_snapshot(
            provider="aws",
            project_id=project_id,
            scope_id=scope_id,
            scope=self._target.account_id,
            regions=self._target.regions,
            read_window_start=read_start,
            read_window_end=self._clock(),
            resources=tuple(observations),
            issued_actions=tuple(
                sorted({_CATALOG["operations"][key]["iam_action"] for key in actions})
            ),
        )
        addresses: dict[str, str] = {}
        snapshot = redact_snapshot(
            snapshot,
            mask_accounts=False,
            sensitive_values=sensitive_values,
            address_map_out=addresses,
        )
        return CollectedPlan(
            snapshot=snapshot,
            permission_denials=tuple(
                item.model_copy(update={"address": addresses[item.address]})
                for item in permission_denials
            ),
            budget=CollectionBudget(
                planned_calls=approved.planned_calls,
                attempted_calls=execution.attempts,
                actual_call_count=execution.actual_call_count,
                call_budget=limits.call_budget,
                budget_consumed=execution.attempts,
                elapsed_seconds=max(0, time.monotonic() - started),
                cancelled=cancel.is_set(),
            ),
        )
