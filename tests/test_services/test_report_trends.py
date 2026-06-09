"""Tests for report trend aggregation."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from importlib import reload
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.dialects import postgresql

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.deployment_outcome_service as deployment_outcome_service_module
import services.feedback_service as feedback_service_module
import services.project_service as project_service_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import ContextCompleteness, EvidenceItem, Finding
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class ReportTrendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(feedback_service_module)
        reload(deployment_outcome_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def _persist(
        self,
        *,
        severity: str,
        recommendation: str,
        tool: str,
        source_interface: str = "ui",
        project_id: int | None = None,
        workspace_id: int | None = None,
        partial_context: bool = False,
        context_score: float = 1.0,
    ) -> dict:
        evidence_id = f"ev-{tool}-{severity}"
        finding_id = f"finding-{tool}-{severity}"
        resource_id = f"{tool}/resource"
        severe_report = severity in {"high", "critical"}
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="input.json",
                    tool=tool,
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="input.json",
                            tool=tool,
                            resource_id=resource_id,
                            action="modify",
                            summary=f"{tool} change",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity=severity,
            recommendation=recommendation,
            top_risk=f"{tool} change",
            top_risk_contributors=[evidence_id] if severe_report else [],
            contributors=[
                RiskContributor(
                    evidence_id=evidence_id if severe_report else None,
                    source_file="input.json",
                    tool=tool,
                    resource_id=resource_id,
                    action="modify",
                    contribution=12,
                    summary=f"{tool} change",
                )
            ],
            interaction_risks=[],
            partial_context=partial_context,
            warnings=[],
            context_completeness=ContextCompleteness(
                topology_freshness_days=0,
                topology_last_imported_at="2026-06-01T00:00:00Z",
                incident_index_size=4,
                parser_success_rate=1.0,
                parser_success_by_tool={tool: 1.0},
                context_score=context_score,
                partial_context=partial_context,
                context_todos=["Refresh topology context."] if partial_context else [],
            ),
        )
        narrative = NarrativeResult(
            opening_sentence=f"{recommendation.upper()}: {tool} change",
            explanation=f"{tool} change explanation",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        return report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            audit_context={"source_interface": source_interface},
            project_id=project_id,
            workspace_id=workspace_id,
            findings=[
                Finding(
                    finding_id=finding_id,
                    analysis_id=0,
                    title=f"{severity.upper()}: {tool} change",
                    description=f"{tool} change",
                    severity=severity,
                    category="generic infrastructure",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=[evidence_id],
                    skill_id=None,
                )
            ]
            if severe_report
            else None,
            evidence_items=[
                EvidenceItem(
                    evidence_id=evidence_id,
                    analysis_id=0,
                    finding_id=finding_id,
                    source_type="artifact",
                    source_ref=f"{tool}://input.json#{resource_id}?action=modify",
                    summary=f"{tool} change",
                    severity_hint=severity,
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ]
            if severe_report
            else None,
        )

    def _set_report_created_at(self, report_id: int, created_at: datetime) -> None:
        with database_module.SessionLocal() as session:
            report = session.get(tables_module.AnalysisReport, report_id)
            self.assertIsNotNone(report)
            report.created_at = created_at
            session.commit()

    def _set_report_schema_version(self, report_id: int, version: str) -> None:
        with database_module.SessionLocal() as session:
            report = session.get(tables_module.AnalysisReport, report_id)
            self.assertIsNotNone(report)
            report.report_schema_version = version
            session.commit()

    def _set_report_contributors_json(self, report_id: int, payload: str) -> None:
        with database_module.SessionLocal() as session:
            report = session.get(tables_module.AnalysisReport, report_id)
            self.assertIsNotNone(report)
            report.contributors_json = payload
            session.commit()

    def _set_feedback_created_at(self, analysis_id: int, created_at: datetime) -> None:
        with database_module.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE feedback_events SET created_at = :created_at "
                    "WHERE analysis_id = :analysis_id"
                ),
                {"created_at": created_at, "analysis_id": analysis_id},
            )
            session.commit()

    def _set_outcome_scope(
        self,
        analysis_id: int,
        *,
        project_id: int,
        workspace_id: int | None = None,
    ) -> None:
        with database_module.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE deployment_outcomes "
                    "SET project_id = :project_id, workspace_id = :workspace_id "
                    "WHERE analysis_id = :analysis_id"
                ),
                {
                    "analysis_id": analysis_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                },
            )
            session.commit()

    def _set_feedback_scope(
        self,
        analysis_id: int,
        *,
        project_id: int,
        workspace_id: int | None = None,
    ) -> None:
        with database_module.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE feedback_events "
                    "SET project_id = :project_id, workspace_id = :workspace_id "
                    "WHERE analysis_id = :analysis_id"
                ),
                {
                    "analysis_id": analysis_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                },
            )
            session.commit()

    def _set_context_completeness_json(self, report_id: int, payload: str) -> None:
        with database_module.SessionLocal() as session:
            session.execute(
                text(
                    "UPDATE risk_assessments SET context_completeness_json = :payload "
                    "WHERE analysis_id = :report_id"
                ),
                {"payload": payload, "report_id": report_id},
            )
            session.commit()

    def test_fetch_risk_trends_summarizes_severity_and_tools(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        self._persist(
            severity="high",
            recommendation="caution",
            tool="terraform",
            project_id=project.id,
        )
        self._persist(
            severity="critical",
            recommendation="no-go",
            tool="kubernetes",
            project_id=project.id,
        )
        trends = report_service_module.fetch_risk_trends(project_id=project.id)
        self.assertEqual(trends["total_reports"], 2)
        self.assertEqual(trends["severity_counts"]["high"], 1)
        self.assertEqual(trends["severity_counts"]["critical"], 1)
        self.assertEqual(trends["tool_counts"]["terraform"], 1)
        self.assertEqual(len(trends["audit_rows"]), 2)
        self.assertEqual(trends["audit_rows"][0]["audit"]["llm_provider"], "ollama")

    def test_fetch_risk_trends_requires_project_scope(self) -> None:
        with self.assertRaises(report_service_module.ReportTrendError) as ctx:
            report_service_module.fetch_risk_trends()

        self.assertEqual(ctx.exception.code, "missing_project_scope")

    def test_fetch_risk_trends_filters_scope_window_toolchain_and_severity(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        prod = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
        staging = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="staging",
            display_name="Staging",
        )
        other_project = project_service_module.create_project(
            project_key="search",
            display_name="Search",
        )
        now = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        included = self._persist(
            severity="high",
            recommendation="no-go",
            tool="terraform",
            project_id=project.id,
            workspace_id=prod.id,
            partial_context=True,
            context_score=0.54,
        )
        wrong_workspace = self._persist(
            severity="high",
            recommendation="no-go",
            tool="terraform",
            project_id=project.id,
            workspace_id=staging.id,
        )
        wrong_tool = self._persist(
            severity="high",
            recommendation="no-go",
            tool="kubernetes",
            project_id=project.id,
            workspace_id=prod.id,
        )
        wrong_severity = self._persist(
            severity="medium",
            recommendation="caution",
            tool="terraform",
            project_id=project.id,
            workspace_id=prod.id,
        )
        out_of_window = self._persist(
            severity="critical",
            recommendation="no-go",
            tool="terraform",
            project_id=project.id,
            workspace_id=prod.id,
        )
        out_of_scope = self._persist(
            severity="critical",
            recommendation="no-go",
            tool="terraform",
            project_id=other_project.id,
        )
        self._set_report_created_at(included["id"], now - timedelta(days=1))
        self._set_report_created_at(wrong_workspace["id"], now - timedelta(days=1))
        self._set_report_created_at(wrong_tool["id"], now - timedelta(days=1))
        self._set_report_created_at(wrong_severity["id"], now - timedelta(days=1))
        self._set_report_created_at(out_of_window["id"], now - timedelta(days=45))
        self._set_report_created_at(out_of_scope["id"], now - timedelta(days=1))

        trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            workspace_key="prod",
            created_from=now - timedelta(days=7),
            created_to=now,
            toolchain="terraform",
            severity="high",
        )

        self.assertEqual(trends["total_reports"], 1)
        self.assertEqual(trends["window"]["start"], "2026-06-01T12:00:00+00:00")
        self.assertEqual(trends["window"]["end"], "2026-06-08T12:00:00+00:00")
        self.assertEqual(trends["filters"]["project_id"], project.id)
        self.assertEqual(trends["filters"]["workspace_key"], "prod")
        self.assertEqual(trends["filters"]["toolchain"], "terraform")
        self.assertEqual(trends["filters"]["severity"], "high")
        self.assertEqual(trends["severity_counts"], {"high": 1})
        self.assertEqual(trends["high_critical_frequency"]["count"], 1)
        self.assertEqual(trends["high_critical_frequency"]["rate"], 1.0)
        self.assertEqual(trends["tool_counts"], {"terraform": 1})
        self.assertEqual(trends["context_completeness"]["partial_context_count"], 1)
        self.assertEqual(trends["context_completeness"]["average_context_score"], 0.54)
        self.assertEqual([row["id"] for row in trends["audit_rows"]], [included["id"]])

    def test_fetch_risk_trends_counts_analyzed_file_tool_without_contributors(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments-analyzed-tools",
            display_name="Payments Analyzed Tools",
        )
        report = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        self._set_report_contributors_json(report["id"], "[]")

        trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            toolchain="terraform",
        )

        self.assertEqual(trends["total_reports"], 1)
        self.assertEqual(trends["tool_counts"], {"terraform": 1})

    def test_fetch_risk_trends_includes_feedback_outcome_and_sparse_limitations(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        warned_failure = self._persist(
            severity="high",
            recommendation="no-go",
            tool="terraform",
            project_id=project.id,
        )
        clean_failure = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        false_positive = self._persist(
            severity="critical",
            recommendation="no-go",
            tool="kubernetes",
            project_id=project.id,
        )
        out_of_scope = self._persist(
            severity="high",
            recommendation="no-go",
            tool="terraform",
        )

        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned_failure["id"],
            outcome="rolled_back",
            deployed_at="2026-06-07T08:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=clean_failure["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=out_of_scope["id"],
            outcome="failure",
            deployed_at="2026-06-07T10:00:00Z",
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=false_positive["id"],
            finding_id=false_positive["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Known compensating control.",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=clean_failure["id"],
            note="Low-risk verdict missed the failed deploy signal.",
        )

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["total_reports"], 3)
        self.assertEqual(trends["outcome_links"]["linked_outcome_count"], 2)
        self.assertEqual(trends["outcome_links"]["failed_outcome_count"], 2)
        self.assertEqual(trends["outcome_links"]["warned_failed_outcome_count"], 1)
        self.assertEqual(
            trends["false_positive_signals"],
            {"count": 1, "event_count": 1, "rate": 1 / 3},
        )
        self.assertEqual(trends["false_reassurance_signals"]["count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["event_count"], 2)
        self.assertEqual(trends["false_reassurance_signals"]["deployment_count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["feedback_count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["rate"], 1 / 3)
        limitation_codes = {limitation["code"] for limitation in trends["limitations"]}
        self.assertIn("sparse_reports", limitation_codes)
        self.assertIn("sparse_feedback", limitation_codes)
        self.assertNotIn(out_of_scope["id"], trends["outcome_links"]["analysis_ids"])

    def test_fetch_risk_trends_surfaces_previous_window_limitations(self) -> None:
        project = project_service_module.create_project(
            project_key="payments-previous-limitations",
            display_name="Payments Previous Limitations",
        )
        for index in range(5):
            report = self._persist(
                severity="low",
                recommendation="go",
                tool="terraform",
                project_id=project.id,
            )
            self._set_report_created_at(
                report["id"],
                datetime(2026, 6, 2 + index, tzinfo=UTC),
            )

        trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 6, 8, tzinfo=UTC),
        )

        limitation_codes = {limitation["code"] for limitation in trends["limitations"]}
        self.assertIn("previous_window_no_reports", limitation_codes)
        previous_window, current_window = trends["trend_windows"]
        self.assertEqual(previous_window["label"], "previous")
        self.assertIn(
            "no_reports",
            {limitation["code"] for limitation in previous_window["limitations"]},
        )
        self.assertEqual(current_window["label"], "current")
        self.assertNotIn(
            "previous_window_no_reports",
            {limitation["code"] for limitation in current_window["limitations"]},
        )

    def test_activity_window_ignores_out_of_scope_event_rows(self) -> None:
        project = project_service_module.create_project(
            project_key="payments-scope",
            display_name="Payments Scope",
        )
        other_project = project_service_module.create_project(
            project_key="other-scope",
            display_name="Other Scope",
        )
        outcome_report = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        feedback_report = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        self._set_report_created_at(
            outcome_report["id"],
            datetime(2026, 5, 1, tzinfo=UTC),
        )
        self._set_report_created_at(
            feedback_report["id"],
            datetime(2026, 5, 2, tzinfo=UTC),
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=outcome_report["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        self._set_outcome_scope(
            outcome_report["id"],
            project_id=other_project.id,
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=feedback_report["id"],
            note="Out-of-scope feedback must not qualify the report.",
        )
        self._set_feedback_created_at(
            feedback_report["id"],
            datetime(2026, 6, 7, tzinfo=UTC),
        )
        self._set_feedback_scope(
            feedback_report["id"],
            project_id=other_project.id,
        )

        page = report_service_module.fetch_filtered_analysis_history_page(
            project_id=project.id,
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 6, 8, tzinfo=UTC),
            skip_unreadable_schema=True,
        )
        trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 6, 8, tzinfo=UTC),
        )

        self.assertEqual(page["total_count"], 0)
        self.assertEqual(page["items"], [])
        self.assertEqual(trends["total_reports"], 0)
        self.assertEqual(trends["outcome_links"]["linked_outcome_count"], 0)
        self.assertEqual(trends["false_reassurance_signals"]["count"], 0)

    def test_project_wide_trends_ignore_wrong_workspace_event_rows(self) -> None:
        project = project_service_module.create_project(
            project_key="payments-workspace-events",
            display_name="Payments Workspace Events",
        )
        prod = project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="prod",
            display_name="Production",
            environment="prod",
        )
        staging = project_service_module.create_workspace(
            project_key=project.project_key,
            workspace_key="staging",
            display_name="Staging",
            environment="staging",
        )
        report = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
            workspace_id=prod.id,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=report["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        self._set_outcome_scope(
            report["id"],
            project_id=project.id,
            workspace_id=staging.id,
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=report["id"],
            note="Wrong-workspace event must not count in project-wide trends.",
        )
        self._set_feedback_scope(
            report["id"],
            project_id=project.id,
            workspace_id=staging.id,
        )

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["total_reports"], 1)
        self.assertEqual(trends["outcome_links"]["linked_outcome_count"], 0)
        self.assertEqual(trends["outcome_counts"], {})
        self.assertEqual(trends["false_reassurance_signals"]["count"], 0)
        self.assertEqual(trends["false_reassurance_signals"]["event_count"], 0)

    def test_fetch_risk_trends_keyset_batches_activity_window_scope(self) -> None:
        project = project_service_module.create_project(
            project_key="payments-batched-trends",
            display_name="Payments Batched Trends",
        )
        report_ids = []
        for index in range(5):
            report = self._persist(
                severity="low",
                recommendation="go",
                tool="terraform" if index % 2 else "kubernetes",
                project_id=project.id,
            )
            report_ids.append(report["id"])
            self._set_report_created_at(
                report["id"],
                datetime(2026, 6, 2 + index, tzinfo=UTC),
            )
        original_list_analysis_reports = report_service_module.list_analysis_reports
        report_query_calls: list[dict] = []
        created_from = datetime(2026, 6, 1, tzinfo=UTC)
        created_to = datetime(2026, 6, 8, tzinfo=UTC)

        def recording_list_analysis_reports(*args, **kwargs):
            report_query_calls.append(dict(kwargs))
            return original_list_analysis_reports(*args, **kwargs)

        with (
            patch.object(report_service_module, "_TREND_REPORT_BATCH_SIZE", 2),
            patch.object(
                report_service_module,
                "list_analysis_reports",
                side_effect=recording_list_analysis_reports,
            ),
        ):
            trends = report_service_module.fetch_risk_trends(
                project_id=project.id,
                created_from=created_from,
                created_to=created_to,
            )

        self.assertEqual(trends["total_reports"], 5)
        current_window_calls = [
            call for call in report_query_calls if call["activity_from"] == created_from
        ]
        self.assertGreaterEqual(len(current_window_calls), 3)
        self.assertEqual(
            len(report_ids),
            len({report_id for report_id in report_ids}),
        )
        self.assertTrue(
            all(call.get("offset") is None for call in current_window_calls)
        )
        self.assertTrue(
            all(call["order_by_activity"] is False for call in current_window_calls)
        )
        self.assertIsNone(current_window_calls[0]["id_before"])
        self.assertTrue(
            all(call["id_before"] is not None for call in current_window_calls[1:])
        )
        self.assertTrue(all(call["limit"] == 2 for call in current_window_calls))

    def test_fetch_risk_trends_aggregates_signals_beyond_audit_sample(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        older_signal = self._persist(
            severity="high",
            recommendation="no-go",
            tool="terraform",
            project_id=project.id,
            partial_context=True,
            context_score=0.25,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=older_signal["id"],
            outcome="failure",
            deployed_at="2026-06-07T08:00:00Z",
        )
        feedback_service_module.record_finding_feedback(
            analysis_id=older_signal["id"],
            finding_id=older_signal["findings"][0]["finding_id"],
            useful=False,
            false_positive_flag=True,
            false_positive_reason="Known exception.",
        )
        for index in range(105):
            self._persist(
                severity="low",
                recommendation="go",
                tool="kubernetes" if index % 2 else "terraform",
                project_id=project.id,
            )

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["total_reports"], 106)
        self.assertEqual(trends["outcome_links"]["linked_outcome_count"], 1)
        self.assertEqual(trends["outcome_links"]["failed_outcome_count"], 1)
        self.assertEqual(trends["false_positive_signals"]["count"], 1)
        self.assertEqual(trends["context_completeness"]["sample_size"], 106)
        self.assertEqual(trends["context_completeness"]["partial_context_count"], 1)
        self.assertEqual(len(trends["audit_rows"]), 100)
        self.assertNotIn(
            older_signal["id"],
            {row["id"] for row in trends["audit_rows"]},
        )

    def test_fetch_risk_trends_filters_and_counts_by_outcome(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        success = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        failure = self._persist(
            severity="medium",
            recommendation="caution",
            tool="terraform",
            project_id=project.id,
        )
        rolled_back = self._persist(
            severity="critical",
            recommendation="no-go",
            tool="kubernetes",
            project_id=project.id,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=success["id"],
            outcome="success",
            deployed_at="2026-06-07T08:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=failure["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=rolled_back["id"],
            outcome="rollback",
            deployed_at="2026-06-07T10:00:00Z",
        )

        failure_trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            outcome="failure",
        )
        rollback_trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            outcome="rollback",
        )

        self.assertEqual(failure_trends["total_reports"], 1)
        self.assertEqual(failure_trends["filters"]["outcome"], "failure")
        self.assertEqual(failure_trends["severity_counts"], {"medium": 1})
        self.assertEqual(failure_trends["outcome_counts"], {"failure": 1})
        self.assertEqual(rollback_trends["total_reports"], 1)
        self.assertEqual(rollback_trends["filters"]["outcome"], "rolled_back")
        self.assertEqual(rollback_trends["outcome_counts"], {"rolled_back": 1})

    def test_fetch_risk_trends_rates_use_unique_affected_reports(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        false_positive = self._persist(
            severity="critical",
            recommendation="no-go",
            tool="terraform",
            project_id=project.id,
        )
        false_reassurance = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        for _ in range(2):
            feedback_service_module.record_finding_feedback(
                analysis_id=false_positive["id"],
                finding_id=false_positive["findings"][0]["finding_id"],
                useful=False,
                false_positive_flag=True,
                false_positive_reason="Known exception.",
            )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=false_reassurance["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=false_reassurance["id"],
            note="Low-risk verdict missed failed deploy.",
        )

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["false_positive_signals"]["count"], 1)
        self.assertEqual(trends["false_positive_signals"]["event_count"], 2)
        self.assertEqual(trends["false_positive_signals"]["rate"], 0.5)
        self.assertEqual(trends["false_reassurance_signals"]["count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["event_count"], 2)
        self.assertEqual(trends["false_reassurance_signals"]["deployment_count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["feedback_count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["rate"], 0.5)

    def test_fetch_risk_trends_rejects_reversed_time_window(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        with self.assertRaises(report_service_module.ReportTrendError) as ctx:
            report_service_module.fetch_risk_trends(
                project_id=project.id,
                created_from=datetime(2026, 6, 8, tzinfo=UTC),
                created_to=datetime(2026, 6, 1, tzinfo=UTC),
            )

        self.assertEqual(ctx.exception.code, "invalid_time_window")

    def test_fetch_risk_trends_flags_missing_context_completeness(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        valid = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        missing = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        self._set_context_completeness_json(missing["id"], "{}")

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["context_completeness"]["sample_size"], 1)
        self.assertEqual(trends["context_completeness"]["missing_count"], 1)
        self.assertEqual(
            trends["context_completeness"]["average_context_score"],
            1.0,
        )
        limitation_codes = {limitation["code"] for limitation in trends["limitations"]}
        self.assertIn("missing_context_completeness", limitation_codes)
        self.assertIn(valid["id"], [row["id"] for row in trends["audit_rows"]])

    def test_fetch_risk_trends_compares_current_and_previous_windows(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        current = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        previous = self._persist(
            severity="critical",
            recommendation="no-go",
            tool="kubernetes",
            project_id=project.id,
        )
        boundary = self._persist(
            severity="high",
            recommendation="no-go",
            tool="cloudformation",
            project_id=project.id,
        )
        boundary_outcome = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        self._set_report_created_at(
            current["id"],
            datetime(2026, 6, 5, tzinfo=UTC),
        )
        self._set_report_created_at(
            previous["id"],
            datetime(2026, 5, 28, tzinfo=UTC),
        )
        self._set_report_created_at(
            boundary["id"],
            datetime(2026, 6, 1, tzinfo=UTC),
        )
        self._set_report_created_at(
            boundary_outcome["id"],
            datetime(2026, 5, 1, tzinfo=UTC),
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=boundary_outcome["id"],
            outcome="failure",
            deployed_at="2026-06-01T00:00:00Z",
        )

        trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 6, 8, tzinfo=UTC),
        )

        self.assertEqual(
            [window["label"] for window in trends["trend_windows"]],
            ["previous", "current"],
        )
        self.assertEqual(trends["trend_windows"][0]["total_reports"], 1)
        self.assertEqual(trends["trend_windows"][1]["total_reports"], 3)
        self.assertEqual(
            trends["trend_comparison"]["severity_count_deltas"]["high"],
            1,
        )
        self.assertEqual(
            trends["trend_comparison"]["tool_count_deltas"]["terraform"],
            2,
        )
        self.assertEqual(
            trends["trend_comparison"]["tool_count_deltas"]["kubernetes"],
            -1,
        )
        self.assertEqual(
            trends["trend_comparison"]["high_critical_count_delta"],
            0,
        )

    def test_fetch_risk_trends_filters_outcome_and_feedback_by_event_window(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        old_report_new_failure = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        new_report_old_failure = self._persist(
            severity="low",
            recommendation="go",
            tool="kubernetes",
            project_id=project.id,
        )
        self._set_report_created_at(
            old_report_new_failure["id"],
            datetime(2026, 5, 1, tzinfo=UTC),
        )
        self._set_report_created_at(
            new_report_old_failure["id"],
            datetime(2026, 6, 5, tzinfo=UTC),
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=old_report_new_failure["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=new_report_old_failure["id"],
            outcome="failure",
            deployed_at="2026-05-20T09:00:00Z",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=old_report_new_failure["id"],
            note="Current-window reviewer miss.",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=new_report_old_failure["id"],
            note="Older reviewer miss.",
        )
        self._set_feedback_created_at(
            old_report_new_failure["id"],
            datetime(2026, 6, 7, tzinfo=UTC),
        )
        self._set_feedback_created_at(
            new_report_old_failure["id"],
            datetime(2026, 5, 20, tzinfo=UTC),
        )

        trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 6, 8, tzinfo=UTC),
        )
        outcome_filtered_trends = report_service_module.fetch_risk_trends(
            project_id=project.id,
            outcome="failure",
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 6, 8, tzinfo=UTC),
        )

        self.assertEqual(trends["total_reports"], 2)
        self.assertEqual(trends["outcome_links"]["linked_outcome_count"], 1)
        self.assertEqual(
            trends["outcome_links"]["analysis_ids"],
            [old_report_new_failure["id"]],
        )
        self.assertEqual(trends["false_reassurance_signals"]["deployment_count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["feedback_count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["event_count"], 2)
        self.assertEqual(outcome_filtered_trends["total_reports"], 2)
        self.assertEqual(
            outcome_filtered_trends["outcome_links"]["analysis_ids"],
            [old_report_new_failure["id"]],
        )
        self.assertEqual(
            outcome_filtered_trends["tool_counts"],
            {"terraform": 1, "kubernetes": 1},
        )

    def test_fetch_risk_trends_uses_warning_semantics_for_false_reassurance(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        warned = self._persist(
            severity="medium",
            recommendation="caution",
            tool="terraform",
            project_id=project.id,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=warned["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        feedback_service_module.record_false_negative_feedback(
            analysis_id=warned["id"],
            note="Reviewer added missed-finding context to a report that warned.",
        )

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["outcome_links"]["warned_failed_outcome_count"], 1)
        self.assertEqual(trends["false_reassurance_signals"]["count"], 0)
        self.assertEqual(trends["false_reassurance_signals"]["event_count"], 0)

    def test_fetch_risk_trends_excludes_unreadable_report_schemas(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        readable = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        unreadable = self._persist(
            severity="critical",
            recommendation="no-go",
            tool="kubernetes",
            project_id=project.id,
        )
        self._set_report_schema_version(unreadable["id"], "v999")

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["total_reports"], 1)
        self.assertEqual([row["id"] for row in trends["audit_rows"]], [readable["id"]])

    def test_fetch_risk_trends_chunks_large_scoped_signal_queries(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        first = None
        for _ in range(205):
            report = self._persist(
                severity="low",
                recommendation="go",
                tool="terraform",
                project_id=project.id,
            )
            if first is None:
                first = report
        self.assertIsNotNone(first)
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=first["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )

        trends = report_service_module.fetch_risk_trends(project_id=project.id)

        self.assertEqual(trends["total_reports"], 205)
        self.assertEqual(trends["outcome_links"]["linked_outcome_count"], 1)
        self.assertEqual(len(trends["audit_rows"]), 100)

    def test_filtered_history_page_filters_by_outcome(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        success = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        failure = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=success["id"],
            outcome="success",
            deployed_at="2026-06-07T08:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=failure["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )

        page = report_service_module.fetch_filtered_analysis_history_page(
            project_id=project.id,
            outcome="failure",
            skip_unreadable_schema=True,
        )

        self.assertEqual(page["total_count"], 1)
        self.assertEqual([item["id"] for item in page["items"]], [failure["id"]])

    def test_activity_window_history_orders_by_latest_activity_time(self) -> None:
        project = project_service_module.create_project(
            project_key="payments-activity-order",
            display_name="Payments Activity Order",
        )
        old_report_recent_outcome = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        newer_report_older_activity = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        self._set_report_created_at(
            old_report_recent_outcome["id"],
            datetime(2026, 5, 1, tzinfo=UTC),
        )
        self._set_report_created_at(
            newer_report_older_activity["id"],
            datetime(2026, 6, 7, tzinfo=UTC),
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=old_report_recent_outcome["id"],
            outcome="failure",
            deployed_at="2026-06-08T12:00:00Z",
        )

        page = report_service_module.fetch_filtered_analysis_history_page(
            project_id=project.id,
            created_from=datetime(2026, 6, 1, tzinfo=UTC),
            created_to=datetime(2026, 6, 9, tzinfo=UTC),
            page_size=1,
            skip_unreadable_schema=True,
        )

        self.assertEqual(page["total_count"], 2)
        self.assertEqual(
            [item["id"] for item in page["items"]],
            [old_report_recent_outcome["id"]],
        )

    def test_activity_order_expression_compiles_for_postgresql(self) -> None:
        expression = analysis_reports_repository_module._activity_order_expression(
            activity_from=datetime(2026, 6, 1, tzinfo=UTC),
            activity_to=datetime(2026, 6, 9, tzinfo=UTC),
        )

        self.assertIsNotNone(expression)
        compiled = str(expression.compile(dialect=postgresql.dialect()))
        self.assertIn("CASE WHEN", compiled.upper())
        self.assertNotIn("max(coalesce", compiled.lower())

    def test_outcome_filtered_history_preserves_unfiltered_previous_scan_diff(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments-diff",
            display_name="Payments Diff",
        )
        previous = self._persist(
            severity="low",
            recommendation="go",
            tool="terraform",
            project_id=project.id,
        )
        current = self._persist(
            severity="high",
            recommendation="no-go",
            tool="terraform",
            project_id=project.id,
        )
        self._set_report_created_at(
            previous["id"],
            datetime(2026, 6, 1, tzinfo=UTC),
        )
        self._set_report_created_at(
            current["id"],
            datetime(2026, 6, 2, tzinfo=UTC),
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=current["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )

        page = report_service_module.fetch_filtered_analysis_history_page(
            project_id=project.id,
            outcome="failure",
            skip_unreadable_schema=True,
        )

        self.assertEqual(page["total_count"], 1)
        self.assertEqual([item["id"] for item in page["items"]], [current["id"]])
        self.assertEqual(
            page["items"][0]["previous_scan_diff"]["previous_report_id"],
            previous["id"],
        )

    def test_filtered_history_page_handles_large_outcome_filtered_sets(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments-large",
            display_name="Payments Large",
        )
        for index in range(205):
            report = self._persist(
                severity="low",
                recommendation="go",
                tool="terraform",
                project_id=project.id,
            )
            deployment_outcome_service_module.record_deployment_outcome(
                analysis_id=report["id"],
                outcome="failure",
                deployed_at=f"2026-06-07T09:{index % 60:02d}:00Z",
            )

        page = report_service_module.fetch_filtered_analysis_history_page(
            project_id=project.id,
            outcome="failure",
            page_size=100,
            skip_unreadable_schema=True,
        )

        self.assertEqual(page["total_count"], 205)
        self.assertEqual(len(page["items"]), 100)

    def test_fetch_dashboard_stats_counts_scanned_files_and_severity(self) -> None:
        self._persist(severity="low", recommendation="go", tool="terraform")
        self._persist(
            severity="critical", recommendation="no-go", tool="cloudformation"
        )

        stats = report_service_module.fetch_dashboard_stats()

        self.assertEqual(stats["total_files_scanned"], 2)
        self.assertEqual(stats["severity_counts"]["low"], 1)
        self.assertEqual(stats["severity_counts"]["critical"], 1)
        self.assertEqual(stats["severity_counts"]["medium"], 0)
