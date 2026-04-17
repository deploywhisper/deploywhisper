"""Helpers and smoke tests for the history page."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload

import app as app_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.report_service as report_service_module
import ui.routes.history as history_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange
from ui.formatters.datetime import format_history_timestamp
from ui.formatters.recommendations import recommendation_classes, recommendation_text
from ui.routes.history import page_selection_state


class HistoryPageHelpersTests(unittest.TestCase):
    def test_format_history_timestamp_humanizes_iso_values(self) -> None:
        self.assertEqual(
            format_history_timestamp("2026-04-16T15:24:44.380822"),
            "Apr 16, 2026 · 3:24 PM",
        )

    def test_page_selection_state_handles_empty_partial_and_full_pages(self) -> None:
        self.assertEqual(page_selection_state(set(), {1, 2}), (False, 0))
        self.assertEqual(page_selection_state({1, 2, 3}, {1}), (False, 1))
        self.assertEqual(page_selection_state({1, 2, 3}, {1, 2, 3, 4}), (True, 3))

    def test_recommendation_helpers_preserve_semantic_go_no_go_styling(self) -> None:
        self.assertEqual(recommendation_text("no-go"), "NO-GO")
        self.assertIn("text-red-600", recommendation_classes("no-go"))
        self.assertIn("text-green-600", recommendation_classes("go"))


class HistoryPageRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "history.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(report_service_module)
        reload(history_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _persist_report(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.main",
                            action="modify",
                            summary="Security group exposure risk",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Security group exposure risk",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
            source="heuristic+llm",
        )
        narrative = NarrativeResult(
            opening_sentence="Ingress widens access to production resources.",
            explanation="Review the security group change before deployment.",
            guidance=[],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )
        report_service_module.persist_analysis_report(parse_batch, assessment, narrative, audit_context={"source_interface": "ui"})

    def test_history_page_renders_toolbar_and_report_actions(self) -> None:
        self._persist_report()

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Select all on page", response.text)
        self.assertIn("Delete selected", response.text)
        self.assertIn("Security group exposure risk", response.text)
        self.assertIn("NO-GO", response.text)
        self.assertIn("Risk: heuristic+llm", response.text)
        self.assertIn("Narrative: llm", response.text)


if __name__ == "__main__":
    unittest.main()
