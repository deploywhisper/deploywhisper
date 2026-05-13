"""Submission manifest construction for analysis reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.schemas import PendingAnalysis
from parsers.base import ParseBatchResult, ParsedFileResult
from services.intake_service import build_pending_analysis

ManifestStatus = Literal["accepted", "excluded", "failed", "sensitive"]
RedactionStatus = Literal["none", "redacted", "sensitive_blocked"]

_LEGACY_REDACTION_STATUS_MAP = {
    "not_redacted": "none",
    "filename_redacted": "redacted",
    "content_excluded": "sensitive_blocked",
}


class SubmissionManifestItem(BaseModel):
    name: str = Field(..., description="Normalized artifact name")
    tool: str = Field(..., description="Detected tool family")
    status: ManifestStatus = Field(..., description="Final manifest outcome")
    intake_status: str = Field(..., description="Upload classification outcome")
    parse_status: str | None = Field(
        default=None, description="Parser outcome when parsing was attempted"
    )
    message: str = Field(..., description="Human-readable outcome summary")
    partial: bool = Field(
        default=False, description="Whether this artifact reduced analysis coverage"
    )
    redaction_status: str = Field(
        default="none", description="Filename/content redaction outcome"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Submission source metadata"
    )


class SubmissionManifest(BaseModel):
    submitted_artifact_count: int = Field(
        default=0, description="Number of artifacts submitted"
    )
    accepted_artifact_count: int = Field(
        default=0, description="Artifacts accepted for parser analysis"
    )
    analyzed_artifact_count: int = Field(
        default=0, description="Accepted artifacts parsed into normalized changes"
    )
    excluded_artifact_count: int = Field(
        default=0, description="Artifacts excluded from parser analysis"
    )
    sensitive_artifact_count: int = Field(
        default=0, description="Sensitive artifacts excluded from unsafe handling"
    )
    failed_artifact_count: int = Field(
        default=0, description="Accepted artifacts that failed parser analysis"
    )
    partial_artifact_count: int = Field(
        default=0, description="Artifacts that made the analysis partial"
    )
    partial_analysis: bool = Field(
        default=False, description="Whether the analysis used partial coverage"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Submission-level source metadata"
    )
    redaction: dict[str, Any] = Field(
        default_factory=dict, description="Submission-level redaction metadata"
    )
    items: list[SubmissionManifestItem] = Field(
        default_factory=list, description="Per-artifact manifest entries"
    )


def _parse_results_by_name(
    parse_batch: ParseBatchResult,
) -> dict[str, ParsedFileResult]:
    return {file_result.file_name: file_result for file_result in parse_batch.files}


def _status_for_item(
    intake_status: str,
    parse_result: ParsedFileResult | None,
) -> ManifestStatus:
    if intake_status == "sensitive":
        return "sensitive"
    if parse_result is not None and parse_result.status == "parsed":
        return "accepted"
    if parse_result is not None and parse_result.status == "failed":
        return "failed"
    if intake_status != "ready":
        return "excluded"
    if parse_result is None:
        return "failed"
    return "excluded"


def _message_for_item(
    *,
    intake_message: str,
    status: ManifestStatus,
    parse_result: ParsedFileResult | None,
) -> str:
    if (
        parse_result is not None
        and parse_result.status == "failed"
        and parse_result.issue is not None
    ):
        tool_name = parse_result.tool.title()
        return f"{tool_name} artifact failed parser validation; analysis coverage is partial."
    if status == "accepted":
        tool_name = (parse_result.tool if parse_result is not None else "").title()
        if tool_name:
            return f"{tool_name} artifact parsed successfully and included in analysis."
        return "Artifact parsed successfully and included in analysis."
    if status == "failed":
        return "Accepted artifact was not parsed, so analysis coverage is partial."
    return intake_message


def normalize_manifest_redaction_status(status: Any) -> RedactionStatus:
    """Return the planned external redaction enum, accepting legacy persisted values."""
    normalized = _LEGACY_REDACTION_STATUS_MAP.get(str(status), str(status))
    if normalized in {"none", "redacted", "sensitive_blocked"}:
        return normalized  # type: ignore[return-value]
    return "none"


def normalize_submission_manifest_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Normalize legacy manifest payload values before exposing them externally."""
    normalized = dict(payload)
    normalized_items = []
    for item in normalized.get("items") or []:
        item_payload = dict(item)
        item_payload["redaction_status"] = normalize_manifest_redaction_status(
            item_payload.get("redaction_status")
        )
        normalized_items.append(item_payload)
    normalized["items"] = normalized_items
    return normalized


def _redaction_status(status: ManifestStatus) -> RedactionStatus:
    if status == "sensitive":
        return "sensitive_blocked"
    return "none"


def build_submission_manifest(
    files: list[tuple[str, bytes | None]],
    *,
    pending_analysis: PendingAnalysis | None = None,
    parse_batch: ParseBatchResult,
    audit_context: dict[str, Any] | None = None,
) -> SubmissionManifest:
    """Return a durable manifest for submitted artifacts and coverage outcomes."""
    pending = pending_analysis or build_pending_analysis(files)
    parse_by_name = _parse_results_by_name(parse_batch)
    context = audit_context or {}
    provenance = {
        "source_interface": context.get("source_interface"),
        "trigger_type": context.get("trigger_type"),
        "trigger_id": context.get("trigger_id"),
        "actor": context.get("actor"),
        "project_id": context.get("project_id"),
        "project_key": context.get("project_key"),
        "workspace_id": context.get("workspace_id"),
        "workspace_key": context.get("workspace_key"),
    }
    items: list[SubmissionManifestItem] = []
    for index, intake_item in enumerate(pending.items, start=1):
        parse_result = parse_by_name.get(intake_item.name)
        status = _status_for_item(intake_item.status, parse_result)
        partial = status != "accepted"
        items.append(
            SubmissionManifestItem(
                name=intake_item.name,
                tool=parse_result.tool
                if parse_result is not None
                else intake_item.tool,
                status=status,
                intake_status=intake_item.status,
                parse_status=(
                    parse_result.status if parse_result is not None else None
                ),
                message=_message_for_item(
                    intake_message=intake_item.message,
                    status=status,
                    parse_result=parse_result,
                ),
                partial=partial,
                redaction_status=_redaction_status(status),
                provenance={
                    **provenance,
                    "submitted_index": index,
                    "submitted_name": intake_item.name,
                },
            )
        )

    accepted_count = sum(1 for item in items if item.status in {"accepted", "failed"})
    analyzed_count = sum(1 for item in items if item.status == "accepted")
    sensitive_count = sum(1 for item in items if item.status == "sensitive")
    failed_count = sum(1 for item in items if item.status == "failed")
    partial_count = sum(1 for item in items if item.partial)
    return SubmissionManifest(
        submitted_artifact_count=len(items),
        accepted_artifact_count=accepted_count,
        analyzed_artifact_count=analyzed_count,
        excluded_artifact_count=sum(1 for item in items if item.status == "excluded"),
        sensitive_artifact_count=sensitive_count,
        failed_artifact_count=failed_count,
        partial_artifact_count=partial_count,
        partial_analysis=partial_count > 0,
        provenance=provenance,
        redaction={
            "filenames_redacted": False,
            "sensitive_content_excluded": sensitive_count > 0,
        },
        items=items,
    )
