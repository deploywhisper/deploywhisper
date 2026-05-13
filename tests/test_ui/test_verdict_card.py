"""Tests for verdict-card confidence and context warning helpers."""

from __future__ import annotations

import unittest

from ui.components.verdict_card import _has_limited_context, _primary_confidence
from ui.formatters.report_header import (
    evidence_law_status,
    next_action_text,
    report_confidence_text,
    report_verdict_text,
)


class VerdictCardHelperTests(unittest.TestCase):
    def test_primary_confidence_does_not_fallback_to_finding_confidence(self) -> None:
        for report in (
            {"findings": [{"confidence": 1.0}]},
            {"confidence": "invalid", "findings": [{"confidence": 1.0}]},
        ):
            with self.subTest(report=report):
                self.assertIsNone(_primary_confidence(report))

    def test_limited_context_treats_uncertainty_as_warning_signal(self) -> None:
        self.assertTrue(
            _has_limited_context(
                {
                    "context_score": 0.74,
                    "insufficient_context": False,
                    "uncertainty": "Uncertainty: evidence coverage is partial.",
                }
            )
        )

    def test_report_header_signals_use_advisory_copy(self) -> None:
        report = {
            "recommendation": "no-go",
            "severity": "critical",
            "confidence": 0.91,
            "findings": [
                {
                    "severity": "critical",
                    "deterministic": True,
                    "evidence_refs": ["ev-001"],
                }
            ],
            "evidence_items": [
                {
                    "evidence_id": "ev-001",
                    "deterministic": True,
                    "determinism_level": "deterministic",
                }
            ],
            "warnings": [],
        }

        status, detail = evidence_law_status(report)

        self.assertEqual(report_verdict_text(report), "NO-GO · CRITICAL RISK")
        self.assertEqual(report_confidence_text(report), "High (0.91)")
        self.assertEqual(status, "Satisfied")
        self.assertIn("deterministic evidence", detail)
        self.assertIn("Review linked evidence", next_action_text(report, status))

    def test_report_header_signals_flag_unsupported_severe_claims(self) -> None:
        report = {
            "recommendation": "no-go",
            "severity": "critical",
            "findings": [{"severity": "critical", "deterministic": False}],
            "warnings": [],
        }

        status, detail = evidence_law_status(report)

        self.assertEqual(status, "Needs review")
        self.assertIn("lacks linked deterministic evidence", detail)
        self.assertIn("before treating severe claims", next_action_text(report, status))

    def test_report_header_signals_do_not_satisfy_severe_report_without_severe_finding(
        self,
    ) -> None:
        report = {
            "recommendation": "no-go",
            "severity": "critical",
            "findings": [{"severity": "medium", "deterministic": True}],
            "evidence_items": [],
            "warnings": [],
        }

        status, detail = evidence_law_status(report)

        self.assertEqual(status, "Needs review")
        self.assertIn("report is severe", detail)

    def test_report_header_signals_require_linked_deterministic_evidence(self) -> None:
        report = {
            "recommendation": "no-go",
            "severity": "critical",
            "findings": [
                {
                    "severity": "critical",
                    "deterministic": True,
                    "evidence_refs": ["missing-evidence"],
                }
            ],
            "evidence_items": [],
            "warnings": [],
        }

        status, detail = evidence_law_status(report)

        self.assertEqual(status, "Needs review")
        self.assertIn("lacks linked deterministic evidence", detail)


if __name__ == "__main__":
    unittest.main()
