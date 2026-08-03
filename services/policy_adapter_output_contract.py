"""Optional policy interpretation over immutable workflow-adapter output."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from services.adapter_output_contract import AdapterOutputContract


class PolicyAdapterStatus(str, Enum):
    """Supported downstream policy interpretations."""

    ADVISORY = "advisory"
    WARN = "warn"
    SOFT_BLOCK = "soft-block"
    HARD_BLOCK = "hard-block"


class PolicyAdapterReason(BaseModel):
    """Structured explanation for a downstream policy interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: StrictStr = Field(..., description="Stable adapter-owned reason code")
    message: StrictStr = Field(..., description="Human-readable policy explanation")

    @field_validator("code", "message")
    @classmethod
    def _normalize_nonblank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Policy adapter reasons must not be blank.")
        return normalized


class PolicyAdapterOutputContract(BaseModel):
    """Versioned policy interpretation that leaves canonical output advisory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: StrictStr = Field(
        default="v1", description="Policy adapter contract version"
    )
    status: PolicyAdapterStatus = Field(..., description="Local workflow decision")
    reasons: tuple[PolicyAdapterReason, ...] = Field(
        ..., min_length=1, description="Reasons for the policy status"
    )
    canonical_report_advisory: Literal[True] = Field(
        default=True,
        description="Confirms policy status does not alter canonical report semantics",
    )
    adapter_output: AdapterOutputContract = Field(
        ..., description="Immutable canonical summary and adapter metadata"
    )

    @field_validator("contract_version")
    @classmethod
    def _validate_contract_version(cls, value: str) -> str:
        if value != "v1":
            raise ValueError("Policy adapter contract version must be v1.")
        return value

    @model_validator(mode="after")
    def _require_advisory_canonical_report(self) -> PolicyAdapterOutputContract:
        summary = self.adapter_output.canonical_summary
        if not summary.advisory_only or summary.should_block:
            raise ValueError(
                "Policy adapters require an advisory, non-blocking canonical report."
            )
        return self


def build_policy_adapter_output_contract(
    adapter_output: AdapterOutputContract,
    *,
    status: PolicyAdapterStatus | str,
    reasons: tuple[PolicyAdapterReason | dict[str, str], ...],
) -> PolicyAdapterOutputContract:
    """Wrap canonical adapter output with a separate local policy interpretation."""
    return PolicyAdapterOutputContract(
        status=status,
        reasons=reasons,
        adapter_output=adapter_output,
    )
