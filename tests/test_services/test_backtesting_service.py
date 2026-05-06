"""Tests for weekly outcome backtesting and calibration feed helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from importlib import reload
from pathlib import Path
from unittest import mock

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.backtesting_service as backtesting_service_module
import services.deployment_outcome_service as deployment_outcome_service_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module
import services.report_service as report_service_module
from models.repositories.settings import get_setting, upsert_setting
from analysis.risk_scorer import RiskAssessment
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult


class BacktestingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "backtesting.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(deployment_outcome_service_module)
        reload(backtesting_service_module)
        database_module.init_db()
        self.project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _persist_report(
        self,
        *,
        top_risk: str,
        recommendation: str,
        severity: str,
        file_name: str,
    ) -> dict:
        return report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name=file_name,
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=66 if recommendation != "go" else 12,
                severity=severity,
                recommendation=recommendation,
                top_risk=top_risk,
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence=top_risk,
                explanation=top_risk,
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=self.project.id,
            audit_context={"source_interface": "api"},
        )

    def _recent_deployed_at(self, *, hours_ago: int = 24) -> str:
        return (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()

    def test_run_weekly_backtest_computes_failed_deploy_warning_rows(self) -> None:
        warned_report = self._persist_report(
            top_risk="Warned deploy failed later.",
            recommendation="no-go",
            severity="high",
            file_name="warned.tf",
        )
        quiet_report = self._persist_report(
            top_risk="Go recommendation later failed.",
            recommendation="go",
            severity="low",
            file_name="quiet.tf",
        )
        success_report = self._persist_report(
            top_risk="Warned deploy succeeded.",
            recommendation="caution",
            severity="medium",
            file_name="success.tf",
        )

        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=quiet_report["id"],
            outcome="rolled_back",
            deployed_at="2026-04-29T10:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=success_report["id"],
            outcome="success",
            deployed_at="2026-04-29T11:00:00Z",
        )

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(summary["project"]["project_key"], "payments")
        self.assertEqual(summary["failed_deploy_count"], 2)
        self.assertEqual(summary["warned_failed_deploy_count"], 1)
        self.assertEqual(summary["overall_recall"], 0.5)
        self.assertEqual(summary["overall_precision"], 0.5)
        self.assertEqual(len(summary["backtest_rows"]), 2)
        self.assertTrue(summary["backtest_rows"][0]["did_warn"])
        self.assertFalse(summary["backtest_rows"][1]["did_warn"])

    def test_run_due_weekly_backtests_persists_and_reuses_snapshot(self) -> None:
        warned_report = self._persist_report(
            top_risk="Warned deploy failed later.",
            recommendation="caution",
            severity="medium",
            file_name="warned.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )

        first = backtesting_service_module.run_due_weekly_backtests(
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
        )
        second = backtesting_service_module.run_due_weekly_backtests(
            now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        )

        self.assertTrue(
            any(item["project"]["project_key"] == "payments" for item in first)
        )
        self.assertEqual(second, [])

        cached = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )
        self.assertEqual(cached["failed_deploy_count"], 1)
        self.assertEqual(cached["warned_failed_deploy_count"], 1)

    def test_run_weekly_backtest_ignores_incident_only_links_without_failed_outcome(
        self,
    ) -> None:
        linked_report = self._persist_report(
            top_risk="Go recommendation later triggered incident.",
            recommendation="go",
            severity="low",
            file_name="linked-incident.tf",
        )

        incident_service_module.ingest_incident_document(
            "incident.md",
            "# Linked incident\nDate: 2026-04-29\nSeverity: high\nRollback after deploy.",
            analysis_id=linked_report["id"],
        )

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(summary["failed_deploy_count"], 0)
        self.assertEqual(summary["warned_failed_deploy_count"], 0)
        self.assertEqual(summary["overall_recall"], 0.0)
        self.assertEqual(summary["backtest_rows"], [])

    def test_run_weekly_backtest_attaches_linked_incident_to_failed_outcome_row(
        self,
    ) -> None:
        warned_report = self._persist_report(
            top_risk="Warned deploy later linked to incident.",
            recommendation="caution",
            severity="medium",
            file_name="warned-incident.tf",
        )

        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        incident = incident_service_module.ingest_incident_document(
            "incident.md",
            "# Linked incident\nDate: 2026-04-29\nSeverity: high\nDeploy later failed in production.",
            analysis_id=warned_report["id"],
        )

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(summary["failed_deploy_count"], 1)
        self.assertEqual(summary["warned_failed_deploy_count"], 1)
        self.assertEqual(summary["overall_precision"], 1.0)
        self.assertEqual(summary["overall_recall"], 1.0)
        self.assertEqual(summary["backtest_rows"][0]["incident_id"], incident["id"])

    def test_run_weekly_backtest_counts_multiple_outcomes_for_one_analysis(
        self,
    ) -> None:
        warned_report = self._persist_report(
            top_risk="Warned deploy recorded twice.",
            recommendation="caution",
            severity="medium",
            file_name="duplicate-outcomes.tf",
        )

        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="rolled_back",
            deployed_at="2026-04-29T10:00:00Z",
        )

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(summary["failed_deploy_count"], 2)
        self.assertEqual(summary["warned_failed_deploy_count"], 2)
        self.assertEqual(summary["overall_precision"], 1.0)
        self.assertEqual(summary["overall_recall"], 1.0)
        self.assertEqual(len(summary["backtest_rows"]), 2)
        self.assertEqual(summary["backtest_rows"][0]["outcome"], "failure")
        self.assertEqual(summary["backtest_rows"][1]["outcome"], "rolled_back")

    def test_run_due_weekly_backtests_accepts_legacy_naive_last_run_timestamps(
        self,
    ) -> None:
        default_project = project_service_module.ensure_default_project()
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:last_run_at:project:{self.project.id}",
                value="2026-04-29T12:00:00",
            )
            upsert_setting(
                session,
                key=f"backtesting:last_run_at:project:{default_project.id}",
                value="2026-04-29T12:00:00",
            )

        summaries = backtesting_service_module.run_due_weekly_backtests(
            now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        )

        self.assertEqual(summaries, [])

    def test_fetch_calibration_dashboard_seed_does_not_stamp_last_run_on_cache_miss(
        self,
    ) -> None:
        warned_report = self._persist_report(
            top_risk="Warned deploy failed later.",
            recommendation="caution",
            severity="medium",
            file_name="warned.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at=self._recent_deployed_at(hours_ago=24),
        )

        summary = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )

        self.assertEqual(summary["failed_deploy_count"], 1)
        with database_module.SessionLocal() as session:
            self.assertIsNone(
                get_setting(
                    session,
                    f"backtesting:last_run_at:project:{self.project.id}",
                )
            )

    def test_record_deployment_outcome_invalidates_cached_snapshot(self) -> None:
        warned_report = self._persist_report(
            top_risk="Warned deploy failed later.",
            recommendation="caution",
            severity="medium",
            file_name="warned.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at=self._recent_deployed_at(hours_ago=24),
        )
        first = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )

        quiet_report = self._persist_report(
            top_risk="Go recommendation later failed.",
            recommendation="go",
            severity="low",
            file_name="quiet.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=quiet_report["id"],
            outcome="failure",
            deployed_at=self._recent_deployed_at(hours_ago=23),
        )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )

        self.assertEqual(first["failed_deploy_count"], 1)
        self.assertEqual(refreshed["failed_deploy_count"], 2)
        self.assertEqual(refreshed["warned_failed_deploy_count"], 1)

    def test_run_due_weekly_backtests_continues_after_one_project_failure(self) -> None:
        other_project = project_service_module.create_project(
            project_key="search",
            display_name="Search",
        )
        warned_report = self._persist_report(
            top_risk="Warned deploy failed later.",
            recommendation="caution",
            severity="medium",
            file_name="warned.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )

        original = backtesting_service_module.run_weekly_backtest

        def flaky_run_weekly_backtest(**kwargs):
            if kwargs.get("project_id") == other_project.id:
                raise RuntimeError("boom")
            return original(**kwargs)

        with mock.patch(
            "services.backtesting_service.run_weekly_backtest",
            side_effect=flaky_run_weekly_backtest,
        ):
            summaries = backtesting_service_module.run_due_weekly_backtests(
                now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
            )

        project_keys = {summary["project"]["project_key"] for summary in summaries}
        self.assertIn("payments", project_keys)
        self.assertNotIn("search", project_keys)
