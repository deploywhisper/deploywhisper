"""Fail-closed contracts for Story 16.19 live qualification drivers."""

from __future__ import annotations

import unittest

from scripts.qualify_https_collection import require_terminal_collection
from scripts.qualify_https_runner_faults import qualification_summary, require


class Story1619QualificationHarnessTests(unittest.TestCase):
    def test_collection_requires_terminal_success_and_report(self):
        require_terminal_collection({"state": "succeeded"}, [{"report_id": 1}])
        for state, links in (
            ("running", [{"report_id": 1}]),
            ("failed", [{"report_id": 1}]),
            ("succeeded", []),
        ):
            with self.subTest(state=state, links=bool(links)):
                with self.assertRaises(RuntimeError):
                    require_terminal_collection({"state": state}, links)

    def test_only_complete_runner_fault_corpus_is_qualified(self):
        records = [
            {"case": "wire-lease-expiry"},
            {"case": "running-revocation"},
            {"case": "log-cap"},
        ]
        self.assertTrue(
            qualification_summary(None, "https://localhost", records, [])["qualified"]
        )
        self.assertFalse(
            qualification_summary("log-cap", "https://localhost", records[-1:], [])[
                "qualified"
            ]
        )
        self.assertFalse(
            qualification_summary(None, "https://localhost", records[:-1], [])[
                "qualified"
            ]
        )

    def test_explicit_requirement_raises_in_optimized_python_too(self):
        with self.assertRaisesRegex(RuntimeError, "required"):
            require(False, "required qualification condition")


if __name__ == "__main__":
    unittest.main()
