"""Tests for the compatibility provider adapter."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from llm.adapters.base import NarrativeProviderError, ProviderRuntimeConfig
from llm.adapters.openai_compatible_adapter import OpenAICompatibleProviderAdapter


class OpenAICompatibleProviderAdapterTests(unittest.TestCase):
    def test_compatibility_adapter_supports_lower_priority_providers(self) -> None:
        adapter = OpenAICompatibleProviderAdapter()

        self.assertTrue(adapter.supports_provider("openrouter"))
        self.assertTrue(adapter.supports_provider("groq"))
        self.assertTrue(adapter.supports_provider("xai"))
        self.assertFalse(adapter.supports_provider("openai"))

    def test_compatibility_adapter_normalizes_provider_prefixed_models(self) -> None:
        captured: dict[str, object] = {}
        adapter = OpenAICompatibleProviderAdapter()

        content = adapter.generate_completion(
            [{"role": "user", "content": "{}"}],
            runtime=ProviderRuntimeConfig(
                provider="openrouter",
                model="openrouter/openai/gpt-4.1-mini",
                api_base="https://openrouter.ai/api/v1",
                api_key="sk-test",
                local_mode=False,
            ),
            completion_client=lambda **kwargs: (
                captured.update(kwargs)
                or SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='{"opening_sentence":"ok"}')
                        )
                    ]
                )
            ),
        )

        self.assertEqual(content, '{"opening_sentence":"ok"}')
        self.assertEqual(captured["model"], "openai/gpt-4.1-mini")
        self.assertEqual(captured["api_base"], "https://openrouter.ai/api/v1")
        self.assertEqual(captured["api_key"], "sk-test")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertEqual(captured["temperature"], 0)
        self.assertEqual(captured["request_timeout_seconds"], 30.0)

    def test_compatibility_adapter_rejects_local_mode(self) -> None:
        adapter = OpenAICompatibleProviderAdapter()

        with self.assertRaises(NarrativeProviderError):
            adapter.generate_completion(
                [{"role": "user", "content": "{}"}],
                runtime=ProviderRuntimeConfig(
                    provider="groq",
                    model="groq/llama-3.3-70b-versatile",
                    api_base="https://api.groq.com/openai/v1",
                    api_key="sk-test",
                    local_mode=True,
                ),
                completion_client=lambda **_: None,
            )

    @patch("openai.OpenAI")
    def test_compatibility_adapter_uses_openai_sdk_client_shape(
        self,
        mock_openai: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"opening_sentence":"ok"}')
                )
            ]
        )

        content = OpenAICompatibleProviderAdapter()._sdk_completion(
            model="grok-2-latest",
            api_base="https://api.x.ai/v1",
            api_key="sk-test",
            messages=[{"role": "user", "content": "{}"}],
            response_format={"type": "json_object"},
            temperature=0,
        )

        self.assertEqual(
            content.choices[0].message.content, '{"opening_sentence":"ok"}'
        )
        mock_openai.assert_called_once_with(
            base_url="https://api.x.ai/v1",
            api_key="sk-test",
            timeout=30.0,
        )
        mock_client.chat.completions.create.assert_called_once_with(
            model="grok-2-latest",
            messages=[{"role": "user", "content": "{}"}],
            response_format={"type": "json_object"},
            temperature=0,
        )

    @patch("openai.OpenAI")
    def test_compatibility_adapter_rejects_invalid_timeout(
        self,
        mock_openai: MagicMock,
    ) -> None:
        with self.assertRaisesRegex(
            NarrativeProviderError,
            "Request timeout must be a positive finite number",
        ):
            OpenAICompatibleProviderAdapter()._sdk_completion(
                model="grok-2-latest",
                api_base="https://api.x.ai/v1",
                api_key="sk-test",
                messages=[{"role": "user", "content": "{}"}],
                response_format={"type": "json_object"},
                temperature=0,
                request_timeout_seconds="not-a-number",
            )

        mock_openai.assert_not_called()

    def test_capabilities_match_compatibility_expectations(self) -> None:
        capabilities = OpenAICompatibleProviderAdapter().capabilities_for("groq")

        self.assertTrue(capabilities.supports_structured_output)
        self.assertFalse(capabilities.supports_local_only_mode)
        self.assertFalse(capabilities.supports_remote_mcp)
        self.assertFalse(capabilities.supports_local_mcp)
        self.assertFalse(capabilities.supports_tool_approval)


if __name__ == "__main__":
    unittest.main()
