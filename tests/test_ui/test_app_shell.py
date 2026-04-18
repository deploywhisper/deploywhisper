"""Smoke test for the dashboard shell."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch
from importlib import reload

import app as app_module
import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.report_service as report_service_module
import ui.components.upload_panel as upload_panel_module
import ui.routes.dashboard as dashboard_module
import ui.routes.history as history_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class DashboardShellTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "ui.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(report_service_module)
        reload(upload_panel_module)
        reload(dashboard_module)
        reload(history_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_root_page_contains_deploywhisper_shell_text(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DeployWhisper", response.text)
        self.assertIn("Upload deployment artifacts", response.text)
        self.assertIn("Deploy review", response.text)
        self.assertIn("Deployment briefing", response.text)
        self.assertIn("Last scan: none yet", response.text)
        self.assertIn("Analysis snapshot", response.text)
        self.assertIn("Files scanned", response.text)
        self.assertNotIn("Foundation ready", response.text)

    def test_history_page_contains_back_to_dashboard_action(self) -> None:
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Back to dashboard", response.text)

    def test_dashboard_shows_persisted_result_provenance_when_active_report_exists(
        self,
    ) -> None:
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
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Risk scoring: heuristic+llm", response.text)
        self.assertIn("Narrative: llm", response.text)
        self.assertIn("Provider: ollama / ollama/llama3", response.text)
        self.assertIn("Skills: git, terraform", response.text)
        self.assertIn("Last scan: plan.json · CRITICAL · NO-GO", response.text)
        self.assertIn(
            "1 saved briefing is shaping the current advisory view.", response.text
        )

    def test_dashboard_shows_llm_fallback_notice_for_active_report(self) -> None:
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
            partial_context=False,
            warnings=[
                "LLM severity assessment unavailable; falling back to heuristic matrix: provider offline"
            ],
            source="heuristic-only",
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
        report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Narrative provider unavailable: provider offline", response.text)

    def test_dashboard_failure_does_not_return_api_error_envelope(self) -> None:
        client = TestClient(app_module.create_app(), raise_server_exceptions=False)
        with patch("app.build_dashboard", side_effect=RuntimeError("ui boom")):
            response = client.get("/")

        self.assertEqual(response.status_code, 500)
        self.assertNotEqual(response.headers.get("content-type"), "application/json")
        self.assertNotIn('"error"', response.text)


if __name__ == "__main__":
    unittest.main()
