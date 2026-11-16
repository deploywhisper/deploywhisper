"""Immutable, provider-neutral cloud observations and connector protocol."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from evidence.models import EvidenceRedactionStatus

_PROVIDER = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")


class FrozenModel(BaseModel):
    """Nested fields use immutable tuples and frozen models, never dictionaries."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", allow_inf_nan=False
    )


class ResourceIdentity(FrozenModel):
    address: StrictStr = Field(min_length=1, max_length=2048)
    resource_type: StrictStr = Field(min_length=1, max_length=128)
    physical_id: StrictStr | None = Field(default=None, min_length=1, max_length=2048)
    arn: StrictStr | None = Field(default=None, min_length=1, max_length=2048)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=2048)
    region: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    tags: tuple[tuple[StrictStr, StrictStr], ...] = ()

    @field_validator("address", "resource_type", "physical_id", "arn", "name", "region")
    @classmethod
    def _nonblank_identity(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Resource identities must not be whitespace")
        return value

    @field_validator("tags")
    @classmethod
    def _tags(cls, value):
        if len({key for key, _ in value}) != len(value) or any(
            not key for key, _ in value
        ):
            raise ValueError("Tags need unique nonempty keys")
        return tuple(sorted(value))


class SnapshotFact(FrozenModel):
    """Selected scalar metadata only; nested bodies cannot enter observations."""

    name: StrictStr = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z][A-Za-z0-9_.:-]*$"
    )
    value: StrictStr | StrictBool | StrictInt | StrictFloat | None

    @field_validator("value")
    @classmethod
    def _bounded_scalar(cls, value):
        if isinstance(value, str) and len(value) > 16384:
            raise ValueError("Snapshot scalar is too large")
        return value


class ReadStatus(str, Enum):
    READ = "read"
    PARTIAL = "partial"
    UNREADABLE = "unreadable"
    UNKNOWN = "unknown"
    NO_LIVE_COUNTERPART = "no_live_counterpart"


class ResourceRead(FrozenModel):
    identity: ResourceIdentity
    status: ReadStatus
    cause: StrictStr | None = Field(default=None, min_length=1, max_length=2048)
    missing_permission: StrictStr | None = Field(
        default=None, min_length=1, max_length=256
    )
    facts: tuple[SnapshotFact, ...] = ()

    @field_validator("cause", "missing_permission")
    @classmethod
    def _nonblank_cause(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Read causes must not be whitespace")
        return value

    @model_validator(mode="after")
    def _result(self):
        if (
            self.status
            in {ReadStatus.PARTIAL, ReadStatus.UNREADABLE, ReadStatus.UNKNOWN}
            and not self.cause
        ):
            raise ValueError("An incomplete read needs a specific cause")
        if (
            self.status
            in {
                ReadStatus.UNREADABLE,
                ReadStatus.UNKNOWN,
                ReadStatus.NO_LIVE_COUNTERPART,
            }
            and self.facts
        ):
            raise ValueError("Unobserved resources cannot carry observed facts")
        if self.missing_permission and self.status not in {
            ReadStatus.UNREADABLE,
            ReadStatus.PARTIAL,
        }:
            raise ValueError("Missing permissions require an incomplete read")
        if len({fact.name for fact in self.facts}) != len(self.facts):
            raise ValueError("Snapshot facts need unique names")
        object.__setattr__(
            self, "facts", tuple(sorted(self.facts, key=lambda fact: fact.name))
        )
        return self


class LiveContextSnapshot(FrozenModel):
    snapshot_version: Literal[1] = 1
    provider: StrictStr = Field(min_length=1, max_length=32)
    project_id: StrictInt = Field(ge=1)
    scope_id: StrictStr = Field(min_length=1, max_length=128)
    scope: StrictStr = Field(min_length=1, max_length=512)
    regions: tuple[StrictStr, ...] = ()
    read_window_start: datetime
    read_window_end: datetime
    resources: tuple[ResourceRead, ...] = ()
    issued_actions: tuple[StrictStr, ...] = ()
    redaction_status: EvidenceRedactionStatus = "none"
    partial: StrictBool = False
    digest: StrictStr = ""

    @field_validator("scope", "scope_id")
    @classmethod
    def _nonblank_scope(cls, value):
        if not value.strip():
            raise ValueError("Snapshot scopes must not be whitespace")
        return value

    @field_validator("provider")
    @classmethod
    def _provider(cls, value):
        if not _PROVIDER.fullmatch(value):
            raise ValueError("Provider name is invalid")
        return value

    @field_validator("read_window_start", "read_window_end")
    @classmethod
    def _utc_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Read windows require timezone-aware timestamps")
        return value.astimezone(timezone.utc)

    @field_validator("regions", "issued_actions")
    @classmethod
    def _canonical_set(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError("Observation set entries must be nonempty")
        if len(values) != len(set(values)):
            raise ValueError("Observation set entries must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def _observation(self, info: ValidationInfo):
        if (
            info.context
            and info.context.get("require_digest")
            and re.fullmatch(r"[0-9a-f]{64}", self.digest) is None
        ):
            raise ValueError("A retained snapshot requires its content digest")
        if self.read_window_end < self.read_window_start:
            raise ValueError("Read window ends before it starts")
        if len({item.identity.address for item in self.resources}) != len(
            self.resources
        ):
            raise ValueError("Snapshot resource addresses must be unique")
        object.__setattr__(
            self,
            "resources",
            tuple(sorted(self.resources, key=lambda item: item.identity.address)),
        )
        partial = any(
            item.status
            in {ReadStatus.PARTIAL, ReadStatus.UNKNOWN, ReadStatus.UNREADABLE}
            for item in self.resources
        )
        if "partial" in self.model_fields_set and self.partial != partial:
            raise ValueError("Snapshot completeness contradicts read results")
        object.__setattr__(self, "partial", partial)
        expected = hashlib.sha256(
            canonical_snapshot_json(self, include_digest=False).encode("utf-8")
        ).hexdigest()
        if self.digest and self.digest != expected:
            raise ValueError("Snapshot digest does not match its observation")
        object.__setattr__(self, "digest", expected)
        return self


def canonical_snapshot_json(
    snapshot: LiveContextSnapshot, *, include_digest: bool = True
) -> str:
    """Canonical bytes bind project, opaque authorized scope and read window."""
    return json.dumps(
        snapshot.model_dump(
            mode="json", exclude=None if include_digest else {"digest"}
        ),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def build_snapshot(**fields: Any) -> LiveContextSnapshot:
    """Build an immutable observation; screening remains mandatory before storage."""
    return LiveContextSnapshot.model_validate(fields)


def validate_snapshot(
    snapshot: LiveContextSnapshot | Mapping[str, Any],
) -> LiveContextSnapshot:
    """Rebuild even existing instances so tampered model_copy values cannot bypass validation."""
    fields = (
        snapshot.model_dump(mode="python", warnings=False)
        if isinstance(snapshot, LiveContextSnapshot)
        else dict(snapshot)
    )
    return LiveContextSnapshot.model_validate(fields, context={"require_digest": True})


@runtime_checkable
class CloudConnector(Protocol):
    def collect(
        self,
        identities: tuple[ResourceIdentity, ...],
        *,
        project_id: int,
        scope_id: str,
    ) -> LiveContextSnapshot:
        """Return only observations of the supplied identities within the authorized scope."""
        ...
