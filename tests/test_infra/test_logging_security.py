"""Regression coverage for the configured console logging boundary."""

from __future__ import annotations

import io
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from logging_config import configure_logging


class LoggingSecurityTests(unittest.TestCase):
    def test_complete_multiline_and_escaped_assignment_bodies_are_redacted(self):
        messages = (
            'password="prefix\\" exposed-suffix"',
            repr({"password": "prefix'\"exposed-suffix"}),
            'password="prefix\nexposed-body"',
            "password: |\n  exposed-body\n  exposed-suffix\nnext: safe",
            "password: >-\n  exposed-body\n  exposed-suffix\nnext: safe",
            "password: |2-\n  exposed-body\n  exposed-suffix\nnext: safe",
            "password = <<-EOF\nexposed-body\nexposed-suffix\nEOF\nnext = safe",
            "password = <<EOF\nexposed-body\neof\nexposed-suffix\nEOF",
            "SECRET_KEY=exposed-body",
        )
        for message in messages:
            with self.subTest(message=message):
                self.output.seek(0)
                self.output.truncate(0)
                logging.getLogger("deploywhisper.security_test").warning(message)
                self.assertNotIn("exposed-", self.output.getvalue())

    def setUp(self) -> None:
        self.root = logging.getLogger()
        self.previous_handlers = self.root.handlers[:]
        self.previous_level = self.root.level
        self.output = io.StringIO()
        with patch("logging_config.settings", SimpleNamespace(log_level="DEBUG")):
            configure_logging()
        for handler in self.root.handlers:
            handler.setStream(self.output)

    def tearDown(self) -> None:
        self.root.handlers = self.previous_handlers
        self.root.setLevel(self.previous_level)

    def test_interpolated_message_is_redacted_and_normal_event_is_preserved(
        self,
    ) -> None:
        secret = "sk-proj-" + "syntheticcredential" * 3
        logging.getLogger("deploywhisper.security_test").warning(
            "Provider failure api_key=%s", secret
        )
        logging.getLogger("deploywhisper.security_test").info("Analysis completed")

        output = self.output.getvalue()
        self.assertNotIn(secret, output)
        self.assertIn("Provider failure", output)
        self.assertIn("Analysis completed", output)

    def test_exception_output_excludes_value_traceback_and_cached_exception_text(
        self,
    ) -> None:
        artifact = "confidential_raw_artifact_and_prompt_sql_parameter"
        try:
            raise RuntimeError(artifact)
        except RuntimeError:
            logging.getLogger("deploywhisper.security_test").exception(
                "Analysis failed", stack_info=True
            )
        record = logging.makeLogRecord(
            {
                "name": "deploywhisper.security_test",
                "levelno": logging.ERROR,
                "levelname": "ERROR",
                "msg": "Cached exception event",
                "exc_text": artifact,
                "stack_info": artifact,
            }
        )
        self.root.handle(record)

        output = self.output.getvalue()
        self.assertIn("RuntimeError", output)
        self.assertIn("Analysis failed", output)
        self.assertIn("Cached exception event", output)
        self.assertNotIn(artifact, output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("raise RuntimeError", output)
        self.assertNotIn("File ", output)

    def test_sdk_debug_payloads_are_blocked_at_the_configured_handler(self) -> None:
        artifact = "confidential_raw_artifact_and_prompt_sql_parameter"
        for name in (
            "httpx",
            "httpcore.connection",
            "openai._base_client",
            "anthropic._base_client",
            "google.genai._api_client",
            "urllib3.connectionpool",
        ):
            with self.subTest(logger=name):
                # Feed records directly to the root, as child loggers may have
                # independently configured levels in the application's process.
                self.root.handle(
                    logging.makeLogRecord(
                        {
                            "name": name,
                            "levelno": logging.DEBUG,
                            "levelname": "DEBUG",
                            "msg": "Request payload: %s",
                            "args": (artifact,),
                        }
                    )
                )
        self.assertNotIn(artifact, self.output.getvalue())

    def test_sql_statement_and_parameter_logs_are_blocked(self) -> None:
        artifact = "confidential_raw_artifact_and_prompt_sql_parameter"
        for name in ("sqlalchemy.engine.Engine", "sqlalchemy.pool.impl.QueuePool"):
            for level in (logging.DEBUG, logging.INFO):
                with self.subTest(logger=name, level=level):
                    self.root.handle(
                        logging.makeLogRecord(
                            {
                                "name": name,
                                "levelno": level,
                                "levelname": logging.getLevelName(level),
                                "msg": "[parameters: %s]",
                                "args": (artifact,),
                            }
                        )
                    )
        self.assertNotIn(artifact, self.output.getvalue())

    def test_safe_sdk_metadata_events_remain_available(self) -> None:
        self.root.handle(
            logging.makeLogRecord(
                {
                    "name": "httpx",
                    "levelno": logging.INFO,
                    "levelname": "INFO",
                    "msg": "HTTP request completed with status 200",
                }
            )
        )
        self.assertIn("HTTP request completed with status 200", self.output.getvalue())

    def test_existing_application_loggers_remain_enabled(self) -> None:
        logger = logging.getLogger("deploywhisper.security_test")
        self.assertFalse(logger.disabled)
        self.assertEqual(self.root.level, logging.DEBUG)
