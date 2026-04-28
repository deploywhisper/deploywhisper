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
import services.project_service as project_service_module
import services.report_service as report_service_module
import services.settings_service as settings_service_module
from analysis.blast_radius import BlastRadiusResult, ImpactNode
from analysis.rollback_planner import RollbackPlan, RollbackStep
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
        reload(project_service_module)
        reload(settings_service_module)
        reload(report_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("APP_BASE_URL", None)
        self.tempdir.cleanup()

    def _persist_shareable_report(self) -> dict:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="prod/network/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="prod/network/plan.json",
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
            top_risk="prod/network/plan.json changed aws_security_group.main and is the highest-impact change.",
            contributors=[
                RiskContributor(
                    source_file="prod/network/plan.json",
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
            opening_sentence="CAUTION: review prod/network/plan.json before release.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-001",
                analysis_id=0,
                title="HIGH: prod/network/plan.json",
                description="Security group changes in prod/network/plan.json can affect production ingress.",
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
                source_ref="terraform://prod/network/plan.json#L14",
                summary="Terraform changed a security group.",
                severity_hint="high",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-1"],
            )
        ]
        return report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=findings,
            evidence_items=evidence_items,
            audit_context={"source_interface": "api"},
        )

    def _persist_comparison_report(
        self,
        *,
        score: int,
        severity: str,
        recommendation: str,
        top_risk: str,
        findings: list[Finding],
        evidence_items: list[EvidenceItem],
    ) -> dict:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="prod/network/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="prod/network/plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.main",
                            action="modify",
                            summary=top_risk,
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=score,
            severity=severity,
            recommendation=recommendation,
            top_risk=top_risk,
            contributors=[
                RiskContributor(
                    source_file="prod/network/plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=18,
                    summary=top_risk,
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence=f"{severity.upper()}: {top_risk}",
            explanation="Comparison test narrative.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        return report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=findings,
            evidence_items=evidence_items,
            audit_context={"source_interface": "api", "trigger_type": "pull_request"},
        )

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
        rollback_plan = RollbackPlan(
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
            complexity_explanation="Score 3/5 because the plan covers 1 destructive change.",
            warning=None,
        )

        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            blast_radius=blast_radius,
            rollback_plan=rollback_plan,
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
        self.assertEqual(persisted["context_completeness"]["context_score"], 0.84)
        self.assertEqual(persisted["blast_radius"]["direct_count"], 1)
        self.assertEqual(persisted["rollback_plan"]["complexity_score"], 3)
        self.assertEqual(
            persisted["rollback_plan"]["steps"][0]["estimated_minutes"], 15
        )
        self.assertEqual(
            persisted["context_completeness"]["topology_last_imported_at"],
            "2026-04-18T11:22:33Z",
        )
        self.assertEqual(persisted["findings"][0]["confidence"], 1.0)
        persisted_evidence_id = persisted["evidence_items"][0]["evidence_id"]
        persisted_finding_id = persisted["findings"][0]["finding_id"]
        self.assertTrue(persisted_evidence_id.startswith("evidence-"))
        self.assertTrue(persisted_finding_id.startswith("finding-"))
        self.assertEqual(persisted["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(
            persisted["findings"][0]["evidence_refs"], [persisted_evidence_id]
        )
        self.assertEqual(
            persisted["contributors"][0]["evidence_id"], persisted_evidence_id
        )

        fetched = report_service_module.fetch_analysis_report(persisted["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["risk_score"], 42)
        self.assertEqual(fetched["audit"]["source_interface"], "api")
        self.assertEqual(fetched["audit"]["files_analyzed"], ["plan.json"])
        self.assertEqual(
            fetched["narrative_explanation"],
            "The deployment widens database access and should be reviewed.",
        )
        self.assertEqual(fetched["assessment_source"], "heuristic-only")
        self.assertEqual(fetched["narrative_source"], "llm")
        self.assertEqual(fetched["report_schema_version"], "v2")
        self.assertEqual(fetched["skills_applied"], ["git", "terraform"])
        self.assertEqual(fetched["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(fetched["context_completeness"]["topology_freshness_days"], 12)
        self.assertEqual(fetched["blast_radius"]["affected"][0]["label"], "Database")
        self.assertEqual(
            fetched["rollback_plan"]["steps"][0]["title"],
            "Revert aws_security_group.main",
        )
        self.assertEqual(
            fetched["context_completeness"]["parser_success_by_tool"],
            {"terraform": 1.0},
        )
        self.assertEqual(fetched["findings"][0]["finding_id"], persisted_finding_id)
        self.assertEqual(
            fetched["findings"][0]["evidence_refs"], [persisted_evidence_id]
        )
        self.assertEqual(
            fetched["evidence_items"][0]["finding_id"], persisted_finding_id
        )
        self.assertEqual(
            fetched["contributors"][0]["evidence_id"], persisted_evidence_id
        )
        self.assertNotIn("prompt", json.dumps(fetched))

        history = report_service_module.fetch_analysis_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], persisted["id"])
        self.assertEqual(history[0]["audit"]["llm_provider"], "ollama")
        self.assertEqual(history[0]["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(history[0]["report_schema_version"], "v2")
        self.assertEqual(history[0]["rollback_plan"]["complexity"], "medium")

    def test_persist_analysis_report_allows_repeated_scans_with_same_logical_ids(
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
                            resource_id="PersistentVolumeClaim/data-apisix-api-gateway-green-etcd-0",
                            action="apply",
                            summary="Kubernetes PVC applied for preproduction etcd storage.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="caution",
            top_risk="PVC storage change requires review.",
            top_risk_contributors=["ev-ea30f3b4d375"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-ea30f3b4d375",
                    source_file="deployment.yaml",
                    tool="kubernetes",
                    resource_id="PersistentVolumeClaim/data-apisix-api-gateway-green-etcd-0",
                    action="apply",
                    contribution=12,
                    summary="PVC storage change requires review.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-039f73a794b8",
                analysis_id=0,
                title="HIGH: PersistentVolumeClaim/data-apisix-api-gateway-green-etcd-0",
                description="Kubernetes PVC apply change requires review.",
                severity="high",
                category="storage",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_refs=["ev-ea30f3b4d375"],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-ea30f3b4d375",
                analysis_id=0,
                finding_id="pending:chg-001",
                source_type="artifact",
                source_ref="kubernetes://deployment.yaml#PersistentVolumeClaim/data-apisix-api-gateway-green-etcd-0?action=apply",
                summary="PVC storage change requires review.",
                severity_hint="high",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["chg-001"],
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the PVC update.",
            explanation="The deployment changes persistent storage configuration.",
            guidance=[],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["kubernetes"],
        )

        first = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=findings,
            evidence_items=evidence_items,
        )
        second = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=findings,
            evidence_items=evidence_items,
        )

        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(
            first["findings"][0]["finding_id"], second["findings"][0]["finding_id"]
        )
        self.assertNotEqual(
            first["evidence_items"][0]["evidence_id"],
            second["evidence_items"][0]["evidence_id"],
        )
        history = report_service_module.fetch_analysis_history()
        self.assertEqual(len(history), 2)

    def test_configure_report_share_persists_password_and_redaction_settings(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        os.environ["APP_BASE_URL"] = "https://install.example.com"

        share_config = report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        self.assertEqual(
            share_config["share_url"],
            f"https://install.example.com/reports/{report['id']}",
        )
        self.assertTrue(share_config["password_protected"])
        self.assertTrue(share_config["redact_filenames"])

        shared_report = report_service_module.fetch_shared_analysis_report(
            report["id"],
            password="s3cret-pass",
        )
        self.assertIsNotNone(shared_report)
        assert shared_report is not None
        self.assertNotIn("prod/network/plan.json", shared_report["top_risk"])
        self.assertNotIn("prod/network/plan.json", shared_report["narrative_opening"])
        self.assertNotIn(
            "prod/network/plan.json", shared_report["findings"][0]["title"]
        )
        self.assertEqual(shared_report["audit"]["files_analyzed"], ["Artifact 1"])
        self.assertEqual(shared_report["contributors"][0]["source_file"], "Artifact 1")
        self.assertIn("Artifact 1", shared_report["evidence_items"][0]["source_ref"])
        self.assertNotIn(
            "prod/network/plan.json",
            shared_report["evidence_items"][0]["source_ref"],
        )

    def test_fetch_shared_analysis_report_requires_password_when_configured(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=False,
        )

        self.assertIsNone(
            report_service_module.fetch_shared_analysis_report(report["id"])
        )
        self.assertIsNone(
            report_service_module.fetch_shared_analysis_report(
                report["id"], password="wrong-pass"
            )
        )
        self.assertIsNotNone(
            report_service_module.fetch_shared_analysis_report(
                report["id"], password="s3cret-pass"
            )
        )

    def test_fetch_report_comparison_returns_findings_and_evidence_deltas(self) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Security group review is still pending.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-shared", "ev-old"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-removed",
                    analysis_id=0,
                    title="LOW: aws_cloudwatch_log_group.api",
                    description="Log retention is unset.",
                    severity="low",
                    category="observability/logging",
                    deterministic=True,
                    confidence=0.82,
                    uncertainty_note=None,
                    evidence_refs=["ev-removed"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-shared",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-old",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L22",
                    summary="Port 22 remains reachable.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-2"],
                ),
                EvidenceItem(
                    evidence_id="ev-removed",
                    analysis_id=0,
                    finding_id="pending:removed",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L31",
                    summary="No retention override is configured.",
                    severity_hint="low",
                    deterministic=True,
                    confidence=0.82,
                    related_change_ids=["change-3"],
                ),
            ],
        )
        current = self._persist_comparison_report(
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="Security group exposure widened after the latest commit.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-shared", "ev-new"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-added",
                    analysis_id=0,
                    title="HIGH: aws_db_instance.main",
                    description="Storage encryption is still disabled.",
                    severity="high",
                    category="data/encryption",
                    deterministic=True,
                    confidence=0.93,
                    uncertainty_note=None,
                    evidence_refs=["ev-added"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-shared",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-new",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L26",
                    summary="Port 3306 is newly reachable.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-4"],
                ),
                EvidenceItem(
                    evidence_id="ev-added",
                    analysis_id=0,
                    finding_id="pending:added",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L40",
                    summary="Storage encryption is set to false.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=0.93,
                    related_change_ids=["change-5"],
                ),
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])
        self.assertEqual(comparison["current_report"]["id"], current["id"])
        self.assertEqual(comparison["risk_score_delta"], 29)
        self.assertEqual(
            comparison["findings"]["added"][0]["title"], "HIGH: aws_db_instance.main"
        )
        self.assertEqual(
            comparison["findings"]["removed"][0]["title"],
            "LOW: aws_cloudwatch_log_group.api",
        )
        self.assertEqual(
            comparison["findings"]["severity_changed"][0]["previous_severity"],
            "medium",
        )
        self.assertEqual(
            comparison["findings"]["severity_changed"][0]["current_severity"],
            "critical",
        )
        self.assertIn(
            "terraform://prod/network/plan.json#L26",
            {item["source_ref"] for item in comparison["evidence"]["added"]},
        )
        self.assertIn(
            "terraform://prod/network/plan.json#L22",
            {item["source_ref"] for item in comparison["evidence"]["removed"]},
        )

    def test_fetch_report_comparison_preserves_duplicate_findings(self) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Duplicate security findings still need review.",
            findings=[
                Finding(
                    finding_id="finding-dup-a",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-dup-a"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-dup-b",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=["ev-dup-b"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-dup-a",
                    analysis_id=0,
                    finding_id="pending:dup-a",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-dup-b",
                    analysis_id=0,
                    finding_id="pending:dup-b",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L22",
                    summary="Port 22 remains reachable.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-2"],
                ),
            ],
        )
        current = self._persist_comparison_report(
            score=51,
            severity="medium",
            recommendation="caution",
            top_risk="One duplicate finding remains after the latest commit.",
            findings=[
                Finding(
                    finding_id="finding-dup-a",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-dup-a"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-dup-a",
                    analysis_id=0,
                    finding_id="pending:dup-a",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])
        self.assertEqual(len(comparison["findings"]["removed"]), 1)
        self.assertEqual(
            comparison["findings"]["removed"][0]["title"],
            "MEDIUM: aws_security_group.main",
        )
        self.assertIn(
            "terraform://prod/network/plan.json#L22",
            {item["source_ref"] for item in comparison["evidence"]["removed"]},
        )

    def test_fetch_report_comparison_is_stable_when_duplicate_finding_order_flips(
        self,
    ) -> None:
        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Duplicate findings exist in one order.",
            findings=[
                Finding(
                    finding_id="finding-dup-a",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-dup-a"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-dup-b",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=["ev-dup-b"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-dup-a",
                    analysis_id=0,
                    finding_id="pending:dup-a",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-dup-b",
                    analysis_id=0,
                    finding_id="pending:dup-b",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L22",
                    summary="Port 22 remains reachable.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-2"],
                ),
            ],
        )
        current = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Duplicate findings exist in reversed order.",
            findings=[
                Finding(
                    finding_id="finding-dup-b",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=["ev-dup-b"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-dup-a",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-dup-a"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-dup-b",
                    analysis_id=0,
                    finding_id="pending:dup-b",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L22",
                    summary="Port 22 remains reachable.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-2"],
                ),
                EvidenceItem(
                    evidence_id="ev-dup-a",
                    analysis_id=0,
                    finding_id="pending:dup-a",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], 1)
        self.assertEqual(comparison["current_report"]["id"], current["id"])
        self.assertEqual(comparison["findings"]["added"], [])
        self.assertEqual(comparison["findings"]["removed"], [])
        self.assertEqual(comparison["findings"]["severity_changed"], [])
        self.assertEqual(comparison["evidence"]["added"], [])
        self.assertEqual(comparison["evidence"]["removed"], [])

    def test_fetch_shared_report_comparison_respects_filename_redaction(self) -> None:
        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="prod/network/plan.json still needs review.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="MEDIUM: prod/network/plan.json",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-shared"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-shared",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )
        current = self._persist_comparison_report(
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="prod/network/plan.json widened database access.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="CRITICAL: prod/network/plan.json",
                    description="Security group ingress is broader than expected.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-new"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-new",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L26",
                    summary="Port 3306 is newly reachable in prod/network/plan.json.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-2"],
                )
            ],
        )
        report_service_module.configure_report_share(
            current["id"],
            password="review-only",
            redact_filenames=True,
        )

        comparison = report_service_module.fetch_shared_report_comparison(
            current["id"],
            password="review-only",
        )

        self.assertIsNotNone(comparison)
        assert comparison is not None
        serialized = json.dumps(comparison)
        self.assertNotIn("prod/network/plan.json", serialized)
        self.assertIn("Artifact 1", serialized)

    def test_fetch_shared_report_comparison_requires_previous_report_access(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Previous report is password protected.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-shared"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-shared",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )
        current = self._persist_comparison_report(
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="Current report is shared without a password.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-shared"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-shared",
                    analysis_id=0,
                    finding_id="pending:shared",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )
        report_service_module.configure_report_share(
            previous["id"],
            password="previous-only",
            redact_filenames=False,
        )

        self.assertIsNone(
            report_service_module.fetch_shared_report_comparison(current["id"])
        )
        self.assertIsNone(
            report_service_module.fetch_shared_report_comparison(
                current["id"],
                password="wrong-pass",
            )
        )
        self.assertIsNotNone(
            report_service_module.fetch_shared_report_comparison(
                current["id"],
                password="previous-only",
            )
        )

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
        self.assertEqual(persisted["narrative_source"], "fallback")
        self.assertEqual(persisted["audit"]["llm_provider"], "ollama")
        self.assertEqual(persisted["audit"]["llm_model"], "ollama/llama3")
        self.assertTrue(persisted["audit"]["llm_local_mode"])
        self.assertEqual(persisted["narrative_provider"], "ollama")
        self.assertEqual(persisted["narrative_model"], "ollama/llama3")
        self.assertTrue(persisted["narrative_local_mode"])
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

    def test_persist_analysis_report_scopes_reports_to_project(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        legacy = self._persist_shareable_report()

        scoped = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.json",
                        tool="terraform",
                        status="parsed",
                        changes=[
                            UnifiedChange(
                                source_file="payments.json",
                                tool="terraform",
                                resource_id="aws_security_group.payments",
                                action="modify",
                                summary="Payments change.",
                            )
                        ],
                    )
                ]
            ),
            RiskAssessment(
                score=15,
                severity="low",
                recommendation="go",
                top_risk="Low-risk payments change.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low-risk payments change.",
                explanation="Scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        self.assertEqual(legacy["project"]["project_key"], "unassigned")
        self.assertEqual(scoped["project"]["project_key"], "payments")

        page = report_service_module.fetch_filtered_analysis_history_page(
            project_key="payments"
        )
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["project"]["project_key"], "payments")

    def test_fetch_analysis_report_respects_project_scope(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        scoped = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments.json",
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
                top_risk="Low-risk payments change.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low-risk payments change.",
                explanation="Scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        with self.assertRaises(project_service_module.ProjectResolutionError):
            report_service_module.fetch_analysis_report(
                scoped["id"], project_key="missing"
            )
        self.assertIsNotNone(
            report_service_module.fetch_analysis_report(
                scoped["id"], project_key=project.project_key
            )
        )

    def test_previous_scan_diffs_do_not_cross_project_boundaries(self) -> None:
        payments = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        first = self._persist_comparison_report(
            score=40,
            severity="medium",
            recommendation="caution",
            top_risk="Payments review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session, int(first["id"]), include_evidence=True
            )
            assert report is not None
            report.project_id = payments.id
            session.commit()
        second = self._persist_comparison_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Platform review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session, int(second["id"]), include_evidence=True
            )
            assert report is not None
            report.project_id = platform.id
            session.commit()

        history = report_service_module.fetch_filtered_analysis_history_page()
        by_id = {item["id"]: item for item in history["items"]}
        self.assertNotIn("previous_scan_diff", by_id[int(first["id"])])
        self.assertNotIn("previous_scan_diff", by_id[int(second["id"])])


if __name__ == "__main__":
    unittest.main()
