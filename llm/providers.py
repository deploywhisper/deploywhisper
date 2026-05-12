"""Provider selection and LLM invocation helpers."""

from __future__ import annotations

from typing import Any, Callable

from llm.adapters.base import (
    NarrativeProviderError,
    ProviderCapabilities,
    ProviderRuntimeConfig,
)
from llm.adapters.anthropic_adapter import AnthropicProviderAdapter
from llm.adapters.gemini_adapter import GeminiProviderAdapter
from llm.adapters.ollama_adapter import OllamaProviderAdapter
from llm.adapters.openai_compatible_adapter import OpenAICompatibleProviderAdapter
from llm.adapters.openai_adapter import OpenAIProviderAdapter
from llm.adapters.registry import ProviderAdapterRegistry

_provider_registry = ProviderAdapterRegistry()
_provider_registry.register(OllamaProviderAdapter())
_provider_registry.register(OpenAIProviderAdapter())
_provider_registry.register(AnthropicProviderAdapter())
_provider_registry.register(GeminiProviderAdapter())
_provider_registry.register(OpenAICompatibleProviderAdapter())


def get_provider_registry() -> ProviderAdapterRegistry:
    """Return the provider adapter registry."""
    return _provider_registry


def get_provider_adapter(provider: str):
    """Resolve the adapter responsible for the given provider."""
    return _provider_registry.resolve(provider)


def generate_completion(
    messages: list[dict[str, str]], completion_client: Callable[..., Any] | None = None
) -> str:
    raise NarrativeProviderError(
        "generate_completion requires resolved provider settings. "
        "Use generate_completion_with_settings(...) from a service boundary."
    )


def generate_completion_with_settings(
    messages: list[dict[str, str]],
    *,
    provider: str,
    model: str,
    api_base: str,
    api_key: str | None = None,
    local_mode: bool = False,
    request_timeout_seconds: float = 30.0,
    completion_client: Callable[..., Any] | None = None,
) -> str:
    runtime = ProviderRuntimeConfig(
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        local_mode=local_mode,
        request_timeout_seconds=request_timeout_seconds,
    )
    adapter = get_provider_adapter(provider)
    return adapter.generate_completion(
        messages,
        runtime=runtime,
        completion_client=completion_client,
    )


def validate_provider_configuration(
    *,
    provider: str,
    model: str,
    api_base: str,
    api_key: str | None = None,
    local_mode: bool = False,
    request_timeout_seconds: float = 30.0,
    completion_client: Callable[..., Any] | None = None,
) -> None:
    """Validate provider runtime settings through the adapter contract."""
    runtime = ProviderRuntimeConfig(
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        local_mode=local_mode,
        request_timeout_seconds=request_timeout_seconds,
    )
    adapter = get_provider_adapter(provider)
    adapter.validate_configuration(runtime=runtime, completion_client=completion_client)


def get_provider_capabilities(provider: str) -> ProviderCapabilities:
    """Return capability metadata for the requested provider."""
    adapter = get_provider_adapter(provider)
    return adapter.capabilities_for(provider)
