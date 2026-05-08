"""Shared parser data structures."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _build_change_id(
    source_file: str,
    tool: str,
    resource_id: str,
    action: str,
    occurrence: int = 0,
) -> str:
    seed = "|".join((source_file, tool, resource_id, action, str(occurrence)))
    return f"chg-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(nested) for key, nested in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe_value(nested) for nested in value]
    return str(value)


class UnifiedChange(BaseModel):
    change_id: str = Field(
        default="",
        description="Stable identifier for this normalized change.",
    )
    source_file: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Source tool name")
    resource_id: str = Field(..., description="Resource identifier")
    action: str = Field(..., description="Change action")
    summary: str = Field(..., description="Human-readable summary")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional parser-specific normalized metadata",
    )

    @field_validator("metadata", mode="before")
    @classmethod
    def _sanitize_metadata(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        safe = _json_safe_value(value)
        return safe if isinstance(safe, dict) else {}

    @model_validator(mode="after")
    def _populate_change_id(self) -> UnifiedChange:
        if not self.change_id:
            self.change_id = _build_change_id(
                self.source_file,
                self.tool,
                self.resource_id,
                self.action,
            )
        return self


NormalizedChange = UnifiedChange
build_change_id = _build_change_id
NON_MUTATING_ACTIONS = {"no-op", "read"}


def normalize_change_action(action: str | list[str]) -> str:
    """Collapse parser action vocabulary into shared lifecycle actions."""
    if isinstance(action, str):
        parts = {part.strip() for part in action.split("+") if part.strip()}
    else:
        parts = {str(part).strip() for part in action if str(part).strip()}
    if parts == {"no-op"}:
        return "no-op"
    if parts == {"read"}:
        return "read"
    if "replace" in parts or ("create" in parts and {"delete", "destroy"} & parts):
        return "replace"
    if {"delete", "destroy"} & parts:
        return "destroy"
    if {"modify", "update"} & parts:
        return "modify"
    if "create" in parts:
        return "create"
    if "apply" in parts:
        return "apply"
    return "modify"


def is_non_mutating_action(action: str) -> bool:
    return normalize_change_action(action) in NON_MUTATING_ACTIONS


ParseStatus = Literal["parsed", "failed", "skipped"]


class ParseIssue(BaseModel):
    file_name: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Detected or expected tool")
    message: str = Field(..., description="Why parsing failed or was partial")


class ParsedFileResult(BaseModel):
    file_name: str = Field(..., description="Source file name")
    tool: str = Field(..., description="Detected tool")
    status: ParseStatus = Field(..., description="Parse outcome for this file")
    changes: list[UnifiedChange] = Field(
        default_factory=list, description="Normalized changes"
    )
    issue: ParseIssue | None = Field(
        default=None, description="Failure context if parsing failed"
    )


class ParseBatchResult(BaseModel):
    files: list[ParsedFileResult] = Field(
        default_factory=list, description="Per-file parse results"
    )

    @property
    def total_change_count(self) -> int:
        return sum(len(file_result.changes) for file_result in self.files)

    @property
    def failed_count(self) -> int:
        return sum(1 for file_result in self.files if file_result.status == "failed")

    @property
    def parsed_count(self) -> int:
        return sum(1 for file_result in self.files if file_result.status == "parsed")

    @property
    def skipped_count(self) -> int:
        return sum(1 for file_result in self.files if file_result.status == "skipped")

    @property
    def has_partial_context(self) -> bool:
        return self.failed_count > 0
