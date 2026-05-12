"""Shared helpers for provider adapters."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from llm.adapters.base import NarrativeProviderError, ProviderRuntimeConfig


def ensure_remote_runtime(runtime: ProviderRuntimeConfig) -> None:
    """Reject local-only mode for hosted providers."""
    if runtime.local_mode:
        raise NarrativeProviderError(
            "Local mode requires an Ollama/local provider path."
        )


def normalize_prefixed_model(model: str, prefix: str) -> str:
    """Strip provider prefixes from persisted model names when SDKs expect raw ids."""
    normalized_prefix = f"{prefix.lower()}/"
    if model.lower().startswith(normalized_prefix):
        return model[len(normalized_prefix) :]
    return model


def split_system_messages(
    messages: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    """Extract system instructions from a mixed role message list."""
    system_parts: list[str] = []
    non_system_messages: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        if role == "system":
            system_parts.append(str(message.get("content") or ""))
            continue
        non_system_messages.append(
            {
                "role": str(message.get("role") or "user"),
                "content": str(message.get("content") or ""),
            }
        )
    return "\n\n".join(part for part in system_parts if part), non_system_messages


def flatten_gemini_contents(messages: list[dict[str, str]]) -> str:
    """Collapse chat messages into a single prompt for Gemini generation."""
    chunks: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").strip().upper()
        content = str(message.get("content") or "").strip()
        if content:
            chunks.append(f"{role}:\n{content}")
    return "\n\n".join(chunks)


def request_timeout_seconds(value: Any) -> float:
    """Validate and normalize a hosted-provider request timeout."""
    if isinstance(value, bool):
        raise NarrativeProviderError(
            "Request timeout must be a positive finite number."
        )
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise NarrativeProviderError(
            "Request timeout must be a positive finite number."
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise NarrativeProviderError(
            "Request timeout must be a positive finite number."
        )
    return timeout


def request_timeout_milliseconds(value: Any) -> int:
    """Return a positive millisecond timeout for SDKs that use millisecond units."""
    milliseconds = request_timeout_seconds(value) * 1000
    if not math.isfinite(milliseconds):
        raise NarrativeProviderError(
            "Request timeout must be a positive finite number."
        )
    return max(1, math.ceil(milliseconds))


def extract_text_content(response: Any) -> str:
    """Extract textual content from SDK or test-double responses."""
    if isinstance(response, str):
        return response

    text_value = getattr(response, "text", None)
    if isinstance(text_value, str) and text_value:
        return text_value

    message = getattr(response, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if isinstance(content, str) and content:
            return content

    choices = getattr(response, "choices", None)
    if isinstance(choices, Iterable):
        choices_list = list(choices)
        if choices_list:
            choice_message = getattr(choices_list[0], "message", None)
            content = getattr(choice_message, "content", None)
            if isinstance(content, str) and content:
                return content

    content_blocks = getattr(response, "content", None)
    if isinstance(content_blocks, Iterable) and not isinstance(
        content_blocks, (str, bytes)
    ):
        parts: list[str] = []
        for block in content_blocks:
            block_type = getattr(block, "type", None)
            block_text = getattr(block, "text", None)
            if block_type == "text" and isinstance(block_text, str):
                parts.append(block_text)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "".join(parts)

    if isinstance(response, dict):
        text = response.get("text")
        if isinstance(text, str) and text:
            return text
        message_dict = response.get("message")
        if isinstance(message_dict, dict):
            content = message_dict.get("content")
            if isinstance(content, str) and content:
                return content
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message_dict = choices[0].get("message")
            if isinstance(message_dict, dict):
                content = message_dict.get("content")
                if isinstance(content, str) and content:
                    return content
        content_blocks = response.get("content")
        if isinstance(content_blocks, list):
            parts = [
                str(block.get("text"))
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            joined = "".join(parts)
            if joined:
                return joined

    raise NarrativeProviderError("Provider response did not include text content.")


def supports_only_temperature_one(provider: str, model: str) -> bool:
    """OpenAI GPT-5 models currently require temperature 1."""
    normalized_provider = provider.lower()
    normalized_model = model.lower()
    return normalized_provider == "openai" and (
        normalized_model.startswith("gpt-5")
        or normalized_model.startswith("openai/gpt-5")
    )
