"""Registry for provider adapters."""

from __future__ import annotations

from llm.adapters.base import NarrativeProviderError, ProviderAdapter


class ProviderAdapterRegistry:
    """Resolve provider adapters for the narrative boundary."""

    def __init__(self) -> None:
        self._adapters: list[ProviderAdapter] = []

    def register(self, adapter: ProviderAdapter) -> None:
        """Register an adapter if it has not already been added."""
        if adapter not in self._adapters:
            self._adapters.append(adapter)

    def resolve(self, provider: str) -> ProviderAdapter:
        """Return the adapter that supports the given provider."""
        normalized = provider.lower()
        for adapter in self._adapters:
            if adapter.supports_provider(normalized):
                return adapter
        raise NarrativeProviderError(f"Unsupported narrative provider: {provider}")
