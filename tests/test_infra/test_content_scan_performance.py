"""Bounded runtime checks for credential scanning of benign identifiers."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ContentScanPerformanceTests(unittest.TestCase):
    def test_long_identifiers_do_not_restart_lexical_scans(self):
        project_root = Path(__file__).resolve().parents[2]
        script = """
import sys
sys.path.insert(0, sys.argv[1])
from services.content_security import redact_text, sensitive_artifact_values

for unit in ('a.', 'a-'):
    text = unit * 8192
    assert redact_text(text) == text
    assert sensitive_artifact_values(text.encode()) == ()
"""
        # A subprocess bounds a regression without leaving a stuck test worker.
        # The allowance is generous for 16KB; the old restarting scans exceed it.
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(  # nosec B603
                [sys.executable, "-c", script, str(project_root)],
                cwd=temp_dir,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
