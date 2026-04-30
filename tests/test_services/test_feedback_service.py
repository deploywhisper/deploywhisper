"""Tests for reviewer feedback capture and summaries."""

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
import services.feedback_service as feedback_service_module
import services.project_service as project_service_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment
from evidence.models import Finding
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult


class FeedbackServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "feedback.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(feedback_service_module)
        database_module.init_db()

        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self.report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=44,
                severity="medium",
                recommendation="caution",
                top_risk="Payments report for feedback tests.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: payments feedback test report.",
                explanation="Feedback test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            findings=[
                Finding(
                    finding_id="finding-001",
                    analysis_id=0,
                    title="MEDIUM: payments security group",
                    description="Security group needs review.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            project_id=self.project.id,
            audit_context={"source_interface": "ui"},
        )
        self.finding_id = self.report["findings"][0]["finding_id"]

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_record_finding_feedback_persists_useful_and_false_positive_reason(
        self,
    ) -> None:
        event = feedback_service_module.record_finding_feedback(
            analysis_id=self.report["id"],
            finding_id=self.finding_id,
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Known compensating control already covers this.",
        )

        self.assertEqual(event["analysis_id"], self.report["id"])
        self.assertEqual(event["finding_id"], self.finding_id)
        self.assertFalse(event["useful"])
        self.assertTrue(event["false_positive_flag"])
        self.assertEqual(
            event["false_positive_reason"],
            "Known compensating control already covers this.",
        )

    def test_record_false_negative_feedback_persists_report_level_note(self) -> None:
        event = feedback_service_module.record_false_negative_feedback(
            analysis_id=self.report["id"],
            note="Missed the lack of rollback alarms on the payments API.",
        )

        self.assertEqual(event["analysis_id"], self.report["id"])
        self.assertIsNone(event["finding_id"])
        self.assertEqual(
            event["false_negative_note"],
            "Missed the lack of rollback alarms on the payments API.",
        )
        self.assertEqual(event["outcome_label"], "missed")

    def test_feedback_summary_uses_latest_finding_feedback_state(self) -> None:
        feedback_service_module.record_finding_feedback(
            analysis_id=self.report["id"],
            finding_id=self.finding_id,
            useful=True,
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=self.report["id"],
            finding_id=self.finding_id,
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Flagged after reviewer confirmation.",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=self.report["id"],
            note="Missed a payments failover prerequisite.",
        )

        summary = feedback_service_module.fetch_feedback_summary(
            project_id=self.project.id
        )

        self.assertEqual(summary["project"]["project_key"], "payments")
        self.assertEqual(summary["current_state"]["useful_count"], 0)
        self.assertEqual(summary["current_state"]["not_useful_count"], 1)
        self.assertEqual(summary["current_state"]["false_positive_count"], 1)
        self.assertEqual(summary["current_state"]["missed_finding_count"], 1)
        self.assertEqual(summary["totals"]["events_recorded"], 3)
        self.assertIn(
            "payments failover prerequisite", summary["recent_notes"][0]["text"]
        )

    def test_record_finding_feedback_rejects_unknown_finding(self) -> None:
        with self.assertRaises(feedback_service_module.FeedbackError) as ctx:
            feedback_service_module.record_finding_feedback(
                analysis_id=self.report["id"],
                finding_id="missing-finding",
                useful=True,
            )

        self.assertEqual(ctx.exception.code, "finding_not_found")
