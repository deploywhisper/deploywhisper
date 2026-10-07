"""Configured policy-adapter output generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.adapter_output_contract import AdapterOutputContract
from services.policy_adapter_output_contract import (
    PolicyAdapterOutputContract,
    build_policy_adapter_output_from_settings,
)
from services.project_service import resolve_project_reference
from services.settings_service import get_policy_adapter_settings
from services.policy_adapter_settings import PolicyAdapterStatus


_STATUS_RANK = {
    PolicyAdapterStatus.ADVISORY: 0,
    PolicyAdapterStatus.WARN: 1,
    PolicyAdapterStatus.SOFT_BLOCK: 2,
    PolicyAdapterStatus.HARD_BLOCK: 3,
}


class IntegrationEnforcementDecision(BaseModel):
    """Auditable integration decision kept separate from canonical analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["v1"] = Field(default="v1")
    configured_mode: PolicyAdapterStatus
    effective_status: PolicyAdapterStatus
    should_block: bool
    policy_output: PolicyAdapterOutputContract

    @model_validator(mode="after")
    def _validate_decision(self) -> IntegrationEnforcementDecision:
        settings = self.policy_output.applied_settings
        if settings is None or settings.enforcement_mode != self.configured_mode:
            raise ValueError(
                "Enforcement decision must match the policy output's applied settings."
            )
        expected_status = min(
            (self.policy_output.status, self.configured_mode),
            key=_STATUS_RANK.__getitem__,
        )
        if self.effective_status != expected_status:
            raise ValueError("Effective status must apply the configured mode ceiling.")
        expected_block = expected_status in {
            PolicyAdapterStatus.SOFT_BLOCK,
            PolicyAdapterStatus.HARD_BLOCK,
        }
        if self.should_block != expected_block:
            raise ValueError("Blocking flag must match the effective status.")
        return self


def build_configured_policy_adapter_output(
    adapter_output: AdapterOutputContract,
) -> PolicyAdapterOutputContract:
    """Resolve scoped defaults and apply them to adapter interpretation only."""
    metadata = adapter_output.adapter_metadata
    project = resolve_project_reference(
        project_id=metadata.project_id,
        project_key=metadata.project_key,
    )
    settings = get_policy_adapter_settings(
        project_key=project.project_key,
        integration=metadata.adapter,
    )
    return build_policy_adapter_output_from_settings(
        adapter_output,
        settings,
        resolved_project_key=project.project_key,
    )


def build_integration_enforcement_decision(
    adapter_output: AdapterOutputContract,
) -> IntegrationEnforcementDecision:
    """Apply the configured integration ceiling to raw policy interpretation."""
    policy_output = build_configured_policy_adapter_output(adapter_output)
    settings = policy_output.applied_settings
    if settings is None:
        raise ValueError("Configured policy output must include applied settings.")
    configured_mode = settings.enforcement_mode
    effective_status = min(
        (policy_output.status, configured_mode), key=_STATUS_RANK.__getitem__
    )
    return IntegrationEnforcementDecision(
        configured_mode=configured_mode,
        effective_status=effective_status,
        should_block=effective_status
        in {PolicyAdapterStatus.SOFT_BLOCK, PolicyAdapterStatus.HARD_BLOCK},
        policy_output=policy_output,
    )
