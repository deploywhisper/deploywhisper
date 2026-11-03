"""Closed internal GitHub facts; these do not extend frozen receiver-v1 wire."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StrictStr, model_validator

from infra_automation.contracts import ClosedModel, CommitSha, Digest, Identifier
from infra_automation.decisions import Version
from infra_automation.lifecycle import Positive


GithubURL = Annotated[StrictStr, Field(min_length=1, max_length=1024)]
GithubStatus = Literal[
    "queued", "in_progress", "completed", "waiting", "pending", "requested"
]
GithubConclusion = Literal[
    "success",
    "failure",
    "neutral",
    "cancelled",
    "skipped",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
]


class DispatchAcceptance(ClosedModel):
    """A correlated run exists; no counted action or completion is implied."""

    version: Version = 1
    api_version: Literal["2026-03-10"] = "2026-03-10"
    state: Literal["accepted"] = "accepted"
    operation_id: Identifier
    binding_digest: Digest
    repository_id: Identifier
    workflow_id: Identifier
    workflow_revision: CommitSha
    workflow_ref: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    run_id: Positive
    run_url: GithubURL
    html_url: GithubURL


class GithubRunObservation(ClosedModel):
    """Bounded polled facts, separate from authenticated receiver outcomes."""

    version: Version = 1
    api_version: Literal["2026-03-10"] = "2026-03-10"
    run_id: Positive
    repository_id: Identifier
    workflow_id: Identifier
    workflow_revision: CommitSha
    workflow_ref: Annotated[StrictStr, Field(min_length=1, max_length=128)]
    run_url: GithubURL
    html_url: GithubURL
    status: GithubStatus
    conclusion: GithubConclusion | None

    @model_validator(mode="after")
    def completed_facts(self):
        if (self.status == "completed") != (self.conclusion is not None):
            raise ValueError("GitHub completion requires a terminal conclusion.")
        return self
