"""Closed, screened approval review projections; none of these values grant authority."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from infra_automation.approval_eligibility import EligibilityResult
from infra_automation.contracts import (
    ClosedModel,
    Digest,
    Identifier,
    AuthorizationKind,
    CommitSha,
)
from infra_automation.decisions import DecisionBinding
from infra_automation.lifecycle import Positive
from infra_automation.state import UTCText

ReviewText = Annotated[StrictStr, Field(max_length=1024)]
ReviewReason = Annotated[StrictStr, Field(max_length=128)]


class ConfirmationRequirements(ClosedModel):
    required: StrictBool
    approve_phrase: Annotated[StrictStr, Field(max_length=256)] | None = None
    reject_phrase: Annotated[StrictStr, Field(max_length=256)] | None = None


class ApprovalReceipt(ClosedModel):
    id: Identifier
    run_id: Identifier
    step_id: Identifier
    project_id: Positive
    workspace_id: Positive
    requested_by: Identifier
    reviewer_id: Identifier | None
    decision_kind: Literal["independent-approval", "acknowledgement"] | None
    generation: Positive
    version: Positive
    status: Literal[
        "pending", "approved", "rejected", "invalidated", "expired", "superseded"
    ]
    reason: Annotated[StrictStr, Field(max_length=2048)] | None
    binding: DecisionBinding
    eligibility: EligibilityResult
    binding_digest: Digest
    deadline_at: UTCText
    created_at: UTCText
    decided_at: UTCText | None


class ReviewConfidence(ClosedModel):
    score: Annotated[StrictFloat, Field(ge=0, le=1)]
    level: Literal["low", "medium", "high"]
    context_score: Annotated[StrictFloat, Field(ge=0, le=1)]
    uncertainty: ReviewText | None = None
    context_todos: Annotated[tuple[ReviewText, ...], Field(max_length=20)] = ()
    partial_context: StrictBool
    insufficient_context: StrictBool


class ReviewBlastRadius(ClosedModel):
    direct_count: Annotated[StrictInt, Field(ge=0)]
    transitive_count: Annotated[StrictInt, Field(ge=0)]
    affected_services: Annotated[tuple[ReviewText, ...], Field(max_length=20)] = ()
    unmatched_resource_count: Annotated[StrictInt, Field(ge=0)]
    warning: ReviewText | None = None


class ReviewRollbackStep(ClosedModel):
    order: Annotated[StrictInt, Field(ge=0)]
    title: ReviewText
    estimated_minutes: Annotated[StrictInt, Field(ge=0)]
    critical: StrictBool


class ReviewRollback(ClosedModel):
    complexity: Literal["low", "medium", "high"]
    complexity_score: Annotated[StrictInt, Field(ge=1, le=5)]
    explanation: ReviewText
    warning: ReviewText | None = None
    steps: Annotated[tuple[ReviewRollbackStep, ...], Field(max_length=20)] = ()


class ApprovalReportSummary(ClosedModel):
    report_id: Positive
    schema_version: Literal["v2"]
    report_bytes_digest: Digest
    report_url: StrictStr
    recommendation: Literal["go", "caution", "no-go"]
    severity: Literal["low", "medium", "high", "critical"]
    should_block: Literal[False] = False
    confidence: ReviewConfidence
    blast_radius: ReviewBlastRadius
    rollback: ReviewRollback
    summary_limited: StrictBool = False

    @field_validator("should_block", mode="before")
    @classmethod
    def actual_advisory_boolean(cls, value):
        if type(value) is not bool or value is not False:
            raise ValueError("Canonical advisory flag must be boolean false")
        return value


class ApprovalActionSummary(ClosedModel):
    kind: Literal["registered_github_handoff"] = "registered_github_handoff"
    authorization_kind: AuthorizationKind
    canonical_target: Identifier
    environment: Identifier
    receiver_id: Identifier
    pipeline_repository_id: Identifier
    pipeline_workflow_id: Identifier
    pipeline_workflow_revision: CommitSha
    source_kind: Literal["uploaded", "collected"]
    source_repository_id: Identifier | None
    source_commit_sha: CommitSha | None
    unit_waves_digest: Digest
    payload_digest: Digest


class ApprovalDeadlines(ClosedModel):
    run: UTCText
    evidence: UTCText
    approval: UTCText
    source: UTCText | None
    custody: UTCText | None


class ApprovalDecisionContext(ClosedModel):
    status: Literal["eligible", "blocked", "unavailable", "decided"]
    can_submit: StrictBool
    evaluated_at: UTCText | None
    decision_kind: Literal["independent-approval", "acknowledgement"] | None
    confirmation: ConfirmationRequirements
    effective_deadline: UTCText
    deadlines: ApprovalDeadlines
    policy_status: Literal["advisory", "warn", "soft-block", "hard-block"] | None = None
    policy_passed: StrictBool | None = None
    reasons: Annotated[tuple[ReviewReason, ...], Field(max_length=50)] = ()
    limitations: Annotated[tuple[ReviewText, ...], Field(max_length=50)] = ()
    context_todos: Annotated[tuple[ReviewText, ...], Field(max_length=50)] = ()

    @model_validator(mode="after")
    def coherent_current_context(self):
        if self.can_submit != (self.status == "eligible"):
            raise ValueError("Only eligible current context can permit submission")
        if self.can_submit and (
            self.reasons
            or self.decision_kind is None
            or self.evaluated_at is None
            or self.evaluated_at >= self.effective_deadline
        ):
            raise ValueError("Current submission context is incomplete or expired")
        if self.evaluated_at is None and self.status != "unavailable":
            raise ValueError("Unknown clock must mark context unavailable")
        return self


class ApprovalAttribution(ClosedModel):
    event_id: Identifier
    principal_id: Identifier
    principal_type: Literal["human", "service"]
    role: Literal[
        "admin", "maintainer", "reviewer", "contributor", "read-only", "coordinator"
    ]
    project_id: Positive
    workspace_id: Positive
    reason: ReviewText
    occurred_at: UTCText
    before_digest: Digest | None
    after_digest: Digest
    state_digest_version: Literal[1] | None

    @field_validator("state_digest_version", mode="before")
    @classmethod
    def strict_digest_version(cls, value):
        if value is not None and (type(value) is not int or value != 1):
            raise ValueError("Unsupported decision state digest version")
        return value


class ApprovalReviewPacket(ClosedModel):
    version: Literal[1] = 1
    receipt: ApprovalReceipt
    report: ApprovalReportSummary
    action: ApprovalActionSummary
    context: ApprovalDecisionContext
    attribution: ApprovalAttribution | None
    can_export_audit: StrictBool
    screening_limited: StrictBool = False

    @field_validator("version", mode="before")
    @classmethod
    def strict_review_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Unsupported review packet version")
        return value

    @model_validator(mode="after")
    def pending_submission_only(self):
        if self.context.can_submit and self.receipt.status != "pending":
            raise ValueError("Recorded decisions cannot be resubmitted")
        return self
