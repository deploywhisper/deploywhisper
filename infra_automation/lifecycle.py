"""Closed lifecycle values shared by persistence services and HTTP adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from infra_automation.contracts import SAFE_INTEGER, ClosedModel
from infra_automation.workflow_schema import (
    CommitSha,
    Digest,
    Identifier,
    UploadedSource,
    Workflow,
)
from services.policy_adapter_settings import PolicyAdapterSettings

Positive = Annotated[StrictInt, Field(ge=1, le=SAFE_INTEGER)]
Version = Annotated[StrictInt, Field(ge=0, le=SAFE_INTEGER)]
Reason = Annotated[StrictStr, Field(min_length=1, max_length=256)]


def _definition_bytes(value: str) -> str:
    if len(value.encode("utf-8", errors="strict")) > 131072:
        raise ValueError("Definition exceeds the byte ceiling.")
    return value


DefinitionText = Annotated[
    StrictStr, Field(min_length=1, max_length=131072), AfterValidator(_definition_bytes)
]


class LifecycleError(ValueError):
    """A fixed nonreflective error; adapters add only correlation metadata."""

    _ERRORS = {
        401: ("authentication_required", "Authentication required.", False),
        403: ("permission_denied", "Operation unavailable.", False),
        409: ("binding_conflict", "Review current evidence again.", False),
        422: ("request_validation_failed", "Request validation failed.", False),
        429: ("quota_exceeded", "Request limit reached.", True),
        503: (
            "authority_unavailable",
            "Current authority could not be verified.",
            True,
        ),
    }

    def __init__(self, status_code: int = 422):
        self.status_code = status_code
        self.code, self.message, self.retryable = self._ERRORS[status_code]
        super().__init__(self.message)


class AutomationSettings(ClosedModel):
    enabled: StrictBool = False
    max_workflows: Annotated[StrictInt, Field(ge=1, le=1000)] = 100
    max_revisions_per_workflow: Annotated[StrictInt, Field(ge=1, le=1000)] = 100
    max_active_runs: Annotated[StrictInt, Field(ge=1, le=10)] = 10
    max_queued_runs: Annotated[StrictInt, Field(ge=1, le=1000)] = 100
    max_artifact_bytes: Annotated[StrictInt, Field(ge=1, le=8388608)] = 8388608
    retention_seconds: Annotated[StrictInt, Field(ge=86400, le=31536000)] = 604800
    evidence_ttl_seconds: Annotated[StrictInt, Field(ge=60, le=3600)] = 3600
    approval_ttl_seconds: Annotated[StrictInt, Field(ge=60, le=3600)] = 900
    credential_ttl_seconds: Annotated[StrictInt, Field(ge=60, le=3600)] = 900

    @model_validator(mode="after")
    def bounded_authority_lifetimes(self) -> AutomationSettings:
        if (
            max(self.approval_ttl_seconds, self.credential_ttl_seconds)
            > self.evidence_ttl_seconds
        ):
            raise ValueError("Authority lifetime exceeds evidence lifetime.")
        return self


class MutationRequest(ClosedModel):
    reason: Reason

    @field_validator("reason", "name", check_fields=False)
    @classmethod
    def safe_label(cls, value: str) -> str:
        if not value.strip() or any(
            ord(char) < 32 or 127 <= ord(char) <= 159 or char in "\u2028\u2029"
            for char in value
        ):
            raise ValueError("A bounded single-line label is required.")
        value.encode("utf-8", errors="strict")
        return value


class CreateWorkflowRequest(MutationRequest):
    project_id: Positive
    workspace_id: Positive | None = None
    name: Annotated[StrictStr, Field(min_length=1, max_length=120)]
    definition: DefinitionText


class SaveDraftRequest(MutationRequest):
    expected_version: Positive
    definition: DefinitionText


class PublishWorkflowRequest(MutationRequest):
    expected_version: Positive
    idempotency_key: Identifier


class ArchiveWorkflowRequest(MutationRequest):
    expected_version: Positive


class RestoreWorkflowRequest(MutationRequest):
    expected_version: Positive
    revision_id: Identifier | None = None


class ValidateWorkflowRequest(ClosedModel):
    project_id: Positive
    workspace_id: Positive | None = None
    definition: DefinitionText


class ValidateDraftRequest(ClosedModel):
    expected_version: Positive
    definition: DefinitionText | None = None


class UpdateSettingsRequest(MutationRequest):
    project_id: Positive
    expected_version: Version
    settings: AutomationSettings = Field(
        json_schema_extra={"required": list(AutomationSettings.model_fields)}
    )

    @field_validator("settings", mode="before")
    @classmethod
    def complete_replacement(cls, value):
        if isinstance(value, dict) and set(value) != set(
            AutomationSettings.model_fields
        ):
            raise ValueError("Complete settings are required.")
        return value


class AdvanceEpochRequest(MutationRequest):
    project_id: Positive
    expected_version: Version


class AuthorityStamp(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    workflow_id: Identifier
    revision_id: Identifier
    project_id: Positive
    workspace_id: Positive
    principal_id: Identifier
    authentication_version: Positive
    membership_version: Positive
    authorization_epoch: Positive
    restore_epoch: Positive
    policy_digest: Digest
    advisory_policy_digest: Digest


EffectOperation = Literal["start", "claim", "dispatch", "consume"]
RetentionState = Literal["pending", "accepted", "unknown", "terminal"]


class UploadedSnapshotSource(UploadedSource):
    step_id: Identifier


class CollectedSnapshotSource(ClosedModel):
    kind: Literal["collected"]
    step_id: Identifier
    repository_id: Identifier
    commit_sha: CommitSha
    profile_digest: Digest


InputScalar = (
    Annotated[StrictStr, Field(max_length=1024)]
    | Annotated[StrictInt, Field(ge=-SAFE_INTEGER, le=SAFE_INTEGER)]
    | StrictBool
)


class SnapshotDocument(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    workflow_id: Identifier
    revision_id: Identifier
    revision_number: Positive
    project_id: Positive
    workspace_id: Positive
    environment: Identifier
    definition: Workflow
    definition_digest: Digest
    inputs: Annotated[
        dict[Identifier, InputScalar],
        Field(max_length=32, json_schema_extra={"additionalProperties": False}),
    ]
    input_digest: Digest
    sources: Annotated[
        list[
            Annotated[
                UploadedSnapshotSource | CollectedSnapshotSource,
                Field(discriminator="kind"),
            ]
        ],
        Field(max_length=50),
    ]
    policy: AutomationSettings
    advisory_policy: PolicyAdapterSettings
    authority: AuthorityStamp
    captured_at: Annotated[
        StrictStr,
        Field(
            min_length=20,
            max_length=20,
            pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        ),
    ]

    @field_validator("captured_at")
    @classmethod
    def real_utc_timestamp(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return value


@dataclass(frozen=True)
class SnapshotExport:
    """Authoritative bytes stay immutable; callers receive fresh decoded views."""

    canonical_bytes: bytes
    digest: str
    definition_digest: str
    input_digest: str

    @property
    def data(self) -> dict:
        import json

        return json.loads(self.canonical_bytes)

    @property
    def authority(self) -> AuthorityStamp:
        return AuthorityStamp.model_validate(self.data["authority"])

    @property
    def snapshot(self) -> SnapshotDocument:
        return SnapshotDocument.model_validate_json(self.canonical_bytes)


class CursorEnvelope(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    snapshot_id: Identifier
    next_cursor: Identifier | None
    limit: Annotated[StrictInt, Field(ge=1, le=100)]
    last_sequence: Annotated[StrictInt, Field(ge=0, le=SAFE_INTEGER)]
    truncated: StrictBool
    gap: StrictBool = False


def lifecycle_json_schema() -> dict:
    """Export the closed requests and in-process consumer value contracts."""
    schema = TypeAdapter(
        CreateWorkflowRequest
        | SaveDraftRequest
        | PublishWorkflowRequest
        | ArchiveWorkflowRequest
        | RestoreWorkflowRequest
        | ValidateWorkflowRequest
        | ValidateDraftRequest
        | UpdateSettingsRequest
        | AdvanceEpochRequest
        | SnapshotDocument
        | CursorEnvelope
    ).json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Workflow lifecycle v1 requests and consumer values"
    return schema
