"""Opt-in live smoke tests for credentialed narrative providers."""

from __future__ import annotations

import json
import os
import unittest

from dotenv import load_dotenv

from llm.providers import generate_completion_with_settings
from services.settings_service import provider_defaults


load_dotenv()
LIVE_SMOKE_ENABLED = os.getenv("DEPLOYWHISPER_LIVE_PROVIDER_SMOKE") == "1"
PROVIDER_API_KEYS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY", "LLM_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY", "LLM_API_KEY"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY", "LLM_API_KEY"),
    "groq": ("GROQ_API_KEY", "LLM_API_KEY"),
    "xai": ("XAI_API_KEY", "LLM_API_KEY"),
}
DEFAULT_PROVIDERS = ("openai", "anthropic", "gemini", "openrouter", "groq", "xai")


def _usable_secret(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip().lower()
    return bool(normalized) and not normalized.startswith("your-")


def _api_key_for(provider: str) -> str | None:
    for env_name in PROVIDER_API_KEYS[provider]:
        value = os.getenv(env_name)
        if _usable_secret(value):
            return value
    return None


def _target_providers() -> list[str]:
    configured = os.getenv("DEPLOYWHISPER_LIVE_PROVIDER_SMOKE_PROVIDERS")
    if not configured:
        return list(DEFAULT_PROVIDERS)
    return [
        provider.strip().lower()
        for provider in configured.split(",")
        if provider.strip()
    ]


@unittest.skipUnless(
    LIVE_SMOKE_ENABLED,
    "Set DEPLOYWHISPER_LIVE_PROVIDER_SMOKE=1 to run live provider smoke tests.",
)
class LiveProviderSmokeTests(unittest.TestCase):
    def test_configured_credentialed_providers_return_json(self) -> None:
        providers = _target_providers()
        runnable = [
            (provider, _api_key_for(provider))
            for provider in providers
            if provider in PROVIDER_API_KEYS and _api_key_for(provider)
        ]
        if not runnable:
            self.fail(
                "Live provider smoke was requested, but no usable provider API key "
                "was found for the configured providers."
            )

        messages = [
            {"role": "system", "content": "Return only a JSON object."},
            {"role": "user", "content": '{"smoke": true}'},
        ]

        for provider, api_key in runnable:
            defaults = provider_defaults(provider)
            model = os.getenv(
                f"DEPLOYWHISPER_LIVE_{provider.upper()}_MODEL",
                str(defaults["model"]),
            )
            api_base = os.getenv(
                f"DEPLOYWHISPER_LIVE_{provider.upper()}_API_BASE",
                str(defaults["api_base"]),
            )
            with self.subTest(provider=provider, model=model):
                raw_content = generate_completion_with_settings(
                    messages,
                    provider=provider,
                    model=model,
                    api_base=api_base,
                    api_key=api_key,
                    local_mode=False,
                )
                self.assertIsInstance(json.loads(raw_content), dict)


if __name__ == "__main__":
    unittest.main()
