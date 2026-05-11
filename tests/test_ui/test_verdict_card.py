"""Tests for verdict-card confidence and context warning helpers."""

from __future__ import annotations

import unittest

from ui.components.verdict_card import _has_limited_context, _primary_confidence


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


if __name__ == "__main__":
    unittest.main()
