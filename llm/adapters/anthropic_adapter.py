"""Direct Anthropic SDK adapter."""

from __future__ import annotations

import logging
from typing import Any, Callable

from llm.adapters._shared import (
    extract_text_content,
    request_timeout_seconds,
    split_system_messages,
)
from llm.adapters.base import (
    NarrativeProviderError,
    ProviderCapabilities,
    ProviderRuntimeConfig,
)

logger = logging.getLogger(__name__)


class AnthropicProviderAdapter:
    """Serve Anthropic requests through the official SDK."""

    _JSON_PREFILL = "{"

    def supports_provider(self, provider: str) -> bool:
        return provider.lower() == "anthropic"

    def _request_kwargs(
        self,
        messages: list[dict[str, str]],
        *,
        runtime: ProviderRuntimeConfig,
    ) -> dict[str, Any]:
        if runtime.local_mode:
            raise NarrativeProviderError(
                "Local mode requires an Ollama/local provider path."
            )
        system_prompt, anthropic_messages = split_system_messages(messages)
        anthropic_messages = [*anthropic_messages, self._assistant_prefill_message()]
        kwargs: dict[str, Any] = {
            "model": runtime.model,
            "api_base": runtime.api_base,
            "messages": anthropic_messages,
            "temperature": 0,
            "max_tokens": 1024,
            "request_timeout_seconds": runtime.request_timeout_seconds,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if runtime.api_key:
            kwargs["api_key"] = runtime.api_key
        return kwargs

    def _assistant_prefill_message(self) -> dict[str, str]:
        """Use Anthropic's documented assistant-prefill path to force JSON output."""
        return {"role": "assistant", "content": self._JSON_PREFILL}

    def _sdk_completion(self, **kwargs: Any) -> Any:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise NarrativeProviderError(
                "The anthropic SDK is not installed. Install the story-required dependencies."
            ) from exc

        client_kwargs: dict[str, Any] = {
            "base_url": kwargs["api_base"],
            "timeout": request_timeout_seconds(
                kwargs.get("request_timeout_seconds", 30.0)
            ),
        }
        if kwargs.get("api_key"):
            client_kwargs["api_key"] = kwargs["api_key"]
        client = Anthropic(**client_kwargs)
        request_kwargs = {
            "model": kwargs["model"],
            "messages": kwargs["messages"],
            "temperature": kwargs["temperature"],
            "max_tokens": kwargs["max_tokens"],
        }
        if kwargs.get("system"):
            request_kwargs["system"] = kwargs["system"]
        return client.messages.create(**request_kwargs)

    def generate_completion(
        self,
        messages: list[dict[str, str]],
        *,
        runtime: ProviderRuntimeConfig,
        completion_client: Callable[..., Any] | None = None,
    ) -> str:
        kwargs = self._request_kwargs(messages, runtime=runtime)
        client = completion_client or self._sdk_completion
        try:
            logger.info(
                "llm_completion_request provider=%s model=%s local_mode=%s message_count=%s",
                runtime.provider,
                runtime.model,
                runtime.local_mode,
                len(messages),
            )
            response = client(**kwargs)
        except NarrativeProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise NarrativeProviderError(str(exc)) from exc
        text = extract_text_content(response).lstrip()
        if text.startswith(self._JSON_PREFILL):
            return text
        return f"{self._JSON_PREFILL}{text}"

    def validate_configuration(
        self,
        *,
        runtime: ProviderRuntimeConfig,
        completion_client: Callable[..., Any] | None = None,
    ) -> None:
        self.generate_completion(
            [
                {"role": "system", "content": "Return a JSON object."},
                {"role": "user", "content": "{}"},
            ],
            runtime=runtime,
            completion_client=completion_client,
        )

    def capabilities_for(self, provider: str) -> ProviderCapabilities:
        if not self.supports_provider(provider):
            raise NarrativeProviderError(f"Unsupported narrative provider: {provider}")
        return ProviderCapabilities()
