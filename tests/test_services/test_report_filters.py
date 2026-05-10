"""Tests for report filtering and retrieval helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import EvidenceItem, Finding
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class ReportFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(report_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _persist(
        self,
        *,
        severity: str,
        recommendation: str,
        top_risk: str,
        source_interface: str = "ui",
    ) -> None:
        evidence_id = f"ev-{severity}"
        finding_id = f"finding-{severity}"
        severe_report = severity in {"high", "critical"}
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
                            summary=top_risk,
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity=severity,
            recommendation=recommendation,
            top_risk=top_risk,
            top_risk_contributors=[evidence_id] if severe_report else [],
            contributors=[
                RiskContributor(
                    evidence_id=evidence_id if severe_report else None,
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary=top_risk,
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence=top_risk,
            explanation=top_risk,
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            audit_context={"source_interface": source_interface},
            findings=[
                Finding(
                    finding_id=finding_id,
                    analysis_id=0,
                    title=f"{severity.upper()}: {top_risk}",
                    description=top_risk,
                    severity=severity,
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=[evidence_id],
                    skill_id=None,
                )
            ]
            if severe_report
            else None,
            evidence_items=[
                EvidenceItem(
                    evidence_id=evidence_id,
                    analysis_id=0,
                    finding_id=finding_id,
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary=top_risk,
                    severity_hint=severity,
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ]
            if severe_report
            else None,
        )

    def test_fetch_filtered_analysis_history_filters_by_severity_and_search(
        self,
    ) -> None:
        self._persist(
            severity="high", recommendation="caution", top_risk="Database exposure risk"
        )
        self._persist(severity="low", recommendation="go", top_risk="Minor change")

        high_reports = report_service_module.fetch_filtered_analysis_history(
            severity="high"
        )
        self.assertEqual(len(high_reports), 1)
        self.assertEqual(high_reports[0]["severity"], "high")

        search_reports = report_service_module.fetch_filtered_analysis_history(
            search="Database exposure"
        )
        self.assertEqual(len(search_reports), 1)
        self.assertIn("Database exposure", search_reports[0]["top_risk"])

    def test_fetch_filtered_analysis_history_retains_audit_metadata(self) -> None:
        self._persist(
            severity="high",
            recommendation="caution",
            top_risk="Database exposure risk",
            source_interface="api",
        )

        reports = report_service_module.fetch_filtered_analysis_history()

        self.assertEqual(reports[0]["audit"]["source_interface"], "api")
        self.assertEqual(reports[0]["audit"]["llm_provider"], "ollama")
        self.assertEqual(reports[0]["report_schema_version"], "v2")

    def test_fetch_filtered_analysis_history_page_limits_results_and_reports_total_count(
        self,
    ) -> None:
        for index in range(6):
            self._persist(
                severity="high" if index % 2 == 0 else "low",
                recommendation="caution",
                top_risk=f"Risk {index}",
            )

        page_one = report_service_module.fetch_filtered_analysis_history_page(
            page=1, page_size=2
        )
        page_two = report_service_module.fetch_filtered_analysis_history_page(
            page=2, page_size=2
        )

        self.assertEqual(len(page_one["items"]), 2)
        self.assertEqual(len(page_two["items"]), 2)
        self.assertEqual(page_one["total_count"], 6)
        self.assertEqual(page_two["page"], 2)

    def test_remove_analysis_reports_supports_single_and_bulk_delete(self) -> None:
        self._persist(
            severity="high",
            recommendation="caution",
            top_risk="Database exposure risk",
            source_interface="api",
        )
        self._persist(
            severity="low",
            recommendation="go",
            top_risk="Minor change",
            source_interface="ui",
        )

        reports = report_service_module.fetch_filtered_analysis_history()
        self.assertEqual(len(reports), 2)

        removed_one = report_service_module.remove_analysis_report(reports[0]["id"])
        self.assertTrue(removed_one)
        reports_after_single = report_service_module.fetch_filtered_analysis_history()
        self.assertEqual(len(reports_after_single), 1)

        removed_many = report_service_module.remove_analysis_reports(
            [report["id"] for report in reports_after_single]
        )
        self.assertEqual(removed_many, 1)
        self.assertEqual(report_service_module.fetch_filtered_analysis_history(), [])
