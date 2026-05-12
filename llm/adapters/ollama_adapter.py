"""Direct Ollama adapter using the local HTTP API."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from llm.adapters._shared import (
    extract_text_content,
    normalize_prefixed_model,
    request_timeout_seconds,
)
from llm.adapters.base import (
    NarrativeProviderError,
    ProviderCapabilities,
    ProviderRuntimeConfig,
)

logger = logging.getLogger(__name__)


class OllamaProviderAdapter:
    """Serve local Ollama requests through the local HTTP API."""

    def supports_provider(self, provider: str) -> bool:
        return provider.lower() == "ollama"

    def _request_kwargs(
        self,
        messages: list[dict[str, str]],
        *,
        runtime: ProviderRuntimeConfig,
    ) -> dict[str, Any]:
        return {
            "model": runtime.model,
            "api_base": runtime.api_base,
            "messages": messages,
            "temperature": 0,
            "response_format": "json",
            "request_timeout_seconds": runtime.request_timeout_seconds,
        }

    def _sdk_completion(self, **kwargs: Any) -> Any:
        request_url = urljoin(f"{kwargs['api_base'].rstrip('/')}/", "api/chat")
        parsed_url = urlparse(request_url)
        if parsed_url.scheme not in {"http", "https"}:
            raise NarrativeProviderError(
                "Ollama API base must use http or https scheme"
            )
        payload = json.dumps(
            {
                "model": normalize_prefixed_model(str(kwargs["model"]), "ollama"),
                "messages": kwargs["messages"],
                "stream": False,
                "format": kwargs["response_format"],
                "options": {"temperature": kwargs["temperature"]},
            }
        ).encode("utf-8")
        request = Request(
            request_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            # Bandit B310 is safe here because scheme is restricted above.
            with urlopen(  # nosec B310
                request,
                timeout=request_timeout_seconds(
                    kwargs.get("request_timeout_seconds", 30.0)
                ),
            ) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore").strip()
            raise NarrativeProviderError(detail or str(exc)) from exc
        except URLError as exc:
            raise NarrativeProviderError(str(exc.reason)) from exc
        except Exception as exc:  # noqa: BLE001
            raise NarrativeProviderError(str(exc)) from exc
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise NarrativeProviderError(
                f"Ollama returned invalid JSON: {exc}"
            ) from exc

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
        return ProviderCapabilities(supports_local_only_mode=True)
