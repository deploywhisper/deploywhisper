"""Evidence-domain Pydantic models."""

from __future__ import annotations

from typing import Literal
from urllib.parse import parse_qs, unquote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RiskSeverity = Literal["low", "medium", "high", "critical"]
DeployRecommendation = Literal["go", "caution", "no-go"]
EvidenceSourceType = Literal[
    "artifact",
    "topology",
    "incident",
    "history",
    "heuristic",
    "skill",
]
EvidenceSourceKind = EvidenceSourceType
DeterminismLevel = Literal["deterministic", "heuristic", "inferred"]
EvidenceRedactionStatus = Literal["none", "redacted", "sensitive_blocked"]


def _validate_string_list(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value]
    if any(not item for item in cleaned):
        raise ValueError("List entries must be non-empty strings.")
    return cleaned


def _parse_source_ref(source_ref: str) -> dict[str, str]:
    if "://" not in source_ref:
        return {"artifact": "", "resource": "", "operation": ""}
    remainder = source_ref.split("://", 1)[1]
    artifact_part, _, fragment = remainder.partition("#")
    resource_part, _, query = fragment.partition("?")
    operation = ""
    if query:
        action_values = parse_qs(query).get("action") or []
        operation = unquote(action_values[0]) if action_values else ""
    return {
        "artifact": unquote(artifact_part),
        "resource": unquote(resource_part),
        "operation": operation,
    }


class ContextCompleteness(BaseModel):
    """Frozen context quality inputs captured for one analysis."""

    model_config = ConfigDict(extra="forbid")

    topology_freshness_days: int | None = Field(default=None, ge=0)
    topology_last_imported_at: str | None = Field(default=None, min_length=1)
    incident_index_size: int = Field(default=0, ge=0)
    parser_success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    parser_success_by_tool: dict[str, float] = Field(default_factory=dict)
    context_score: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("parser_success_by_tool")
    @classmethod
    def _validate_parser_success_by_tool(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        for tool_name, score in value.items():
            normalized_name = str(tool_name).strip()
            if not normalized_name:
                raise ValueError(
                    "Parser success by tool requires non-empty tool names."
                )
            numeric_score = float(score)
            if numeric_score < 0.0 or numeric_score > 1.0:
                raise ValueError(
                    "Parser success by tool scores must be between 0 and 1."
                )
            cleaned[normalized_name] = numeric_score
        return cleaned


class SkillReference(BaseModel):
    """Skill identity captured in a context snapshot."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str = Field(..., min_length=1)
    version: str | None = Field(default=None, min_length=1)


class EvidenceItem(BaseModel):
    """Traceable evidence behind one or more findings."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(..., min_length=1)
    analysis_id: int = Field(
        ...,
        ge=0,
        description="Analysis identifier. Use 0 for pre-persistence evidence extraction.",
    )
    finding_id: str = Field(..., min_length=1)
    source_type: EvidenceSourceType
    source_ref: str = Field(..., min_length=1)
    artifact: str = Field(default="", description="Submitted artifact identifier")
    location: str = Field(default="", description="Inspectable artifact location")
    resource: str = Field(default="", description="Changed resource identifier")
    operation: str = Field(default="", description="Normalized change operation")
    project_id: int | None = Field(default=None, ge=1)
    project_key: str | None = Field(default=None, min_length=1)
    workspace_id: int | None = Field(default=None, ge=1)
    workspace_key: str | None = Field(default=None, min_length=1)
    source_kind: EvidenceSourceKind = Field(default="artifact")
    determinism_level: DeterminismLevel = Field(default="deterministic")
    redaction_status: EvidenceRedactionStatus = Field(default="none")
    summary: str = Field(..., min_length=1)
    severity_hint: RiskSeverity
    deterministic: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    related_change_ids: list[str] = Field(default_factory=list)

    @field_validator("related_change_ids")
    @classmethod
    def _validate_related_change_ids(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value)

    @model_validator(mode="after")
    def _populate_identity_fields(self) -> EvidenceItem:
        parsed = _parse_source_ref(self.source_ref)
        if not self.artifact and parsed["artifact"]:
            self.artifact = parsed["artifact"]
        if not self.resource and parsed["resource"]:
            self.resource = parsed["resource"]
        if not self.operation and parsed["operation"]:
            self.operation = parsed["operation"]
        if not self.location and self.artifact:
            self.location = (
                f"{self.artifact}#{self.resource}" if self.resource else self.artifact
            )
        if self.source_kind != self.source_type:
            self.source_kind = self.source_type
        expected_level: DeterminismLevel = (
            "deterministic" if self.deterministic else "inferred"
        )
        if self.determinism_level == "deterministic" and not self.deterministic:
            self.determinism_level = expected_level
        return self


class Finding(BaseModel):
    """Reviewer-facing deployment finding backed by evidence."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(..., min_length=1)
    analysis_id: int = Field(
        ...,
        ge=0,
        description="Analysis identifier. Use 0 for pre-persistence finding generation.",
    )
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: RiskSeverity
    category: str = Field(..., min_length=1)
    deterministic: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    uncertainty_note: str | None = Field(default=None, min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    skill_id: str | None = Field(default=None, min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def _validate_evidence_refs(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value)


class RiskAssessment(BaseModel):
    """Evidence-backed overall verdict for one analysis."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: int = Field(..., ge=1)
    overall_severity: RiskSeverity
    recommendation: DeployRecommendation
    score: int = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    top_risk_contributors: list[str] = Field(default_factory=list)
    context_completeness: ContextCompleteness = Field(
        default_factory=ContextCompleteness
    )

    @field_validator("top_risk_contributors")
    @classmethod
    def _validate_top_risk_contributors(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value)


class ContextSnapshot(BaseModel):
    """Frozen context inputs referenced by downstream scoring and review."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: int = Field(..., ge=1)
    topology_version: str | None = Field(default=None, min_length=1)
    incident_index_version: str | None = Field(default=None, min_length=1)
    history_window: str | None = Field(default=None, min_length=1)
    criticality_inputs: dict[str, str] = Field(default_factory=dict)
    owner_mapping_version: str | None = Field(default=None, min_length=1)
    skills_active: list[SkillReference] = Field(default_factory=list)
