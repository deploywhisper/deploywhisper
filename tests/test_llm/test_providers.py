"""Tests for provider facade and adapter registry behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import llm.providers as providers_module
from llm.adapters.base import NarrativeProviderError


class ProviderFacadeTests(unittest.TestCase):
    def test_generate_completion_routes_through_registered_adapter(self) -> None:
        class FakeAdapter:
            def supports_provider(self, provider: str) -> bool:
                return provider == "openai"

            def generate_completion(self, messages, *, runtime, completion_client=None):
                self.messages = messages
                self.runtime = runtime
                self.completion_client = completion_client
                return '{"ok":true}'

            def validate_configuration(self, *, runtime, completion_client=None):
                raise AssertionError("not used in this test")

            def capabilities_for(self, provider: str):
                raise AssertionError("not used in this test")

        fake_adapter = FakeAdapter()
        with patch.object(
            providers_module.get_provider_registry(),
            "resolve",
            return_value=fake_adapter,
        ):
            content = providers_module.generate_completion_with_settings(
                [{"role": "user", "content": "{}"}],
                provider="openai",
                model="gpt-4.1-mini",
                api_base="https://api.openai.com/v1",
                api_key="sk-test",
                local_mode=False,
                completion_client=object(),
            )

        self.assertEqual(content, '{"ok":true}')
        self.assertEqual(fake_adapter.runtime.provider, "openai")
        self.assertEqual(fake_adapter.runtime.model, "gpt-4.1-mini")
        self.assertEqual(fake_adapter.runtime.api_base, "https://api.openai.com/v1")
        self.assertEqual(fake_adapter.runtime.api_key, "sk-test")
        self.assertFalse(fake_adapter.runtime.local_mode)
        self.assertEqual(fake_adapter.messages, [{"role": "user", "content": "{}"}])

    def test_validate_provider_configuration_routes_through_registered_adapter(
        self,
    ) -> None:
        captured: dict[str, object] = {}

        class FakeAdapter:
            def supports_provider(self, provider: str) -> bool:
                return provider == "ollama"

            def generate_completion(self, messages, *, runtime, completion_client=None):
                raise AssertionError("not used in this test")

            def validate_configuration(self, *, runtime, completion_client=None):
                captured["runtime"] = runtime
                captured["completion_client"] = completion_client

            def capabilities_for(self, provider: str):
                raise AssertionError("not used in this test")

        with patch.object(
            providers_module.get_provider_registry(),
            "resolve",
            return_value=FakeAdapter(),
        ):
            providers_module.validate_provider_configuration(
                provider="ollama",
                model="ollama/llama3",
                api_base="http://localhost:11434",
                local_mode=True,
                completion_client=object(),
            )

        runtime = captured["runtime"]
        self.assertEqual(runtime.provider, "ollama")
        self.assertEqual(runtime.model, "ollama/llama3")
        self.assertEqual(runtime.api_base, "http://localhost:11434")
        self.assertTrue(runtime.local_mode)

    def test_get_provider_capabilities_returns_registered_capabilities(self) -> None:
        capabilities = providers_module.get_provider_capabilities("ollama")

        self.assertTrue(capabilities.supports_structured_output)
        self.assertTrue(capabilities.supports_local_only_mode)
        self.assertFalse(capabilities.supports_remote_mcp)
        self.assertFalse(capabilities.supports_local_mcp)
        self.assertFalse(capabilities.supports_tool_approval)

    def test_get_provider_adapter_raises_for_unsupported_provider(self) -> None:
        with self.assertRaises(NarrativeProviderError):
            providers_module.get_provider_adapter("unsupported-provider")

    def test_registry_routes_tier1_providers_to_direct_adapters(self) -> None:
        self.assertEqual(
            providers_module.get_provider_adapter("openai").__class__.__name__,
            "OpenAIProviderAdapter",
        )
        self.assertEqual(
            providers_module.get_provider_adapter("anthropic").__class__.__name__,
            "AnthropicProviderAdapter",
        )
        self.assertEqual(
            providers_module.get_provider_adapter("gemini").__class__.__name__,
            "GeminiProviderAdapter",
        )
        self.assertEqual(
            providers_module.get_provider_adapter("ollama").__class__.__name__,
            "OllamaProviderAdapter",
        )

    def test_registry_routes_compatibility_providers_to_explicit_adapter(self) -> None:
        self.assertEqual(
            providers_module.get_provider_adapter("openrouter").__class__.__name__,
            "OpenAICompatibleProviderAdapter",
        )
        self.assertEqual(
            providers_module.get_provider_adapter("groq").__class__.__name__,
            "OpenAICompatibleProviderAdapter",
        )
        self.assertEqual(
            providers_module.get_provider_adapter("xai").__class__.__name__,
            "OpenAICompatibleProviderAdapter",
        )


if __name__ == "__main__":
    unittest.main()
