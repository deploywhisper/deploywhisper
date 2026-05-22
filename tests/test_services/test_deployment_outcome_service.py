"""Tests for deployment outcome capture and retrieval."""

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
import services.deployment_outcome_service as deployment_outcome_service_module
import services.project_service as project_service_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment
from llm.narrator import NarrativeResult
from models.database import SessionLocal
from models.repositories.incident_records import create_incident_record
from parsers.base import ParseBatchResult, ParsedFileResult


class DeploymentOutcomeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "outcomes.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(deployment_outcome_service_module)
        database_module.init_db()

        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self.workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        self.persisted_report = report_service_module.persist_analysis_report(
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
                score=18,
                severity="low",
                recommendation="go",
                top_risk="Scoped deployment history test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: deployment history test report.",
                explanation="Deployment history test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            audit_context={"source_interface": "api"},
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_record_deployment_outcome_uses_report_project_and_returns_payload(
        self,
    ) -> None:
        with SessionLocal() as session:
            incident = create_incident_record(
                session,
                title="Checkout degraded",
                severity="high",
                source_file="incident.md",
                incident_date="2026-04-30",
                project_id=self.project.id,
                workspace_id=self.workspace.id,
                content="Rollback needed after checkout deployment.",
            )

        recorded = deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=self.persisted_report["id"],
            outcome="rolled_back",
            deployed_at="2026-04-30T08:15:00Z",
            linked_incident_id=incident.id,
            environment="prod",
            summary="Rollback completed after checkout errors.",
            notes="Operator notes captured during post-deploy review.",
            source_interface="api",
        )

        self.assertEqual(recorded["analysis_id"], self.persisted_report["id"])
        self.assertEqual(recorded["project"]["project_key"], "payments")
        self.assertEqual(recorded["workspace"]["workspace_key"], "prod")
        self.assertEqual(recorded["outcome"], "rolled_back")
        self.assertEqual(recorded["linked_incident_id"], incident.id)
        self.assertEqual(recorded["environment"], "prod")
        self.assertEqual(
            recorded["summary"], "Rollback completed after checkout errors."
        )
        self.assertEqual(
            recorded["notes"], "Operator notes captured during post-deploy review."
        )
        self.assertEqual(recorded["deployed_at"], "2026-04-30T08:15:00+00:00")

    def test_record_deployment_outcome_accepts_notes_and_rollback_alias(
        self,
    ) -> None:
        with SessionLocal() as session:
            incident = create_incident_record(
                session,
                title="Payments rollback",
                severity="high",
                source_file="payments-incident.md",
                incident_date="2026-04-30",
                project_id=self.project.id,
                workspace_id=self.workspace.id,
                content="Payments deploy rolled back after elevated errors.",
            )

        recorded = deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=self.persisted_report["id"],
            outcome="rollback",
            deployed_at="2026-04-30T09:45:00Z",
            linked_incident_id=incident.id,
            environment="prod",
            notes="Rollback captured from deployment review notes.",
        )

        self.assertEqual(recorded["outcome"], "rolled_back")
        self.assertEqual(recorded["linked_incident_id"], incident.id)
        self.assertEqual(recorded["project"]["project_key"], "payments")
        self.assertEqual(recorded["workspace"]["workspace_key"], "prod")
        self.assertIsNone(recorded["summary"])
        self.assertEqual(
            recorded["notes"], "Rollback captured from deployment review notes."
        )

    def test_record_deployment_outcome_rejects_mismatched_project_reference(
        self,
    ) -> None:
        other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        with self.assertRaises(
            deployment_outcome_service_module.DeploymentOutcomeError
        ) as ctx:
            deployment_outcome_service_module.record_deployment_outcome(
                analysis_id=self.persisted_report["id"],
                outcome="success",
                project_id=other_project.id,
            )

        self.assertEqual(ctx.exception.code, "conflicting_project_reference")

    def test_record_deployment_outcome_rejects_cross_project_incident_link(
        self,
    ) -> None:
        other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        with SessionLocal() as session:
            incident = create_incident_record(
                session,
                title="Platform degraded",
                severity="high",
                source_file="platform-incident.md",
                incident_date="2026-04-30",
                project_id=other_project.id,
                content="Platform rollback needed.",
            )

        with self.assertRaises(
            deployment_outcome_service_module.DeploymentOutcomeError
        ) as ctx:
            deployment_outcome_service_module.record_deployment_outcome(
                analysis_id=self.persisted_report["id"],
                outcome="rolled_back",
                linked_incident_id=incident.id,
            )

        self.assertEqual(ctx.exception.code, "conflicting_incident_scope")

    def test_list_deployment_outcomes_filters_by_analysis_id(self) -> None:
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=self.persisted_report["id"],
            outcome="success",
            deployed_at="2026-04-30T08:15:00Z",
            source_interface="api",
        )

        other_project = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        other_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="platform.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=20,
                severity="low",
                recommendation="go",
                top_risk="Other project report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: other project report.",
                explanation="Other project report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=other_project.id,
            audit_context={"source_interface": "api"},
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=other_report["id"],
            outcome="failure",
            deployed_at="2026-04-30T09:30:00Z",
            source_interface="api",
        )

        results = deployment_outcome_service_module.list_deployment_outcomes(
            analysis_id=self.persisted_report["id"]
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["analysis_id"], self.persisted_report["id"])
        self.assertEqual(results[0]["project"]["project_key"], "payments")
        self.assertEqual(results[0]["workspace"]["workspace_key"], "prod")

    def test_list_deployment_outcomes_filters_by_workspace_id(self) -> None:
        staging_workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=self.persisted_report["id"],
            outcome="success",
            deployed_at="2026-04-30T08:15:00Z",
            source_interface="api",
        )
        staging_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments-staging.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=20,
                severity="low",
                recommendation="go",
                top_risk="Staging report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: staging report.",
                explanation="Staging report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=self.project.id,
            workspace_id=staging_workspace.id,
            audit_context={"source_interface": "api"},
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=staging_report["id"],
            outcome="failure",
            deployed_at="2026-04-30T09:30:00Z",
            source_interface="api",
        )

        results = deployment_outcome_service_module.list_deployment_outcomes(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["analysis_id"], self.persisted_report["id"])
        self.assertEqual(results[0]["workspace"]["workspace_key"], "prod")
