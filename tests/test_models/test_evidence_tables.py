"""Tests for evidence-domain ORM tables."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.tables as tables_module
import services.project_service as project_service_module
from sqlalchemy.exc import IntegrityError


class EvidenceTableTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "evidence.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(project_service_module)
        database_module.init_db()
        self.default_project = project_service_module.ensure_default_project()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_init_db_creates_evidence_tables(self) -> None:
        sqlite_conn = sqlite3.connect(self.db_path)
        tables = {
            row[0]
            for row in sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        sqlite_conn.close()

        self.assertIn("analysis_reports", tables)
        self.assertIn("findings", tables)
        self.assertIn("evidence_items", tables)
        self.assertIn("risk_assessments", tables)
        self.assertIn("context_snapshots", tables)

    def test_init_db_enables_sqlite_foreign_key_enforcement(self) -> None:
        with database_module.engine.connect() as connection:
            enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()

        self.assertEqual(enabled, 1)

    def test_report_findings_and_evidence_relationships_round_trip(self) -> None:
        with database_module.SessionLocal() as session:
            report = tables_module.AnalysisReport(
                project_id=self.default_project.id,
                risk_score=55,
                severity="medium",
                recommendation="caution",
                top_risk="Broad ingress change",
                report_schema_version="v2",
                parse_summary="1 parsed, 0 failed, 0 skipped, 1 normalized changes",
                narrative_opening="CAUTION: review the ingress update.",
                narrative_explanation="Ingress exposure expanded for a shared service.",
                warnings_json='["topology missing"]',
                contributors_json="[]",
                analyzed_files_json='["plan.json"]',
                llm_provider="ollama",
                llm_model="ollama/llama3",
                llm_local_mode="true",
                assessment_source="heuristic-only",
                narrative_source="fallback",
                narrative_skills_json='["terraform"]',
                source_interface="api",
                trigger_type="session",
                trigger_id="sess-123",
                dashboard_display_duration_seconds=None,
            )
            session.add(report)
            session.flush()

            finding = tables_module.Finding(
                finding_id="finding-001",
                analysis_id=report.id,
                title="Security group exposure",
                description="Ingress allows 0.0.0.0/0 to reach a database subnet.",
                explanation="Ingress allows database access from the internet.",
                severity="high",
                category="networking/ingress",
                deterministic=True,
                confidence=0.95,
                uncertainty_note=None,
                guidance_json='["Restrict ingress before deployment."]',
                evidence_classification="deterministic",
                evidence_refs_json='["ev-001"]',
                skill_id=None,
            )
            session.add(finding)

            session.add(
                tables_module.EvidenceItem(
                    evidence_id="ev-001",
                    analysis_id=report.id,
                    finding_id=finding.finding_id,
                    source_type="artifact",
                    source_ref="terraform://plan.json#aws_security_group.main",
                    artifact="plan.json",
                    location="plan.json#aws_security_group.main",
                    resource="aws_security_group.main",
                    operation="modify",
                    project_id=self.default_project.id,
                    project_key=self.default_project.project_key,
                    source_kind="artifact",
                    determinism_level="deterministic",
                    redaction_status="none",
                    summary="Ingress widened to 0.0.0.0/0",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids_json='["change-1"]',
                )
            )
            session.add(
                tables_module.RiskAssessment(
                    analysis_id=report.id,
                    overall_severity="high",
                    recommendation="caution",
                    score=72,
                    confidence=0.9,
                    top_risk_contributors_json='["ev-001"]',
                    context_completeness_json='{"context_score": 0.8}',
                )
            )
            session.add(
                tables_module.ContextSnapshot(
                    analysis_id=report.id,
                    topology_version="2026-04-20",
                    incident_index_version="incidents-v1",
                    history_window="90d",
                    criticality_inputs_json='{"payments-api": "tier-1"}',
                    owner_mapping_version="owners-v2",
                    skills_active_json='[{"skill_id":"terraform","version":"1.0.0"}]',
                )
            )
            session.commit()

        with database_module.SessionLocal() as session:
            stored = session.get(tables_module.AnalysisReport, 1)

            self.assertIsNotNone(stored)
            self.assertEqual(len(stored.findings), 1)
            self.assertEqual(stored.findings[0].finding_id, "finding-001")
            self.assertEqual(
                stored.findings[0].explanation,
                "Ingress allows database access from the internet.",
            )
            self.assertEqual(
                stored.findings[0].guidance_json,
                '["Restrict ingress before deployment."]',
            )
            self.assertEqual(
                stored.findings[0].evidence_classification,
                "deterministic",
            )
            self.assertEqual(len(stored.findings[0].evidence_items), 1)
            self.assertEqual(
                stored.findings[0].evidence_items[0].source_ref,
                "terraform://plan.json#aws_security_group.main",
            )
            self.assertEqual(stored.findings[0].evidence_items[0].artifact, "plan.json")
            self.assertEqual(stored.findings[0].evidence_items[0].operation, "modify")
            self.assertEqual(
                stored.findings[0].evidence_items[0].project_key, "unassigned"
            )
            self.assertEqual(
                stored.findings[0].evidence_items[0].determinism_level,
                "deterministic",
            )
            self.assertEqual(stored.risk_assessment.score, 72)
            self.assertEqual(stored.context_snapshot.history_window, "90d")

    def test_evidence_item_requires_matching_report_and_finding(self) -> None:
        with database_module.SessionLocal() as session:
            session.add(
                tables_module.AnalysisReport(
                    project_id=self.default_project.id,
                    risk_score=10,
                    severity="low",
                    recommendation="go",
                    top_risk="Low risk",
                    report_schema_version="v2",
                    parse_summary="0 parsed, 0 failed, 0 skipped, 0 normalized changes",
                    narrative_opening="GO: low risk",
                    narrative_explanation="Low risk",
                    warnings_json="[]",
                    contributors_json="[]",
                    analyzed_files_json="[]",
                    llm_provider="ollama",
                    llm_model="ollama/llama3",
                    llm_local_mode="true",
                    assessment_source="heuristic-only",
                    narrative_source="fallback",
                    narrative_skills_json="[]",
                    source_interface="api",
                    trigger_type="session",
                    trigger_id="sess-1",
                    dashboard_display_duration_seconds=None,
                )
            )
            session.add(
                tables_module.AnalysisReport(
                    project_id=self.default_project.id,
                    risk_score=20,
                    severity="medium",
                    recommendation="caution",
                    top_risk="Medium risk",
                    report_schema_version="v2",
                    parse_summary="0 parsed, 0 failed, 0 skipped, 0 normalized changes",
                    narrative_opening="CAUTION: medium risk",
                    narrative_explanation="Medium risk",
                    warnings_json="[]",
                    contributors_json="[]",
                    analyzed_files_json="[]",
                    llm_provider="ollama",
                    llm_model="ollama/llama3",
                    llm_local_mode="true",
                    assessment_source="heuristic-only",
                    narrative_source="fallback",
                    narrative_skills_json="[]",
                    source_interface="api",
                    trigger_type="session",
                    trigger_id="sess-2",
                    dashboard_display_duration_seconds=None,
                )
            )
            session.flush()
            session.add(
                tables_module.Finding(
                    finding_id="finding-001",
                    analysis_id=1,
                    title="Security group exposure",
                    description="Ingress allows 0.0.0.0/0 to reach a database subnet.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.95,
                    uncertainty_note=None,
                    evidence_refs_json='["ev-001"]',
                    skill_id=None,
                )
            )
            session.commit()

        with self.assertRaises(IntegrityError):
            with database_module.SessionLocal() as session:
                session.add(
                    tables_module.EvidenceItem(
                        evidence_id="ev-002",
                        analysis_id=2,
                        finding_id="finding-001",
                        source_type="artifact",
                        source_ref="terraform://plan.json#aws_security_group.main",
                        summary="Ingress widened to 0.0.0.0/0",
                        severity_hint="high",
                        deterministic=True,
                        confidence=1.0,
                        related_change_ids_json='["change-2"]',
                    )
                )
                session.commit()

    def test_finding_rejects_invalid_evidence_classification(self) -> None:
        with database_module.SessionLocal() as session:
            report = tables_module.AnalysisReport(
                project_id=self.default_project.id,
                risk_score=42,
                severity="medium",
                recommendation="caution",
                top_risk="Medium risk",
                report_schema_version="v2",
                parse_summary="0 parsed, 0 failed, 0 skipped, 0 normalized changes",
                narrative_opening="CAUTION: medium risk",
                narrative_explanation="Medium risk",
                warnings_json="[]",
                contributors_json="[]",
                analyzed_files_json="[]",
                submission_manifest_json="{}",
                submission_manifest_fallback_json="[]",
                llm_provider="ollama",
                llm_model="ollama/llama3",
                llm_local_mode="true",
                assessment_source="heuristic-only",
                narrative_source="fallback",
                narrative_skills_json="[]",
                source_interface="api",
                trigger_type="session",
                trigger_id="sess-3",
                dashboard_display_duration_seconds=None,
            )
            session.add(report)
            session.flush()
            session.add(
                tables_module.Finding(
                    finding_id="finding-invalid-classification",
                    analysis_id=report.id,
                    title="Security group exposure",
                    description="Ingress allows 0.0.0.0/0 to reach a database subnet.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.95,
                    uncertainty_note=None,
                    evidence_classification="unsupported",
                    evidence_refs_json="[]",
                    skill_id=None,
                )
            )

            with self.assertRaises(IntegrityError):
                session.commit()


if __name__ == "__main__":
    unittest.main()
