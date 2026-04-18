"""Provider selection and LLM invocation helpers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from litellm import completion

logger = logging.getLogger(__name__)


class NarrativeProviderError(RuntimeError):
    """Raised when the configured narrative provider cannot be used."""


def _supports_only_temperature_one(provider: str, model: str) -> bool:
    normalized_provider = provider.lower()
    normalized_model = model.lower()
    return normalized_provider == "openai" and (
        normalized_model.startswith("gpt-5")
        or normalized_model.startswith("openai/gpt-5")
    )


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
    completion_client: Callable[..., Any] | None = None,
) -> str:
    client = completion_client or completion
    temperature = 1 if _supports_only_temperature_one(provider, model) else 0
    kwargs: dict[str, Any] = {
        "model": model,
        "api_base": api_base,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }
    if local_mode and provider != "ollama":
        raise NarrativeProviderError(
            "Local mode requires an Ollama/local provider path."
        )
    if api_key and not local_mode:
        kwargs["api_key"] = api_key
    try:
        logger.info(
            "llm_completion_request provider=%s model=%s local_mode=%s message_count=%s",
            provider,
            model,
            local_mode,
            len(messages),
        )
        response = client(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise NarrativeProviderError(str(exc)) from exc

    return response.choices[0].message.content
