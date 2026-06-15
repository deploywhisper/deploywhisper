"""Tests for weekly outcome backtesting and calibration feed helpers."""

from __future__ import annotations

import json
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
import models.repositories.incident_records as incident_records_repository_module
import models.tables as tables_module
import services.artifact_snapshot_service as artifact_snapshot_service_module
import services.backtesting_service as backtesting_service_module
import services.deployment_outcome_service as deployment_outcome_service_module
import services.feedback_service as feedback_service_module
import services.incident_service as incident_service_module
import services.project_service as project_service_module
import services.report_service as report_service_module
from models.repositories.settings import get_setting, upsert_setting
from analysis.risk_scorer import RiskAssessment
from evidence.models import ContextCompleteness, EvidenceItem, Finding
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult


class BacktestingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "backtesting.db"
        self.snapshot_dir = Path(self.tempdir.name) / "report-artifacts"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["ARTIFACT_SNAPSHOT_DIR"] = str(self.snapshot_dir)
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(incident_records_repository_module)
        reload(artifact_snapshot_service_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(feedback_service_module)
        reload(deployment_outcome_service_module)
        reload(incident_service_module)
        reload(backtesting_service_module)
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

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("ARTIFACT_SNAPSHOT_DIR", None)
        self.tempdir.cleanup()

    def _persist_report(
        self,
        *,
        top_risk: str,
        recommendation: str,
        severity: str,
        file_name: str,
        confidence: float = 1.0,
        workspace_id: int | None = None,
        include_finding: bool = False,
        finding_count: int = 1,
    ) -> dict:
        findings = (
            [
                Finding(
                    finding_id=f"finding-{file_name.replace('.', '-')}-{index}",
                    analysis_id=0,
                    title=f"{severity.upper()}: {top_risk}",
                    description=top_risk,
                    severity=severity,
                    category="calibration/test",
                    deterministic=True,
                    confidence=confidence,
                    uncertainty_note=None,
                    evidence_refs=[],
                    skill_id=None,
                )
                for index in range(finding_count)
            ]
            if include_finding
            else []
        )
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
                confidence=confidence,
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
            findings=findings,
            project_id=self.project.id,
            workspace_id=workspace_id,
            audit_context={"source_interface": "api"},
        )

    def _persist_replay_report(
        self,
        *,
        file_name: str,
        extra_file_names: list[str] | None = None,
        recommendation: str = "go",
        severity: str = "low",
        project_id: int | None = None,
        workspace_id: int | None = None,
        artifact_snapshots: dict[str, bytes | None] | None = None,
    ) -> dict:
        file_names = [file_name, *(extra_file_names or [])]
        if artifact_snapshots is None:
            artifact_snapshots = {
                name: f"resource {name}\n".encode("utf-8") for name in file_names
            }
        return report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name=name,
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                    for name in file_names
                ]
            ),
            RiskAssessment(
                score=12 if recommendation == "go" else 66,
                severity=severity,
                recommendation=recommendation,
                top_risk=f"Replay fixture for {file_name}.",
                confidence=0.8,
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence=f"Replay fixture for {file_name}.",
                explanation=f"Replay fixture for {file_name}.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            findings=[
                Finding(
                    finding_id=f"expected-{file_name.replace('.', '-')}",
                    analysis_id=0,
                    title=f"Expected incident evidence for {file_name}",
                    description="Historical evidence expected during replay.",
                    severity=severity,
                    category="incident/backtest",
                    deterministic=True,
                    confidence=0.8,
                    uncertainty_note=None,
                    evidence_refs=[f"expected-evidence-{file_name.replace('.', '-')}"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id=f"expected-evidence-{file_name.replace('.', '-')}",
                    analysis_id=0,
                    finding_id=f"expected-{file_name.replace('.', '-')}",
                    source_type="artifact",
                    source_ref=f"artifact://{file_name}#expected",
                    artifact=file_name,
                    location="line 1",
                    resource="fixture",
                    operation="modify",
                    summary="Historical replay evidence.",
                    severity_hint=severity,
                    deterministic=True,
                    confidence=0.8,
                )
            ],
            project_id=project_id or self.project.id,
            workspace_id=workspace_id,
            audit_context={"source_interface": "api"},
            artifact_snapshots=artifact_snapshots,
        )

    def _fake_replay_artifacts(
        self,
        *,
        recommendation: str,
        severity: str,
        insufficient_context: bool = False,
    ):
        return mock.Mock(
            assessment=RiskAssessment(
                score=12 if recommendation == "go" else 66,
                severity=severity,
                recommendation=recommendation,
                top_risk="Replay assessment.",
                confidence=0.8,
                contributors=[],
                interaction_risks=[],
                context_completeness=ContextCompleteness(
                    context_score=0.4 if insufficient_context else 1.0,
                    confidence_level="low" if insufficient_context else "high",
                    insufficient_context=insufficient_context,
                    context_todos=["Import more topology."]
                    if insufficient_context
                    else [],
                ),
                partial_context=False,
                warnings=[],
            ),
            evidence_items=[
                EvidenceItem(
                    evidence_id="observed-evidence",
                    analysis_id=0,
                    finding_id="observed-finding",
                    source_type="artifact",
                    source_ref="artifact://fixture#observed",
                    artifact="fixture.tf",
                    location="line 1",
                    resource="fixture",
                    operation="modify",
                    summary="Observed replay evidence.",
                    severity_hint=severity,
                    deterministic=True,
                    confidence=0.8,
                )
            ],
            findings=[
                Finding(
                    finding_id="observed-finding",
                    analysis_id=0,
                    title="Observed replay finding",
                    description="Observed replay finding.",
                    severity=severity,
                    category="incident/backtest",
                    deterministic=True,
                    confidence=0.8,
                    uncertainty_note=None,
                    evidence_refs=["observed-evidence"],
                    skill_id=None,
                )
            ],
            submission_manifest=mock.Mock(accepted_artifact_count=1),
        )

    def _recent_deployed_at(self, *, hours_ago: int = 24) -> str:
        return (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()

    def _stamp_all_feedback_created_at(self, created_at: datetime) -> None:
        with database_module.SessionLocal() as session:
            events = session.query(tables_module.FeedbackEvent).all()
            for event in events:
                event.created_at = created_at
            session.commit()

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

    def test_run_weekly_backtest_includes_feedback_outcome_calibration_metrics(
        self,
    ) -> None:
        warned_failure_report = self._persist_report(
            top_risk="Warned production deploy failed later.",
            recommendation="no-go",
            severity="high",
            file_name="warned-failure.tf",
            confidence=0.88,
            workspace_id=self.workspace.id,
            include_finding=True,
        )
        warned_success_report = self._persist_report(
            top_risk="Warned production deploy succeeded.",
            recommendation="caution",
            severity="medium",
            file_name="warned-success.tf",
            confidence=0.72,
            workspace_id=self.workspace.id,
            include_finding=True,
        )
        quiet_failure_report = self._persist_report(
            top_risk="GO report missed rollback risk.",
            recommendation="go",
            severity="low",
            file_name="quiet-failure.tf",
            confidence=0.52,
            workspace_id=self.workspace.id,
        )
        staging = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        staging_report = self._persist_report(
            top_risk="Staging deploy should not enter prod metrics.",
            recommendation="no-go",
            severity="critical",
            file_name="staging.tf",
            confidence=0.95,
            workspace_id=staging.id,
        )

        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_failure_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_success_report["id"],
            outcome="success",
            deployed_at="2026-04-29T10:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=quiet_failure_report["id"],
            outcome="rolled_back",
            deployed_at="2026-04-29T11:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=staging_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T12:00:00Z",
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=warned_failure_report["id"],
            finding_id=warned_failure_report["findings"][0]["finding_id"],
            useful=True,
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=warned_success_report["id"],
            finding_id=warned_success_report["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="The compensating control already covered this.",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=quiet_failure_report["id"],
            note="Missed a rollback dependency that caused the incident.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))
        before = report_service_module.fetch_analysis_report(
            warned_success_report["id"]
        )

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )
        after = report_service_module.fetch_analysis_report(warned_success_report["id"])

        self.assertEqual(summary["workspace"]["workspace_key"], "prod")
        self.assertEqual(summary["failed_deploy_count"], 2)
        self.assertEqual(summary["warned_failed_deploy_count"], 1)
        self.assertEqual(summary["overall_precision"], 0.5)
        self.assertEqual(summary["overall_recall"], 0.5)
        metrics = summary["calibration_metrics"]
        self.assertEqual(metrics["sample_size"], 3)
        self.assertEqual(metrics["feedback_event_count"], 3)
        self.assertEqual(metrics["feedback_history_event_count"], 3)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall_proxy"], 0.5)
        self.assertEqual(metrics["false_positive_count"], 1)
        self.assertEqual(metrics["false_positive_rate"], 0.5)
        self.assertEqual(metrics["false_reassurance_count"], 2)
        self.assertEqual(metrics["false_reassurance_rate"], 0.5)
        self.assertEqual(
            metrics["recall_proxy_signals"]["failed_without_warning_count"], 1
        )
        self.assertEqual(
            summary["false_positive_cases"][0]["analysis_id"],
            warned_success_report["id"],
        )
        self.assertEqual(
            summary["false_reassurance_cases"][0]["analysis_id"],
            quiet_failure_report["id"],
        )
        confidence_buckets = summary["confidence_trends"]["buckets"]
        self.assertEqual(confidence_buckets["high"]["sample_count"], 1)
        self.assertEqual(confidence_buckets["medium"]["sample_count"], 1)
        self.assertEqual(confidence_buckets["low"]["sample_count"], 1)
        limitation_codes = {
            limitation["code"] for limitation in summary["confidence_limitations"]
        }
        self.assertIn("sparse_outcomes", limitation_codes)
        self.assertFalse(summary["statistical_certainty"])
        self.assertEqual(summary["confidence_label"], "Directional only")
        self.assertIsNotNone(before)
        self.assertIsNotNone(after)
        if before is None or after is None:
            self.fail("Expected report before and after calibration metrics.")
        self.assertEqual(after["severity"], before["severity"])
        self.assertEqual(after["recommendation"], before["recommendation"])
        self.assertEqual(after["confidence"], before["confidence"])

    def test_run_weekly_backtest_includes_feedback_only_calibration_inputs(
        self,
    ) -> None:
        feedback_only_report = self._persist_report(
            top_risk="Reviewer found a noisy warning without deployment outcome.",
            recommendation="caution",
            severity="medium",
            file_name="feedback-only.tf",
            workspace_id=self.workspace.id,
            include_finding=True,
        )

        feedback_service_module.record_finding_feedback(
            analysis_id=feedback_only_report["id"],
            finding_id=feedback_only_report["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Reviewer confirmed this warning was noisy.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        metrics = summary["calibration_metrics"]
        self.assertEqual(metrics["sample_size"], 0)
        self.assertEqual(metrics["feedback_event_count"], 1)
        self.assertEqual(metrics["false_positive_count"], 1)
        self.assertEqual(metrics["false_positive_rate"], 1.0)
        self.assertEqual(summary["false_positive_cases"][0]["severity"], "medium")
        limitation_codes = {
            limitation["code"] for limitation in summary["confidence_limitations"]
        }
        self.assertNotIn("no_calibration_inputs", limitation_codes)
        self.assertIn("sparse_outcomes", limitation_codes)
        self.assertIn("sparse_feedback", limitation_codes)
        self.assertIn("feedback_bias", limitation_codes)
        bucket_false_positive_count = sum(
            bucket["false_positive_count"]
            for bucket in summary["confidence_trends"]["buckets"].values()
        )
        self.assertEqual(bucket_false_positive_count, 0)

    def test_run_weekly_backtest_excludes_stale_feedback_from_window_metrics(
        self,
    ) -> None:
        stale_feedback_report = self._persist_report(
            top_risk="Old reviewer feedback should stay out of current calibration.",
            recommendation="caution",
            severity="medium",
            file_name="stale-feedback.tf",
            workspace_id=self.workspace.id,
            include_finding=True,
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=stale_feedback_report["id"],
            finding_id=stale_feedback_report["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Old reviewer feedback outside this window.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 1, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        metrics = summary["calibration_metrics"]
        self.assertEqual(metrics["feedback_event_count"], 0)
        self.assertEqual(metrics["feedback_history_event_count"], 1)
        self.assertEqual(metrics["false_positive_count"], 0)
        self.assertEqual(summary["false_positive_cases"], [])
        limitation_codes = {
            limitation["code"] for limitation in summary["confidence_limitations"]
        }
        self.assertIn("sparse_feedback", limitation_codes)
        self.assertNotIn("no_calibration_inputs", limitation_codes)

    def test_run_weekly_backtest_includes_feedback_only_false_reassurance(
        self,
    ) -> None:
        feedback_only_report = self._persist_report(
            top_risk="Reviewer found a missed risk without deployment outcome.",
            recommendation="go",
            severity="low",
            file_name="feedback-only-miss.tf",
            workspace_id=self.workspace.id,
            include_finding=True,
        )

        feedback_service_module.record_false_negative_feedback(
            analysis_id=feedback_only_report["id"],
            finding_id=feedback_only_report["findings"][0]["finding_id"],
            note="Reviewer identified a missed rollback dependency.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        metrics = summary["calibration_metrics"]
        self.assertEqual(metrics["sample_size"], 0)
        self.assertEqual(metrics["feedback_event_count"], 1)
        self.assertEqual(metrics["false_reassurance_count"], 1)
        self.assertEqual(metrics["false_reassurance_rate"], 0.0)
        self.assertEqual(metrics["deployment_false_reassurance_count"], 0)
        self.assertEqual(metrics["reviewer_missed_feedback_count"], 1)
        self.assertEqual(
            summary["false_reassurance_cases"][0]["analysis_id"],
            feedback_only_report["id"],
        )
        bucket_false_reassurance_count = sum(
            bucket["false_reassurance_count"]
            for bucket in summary["confidence_trends"]["buckets"].values()
        )
        self.assertEqual(bucket_false_reassurance_count, 0)
        limitation_codes = {
            limitation["code"] for limitation in summary["confidence_limitations"]
        }
        self.assertNotIn("no_calibration_inputs", limitation_codes)
        self.assertIn("feedback_bias", limitation_codes)

    def test_false_reassurance_cases_sort_by_event_timestamp(self) -> None:
        deployment_miss_report = self._persist_report(
            top_risk="Older GO deployment failed without warning.",
            recommendation="go",
            severity="low",
            file_name="older-deploy-miss.tf",
        )
        reviewer_miss_report = self._persist_report(
            top_risk="Newer reviewer missed finding should sort first.",
            recommendation="go",
            severity="low",
            file_name="newer-reviewer-miss.tf",
            workspace_id=self.workspace.id,
            include_finding=True,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=deployment_miss_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=reviewer_miss_report["id"],
            finding_id=reviewer_miss_report["findings"][0]["finding_id"],
            note="Reviewer identified a missed risk after the deploy event.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(
            [case["reason"] for case in summary["false_reassurance_cases"]],
            ["reviewer_missed_finding_feedback", "failed_without_warning"],
        )

    def test_run_weekly_backtest_bounds_feedback_rates_and_preserves_missed_cases(
        self,
    ) -> None:
        noisy_report = self._persist_report(
            top_risk="One warned report has multiple noisy findings.",
            recommendation="caution",
            severity="medium",
            file_name="multi-finding.tf",
            include_finding=True,
            finding_count=2,
        )
        missed_report = self._persist_report(
            top_risk="GO report missed multiple rollback risks.",
            recommendation="go",
            severity="low",
            file_name="multiple-misses.tf",
            include_finding=True,
            finding_count=2,
        )
        success_missed_report = self._persist_report(
            top_risk="Successful deploy has unrelated missed-feedback note.",
            recommendation="go",
            severity="low",
            file_name="successful-miss.tf",
            include_finding=True,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=noisy_report["id"],
            outcome="success",
            deployed_at="2026-04-29T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=missed_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T10:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=success_missed_report["id"],
            outcome="success",
            deployed_at="2026-04-29T11:00:00Z",
        )
        for finding in noisy_report["findings"]:
            feedback_service_module.record_finding_feedback(
                analysis_id=noisy_report["id"],
                finding_id=finding["finding_id"],
                useful=False,
                false_positive_flag=True,
                false_positive_reason="Reviewer confirmed noisy warning.",
            )
        for finding in missed_report["findings"]:
            feedback_service_module.record_false_negative_feedback(
                analysis_id=missed_report["id"],
                finding_id=finding["finding_id"],
                note="Missed a distinct rollback dependency.",
            )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=success_missed_report["id"],
            finding_id=success_missed_report["findings"][0]["finding_id"],
            note="This note should not count against a successful outcome.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        metrics = summary["calibration_metrics"]
        self.assertEqual(metrics["false_positive_count"], 2)
        self.assertEqual(metrics["false_positive_rate"], 1.0)
        self.assertEqual(metrics["false_reassurance_count"], 3)
        self.assertEqual(metrics["false_reassurance_rate"], 1.0)
        confidence_buckets = summary["confidence_trends"]["buckets"]
        self.assertEqual(confidence_buckets["high"]["false_positive_count"], 1)
        self.assertEqual(confidence_buckets["high"]["false_reassurance_count"], 1)
        self.assertEqual(
            {
                case["finding_id"]
                for case in summary["false_reassurance_cases"]
                if case["finding_id"] is not None
            },
            {finding["finding_id"] for finding in missed_report["findings"]},
        )

    def test_failed_without_warning_keeps_deployment_case_with_reviewer_miss(
        self,
    ) -> None:
        missed_report = self._persist_report(
            top_risk="GO report missed a deploy rollback.",
            recommendation="go",
            severity="low",
            file_name="deployment-and-reviewer-miss.tf",
            include_finding=True,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=missed_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=missed_report["id"],
            finding_id=missed_report["findings"][0]["finding_id"],
            note="Reviewer found the missed deploy risk after the failure.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(
            [case["reason"] for case in summary["false_reassurance_cases"]],
            ["reviewer_missed_finding_feedback", "failed_without_warning"],
        )
        metrics = summary["calibration_metrics"]
        self.assertEqual(metrics["deployment_false_reassurance_count"], 1)
        self.assertEqual(metrics["reviewer_missed_feedback_count"], 1)

    def test_feedback_bias_uses_reviewer_feedback_not_outcome_misses(self) -> None:
        quiet_failure_report = self._persist_report(
            top_risk="GO report later failed without reviewer feedback.",
            recommendation="go",
            severity="low",
            file_name="quiet-outcome-miss.tf",
        )
        useful_report = self._persist_report(
            top_risk="Useful warning should balance feedback mix.",
            recommendation="caution",
            severity="medium",
            file_name="useful-feedback.tf",
            include_finding=True,
        )
        noisy_report = self._persist_report(
            top_risk="Noisy warning should balance feedback mix.",
            recommendation="caution",
            severity="medium",
            file_name="noisy-feedback.tf",
            include_finding=True,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=quiet_failure_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T10:00:00Z",
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=useful_report["id"],
            finding_id=useful_report["findings"][0]["finding_id"],
            useful=True,
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=noisy_report["id"],
            finding_id=noisy_report["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Reviewer confirmed the warning was noisy.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        metrics = summary["calibration_metrics"]
        self.assertEqual(metrics["false_reassurance_count"], 1)
        self.assertEqual(metrics["deployment_false_reassurance_count"], 1)
        self.assertEqual(metrics["false_reassurance_rate"], 1.0)
        limitation_codes = {
            limitation["code"] for limitation in summary["confidence_limitations"]
        }
        self.assertNotIn("feedback_bias", limitation_codes)

    def test_warned_report_false_negative_feedback_is_not_false_reassurance(
        self,
    ) -> None:
        warned_report = self._persist_report(
            top_risk="Warned report should not be false reassurance.",
            recommendation="caution",
            severity="medium",
            file_name="warned-miss.tf",
            include_finding=True,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T10:00:00Z",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=warned_report["id"],
            finding_id=warned_report["findings"][0]["finding_id"],
            note="Reviewer added missed-finding context to a report that warned.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        metrics = summary["calibration_metrics"]
        self.assertEqual(summary["warned_failed_deploy_count"], 1)
        self.assertEqual(metrics["false_reassurance_count"], 0)
        self.assertEqual(summary["false_reassurance_cases"], [])

    def test_workspace_backtest_does_not_stamp_project_last_run(self) -> None:
        warned_report = self._persist_report(
            top_risk="Workspace backtest should not mark project due state.",
            recommendation="caution",
            severity="medium",
            file_name="workspace-last-run.tf",
            workspace_id=self.workspace.id,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(summary["failed_deploy_count"], 1)
        with database_module.SessionLocal() as session:
            self.assertIsNone(
                get_setting(
                    session,
                    f"backtesting:last_run_at:project:{self.project.id}",
                )
            )
            self.assertIsNotNone(
                get_setting(
                    session,
                    (
                        f"backtesting:snapshot:project:{self.project.id}"
                        f":workspace:{self.workspace.id}"
                    ),
                )
            )

    def test_workspace_calibration_seed_refreshes_stale_cached_snapshot(self) -> None:
        warned_report = self._persist_report(
            top_risk="Old workspace snapshot should refresh on read.",
            recommendation="caution",
            severity="medium",
            file_name="workspace-stale-cache.tf",
            workspace_id=self.workspace.id,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        old_summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 5, 8, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(old_summary["failed_deploy_count"], 1)
        self.assertEqual(refreshed["failed_deploy_count"], 0)
        self.assertEqual(
            refreshed["window"]["end"],
            "2026-05-08T12:00:00+00:00",
        )
        with database_module.SessionLocal() as session:
            self.assertIsNotNone(
                get_setting(
                    session,
                    (
                        f"backtesting:snapshot:project:{self.project.id}"
                        f":workspace:{self.workspace.id}"
                    ),
                )
            )

    def test_calibration_seed_refreshes_corrupt_cached_snapshot(self) -> None:
        warned_report = self._persist_report(
            top_risk="Corrupt cached calibration should self-heal.",
            recommendation="caution",
            severity="medium",
            file_name="corrupt-cache.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:snapshot:project:{self.project.id}",
                value="{not-valid-json",
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 1)
        self.assertEqual(refreshed["warned_failed_deploy_count"], 1)

    def test_calibration_seed_refreshes_future_dated_cached_snapshot(self) -> None:
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:snapshot:project:{self.project.id}",
                value=json.dumps(
                    {
                        "window": {
                            "end": "2026-05-20T12:00:00+00:00",
                            "days": 7,
                        },
                        "failed_deploy_count": 99,
                    }
                ),
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 0)
        self.assertEqual(
            refreshed["window"]["end"],
            "2026-04-30T12:00:00+00:00",
        )

    def test_calibration_seed_refreshes_old_schema_cached_snapshot(self) -> None:
        warned_report = self._persist_report(
            top_risk="Fresh old-schema cache should refresh on read.",
            recommendation="caution",
            severity="medium",
            file_name="old-schema-cache.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:snapshot:project:{self.project.id}",
                value=json.dumps(
                    {
                        "project": {"id": self.project.id},
                        "window": {
                            "end": "2026-04-30T12:00:00+00:00",
                            "days": 7,
                        },
                        "failed_deploy_count": 99,
                        "warned_failed_deploy_count": 0,
                        "overall_precision": 0.0,
                        "overall_recall": 0.0,
                    }
                ),
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 1)
        self.assertEqual(refreshed["warned_failed_deploy_count"], 1)
        self.assertIn("calibration_metrics", refreshed)

    def test_calibration_seed_rejects_wrong_window_cached_snapshot(self) -> None:
        cached = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )
        cached["window"]["days"] = 14
        cached["failed_deploy_count"] = 99
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:snapshot:project:{self.project.id}",
                value=json.dumps(cached),
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 0)
        self.assertEqual(refreshed["window"]["days"], 7)

    def test_calibration_seed_rejects_mismatched_window_bounds_snapshot(self) -> None:
        cached = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )
        cached["window"]["start"] = "2026-04-20T12:00:00+00:00"
        cached["failed_deploy_count"] = 99
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:snapshot:project:{self.project.id}",
                value=json.dumps(cached),
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 0)
        self.assertEqual(
            refreshed["window"]["start"],
            "2026-04-23T12:00:00+00:00",
        )

    def test_calibration_seed_rejects_partial_shape_cached_snapshot(self) -> None:
        cached = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )
        cached.pop("false_reassurance_cases")
        cached["failed_deploy_count"] = 99
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:snapshot:project:{self.project.id}",
                value=json.dumps(cached),
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 0)
        self.assertIn("false_reassurance_cases", refreshed)

    def test_calibration_seed_rejects_malformed_nested_metrics_snapshot(
        self,
    ) -> None:
        cached = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )
        cached["failed_deploy_count"] = 99
        cached["calibration_metrics"]["false_positive_rate"] = "1.0"
        cached["calibration_metrics"]["recall_proxy_signals"]["failed_deploy_count"] = (
            "0"
        )
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=f"backtesting:snapshot:project:{self.project.id}",
                value=json.dumps(cached),
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 0)
        self.assertIsInstance(
            refreshed["calibration_metrics"]["false_positive_rate"],
            float,
        )

    def test_workspace_calibration_seed_rejects_wrong_scope_cached_snapshot(
        self,
    ) -> None:
        staging = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        cached = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )
        cached["workspace"] = {
            "id": staging.id,
            "workspace_key": "staging",
            "display_name": "Staging",
        }
        cached["failed_deploy_count"] = 99
        with database_module.SessionLocal() as session:
            upsert_setting(
                session,
                key=(
                    f"backtesting:snapshot:project:{self.project.id}"
                    f":workspace:{self.workspace.id}"
                ),
                value=json.dumps(cached),
            )

        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            workspace_id=self.workspace.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(refreshed["failed_deploy_count"], 0)
        self.assertEqual(refreshed["workspace"]["id"], self.workspace.id)

    def test_confidence_trends_count_outcomes_and_preserve_unknown_confidence(
        self,
    ) -> None:
        duplicate_report = self._persist_report(
            top_risk="Duplicate outcomes should stay in confidence sample.",
            recommendation="caution",
            severity="medium",
            file_name="duplicate-confidence.tf",
            confidence=0.72,
        )
        unknown_report = self._persist_report(
            top_risk="Missing confidence should not become zero.",
            recommendation="go",
            severity="low",
            file_name="unknown-confidence.tf",
            confidence=0.51,
        )
        with database_module.SessionLocal() as session:
            risk_assessment = (
                session.query(tables_module.RiskAssessment)
                .filter_by(analysis_id=unknown_report["id"])
                .one()
            )
            session.delete(risk_assessment)
            session.commit()
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=duplicate_report["id"],
            outcome="failure",
            deployed_at="2026-04-29T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=duplicate_report["id"],
            outcome="rolled_back",
            deployed_at="2026-04-29T10:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=unknown_report["id"],
            outcome="success",
            deployed_at="2026-04-29T11:00:00Z",
        )

        summary = backtesting_service_module.run_weekly_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        buckets = summary["confidence_trends"]["buckets"]
        self.assertEqual(summary["confidence_trends"]["sample_size"], 3)
        self.assertEqual(buckets["medium"]["sample_count"], 2)
        self.assertEqual(buckets["medium"]["average_confidence"], 0.72)
        self.assertEqual(buckets["unknown"]["sample_count"], 1)
        self.assertIsNone(buckets["unknown"]["average_confidence"])

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
            project_id=self.project.id,
            now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
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

    def test_run_incident_backtest_replays_linked_report_artifacts(self) -> None:
        detected_report = self._persist_replay_report(
            file_name="detected.tf",
            recommendation="caution",
            severity="medium",
        )
        missed_report = self._persist_replay_report(file_name="missed.tf")
        insufficient_report = self._persist_replay_report(file_name="insufficient.tf")
        unsupported_report = self._persist_report(
            top_risk="Legacy report lacks stored replay artifacts.",
            recommendation="go",
            severity="low",
            file_name="unsupported.tf",
        )

        detected_incident = incident_service_module.ingest_incident_document(
            "detected-incident.md",
            "# Detected incident\nDate: 2026-04-29\nSeverity: high\nReplay should warn.",
            analysis_id=detected_report["id"],
        )
        incident_service_module.ingest_incident_document(
            "missed-incident.md",
            "# Missed incident\nDate: 2026-04-29\nSeverity: high\nReplay should miss.",
            analysis_id=missed_report["id"],
        )
        incident_service_module.ingest_incident_document(
            "insufficient-incident.md",
            "# Insufficient incident\nDate: 2026-04-29\nSeverity: high\nReplay lacks context.",
            analysis_id=insufficient_report["id"],
        )
        incident_service_module.ingest_incident_document(
            "unsupported-incident.md",
            "# Unsupported incident\nDate: 2026-04-29\nSeverity: high\nNo replay artifact snapshot.",
            analysis_id=unsupported_report["id"],
        )

        def fake_replay(files):
            artifact_name = files[0][0]
            if artifact_name == "detected.tf":
                return self._fake_replay_artifacts(
                    recommendation="caution",
                    severity="medium",
                )
            if artifact_name == "insufficient.tf":
                return self._fake_replay_artifacts(
                    recommendation="go",
                    severity="low",
                    insufficient_context=True,
                )
            return self._fake_replay_artifacts(recommendation="go", severity="low")

        with mock.patch(
            "services.backtesting_service._run_incident_replay_analysis",
            side_effect=fake_replay,
        ):
            result = backtesting_service_module.run_incident_backtest(
                project_id=self.project.id,
                now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            )

        self.assertFalse(result["passed"])
        self.assertEqual(result["summary"]["scenario_count"], 4)
        self.assertEqual(result["summary"]["detected_count"], 1)
        self.assertEqual(result["summary"]["missed_count"], 1)
        self.assertEqual(result["summary"]["insufficient_context_count"], 1)
        self.assertEqual(result["summary"]["unsupported_count"], 1)
        statuses = {
            scenario["incident"]["source_file"]: scenario["status"]
            for scenario in result["scenarios"]
        }
        self.assertEqual(statuses["detected-incident.md"], "detected")
        self.assertEqual(statuses["missed-incident.md"], "missed")
        self.assertEqual(statuses["insufficient-incident.md"], "insufficient_context")
        self.assertEqual(statuses["unsupported-incident.md"], "unsupported")
        detected = next(
            scenario
            for scenario in result["scenarios"]
            if scenario["incident"]["id"] == detected_incident["id"]
        )
        self.assertEqual(detected["replay_artifacts"], ["detected.tf"])
        self.assertEqual(detected["linked_report"]["id"], detected_report["id"])
        self.assertTrue(detected["expected_evidence"])
        self.assertEqual(
            detected["expected_evidence"][0]["artifact"],
            "detected.tf",
        )
        self.assertTrue(detected["observed_findings"][0]["evidence_refs"])
        self.assertEqual(detected["incident"]["project_id"], self.project.id)
        self.assertIsNone(detected["incident"]["workspace_id"])
        self.assertEqual(detected["linked_report"]["project_id"], self.project.id)
        self.assertIsNone(detected["linked_report"]["workspace_id"])

    def test_run_incident_backtest_reports_unlinked_incident_as_unsupported(
        self,
    ) -> None:
        incident_service_module.ingest_incident_document(
            "unlinked-incident.md",
            "# Unlinked incident\nDate: 2026-04-29\nSeverity: high\nNo replay report.",
            project_id=self.project.id,
        )

        result = backtesting_service_module.run_incident_backtest(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(result["summary"]["scenario_count"], 1)
        self.assertEqual(result["summary"]["unsupported_count"], 1)
        self.assertEqual(result["scenarios"][0]["status"], "unsupported")
        self.assertIn("Incident is not linked", result["scenarios"][0]["reasons"][0])

    def test_run_incident_backtest_rejects_cross_scope_linked_report(
        self,
    ) -> None:
        other_project = project_service_module.create_project(
            project_key="identity",
            display_name="Identity",
        )
        other_report = self._persist_replay_report(
            file_name="identity.tf",
            project_id=other_project.id,
        )
        with database_module.SessionLocal() as session:
            incident_records_repository_module.create_incident_record(
                session,
                project_id=self.project.id,
                title="Cross-scope incident",
                severity="high",
                source_file="cross-scope-incident.md",
                incident_date="2026-04-29",
                analysis_id=other_report["id"],
                content="Cross-scope report links should not replay.",
            )

        with mock.patch(
            "services.backtesting_service._run_incident_replay_analysis"
        ) as replay:
            result = backtesting_service_module.run_incident_backtest(
                project_id=self.project.id,
                now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            )

        replay.assert_not_called()
        self.assertTrue(result["passed"])
        self.assertEqual(result["summary"]["unsupported_count"], 1)
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["status"], "unsupported")
        self.assertIsNone(scenario["linked_report"])
        self.assertIn("unavailable", scenario["reasons"][0])

    def test_run_incident_backtest_rejects_cross_workspace_linked_report(
        self,
    ) -> None:
        workspace_report = self._persist_replay_report(
            file_name="workspace.tf",
            workspace_id=self.workspace.id,
        )
        with database_module.SessionLocal() as session:
            incident_records_repository_module.create_incident_record(
                session,
                project_id=self.project.id,
                workspace_id=None,
                title="Project incident linked to workspace report",
                severity="high",
                source_file="cross-workspace-incident.md",
                incident_date="2026-04-29",
                analysis_id=workspace_report["id"],
                content="Cross-workspace report links should not replay.",
            )

        with mock.patch(
            "services.backtesting_service._run_incident_replay_analysis"
        ) as replay:
            result = backtesting_service_module.run_incident_backtest(
                project_id=self.project.id,
                now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            )

        replay.assert_not_called()
        self.assertTrue(result["passed"])
        self.assertEqual(result["summary"]["unsupported_count"], 1)
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["status"], "unsupported")
        self.assertIsNone(scenario["linked_report"])
        self.assertIn("unavailable", scenario["reasons"][0])

    def test_run_incident_backtest_rejects_partial_replay_artifact_snapshots(
        self,
    ) -> None:
        report = self._persist_replay_report(
            file_name="partial-a.tf",
            extra_file_names=["partial-b.tf"],
        )
        report_dir = self.snapshot_dir / str(report["id"])
        manifest = json.loads(
            (report_dir / "manifest.json").read_text(encoding="utf-8")
        )
        (report_dir / manifest["partial-b.tf"]).unlink()
        incident_service_module.ingest_incident_document(
            "partial-incident.md",
            "# Partial incident\nDate: 2026-04-29\nSeverity: high\nReplay is incomplete.",
            analysis_id=report["id"],
        )

        with mock.patch(
            "services.backtesting_service._run_incident_replay_analysis"
        ) as replay:
            result = backtesting_service_module.run_incident_backtest(
                project_id=self.project.id,
                now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            )

        replay.assert_not_called()
        self.assertTrue(result["passed"])
        self.assertEqual(result["summary"]["unsupported_count"], 1)
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["status"], "unsupported")
        self.assertEqual(scenario["replay_artifacts"], ["partial-a.tf"])
        self.assertEqual(scenario["missing_replay_artifacts"], ["partial-b.tf"])

    def test_run_incident_backtest_reports_snapshot_load_error_per_scenario(
        self,
    ) -> None:
        report = self._persist_replay_report(file_name="corrupt.tf")
        incident_service_module.ingest_incident_document(
            "corrupt-incident.md",
            "# Corrupt incident\nDate: 2026-04-29\nSeverity: high\nSnapshot cannot load.",
            analysis_id=report["id"],
        )

        with mock.patch(
            "services.backtesting_service.load_report_artifact",
            side_effect=ValueError("corrupt artifact manifest"),
        ):
            result = backtesting_service_module.run_incident_backtest(
                project_id=self.project.id,
                now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            )

        self.assertFalse(result["passed"])
        self.assertEqual(result["summary"]["error_count"], 1)
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["status"], "error")
        self.assertIn("corrupt artifact manifest", scenario["reasons"])

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

    def test_record_finding_feedback_invalidates_cached_calibration_snapshot(
        self,
    ) -> None:
        warned_report = self._persist_report(
            top_risk="Warned deploy later marked noisy.",
            recommendation="caution",
            severity="medium",
            file_name="warned-feedback.tf",
            include_finding=True,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="success",
            deployed_at=self._recent_deployed_at(hours_ago=24),
        )
        first = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )

        feedback_service_module.record_finding_feedback(
            analysis_id=warned_report["id"],
            finding_id=warned_report["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Control owner confirmed the warning was noisy.",
        )
        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )

        self.assertEqual(first["calibration_metrics"]["false_positive_count"], 0)
        self.assertEqual(refreshed["calibration_metrics"]["false_positive_count"], 1)
        self.assertEqual(refreshed["calibration_metrics"]["false_positive_rate"], 1.0)

    def test_remove_analysis_report_invalidates_cached_calibration_snapshot(
        self,
    ) -> None:
        warned_report = self._persist_report(
            top_risk="Deleted report should leave calibration cache stale.",
            recommendation="caution",
            severity="medium",
            file_name="deleted-report-cache.tf",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_report["id"],
            outcome="failure",
            deployed_at=self._recent_deployed_at(hours_ago=24),
        )
        first = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )

        removed = report_service_module.remove_analysis_report(warned_report["id"])
        refreshed = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id
        )

        self.assertTrue(removed)
        self.assertEqual(first["failed_deploy_count"], 1)
        self.assertEqual(refreshed["failed_deploy_count"], 0)

    def test_deleted_report_feedback_does_not_pollute_calibration_metrics(
        self,
    ) -> None:
        noisy_report = self._persist_report(
            top_risk="Deleted feedback should not remain calibration input.",
            recommendation="caution",
            severity="medium",
            file_name="deleted-feedback-cache.tf",
            include_finding=True,
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=noisy_report["id"],
            finding_id=noisy_report["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Reviewer confirmed the warning was noisy.",
        )
        self._stamp_all_feedback_created_at(datetime(2026, 4, 29, 12, 0, tzinfo=UTC))
        before_delete = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        removed = report_service_module.remove_analysis_report(noisy_report["id"])
        after_delete = backtesting_service_module.fetch_calibration_dashboard_seed(
            project_id=self.project.id,
            now=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        )

        self.assertTrue(removed)
        self.assertEqual(
            before_delete["calibration_metrics"]["false_positive_count"], 1
        )
        self.assertEqual(after_delete["calibration_metrics"]["feedback_event_count"], 0)
        self.assertEqual(
            after_delete["calibration_metrics"]["feedback_history_event_count"],
            0,
        )
        self.assertEqual(after_delete["calibration_metrics"]["false_positive_count"], 0)

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
