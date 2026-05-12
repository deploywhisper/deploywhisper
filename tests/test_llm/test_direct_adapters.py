"""Tests for direct provider adapters."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from llm.adapters.anthropic_adapter import AnthropicProviderAdapter
from llm.adapters.base import NarrativeProviderError, ProviderRuntimeConfig
from llm.adapters.gemini_adapter import GeminiProviderAdapter
from llm.adapters.ollama_adapter import OllamaProviderAdapter
from llm.adapters.openai_adapter import OpenAIProviderAdapter


class DirectProviderAdapterTests(unittest.TestCase):
    def test_openai_adapter_uses_json_mode_and_gpt5_temperature_rule(self) -> None:
        captured: dict[str, object] = {}

        def fake_completion(**kwargs: object):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"opening_sentence":"ok"}')
                    )
                ]
            )

        adapter = OpenAIProviderAdapter()
        content = adapter.generate_completion(
            [{"role": "user", "content": "{}"}],
            runtime=ProviderRuntimeConfig(
                provider="openai",
                model="gpt-5.4-mini",
                api_base="https://api.openai.com/v1",
                api_key="sk-test",
                local_mode=False,
            ),
            completion_client=fake_completion,
        )

        self.assertEqual(content, '{"opening_sentence":"ok"}')
        self.assertEqual(captured["model"], "gpt-5.4-mini")
        self.assertEqual(captured["api_base"], "https://api.openai.com/v1")
        self.assertEqual(captured["api_key"], "sk-test")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertEqual(captured["temperature"], 1)
        self.assertEqual(captured["request_timeout_seconds"], 30.0)

    def test_openai_adapter_normalizes_prefixed_model_name(self) -> None:
        captured: dict[str, object] = {}

        def fake_completion(**kwargs: object):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"opening_sentence":"ok"}')
                    )
                ]
            )

        adapter = OpenAIProviderAdapter()
        content = adapter.generate_completion(
            [{"role": "user", "content": "{}"}],
            runtime=ProviderRuntimeConfig(
                provider="openai",
                model="openai/gpt-4.1-mini",
                api_base="https://api.openai.com/v1",
                api_key="sk-test",
                local_mode=False,
            ),
            completion_client=fake_completion,
        )

        self.assertEqual(content, '{"opening_sentence":"ok"}')
        self.assertEqual(captured["model"], "gpt-4.1-mini")

    def test_anthropic_adapter_splits_system_prompt_and_messages(self) -> None:
        captured: dict[str, object] = {}

        def fake_completion(**kwargs: object):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"opening_sentence":"ok"}')]
            )

        adapter = AnthropicProviderAdapter()
        content = adapter.generate_completion(
            [
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "{}"},
            ],
            runtime=ProviderRuntimeConfig(
                provider="anthropic",
                model="claude-3-5-sonnet-latest",
                api_base="https://api.anthropic.com",
                api_key="sk-test",
                local_mode=False,
            ),
            completion_client=fake_completion,
        )

        self.assertEqual(content, '{"opening_sentence":"ok"}')
        self.assertEqual(captured["system"], "Return JSON.")
        self.assertEqual(captured["model"], "claude-3-5-sonnet-latest")
        self.assertEqual(captured["api_base"], "https://api.anthropic.com")
        self.assertEqual(captured["api_key"], "sk-test")
        self.assertEqual(captured["temperature"], 0)
        self.assertEqual(captured["max_tokens"], 1024)
        self.assertEqual(
            captured["messages"],
            [
                {"role": "user", "content": "{}"},
                {"role": "assistant", "content": "{"},
            ],
        )

    def test_anthropic_adapter_reconstructs_prefilled_json_response(self) -> None:
        adapter = AnthropicProviderAdapter()

        content = adapter.generate_completion(
            [
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "{}"},
            ],
            runtime=ProviderRuntimeConfig(
                provider="anthropic",
                model="claude-3-5-sonnet-latest",
                api_base="https://api.anthropic.com",
                api_key="sk-test",
                local_mode=False,
            ),
            completion_client=lambda **_: SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="text",
                        text='"opening_sentence":"ok"}',
                    )
                ]
            ),
        )

        self.assertEqual(content, '{"opening_sentence":"ok"}')

    def test_gemini_adapter_normalizes_prefixed_model_name(self) -> None:
        captured: dict[str, object] = {}

        def fake_completion(**kwargs: object):
            captured.update(kwargs)
            return SimpleNamespace(text='{"opening_sentence":"ok"}')

        adapter = GeminiProviderAdapter()
        content = adapter.generate_completion(
            [
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "{}"},
            ],
            runtime=ProviderRuntimeConfig(
                provider="gemini",
                model="gemini/gemini-2.0-flash",
                api_base="https://generativelanguage.googleapis.com",
                api_key="gm-test",
                local_mode=False,
            ),
            completion_client=fake_completion,
        )

        self.assertEqual(content, '{"opening_sentence":"ok"}')
        self.assertEqual(captured["model"], "gemini-2.0-flash")
        self.assertEqual(
            captured["api_base"], "https://generativelanguage.googleapis.com"
        )
        self.assertEqual(captured["api_key"], "gm-test")
        self.assertEqual(captured["temperature"], 0)
        self.assertEqual(captured["response_mime_type"], "application/json")

    def test_ollama_adapter_normalizes_local_model_and_omits_api_key(self) -> None:
        captured: dict[str, object] = {}

        def fake_completion(**kwargs: object):
            captured.update(kwargs)
            return SimpleNamespace(
                message=SimpleNamespace(content='{"opening_sentence":"ok"}')
            )

        adapter = OllamaProviderAdapter()
        content = adapter.generate_completion(
            [
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "{}"},
            ],
            runtime=ProviderRuntimeConfig(
                provider="ollama",
                model="ollama/llama3",
                api_base="http://localhost:11434",
                api_key="ignored",
                local_mode=True,
            ),
            completion_client=fake_completion,
        )

        self.assertEqual(content, '{"opening_sentence":"ok"}')
        self.assertEqual(captured["model"], "ollama/llama3")
        self.assertEqual(captured["api_base"], "http://localhost:11434")
        self.assertEqual(captured["temperature"], 0)
        self.assertNotIn("api_key", captured)

    @patch("openai.OpenAI")
    def test_openai_sdk_completion_uses_official_client_shape(
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

        content = OpenAIProviderAdapter()._sdk_completion(
            model="gpt-4.1-mini",
            api_base="https://api.openai.com/v1",
            api_key="sk-test",
            messages=[{"role": "user", "content": "{}"}],
            response_format={"type": "json_object"},
            temperature=0,
        )

        self.assertEqual(
            content.choices[0].message.content, '{"opening_sentence":"ok"}'
        )
        mock_openai.assert_called_once_with(
            base_url="https://api.openai.com/v1",
            api_key="sk-test",
            timeout=30.0,
        )
        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "{}"}],
            response_format={"type": "json_object"},
            temperature=0,
        )

    @patch("anthropic.Anthropic")
    def test_anthropic_sdk_completion_prefills_json_on_official_client(
        self,
        mock_anthropic: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create.return_value = SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="text",
                    text='"opening_sentence":"ok"}',
                )
            ]
        )

        content = AnthropicProviderAdapter()._sdk_completion(
            model="claude-3-5-sonnet-latest",
            api_base="https://api.anthropic.com",
            api_key="sk-test",
            messages=[
                {"role": "user", "content": "{}"},
                {"role": "assistant", "content": "{"},
            ],
            temperature=0,
            max_tokens=1024,
            system="Return JSON.",
        )

        self.assertEqual(content.content[0].text, '"opening_sentence":"ok"}')
        mock_anthropic.assert_called_once_with(
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            timeout=30.0,
        )
        mock_client.messages.create.assert_called_once_with(
            model="claude-3-5-sonnet-latest",
            messages=[
                {"role": "user", "content": "{}"},
                {"role": "assistant", "content": "{"},
            ],
            temperature=0,
            max_tokens=1024,
            system="Return JSON.",
        )

    @patch("google.genai.Client")
    def test_gemini_sdk_completion_uses_official_client_shape(
        self,
        mock_client_cls: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = SimpleNamespace(
            text='{"opening_sentence":"ok"}'
        )

        content = GeminiProviderAdapter()._sdk_completion(
            model="gemini-2.0-flash",
            api_base="https://generativelanguage.googleapis.com",
            api_key="gm-test",
            contents="USER:\n{}",
            response_mime_type="application/json",
            temperature=0,
            system_instruction="Return JSON.",
        )

        self.assertEqual(content.text, '{"opening_sentence":"ok"}')
        mock_client_cls.assert_called_once_with(
            api_key="gm-test",
            http_options={
                "base_url": "https://generativelanguage.googleapis.com",
                "timeout": 30000,
            },
        )
        mock_client.models.generate_content.assert_called_once_with(
            model="gemini-2.0-flash",
            contents="USER:\n{}",
            config={
                "response_mime_type": "application/json",
                "temperature": 0,
                "system_instruction": "Return JSON.",
            },
        )

    @patch("google.genai.Client")
    def test_gemini_sdk_completion_converts_timeout_seconds_to_milliseconds(
        self,
        mock_client_cls: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = SimpleNamespace(
            text='{"opening_sentence":"ok"}'
        )

        GeminiProviderAdapter()._sdk_completion(
            model="gemini-2.0-flash",
            api_base="",
            api_key="gm-test",
            contents="USER:\n{}",
            response_mime_type="application/json",
            temperature=0,
            request_timeout_seconds=12.5,
        )

        mock_client_cls.assert_called_once_with(
            api_key="gm-test",
            http_options={"timeout": 12500},
        )

    @patch("llm.adapters.ollama_adapter.urlopen")
    def test_ollama_sdk_completion_uses_local_http_api(
        self,
        mock_urlopen: MagicMock,
    ) -> None:
        response = MagicMock()
        response.read.return_value = (
            b'{"message":{"content":"{\\"opening_sentence\\":\\"ok\\"}"}}'
        )
        mock_urlopen.return_value.__enter__.return_value = response

        content = OllamaProviderAdapter()._sdk_completion(
            model="ollama/llama3",
            api_base="http://localhost:11434",
            messages=[{"role": "user", "content": "{}"}],
            response_format="json",
            temperature=0,
        )

        self.assertEqual(content["message"]["content"], '{"opening_sentence":"ok"}')
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.data,
            (
                b'{"model": "llama3", "messages": [{"role": "user", "content": "{}"}], '
                b'"stream": false, "format": "json", "options": {"temperature": 0}}'
            ),
        )

    def test_direct_remote_adapters_reject_local_mode(self) -> None:
        adapter = OpenAIProviderAdapter()

        with self.assertRaises(NarrativeProviderError):
            adapter.generate_completion(
                [{"role": "user", "content": "{}"}],
                runtime=ProviderRuntimeConfig(
                    provider="openai",
                    model="gpt-4.1-mini",
                    api_base="https://api.openai.com/v1",
                    api_key="sk-test",
                    local_mode=True,
                ),
                completion_client=lambda **_: None,
            )

    def test_capabilities_match_story_expectations(self) -> None:
        self.assertTrue(
            OllamaProviderAdapter().capabilities_for("ollama").supports_local_only_mode
        )
        self.assertFalse(
            OpenAIProviderAdapter().capabilities_for("openai").supports_local_only_mode
        )
        self.assertFalse(
            AnthropicProviderAdapter().capabilities_for("anthropic").supports_remote_mcp
        )
        self.assertTrue(
            GeminiProviderAdapter()
            .capabilities_for("gemini")
            .supports_structured_output
        )


if __name__ == "__main__":
    unittest.main()
