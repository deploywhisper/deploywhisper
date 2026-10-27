"""Closed engine values; frozen wire states and explicit local transitions."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Annotated, Literal
from pydantic import (
    AfterValidator,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
)
from infra_automation.contracts import ClosedModel, OutputKind, SAFE_INTEGER
from infra_automation.lifecycle import (
    InputScalar,
    MutationRequest,
    Positive,
    CursorEnvelope,
)
from infra_automation.workflow_schema import Identifier, Digest

RunState = Literal[
    "queued",
    "running",
    "waiting_approval",
    "ready_handoff",
    "handing_off",
    "external_running",
    "succeeded",
    "failed",
    "stopped_by_gate",
    "rejected",
    "expired",
    "timed_out",
    "cancelled",
    "delivery_unknown",
]
AttemptState = Literal[
    "pending", "claimed", "running", "succeeded", "failed", "timed_out", "cancelled"
]
TERMINAL_STATES = frozenset(
    (
        "succeeded",
        "failed",
        "stopped_by_gate",
        "rejected",
        "expired",
        "timed_out",
        "cancelled",
    )
)
ACTIVE_STATES = frozenset(
    (
        "running",
        "waiting_approval",
        "ready_handoff",
        "handing_off",
        "external_running",
        "delivery_unknown",
    )
)
_FAILURES = frozenset(
    ("failed", "stopped_by_gate", "rejected", "expired", "timed_out", "cancelled")
)
RUN_TRANSITIONS = MappingProxyType(
    {
        "queued": frozenset(("running", "cancelled", "expired", "timed_out", "failed")),
        "running": TERMINAL_STATES
        | frozenset(
            ("waiting_approval", "ready_handoff", "handing_off", "external_running")
        ),
        "waiting_approval": _FAILURES | {"ready_handoff"},
        "ready_handoff": _FAILURES | {"handing_off"},
        "handing_off": frozenset(("external_running", "delivery_unknown")),
        "external_running": frozenset(("delivery_unknown",)),
        **{x: frozenset() for x in TERMINAL_STATES | {"delivery_unknown"}},
    }
)
ATTEMPT_TRANSITIONS = MappingProxyType(
    {
        "pending": frozenset(("claimed", "failed", "timed_out", "cancelled")),
        "claimed": frozenset(("running", "failed", "timed_out", "cancelled")),
        "running": frozenset(("succeeded", "failed", "timed_out", "cancelled")),
        **{x: frozenset() for x in ("succeeded", "failed", "timed_out", "cancelled")},
    }
)


def require_run_transition(old: str, new: str) -> None:
    if old not in RUN_TRANSITIONS or new not in RUN_TRANSITIONS[old]:
        raise ValueError("Invalid run transition.")


def require_attempt_transition(old: str, new: str) -> None:
    if old not in ATTEMPT_TRANSITIONS or new not in ATTEMPT_TRANSITIONS[old]:
        raise ValueError("Invalid attempt transition.")


class RunRequest(MutationRequest):
    workflow_id: Identifier
    revision_id: Identifier
    workspace_id: Positive
    inputs: Annotated[
        dict[Identifier, InputScalar],
        Field(max_length=32, json_schema_extra={"additionalProperties": False}),
    ] = Field(default_factory=dict)
    idempotency_key: Identifier
    total_timeout_seconds: Annotated[StrictInt, Field(ge=60, le=3600)] = 3600


class CancelRunRequest(MutationRequest):
    expected_version: Positive


class RetryAttemptRequest(CancelRunRequest):
    pass


class OutputReference(ClosedModel):
    kind: OutputKind
    reference: Identifier
    digest: Digest


def _utc_timestamp(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return value


UTCText = Annotated[
    StrictStr,
    Field(
        min_length=20, max_length=20, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    ),
    AfterValidator(_utc_timestamp),
]


def _log_bytes(value: str) -> str:
    if len(value.encode("utf-8", errors="strict")) > 16384:
        raise ValueError("Log chunk exceeds byte ceiling.")
    return value


class RunView(ClosedModel):
    id: Identifier
    workflow_id: Identifier
    revision_id: Identifier
    project_id: Positive
    workspace_id: Positive
    requested_by: Identifier
    state: RunState
    version: Positive
    snapshot_digest: Digest
    definition_digest: Digest
    input_digest: Digest
    created_at: UTCText
    deadline_at: UTCText
    cancel_requested: StrictBool
    cancellation_requested_at: UTCText | None


class StepView(ClosedModel):
    id: Identifier
    run_id: Identifier
    step_id: Identifier
    attempt_number: Positive
    state: AttemptState
    version: Positive
    fence: Positive
    generation: Annotated[StrictInt, Field(ge=0, le=SAFE_INTEGER)]
    deadline_at: UTCText
    lease_until: UTCText | None
    output: OutputReference | None = None
    uploads: Annotated[list[OutputReference], Field(max_length=50)] = Field(
        default_factory=list
    )


class LogChunk(ClosedModel):
    sequence: Positive
    text: Annotated[StrictStr, Field(max_length=16384), AfterValidator(_log_bytes)]


class RunPage(ClosedModel):
    items: Annotated[list[RunView], Field(max_length=100)]
    cursor: CursorEnvelope


class StepPage(ClosedModel):
    items: Annotated[list[StepView], Field(max_length=100)]
    cursor: CursorEnvelope


class LogPage(ClosedModel):
    items: Annotated[list[LogChunk], Field(max_length=100)]
    cursor: CursorEnvelope


class WorkerResult(ClosedModel):
    outcome: Literal[
        "local_success",
        "retryable_local_failure",
        "permanent_local_failure",
        "stopped_by_gate",
        "rejected",
        "external_unknown",
    ]
    output: OutputReference | None = None


class EngineBounds(ClosedModel):
    global_queued_runs: Annotated[StrictInt, Field(ge=1, le=1000)] = 1000
    disk_reserve_bytes: Annotated[StrictInt, Field(ge=1, le=67108864)] = 67108864
    workflow_active_runs: Annotated[StrictInt, Field(ge=1, le=5)] = 5
    workflow_queued_runs: Annotated[StrictInt, Field(ge=1, le=25)] = 25
    analysis_workers: Annotated[StrictInt, Field(ge=1, le=2)] = 2
    project_bytes: Annotated[StrictInt, Field(ge=1, le=67108864)] = 67108864
    global_bytes: Annotated[StrictInt, Field(ge=1, le=268435456)] = 268435456
    attempt_log_bytes: Annotated[StrictInt, Field(ge=1, le=1048576)] = 1048576
    log_chunk_utf8_bytes: Annotated[StrictInt, Field(ge=1, le=16384)] = 16384


@dataclass(frozen=True)
class CoordinatorHandle:
    owner_id: str
    owner_secret: str = field(repr=False)
    generation: int


@dataclass(frozen=True)
class AttemptHandle(CoordinatorHandle):
    project_id: int
    workspace_id: int
    principal_id: str
    run_id: str
    step_id: str
    attempt_id: str
    attempt_number: int
    fence: int
    authorization_epoch: int
    restore_epoch: int


def engine_json_schema() -> dict:
    schema = TypeAdapter(
        RunRequest
        | CancelRunRequest
        | RetryAttemptRequest
        | RunView
        | StepView
        | OutputReference
        | WorkerResult
        | EngineBounds
        | RunPage
        | StepPage
        | LogPage
    ).json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Durable engine v1 requests and consumer values"
    return schema


@dataclass(frozen=True)
class AuditActor:
    principal_id: str
    principal_type: str
    role: str
