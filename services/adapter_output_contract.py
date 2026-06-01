"""Canonical output contracts for workflow adapters."""

from __future__ import annotations

import math
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from services.analysis_service import (
    ShareSummary,
    ShareSummaryContext,
    ShareSummaryFinding,
    ShareSummaryJsonPayload,
)

AdapterMetadataValue = str | int | float | bool | None


class AdapterOutputContractError(ValueError):
    """Raised when adapter-specific output attempts to shadow canonical fields."""


class FrozenDict(dict):
    """JSON-serializable immutable dict used for adapter-owned maps."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("FrozenDict is immutable.")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __ior__(self, other: object) -> FrozenDict:
        self._immutable()
        return self


def _freeze_value(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, dict):
        return FrozenDict({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


class AdapterMetadata(BaseModel):
    """Workflow adapter identity and delivery context."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter: str = Field(..., description="Adapter family, such as gitlab or jenkins")
    format: str = Field(..., description="Adapter output format or destination type")
    version: str | None = Field(default=None, description="Adapter contract version")
    project_key: str | None = Field(default=None, description="Project key in scope")
    project_id: StrictInt | None = Field(
        default=None, description="Project ID in scope"
    )
    workspace_key: str | None = Field(
        default=None, description="Workspace key in scope"
    )
    workspace_id: StrictInt | None = Field(
        default=None, description="Workspace ID in scope"
    )
    invocation_id: str | None = Field(
        default=None, description="Adapter invocation or workflow run identifier"
    )
    delivery_target: str | None = Field(
        default=None, description="Adapter-specific delivery target"
    )
    extra: dict[str, AdapterMetadataValue] = Field(
        default_factory=dict,
        description="Adapter-specific metadata that does not shadow canonical fields",
    )

    @field_validator("adapter", "format")
    @classmethod
    def _normalize_required_label(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Adapter metadata labels must not be blank.")
        return normalized

    @field_validator(
        "version",
        "project_key",
        "workspace_key",
        "invocation_id",
        "delivery_target",
    )
    @classmethod
    def _normalize_optional_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Adapter metadata labels must not be blank.")
        return normalized

    @field_validator("project_id", "workspace_id")
    @classmethod
    def _validate_positive_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Adapter metadata IDs must be positive.")
        return value

    @model_validator(mode="after")
    def _validate_scope_and_extra_keys(self) -> AdapterMetadata:
        if self.project_key is None and self.project_id is None:
            raise ValueError("Adapter metadata requires project_key or project_id.")
        if self.project_key is not None and self.project_id is not None:
            raise ValueError(
                "Adapter metadata must use either project_key or project_id, not both."
            )
        if self.workspace_key is not None and self.workspace_id is not None:
            raise ValueError(
                "Adapter metadata must use either workspace_key or workspace_id, not both."
            )
        shadowed = sorted(
            key for key in self.extra if key in _reserved_adapter_fields()
        )
        if shadowed:
            joined = ", ".join(shadowed)
            raise ValueError(
                f"Adapter metadata extra cannot shadow canonical field(s): {joined}."
            )
        non_finite_numbers = sorted(
            key
            for key, value in self.extra.items()
            if isinstance(value, float) and not math.isfinite(value)
        )
        if non_finite_numbers:
            joined = ", ".join(non_finite_numbers)
            raise ValueError(
                f"Adapter metadata extra numbers must be finite: {joined}."
            )
        return self

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "extra", _freeze_value(dict(self.extra)))


class FrozenShareSummaryFinding(ShareSummaryFinding):
    """Immutable share-summary finding for adapter contracts."""

    model_config = ConfigDict(frozen=True)


class FrozenShareSummaryContext(ShareSummaryContext):
    """Immutable context summary for adapter contracts."""

    model_config = ConfigDict(frozen=True)


class FrozenShareSummaryJsonPayload(ShareSummaryJsonPayload):
    """Immutable machine-friendly share-summary payload for adapter contracts."""

    model_config = ConfigDict(frozen=True)

    top_findings: tuple[FrozenShareSummaryFinding, ...] = Field(
        default_factory=tuple, description="Top findings to surface"
    )
    context_completeness: FrozenShareSummaryContext = Field(
        ..., description="Context completeness summary"
    )


class AdapterCanonicalSummary(ShareSummary):
    """Immutable canonical report summary consumed by all workflow adapters."""

    model_config = ConfigDict(frozen=True)

    json_payload: FrozenShareSummaryJsonPayload = Field(
        ..., description="Machine-friendly share-summary payload"
    )


class AdapterOutputContract(BaseModel):
    """One report-output envelope for future delivery adapters."""

    model_config = ConfigDict(frozen=True)

    contract_version: StrictStr = Field(
        default="v1", description="Adapter contract version"
    )
    adapter_metadata: AdapterMetadata = Field(..., description="Adapter metadata")
    canonical_summary: AdapterCanonicalSummary = Field(
        ..., description="Immutable canonical summary"
    )
    adapter_payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-specific formatting and delivery fields",
    )

    @field_validator("contract_version")
    @classmethod
    def _validate_contract_version(cls, value: str) -> str:
        if value != "v1":
            raise ValueError("Adapter contract version must be v1.")
        return value

    @model_validator(mode="after")
    def _reject_payload_canonical_keys(self) -> AdapterOutputContract:
        _validate_adapter_payload(self.adapter_payload)
        return self

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(
            self, "adapter_payload", _freeze_value(dict(self.adapter_payload))
        )


def build_adapter_output_contract(
    share_summary: ShareSummary,
    adapter_metadata: AdapterMetadata | dict[str, Any],
    *,
    adapter_payload: dict[str, Any] | None = None,
) -> AdapterOutputContract:
    """Return a canonical adapter envelope without letting adapters rewrite core fields."""
    metadata = AdapterMetadata.model_validate(adapter_metadata)
    payload = dict(adapter_payload or {})
    _validate_adapter_payload(payload)

    canonical_summary = AdapterCanonicalSummary.model_validate(
        share_summary.model_dump()
    )
    return AdapterOutputContract(
        adapter_metadata=metadata,
        canonical_summary=canonical_summary,
        adapter_payload=payload,
    )


def _reserved_adapter_fields() -> frozenset[str]:
    return frozenset(
        {
            *AdapterCanonicalSummary.model_fields,
            *FrozenShareSummaryJsonPayload.model_fields,
            *FrozenShareSummaryFinding.model_fields,
            *FrozenShareSummaryContext.model_fields,
            "adapter_metadata",
            "adapter_payload",
            "canonical_summary",
            "contract_version",
        }
    )


def _validate_adapter_payload(payload: dict[str, Any]) -> None:
    _validate_json_payload_value(payload, "adapter_payload")


def _validate_json_payload_value(value: Any, path: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AdapterOutputContractError(
                    f"Adapter payload keys must be strings at {path}."
                )
            child_path = f"{path}.{key}"
            if key in _reserved_adapter_fields():
                raise AdapterOutputContractError(
                    f"Adapter payload cannot shadow canonical field at {child_path}."
                )
            _validate_json_payload_value(item, child_path)
        return

    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _validate_json_payload_value(item, f"{path}[{index}]")
        return

    if value is None or isinstance(value, str | bool | int):
        return

    if isinstance(value, float) and math.isfinite(value):
        return

    if isinstance(value, float):
        raise AdapterOutputContractError(
            f"Adapter payload numbers must be finite at {path}."
        )

    raise AdapterOutputContractError(
        f"Adapter payload values must be JSON-serializable at {path}."
    )
