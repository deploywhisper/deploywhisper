"""Tests for deployment outcome API routes."""

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
import services.project_service as project_service_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment
from app import create_app
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from models.database import SessionLocal
from models.repositories.incident_records import create_incident_record
from parsers.base import ParseBatchResult, ParsedFileResult


class DeploymentOutcomesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "deployments.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["DEPLOYWHISPER_OUTCOME_TOKEN"] = "outcome-secret"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
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
            audit_context={"source_interface": "api"},
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("DEPLOYWHISPER_OUTCOME_TOKEN", None)
        self.tempdir.cleanup()

    def test_webhook_endpoint_records_and_lists_deployment_outcomes(self) -> None:
        workspace = project_service_module.create_workspace(
            project_key=self.project.project_key,
            workspace_key="prod",
            display_name="Production",
        )
        scoped_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments-prod.tf",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=52,
                severity="medium",
                recommendation="caution",
                top_risk="Production outcome test report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: production outcome test report.",
                explanation="Production outcome test report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=self.project.id,
            workspace_id=workspace.id,
            audit_context={"source_interface": "api"},
        )
        with SessionLocal() as session:
            incident = create_incident_record(
                session,
                title="Payments rollback",
                severity="high",
                source_file="payments-incident.md",
                incident_date="2026-04-30",
                project_id=self.project.id,
                workspace_id=workspace.id,
                content="Payments deploy rolled back after elevated errors.",
            )

        response = self.client.post(
            "/api/v1/deployments/outcomes",
            headers={"X-DeployWhisper-Outcome-Token": "outcome-secret"},
            json={
                "analysis_id": scoped_report["id"],
                "outcome": "rollback",
                "deployed_at": "2026-04-30T08:15:00Z",
                "linked_incident_id": incident.id,
                "environment": "prod",
                "summary": "Rollback completed.",
                "notes": "Rollback completed after checkout errors.",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["analysis_id"], scoped_report["id"])
        self.assertEqual(payload["data"]["project"]["project_key"], "payments")
        self.assertEqual(payload["data"]["workspace"]["workspace_key"], "prod")
        self.assertEqual(payload["data"]["outcome"], "rolled_back")
        self.assertEqual(payload["data"]["linked_incident_id"], incident.id)
        self.assertEqual(payload["data"]["summary"], "Rollback completed.")
        self.assertEqual(
            payload["data"]["notes"], "Rollback completed after checkout errors."
        )

        list_response = self.client.get(
            "/api/v1/deployments/outcomes",
            params={"analysis_id": scoped_report["id"]},
        )
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        self.assertEqual(list_payload["meta"]["count"], 1)
        self.assertEqual(list_payload["data"][0]["outcome"], "rolled_back")
        self.assertEqual(
            list_payload["data"][0]["notes"],
            "Rollback completed after checkout errors.",
        )

    def test_webhook_endpoint_returns_standard_error_for_unknown_analysis(self) -> None:
        response = self.client.post(
            "/api/v1/deployments/outcomes",
            headers={"X-DeployWhisper-Outcome-Token": "outcome-secret"},
            json={
                "analysis_id": 999,
                "outcome": "failure",
                "deployed_at": "2026-04-30T08:15:00Z",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "analysis_not_found")

    def test_webhook_endpoint_rejects_missing_token(self) -> None:
        response = self.client.post(
            "/api/v1/deployments/outcomes",
            json={
                "analysis_id": self.persisted_report["id"],
                "outcome": "success",
                "deployed_at": "2026-04-30T08:15:00Z",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["error"]["code"],
            "deployment_outcome_ingest_forbidden",
        )

    def test_webhook_endpoint_denies_role_without_outcome_manage(self) -> None:
        response = self.client.post(
            "/api/v1/deployments/outcomes",
            headers={
                "X-DeployWhisper-Outcome-Token": "outcome-secret",
                "X-DeployWhisper-Project-Role": "reviewer",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
            json={
                "analysis_id": self.persisted_report["id"],
                "outcome": "success",
                "deployed_at": "2026-04-30T08:15:00Z",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn(self.project.project_key, payload["error"]["message"])

    def test_outcome_list_denies_project_outside_actor_scope(self) -> None:
        response = self.client.get(
            "/api/v1/deployments/outcomes",
            params={"analysis_id": self.persisted_report["id"]},
            headers={
                "X-DeployWhisper-Project-Role": "reviewer",
                "X-DeployWhisper-Project-Keys": "platform",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")
        self.assertNotIn(self.project.project_key, payload["error"]["message"])

    def test_outcome_list_authorizes_analysis_before_supplied_project_scope(
        self,
    ) -> None:
        platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        response = self.client.get(
            "/api/v1/deployments/outcomes",
            params={
                "analysis_id": self.persisted_report["id"],
                "project_key": platform.project_key,
            },
            headers={
                "X-DeployWhisper-Project-Role": "reviewer",
                "X-DeployWhisper-Project-Keys": platform.project_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")

    def test_outcome_create_authorizes_analysis_before_supplied_project_scope(
        self,
    ) -> None:
        platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )

        response = self.client.post(
            "/api/v1/deployments/outcomes",
            headers={
                "X-DeployWhisper-Outcome-Token": "outcome-secret",
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": platform.project_key,
            },
            json={
                "analysis_id": self.persisted_report["id"],
                "project_key": platform.project_key,
                "outcome": "success",
                "deployed_at": "2026-04-30T08:15:00Z",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")

    def test_outcome_list_masks_missing_analysis_for_scoped_actor(self) -> None:
        response = self.client.get(
            "/api/v1/deployments/outcomes",
            params={"analysis_id": 999},
            headers={
                "X-DeployWhisper-Project-Role": "reviewer",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")

    def test_outcome_list_rejects_workspace_id_without_project_scope(self) -> None:
        response = self.client.get(
            "/api/v1/deployments/outcomes",
            params={"workspace_id": 999},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "missing_project_scope")

    def test_outcome_list_masks_foreign_workspace_for_scoped_actor(self) -> None:
        platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        workspace = project_service_module.create_workspace(
            project_key=platform.project_key,
            workspace_key="prod",
            display_name="Production",
        )

        response = self.client.get(
            "/api/v1/deployments/outcomes",
            params={
                "analysis_id": self.persisted_report["id"],
                "workspace_id": workspace.id,
            },
            headers={
                "X-DeployWhisper-Project-Role": "reviewer",
                "X-DeployWhisper-Project-Keys": self.project.project_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_forbidden")
