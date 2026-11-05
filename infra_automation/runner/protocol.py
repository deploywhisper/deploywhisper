"""Closed frozen runner-v1 and enrollment-v1 wire contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)
from infra_automation.contracts import ClosedModel, Digest, Identifier, SAFE_INTEGER
from infra_automation.lifecycle import Positive
from infra_automation.state import UTCText

MAX_BYTES = 128 * 1024
Version = Annotated[StrictInt, Field(ge=1, le=1)]


def _materialize(value, depth=0):
    if depth > 16:
        raise ValueError("Runner message nesting limit exceeded.")
    if isinstance(value, BaseModel):
        value = {**value.__dict__, **(value.__pydantic_extra__ or {})}
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("Invalid runner object.")
        return {key: _materialize(child, depth + 1) for key, child in value.items()}
    if type(value) is list:
        return [_materialize(child, depth + 1) for child in value]
    if value is not None and type(value) not in (str, int, bool):
        raise ValueError("Invalid runner value.")
    if type(value) is int and abs(value) > SAFE_INTEGER:
        raise ValueError("Invalid runner integer.")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate runner field.")
        result[key] = value
    return result


def _wire(value):
    if type(value) in (str, bytes):
        raw = value.encode("utf-8") if type(value) is str else value
        if len(raw) > MAX_BYTES:
            raise ValueError("Runner message byte limit exceeded.")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    value = _materialize(value)
    raw = json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("Runner message byte limit exceeded.")
    return value


class RunnerClosed(ClosedModel):
    model_config = ConfigDict(revalidate_instances="always")
    version: Version = 1

    @model_validator(mode="before")
    @classmethod
    def wire_boundary(cls, value):
        return _wire(value)


class TaskScope(RunnerClosed):
    runner_id: Identifier
    project_id: Identifier
    workspace_id: Identifier
    run_id: Identifier
    step_id: Identifier
    attempt: Positive
    fence: Positive
    coordinator_generation: Positive
    authorization_epoch: Positive
    restore_epoch: Positive
    lease_deadline: UTCText
    audience: Literal["runner-task-v1"]


class RunnerMessage(RunnerClosed):
    operation: Literal["claim", "heartbeat", "log", "upload", "complete"]
    scope: TaskScope
    capabilities: Annotated[
        list[Literal["screened-collection-v1"]], Field(min_length=1, max_length=1)
    ]
    profile_digest: Digest
    sequence: Positive
    log: Annotated[str, Field(max_length=16384)] | None = Field(
        default=None, repr=False
    )
    upload_digest: Digest | None = None
    atomic_upload_id: Identifier | None = None
    state: Literal["succeeded", "failed"] | None = None

    @model_validator(mode="after")
    def operation_fields(self):
        expected = {
            "claim": set(),
            "heartbeat": set(),
            "log": {"log"},
            "upload": {"upload_digest", "atomic_upload_id"},
            "complete": {"atomic_upload_id", "state"},
        }[self.operation]
        if (
            self.operation == "complete"
            and self.state == "failed"
            and self.atomic_upload_id is None
        ):
            expected = {"state"}
        present = {
            key
            for key in ("log", "upload_digest", "atomic_upload_id", "state")
            if getattr(self, key) is not None
        }
        if present != expected or (
            self.log is not None and len(self.log.encode("utf-8")) > 16384
        ):
            raise ValueError("Runner operation payload is invalid.")
        return self


class Enrollment(RunnerClosed):
    audience: Literal["runner-enrollment-v1"]
    enrollment_id: Identifier
    runner_id: Identifier
    project_id: Identifier
    workspace_id: Identifier
    expires_at: UTCText
    one_use: Literal[True]

    @field_validator("one_use", mode="before")
    @classmethod
    def actual_true(cls, value):
        if type(value) is not bool or not value:
            raise ValueError("Enrollment must be one use.")
        return value


@dataclass(frozen=True)
class RunnerCredential:
    runner_id: str
    token: str = field(repr=False)


def parse_message(value) -> RunnerMessage:
    return RunnerMessage.model_validate(_wire(value))


def parse_enrollment(value) -> Enrollment:
    return Enrollment.model_validate(_wire(value))
