"""Tests for narrative warning formatting helpers."""

from __future__ import annotations

import unittest

from ui.formatters.narrative import (
    extract_llm_notice,
    extract_submission_manifest_notice,
)


class NarrativeFormatterTests(unittest.TestCase):
    def test_extract_llm_notice_prefers_narrative_provider_warning(self) -> None:
        notice = extract_llm_notice(
            [
                "LLM severity assessment unavailable; falling back to heuristic matrix: provider offline",
                "Narrative provider unavailable: provider offline",
            ]
        )
        self.assertEqual(notice, "Narrative provider unavailable: provider offline")

    def test_extract_llm_notice_returns_none_for_unrelated_warnings(self) -> None:
        self.assertIsNone(extract_llm_notice(["Topology context missing."]))

    def test_extract_submission_manifest_notice_returns_manifest_warning(self) -> None:
        warning = (
            "Submission manifest metadata was unavailable because persisted JSON was "
            "malformed."
        )

        self.assertEqual(
            extract_submission_manifest_notice(["Topology context missing.", warning]),
            warning,
        )


if __name__ == "__main__":
    unittest.main()
