"""Helpers and smoke tests for the history page."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload

import app as app_module
import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.report_service as report_service_module
import ui.routes.history as history_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from analysis.rollback_planner import RollbackPlan, RollbackStep
from evidence.models import Finding
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
        self.assertIn("dw-danger-text", recommendation_classes("no-go"))
        self.assertIn("dw-success-text", recommendation_classes("go"))


class HistoryPageRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "history.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(report_service_module)
        reload(history_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("APP_BASE_URL", None)
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _persist_report(
        self,
        *,
        score: int = 88,
        severity: str = "critical",
        recommendation: str = "no-go",
        top_risk: str = "Security group exposure risk",
        opening_sentence: str = "Ingress widens access to production resources.",
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
                            summary="Security group exposure risk",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=score,
            severity=severity,
            recommendation=recommendation,
            top_risk=top_risk,
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
            opening_sentence=opening_sentence,
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
        report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            rollback_plan=RollbackPlan(
                steps=[
                    RollbackStep(
                        order=1,
                        title="Revert aws_security_group.main",
                        detail="Rollback the terraform change safely.",
                        estimated_minutes=15,
                        critical=True,
                    )
                ],
                complexity="medium",
                complexity_score=3,
                complexity_explanation=(
                    "Score 3/5 because the plan covers 1 rollback step."
                ),
                warning=None,
            ),
            findings=[
                Finding(
                    finding_id="finding-001",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.main",
                    description="Security group exposure risk",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-001"],
                    skill_id=None,
                )
            ],
            audit_context={"source_interface": "ui"},
        )

    def test_history_page_renders_toolbar_and_report_actions(self) -> None:
        self._persist_report()

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Select all on page", response.text)
        self.assertIn("Delete selected", response.text)
        self.assertIn("Security group exposure risk", response.text)
        self.assertIn("NO-GO", response.text)
        self.assertIn("HIGH CONFIDENCE", response.text)
        self.assertIn('"title":"Confidence 1.00"', response.text)
        self.assertIn("Risk: heuristic+llm", response.text)
        self.assertIn("Narrative: llm", response.text)

    def test_history_page_shows_diff_indicator_for_rescanned_same_artifact(
        self,
    ) -> None:
        self._persist_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Initial security group review",
            opening_sentence="Initial review of the security group change.",
        )
        self._persist_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure risk",
            opening_sentence="Ingress widens access to production resources.",
        )

        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Rescan diff", response.text)
        self.assertIn("+46 risk vs report #1", response.text)
        self.assertIn("MEDIUM → CRITICAL", response.text)
        self.assertIn("CAUTION → NO-GO", response.text)

    def test_history_detail_route_renders_dedicated_report_page(self) -> None:
        self._persist_report()

        response = self.client.get("/history/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Back to History", response.text)
        self.assertIn("Analysis report detail", response.text)
        self.assertIn("Rollback plan", response.text)
        self.assertIn("Revert aws_security_group.main", response.text)
        self.assertIn("Findings table", response.text)
        self.assertIn("Context completeness", response.text)
        self.assertIn("Blast radius", response.text)
        self.assertIn("Audit metadata", response.text)
        self.assertNotIn('"data-dw-modal-root":"1"', response.text)

    def test_public_report_route_renders_read_only_share_view(self) -> None:
        self._persist_report()

        response = self.client.get("/reports/1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Shared DeployWhisper report", response.text)
        self.assertIn("Analysis report", response.text)
        self.assertNotIn("Delete selected", response.text)

    def test_public_report_route_requires_password_and_redacts_filenames(self) -> None:
        self._persist_report()
        report_service_module.configure_report_share(
            1,
            password="s3cret-pass",
            redact_filenames=True,
        )

        prompt_response = self.client.get("/reports/1")
        self.assertEqual(prompt_response.status_code, 200)
        self.assertIn("Password required", prompt_response.text)
        self.assertIn("method='post'", prompt_response.text)

        shared_response = self.client.post(
            "/reports/1/unlock",
            data={"password": "s3cret-pass"},
            follow_redirects=True,
        )
        self.assertEqual(shared_response.status_code, 200)
        self.assertIn("Artifact 1", shared_response.text)
        self.assertNotIn("plan.json", shared_response.text)
        self.assertNotIn("password=s3cret-pass", shared_response.text)

    def test_public_report_unlock_sets_secure_cookie_for_https_share_urls(self) -> None:
        os.environ["APP_BASE_URL"] = "https://install.example.com"
        self._persist_report()
        report_service_module.configure_report_share(
            1,
            password="s3cret-pass",
            redact_filenames=True,
        )

        response = self.client.post(
            "/reports/1/unlock",
            data={"password": "s3cret-pass"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        cookie_header = response.headers.get("set-cookie", "")
        self.assertIn("Secure", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("Path=/reports/1", cookie_header)

    def test_history_page_keeps_legacy_query_parameter_as_detail_fallback(self) -> None:
        self._persist_report()

        response = self.client.get("/history?report_id=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Analysis report detail", response.text)
        self.assertIn("Back to History", response.text)


if __name__ == "__main__":
    unittest.main()
