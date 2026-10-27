"""Closed upload and relational provenance values; canonical reports stay v2."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr

from infra_automation.contracts import ClosedModel, CommitSha, Digest, Identifier
from infra_automation.lifecycle import Positive
from infra_automation.state import RunRequest, UTCText


class ArtifactUpload(ClosedModel):
    name: Annotated[StrictStr, Field(min_length=1, max_length=256)]
    content: Annotated[StrictStr, Field(min_length=1, max_length=8388608)]


class PreflightRequest(ClosedModel):
    run: RunRequest
    artifacts: Annotated[list[ArtifactUpload], Field(min_length=1, max_length=32)]


class UploadedProvenance(ClosedModel):
    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    kind: Literal["uploaded"] = "uploaded"
    repository_source: Literal["unavailable"] = "unavailable"
    limitation: Literal[
        "Repository and immutable commit were not verified for uploaded evidence."
    ] = "Repository and immutable commit were not verified for uploaded evidence."


class PreflightLinkView(ClosedModel):
    id: Identifier
    run_id: Identifier
    attempt_id: Identifier
    manifest_id: Identifier
    report_id: Positive
    report_url: StrictStr
    provenance: UploadedProvenance
    limitations: Annotated[list[StrictStr], Field(max_length=50)]
    context_todos: Annotated[list[StrictStr], Field(max_length=50)]
    approval_eligible: Literal[False] = False


class SyntheticCollectionEnvelope(ClosedModel):
    """Operational v1 proof, never a machine credential or custody assertion."""

    version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    project_id: Positive
    workspace_id: Positive
    run_id: Identifier
    step_id: Identifier
    attempt_id: Identifier
    fence: Positive
    collector_id: Identifier
    repository_id: Identifier
    commit_sha: CommitSha
    profile_digest: Digest
    command_digest: Digest
    argv_digest: Digest
    raw_local_digest: Digest
    sanitized_digest: Digest
    redaction_version: Annotated[StrictInt, Field(ge=1, le=1)] = 1
    exit_code: Annotated[StrictInt, Field(ge=-255, le=255)]
    collected_at: UTCText
    source_deadline: UTCText
