"""Shared parser data structures."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def _build_change_id(
    source_file: str,
    tool: str,
    resource_id: str,
    action: str,
    occurrence: int = 0,
) -> str:
    seed = "|".join((source_file, tool, resource_id, action, str(occurrence)))
    return f"chg-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"


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
