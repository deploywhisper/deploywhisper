"""Tests for report persistence and retrieval."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.report_service as report_service_module
import services.settings_service as settings_service_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class ReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(settings_service_module)
        reload(report_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_persist_analysis_report_stores_and_returns_metadata(self) -> None:
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
                            summary="Terraform changed a security group.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform aws_security_group.main is the highest-impact change.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Inspect the change table."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            audit_context={"source_interface": "api", "trigger_type": "session", "trigger_id": "sess-123"},
        )
        self.assertIn("id", persisted)
        self.assertEqual(persisted["audit"]["source_interface"], "api")
        self.assertEqual(persisted["audit"]["trigger_type"], "session")
        self.assertEqual(persisted["audit"]["trigger_id"], "sess-123")
        self.assertEqual(persisted["audit"]["files_analyzed"], ["plan.json"])
        self.assertEqual(persisted["audit"]["llm_provider"], "ollama")
        self.assertEqual(persisted["assessment_source"], "heuristic-only")
        self.assertEqual(persisted["narrative_source"], "llm")
        self.assertEqual(persisted["narrative_provider"], "ollama")
        self.assertEqual(persisted["narrative_model"], "ollama/llama3")
        self.assertEqual(persisted["skills_applied"], ["git", "terraform"])

        fetched = report_service_module.fetch_analysis_report(persisted["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["risk_score"], 42)
        self.assertEqual(fetched["audit"]["source_interface"], "api")
        self.assertEqual(fetched["audit"]["files_analyzed"], ["plan.json"])
        self.assertEqual(fetched["assessment_source"], "heuristic-only")
        self.assertEqual(fetched["narrative_source"], "llm")
        self.assertEqual(fetched["skills_applied"], ["git", "terraform"])
        self.assertNotIn("prompt", json.dumps(fetched))

        history = report_service_module.fetch_analysis_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], persisted["id"])
        self.assertEqual(history[0]["audit"]["llm_provider"], "ollama")

    def test_persist_analysis_report_combines_assessment_and_narrative_warnings(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="deployment.yaml",
                    tool="kubernetes",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="deployment.yaml",
                            tool="kubernetes",
                            resource_id="Deployment/api",
                            action="apply",
                            summary="Kubernetes deployment included in analysis.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Kubernetes deployment requires review.",
            contributors=[
                RiskContributor(
                    source_file="deployment.yaml",
                    tool="kubernetes",
                    resource_id="Deployment/api",
                    action="apply",
                    contribution=12,
                    summary="Kubernetes deployment requires review.",
                )
            ],
            interaction_risks=[],
            partial_context=True,
            warnings=["LLM severity assessment unavailable; falling back to heuristic matrix: provider offline"],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the deployment.",
            explanation="Fallback output used.",
            guidance=[],
            degraded=True,
            warnings=["Narrative provider unavailable: provider offline"],
            source="fallback",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "kubernetes"],
        )

        persisted = report_service_module.persist_analysis_report(parse_batch, assessment, narrative)

        self.assertIn("LLM severity assessment unavailable", " ".join(persisted["warnings"]))
        self.assertIn("Narrative provider unavailable", " ".join(persisted["warnings"]))

    def test_fetch_active_dashboard_report_returns_recent_dashboard_upload(self) -> None:
        settings_service_module.save_dashboard_result_display_duration_seconds(600)
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
                            summary="Terraform changed a security group.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=75,
            severity="high",
            recommendation="no-go",
            top_risk="High-risk change",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=75,
                    summary="Terraform changed a security group.",
                    severity="high",
                    reasoning="Security group changes can affect production ingress.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Inspect the change table."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            audit_context={"source_interface": "ui", "trigger_type": "dashboard_upload"},
        )

        active = report_service_module.fetch_active_dashboard_report(now=datetime.now(UTC) + timedelta(seconds=120))

        self.assertIsNotNone(active)
        self.assertEqual(active["recommendation"], "no-go")
        self.assertEqual(active["dashboard_display_duration_seconds"], 600)
        self.assertEqual(active["assessment_source"], "heuristic-only")
        self.assertEqual(active["narrative_source"], "llm")
        self.assertEqual(active["skills_applied"], ["git", "terraform"])
        self.assertGreater(active["dashboard_remaining_seconds"], 0)

    def test_init_db_upgrades_existing_analysis_reports_table_for_audit_columns(self) -> None:
        database_module.engine.dispose()
        sqlite_conn = sqlite3.connect(self.db_path)
        sqlite_conn.execute("DROP TABLE IF EXISTS analysis_reports")
        sqlite_conn.execute(
            """
            CREATE TABLE analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                risk_score INTEGER,
                severity VARCHAR(20),
                recommendation VARCHAR(20),
                top_risk TEXT,
                parse_summary TEXT,
                narrative_opening TEXT,
                narrative_explanation TEXT,
                warnings_json TEXT DEFAULT '[]',
                contributors_json TEXT DEFAULT '[]',
                created_at TEXT
            )
            """
        )
        sqlite_conn.commit()
        sqlite_conn.close()

        reload(database_module)
        reload(report_service_module)
        database_module.init_db()

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
                            summary="Terraform changed a security group.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform aws_security_group.main is the highest-impact change.",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Inspect the change table."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        persisted = report_service_module.persist_analysis_report(parse_batch, assessment, narrative)
        self.assertIn("audit", persisted)
        self.assertEqual(persisted["audit"]["files_analyzed"], ["plan.json"])


if __name__ == "__main__":
    unittest.main()
