"""Tests for local-only mode behavior."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.settings_service as settings_service_module
import llm.providers as providers_module


class LocalModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "settings.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(settings_service_module)
        reload(providers_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_activate_local_mode_persists_ollama_configuration(self) -> None:
        saved = settings_service_module.activate_local_mode(
            model="ollama/llama3",
            api_base="http://localhost:11434",
        )
        self.assertTrue(saved.local_mode)
        self.assertEqual(saved.provider, "ollama")

        loaded = settings_service_module.get_provider_settings()
        self.assertTrue(loaded.local_mode)
        self.assertEqual(loaded.provider, "ollama")

    def test_generate_completion_omits_api_key_in_local_mode(self) -> None:
        settings_service_module.activate_local_mode(
            model="ollama/llama3",
            api_base="http://localhost:11434",
        )
        captured: dict[str, object] = {}

        class Message:
            def __init__(self, content: str) -> None:
                self.content = content

        class Choice:
            def __init__(self, content: str) -> None:
                self.message = Message(content)

        class Response:
            def __init__(self) -> None:
                self.choices = [Choice("{}")]

        def fake_completion(**kwargs: object) -> Response:
            captured.update(kwargs)
            return Response()

        providers_module.generate_completion_with_settings(
            messages=[
                {"role": "system", "content": "Return JSON"},
                {"role": "user", "content": "{}"},
            ],
            provider="ollama",
            model="ollama/llama3",
            api_base="http://localhost:11434",
            local_mode=True,
            completion_client=fake_completion,
        )
        self.assertEqual(captured["model"], "ollama/llama3")
        self.assertNotIn("api_key", captured)
