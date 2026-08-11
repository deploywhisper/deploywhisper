"""Pure settings contracts for optional policy-adapter interpretation."""

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


class PolicyAdapterStatus(str, Enum):
    """Supported downstream policy interpretations."""

    ADVISORY = "advisory"
    WARN = "warn"
    SOFT_BLOCK = "soft-block"
    HARD_BLOCK = "hard-block"


class PolicySeverity(str, Enum):
    """Canonical severities policy thresholds may interpret."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_RANK = {
    PolicySeverity.LOW: 1,
    PolicySeverity.MEDIUM: 2,
    PolicySeverity.HIGH: 3,
    PolicySeverity.CRITICAL: 4,
}


class PolicyAdapterSettingsIntegrityError(RuntimeError):
    """Raised when persisted policy settings fail their storage contract."""


class PolicyAdapterSettings(BaseModel):
    """Resolved project or integration defaults for policy interpretation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_key: StrictStr = Field(..., description="Project owning these defaults")
    integration: StrictStr | None = Field(
        default=None,
        description="Optional integration identifier for an overriding default",
    )
    source: Literal["built-in", "project", "integration"] = Field(
        ..., description="Scope from which the effective defaults were resolved"
    )
    warn_at: PolicySeverity | None = Field(
        default=PolicySeverity.MEDIUM,
        description="Minimum canonical severity interpreted as warn",
    )
    soft_block_at: PolicySeverity | None = Field(
        default=PolicySeverity.HIGH,
        description="Minimum canonical severity interpreted as soft-block",
    )
    hard_block_at: PolicySeverity | None = Field(
        default=PolicySeverity.CRITICAL,
        description="Minimum canonical severity interpreted as hard-block",
    )
    reporting_default: PolicyAdapterStatus = Field(
        default=PolicyAdapterStatus.ADVISORY,
        description="Adapter status reported when no severity threshold is met",
    )

    @field_validator("project_key", "integration")
    @classmethod
    def _normalize_scope_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Policy adapter scope labels must not be blank.")
        if not all(
            character.isalnum() or character in {"-", "_", "."}
            for character in normalized
        ):
            raise ValueError(
                "Policy adapter scope labels may contain letters, numbers, '.', '_', and '-'."
            )
        return normalized

    @model_validator(mode="after")
    def _validate_defaults(self) -> PolicyAdapterSettings:
        if self.reporting_default not in {
            PolicyAdapterStatus.ADVISORY,
            PolicyAdapterStatus.WARN,
        }:
            raise ValueError("reporting_default must be advisory or warn.")
        if self.source == "integration" and self.integration is None:
            raise ValueError("Integration settings require an integration identifier.")
        if self.source == "project" and self.integration is not None:
            raise ValueError(
                "Project settings cannot include an integration identifier."
            )
        if self.source == "built-in" and (
            self.integration is not None
            or self.warn_at != PolicySeverity.MEDIUM
            or self.soft_block_at != PolicySeverity.HIGH
            or self.hard_block_at != PolicySeverity.CRITICAL
            or self.reporting_default != PolicyAdapterStatus.ADVISORY
        ):
            raise ValueError(
                "Built-in settings must use the fixed advisory-first defaults."
            )

        configured = [
            threshold
            for threshold in (self.warn_at, self.soft_block_at, self.hard_block_at)
            if threshold is not None
        ]
        if any(
            SEVERITY_RANK[current] >= SEVERITY_RANK[next_threshold]
            for current, next_threshold in zip(configured, configured[1:])
        ):
            raise ValueError(
                "Configured warn, soft-block, and hard-block thresholds must increase in severity."
            )
        return self
