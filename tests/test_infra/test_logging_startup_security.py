"""Ensure migration startup retains the real application's logging boundary."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class LoggingStartupSecurityTests(unittest.TestCase):
    def test_application_logging_stays_safe_after_database_initialization(self):
        script = """
import logging
import app
import uvicorn
from unittest.mock import patch
from models.database import init_db
from logging_config import SafeFormatter, PayloadLogFilter
with patch('app.uvicorn.run') as start_server:
    app.run()
    args, kwargs = start_server.call_args
uvicorn.Config(*args, **kwargs)
init_db()
root = logging.getLogger()
assert all(isinstance(handler.formatter, SafeFormatter) for handler in root.handlers)
assert all(any(isinstance(item, PayloadLogFilter) for item in handler.filters) for handler in root.handlers)
for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
    assert not logging.getLogger(name).handlers, name
try:
    raise RuntimeError('unlabelled_raw_artifact_source')
except RuntimeError:
    logging.getLogger('startup_boundary').exception('password="synthetic-startup-secret"')
"""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[2],
                env={**os.environ, "DATABASE_URL": f"sqlite:///{directory}/startup.db"},
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("synthetic-startup-secret", result.stderr)
        self.assertNotIn("unlabelled_raw_artifact_source", result.stderr)
        self.assertIn("RuntimeError", result.stderr)


if __name__ == "__main__":
    unittest.main()
