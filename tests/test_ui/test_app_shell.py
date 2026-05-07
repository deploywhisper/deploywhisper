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
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.project_service as project_service_module
import services.report_service as report_service_module
import ui.components.upload_panel as upload_panel_module
import ui.project_authorization as project_authorization_module
import ui.routes.dashboard as dashboard_module
import ui.routes.history as history_module
import ui.routes.settings as settings_module
import ui.theme as theme_module
from analysis.blast_radius import BlastRadiusResult, ImpactNode
from analysis.rollback_planner import RollbackPlan, RollbackStep
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import Finding
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
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(project_authorization_module)
        reload(theme_module)
        reload(history_module)
        reload(settings_module)
        reload(upload_panel_module)
        reload(dashboard_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEPLOYWHISPER_PROJECT_ROLE", None)
        os.environ.pop("DEPLOYWHISPER_PROJECT_KEYS", None)
        self.tempdir.cleanup()

    def test_root_page_contains_deploywhisper_shell_text(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DeployWhisper", response.text)
        self.assertIn("Active Project", response.text)
        self.assertIn("Search repo or project name", response.text)
        self.assertIn("New project", response.text)
        self.assertIn("Unassigned", response.text)
        self.assertIn("Default workspace", response.text)
        self.assertIn("dw-project-bar", response.text)
        self.assertIn("Upload deployment artifacts", response.text)
        self.assertIn("Deploy review", response.text)
        self.assertIn("Deployment briefing", response.text)
        self.assertIn("Last scan: none yet", response.text)
        self.assertIn("Analysis snapshot", response.text)
        self.assertIn("Files scanned", response.text)
        self.assertIn("/assets/favicon-512.png", response.text)
        self.assertIn("/assets/favicon.ico", response.text)
        self.assertNotIn("Foundation ready", response.text)
        self.assertNotIn("5-second verdict", response.text)

    def test_brand_icon_assets_are_served(self) -> None:
        brand_icon = self.client.get("/assets/favicon-512.png")
        favicon = self.client.get("/assets/favicon.ico")

        self.assertEqual(brand_icon.status_code, 200)
        self.assertEqual(brand_icon.headers["content-type"], "image/png")
        self.assertGreater(len(brand_icon.content), 0)
        self.assertEqual(favicon.status_code, 200)
        self.assertIn(
            favicon.headers["content-type"],
            {"image/x-icon", "image/vnd.microsoft.icon"},
        )
        self.assertGreater(len(favicon.content), 0)

    def test_history_page_contains_back_to_dashboard_action(self) -> None:
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Search repo or project name", response.text)
        self.assertIn("Back to dashboard", response.text)

    def test_shell_reflects_active_project_across_dashboard_and_history(self) -> None:
        payments = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        project_service_module.set_active_project(payments.id)

        dashboard_response = self.client.get("/")
        history_response = self.client.get("/history")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)
        self.assertIn("Active Project", dashboard_response.text)
        self.assertIn("Payments", dashboard_response.text)
        self.assertIn("Key payments", dashboard_response.text)
        self.assertIn("Active Project", history_response.text)
        self.assertIn("Payments", history_response.text)
        self.assertIn("Key payments", history_response.text)
        self.assertIn(
            "Project-scoped history for Payments (payments).",
            history_response.text,
        )

    def test_ui_pages_ignore_saved_active_project_when_actor_scope_is_invalid(
        self,
    ) -> None:
        platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        project_service_module.set_active_project(platform.id)
        platform_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="platform-plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=91,
                severity="critical",
                recommendation="no-go",
                top_risk="Platform-only risk.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="NO-GO: platform-only risk.",
                explanation="Platform-only risk.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=platform.id,
            audit_context={"source_interface": "ui"},
        )
        report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="unassigned-plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=15,
                severity="low",
                recommendation="go",
                top_risk="Unassigned risk.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: unassigned risk.",
                explanation="Unassigned risk.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            audit_context={"source_interface": "ui"},
        )
        os.environ["DEPLOYWHISPER_PROJECT_ROLE"] = "read-only"

        dashboard_response = self.client.get("/")
        project_service_module.set_active_project(platform.id)
        history_response = self.client.get("/history")
        project_service_module.set_active_project(platform.id)
        history_detail_response = self.client.get(f"/history/{platform_report['id']}")
        project_service_module.set_active_project(platform.id)
        history_compare_response = self.client.get(
            f"/history/{platform_report['id']}/compare"
        )
        project_service_module.set_active_project(platform.id)
        settings_response = self.client.get("/settings")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_detail_response.status_code, 200)
        self.assertEqual(history_compare_response.status_code, 200)
        self.assertEqual(settings_response.status_code, 200)
        self.assertIn(
            "Caller role requires an explicit project scope.",
            dashboard_response.text,
        )
        self.assertNotIn("Last scan: unassigned-plan.json", dashboard_response.text)
        self.assertNotIn("Last scan: platform-plan.json", dashboard_response.text)
        self.assertIn(
            "Caller role requires an explicit project scope.",
            history_response.text,
        )
        self.assertNotIn("unassigned-plan.json", history_response.text)
        self.assertNotIn("platform-plan.json", history_response.text)
        self.assertNotIn("Project-scoped history for Platform", history_response.text)
        self.assertIn(
            "Project authorization unavailable",
            history_detail_response.text,
        )
        self.assertIn(
            "Project authorization unavailable",
            history_compare_response.text,
        )
        self.assertNotIn("Platform-only risk.", history_detail_response.text)
        self.assertNotIn("platform-plan.json", history_detail_response.text)
        self.assertNotIn("Platform-only risk.", history_compare_response.text)
        self.assertNotIn("platform-plan.json", history_compare_response.text)
        self.assertIn(
            "Caller role requires an explicit project scope.",
            settings_response.text,
        )
        self.assertNotIn(
            "Active project: Platform (platform)",
            settings_response.text,
        )
        self.assertNotIn("Active file:", settings_response.text)
        self.assertTrue(project_service_module.has_active_project_selection())

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
            blast_radius=BlastRadiusResult(
                affected=[
                    ImpactNode(
                        service_id="database",
                        label="Primary Database",
                        depth=0,
                    ),
                    ImpactNode(
                        service_id="api",
                        label="Payments API",
                        depth=1,
                    ),
                ],
                direct_count=1,
                transitive_count=1,
                warning=None,
                unmatched_resources=[],
            ),
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
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )
        project_service_module.set_active_project(
            project_service_module.ensure_default_project().id
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("5-second verdict", response.text)
        self.assertIn("Risk score", response.text)
        self.assertIn("dw-verdict-score-value", response.text)
        self.assertIn('"text":"88"', response.text)
        self.assertIn("STRONG CONTEXT", response.text)
        self.assertNotIn("Know the risk before", response.text)
        self.assertEqual(response.text.count("5-second verdict"), 1)
        self.assertIn("Risk scoring: heuristic+llm", response.text)
        self.assertIn("Narrative: llm", response.text)
        self.assertIn("Provider: ollama / ollama/llama3", response.text)
        self.assertIn("Skills: git, terraform", response.text)
        self.assertIn("HIGH CONFIDENCE", response.text)
        self.assertIn('"title":"Confidence 1.00"', response.text)
        self.assertIn("Last scan: plan.json · CRITICAL · NO-GO", response.text)
        self.assertIn(
            "1 saved briefing is shaping the current advisory view.", response.text
        )
        self.assertIn("Findings table", response.text)
        self.assertIn("Reviewer feedback", response.text)
        self.assertIn("Thumbs up", response.text)
        self.assertIn("Thumbs down", response.text)
        self.assertIn("Missed finding note", response.text)
        self.assertIn("Severity", response.text)
        self.assertIn("Evidence", response.text)
        self.assertIn("View evidence", response.text)
        self.assertIn("Blast radius", response.text)
        self.assertIn("1 services directly affected, 1 transitively", response.text)
        self.assertIn("Rollback plan", response.text)
        self.assertIn("Copy full plan", response.text)
        self.assertIn("Critical path", response.text)
        self.assertIn("~15 min", response.text)
        self.assertIn('"data-dw-review-section":"verdict"', response.text)
        self.assertIn('"data-dw-review-section":"findings"', response.text)
        self.assertIn('"data-dw-review-section":"context"', response.text)
        self.assertIn('"data-dw-review-section":"blast-radius"', response.text)
        self.assertIn('"data-dw-review-section":"rollback"', response.text)
        self.assertIn('"data-dw-finding-row":"1"', response.text)
        self.assertIn('"tabindex":"0"', response.text)

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
            available=False,
            opening_sentence="",
            explanation="",
            guidance=[],
            degraded=True,
            warnings=["Narrative provider unavailable: provider offline"],
            failure_notice="Narrative provider unavailable: provider offline",
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
        project_service_module.set_active_project(
            project_service_module.ensure_default_project().id
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("5-second verdict", response.text)
        self.assertIn("Narrative provider unavailable: provider offline", response.text)
        self.assertIn("Narrative unavailable.", response.text)

    def test_dashboard_shows_context_warning_for_low_context_score(self) -> None:
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
            top_risk="Security group exposure risk",
            context_completeness={
                "topology_freshness_days": 45,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 0,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.52,
            },
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
            source="heuristic-only",
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
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
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )
        project_service_module.set_active_project(
            project_service_module.ensure_default_project().id
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("LIMITED CONTEXT", response.text)
        self.assertIn("Topology freshness", response.text)
        self.assertIn("45 days old", response.text)
        self.assertIn("STALE 30+", response.text)
        self.assertIn("Manage topology", response.text)
        self.assertIn("/settings#topology-context", response.text)
        self.assertIn("Context completeness", response.text)
        self.assertIn("Last import", response.text)
        self.assertIn("Terraform", response.text)
        self.assertIn("Fix in settings", response.text)
        self.assertIn(
            "Context warning: supporting topology or incident history may be stale.",
            response.text,
        )

    def test_dashboard_keeps_settings_fix_link_for_stale_topology_with_stronger_score(
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
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Security group exposure risk",
            context_completeness={
                "topology_freshness_days": 45,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 10,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.82,
            },
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
            source="heuristic-only",
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
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
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )
        project_service_module.set_active_project(
            project_service_module.ensure_default_project().id
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Topology freshness", response.text)
        self.assertIn("45 days old", response.text)
        self.assertIn("STALE 30+", response.text)
        self.assertIn("Manage topology", response.text)
        self.assertIn("/settings#topology-context", response.text)
        self.assertIn("Fix in settings", response.text)
        self.assertIn("/settings", response.text)

    def test_dashboard_shows_critical_topology_freshness_badge(self) -> None:
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
            top_risk="Security group exposure risk",
            context_completeness={
                "topology_freshness_days": 95,
                "topology_last_imported_at": "2026-01-18T11:22:33Z",
                "incident_index_size": 10,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.82,
            },
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
            source="heuristic-only",
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
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
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )
        project_service_module.set_active_project(
            project_service_module.ensure_default_project().id
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("95 days old", response.text)
        self.assertIn("CRITICAL 90+", response.text)

    def test_dashboard_failure_does_not_return_api_error_envelope(self) -> None:
        client = TestClient(app_module.create_app(), raise_server_exceptions=False)
        with patch("app.build_dashboard", side_effect=RuntimeError("ui boom")):
            response = client.get("/")

        self.assertEqual(response.status_code, 500)
        self.assertNotEqual(response.headers.get("content-type"), "application/json")
        self.assertNotIn('"error"', response.text)


if __name__ == "__main__":
    unittest.main()
