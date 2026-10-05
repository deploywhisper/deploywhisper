"""Provider selection and LLM invocation helpers."""

from __future__ import annotations

import json
from urllib.parse import unquote, urlsplit

from llm.adapters._shared import request_timeout_seconds as validate_timeout
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
        "Provider model must not be blank.",
        "Provider model and API base must not contain credentials.",
        "Provider API base must be an absolute HTTP or HTTPS URL.",
        "Provider API base must not contain credentials, query parameters, or fragments.",
        "Provider API key is missing from environment-backed configuration.",
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


def validate_provider_settings_shape(
    *,
    provider: str,
    model: str,
    api_base: str,
    local_mode: bool,
    request_timeout_seconds: float,
    api_key: str | None = None,
    sensitive_values: tuple[str, ...] = (),
) -> None:
    """Check configuration through the adapter boundary without network access."""
    adapter = get_provider_adapter(provider)
    if local_mode and not adapter.capabilities_for(provider).supports_local_only_mode:
        raise NarrativeProviderError(
            "Local mode requires an Ollama/local provider path."
        )
    if not model.strip():
        raise NarrativeProviderError("Provider model must not be blank.")
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in api_base
    ):
        raise NarrativeProviderError(
            "Provider API base must be an absolute HTTP or HTTPS URL."
        )
    try:
        endpoint = urlsplit(api_base)
        valid_url = endpoint.scheme in {"http", "https"} and bool(endpoint.hostname)
        valid_url = valid_url and endpoint.port != 0
    except ValueError:
        valid_url = False
    if not valid_url:
        raise NarrativeProviderError(
            "Provider API base must be an absolute HTTP or HTTPS URL."
        )
    if (
        endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
    ):
        raise NarrativeProviderError(
            "Provider API base must not contain credentials, query parameters, or fragments."
        )
    sensitive_values = sensitive_values + ((api_key,) if api_key else ())
    if any(
        redact_text(value, sensitive_values=sensitive_values) != value
        for value in (model, api_base, unquote(model), unquote(api_base))
    ):
        raise NarrativeProviderError(
            "Provider model and API base must not contain credentials."
        )
    validate_timeout(request_timeout_seconds)


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
        validate_provider_settings_shape(
            provider=provider,
            model=model,
            api_base=api_base,
            local_mode=local_mode,
            request_timeout_seconds=request_timeout_seconds,
            api_key=api_key,
        )
        if provider.lower() != "ollama" and not api_key and completion_client is None:
            raise NarrativeProviderError(
                "Provider API key is missing from environment-backed configuration."
            )
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
        validate_provider_settings_shape(
            provider=provider,
            model=model,
            api_base=api_base,
            local_mode=local_mode,
            request_timeout_seconds=request_timeout_seconds,
            api_key=api_key,
        )
        if provider.lower() != "ollama" and not api_key and completion_client is None:
            raise NarrativeProviderError(
                "Provider API key is missing from environment-backed configuration."
            )
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
