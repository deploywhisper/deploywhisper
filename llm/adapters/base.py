"""Core provider adapter contracts for narrative generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class NarrativeProviderError(RuntimeError):
    """Raised when the configured narrative provider cannot be used."""


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    """Runtime configuration for a single provider invocation."""

    provider: str
    model: str
    api_base: str
    api_key: str | None = None
    local_mode: bool = False
    request_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class ProviderCapabilities:
    """Capability surface exposed by a provider adapter."""

    supports_structured_output: bool = True
    supports_remote_mcp: bool = False
    supports_local_mcp: bool = False
    supports_tool_approval: bool = False
    supports_local_only_mode: bool = False


class ProviderAdapter(Protocol):
    """Adapter interface for narrative-provider implementations."""

    def supports_provider(self, provider: str) -> bool:
        """Return whether this adapter can serve the given provider."""

    def generate_completion(
        self,
        messages: list[dict[str, str]],
        *,
        runtime: ProviderRuntimeConfig,
        completion_client: Callable[..., Any] | None = None,
    ) -> str:
        """Generate a completion for the given provider runtime."""

    def validate_configuration(
        self,
        *,
        runtime: ProviderRuntimeConfig,
        completion_client: Callable[..., Any] | None = None,
    ) -> None:
        """Validate the provider runtime or raise NarrativeProviderError."""

    def capabilities_for(self, provider: str) -> ProviderCapabilities:
        """Return capability metadata for the given provider."""
