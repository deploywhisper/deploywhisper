"""Plan-bound collection outcomes, independent of retained snapshot-v1 bytes."""

from __future__ import annotations

from datetime import datetime, timezone
import threading
import time
import math
from typing import Literal

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator

from cloud.base import (
    FrozenModel,
    LiveContextSnapshot,
    ResourceRead,
    ReadStatus,
    build_snapshot,
    validate_snapshot,
)
from cloud.aws.client import AwsReader, Limits
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


class PlanGroundingOutcome(FrozenModel):
    """Service outcome; only its operational budget enters analysis surfaces."""

    model_config = ConfigDict(hide_input_in_errors=True)
    state: Literal["disabled", "snapshot", "unavailable"]
    project_id: StrictInt = Field(ge=1)
    snapshot: LiveContextSnapshot | None = None
    context: ContextSourceMetadata | None = None
    budget: CollectionBudget | None = None

    @model_validator(mode="after")
    def _state(self):
        if self.state == "disabled":
            if any(
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
        read_start = self._clock()
        results = {}
        attempted = actual = 0
        issued = set()
        for region in self._target.regions:
            indices = tuple(
                i for i, e in enumerate(approved.entries) if e.region == region
            )
            if not indices:
                continue
            remaining = deadline - time.monotonic()
            if cancel.is_set() or remaining <= 0 or attempted >= limits.call_budget:
                break
            batch_limits = Limits(
                per_call_timeout=limits.per_call_timeout,
                total_deadline=min(15, remaining),
                concurrency=limits.concurrency,
                call_budget=limits.call_budget - attempted,
                backoff=limits.backoff,
            )
            result = AwsReader(
                self._session, config={"region": region}
            ).execute_selected(
                approved,
                indices=indices,
                target=self._target,
                resources=resources,
                limits=batch_limits,
                cancel=cancel,
                deadline=deadline,
            )
            attempted += result.attempts
            actual += result.actual_call_count
            issued.update(indices[index] for index in result.issued_indices)
            results.update(zip(indices, result.items))
        observations = []
        actions = {approved.entries[index].capability for index in issued}
        fact_count = fact_bytes = 0
        for row in approved.resources:
            if row.state == "no_live_counterpart":
                observations.append(
                    ResourceRead(
                        identity=row.identity, status=ReadStatus.NO_LIVE_COUNTERPART
                    )
                )
                continue
            entries = [
                (i, e)
                for i, e in enumerate(approved.entries)
                if e.address == row.identity.address
            ]
            facts = {}
            missing = []
            causes = []
            for i, entry in entries:
                result = results.get(i)
                if result is None:
                    causes.append("cancelled" if cancel.is_set() else "bounded")
                    continue
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
            causes.extend(
                issue.cause
                for issue in approved.issues
                if issue.address == row.identity.address
            )
            if row.state == "unknown":
                causes.append(row.cause or "recorded_identity_missing")
            if not entries and not causes:
                causes.append("recorded_identity_missing")
            incomplete = bool(causes)
            status = (
                ReadStatus.PARTIAL
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
        from cloud.aws.allowlist import _CATALOG

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
        snapshot = redact_snapshot(snapshot, mask_accounts=False)
        return CollectedPlan(
            snapshot=snapshot,
            budget=CollectionBudget(
                planned_calls=approved.planned_calls,
                attempted_calls=attempted,
                actual_call_count=actual,
                call_budget=limits.call_budget,
                budget_consumed=attempted,
                elapsed_seconds=max(0, time.monotonic() - started),
                cancelled=cancel.is_set(),
            ),
        )
