"""Tests for provider settings workflow."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.repositories.settings as settings_repository_module
import models.tables as tables_module
import services.settings_service as settings_service_module


class SettingsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "settings.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(settings_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_save_and_get_provider_settings(self) -> None:
        saved = settings_service_module.save_provider_settings(
            provider="openai",
            model="gpt-test",
            api_base="http://localhost:9999",
            api_key="sk-test",
        )
        self.assertEqual(saved.provider, "openai")
        self.assertEqual(saved.api_key, "sk-test")

        loaded = settings_service_module.get_provider_settings()
        self.assertEqual(loaded.provider, "openai")
        self.assertEqual(loaded.model, "gpt-test")
        self.assertEqual(loaded.api_base, "http://localhost:9999")
        self.assertIsNone(loaded.api_key)

        with database_module.SessionLocal() as session:
            keys = {
                record.key
                for record in settings_repository_module.list_settings(session)
            }
        self.assertNotIn("llm_api_key", keys)
        self.assertNotIn("llm_provider_config::openai::api_key", keys)

    def test_provider_profiles_can_be_saved_per_provider_and_switched(self) -> None:
        settings_service_module.save_provider_settings(
            provider="openai",
            model="gpt-4.1-mini",
            api_base="https://api.openai.com/v1",
            api_key="sk-openai",
            activate=True,
        )
        settings_service_module.save_provider_settings(
            provider="anthropic",
            model="claude-3-5-sonnet-latest",
            api_base="https://api.anthropic.com",
            api_key="sk-anthropic",
            activate=False,
        )

        active = settings_service_module.get_provider_settings()
        anthropic = settings_service_module.get_provider_settings("anthropic")

        self.assertEqual(active.provider, "openai")
        self.assertIsNone(active.api_key)
        self.assertEqual(anthropic.provider, "anthropic")
        self.assertIsNone(anthropic.api_key)

    def test_provider_profiles_resolve_provider_specific_env_keys(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-openai-env"
        os.environ["ANTHROPIC_API_KEY"] = "sk-anthropic-env"
        reload(config_module)
        reload(settings_service_module)

        settings_service_module.save_provider_settings(
            provider="openai",
            model="gpt-4.1-mini",
            api_base="https://api.openai.com/v1",
            activate=True,
        )
        settings_service_module.save_provider_settings(
            provider="anthropic",
            model="claude-3-5-sonnet-latest",
            api_base="https://api.anthropic.com",
            activate=False,
        )

        active = settings_service_module.get_provider_settings()
        anthropic = settings_service_module.get_provider_settings("anthropic")

        self.assertEqual(active.api_key, "sk-openai-env")
        self.assertEqual(anthropic.api_key, "sk-anthropic-env")
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_requested_provider_profile_uses_provider_specific_env_key(self) -> None:
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-groq-env"}, clear=False):
            reload(config_module)
            reload(settings_service_module)
            loaded = settings_service_module.get_provider_settings("groq")

        self.assertEqual(loaded.provider, "groq")
        self.assertEqual(loaded.api_key, "gsk-groq-env")
        self.assertEqual(loaded.source, "environment")

    def test_resolve_provider_runtime_includes_configured_request_timeout(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-4.1-mini",
                "LLM_API_BASE": "https://api.openai.com/v1",
                "LLM_REQUEST_TIMEOUT_SECONDS": "12.5",
            },
            clear=False,
        ):
            reload(config_module)
            reload(settings_service_module)
            runtime = settings_service_module.resolve_provider_runtime()

        self.assertEqual(runtime["provider"], "openai")
        self.assertEqual(runtime["request_timeout_seconds"], 12.5)

    def test_invalid_request_timeout_env_falls_back_without_import_failure(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "openai",
                "LLM_REQUEST_TIMEOUT_SECONDS": "not-a-number",
            },
            clear=False,
        ):
            reload(config_module)
            reload(settings_service_module)
            runtime = settings_service_module.resolve_provider_runtime()

        self.assertEqual(runtime["provider"], "openai")
        self.assertEqual(runtime["request_timeout_seconds"], 30.0)

    def test_saving_provider_as_active_switches_single_active_provider(self) -> None:
        settings_service_module.save_provider_settings(
            provider="openai",
            model="gpt-4.1-mini",
            api_base="https://api.openai.com/v1",
            activate=True,
        )
        settings_service_module.save_provider_settings(
            provider="groq",
            model="groq/qwen/qwen3-32b",
            api_base="https://api.groq.com/openai/v1",
            activate=True,
        )

        active = settings_service_module.get_provider_settings()

        self.assertEqual(active.provider, "groq")
        self.assertEqual(active.model, "groq/qwen/qwen3-32b")
        self.assertEqual(active.api_base, "https://api.groq.com/openai/v1")

    def test_provider_select_options_keep_compatibility_providers_available(
        self,
    ) -> None:
        options = settings_service_module.provider_select_options()

        self.assertIn("openrouter", options)
        self.assertIn("groq", options)
        self.assertIn("xai", options)

    def test_get_provider_settings_includes_capability_metadata(self) -> None:
        loaded = settings_service_module.get_provider_settings("ollama")

        self.assertTrue(loaded.capabilities.supports_structured_output)
        self.assertTrue(loaded.capabilities.supports_local_only_mode)
        self.assertFalse(loaded.capabilities.supports_remote_mcp)
        self.assertFalse(loaded.capabilities.supports_local_mcp)
        self.assertFalse(loaded.capabilities.supports_tool_approval)

    def test_get_provider_settings_survives_unsupported_provider_capabilities(
        self,
    ) -> None:
        loaded = settings_service_module.get_provider_settings("unknown-provider")

        self.assertEqual(loaded.provider, "unknown-provider")
        self.assertTrue(loaded.capabilities.supports_structured_output)
        self.assertFalse(loaded.capabilities.supports_local_only_mode)

    def test_get_provider_settings_can_resolve_from_environment_without_db_rows(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "LLM_MODEL": "gemini/gemini-2.0-flash",
                "LLM_API_BASE": "https://generativelanguage.googleapis.com",
                "GEMINI_API_KEY": "gm-env-test",
            },
            clear=False,
        ):
            reload(config_module)
            reload(settings_service_module)

            loaded = settings_service_module.get_provider_settings()

        self.assertEqual(loaded.provider, "gemini")
        self.assertEqual(loaded.model, "gemini/gemini-2.0-flash")
        self.assertEqual(loaded.api_base, "https://generativelanguage.googleapis.com")
        self.assertEqual(loaded.api_key, "gm-env-test")
        self.assertFalse(loaded.local_mode)
        self.assertEqual(loaded.source, "environment")

    def test_validate_provider_settings_returns_failure_message(self) -> None:
        config = settings_service_module.ProviderSettings(
            provider="openai",
            model="gpt-test",
            api_base="http://localhost:9999",
            api_key="sk-test",
            source="database",
        )

        def broken_completion(**_: object):
            raise RuntimeError("provider offline")

        result = settings_service_module.validate_provider_settings(
            config, completion_client=broken_completion
        )
        self.assertFalse(result["valid"])
        self.assertIn("provider offline", result["message"])

    def test_check_provider_readiness_reports_missing_api_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_API_KEY": "",
                "OPENAI_API_KEY": "",
                "ANTHROPIC_API_KEY": "",
                "GEMINI_API_KEY": "",
                "GOOGLE_API_KEY": "",
                "OPENROUTER_API_KEY": "",
                "GROQ_API_KEY": "",
                "XAI_API_KEY": "",
            },
            clear=False,
        ):
            reload(config_module)
            reload(settings_service_module)
            settings_service_module.save_provider_settings(
                provider="openai",
                model="gpt-4.1-mini",
                api_base="https://api.openai.com/v1",
                activate=True,
            )

            readiness = settings_service_module.check_provider_readiness()

        self.assertFalse(readiness.ready)
        self.assertTrue(readiness.requires_api_key)
        self.assertFalse(readiness.has_api_key)
        self.assertIn("no API key is available", readiness.message)

    def test_check_provider_readiness_reports_provider_failure(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-openai-env"
        reload(config_module)
        reload(settings_service_module)
        settings_service_module.save_provider_settings(
            provider="openai",
            model="gpt-4.1-mini",
            api_base="https://api.openai.com/v1",
            activate=True,
        )

        def broken_completion(**_: object):
            raise RuntimeError("provider offline")

        readiness = settings_service_module.check_provider_readiness(
            completion_client=broken_completion
        )

        self.assertFalse(readiness.ready)
        self.assertTrue(readiness.has_api_key)
        self.assertIn("provider offline", readiness.message)
        os.environ.pop("OPENAI_API_KEY", None)

    def test_check_provider_readiness_validates_local_mode_without_api_key(
        self,
    ) -> None:
        settings_service_module.activate_local_mode(
            model="ollama/llama3",
            api_base="http://localhost:11434",
        )

        def fake_completion(**_: object):
            class Message:
                def __init__(self, content: str) -> None:
                    self.content = content

            class Choice:
                def __init__(self, content: str) -> None:
                    self.message = Message(content)

            class Response:
                def __init__(self) -> None:
                    self.choices = [Choice("{}")]

            return Response()

        readiness = settings_service_module.check_provider_readiness(
            completion_client=fake_completion
        )

        self.assertTrue(readiness.ready)
        self.assertEqual(readiness.provider, "ollama")
        self.assertEqual(readiness.model, "ollama/llama3")
        self.assertTrue(readiness.local_mode)
        self.assertFalse(readiness.requires_api_key)
        self.assertFalse(readiness.has_api_key)
        self.assertEqual(
            readiness.message, "LLM provider connection validated for analysis."
        )

    def test_get_provider_health_snapshot_does_not_probe_provider(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-openai-env"
        reload(config_module)
        reload(settings_service_module)
        settings_service_module.save_provider_settings(
            provider="openai",
            model="gpt-4.1-mini",
            api_base="https://api.openai.com/v1",
            activate=True,
        )

        with patch(
            "services.settings_service.validate_provider_settings",
            side_effect=AssertionError("should not validate"),
        ):
            readiness = settings_service_module.get_provider_health_snapshot()

        self.assertTrue(readiness.ready)
        self.assertEqual(readiness.provider, "openai")
        self.assertTrue(readiness.capabilities.supports_structured_output)
        self.assertFalse(readiness.capabilities.supports_local_only_mode)
        self.assertFalse(readiness.capabilities.supports_remote_mcp)
        self.assertIn(
            "Live connectivity is checked during analysis runs", readiness.message
        )
        os.environ.pop("OPENAI_API_KEY", None)

    def test_validate_provider_settings_uses_supplied_values(self) -> None:
        captured: dict[str, str] = {}

        def fake_completion(**kwargs: object):
            captured["model"] = kwargs["model"]
            captured["api_base"] = kwargs["api_base"]
            captured["temperature"] = str(kwargs["temperature"])

            class Message:
                def __init__(self, content: str) -> None:
                    self.content = content

            class Choice:
                def __init__(self, content: str) -> None:
                    self.message = Message(content)

            class Response:
                def __init__(self) -> None:
                    self.choices = [Choice("{}")]

            return Response()

        config = settings_service_module.ProviderSettings(
            provider="openai",
            model="gpt-supplied",
            api_base="http://localhost:9998",
            api_key="sk-test",
            source="database",
        )
        result = settings_service_module.validate_provider_settings(
            config, completion_client=fake_completion
        )
        self.assertTrue(result["valid"])
        self.assertEqual(captured["model"], "gpt-supplied")
        self.assertEqual(captured["api_base"], "http://localhost:9998")
        self.assertEqual(captured["temperature"], "0")

    def test_validate_provider_settings_uses_temperature_one_for_openai_gpt5_models(
        self,
    ) -> None:
        captured: dict[str, str] = {}

        def fake_completion(**kwargs: object):
            captured["temperature"] = str(kwargs["temperature"])

            class Message:
                def __init__(self, content: str) -> None:
                    self.content = content

            class Choice:
                def __init__(self, content: str) -> None:
                    self.message = Message(content)

            class Response:
                def __init__(self) -> None:
                    self.choices = [Choice("{}")]

            return Response()

        config = settings_service_module.ProviderSettings(
            provider="openai",
            model="gpt-5.4-mini",
            api_base="https://api.openai.com/v1",
            api_key="sk-test",
            source="database",
        )

        result = settings_service_module.validate_provider_settings(
            config, completion_client=fake_completion
        )

        self.assertTrue(result["valid"])
        self.assertEqual(captured["temperature"], "1")

    def test_save_and_get_dashboard_result_display_duration(self) -> None:
        self.assertEqual(
            settings_service_module.get_dashboard_result_display_duration_seconds(),
            settings_service_module.DEFAULT_DASHBOARD_RESULT_DURATION_SECONDS,
        )

        saved = settings_service_module.save_dashboard_result_display_duration_seconds(
            900
        )

        self.assertEqual(saved, 900)
        self.assertEqual(
            settings_service_module.get_dashboard_result_display_duration_seconds(), 900
        )

    def test_save_and_get_topology_drift_check_interval_hours(self) -> None:
        self.assertEqual(
            settings_service_module.get_topology_drift_check_interval_hours(),
            settings_service_module.DEFAULT_TOPOLOGY_DRIFT_CHECK_INTERVAL_HOURS,
        )

        saved = settings_service_module.save_topology_drift_check_interval_hours(168)

        self.assertEqual(saved, 168)
        self.assertEqual(
            settings_service_module.get_topology_drift_check_interval_hours(),
            168,
        )
