"""Closed immutable decision tuples and exact report export byte identity."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Annotated, Literal
from pydantic import Field, StrictInt, model_validator
from infra_automation.contracts import (
    ClosedModel,
    AuthorizationKind,
    Identifier,
    Digest,
    CommitSha,
)
from infra_automation.lifecycle import Positive
from infra_automation.preflight_contracts import UploadedProvenance
from infra_automation.state import UTCText

Version = Annotated[StrictInt, Field(ge=1, le=1)]


def instant(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def utc_now(now: datetime | None = None) -> datetime:
    value = now if now is not None else datetime.now(timezone.utc)
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware UTC clock is required.")
    return value.astimezone(timezone.utc)


class CollectedSource(ClosedModel):
    version: Version = 1
    kind: Literal["collected"] = "collected"
    repository_id: Identifier
    commit_sha: CommitSha
    collector_id: Identifier
    profile_digest: Digest
    screened_transport_digest: Digest
    redaction_version: Positive
    collected_at: UTCText
    source_deadline: UTCText

    @model_validator(mode="after")
    def finite_ttl(self):
        if (
            not 0
            < (
                instant(self.source_deadline) - instant(self.collected_at)
            ).total_seconds()
            <= 3600
        ):
            raise ValueError("Collection validity must be within 60 minutes.")
        return self


class Custody(ClosedModel):
    version: Version = 1
    handle: Identifier
    raw_local_digest: Digest
    expires_at: UTCText


class DecisionProvenance(ClosedModel):
    version: Version = 1
    authorization_kind: AuthorizationKind
    source: Annotated[UploadedProvenance | CollectedSource, Field(discriminator="kind")]
    custody: Custody | None = None

    @model_validator(mode="after")
    def source_custody(self):
        if self.authorization_kind == "exact_plan" and (
            not isinstance(self.source, CollectedSource) or self.custody is None
        ):
            raise ValueError("Exact plan requires collected evidence and custody.")
        if isinstance(self.source, UploadedProvenance) and self.custody is not None:
            raise ValueError("Uploads cannot manufacture custody.")
        return self


class DecisionBinding(ClosedModel):
    version: Version = 1
    authorization_kind: AuthorizationKind
    workflow_id: Identifier
    revision_id: Identifier
    workflow_revision_digest: Digest
    input_digest: Digest
    provenance: DecisionProvenance
    project_id: Positive
    workspace_id: Positive
    environment: Identifier
    canonical_target: Identifier
    receiver_id: Identifier
    pipeline_repository_id: Identifier
    pipeline_workflow_id: Identifier
    pipeline_workflow_revision: CommitSha
    report_id: Positive
    report_schema_version: Literal["v2"]
    report_bytes_digest: Digest
    policy_version: Positive
    policy_result: Literal["passed"]
    policy_digest: Digest
    unit_waves_digest: Digest
    screened_artifact_digests: Annotated[
        tuple[Digest, ...], Field(min_length=1, max_length=50)
    ]
    redaction_version: Positive
    payload_digest: Digest
    evidence_deadline: UTCText
    approval_deadline: UTCText
    authorization_epoch: Positive
    restore_epoch: Positive

    @model_validator(mode="after")
    def matching_source(self):
        if self.authorization_kind != self.provenance.authorization_kind:
            raise ValueError("Authorization source mismatch.")
        source = self.provenance.source
        if isinstance(source, CollectedSource):
            if (
                source.screened_transport_digest not in self.screened_artifact_digests
                or source.redaction_version != self.redaction_version
            ):
                raise ValueError("Screened evidence identity mismatch.")
            if instant(self.evidence_deadline) > instant(source.source_deadline):
                raise ValueError("Evidence cannot outlive its source.")
        return self


def binding_bytes(binding: DecisionBinding) -> bytes:
    # Revalidate to reject unchecked model_copy/model_construct values.
    typed = DecisionBinding.model_validate_json(
        binding.model_dump_json(warnings="error")
    )
    return json.dumps(
        typed.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def binding_digest(binding: DecisionBinding) -> str:
    return content_digest(binding_bytes(binding))


def effective_deadline(binding: DecisionBinding) -> datetime:
    deadlines = [instant(binding.evidence_deadline), instant(binding.approval_deadline)]
    if isinstance(binding.provenance.source, CollectedSource):
        deadlines.append(instant(binding.provenance.source.source_deadline))
    if binding.provenance.custody:
        deadlines.append(instant(binding.provenance.custody.expires_at))
    return min(deadlines)


def freeze_report_snapshot(report_payload: dict) -> tuple[bytes, str]:
    if (
        type(report_payload) is not dict
        or report_payload.get("report_schema_version") != "v2"
    ):
        raise ValueError("Canonical report v2 is required.")
    raw = json.dumps(
        report_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if not 0 < len(raw) <= 8388608:
        raise ValueError("Report export exceeds its 8 MiB limit.")
    return raw, content_digest(raw)
