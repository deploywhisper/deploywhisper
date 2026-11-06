"""Closed signed-intake values and operator-owned nonsecret key references."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    Field,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from infra_automation.contracts import ClosedModel, CommitSha, Identifier
from infra_automation.lifecycle import InputScalar, Positive
from infra_automation.state import UTCText

TriggerVersion = Annotated[StrictInt, Field(ge=1, le=1)]
TriggerOrigin = Literal["webhook", "pull_request", "cli"]
SecretEnvironmentReference = Annotated[
    StrictStr, Field(min_length=1, max_length=128, pattern=r"^[A-Z][A-Z0-9_]*$")
]


class TriggerSourcePin(ClosedModel):
    repository_id: Identifier
    commit_sha: CommitSha


class TriggerSource(TriggerSourcePin):
    origin: TriggerOrigin
    pr_ref: (
        Annotated[
            StrictStr,
            Field(
                min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
            ),
        ]
        | None
    ) = None

    @field_validator("pr_ref")
    @classmethod
    def safe_reference(cls, value):
        if value is not None and (
            ".." in value or "//" in value or value.endswith(("/", ".", ".lock"))
        ):
            raise ValueError("A bounded plain pull-request reference is required.")
        return value

    @model_validator(mode="after")
    def origin_reference(self):
        if (self.origin == "pull_request") != (self.pr_ref is not None):
            raise ValueError("Only pull-request origin requires a reference.")
        return self


class TriggerRequest(ClosedModel):
    version: TriggerVersion
    workflow_revision_id: Identifier
    project_id: Positive
    workspace_id: Positive
    source: TriggerSource
    inputs: Annotated[dict[Identifier, InputScalar], Field(max_length=32)]
    idempotency_key: Identifier


class TriggerStatusRequest(ClosedModel):
    version: TriggerVersion
    run_id: Identifier


class TriggerListRequest(ClosedModel):
    version: TriggerVersion
    workflow_id: Identifier | None = None
    limit: Annotated[StrictInt, Field(ge=1, le=100)] = 25
    cursor: Identifier | None = None


class TriggerKeyDefinition(ClosedModel):
    key_id: Identifier
    principal_id: Identifier
    principal_type: Literal["service", "agent"]
    project_id: Positive
    workspace_id: Positive
    allowed_revision_ids: Annotated[
        tuple[Identifier, ...], Field(min_length=1, max_length=32)
    ]
    allowed_sources: Annotated[
        tuple[TriggerSourcePin, ...], Field(min_length=1, max_length=32)
    ]
    allowed_origins: Annotated[
        tuple[TriggerOrigin, ...], Field(min_length=1, max_length=3)
    ]
    authentication_version: Positive
    membership_version: Positive
    restore_epoch: Positive
    expires_at: UTCText
    secret_env_ref: SecretEnvironmentReference

    @field_validator(
        "allowed_revision_ids", "allowed_sources", "allowed_origins", mode="before"
    )
    @classmethod
    def json_arrays(cls, value):
        return tuple(value) if type(value) is list else value

    @model_validator(mode="after")
    def unique_allowlists(self):
        sources = [
            (source.repository_id, source.commit_sha) for source in self.allowed_sources
        ]
        if (
            len(set(self.allowed_revision_ids)) != len(self.allowed_revision_ids)
            or len(set(sources)) != len(sources)
            or len(set(self.allowed_origins)) != len(self.allowed_origins)
        ):
            raise ValueError("Allowlist entries must be unique.")
        return self


class TriggerKeyManifest(ClosedModel):
    version: TriggerVersion
    keys: Annotated[
        tuple[TriggerKeyDefinition, ...], Field(min_length=1, max_length=32)
    ]

    @field_validator("keys", mode="before")
    @classmethod
    def json_array(cls, value):
        return tuple(value) if type(value) is list else value

    @model_validator(mode="after")
    def unique_key_ids(self):
        if len({key.key_id for key in self.keys}) != len(self.keys):
            raise ValueError("Key IDs must be unique.")
        return self


def trigger_json_schema() -> dict:
    schema = TypeAdapter(
        TriggerRequest | TriggerStatusRequest | TriggerListRequest | TriggerKeyManifest
    ).json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Signed trigger v1 requests and protected key manifest"
    return schema
