"""Closed collection-v1 transport; provenance is distinct from report evidence."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr, model_validator

from infra_automation.contracts import ClosedModel, CommitSha, Digest, Identifier
from infra_automation.runner.protocol import TaskScope
from infra_automation.state import UTCText


class CollectionProfile(ClosedModel):
    profile_digest: Digest
    tool: Literal["opentofu", "terraform"]
    tool_version: Annotated[StrictStr, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    runner_version: Identifier
    tags: Annotated[list[Identifier], Field(max_length=32)]


class CollectionCustody(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    handle: Identifier
    raw_local_digest: Digest
    expires_at: UTCText


class CollectionProvenance(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    kind: Literal["collected"] = "collected"
    scope: TaskScope
    repository_id: Identifier
    commit_sha: CommitSha
    profile_digest: Digest
    tool: Literal["opentofu", "terraform"]
    tool_version: Annotated[StrictStr, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]
    command_digest: Digest
    argv_digest: Digest
    raw_local_digest: Digest
    sanitized_digest: Digest
    redaction_version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    exit_code: Annotated[StrictInt, Field(ge=0, le=2)]
    collected_at: UTCText
    source_deadline: UTCText
    custody: CollectionCustody
    limitation: Literal[
        "Collected provenance does not establish completeness or authorize an action."
    ] = "Collected provenance does not establish completeness or authorize an action."

    @model_validator(mode="after")
    def successful_exact_bytes(self):
        if (
            self.exit_code not in (0, 2)
            or self.raw_local_digest != self.custody.raw_local_digest
        ):
            raise ValueError("Invalid collection result.")
        return self


class CollectedArtifact(ClosedModel):
    name: Literal["plan.json"]
    content: Annotated[StrictStr, Field(min_length=1, max_length=131072)]


class CollectionUpload(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    provenance: CollectionProvenance
    artifacts: Annotated[list[CollectedArtifact], Field(min_length=1, max_length=1)]
