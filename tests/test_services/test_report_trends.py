"""Tests for report trend aggregation."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class ReportTrendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(report_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _persist(self, *, severity: str, recommendation: str, tool: str, source_interface: str = "ui") -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="input.json",
                    tool=tool,
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="input.json",
                            tool=tool,
                            resource_id=f"{tool}/resource",
                            action="modify",
                            summary=f"{tool} change",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity=severity,
            recommendation=recommendation,
            top_risk=f"{tool} change",
            contributors=[
                RiskContributor(
                    source_file="input.json",
                    tool=tool,
                    resource_id=f"{tool}/resource",
                    action="modify",
                    contribution=12,
                    summary=f"{tool} change",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence=f"{recommendation.upper()}: {tool} change",
            explanation=f"{tool} change explanation",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            audit_context={"source_interface": source_interface},
        )

    def test_fetch_risk_trends_summarizes_severity_and_tools(self) -> None:
        self._persist(severity="high", recommendation="caution", tool="terraform")
        self._persist(severity="critical", recommendation="no-go", tool="kubernetes")
        trends = report_service_module.fetch_risk_trends()
        self.assertEqual(trends["total_reports"], 2)
        self.assertEqual(trends["severity_counts"]["high"], 1)
        self.assertEqual(trends["severity_counts"]["critical"], 1)
        self.assertEqual(trends["tool_counts"]["terraform"], 1)
        self.assertEqual(len(trends["audit_rows"]), 2)
        self.assertEqual(trends["audit_rows"][0]["audit"]["llm_provider"], "ollama")

    def test_fetch_dashboard_stats_counts_scanned_files_and_severity(self) -> None:
        self._persist(severity="low", recommendation="go", tool="terraform")
        self._persist(severity="critical", recommendation="no-go", tool="cloudformation")

        stats = report_service_module.fetch_dashboard_stats()

        self.assertEqual(stats["total_files_scanned"], 2)
        self.assertEqual(stats["severity_counts"]["low"], 1)
        self.assertEqual(stats["severity_counts"]["critical"], 1)
        self.assertEqual(stats["severity_counts"]["medium"], 0)
