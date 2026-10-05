"""Provider selection and LLM invocation helpers."""

from __future__ import annotations

import json
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
from services.content_security import redact_text, redact_value

SENSITIVE_RESPONSE_NOTICE = (
    "Provider response blocked because sensitive content was detected."
)
_SAFE_ERROR_MESSAGES = frozenset(
    {
        SENSITIVE_RESPONSE_NOTICE,
        "Local mode requires an Ollama/local provider path.",
        "Request timeout must be a positive finite number.",
        "Ollama API base must use http or https scheme",
        "Provider response did not include text content.",
        "Narrative provider returned empty output.",
        "Narrative provider returned unsafe or contradictory deployment guidance.",
        "The openai SDK is not installed. Install the story-required dependencies.",
        "The anthropic SDK is not installed. Install the story-required dependencies.",
        "The google-genai SDK is not installed. Install the story-required dependencies.",
    }
)


def safe_error_message(exc: Exception) -> str:
    """Expose known notices or an exception class, never arbitrary provider content."""
    message = str(exc)
    if message in _SAFE_ERROR_MESSAGES:
        return message
    cause = exc.__cause__ if isinstance(exc.__cause__, Exception) else exc
    return f"Provider operation failed ({type(cause).__name__})."


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
    try:
        adapter = get_provider_adapter(provider)
        safe_messages = redact_value(
            messages, sensitive_values=(api_key,) if api_key else ()
        )
        for message, safe_message in zip(messages, safe_messages):
            try:
                message_payload = json.loads(message["content"])
            except (ValueError, TypeError, KeyError):
                continue
            safe_payload = redact_value(
                message_payload, sensitive_values=(api_key,) if api_key else ()
            )
            if safe_payload != message_payload:
                safe_message["content"] = redact_text(
                    json.dumps(safe_payload),
                    sensitive_values=(api_key,) if api_key else (),
                )
        content = adapter.generate_completion(
            safe_messages,
            runtime=runtime,
            completion_client=completion_client,
        )
        if (
            redact_text(content, sensitive_values=(api_key,) if api_key else ())
            != content
        ):
            raise NarrativeProviderError(SENSITIVE_RESPONSE_NOTICE)
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            payload = None
        if (
            redact_value(payload, sensitive_values=(api_key,) if api_key else ())
            != payload
        ):
            raise NarrativeProviderError(SENSITIVE_RESPONSE_NOTICE)
        return content
    except Exception as exc:  # noqa: BLE001
        raise NarrativeProviderError(safe_error_message(exc)) from None


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
    try:
        adapter = get_provider_adapter(provider)
        adapter.validate_configuration(
            runtime=runtime, completion_client=completion_client
        )
    except Exception as exc:  # noqa: BLE001
        raise NarrativeProviderError(safe_error_message(exc)) from None


def get_provider_capabilities(provider: str) -> ProviderCapabilities:
    """Return capability metadata for the requested provider."""
    adapter = get_provider_adapter(provider)
    return adapter.capabilities_for(provider)
