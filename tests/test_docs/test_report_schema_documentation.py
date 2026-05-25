"""Tests for report schema documentation coverage."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_SCHEMA_GUIDE = REPO_ROOT / "docs" / "schemas" / "report-v2.md"


class ReportSchemaDocumentationTests(unittest.TestCase):
    def test_report_v2_guide_covers_machine_consumers_and_contract_fields(
        self,
    ) -> None:
        self.assertTrue(REPORT_SCHEMA_GUIDE.exists(), "Report v2 guide is missing.")
        content = REPORT_SCHEMA_GUIDE.read_text(encoding="utf-8").lower()

        for consumer in (
            "persisted `analysis_reports` rows",
            "api analysis payloads",
            "cli analysis payloads",
            "share-summary json payloads",
            "pr comment",
            "benchmark",
            "agent",
        ):
            with self.subTest(consumer=consumer):
                self.assertIn(consumer, content)

        for field in (
            '"api_version"',
            '"report_schema_version"',
            '"findings"',
            '"evidence_items"',
            '"report_schema_versions"',
            '"context_completeness"',
            '"narrative_available"',
            '"narrative_degraded"',
            '"narrative_failure_notice"',
            '"advisory_only"',
            '"should_block"',
            '"top_risk"',
        ):
            with self.subTest(field=field):
                self.assertIn(field, content)

    def test_report_v2_guide_documents_share_summary_v1_additive_compatibility(
        self,
    ) -> None:
        content = REPORT_SCHEMA_GUIDE.read_text(encoding="utf-8").lower()

        self.assertIn("share-summary payload `version` remains `v1`", content)
        self.assertIn("additive fields are compatible", content)


if __name__ == "__main__":
    unittest.main()
