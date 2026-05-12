"""Direct Gemini SDK adapter."""

from __future__ import annotations

import logging
from typing import Any, Callable

from llm.adapters._shared import (
    extract_text_content,
    flatten_gemini_contents,
    normalize_prefixed_model,
    request_timeout_milliseconds,
    split_system_messages,
)
from llm.adapters.base import (
    NarrativeProviderError,
    ProviderCapabilities,
    ProviderRuntimeConfig,
)

logger = logging.getLogger(__name__)


class GeminiProviderAdapter:
    """Serve Gemini requests through the official google-genai SDK."""

    def supports_provider(self, provider: str) -> bool:
        return provider.lower() == "gemini"

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
        system_prompt, non_system_messages = split_system_messages(messages)
        kwargs: dict[str, Any] = {
            "model": normalize_prefixed_model(runtime.model, "gemini"),
            "api_base": runtime.api_base,
            "api_key": runtime.api_key,
            "contents": flatten_gemini_contents(non_system_messages),
            "response_mime_type": "application/json",
            "temperature": 0,
            "request_timeout_seconds": runtime.request_timeout_seconds,
        }
        if system_prompt:
            kwargs["system_instruction"] = system_prompt
        return kwargs

    def _sdk_completion(self, **kwargs: Any) -> Any:
        try:
            from google import genai
        except ImportError as exc:
            raise NarrativeProviderError(
                "The google-genai SDK is not installed. Install the story-required dependencies."
            ) from exc

        client_kwargs: dict[str, Any] = {}
        if kwargs.get("api_key"):
            client_kwargs["api_key"] = kwargs["api_key"]
        http_options: dict[str, Any] = {
            "timeout": request_timeout_milliseconds(
                kwargs.get("request_timeout_seconds", 30.0)
            )
        }
        if kwargs.get("api_base"):
            http_options["base_url"] = kwargs["api_base"]
        client_kwargs["http_options"] = http_options
        client = genai.Client(**client_kwargs)
        config: dict[str, Any] = {
            "response_mime_type": kwargs["response_mime_type"],
            "temperature": kwargs["temperature"],
        }
        if kwargs.get("system_instruction"):
            config["system_instruction"] = kwargs["system_instruction"]
        return client.models.generate_content(
            model=kwargs["model"],
            contents=kwargs["contents"],
            config=config,
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
