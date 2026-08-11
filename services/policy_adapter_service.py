"""Configured policy-adapter output generation."""

from __future__ import annotations

from services.adapter_output_contract import AdapterOutputContract
from services.policy_adapter_output_contract import (
    PolicyAdapterOutputContract,
    build_policy_adapter_output_from_settings,
)
from services.project_service import resolve_project_reference
from services.settings_service import get_policy_adapter_settings


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
