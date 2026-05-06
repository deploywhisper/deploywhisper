"""Tests for incident ingestion and retrieval."""

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
import services.incident_service as incident_service_module
import services.project_service as project_service_module
import analysis.incident_matcher as incident_matcher_module
from analysis.risk_scorer import RiskAssessment
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult


class IncidentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "incidents.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(incident_service_module)
        reload(incident_matcher_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_ingest_incident_document_persists_record(self) -> None:
        result = incident_service_module.ingest_incident_document(
            "incident.md",
            "# Database exposure\nDate: 2026-04-16\nSeverity: P1\nThe security group was opened too broadly.",
            project_id=self.project.id,
        )
        self.assertEqual(result["title"], "Database exposure")
        self.assertEqual(result["severity"], "critical")
        self.assertEqual(result["incident_date"], "2026-04-16")

        records = incident_service_module.get_incident_records(
            project_id=self.project.id
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_file"], "incident.md")
        self.assertEqual(records[0]["project_id"], self.project.id)

    def test_ingest_incident_document_requires_project_scope(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            incident_service_module.ingest_incident_document(
                "incident.md",
                "# Database exposure\nSeverity: high\nRollback required.",
            )

        self.assertIn("Project scope is required", str(ctx.exception))

    def test_incident_matcher_can_load_stored_candidates(self) -> None:
        incident_service_module.ingest_incident_document(
            "incident.md",
            "# Database exposure\nSeverity: high\nThe security group was opened too broadly.",
            project_id=self.project.id,
        )
        candidates = incident_matcher_module.load_incident_candidates(
            project_id=self.project.id
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "Database exposure")

    def test_incident_candidates_do_not_cross_project_or_workspace(self) -> None:
        other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        prod_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        staging_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        incident_service_module.ingest_incident_document(
            "payments-prod.md",
            "# Payments prod exposure\nSeverity: high\nPayment API ingress opened.",
            project_id=self.project.id,
            workspace_id=prod_workspace.id,
        )
        incident_service_module.ingest_incident_document(
            "payments-staging.md",
            "# Payments staging exposure\nSeverity: high\nPayment API ingress opened.",
            project_id=self.project.id,
            workspace_id=staging_workspace.id,
        )
        incident_service_module.ingest_incident_document(
            "platform.md",
            "# Platform exposure\nSeverity: high\nPlatform ingress opened.",
            project_id=other_project.id,
        )

        prod_candidates = incident_matcher_module.load_incident_candidates(
            project_id=self.project.id,
            workspace_id=prod_workspace.id,
        )
        project_candidates = incident_matcher_module.load_incident_candidates(
            project_id=self.project.id,
        )

        self.assertEqual(
            [item["source_file"] for item in prod_candidates], ["payments-prod.md"]
        )
        self.assertEqual(
            [item["source_file"] for item in project_candidates],
            ["payments-prod.md", "payments-staging.md"],
        )

    def test_ingest_plain_text_without_heading_or_severity_uses_fallbacks(self) -> None:
        result = incident_service_module.ingest_incident_document(
            "plain.txt",
            "Database access widened during deployment and required emergency rollback.",
            project_id=self.project.id,
        )
        self.assertEqual(
            result["title"],
            "Database access widened during deployment and required emergency rollback.",
        )
        self.assertEqual(result["severity"], "unknown")
        self.assertIsNone(result["incident_date"])

    def test_ingest_incident_document_can_reference_analysis_id(self) -> None:
        project = self.project
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="incident-link.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=10,
                severity="low",
                recommendation="go",
                top_risk="Linked incident test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: linked incident test report.",
                explanation="Linked incident test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        result = incident_service_module.ingest_incident_document(
            "incident.md",
            "# Linked incident\nSeverity: high\nRollback after deploy.",
            analysis_id=report["id"],
        )

        self.assertEqual(result["analysis_id"], report["id"])
        records = incident_service_module.get_incident_records(project_id=project.id)
        self.assertEqual(records[0]["analysis_id"], report["id"])
        self.assertEqual(records[0]["project_id"], project.id)


if __name__ == "__main__":
    unittest.main()
