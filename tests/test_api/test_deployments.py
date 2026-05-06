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
        response = self.client.post(
            "/api/v1/deployments/outcomes",
            headers={"X-DeployWhisper-Outcome-Token": "outcome-secret"},
            json={
                "analysis_id": self.persisted_report["id"],
                "outcome": "success",
                "deployed_at": "2026-04-30T08:15:00Z",
                "environment": "prod",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["analysis_id"], self.persisted_report["id"])
        self.assertEqual(payload["data"]["project"]["project_key"], "payments")
        self.assertEqual(payload["data"]["outcome"], "success")

        list_response = self.client.get(
            "/api/v1/deployments/outcomes",
            params={"analysis_id": self.persisted_report["id"]},
        )
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        self.assertEqual(list_payload["meta"]["count"], 1)
        self.assertEqual(list_payload["data"][0]["outcome"], "success")

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
