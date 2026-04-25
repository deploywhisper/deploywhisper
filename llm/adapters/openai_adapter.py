"""Direct OpenAI SDK adapter."""

from __future__ import annotations

import logging
from typing import Any, Callable

from llm.adapters.base import (
    NarrativeProviderError,
    ProviderCapabilities,
    ProviderRuntimeConfig,
)
from llm.adapters._shared import (
    extract_text_content,
    normalize_prefixed_model,
    supports_only_temperature_one,
)

logger = logging.getLogger(__name__)


class OpenAIProviderAdapter:
    """Serve OpenAI requests through the official SDK."""

    def supports_provider(self, provider: str) -> bool:
        return provider.lower() == "openai"

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
        model = normalize_prefixed_model(runtime.model, "openai")
        kwargs: dict[str, Any] = {
            "model": model,
            "api_base": runtime.api_base,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": (
                1
                if supports_only_temperature_one(runtime.provider, runtime.model)
                else 0
            ),
        }
        if runtime.api_key:
            kwargs["api_key"] = runtime.api_key
        return kwargs

    def _sdk_completion(self, **kwargs: Any) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise NarrativeProviderError(
                "The openai SDK is not installed. Install the story-required dependencies."
            ) from exc

        client_kwargs: dict[str, Any] = {"base_url": kwargs["api_base"]}
        if kwargs.get("api_key"):
            client_kwargs["api_key"] = kwargs["api_key"]
        client = OpenAI(**client_kwargs)
        return client.chat.completions.create(
            model=kwargs["model"],
            messages=kwargs["messages"],
            response_format=kwargs["response_format"],
            temperature=kwargs["temperature"],
        )

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
        return extract_text_content(response)

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
