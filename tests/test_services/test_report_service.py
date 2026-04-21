"""Tests for report persistence and retrieval."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from importlib import reload
from pathlib import Path

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.report_service as report_service_module
import services.settings_service as settings_service_module
from analysis.blast_radius import BlastRadiusResult, ImpactNode
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import EvidenceItem, Finding
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class ReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(settings_service_module)
        reload(report_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        self.tempdir.cleanup()

    def test_persist_analysis_report_stores_and_returns_metadata(self) -> None:
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
            top_risk="Terraform aws_security_group.main is the highest-impact change.",
            top_risk_contributors=["ev-001"],
            context_completeness={
                "topology_freshness_days": 12,
                "topology_last_imported_at": "2026-04-18T11:22:33Z",
                "incident_index_size": 4,
                "parser_success_rate": 1.0,
                "parser_success_by_tool": {"terraform": 1.0},
                "context_score": 0.84,
            },
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
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
        findings = [
            Finding(
                finding_id="finding-001",
                analysis_id=0,
                title="HIGH: aws_security_group.main",
                description="Security group changes can affect production ingress.",
                severity="high",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_refs=["ev-001"],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                summary="Terraform changed a security group.",
                severity_hint="high",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-1"],
            )
        ]
        blast_radius = BlastRadiusResult(
            affected=[
                ImpactNode(service_id="database", label="Database", depth=0),
                ImpactNode(service_id="api", label="API Service", depth=1),
            ],
            direct_count=1,
            transitive_count=1,
            warning=None,
            unmatched_resources=[],
        )

        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            blast_radius=blast_radius,
            findings=findings,
            evidence_items=evidence_items,
            audit_context={
                "source_interface": "api",
                "trigger_type": "session",
                "trigger_id": "sess-123",
            },
        )
        self.assertIn("id", persisted)
        self.assertEqual(persisted["audit"]["source_interface"], "api")
        self.assertEqual(persisted["audit"]["trigger_type"], "session")
        self.assertEqual(persisted["audit"]["trigger_id"], "sess-123")
        self.assertEqual(persisted["audit"]["files_analyzed"], ["plan.json"])
        self.assertEqual(persisted["audit"]["llm_provider"], "ollama")
        self.assertEqual(persisted["assessment_source"], "heuristic-only")
        self.assertEqual(persisted["narrative_source"], "llm")
        self.assertEqual(persisted["report_schema_version"], "v2")
        self.assertEqual(persisted["narrative_provider"], "ollama")
        self.assertEqual(persisted["narrative_model"], "ollama/llama3")
        self.assertEqual(persisted["skills_applied"], ["git", "terraform"])
        self.assertEqual(persisted["top_risk_contributors"], ["ev-001"])
        self.assertEqual(persisted["context_completeness"]["context_score"], 0.84)
        self.assertEqual(persisted["blast_radius"]["direct_count"], 1)
        self.assertEqual(
            persisted["context_completeness"]["topology_last_imported_at"],
            "2026-04-18T11:22:33Z",
        )
        self.assertEqual(persisted["findings"][0]["confidence"], 1.0)
        self.assertEqual(persisted["evidence_items"][0]["evidence_id"], "ev-001")
        self.assertEqual(persisted["contributors"][0]["evidence_id"], "ev-001")

        fetched = report_service_module.fetch_analysis_report(persisted["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["risk_score"], 42)
        self.assertEqual(fetched["audit"]["source_interface"], "api")
        self.assertEqual(fetched["audit"]["files_analyzed"], ["plan.json"])
        self.assertEqual(fetched["assessment_source"], "heuristic-only")
        self.assertEqual(fetched["narrative_source"], "llm")
        self.assertEqual(fetched["report_schema_version"], "v2")
        self.assertEqual(fetched["skills_applied"], ["git", "terraform"])
        self.assertEqual(fetched["top_risk_contributors"], ["ev-001"])
        self.assertEqual(fetched["context_completeness"]["topology_freshness_days"], 12)
        self.assertEqual(fetched["blast_radius"]["affected"][0]["label"], "Database")
        self.assertEqual(
            fetched["context_completeness"]["parser_success_by_tool"],
            {"terraform": 1.0},
        )
        self.assertEqual(fetched["findings"][0]["evidence_refs"], ["ev-001"])
        self.assertEqual(fetched["evidence_items"][0]["finding_id"], "finding-001")
        self.assertEqual(fetched["contributors"][0]["evidence_id"], "ev-001")
        self.assertNotIn("prompt", json.dumps(fetched))

        history = report_service_module.fetch_analysis_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], persisted["id"])
        self.assertEqual(history[0]["audit"]["llm_provider"], "ollama")
        self.assertEqual(history[0]["top_risk_contributors"], ["ev-001"])
        self.assertEqual(history[0]["report_schema_version"], "v2")

    def test_report_schema_helpers_preserve_forward_compatibility(self) -> None:
        self.assertEqual(
            report_service_module.normalize_report_schema_version(None), "v1"
        )
        self.assertTrue(report_service_module.can_read_report_schema("v3", "v2"))
        self.assertFalse(report_service_module.can_read_report_schema("v2", "v3"))

    def test_persist_analysis_report_combines_assessment_and_narrative_warnings(
        self,
    ) -> None:
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
            partial_context=True,
            warnings=[
                "LLM severity assessment unavailable; falling back to heuristic matrix: provider offline"
            ],
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

        persisted = report_service_module.persist_analysis_report(
            parse_batch, assessment, narrative
        )

        self.assertIn(
            "LLM severity assessment unavailable", " ".join(persisted["warnings"])
        )
        self.assertIn("Narrative provider unavailable", " ".join(persisted["warnings"]))
        self.assertFalse(persisted["narrative_available"])
        self.assertEqual(
            persisted["narrative_failure_notice"],
            "Narrative provider unavailable: provider offline",
        )

    def test_fetch_active_dashboard_report_returns_recent_dashboard_upload(
        self,
    ) -> None:
        settings_service_module.save_dashboard_result_display_duration_seconds(600)
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
            score=75,
            severity="high",
            recommendation="no-go",
            top_risk="High-risk change",
            contributors=[
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=75,
                    summary="Terraform changed a security group.",
                    severity="high",
                    reasoning="Security group changes can affect production ingress.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
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
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )

        active = report_service_module.fetch_active_dashboard_report(
            now=datetime.now(UTC) + timedelta(seconds=120)
        )

        self.assertIsNotNone(active)
        self.assertEqual(active["recommendation"], "no-go")
        self.assertEqual(active["dashboard_display_duration_seconds"], 600)
        self.assertEqual(active["assessment_source"], "heuristic-only")
        self.assertEqual(active["narrative_source"], "llm")
        self.assertEqual(active["report_schema_version"], "v2")
        self.assertEqual(active["skills_applied"], ["git", "terraform"])
        self.assertGreater(active["dashboard_remaining_seconds"], 0)

    def test_fetch_filtered_history_page_omits_evidence_payloads(self) -> None:
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
            top_risk="Terraform changed a security group.",
            top_risk_contributors=["ev-001"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=12,
                    summary="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            NarrativeResult(
                opening_sentence="CAUTION: review the security group update.",
                explanation="The deployment widens database access and should be reviewed.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            findings=[
                Finding(
                    finding_id="finding-001",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Security group changes can affect production ingress.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-001"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-001",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        page = report_service_module.fetch_filtered_analysis_history_page(
            page=1, page_size=5
        )

        self.assertEqual(page["items"][0]["evidence_items"], [])

    def test_persist_analysis_report_raises_when_evidence_cannot_attach_to_finding(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed a security group.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )

        with self.assertRaises(ValueError):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                NarrativeResult(
                    opening_sentence="CAUTION: review the security group update.",
                    explanation="The deployment widens database access and should be reviewed.",
                    guidance=[],
                    degraded=False,
                    warnings=[],
                ),
                findings=[
                    Finding(
                        finding_id="finding-001",
                        analysis_id=0,
                        title="HIGH: aws_security_group.main",
                        description="Security group changes can affect production ingress.",
                        severity="high",
                        category="networking/ingress",
                        deterministic=True,
                        confidence=1.0,
                        uncertainty_note=None,
                        evidence_refs=[],
                        skill_id=None,
                    ),
                    Finding(
                        finding_id="finding-002",
                        analysis_id=0,
                        title="HIGH: aws_security_group.secondary",
                        description="A second security group also changed.",
                        severity="high",
                        category="networking/ingress",
                        deterministic=True,
                        confidence=1.0,
                        uncertainty_note=None,
                        evidence_refs=[],
                        skill_id=None,
                    ),
                ],
                evidence_items=[
                    EvidenceItem(
                        evidence_id="ev-001",
                        analysis_id=0,
                        finding_id="pending:change-1",
                        source_type="artifact",
                        source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                        summary="Terraform changed a security group.",
                        severity_hint="high",
                        deterministic=True,
                        confidence=1.0,
                        related_change_ids=["change-1"],
                    ),
                    EvidenceItem(
                        evidence_id="ev-002",
                        analysis_id=0,
                        finding_id="pending:change-2",
                        source_type="artifact",
                        source_ref="terraform://plan.json#aws_security_group.secondary?action=modify",
                        summary="Terraform changed another security group.",
                        severity_hint="high",
                        deterministic=True,
                        confidence=1.0,
                        related_change_ids=["change-2"],
                    ),
                ],
            )

    def test_init_db_creates_current_analysis_report_schema(self) -> None:
        database_module.engine.dispose()
        if self.db_path.exists():
            self.db_path.unlink()

        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(report_service_module)
        database_module.init_db()

        sqlite_conn = sqlite3.connect(self.db_path)
        cursor = sqlite_conn.execute("PRAGMA table_info(analysis_reports)")
        columns = {row[1] for row in cursor.fetchall()}
        sqlite_conn.close()

        self.assertIn("analyzed_files_json", columns)
        self.assertIn("llm_provider", columns)
        self.assertIn("assessment_source", columns)
        self.assertIn("narrative_source", columns)
        self.assertIn("narrative_skills_json", columns)
        self.assertIn("dashboard_display_duration_seconds", columns)
        self.assertIn("report_schema_version", columns)


if __name__ == "__main__":
    unittest.main()
