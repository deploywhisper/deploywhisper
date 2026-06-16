"""Tests for read-only dashboard stats API routes."""

from __future__ import annotations

import os
import sqlite3
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
import services.stats_service as stats_service_module
from analysis.risk_scorer import RiskAssessment
from app import create_app
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class StatsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "stats-api.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(stats_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())

        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
            default_branch="main",
        )
        self.workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
            environment="prod",
        )
        self.clean_report = self._persist_report(
            file_name="clean-plan.json",
            score=12,
            severity="low",
            recommendation="go",
            duration=12,
            project_id=self.project.id,
            workspace_id=self.workspace.id,
        )
        self.high_report = self._persist_report(
            file_name="risky-plan.json",
            score=88,
            severity="high",
            recommendation="no-go",
            duration=18,
            project_id=self.project.id,
            workspace_id=self.workspace.id,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                (
                    "UPDATE analysis_reports "
                    "SET severity = ?, recommendation = ? WHERE id = ?"
                ),
                ("high", "no-go", self.high_report["id"]),
            )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _persist_report(
        self,
        *,
        file_name: str,
        score: int,
        severity: str,
        recommendation: str,
        duration: int,
        project_id: int,
        workspace_id: int,
    ) -> dict:
        return report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name=file_name,
                        tool="terraform",
                        status="parsed",
                        changes=[
                            UnifiedChange(
                                source_file=file_name,
                                tool="terraform",
                                resource_id="aws_security_group.main",
                                action="modify",
                                summary="Terraform changed a security group.",
                            )
                        ],
                    )
                ]
            ),
            RiskAssessment(
                score=score,
                severity=severity,
                recommendation=recommendation,
                top_risk=f"{severity} deployment risk.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence=f"{recommendation.upper()}: {severity} risk.",
                explanation="Review the deployment before release.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project_id,
            workspace_id=workspace_id,
            analysis_duration_seconds=duration,
        )

    def test_stats_summary_returns_dashboard_kpis_and_series(self) -> None:
        response = self.client.get(
            "/api/v1/stats/summary",
            params={"project_key": "payments", "workspace_key": "prod"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["app"], "DeployWhisper")
        self.assertEqual(payload["meta"]["version"], "1.2.0")
        data = payload["data"]
        self.assertEqual(data["total_analyses"], 2)
        self.assertEqual(data["totals"]["analyses"], 2)
        self.assertEqual(data["clean_verdict_rate"], 50.0)
        self.assertEqual(data["open_high_critical_count"], 1)
        self.assertEqual(data["avg_time_to_verdict_seconds"], 15.0)
        for series in data["series"].values():
            self.assertEqual(len(series), 7)
            self.assertIn("date", series[-1])
            self.assertIn("value", series[-1])
        self.assertEqual(data["series"]["analyses"][-1]["value"], 2.0)
        self.assertEqual(data["series"]["clean_verdict_rate"][-1]["value"], 50.0)
        self.assertEqual(
            data["series"]["open_high_critical_count"][-1]["value"],
            1.0,
        )

    def test_verdict_distribution_counts_recommendations(self) -> None:
        response = self.client.get(
            "/api/v1/stats/verdict-distribution",
            params={"days": 30, "project_id": self.project.id},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["days"], 30)
        self.assertEqual(data["counts"], {"go": 1, "caution": 0, "no-go": 1})
        self.assertEqual(data["total"], 2)
        self.assertIn("window_start", data)
        self.assertIn("window_end", data)

    def test_stats_routes_return_not_found_for_unknown_project(self) -> None:
        response = self.client.get(
            "/api/v1/stats/summary",
            params={"project_key": "missing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")


if __name__ == "__main__":
    unittest.main()
