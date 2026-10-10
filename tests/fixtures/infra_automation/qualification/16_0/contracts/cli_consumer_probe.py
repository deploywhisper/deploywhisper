"""Reproducible isolated existing CLI consumer vectors; no app changes."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
spec = importlib.util.spec_from_file_location(
    "cli_compat_test", Path("tests/test_cli/test_analyze.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
original = m.AnalyzeCliTests._persisted_report_with_scanner_conflict
cases = 0
for block in (None, {"version": 1}, {"version": 99}):

    def fixture(self):
        result = original(self)
        if block is not None:
            result["infra_automation_provenance"] = block
        return result

    with patch.object(
        m.AnalyzeCliTests, "_persisted_report_with_scanner_conflict", fixture
    ):
        for name in (
            "test_analyze_agent_json_emits_stable_advisory_contract",
            "test_analyze_command_serializes_scanner_conflict_share_summary_payload",
        ):
            result = unittest.TestResult()
            m.AnalyzeCliTests(name).run(result)
            if not result.wasSuccessful():
                raise RuntimeError(str(result.errors) + str(result.failures))
            cases += 1
print(
    json.dumps(
        {
            "consumer": "actual CLI main existing JSON/share-summary and agent JSON tests with absent/known/unknown report metadata",
            "cases": cases,
            "passed": True,
            "database": "isolated per existing fixture test",
        }
    )
)
