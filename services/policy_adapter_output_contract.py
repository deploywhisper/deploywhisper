"""Optional policy interpretation over immutable workflow-adapter output."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

from services.adapter_output_contract import AdapterOutputContract
from services.policy_adapter_settings import (
    SEVERITY_RANK,
    PolicyAdapterSettings,
    PolicyAdapterStatus,
    PolicySeverity,
)
from services.project_service import normalize_project_key


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
        try:
            normalized.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "Policy adapter reasons must be valid UTF-8 text."
            ) from exc
        if not all(character.isprintable() for character in normalized):
            raise ValueError("Policy adapter reasons must contain printable text only.")
        if not any(not character.isspace() for character in normalized):
            raise ValueError("Policy adapter reasons must contain visible text.")
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
    applied_settings: PolicyAdapterSettings | None = Field(
        default=None,
        description="Resolved threshold and reporting defaults used for interpretation",
    )

    @field_validator("status", mode="before")
    @classmethod
    def _reject_coerced_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            raise ValueError("Policy adapter status must be a string.")
        return value

    @field_validator("reasons", mode="before")
    @classmethod
    def _reject_unordered_reasons(cls, value: Any) -> Any:
        if isinstance(value, set | frozenset):
            raise ValueError("Policy adapter reasons must be ordered.")
        return value

    @field_validator("canonical_report_advisory", mode="before")
    @classmethod
    def _require_literal_advisory_true(cls, value: Any) -> Any:
        if type(value) is not bool or value is not True:
            raise ValueError("canonical_report_advisory must be true.")
        return value

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
    applied_settings: PolicyAdapterSettings | None = None,
) -> PolicyAdapterOutputContract:
    """Wrap canonical adapter output with a separate local policy interpretation."""
    return PolicyAdapterOutputContract(
        status=status,
        reasons=reasons,
        adapter_output=adapter_output,
        applied_settings=applied_settings,
    )


def build_policy_adapter_output_from_settings(
    adapter_output: AdapterOutputContract,
    settings: PolicyAdapterSettings,
    *,
    resolved_project_key: str | None = None,
) -> PolicyAdapterOutputContract:
    """Interpret canonical severity with resolved defaults without mutating it."""
    metadata = adapter_output.adapter_metadata
    metadata_project_key = (
        normalize_project_key(metadata.project_key)
        if metadata.project_key is not None
        else None
    )
    normalized_resolved_key = (
        normalize_project_key(resolved_project_key)
        if resolved_project_key is not None
        else None
    )
    if (
        metadata_project_key is not None
        and normalized_resolved_key is not None
        and metadata_project_key != normalized_resolved_key
    ):
        raise ValueError("Resolved project does not match adapter metadata.")
    effective_project_key = metadata_project_key or normalized_resolved_key
    if effective_project_key is None:
        raise ValueError("Project ID adapter metadata requires a resolved project key.")
    if effective_project_key != normalize_project_key(settings.project_key):
        raise ValueError("Policy adapter settings do not match the adapter project.")
    if (
        settings.integration is not None
        and metadata.adapter.lower() != settings.integration
    ):
        raise ValueError(
            "Policy adapter settings do not match the adapter integration."
        )

    canonical_severity = str(adapter_output.canonical_summary.severity).strip().lower()
    try:
        severity = PolicySeverity(canonical_severity)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported canonical severity: {canonical_severity or 'blank'}."
        ) from exc

    matched_status: PolicyAdapterStatus | None = None
    matched_threshold: PolicySeverity | None = None
    for status, threshold in (
        (PolicyAdapterStatus.HARD_BLOCK, settings.hard_block_at),
        (PolicyAdapterStatus.SOFT_BLOCK, settings.soft_block_at),
        (PolicyAdapterStatus.WARN, settings.warn_at),
    ):
        if (
            threshold is not None
            and SEVERITY_RANK[severity] >= SEVERITY_RANK[threshold]
        ):
            matched_status = status
            matched_threshold = threshold
            break

    if matched_status is None:
        status = settings.reporting_default
        reason = PolicyAdapterReason(
            code="reporting_default_applied",
            message=(
                f"Canonical severity {canonical_severity or 'unknown'} did not meet a "
                f"configured threshold; reporting default {status.value} applied."
            ),
        )
    else:
        status = matched_status
        reason = PolicyAdapterReason(
            code="severity_threshold_matched",
            message=(
                f"Canonical severity {canonical_severity} met configured "
                f"{status.value} threshold {matched_threshold.value}."
            ),
        )

    return build_policy_adapter_output_contract(
        adapter_output,
        status=status,
        reasons=(reason,),
        applied_settings=settings,
    )
