"""Evidence-domain Pydantic models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


def _validate_string_list(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value]
    if any(not item for item in cleaned):
        raise ValueError("List entries must be non-empty strings.")
    return cleaned


class ContextCompleteness(BaseModel):
    """Frozen context quality inputs captured for one analysis."""

    model_config = ConfigDict(extra="forbid")

    topology_freshness_days: int | None = Field(default=None, ge=0)
    incident_index_size: int = Field(default=0, ge=0)
    parser_success_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    context_score: float = Field(default=1.0, ge=0.0, le=1.0)


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
    summary: str = Field(..., min_length=1)
    severity_hint: RiskSeverity
    deterministic: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    related_change_ids: list[str] = Field(default_factory=list)

    @field_validator("related_change_ids")
    @classmethod
    def _validate_related_change_ids(cls, value: list[str]) -> list[str]:
        return _validate_string_list(value)


class Finding(BaseModel):
    """Reviewer-facing deployment finding backed by evidence."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(..., min_length=1)
    analysis_id: int = Field(..., ge=1)
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
