"""Typed request for conservative screened manifest payload retention."""

from __future__ import annotations

from typing import Literal

from infra_automation.lifecycle import MutationRequest, Positive, Reason
from infra_automation.state import UTCText
from infra_automation.contracts import ClosedModel, Digest, Identifier


class PurgeManifestRequest(MutationRequest):
    manifest_id: Identifier
    expected_run_version: Positive


class PurgeManifestBody(MutationRequest):
    expected_run_version: Positive


class RetentionReceipt(ClosedModel):
    version: Literal[1] = 1
    manifest_id: Identifier
    run_id: Identifier
    project_id: Positive
    workspace_id: Positive
    original_digest: Digest
    original_size: Positive
    actor_id: Identifier
    deleted_at: UTCText
    reason: Reason
    content_status: Literal["removed"] = "removed"
