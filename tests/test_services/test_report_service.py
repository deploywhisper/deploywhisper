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
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.artifact_snapshot_service as artifact_snapshot_service_module
import services.project_service as project_service_module
import services.report_service as report_service_module
import services.settings_service as settings_service_module
from analysis.blast_radius import BlastRadiusResult, ImpactNode
from analysis.rollback_planner import RollbackPlan, RollbackStep
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import EvidenceItem, Finding
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParseIssue, ParsedFileResult, UnifiedChange
from parsers.terraform_parser import parse_terraform
from pydantic import ValidationError


class ReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        self.snapshot_dir = Path(self.tempdir.name) / "artifacts"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["ARTIFACT_SNAPSHOT_DIR"] = str(self.snapshot_dir)
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(artifact_snapshot_service_module)
        reload(project_service_module)
        reload(settings_service_module)
        reload(report_service_module)
        database_module.init_db()

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("APP_BASE_URL", None)
        os.environ.pop("ARTIFACT_SNAPSHOT_DIR", None)
        self.tempdir.cleanup()

    def test_create_analysis_report_validates_finding_context_payloads(self) -> None:
        project = project_service_module.ensure_default_project()
        report_kwargs = {
            "project_id": project.id,
            "risk_score": 42,
            "severity": "medium",
            "recommendation": "caution",
            "top_risk": "Security group exposure",
            "report_schema_version": "v2",
            "parse_summary": "1 parsed, 0 failed, 0 skipped, 1 normalized change",
            "narrative_opening": "CAUTION: review the security group update.",
            "narrative_explanation": "Review the ingress change.",
            "warnings_json": "[]",
            "contributors_json": "[]",
            "analyzed_files_json": '["plan.json"]',
            "submission_manifest_json": "{}",
            "submission_manifest_fallback_json": "[]",
            "blast_radius_json": "{}",
            "rollback_plan_json": "{}",
            "llm_provider": "ollama",
            "llm_model": "ollama/llama3",
            "llm_local_mode": "true",
            "assessment_source": "heuristic-only",
            "narrative_source": "fallback",
            "narrative_skills_json": "[]",
            "source_interface": "api",
            "trigger_type": "session",
            "trigger_id": "sess-invalid-finding",
            "dashboard_display_duration_seconds": None,
        }
        finding = {
            "finding_id": "finding-invalid",
            "analysis_id": 0,
            "title": "MEDIUM: aws_security_group.main",
            "description": "Security group changes can affect ingress.",
            "severity": "medium",
            "category": "networking/ingress",
            "deterministic": True,
            "confidence": 1.0,
            "guidance": ["Review ingress before deployment."],
            "evidence_classification": "deterministic",
            "evidence_refs": [],
            "skill_id": None,
        }

        for invalid_fields in (
            {"guidance": "Review ingress before deployment."},
            {"evidence_classification": "unsupported"},
        ):
            with self.subTest(invalid_fields=invalid_fields):
                with database_module.SessionLocal() as session:
                    with self.assertRaises(ValidationError):
                        analysis_reports_repository_module.create_analysis_report(
                            session,
                            **report_kwargs,
                            findings_payload=[{**finding, **invalid_fields}],
                            evidence_payload=[],
                        )

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
        parse_files: list[ParsedFileResult] | None = None,
    ) -> dict:
        parsed_files = parse_files or [
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
        contributor_source = next(
            (
                file_result.file_name
                for file_result in parsed_files
                if file_result.status == "parsed"
            ),
            parsed_files[0].file_name,
        )
        parse_batch = ParseBatchResult(files=parsed_files)
        assessment = RiskAssessment(
            score=score,
            severity=severity,
            recommendation=recommendation,
            top_risk=top_risk,
            contributors=[
                RiskContributor(
                    source_file=contributor_source,
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
                            metadata={
                                "module_address": "module.network",
                                "redacted_fields": ["ingress.0.description"],
                                "plan_unsupported_fields": ["plan.planned_values"],
                            },
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
                    metadata={
                        "module_address": "module.network",
                        "redacted_fields": ["ingress.0.description"],
                        "plan_unsupported_fields": ["plan.planned_values"],
                    },
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
                explanation="Security group ingress changed in the submitted plan.",
                guidance=["Review ingress before deployment."],
                severity="high",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_classification="deterministic",
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
        self.assertEqual(
            persisted["findings"][0]["explanation"],
            "Security group ingress changed in the submitted plan.",
        )
        self.assertEqual(
            persisted["findings"][0]["guidance"],
            ["Review ingress before deployment."],
        )
        self.assertEqual(
            persisted["findings"][0]["evidence_classification"],
            "deterministic",
        )
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
        self.assertEqual(
            persisted["contributors"][0]["metadata"]["module_address"],
            "module.network",
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
            fetched["findings"][0]["explanation"],
            "Security group ingress changed in the submitted plan.",
        )
        self.assertEqual(
            fetched["findings"][0]["guidance"],
            ["Review ingress before deployment."],
        )
        self.assertEqual(
            fetched["findings"][0]["evidence_classification"],
            "deterministic",
        )
        self.assertEqual(
            fetched["findings"][0]["evidence_refs"], [persisted_evidence_id]
        )
        self.assertEqual(
            fetched["evidence_items"][0]["finding_id"], persisted_finding_id
        )
        self.assertEqual(fetched["evidence_items"][0]["artifact"], "plan.json")
        self.assertEqual(
            fetched["evidence_items"][0]["location"],
            "plan.json#aws_security_group.main",
        )
        self.assertEqual(
            fetched["evidence_items"][0]["resource"], "aws_security_group.main"
        )
        self.assertEqual(fetched["evidence_items"][0]["operation"], "modify")
        self.assertEqual(
            fetched["evidence_items"][0]["project_id"],
            persisted["project"]["id"],
        )
        self.assertEqual(
            fetched["evidence_items"][0]["project_key"],
            persisted["project"]["project_key"],
        )
        self.assertIsNone(fetched["evidence_items"][0]["workspace_id"])
        self.assertIsNone(fetched["evidence_items"][0]["workspace_key"])
        self.assertEqual(fetched["evidence_items"][0]["source_kind"], "artifact")
        self.assertEqual(
            fetched["evidence_items"][0]["determinism_level"], "deterministic"
        )
        self.assertEqual(fetched["evidence_items"][0]["redaction_status"], "none")
        self.assertEqual(
            fetched["contributors"][0]["evidence_id"], persisted_evidence_id
        )
        self.assertEqual(
            fetched["contributors"][0]["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        self.assertNotIn("prompt", json.dumps(fetched))

        history = report_service_module.fetch_analysis_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], persisted["id"])
        self.assertEqual(history[0]["audit"]["llm_provider"], "ollama")
        self.assertEqual(history[0]["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(history[0]["report_schema_version"], "v2")
        self.assertEqual(history[0]["rollback_plan"]["complexity"], "medium")
        self.assertEqual(
            history[0]["contributors"][0]["metadata"]["redacted_fields"],
            ["ingress.0.description"],
        )

    def test_empty_plan_unsupported_fields_from_real_parser_survive_report_fetch(
        self,
    ) -> None:
        changes = parse_terraform(
            "empty-plan.json",
            b'{"planned_values": {}, "resource_changes": []}',
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(
            changes[0].metadata["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="empty-plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=changes,
                )
            ]
        )
        assessment = RiskAssessment(
            score=0,
            severity="low",
            recommendation="go",
            top_risk="Terraform plan contains no planned resource mutations.",
            top_risk_contributors=["ev-empty"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-empty",
                    source_file=changes[0].source_file,
                    tool=changes[0].tool,
                    resource_id=changes[0].resource_id,
                    action=changes[0].action,
                    contribution=0,
                    summary=changes[0].summary,
                    metadata=changes[0].metadata,
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: Terraform plan has no planned resource mutations.",
            explanation="The submitted plan is a valid empty Terraform plan.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-empty",
                analysis_id=0,
                finding_id="pending:empty-plan",
                source_type="artifact",
                source_ref="terraform://empty-plan.json#terraform-plan?action=no-op",
                summary=changes[0].summary,
                severity_hint="low",
                deterministic=True,
                confidence=1.0,
                related_change_ids=[changes[0].change_id],
            )
        ]
        findings = [
            Finding(
                finding_id="finding-empty",
                analysis_id=0,
                title="LOW: empty Terraform plan",
                description="The Terraform plan is valid and contains no mutations.",
                severity="low",
                category="terraform/plan",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_refs=["ev-empty"],
                skill_id=None,
            )
        ]

        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=findings,
            evidence_items=evidence_items,
        )

        fetched = report_service_module.fetch_analysis_report(persisted["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(
            fetched["contributors"][0]["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        history = report_service_module.fetch_analysis_history()
        self.assertEqual(
            history[0]["contributors"][0]["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )

    def test_persist_analysis_report_preserves_explicit_evidence_determinism_level(
        self,
    ) -> None:
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
            contributors=[
                RiskContributor(
                    evidence_id="ev-heuristic",
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
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-heuristic",
                analysis_id=0,
                title="MEDIUM: aws_security_group.main",
                description="Security group changes can affect ingress.",
                severity="medium",
                category="networking/ingress",
                deterministic=False,
                confidence=0.7,
                uncertainty_note="Severity is inferred from incomplete context.",
                evidence_refs=["ev-heuristic"],
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-heuristic",
                analysis_id=0,
                finding_id="pending:change-heuristic",
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                summary="Terraform changed a security group.",
                severity_hint="medium",
                deterministic=False,
                determinism_level="heuristic",
                confidence=0.7,
                related_change_ids=["change-heuristic"],
            )
        ]

        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=findings,
            evidence_items=evidence_items,
            audit_context={"source_interface": "api"},
        )
        fetched = report_service_module.fetch_analysis_report(persisted["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["evidence_items"][0]["determinism_level"], "heuristic")
        self.assertFalse(fetched["evidence_items"][0]["deterministic"])

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

    def test_shared_report_redaction_preserves_sensitive_content_exclusion(
        self,
    ) -> None:
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
            top_risk="prod/network/plan.json changed aws_security_group.main.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review prod/network/plan.json before release.",
            explanation="The deployment should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            artifact_snapshots={
                "prod/network/plan.json": b'{"resource_changes": []}',
                ".env": b"SECRET=1",
            },
            audit_context={"source_interface": "api"},
        )
        report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        shared_report = report_service_module.fetch_shared_analysis_report(
            report["id"],
            password="s3cret-pass",
        )

        self.assertIsNotNone(shared_report)
        assert shared_report is not None
        manifest_items = shared_report["submission_manifest"]["items"]
        self.assertEqual(
            [item["name"] for item in manifest_items],
            ["Artifact 1", "Artifact 2"],
        )
        by_status = {item["status"]: item for item in manifest_items}
        self.assertEqual(by_status["accepted"]["redaction_status"], "redacted")
        self.assertEqual(
            by_status["sensitive"]["redaction_status"],
            "sensitive_blocked",
        )
        self.assertEqual(shared_report["submission_manifest"]["provenance"], {})
        for item in manifest_items:
            self.assertEqual(
                set(item["provenance"]),
                {"submitted_index", "submitted_name"},
            )
            self.assertNotIn("trigger_id", item["provenance"])
            self.assertNotIn("project_id", item["provenance"])
            self.assertNotIn("project_key", item["provenance"])
            self.assertNotIn("workspace_id", item["provenance"])
            self.assertNotIn("workspace_key", item["provenance"])
        self.assertTrue(
            shared_report["submission_manifest"]["redaction"]["filenames_redacted"]
        )

    def test_shared_report_redaction_rewrites_manifest_messages(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="prod/network/plan.json",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="prod/network/plan.json",
                        tool="terraform",
                        message="Could not parse prod/network/plan.json",
                    ),
                )
            ]
        )
        assessment = RiskAssessment(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="prod/network/plan.json did not parse.",
            contributors=[],
            interaction_risks=[],
            partial_context=True,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="Review prod/network/plan.json.",
            explanation="The deployment could not be fully analyzed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            artifact_snapshots={
                "prod/network/plan.json": b"resource {",
            },
            audit_context={"source_interface": "api"},
        )
        report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        shared_report = report_service_module.fetch_shared_analysis_report(
            report["id"],
            password="s3cret-pass",
        )

        self.assertIsNotNone(shared_report)
        assert shared_report is not None
        message = shared_report["submission_manifest"]["items"][0]["message"]
        self.assertEqual(
            message,
            "Terraform artifact failed parser validation; analysis coverage is partial.",
        )
        self.assertNotIn("prod/network/plan.json", message)
        self.assertNotIn("plan.json", message)

    def test_shared_report_redaction_preserves_extensionless_basename_words(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="prod/main",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="prod/main",
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
            top_risk="prod/main changed; the main service remains healthy.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: prod/main needs review, but the main path is stable.",
            explanation="Review required.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
        )
        report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        shared_report = report_service_module.fetch_shared_analysis_report(
            report["id"],
            password="s3cret-pass",
        )

        self.assertIsNotNone(shared_report)
        assert shared_report is not None
        self.assertEqual(
            shared_report["top_risk"],
            "Artifact 1 changed; the main service remains healthy.",
        )
        self.assertEqual(
            shared_report["narrative_opening"],
            "CAUTION: Artifact 1 needs review, but the main path is stable.",
        )

    def test_shared_report_redaction_redacts_file_like_extensionless_basenames(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="ci/Jenkinsfile",
                    tool="jenkins",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="ci/Jenkinsfile",
                            tool="jenkins",
                            resource_id="pipeline.deploy",
                            action="modify",
                            summary="Jenkinsfile changed.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="ci/Jenkinsfile changed; Jenkinsfile deploy stage needs review.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: Jenkinsfile needs review.",
            explanation="Review required.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
        )
        report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        shared_report = report_service_module.fetch_shared_analysis_report(
            report["id"],
            password="s3cret-pass",
        )

        self.assertIsNotNone(shared_report)
        assert shared_report is not None
        serialized = json.dumps(shared_report)
        self.assertNotIn("Jenkinsfile", serialized)
        self.assertIn("Artifact 1", serialized)

    def test_shared_report_redaction_redacts_duplicate_basenames_generically(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="prod/a/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="prod/a/plan.json",
                            tool="terraform",
                            resource_id="aws_s3_bucket.a",
                            action="modify",
                            summary="Bucket changed.",
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name="prod/b/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="prod/b/plan.json",
                            tool="terraform",
                            resource_id="aws_s3_bucket.b",
                            action="modify",
                            summary="Bucket changed.",
                        )
                    ],
                ),
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="plan.json needs review after prod/a/plan.json changed.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: plan.json should be reviewed.",
            explanation="Review required.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
        )
        report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        shared_report = report_service_module.fetch_shared_analysis_report(
            report["id"],
            password="s3cret-pass",
        )

        self.assertIsNotNone(shared_report)
        assert shared_report is not None
        serialized = json.dumps(shared_report)
        self.assertNotIn("plan.json", serialized)
        self.assertNotIn("prod/a/plan.json", serialized)
        self.assertNotIn("prod/b/plan.json", serialized)
        self.assertIn("Artifact file", serialized)

    def test_shared_report_redaction_prefers_longest_overlapping_filename(
        self,
    ) -> None:
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
                ),
                ParsedFileResult(
                    file_name="plan.json.bak",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json.bak",
                            tool="terraform",
                            resource_id="aws_s3_bucket.backup",
                            action="modify",
                            summary="Backup bucket changed.",
                        )
                    ],
                ),
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="plan.json.bak changed after plan.json.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: compare plan.json.bak with plan.json.",
            explanation="Review required.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
        )
        report_service_module.configure_report_share(
            report["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        shared_report = report_service_module.fetch_shared_analysis_report(
            report["id"],
            password="s3cret-pass",
        )

        self.assertIsNotNone(shared_report)
        assert shared_report is not None
        serialized = json.dumps(shared_report)
        self.assertNotIn("plan.json", serialized)
        self.assertNotIn(".bak", serialized)
        self.assertIn("Artifact 2 changed after Artifact 1", shared_report["top_risk"])

    def test_persist_manifest_uses_submitted_artifacts_without_raw_snapshots(
        self,
    ) -> None:
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
                ),
                ParsedFileResult(
                    file_name="broken.tf",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="broken.tf",
                        tool="terraform",
                        message="Unexpected token",
                    ),
                ),
            ]
        )
        assessment = RiskAssessment(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="plan.json changed aws_security_group.main.",
            contributors=[],
            interaction_risks=[],
            partial_context=True,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: review the partial analysis.",
            explanation="The deployment was partially analyzed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            submitted_artifacts=[
                ("plan.json", b'{"resource_changes": []}'),
                ("broken.tf", b"resource {"),
                (".env", b"SECRET=1"),
                ("notes.txt", b"hello"),
            ],
            audit_context={"source_interface": "api"},
        )

        self.assertIsNotNone(
            artifact_snapshot_service_module.load_report_artifact(
                report["id"], "plan.json"
            )
        )
        self.assertIsNone(
            artifact_snapshot_service_module.load_report_artifact(
                report["id"], "broken.tf"
            )
        )
        self.assertIsNone(
            artifact_snapshot_service_module.load_report_artifact(report["id"], ".env")
        )
        self.assertIsNone(
            artifact_snapshot_service_module.load_report_artifact(
                report["id"], "notes.txt"
            )
        )
        manifest = report["submission_manifest"]
        self.assertEqual(manifest["submitted_artifact_count"], 4)
        self.assertEqual(manifest["accepted_artifact_count"], 2)
        self.assertEqual(manifest["analyzed_artifact_count"], 1)
        self.assertEqual(manifest["excluded_artifact_count"], 1)
        self.assertEqual(manifest["sensitive_artifact_count"], 1)
        self.assertEqual(manifest["failed_artifact_count"], 1)
        self.assertEqual(report["audit"]["files_analyzed"], ["plan.json"])
        by_name = {item["name"]: item for item in manifest["items"]}
        self.assertEqual(
            by_name["plan.json"]["message"],
            "Terraform artifact parsed successfully and included in analysis.",
        )
        self.assertEqual(by_name[".env"]["status"], "sensitive")
        self.assertEqual(by_name["notes.txt"]["status"], "excluded")
        self.assertEqual(by_name["broken.tf"]["status"], "failed")
        self.assertEqual(
            by_name["broken.tf"]["message"],
            "Terraform artifact failed parser validation; analysis coverage is partial.",
        )
        self.assertNotIn("Unexpected token", by_name["broken.tf"]["message"])

    def test_failed_artifact_snapshots_are_not_persisted(self) -> None:
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
                ),
                ParsedFileResult(
                    file_name="broken.tf",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="broken.tf",
                        tool="terraform",
                        message="Unexpected token SECRET=1",
                    ),
                ),
            ]
        )
        assessment = RiskAssessment(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="plan.json changed aws_security_group.main.",
            contributors=[],
            interaction_risks=[],
            partial_context=True,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: review the partial analysis.",
            explanation="The deployment was partially analyzed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            artifact_snapshots={
                "plan.json": b'{"resource_changes": []}',
                "broken.tf": b"SECRET=1",
            },
            audit_context={"source_interface": "api"},
        )

        self.assertIsNotNone(
            artifact_snapshot_service_module.load_report_artifact(
                report["id"], "plan.json"
            )
        )
        self.assertIsNone(
            artifact_snapshot_service_module.load_report_artifact(
                report["id"], "broken.tf"
            )
        )
        by_name = {
            item["name"]: item for item in report["submission_manifest"]["items"]
        }
        self.assertEqual(
            by_name["broken.tf"]["message"],
            "Terraform artifact failed parser validation; analysis coverage is partial.",
        )
        self.assertNotIn("SECRET=1", by_name["broken.tf"]["message"])

    def test_persist_manifest_records_resolved_project_workspace_scope(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        workspace = project_service_module.create_workspace(
            project_key="payments",
            workspace_key="prod",
            display_name="Production",
        )
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
            score=30,
            severity="low",
            recommendation="go",
            top_risk="plan.json changed aws_security_group.main.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: review the deployment.",
            explanation="The deployment was analyzed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            project_id=project.id,
            workspace_id=workspace.id,
            audit_context={"source_interface": "api"},
        )

        provenance = report["submission_manifest"]["provenance"]
        self.assertEqual(provenance["project_id"], project.id)
        self.assertEqual(provenance["project_key"], "payments")
        self.assertEqual(provenance["workspace_id"], workspace.id)
        self.assertEqual(provenance["workspace_key"], "prod")
        item_provenance = report["submission_manifest"]["items"][0]["provenance"]
        self.assertEqual(item_provenance["project_key"], "payments")
        self.assertEqual(item_provenance["workspace_key"], "prod")

    def test_persist_manifest_warns_when_submitted_artifact_context_is_inferred(
        self,
    ) -> None:
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
                ),
                ParsedFileResult(
                    file_name="notes.txt",
                    tool="unsupported",
                    status="skipped",
                    issue=ParseIssue(
                        file_name="notes.txt",
                        tool="unsupported",
                        message="Unsupported or unrecognized file excluded from parsing.",
                    ),
                ),
            ]
        )
        assessment = RiskAssessment(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="plan.json changed aws_security_group.main.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: review the deployment.",
            explanation="The deployment was analyzed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
        )

        self.assertIn(
            "Submission manifest metadata was inferred from available analysis artifacts "
            "because submitted artifact context was unavailable; excluded or sensitive "
            "submissions may be missing.",
            report["warnings"],
        )
        by_name = {
            item["name"]: item for item in report["submission_manifest"]["items"]
        }
        self.assertEqual(by_name["notes.txt"]["status"], "excluded")
        self.assertEqual(
            by_name["notes.txt"]["message"],
            "Unsupported or unrecognized file excluded from parsing.",
        )
        self.assertTrue(by_name["notes.txt"]["partial"])

    def test_fetch_report_degrades_on_malformed_submission_manifest_json(self) -> None:
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
                ),
                ParsedFileResult(
                    file_name="broken.tf",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="broken.tf",
                        tool="terraform",
                        message="Unexpected token",
                    ),
                ),
            ]
        )
        assessment = RiskAssessment(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="plan.json changed aws_security_group.main.",
            contributors=[],
            interaction_risks=[],
            partial_context=True,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: review the partial analysis.",
            explanation="The deployment was partially analyzed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            submitted_artifacts=[
                ("plan.json", b'{"resource_changes": []}'),
                ("broken.tf", b"resource {"),
                (".env", b"SECRET=1"),
                ("notes.txt", b"hello"),
            ],
            audit_context={"source_interface": "api"},
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id = ?",
                ("{not-valid-json", report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertIsNone(fetched["submission_manifest"])
        self.assertIn(
            "Submission manifest metadata was unavailable because persisted JSON was malformed.",
            fetched["warnings"],
        )
        fallback_by_name = {
            item["name"]: item for item in fetched["submission_manifest_fallback"]
        }
        self.assertEqual(fallback_by_name["plan.json"]["status"], "accepted")
        self.assertEqual(fallback_by_name["broken.tf"]["status"], "failed")
        self.assertEqual(fallback_by_name[".env"]["status"], "sensitive")
        self.assertEqual(fallback_by_name["notes.txt"]["status"], "excluded")

    def test_fetch_report_degrades_on_wrong_shape_submission_manifest_json(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id = ?",
                ("[]", report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertIsNone(fetched["submission_manifest"])
        self.assertIn(
            "Submission manifest metadata was unavailable because persisted JSON had an unexpected shape.",
            fetched["warnings"],
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

    def test_fetch_shared_report_comparison_redacts_manifest_only_failed_files(
        self,
    ) -> None:
        parse_files = [
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
                        summary="Security group changed.",
                    )
                ],
            ),
            ParsedFileResult(
                file_name="prod/network/broken.tf",
                tool="terraform",
                status="failed",
                issue=ParseIssue(
                    file_name="prod/network/broken.tf",
                    tool="terraform",
                    message="Could not parse prod/network/broken.tf",
                ),
            ),
        ]
        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="prod/network/broken.tf was excluded from analysis.",
            findings=[
                Finding(
                    finding_id="finding-partial",
                    analysis_id=0,
                    title="MEDIUM: prod/network/broken.tf partial coverage",
                    description="prod/network/broken.tf could not be parsed.",
                    severity="medium",
                    category="parser/coverage",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-partial"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-partial",
                    analysis_id=0,
                    finding_id="pending:partial",
                    source_type="artifact",
                    source_ref="terraform://prod/network/broken.tf",
                    summary="prod/network/broken.tf failed parsing.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-partial"],
                )
            ],
            parse_files=parse_files,
        )
        current = self._persist_comparison_report(
            score=55,
            severity="high",
            recommendation="caution",
            top_risk="prod/network/broken.tf still needs parser review.",
            findings=[],
            evidence_items=[],
            parse_files=parse_files,
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
        self.assertNotIn("prod/network/broken.tf", serialized)
        self.assertNotIn("broken.tf", serialized)
        self.assertIn("Artifact 2", serialized)

    def test_previous_comparable_report_requires_matching_manifest_coverage(
        self,
    ) -> None:
        def parse_files(failed_name: str):
            return [
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
                            summary="Security group changed.",
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name=failed_name,
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name=failed_name,
                        tool="terraform",
                        message=f"Could not parse {failed_name}",
                    ),
                ),
            ]

        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="prod/network/broken-a.tf was excluded.",
            findings=[],
            evidence_items=[],
            parse_files=parse_files("prod/network/broken-a.tf"),
        )
        current = self._persist_comparison_report(
            score=55,
            severity="high",
            recommendation="caution",
            top_risk="prod/network/broken-b.tf was excluded.",
            findings=[],
            evidence_items=[],
            parse_files=parse_files("prod/network/broken-b.tf"),
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNone(comparison)

    def test_previous_comparable_report_matches_equivalent_legacy_report(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="prod/network/plan.json was reviewed.",
            findings=[],
            evidence_items=[],
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = '{}' WHERE id = ?",
                (previous["id"],),
            )
        current = self._persist_comparison_report(
            score=55,
            severity="high",
            recommendation="caution",
            top_risk="prod/network/plan.json still needs review.",
            findings=[],
            evidence_items=[],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(
            comparison["previous_report"]["id"],
            previous["id"],
        )

    def test_previous_comparable_report_requires_matching_artifact_tool(
        self,
    ) -> None:
        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="plan.json was parsed as Terraform.",
            findings=[],
            evidence_items=[],
            parse_files=[
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
                            summary="Terraform security group changed.",
                        )
                    ],
                )
            ],
        )
        current = self._persist_comparison_report(
            score=55,
            severity="high",
            recommendation="caution",
            top_risk="plan.json was parsed as CloudFormation.",
            findings=[],
            evidence_items=[],
            parse_files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="cloudformation",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="cloudformation",
                            resource_id="AWS::EC2::SecurityGroup.Main",
                            action="modify",
                            summary="CloudFormation security group changed.",
                        )
                    ],
                )
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNone(comparison)

    def test_legacy_previous_comparable_report_requires_inferred_tool_match(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="plan.json was parsed as Terraform.",
            findings=[],
            evidence_items=[],
            parse_files=[
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
                            summary="Terraform security group changed.",
                        )
                    ],
                )
            ],
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = '{}' WHERE id = ?",
                (previous["id"],),
            )
        current = self._persist_comparison_report(
            score=55,
            severity="high",
            recommendation="caution",
            top_risk="plan.json was parsed as CloudFormation.",
            findings=[],
            evidence_items=[],
            parse_files=[
                ParsedFileResult(
                    file_name="plan.json",
                    tool="cloudformation",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="plan.json",
                            tool="cloudformation",
                            resource_id="AWS::EC2::SecurityGroup.Main",
                            action="modify",
                            summary="CloudFormation security group changed.",
                        )
                    ],
                )
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNone(comparison)

    def test_malformed_manifest_reports_are_excluded_from_auto_comparison(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="prod/network/broken-a.tf was excluded.",
            findings=[],
            evidence_items=[],
            parse_files=[
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
                            summary="Terraform security group changed.",
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name="prod/network/broken-a.tf",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="prod/network/broken-a.tf",
                        tool="terraform",
                        message="Could not parse prod/network/broken-a.tf",
                    ),
                ),
            ],
        )
        current = self._persist_comparison_report(
            score=55,
            severity="high",
            recommendation="caution",
            top_risk="prod/network/broken-b.tf was excluded.",
            findings=[],
            evidence_items=[],
            parse_files=[
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
                            summary="Terraform security group changed.",
                        )
                    ],
                ),
                ParsedFileResult(
                    file_name="prod/network/broken-b.tf",
                    tool="terraform",
                    status="failed",
                    issue=ParseIssue(
                        file_name="prod/network/broken-b.tf",
                        tool="terraform",
                        message="Could not parse prod/network/broken-b.tf",
                    ),
                ),
            ],
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id IN (?, ?)",
                ("{not-valid-json", previous["id"], current["id"]),
            )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNone(comparison)

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

    def test_persist_analysis_report_stores_and_filters_workspace_scope(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
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

        prod_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments-prod.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=72,
                severity="high",
                recommendation="no-go",
                top_risk="Production payment ingress widened.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="NO-GO: production payment ingress widened.",
                explanation="Workspace-scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            workspace_id=prod.id,
            audit_context={"source_interface": "api"},
        )
        report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments-staging.json",
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
                top_risk="Staging payment ingress changed.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: staging payment ingress changed.",
                explanation="Workspace-scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            workspace_id=staging.id,
            audit_context={"source_interface": "api"},
        )

        scoped_page = report_service_module.fetch_filtered_analysis_history_page(
            project_key=project.project_key,
            workspace_key=prod.workspace_key,
        )
        wrong_workspace = report_service_module.fetch_analysis_report(
            prod_report["id"],
            project_key=project.project_key,
            workspace_key=staging.workspace_key,
        )

        self.assertEqual(scoped_page["total_count"], 1)
        self.assertEqual(scoped_page["items"][0]["id"], prod_report["id"])
        self.assertEqual(scoped_page["items"][0]["workspace"]["workspace_key"], "prod")
        self.assertIsNone(wrong_workspace)

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

    def test_previous_scan_diffs_use_immediately_previous_comparable_report(
        self,
    ) -> None:
        first = self._persist_comparison_report(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="First review",
            findings=[],
            evidence_items=[],
        )
        second = self._persist_comparison_report(
            score=50,
            severity="medium",
            recommendation="caution",
            top_risk="Second review",
            findings=[],
            evidence_items=[],
        )
        third = self._persist_comparison_report(
            score=80,
            severity="high",
            recommendation="no-go",
            top_risk="Third review",
            findings=[],
            evidence_items=[],
        )

        history = report_service_module.fetch_filtered_analysis_history_page()

        by_id = {item["id"]: item for item in history["items"]}
        self.assertEqual(
            by_id[int(third["id"])]["previous_scan_diff"]["previous_report_id"],
            second["id"],
        )
        self.assertEqual(
            by_id[int(second["id"])]["previous_scan_diff"]["previous_report_id"],
            first["id"],
        )

    def test_previous_scan_diffs_compute_history_signature_once_per_report(
        self,
    ) -> None:
        reports = [
            self._persist_comparison_report(
                score=30 + index,
                severity="low",
                recommendation="go",
                top_risk=f"Review {index}",
                findings=[],
                evidence_items=[],
            )
            for index in range(5)
        ]
        original_history_signature = report_service_module._history_signature
        call_count = 0

        def counting_history_signature(report):
            nonlocal call_count
            call_count += 1
            return original_history_signature(report)

        with (
            patch.object(
                report_service_module,
                "_history_signature",
                side_effect=counting_history_signature,
            ),
            patch.object(
                report_service_module,
                "_comparison_signatures_match",
                side_effect=AssertionError(
                    "history annotation must use exact signature index"
                ),
            ),
        ):
            history = report_service_module.fetch_filtered_analysis_history_page()

        self.assertEqual(history["total_count"], len(reports))
        self.assertEqual(call_count, len(reports))


if __name__ == "__main__":
    unittest.main()
