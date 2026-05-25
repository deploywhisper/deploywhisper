"""Tests for report persistence and retrieval."""

from __future__ import annotations

import json
import math
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
import services.incident_service as incident_service_module
import services.report_service as report_service_module
import services.settings_service as settings_service_module
from analysis.blast_radius import BlastRadiusResult, ImpactNode
from analysis.incident_matcher import IncidentMatch
from analysis.rollback_planner import RollbackPlan, RollbackStep
from analysis.risk_scorer import RiskAssessment, RiskContributor
from evidence.models import ContextCompleteness, EvidenceItem, Finding
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
        reload(incident_service_module)
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

        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                **{
                    **report_kwargs,
                    "recommendation": "go",
                    "top_risk": "Medium security group review.",
                    "narrative_opening": "GO: medium security group review.",
                    "narrative_explanation": "Medium severity remains advisory.",
                },
                findings_payload=[],
                evidence_payload=[],
            )
            self.assertEqual(report.severity, "medium")
            self.assertEqual(report.recommendation, "go")

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

        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(ValueError, "Risk confidence"):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    risk_confidence=1.5,
                    findings_payload=[],
                    evidence_payload=[],
                )

        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(ValueError, "missing evidence item ev-missing"):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[
                        {
                            **finding,
                            "evidence_refs": ["ev-missing"],
                        }
                    ],
                    evidence_payload=[],
                )

        heuristic_evidence = {
            "evidence_id": "ev-heuristic",
            "analysis_id": 0,
            "finding_id": "finding-high",
            "source_type": "artifact",
            "source_ref": "terraform://plan.json#aws_security_group.main?action=modify",
            "summary": "Security group exposure",
            "severity_hint": "high",
            "deterministic": False,
            "determinism_level": "heuristic",
            "confidence": 0.7,
            "related_change_ids": ["chg-001"],
        }
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "without linked deterministic evidence",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-high",
                            "severity": "high",
                            "evidence_refs": ["ev-heuristic"],
                        }
                    ],
                    evidence_payload=[heuristic_evidence],
                )
        string_false_evidence = {
            **heuristic_evidence,
            "evidence_id": "ev-string-false",
            "deterministic": "false",
            "determinism_level": "deterministic",
        }
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "without linked deterministic evidence",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-string-false",
                            "severity": "high",
                            "evidence_refs": ["ev-string-false"],
                        }
                    ],
                    evidence_payload=[string_false_evidence],
                )
        string_true_evidence = {
            **heuristic_evidence,
            "evidence_id": "ev-string-true",
            "deterministic": "true",
            "determinism_level": "deterministic",
        }
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "without linked deterministic evidence",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-string-true",
                            "severity": "high",
                            "evidence_refs": ["ev-string-true"],
                        }
                    ],
                    evidence_payload=[string_true_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "without a linked deterministic severe finding",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 72,
                        "severity": "high",
                        "recommendation": "no-go",
                        "top_risk": "Unsupported severe report.",
                    },
                    findings_payload=[],
                    evidence_payload=[],
                )
        for unnormalized_severity in ("HIGH", " high "):
            with self.subTest(unnormalized_severity=unnormalized_severity):
                with database_module.SessionLocal() as session:
                    with self.assertRaisesRegex(
                        ValueError,
                        "without a linked deterministic severe finding",
                    ):
                        analysis_reports_repository_module.create_analysis_report(
                            session,
                            **{
                                **report_kwargs,
                                "risk_score": 72,
                                "severity": unnormalized_severity,
                                "recommendation": "no-go",
                                "top_risk": "Unsupported severe report.",
                            },
                            findings_payload=[],
                            evidence_payload=[],
                        )

        evidence = {
            "evidence_id": "ev-001",
            "analysis_id": 0,
            "finding_id": "finding-invalid",
            "source_type": "artifact",
            "source_ref": "terraform://plan.json#aws_security_group.main?action=modify",
            "summary": "Security group exposure",
            "severity_hint": "medium",
            "deterministic": True,
            "confidence": 1.0,
            "related_change_ids": ["chg-001"],
        }
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "without a linked deterministic severe finding",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 72,
                        "severity": "high",
                        "recommendation": "no-go",
                        "top_risk": "Unsupported severe report.",
                    },
                    findings_payload=[
                        {
                            **finding,
                            "evidence_refs": ["ev-001"],
                        }
                    ],
                    evidence_payload=[evidence],
                )
        string_false_medium_evidence = {
            **evidence,
            "evidence_id": "ev-string-false-medium",
            "deterministic": "false",
            "determinism_level": "deterministic",
        }
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                **report_kwargs,
                findings_payload=[
                    {
                        **finding,
                        "finding_id": "finding-string-false-medium",
                        "evidence_refs": ["ev-string-false-medium"],
                    }
                ],
                evidence_payload=[string_false_medium_evidence],
            )
            stored_evidence = report.findings[0].evidence_items[0]
            self.assertFalse(stored_evidence.deterministic)
            self.assertEqual(stored_evidence.determinism_level, "inferred")
        string_true_medium_evidence = {
            **evidence,
            "evidence_id": "ev-string-true-medium",
            "deterministic": "true",
            "determinism_level": "deterministic",
        }
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                **report_kwargs,
                findings_payload=[
                    {
                        **finding,
                        "finding_id": "finding-string-true-medium",
                        "evidence_refs": ["ev-string-true-medium"],
                    }
                ],
                evidence_payload=[string_true_medium_evidence],
            )
            stored_evidence = report.findings[0].evidence_items[0]
            self.assertFalse(stored_evidence.deterministic)
            self.assertEqual(stored_evidence.determinism_level, "inferred")
        missing_deterministic_evidence = {
            key: value for key, value in evidence.items() if key != "deterministic"
        }
        with database_module.SessionLocal() as session:
            with self.assertRaises(ValidationError):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-missing-deterministic",
                            "evidence_refs": ["ev-001"],
                        }
                    ],
                    evidence_payload=[missing_deterministic_evidence],
                )
        high_evidence = {
            **evidence,
            "evidence_id": "ev-high",
            "finding_id": "finding-supported-high",
            "severity_hint": "high",
        }
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "Top-risk contributor ev-missing does not reference persisted evidence",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 72,
                        "severity": "high",
                        "recommendation": "no-go",
                        "top_risk": "HIGH: supported severe report.",
                        "narrative_opening": "NO-GO: supported severe report.",
                        "narrative_explanation": "Deterministic severe evidence supports the report.",
                        "top_risk_contributors_json": '["ev-missing"]',
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "evidence_refs": ["ev-high"],
                        }
                    ],
                    evidence_payload=[high_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "High/critical reports must persist top-risk contributor evidence IDs",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 72,
                        "severity": "high",
                        "recommendation": "no-go",
                        "top_risk": "HIGH: supported severe report.",
                        "narrative_opening": "NO-GO: supported severe report.",
                        "narrative_explanation": "Deterministic severe evidence supports the report.",
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "evidence_refs": ["ev-high"],
                        }
                    ],
                    evidence_payload=[high_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "Top-risk contributors must belong to one persisted finding",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 72,
                        "severity": "high",
                        "recommendation": "no-go",
                        "top_risk": "HIGH: supported severe report.",
                        "narrative_opening": "NO-GO: supported severe report.",
                        "narrative_explanation": "Deterministic severe evidence supports the report.",
                        "top_risk_contributors_json": '["ev-high", "ev-medium-cross"]',
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "evidence_refs": ["ev-high"],
                        },
                        {
                            **finding,
                            "finding_id": "finding-medium-cross",
                            "severity": "medium",
                            "evidence_refs": ["ev-medium-cross"],
                        },
                    ],
                    evidence_payload=[
                        high_evidence,
                        {
                            **evidence,
                            "evidence_id": "ev-medium-cross",
                            "finding_id": "finding-medium-cross",
                        },
                    ],
                )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                **{
                    **report_kwargs,
                    "top_risk": "Shared evidence ownership is canonical.",
                    "narrative_opening": "CAUTION: shared evidence ownership.",
                    "narrative_explanation": (
                        "The evidence owner is explicit even when references are shared."
                    ),
                },
                findings_payload=[
                    {
                        **finding,
                        "finding_id": "finding-shared-one",
                        "evidence_refs": ["ev-shared"],
                    },
                    {
                        **finding,
                        "finding_id": "finding-shared-two",
                        "evidence_refs": ["ev-shared"],
                    },
                ],
                evidence_payload=[
                    {
                        **evidence,
                        "evidence_id": "ev-shared",
                        "finding_id": "finding-shared-one",
                    }
                ],
            )
            self.assertEqual(
                [json.loads(item.evidence_refs_json) for item in report.findings],
                [["ev-shared"], ["ev-shared"]],
            )
            self.assertEqual(
                report.findings[0].evidence_items[0].evidence_id,
                "ev-shared",
            )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "Evidence item ev-shared has ambiguous finding ownership",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "top_risk": "Shared evidence ownership is ambiguous.",
                        "narrative_opening": "CAUTION: shared evidence ownership.",
                        "narrative_explanation": (
                            "Each shared evidence item needs a canonical owner."
                        ),
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-shared-one",
                            "evidence_refs": ["ev-shared"],
                        },
                        {
                            **finding,
                            "finding_id": "finding-shared-two",
                            "evidence_refs": ["ev-shared"],
                        },
                    ],
                    evidence_payload=[
                        {
                            **evidence,
                            "evidence_id": "ev-shared",
                            "finding_id": "finding-unreferenced-owner",
                        }
                    ],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "without a linked deterministic severe finding",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 92,
                        "severity": "critical",
                        "recommendation": "no-go",
                        "top_risk": "Unsupported critical report.",
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "evidence_refs": ["ev-high"],
                        }
                    ],
                    evidence_payload=[high_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "contradicts linked deterministic evidence",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 72,
                        "severity": "high",
                        "recommendation": "no-go",
                        "top_risk": "Supported severe report.",
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "deterministic": False,
                            "evidence_classification": "model_inferred",
                            "evidence_refs": ["ev-high"],
                        }
                    ],
                    evidence_payload=[high_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "inconsistent verdict metadata",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 42,
                        "severity": "high",
                        "recommendation": "go",
                        "top_risk": "Supported severe report.",
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "evidence_refs": ["ev-high"],
                        }
                    ],
                    evidence_payload=[high_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "understates linked deterministic severe finding",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 42,
                        "severity": "medium",
                        "recommendation": "caution",
                        "top_risk": "Underclaimed supported severe report.",
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "evidence_refs": ["ev-high"],
                        }
                    ],
                    evidence_payload=[high_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "Report verdict text contradicts severity metadata",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "top_risk": "CRITICAL: stale severe copy.",
                        "narrative_opening": "NO-GO: stale severe copy.",
                        "narrative_explanation": "Unsupported stale severe copy.",
                    },
                    findings_payload=[],
                    evidence_payload=[],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "Report verdict text contradicts severity metadata",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 72,
                        "severity": "high",
                        "recommendation": "no-go",
                        "top_risk": "MEDIUM: stale non-severe copy.",
                        "narrative_opening": "CAUTION: stale non-severe copy.",
                        "narrative_explanation": "Supported severe report.",
                    },
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-supported-high",
                            "severity": "high",
                            "evidence_refs": ["ev-high"],
                        }
                    ],
                    evidence_payload=[high_evidence],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "inconsistent verdict metadata",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "recommendation": "no-go",
                        "top_risk": "NO-GO: stale non-severe recommendation.",
                        "narrative_opening": "NO-GO: stale non-severe recommendation.",
                        "narrative_explanation": "No severe deterministic finding.",
                    },
                    findings_payload=[],
                    evidence_payload=[],
                )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "Report verdict text contradicts severity metadata",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "top_risk": "GO: stale go copy.",
                        "narrative_opening": "GO: stale go copy.",
                        "narrative_explanation": "Review is still required.",
                    },
                    findings_payload=[],
                    evidence_payload=[],
                )
        for stale_verdict_text in (
            "NO-GO deployment review.",
            "CRITICAL database exposure remains.",
        ):
            with self.subTest(stale_verdict_text=stale_verdict_text):
                with database_module.SessionLocal() as session:
                    with self.assertRaisesRegex(
                        ValueError,
                        "Report verdict text contradicts severity metadata",
                    ):
                        analysis_reports_repository_module.create_analysis_report(
                            session,
                            **{
                                **report_kwargs,
                                "top_risk": stale_verdict_text,
                            },
                            findings_payload=[],
                            evidence_payload=[],
                        )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "inconsistent verdict metadata",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **{
                        **report_kwargs,
                        "risk_score": 95,
                        "top_risk": "Review remains cautionary.",
                    },
                    findings_payload=[],
                    evidence_payload=[],
                )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                **{
                    **report_kwargs,
                    "top_risk": "High availability rollout requires review.",
                    "narrative_opening": "Go live review is pending.",
                    "narrative_explanation": (
                        "Critical path implementation detail remains under review."
                    ),
                },
                findings_payload=[],
                evidence_payload=[],
            )
            self.assertEqual(
                report.top_risk,
                "High availability rollout requires review.",
            )
            self.assertEqual(report.narrative_opening, "Go live review is pending.")
            self.assertEqual(
                report.narrative_explanation,
                "Critical path implementation detail remains under review.",
            )
        external_evidence = {
            "evidence_id": "ev-external-high",
            "analysis_id": 0,
            "finding_id": "finding-external-high",
            "source_type": "external_scanner",
            "source_ref": "scanner://sast.json#rule.high?action=flag",
            "summary": "External scanner flagged a high risk.",
            "severity_hint": "high",
            "deterministic": True,
            "confidence": 1.0,
            "related_change_ids": ["chg-001"],
        }
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                **{
                    **report_kwargs,
                    "risk_score": 72,
                    "severity": "high",
                    "recommendation": "no-go",
                    "top_risk": "HIGH: External scanner high risk.",
                    "narrative_opening": "NO-GO: External scanner high risk.",
                    "narrative_explanation": "External scanner evidence is deterministic.",
                    "top_risk_contributors_json": '["ev-external-high"]',
                },
                findings_payload=[
                    {
                        **finding,
                        "finding_id": "finding-external-high",
                        "title": "HIGH: External scanner high risk.",
                        "severity": "high",
                        "deterministic": True,
                        "evidence_classification": "external",
                        "evidence_refs": ["ev-external-high"],
                    }
                ],
                evidence_payload=[external_evidence],
            )
            self.assertEqual(
                report.findings[0].evidence_classification,
                "external",
            )
        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "repeats evidence refs",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[
                        {
                            **finding,
                            "evidence_refs": ["ev-001", "ev-001"],
                        }
                    ],
                    evidence_payload=[evidence],
                )

        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "not referenced by any persisted finding",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[finding],
                    evidence_payload=[evidence],
                )

        with database_module.SessionLocal() as session:
            with self.assertRaisesRegex(
                ValueError,
                "Evidence item ev-001 has ambiguous finding ownership",
            ):
                analysis_reports_repository_module.create_analysis_report(
                    session,
                    **report_kwargs,
                    findings_payload=[
                        {
                            **finding,
                            "finding_id": "finding-one",
                            "evidence_refs": ["ev-001"],
                        },
                        {
                            **finding,
                            "finding_id": "finding-two",
                            "evidence_refs": ["ev-001"],
                        },
                    ],
                    evidence_payload=[evidence],
                )

    def test_scope_report_entities_downgrades_stripped_evidence_classification(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="unresolved evidence",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-stale",
                analysis_id=0,
                title="MEDIUM: unresolved evidence",
                description="Finding references evidence not present in this report.",
                severity="medium",
                category="cross-tool interaction",
                deterministic=True,
                confidence=0.8,
                uncertainty_note=None,
                evidence_classification="deterministic",
                evidence_refs=["ev-missing"],
                skill_id=None,
            )
        ]

        _, scoped_findings, _ = report_service_module._scope_report_entities(
            assessment,
            findings,
            [],
        )

        self.assertIsNotNone(scoped_findings)
        assert scoped_findings is not None
        self.assertEqual(scoped_findings[0].evidence_refs, [])
        self.assertEqual(
            scoped_findings[0].evidence_classification,
            "model_inferred",
        )

    def test_scope_report_entities_preserves_shared_evidence_classification(
        self,
    ) -> None:
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="shared evidence",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-shared-one",
                analysis_id=0,
                title="MEDIUM: shared evidence one",
                description="First finding shares deterministic evidence.",
                severity="medium",
                category="cross-tool interaction",
                deterministic=False,
                confidence=0.8,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=["ev-shared"],
                skill_id=None,
            ),
            Finding(
                finding_id="finding-shared-two",
                analysis_id=0,
                title="MEDIUM: shared evidence two",
                description="Second finding shares deterministic evidence.",
                severity="medium",
                category="cross-tool interaction",
                deterministic=False,
                confidence=0.8,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=["ev-shared"],
                skill_id=None,
            ),
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-shared",
                analysis_id=0,
                finding_id="finding-shared-one",
                source_type="artifact",
                source_ref="terraform://plan.json#shared",
                summary="Shared deterministic support.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
                source_kind="artifact",
                determinism_level="deterministic",
            )
        ]

        _, scoped_findings, scoped_evidence_items = (
            report_service_module._scope_report_entities(
                assessment,
                findings,
                evidence_items,
            )
        )

        self.assertIsNotNone(scoped_findings)
        self.assertIsNotNone(scoped_evidence_items)
        assert scoped_findings is not None
        assert scoped_evidence_items is not None
        shared_scoped_ref = scoped_evidence_items[0].evidence_id
        self.assertEqual(
            [finding.evidence_refs for finding in scoped_findings],
            [[shared_scoped_ref], [shared_scoped_ref]],
        )
        self.assertEqual(
            [finding.evidence_classification for finding in scoped_findings],
            ["deterministic", "deterministic"],
        )

    def test_persist_analysis_report_preserves_shared_evidence_references(
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
            top_risk="Two findings share one deterministic evidence item.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: shared evidence review.",
            explanation="One artifact supports multiple related findings.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-shared-one",
                    analysis_id=0,
                    title="MEDIUM: shared evidence one",
                    description="First finding shares deterministic evidence.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.8,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=["ev-shared"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-shared-two",
                    analysis_id=0,
                    title="MEDIUM: shared evidence two",
                    description="Second finding shares deterministic evidence.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.8,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=["ev-shared"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-shared",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref="terraform://plan.json#aws_security_group.main",
                    summary="Shared deterministic support.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    source_kind="artifact",
                    determinism_level="deterministic",
                )
            ],
        )

        persisted_evidence_id = report["evidence_items"][0]["evidence_id"]
        self.assertEqual(
            [finding["evidence_refs"] for finding in report["findings"]],
            [[persisted_evidence_id], [persisted_evidence_id]],
        )
        self.assertEqual(
            report["evidence_items"][0]["finding_id"],
            report["findings"][0]["finding_id"],
        )

    def test_persist_analysis_report_prefers_severe_owner_for_generated_shared_evidence(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="HIGH: shared deterministic evidence supports severe ingress risk.",
            top_risk_contributors=["ev-shared"],
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: shared evidence supports severe ingress risk.",
            explanation="The same artifact supports related medium and high findings.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-shared-medium",
                    analysis_id=0,
                    title="MEDIUM: shared evidence context",
                    description="Medium finding appears first and shares evidence.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.8,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=["ev-shared"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-shared-high",
                    analysis_id=0,
                    title="HIGH: shared evidence severe risk",
                    description="High finding also links the deterministic evidence.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.9,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=["ev-shared"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-shared",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref="terraform://plan.json#aws_security_group.main",
                    summary="Shared deterministic severe support.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    source_kind="artifact",
                    determinism_level="deterministic",
                )
            ],
        )

        high_finding = next(
            finding for finding in report["findings"] if finding["severity"] == "high"
        )
        persisted_evidence_id = report["evidence_items"][0]["evidence_id"]
        self.assertEqual(
            report["evidence_items"][0]["finding_id"], high_finding["finding_id"]
        )
        self.assertEqual(report["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(
            [finding["evidence_refs"] for finding in report["findings"]],
            [[persisted_evidence_id], [persisted_evidence_id]],
        )

    def test_report_finding_maps_resolves_shared_evidence_refs(self) -> None:
        _, evidence_by_finding_id = report_service_module._report_finding_maps(
            {
                "findings": [
                    {
                        "finding_id": "finding-one",
                        "title": "MEDIUM: shared one",
                        "description": "First finding shares evidence.",
                        "category": "cross-tool interaction",
                        "evidence_refs": ["ev-shared"],
                    },
                    {
                        "finding_id": "finding-two",
                        "title": "MEDIUM: shared two",
                        "description": "Second finding shares evidence.",
                        "category": "cross-tool interaction",
                        "evidence_refs": ["ev-shared"],
                    },
                ],
                "evidence_items": [
                    {
                        "evidence_id": "ev-shared",
                        "finding_id": "finding-one",
                        "source_ref": "terraform://plan.json#shared",
                    }
                ],
            }
        )

        self.assertEqual(
            [item["evidence_id"] for item in evidence_by_finding_id["finding-one"]],
            ["ev-shared"],
        )
        self.assertEqual(
            [item["evidence_id"] for item in evidence_by_finding_id["finding-two"]],
            ["ev-shared"],
        )

    def test_persist_analysis_report_repairs_stale_assessment_evidence_links(
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
            top_risk="Terraform changed a security group.",
            top_risk_contributors=["ev-stale"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-stale",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=18,
                    summary="Terraform changed a security group.",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    severity="medium",
                    reasoning="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review deterministic evidence.",
            explanation="The report has a stale assessment evidence ID.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-unlinked",
                analysis_id=0,
                title="MEDIUM: aws_security_group.main",
                description="Terraform changed a security group.",
                severity="medium",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=[],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-real",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref=(
                    "terraform://plan.json#aws_security_group.main?action=modify"
                ),
                summary="Terraform changed a security group.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
            )
        ]

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=findings,
            evidence_items=evidence_items,
        )

        persisted_evidence_id = report["evidence_items"][0]["evidence_id"]
        self.assertEqual(
            report["findings"][0]["evidence_refs"], [persisted_evidence_id]
        )
        self.assertEqual(
            report["findings"][0]["evidence_classification"],
            "deterministic",
        )
        self.assertEqual(
            report["contributors"][0]["evidence_id"], persisted_evidence_id
        )
        self.assertEqual(report["top_risk_contributors"], [persisted_evidence_id])

    def test_persist_analysis_report_downgrades_severe_finding_without_deterministic_evidence(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Inferred severe risk.",
            top_risk_contributors=["ev-stale"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-stale",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=28,
                    summary="Stale unsupported severe contributor.",
                    severity="high",
                    reasoning="Unsupported severe claim.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: inferred severe risk.",
            explanation="The narrative is not deterministic evidence.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-inferred-high",
                    analysis_id=0,
                    title="HIGH: inferred production exposure",
                    description="Model-inferred exposure without deterministic support.",
                    explanation="Critical ingress exposure requires immediate action.",
                    guidance=["Require human review before applying the change."],
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.92,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            evidence_items=[],
        )

        self.assertEqual(report["findings"][0]["severity"], "medium")
        self.assertEqual(
            report["findings"][0]["title"], "MEDIUM: inferred production exposure"
        )
        self.assertFalse(report["findings"][0]["deterministic"])
        self.assertLessEqual(report["findings"][0]["confidence"], 0.85)
        self.assertEqual(
            report["findings"][0]["explanation"],
            "Evidence Law downgraded this finding to medium because it does not link to deterministic evidence.",
        )
        self.assertEqual(
            report["findings"][0]["guidance"],
            [
                "Review the available linked evidence before deployment.",
                "Add deterministic evidence before treating this finding as severe.",
            ],
        )
        self.assertNotIn("Critical ingress", report["findings"][0]["explanation"])
        self.assertNotIn(
            "Require human review",
            " ".join(report["findings"][0]["guidance"]),
        )
        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "caution")
        self.assertLessEqual(report["risk_score"], 69)
        self.assertEqual(report["top_risk_contributors"], [])
        self.assertEqual(report["contributors"], [])
        self.assertNotIn("NO-GO", report["narrative_opening"])
        self.assertIn("CAUTION", report["narrative_opening"])
        self.assertIn("Evidence Law downgraded", report["narrative_explanation"])
        self.assertIn("Evidence Law downgraded", " ".join(report["warnings"]))

    def test_persist_analysis_report_downgrades_severe_report_without_findings(
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
            score=91,
            severity="medium",
            recommendation="caution",
            top_risk="Report-level severe risk without evidence.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: unsupported report-level risk.",
            explanation="Unsupported report-level risk.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
        )

        self.assertEqual(report["findings"], [])
        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "caution")
        self.assertLessEqual(report["risk_score"], 69)
        self.assertNotIn("NO-GO", report["narrative_opening"])
        self.assertIn("CAUTION", report["narrative_opening"])
        self.assertIn("unsupported severe report verdict", report["top_risk"])
        self.assertIn("Evidence Law downgraded", " ".join(report["warnings"]))

    def test_persist_analysis_report_repoints_partial_downgrade_summary_to_supported_severe_finding(
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
            score=82,
            severity="high",
            recommendation="no-go",
            top_risk="HIGH: unsupported inferred exposure.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: unsupported inferred exposure.",
            explanation="Unsupported inferred exposure is the severe issue.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-unsupported",
                    analysis_id=0,
                    title="HIGH: unsupported inferred exposure",
                    description="Unsupported inferred exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.94,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-supported",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        severities_by_title = {
            finding["title"]: finding["severity"] for finding in report["findings"]
        }
        self.assertEqual(
            severities_by_title["MEDIUM: unsupported inferred exposure"],
            "medium",
        )
        self.assertEqual(severities_by_title["HIGH: aws_security_group.main"], "high")
        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["recommendation"], "no-go")
        self.assertIn("aws_security_group.main", report["top_risk"])
        self.assertNotIn("unsupported inferred exposure", report["top_risk"])
        self.assertIn("deterministic severe risk remains", report["narrative_opening"])
        self.assertIn("Evidence Law downgraded", report["narrative_explanation"])

    def test_persist_analysis_report_clears_stale_severe_top_risk_on_medium_assessment(
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
            score=52,
            severity="medium",
            recommendation="caution",
            top_risk="CRITICAL: unsupported no-go claim.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: unsupported no-go claim.",
            explanation="CRITICAL unsupported no-go claim.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-unsupported-critical",
                    analysis_id=0,
                    title="CRITICAL: unsupported no-go claim",
                    description="Unsupported critical claim without deterministic evidence.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.96,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            evidence_items=[],
        )

        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "caution")
        self.assertIn("Evidence Law downgraded", report["top_risk"])
        self.assertNotIn("CRITICAL", report["top_risk"])
        self.assertNotIn("NO-GO", report["narrative_opening"])
        self.assertNotIn("CRITICAL", report["narrative_explanation"])

    def test_persist_analysis_report_sanitizes_stale_severe_copy_without_findings(
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
            score=52,
            severity="medium",
            recommendation="caution",
            top_risk="CRITICAL: stale no-go copy.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: stale no-go copy.",
            explanation="CRITICAL stale no-go copy.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[],
            evidence_items=[],
        )

        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "caution")
        self.assertIn("MEDIUM", report["top_risk"])
        self.assertNotIn("CRITICAL", report["top_risk"])
        self.assertIn("CAUTION", report["narrative_opening"])
        self.assertNotIn("NO-GO", report["narrative_opening"])
        self.assertNotIn("CRITICAL", report["narrative_explanation"])
        self.assertIn("Evidence Law", " ".join(report["warnings"]))

    def test_persist_analysis_report_reconciles_non_severe_recommendation_text(
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
            score=95,
            severity="medium",
            recommendation="no-go",
            top_risk="NO-GO: stale recommendation copy.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: stale recommendation copy.",
            explanation="NO-GO stale recommendation copy.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[],
            evidence_items=[],
        )

        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "caution")
        self.assertEqual(report["risk_score"], 69)
        self.assertIn("MEDIUM", report["top_risk"])
        self.assertNotIn("NO-GO", report["top_risk"])
        self.assertIn("CAUTION", report["narrative_opening"])
        self.assertNotIn("NO-GO", report["narrative_opening"])
        self.assertNotIn("NO-GO", report["narrative_explanation"])
        self.assertIn(
            "recommendation to match severity",
            " ".join(report["warnings"]),
        )
        self.assertIn("score to match severity", " ".join(report["warnings"]))

    def test_persist_analysis_report_preserves_medium_go_recommendation(
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
            recommendation="go",
            top_risk="Medium security group review.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: medium security group review.",
            explanation="Medium severity remains advisory.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[],
            evidence_items=[],
        )

        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "go")
        self.assertEqual(report["risk_score"], 42)
        self.assertEqual(report["top_risk"], "Medium security group review.")
        self.assertEqual(
            report["narrative_opening"],
            "GO: medium security group review.",
        )
        self.assertNotIn("Evidence Law", " ".join(report["warnings"]))

    def test_persist_analysis_report_preserves_medium_go_recommendation_when_reconciling_score(
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
            score=95,
            severity="medium",
            recommendation="go",
            top_risk="Medium security group review.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: medium security group review.",
            explanation="Medium severity remains advisory.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[],
            evidence_items=[],
        )

        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "go")
        self.assertEqual(report["risk_score"], 69)
        self.assertEqual(report["top_risk"], "Medium security group review.")
        self.assertIn("score to match severity", " ".join(report["warnings"]))
        self.assertNotIn(
            "recommendation to match severity", " ".join(report["warnings"])
        )

    def test_persist_analysis_report_preserves_hyphenated_verdict_prose(
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
            score=52,
            severity="medium",
            recommendation="caution",
            top_risk="High availability rollout requires review.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="Go live review is pending.",
            explanation="Critical path implementation detail remains under review.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[],
            evidence_items=[],
        )

        self.assertEqual(
            report["top_risk"], "High availability rollout requires review."
        )
        self.assertEqual(report["narrative_opening"], "Go live review is pending.")
        self.assertEqual(
            report["narrative_explanation"],
            "Critical path implementation detail remains under review.",
        )
        self.assertNotIn("Evidence Law refreshed", " ".join(report["warnings"]))

    def test_persist_analysis_report_promotes_downgraded_severe_finding_to_medium_assessment(
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
            score=18,
            severity="low",
            recommendation="go",
            top_risk="CRITICAL: unsupported no-go claim.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: unsupported no-go claim.",
            explanation="CRITICAL unsupported no-go claim.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-unsupported-critical",
                    analysis_id=0,
                    title="CRITICAL: unsupported no-go claim",
                    description="Unsupported critical claim without deterministic evidence.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.96,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            evidence_items=[],
        )

        self.assertEqual(report["findings"][0]["severity"], "medium")
        self.assertEqual(report["severity"], "medium")
        self.assertEqual(report["recommendation"], "caution")
        self.assertGreaterEqual(report["risk_score"], 42)
        self.assertIn("Evidence Law downgraded", report["top_risk"])

    def test_persist_analysis_report_reconciles_critical_verdict_to_supported_high_finding(
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
            score=95,
            severity="critical",
            recommendation="no-go",
            top_risk="CRITICAL: unsupported inferred exposure.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: unsupported inferred exposure.",
            explanation="Unsupported inferred exposure is the severe issue.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-unsupported-critical",
                    analysis_id=0,
                    title="CRITICAL: unsupported inferred exposure",
                    description="Unsupported inferred exposure.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.97,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-supported-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported-high"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["recommendation"], "no-go")
        self.assertLessEqual(report["risk_score"], 89)
        self.assertIn("HIGH: aws_security_group.main", report["top_risk"])
        self.assertNotIn("CRITICAL", report["top_risk"])
        self.assertIn(
            "highest linked deterministic finding severity: high",
            report["narrative_explanation"],
        )

    def test_persist_analysis_report_reconciles_overclaimed_critical_verdict_without_finding_downgrade(
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
            score=94,
            severity="critical",
            recommendation="no-go",
            top_risk="CRITICAL: reported verdict overstates the supported finding.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: critical report verdict.",
            explanation="Critical report verdict overstates the supported finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-supported-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["recommendation"], "no-go")
        self.assertLessEqual(report["risk_score"], 89)
        self.assertIn("HIGH: aws_security_group.main", report["top_risk"])
        self.assertIn("Evidence Law downgraded", report["narrative_explanation"])
        self.assertNotIn(
            "Critical report verdict overstates", report["narrative_explanation"]
        )

    def test_persist_analysis_report_promotes_underclaimed_verdict_to_supported_high_finding(
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
            top_risk="Medium report verdict understates deterministic severe finding.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: medium report verdict.",
            explanation="Medium report verdict understates deterministic severe finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-supported-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["recommendation"], "no-go")
        self.assertGreaterEqual(report["risk_score"], 70)
        self.assertIn("HIGH: aws_security_group.main", report["top_risk"])
        self.assertIn("Evidence Law promoted", " ".join(report["warnings"]))
        self.assertIn(
            "Deterministic severe risk remains", report["narrative_explanation"]
        )
        self.assertNotIn(
            "Medium report verdict understates",
            report["narrative_explanation"],
        )

    def test_persist_analysis_report_refreshes_stale_non_severe_copy_for_supported_high(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="MEDIUM: stale non-severe copy.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: stale non-severe copy.",
            explanation="Medium stale non-severe copy.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-supported-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["recommendation"], "no-go")
        self.assertIn("HIGH: aws_security_group.main", report["top_risk"])
        self.assertNotIn("MEDIUM", report["top_risk"])
        self.assertIn("deterministic severe risk remains", report["narrative_opening"])
        self.assertIn("aws_security_group.main", report["narrative_explanation"])

    def test_persist_analysis_report_normalizes_supported_severe_finding_metadata(
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
            severity="high",
            recommendation="go",
            top_risk="HIGH: aws_security_group.main",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: deterministic severe risk.",
            explanation="Linked deterministic evidence supports the severe finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-supported-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=["ev-supported-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["recommendation"], "no-go")
        self.assertGreaterEqual(report["risk_score"], 70)
        self.assertTrue(report["findings"][0]["deterministic"])
        self.assertEqual(
            report["findings"][0]["evidence_classification"],
            "deterministic",
        )

    def test_persist_analysis_report_normalizes_supported_severe_finding_metadata_with_consistent_report(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="HIGH: aws_security_group.main",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: deterministic severe risk.",
            explanation="Linked deterministic evidence supports the severe finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-supported-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=["ev-supported-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["recommendation"], "no-go")
        self.assertEqual(report["risk_score"], 72)
        self.assertTrue(report["findings"][0]["deterministic"])
        self.assertEqual(
            report["findings"][0]["evidence_classification"],
            "deterministic",
        )

    def test_persist_analysis_report_uses_highest_supported_severe_finding_for_partial_downgrade(
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
            score=92,
            severity="critical",
            recommendation="no-go",
            top_risk="CRITICAL: unsupported inferred exposure.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: unsupported inferred exposure.",
            explanation="Unsupported inferred exposure is the severe issue.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-unsupported",
                    analysis_id=0,
                    title="CRITICAL: unsupported inferred exposure",
                    description="Unsupported inferred exposure.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.97,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-supported-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported-high"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-supported-critical",
                    analysis_id=0,
                    title="CRITICAL: aws_iam_policy.admin",
                    description="Deterministic admin policy exposure.",
                    severity="critical",
                    category="iam/rbac",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported-critical"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-supported-critical",
                    analysis_id=0,
                    finding_id="pending:change-2",
                    source_type="artifact",
                    source_ref="terraform://plan.json#aws_iam_policy.admin?action=modify",
                    summary="Terraform changed an admin policy.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-2"],
                ),
            ],
        )

        critical_evidence_id = next(
            evidence["evidence_id"]
            for evidence in report["evidence_items"]
            if "aws_iam_policy.admin" in evidence["source_ref"]
        )
        self.assertIn("CRITICAL: aws_iam_policy.admin", report["top_risk"])
        self.assertNotIn("HIGH: aws_security_group.main", report["top_risk"])
        self.assertEqual(report["top_risk_contributors"], [critical_evidence_id])

    def test_persist_analysis_report_explains_remaining_supported_severe_risk_after_partial_downgrade(
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
            score=82,
            severity="high",
            recommendation="no-go",
            top_risk="HIGH: unsupported inferred exposure.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: unsupported inferred exposure.",
            explanation="Unsupported inferred exposure is the severe issue.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-unsupported",
                    analysis_id=0,
                    title="HIGH: unsupported inferred exposure",
                    description="Unsupported inferred exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.94,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-supported",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Deterministic security group exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-supported"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-supported",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertIn(
            "Deterministic severe risk remains", report["narrative_explanation"]
        )
        self.assertIn("aws_security_group.main", report["narrative_explanation"])
        self.assertIn("Evidence Law downgraded", report["narrative_explanation"])
        self.assertNotIn(
            "unsupported inferred exposure is the severe issue",
            report["narrative_explanation"],
        )

    def test_persist_analysis_report_rewrites_severity_only_downgraded_title(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Severity-only title.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: severity-only title.",
            explanation="Severity-only title.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-severity-only",
                    analysis_id=0,
                    title="HIGH:",
                    description="Bare severity title must not survive downgrade.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.9,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            evidence_items=[],
        )

        self.assertEqual(
            report["findings"][0]["title"],
            "MEDIUM: Bare severity title must not survive downgrade.",
        )
        self.assertNotIn("HIGH", report["findings"][0]["title"])

    def test_persist_analysis_report_strips_verdict_prefix_from_downgraded_title(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="NO-GO: unsupported severe claim.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: unsupported severe claim.",
            explanation="Unsupported severe claim.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-verdict-title",
                    analysis_id=0,
                    title="NO-GO: unsupported severe claim",
                    description="Unsupported severe claim.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.9,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            evidence_items=[],
        )

        self.assertEqual(
            report["findings"][0]["title"],
            "MEDIUM: unsupported severe claim",
        )
        self.assertNotIn("NO-GO", report["findings"][0]["title"])

    def test_persist_analysis_report_strips_unpunctuated_verdict_prefix_from_downgraded_title(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="NO-GO unsupported severe claim.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO unsupported severe claim.",
            explanation="CRITICAL risk remains without deterministic evidence.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-unpunctuated-verdict-title",
                    analysis_id=0,
                    title="NO-GO unsupported severe claim",
                    description="Unsupported severe claim.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.9,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            evidence_items=[],
        )

        self.assertEqual(
            report["findings"][0]["title"],
            "MEDIUM: unsupported severe claim",
        )
        self.assertNotIn("NO-GO", report["findings"][0]["title"])
        self.assertNotIn("NO-GO", report["narrative_opening"])
        self.assertNotIn("CRITICAL risk remains", report["narrative_explanation"])

    def test_persist_analysis_report_strips_plain_language_verdict_lead_ins(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="NO-GO deployment review remains blocked.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO deployment review remains blocked.",
            explanation="CRITICAL database exposure remains without deterministic evidence.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-plain-language-verdict-title",
                    analysis_id=0,
                    title="HIGH ingress exposure requires review",
                    description="Unsupported ingress exposure.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=False,
                    confidence=0.9,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=[],
                    skill_id=None,
                )
            ],
            evidence_items=[],
        )

        self.assertEqual(
            report["findings"][0]["title"],
            "MEDIUM: ingress exposure requires review",
        )
        self.assertNotIn("HIGH", report["findings"][0]["title"])
        self.assertNotIn("NO-GO", report["narrative_opening"])
        self.assertNotIn("CRITICAL database exposure", report["narrative_explanation"])

    def test_persist_analysis_report_preserves_severe_finding_with_deterministic_evidence(
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
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="Deterministic severe risk.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: deterministic severe risk.",
            explanation="The linked plan evidence supports the severe finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-high",
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
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        self.assertEqual(report["findings"][0]["severity"], "high")
        self.assertEqual(
            report["findings"][0]["evidence_classification"],
            "deterministic",
        )
        self.assertNotIn("Evidence Law downgraded", " ".join(report["warnings"]))

    def test_persist_analysis_report_preserves_external_deterministic_severe_finding(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="scanner.json",
                    tool="terraform",
                    status="parsed",
                    changes=[],
                )
            ]
        )
        assessment = RiskAssessment(
            score=72,
            severity="high",
            recommendation="no-go",
            top_risk="HIGH: External scanner high risk.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: external scanner high risk.",
            explanation="External scanner evidence supports the severe finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-external-high",
                    analysis_id=0,
                    title="HIGH: External scanner high risk.",
                    description="External scanner reported a deterministic high risk.",
                    severity="high",
                    category="external/scanner",
                    deterministic=False,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_classification="model_inferred",
                    evidence_refs=["ev-external-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-external-high",
                    analysis_id=0,
                    finding_id="pending:scanner-1",
                    source_type="external_scanner",
                    source_ref="scanner://sast.json#rule.high?action=flag",
                    summary="External scanner flagged a high risk.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["scanner-1"],
                )
            ],
        )

        self.assertEqual(report["severity"], "high")
        self.assertEqual(report["findings"][0]["severity"], "high")
        self.assertTrue(report["findings"][0]["deterministic"])
        self.assertEqual(report["findings"][0]["evidence_classification"], "external")

    def test_persist_analysis_report_rejects_unmatched_single_finding_evidence(
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
                            resource_id="aws_security_group.first",
                            action="modify",
                            summary="Terraform changed a security group.",
                        ),
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_security_group.second",
                            action="modify",
                            summary="Terraform changed another security group.",
                        ),
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed security groups.",
            top_risk_contributors=["ev-stale"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-stale",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.unmatched",
                    action="modify",
                    contribution=18,
                    summary="Terraform changed security groups.",
                    severity="medium",
                    reasoning="Terraform changed security groups.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review deterministic evidence.",
            explanation="The report has a stale assessment evidence ID.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-unlinked",
                analysis_id=0,
                title="MEDIUM: security group changes",
                description="Terraform changed security groups.",
                severity="medium",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=[],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-first",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref=(
                    "terraform://plan.json#aws_security_group.first?action=modify"
                ),
                summary="Terraform changed a security group.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
            ),
            EvidenceItem(
                evidence_id="ev-second",
                analysis_id=0,
                finding_id="pending:change-2",
                source_type="artifact",
                source_ref=(
                    "terraform://plan.json#aws_security_group.second?action=modify"
                ),
                summary="Terraform changed another security group.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
            ),
        ]

        with self.assertRaisesRegex(
            ValueError,
            "not referenced by any persisted finding",
        ):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                narrative,
                findings=findings,
                evidence_items=evidence_items,
            )

    def test_persist_analysis_report_does_not_repair_stale_link_by_same_basename(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="prod/plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="prod/plan.json",
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
            top_risk_contributors=["ev-stale"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-stale",
                    source_file="prod/plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=18,
                    summary="Terraform changed a security group.",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    severity="medium",
                    reasoning="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review deterministic evidence.",
            explanation="The report has a stale assessment evidence ID.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-unlinked",
                analysis_id=0,
                title="MEDIUM: aws_security_group.main",
                description="Terraform changed a security group.",
                severity="medium",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=[],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-wrong-artifact",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref=(
                    "terraform://staging/plan.json#aws_security_group.main?action=modify"
                ),
                summary="Terraform changed a security group in a different artifact.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
            )
        ]

        with self.assertRaisesRegex(
            ValueError,
            "not referenced by any persisted finding",
        ):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                narrative,
                findings=findings,
                evidence_items=evidence_items,
            )

    def test_persist_analysis_report_does_not_repair_stale_link_by_resource_prefix(
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
            top_risk="Terraform changed a security group.",
            top_risk_contributors=["ev-stale"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-stale",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=18,
                    summary="Terraform changed a security group.",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    severity="medium",
                    reasoning="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review deterministic evidence.",
            explanation="The report has a stale assessment evidence ID.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-unlinked",
                analysis_id=0,
                title="MEDIUM: aws_security_group.main",
                description="Terraform changed a security group.",
                severity="medium",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=[],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-wrong-resource",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref=(
                    "terraform://plan.json#aws_security_group.main-extra?action=modify"
                ),
                summary="Terraform changed a similarly named security group.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
            )
        ]

        with self.assertRaisesRegex(
            ValueError,
            "not referenced by any persisted finding",
        ):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                narrative,
                findings=findings,
                evidence_items=evidence_items,
            )

    def test_persist_analysis_report_does_not_repair_stale_link_without_operation(
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
            top_risk="Terraform changed a security group.",
            top_risk_contributors=["ev-stale"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-stale",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=18,
                    summary="Terraform changed a security group.",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    severity="medium",
                    reasoning="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review deterministic evidence.",
            explanation="The report has a stale assessment evidence ID.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-unlinked",
                analysis_id=0,
                title="MEDIUM: aws_security_group.main",
                description="Terraform changed a security group.",
                severity="medium",
                category="networking/ingress",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=[],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-missing-operation",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main",
                summary="Terraform changed a security group without action metadata.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
            )
        ]

        with self.assertRaisesRegex(
            ValueError,
            "not referenced by any persisted finding",
        ):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                narrative,
                findings=findings,
                evidence_items=evidence_items,
            )

    def test_persist_analysis_report_does_not_repair_stale_link_to_unrelated_only_finding(
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
            top_risk="Terraform changed a security group.",
            top_risk_contributors=["ev-stale"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-stale",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=18,
                    summary="Terraform changed a security group.",
                    normalized_action="modify",
                    resource_category="networking/ingress",
                    severity="medium",
                    reasoning="Terraform changed a security group.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review deterministic evidence.",
            explanation="The report has a stale assessment evidence ID.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        findings = [
            Finding(
                finding_id="finding-unlinked",
                analysis_id=0,
                title="MEDIUM: unrelated database migration",
                description="Database migration needs review.",
                severity="medium",
                category="data/service",
                deterministic=True,
                confidence=1.0,
                uncertainty_note=None,
                evidence_classification="model_inferred",
                evidence_refs=[],
                skill_id=None,
            )
        ]
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-real",
                analysis_id=0,
                finding_id="pending:change-1",
                source_type="artifact",
                source_ref=(
                    "terraform://plan.json#aws_security_group.main?action=modify"
                ),
                summary="Terraform changed a security group.",
                severity_hint="medium",
                deterministic=True,
                confidence=1.0,
            )
        ]

        with self.assertRaisesRegex(
            ValueError,
            "not referenced by any persisted finding",
        ):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                narrative,
                findings=findings,
                evidence_items=evidence_items,
            )

    def _persist_shareable_report(self, audit_actor: str | None = None) -> dict:
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
                    evidence_id="ev-001",
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
            audit_context={
                "source_interface": "api",
                **({"actor": audit_actor} if audit_actor is not None else {}),
            },
        )

    def _persist_shareable_report_with_audit_actor(self, audit_actor: str) -> dict:
        return self._persist_shareable_report(audit_actor=audit_actor)

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
        audit_context: dict[str, object] | None = None,
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
            audit_context=audit_context
            or {"source_interface": "api", "trigger_type": "pull_request"},
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
            confidence=0.84,
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
            incident_matches=[
                IncidentMatch(
                    incident_id=0,
                    match_type="public_risk_pattern",
                    public_pattern_id="public-ingress-wide-open",
                    title="Wide-open administrative ingress",
                    severity="high",
                    source_file="plan.json",
                    incident_date=None,
                    similarity=0.86,
                    confidence=0.86,
                    confidence_label="high",
                    reason="The change exposes administrative ingress publicly.",
                    evidence=[
                        "plan.json: aws_security_group.main (modify) - public SSH"
                    ],
                    matched_signals=["0.0.0.0/0", "ssh"],
                    affected_services=["aws_security_group.main"],
                    prevention_notes=["Use trusted administrative access."],
                    verification_guidance=[
                        "Confirm public CIDR is intentional.",
                        "Restrict ingress to trusted networks.",
                    ],
                    summary="Public risk pattern match: wide-open administrative ingress.",
                )
            ],
            findings=findings,
            evidence_items=evidence_items,
            audit_context={
                "source_interface": "api",
                "trigger_type": "session",
                "trigger_id": "sess-123",
                "actor": "reviewer@example.com",
            },
        )
        self.assertIn("id", persisted)
        self.assertEqual(persisted["audit"]["source_interface"], "api")
        self.assertEqual(persisted["audit"]["trigger_type"], "session")
        self.assertEqual(persisted["audit"]["trigger_id"], "sess-123")
        self.assertEqual(persisted["audit"]["actor"], "reviewer@example.com")
        self.assertEqual(persisted["audit"]["files_analyzed"], ["plan.json"])
        self.assertEqual(persisted["audit"]["llm_provider"], "ollama")
        self.assertEqual(persisted["audit"]["persisted_at"], persisted["created_at"])
        self.assertEqual(
            persisted["audit"]["delivery"],
            {
                "surface": "api",
                "trigger_type": "session",
                "trigger_id": "sess-123",
                "report_id": persisted["id"],
                "status": "persisted",
            },
        )
        self.assertEqual(persisted["audit"]["redaction_status"], "none")
        self.assertEqual(
            persisted["submission_manifest"]["provenance"]["actor"],
            "reviewer@example.com",
        )
        self.assertEqual(persisted["assessment_source"], "heuristic-only")
        self.assertEqual(persisted["narrative_source"], "llm")
        self.assertEqual(persisted["report_schema_version"], "v2")
        self.assertEqual(persisted["confidence"], 0.84)
        self.assertEqual(persisted["narrative_provider"], "ollama")
        self.assertEqual(persisted["narrative_model"], "ollama/llama3")
        self.assertEqual(persisted["skills_applied"], ["git", "terraform"])
        self.assertEqual(persisted["context_completeness"]["context_score"], 0.84)
        self.assertEqual(persisted["blast_radius"]["direct_count"], 1)
        self.assertEqual(persisted["rollback_plan"]["complexity_score"], 3)
        self.assertEqual(len(persisted["incident_matches"]), 1)
        self.assertEqual(
            persisted["incident_matches"][0]["public_pattern_id"],
            "public-ingress-wide-open",
        )
        self.assertEqual(persisted["incident_matches"][0]["confidence"], 0.86)
        self.assertEqual(persisted["incident_matches"][0]["confidence_label"], "high")
        self.assertEqual(
            persisted["incident_matches"][0]["matched_signals"],
            ["0.0.0.0/0", "ssh"],
        )
        self.assertEqual(
            persisted["incident_matches"][0]["affected_services"],
            ["aws_security_group.main"],
        )
        self.assertEqual(
            persisted["incident_matches"][0]["prevention_notes"],
            ["Use trusted administrative access."],
        )
        self.assertTrue(persisted["incident_matches"][0]["evidence"])
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
        self.assertEqual(fetched["risk_score"], 70)
        self.assertEqual(fetched["severity"], "high")
        self.assertEqual(fetched["recommendation"], "no-go")
        self.assertEqual(fetched["audit"]["source_interface"], "api")
        self.assertEqual(fetched["audit"]["actor"], "reviewer@example.com")
        self.assertEqual(fetched["audit"]["persisted_at"], fetched["created_at"])
        self.assertEqual(fetched["audit"]["redaction_status"], "none")
        self.assertEqual(fetched["audit"]["files_analyzed"], ["plan.json"])
        self.assertIn(
            "Deterministic severe risk remains", fetched["narrative_explanation"]
        )
        self.assertIn("Evidence Law promoted", fetched["narrative_explanation"])
        self.assertEqual(fetched["assessment_source"], "heuristic-only")
        self.assertEqual(fetched["narrative_source"], "llm")
        self.assertEqual(fetched["report_schema_version"], "v2")
        self.assertEqual(fetched["skills_applied"], ["git", "terraform"])
        self.assertEqual(fetched["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(fetched["context_completeness"]["topology_freshness_days"], 12)
        self.assertEqual(fetched["blast_radius"]["affected"][0]["label"], "Database")
        self.assertEqual(
            fetched["incident_matches"][0]["public_pattern_id"],
            "public-ingress-wide-open",
        )
        self.assertEqual(
            fetched["incident_matches"][0]["verification_guidance"],
            [
                "Confirm public CIDR is intentional.",
                "Restrict ingress to trusted networks.",
            ],
        )
        self.assertEqual(fetched["incident_matches"][0]["confidence_label"], "high")
        self.assertEqual(
            fetched["incident_matches"][0]["matched_signals"],
            ["0.0.0.0/0", "ssh"],
        )
        self.assertEqual(
            fetched["incident_matches"][0]["affected_services"],
            ["aws_security_group.main"],
        )
        self.assertEqual(
            fetched["incident_matches"][0]["prevention_notes"],
            ["Use trusted administrative access."],
        )
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

    def test_fetch_analysis_report_marks_incident_index_snapshot_stale(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        incident_service_module.ingest_incident_document(
            "checkout-a.md",
            "# Checkout A\nSeverity: high\nRedaction status: redacted\n",
            project_id=project.id,
        )
        snapshot = incident_service_module.get_incident_index_snapshot(
            project_id=project.id
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
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Security group review.",
            contributors=[],
            interaction_risks=[],
            context_completeness=ContextCompleteness(
                context_score=0.9,
                incident_index_size=int(snapshot["incident_index_size"] or 0),
                incident_index_version=str(snapshot["incident_index_version"]),
                incident_index_last_indexed_at=snapshot[
                    "incident_index_last_indexed_at"
                ],
                incident_index_freshness_status=str(
                    snapshot["incident_index_freshness_status"]
                ),
            ),
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="Review the ingress change.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        incident_service_module.ingest_incident_document(
            "checkout-b.md",
            "# Checkout B\nSeverity: medium\nRedaction status: redacted\n",
            project_id=project.id,
        )
        fetched = report_service_module.fetch_analysis_report(persisted["id"])

        self.assertIsNotNone(fetched)
        self.assertEqual(
            fetched["context_completeness"]["incident_index_freshness_status"],
            "stale",
        )
        self.assertEqual(
            fetched["context_completeness"]["incident_index_version"],
            snapshot["incident_index_version"],
        )

    def test_fetch_analysis_report_marks_incident_index_stale_when_lookup_fails(
        self,
    ) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
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
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Security group review.",
            contributors=[],
            interaction_risks=[],
            context_completeness=ContextCompleteness(
                context_score=0.9,
                incident_index_size=1,
                incident_index_version="incidents:1:old",
                incident_index_last_indexed_at="2026-05-20T00:00:00Z",
                incident_index_freshness_status="current",
            ),
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="Review the ingress change.",
            guidance=[],
            degraded=False,
            warnings=[],
        )
        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        with patch(
            "services.incident_service.get_incident_index_snapshot",
            side_effect=RuntimeError("snapshot unavailable"),
        ):
            fetched = report_service_module.fetch_analysis_report(persisted["id"])

        self.assertIsNotNone(fetched)
        self.assertEqual(
            fetched["context_completeness"]["incident_index_freshness_status"],
            "stale",
        )

    def test_persist_analysis_report_cleans_up_committed_row_after_artifact_failure(
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
                            resource_id="aws_instance.main",
                            action="modify",
                            summary="Terraform changed an instance.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed an instance.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the instance update.",
            explanation="The deployment should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.report_service.save_report_artifacts",
                side_effect=RuntimeError("snapshot disk full"),
            ),
            self.assertRaisesRegex(RuntimeError, "snapshot disk full"),
        ):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                narrative,
                artifact_snapshots={"plan.json": b'{"resource_changes": []}'},
            )

        with sqlite3.connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM analysis_reports"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_persist_analysis_report_cleans_up_row_when_artifact_cleanup_fails(
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
                            resource_id="aws_instance.main",
                            action="modify",
                            summary="Terraform changed an instance.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Terraform changed an instance.",
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the instance update.",
            explanation="The deployment should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.report_service.save_report_artifacts",
                side_effect=RuntimeError("snapshot disk full"),
            ),
            patch(
                "services.report_service.delete_report_artifacts",
                side_effect=RuntimeError("cleanup disk full"),
            ),
            self.assertRaisesRegex(RuntimeError, "snapshot disk full"),
        ):
            report_service_module.persist_analysis_report(
                parse_batch,
                assessment,
                narrative,
                artifact_snapshots={"plan.json": b'{"resource_changes": []}'},
            )

        with sqlite3.connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM analysis_reports"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_persist_analysis_report_normalizes_actor_metadata(self) -> None:
        report = self._persist_shareable_report_with_audit_actor(
            " reviewer@example.com\nInjected: yes\t" + ("x" * 200)
        )

        self.assertNotIn("\n", report["audit"]["actor"])
        self.assertNotIn("\t", report["audit"]["actor"])
        self.assertTrue(report["audit"]["actor"].startswith("reviewer@example.com "))
        self.assertLessEqual(len(report["audit"]["actor"]), 120)

    def test_fetch_report_recovers_actor_from_submission_manifest_fallback(
        self,
    ) -> None:
        report = self._persist_shareable_report_with_audit_actor("reviewer@example.com")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id = ?",
                ("{not-valid-json", report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["audit"]["actor"], "reviewer@example.com")
        self.assertTrue(fetched["submission_manifest_fallback"])
        self.assertEqual(
            fetched["submission_manifest_fallback"][0]["actor"],
            "reviewer@example.com",
        )

    def test_persist_analysis_report_applies_context_uncertainty_downgrade(
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
            score=12,
            severity="low",
            recommendation="go",
            confidence=1.0,
            top_risk="Terraform change looks low risk.",
            context_completeness={
                "topology_freshness_days": None,
                "incident_index_size": 0,
                "parser_success_rate": 1.0,
                "evidence_success_rate": 1.0,
                "context_score": 0.52,
            },
            contributors=[],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CAUTION: context is incomplete.",
            explanation="Reviewer verification is required before trusting low risk.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            audit_context={"source_interface": "api"},
        )

        self.assertEqual(persisted["risk_score"], 42)
        self.assertEqual(persisted["severity"], "medium")
        self.assertEqual(persisted["recommendation"], "caution")
        self.assertEqual(persisted["confidence"], 0.52)
        self.assertTrue(persisted["context_completeness"]["insufficient_context"])
        self.assertIn("INSUFFICIENT CONTEXT", persisted["top_risk"])
        self.assertIn("Insufficient context", persisted["warnings"][0])

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
        self.assertIn("confidence_ledger", shared_report)
        self.assertIn(
            "Artifact 1", shared_report["confidence_ledger"]["contributors"][0]
        )
        self.assertNotIn(
            "prod/network/plan.json",
            " ".join(shared_report["confidence_ledger"]["contributors"]),
        )
        self.assertIn("Artifact 1", shared_report["evidence_items"][0]["source_ref"])
        self.assertNotIn(
            "prod/network/plan.json",
            shared_report["evidence_items"][0]["source_ref"],
        )

    def test_fetch_analysis_report_builds_confidence_ledger_from_legacy_contributors(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        legacy_contributors = [
            {
                "evidence_id": "ev-low",
                "source_file": "low.json",
                "tool": "terraform",
                "resource_id": "hidden.low",
                "action": "modify",
                "contribution": "2.5",
                "summary": "Lower contributor.",
                "severity": "medium",
            },
            {
                "evidence_id": "ev-top",
                "source_file": "top.json",
                "tool": "terraform",
                "resource_id": "visible.top",
                "action": "modify",
                "contribution": "20.5",
                "summary": "Top contributor.",
                "severity": "high",
            },
            {
                "evidence_id": "ev-invalid",
                "source_file": "legacy.json",
                "tool": "terraform",
                "resource_id": "invalid.legacy",
                "action": "modify",
                "contribution": "unknown",
                "summary": "Malformed legacy contributor.",
                "severity": "low",
            },
        ]
        with database_module.SessionLocal() as session:
            stored = session.get(tables_module.AnalysisReport, report["id"])
            assert stored is not None
            stored.contributors_json = json.dumps(legacy_contributors)
            session.commit()

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        ledger = fetched["confidence_ledger"]
        self.assertEqual(
            ledger["contributors"][0],
            "visible.top · HIGH · contribution 20.5 · top.json",
        )
        self.assertIn(
            "invalid.legacy · LOW · contribution unknown · legacy.json",
            ledger["contributors"],
        )
        self.assertIn("visible.top", ledger["why_not_lower"][0])
        self.assertTrue(any("visible.top" in item for item in ledger["why_not_higher"]))

    def test_history_summary_ledger_marks_evidence_detail_omitted(self) -> None:
        self._persist_shareable_report()

        history = report_service_module.fetch_filtered_analysis_history()

        self.assertEqual(len(history), 1)
        factors = " ".join(history[0]["confidence_ledger"]["confidence_factors"])
        self.assertNotIn("lacks linked deterministic evidence", factors)

    def test_share_report_link_normalizes_unspecified_app_host(self) -> None:
        for raw_host in ("", "   ", "0.0.0.0", "::", " :: ", "[::]"):
            with self.subTest(raw_host=raw_host):
                with patch.dict(
                    os.environ,
                    {
                        "APP_BASE_URL": "",
                        "PUBLIC_APP_URL": "",
                        "APP_HOST": raw_host,
                        "APP_PORT": "18080",
                    },
                ):
                    share_url = report_service_module.build_share_report_link(42)

                    self.assertEqual(share_url, "http://localhost:18080/reports/42")

    def test_share_report_link_unwraps_bracketed_hostname_app_host(self) -> None:
        for raw_host in ("[localhost]", "[deploywhisper.local]"):
            with self.subTest(raw_host=raw_host):
                with patch.dict(
                    os.environ,
                    {
                        "APP_BASE_URL": "",
                        "PUBLIC_APP_URL": "",
                        "APP_HOST": raw_host,
                        "APP_PORT": "18080",
                    },
                ):
                    share_url = report_service_module.build_share_report_link(42)

                    self.assertEqual(
                        share_url,
                        f"http://{raw_host.removeprefix('[').removesuffix(']')}:18080/reports/42",
                    )

    def test_share_report_link_strips_embedded_app_host_port(self) -> None:
        expected_hosts = {
            "localhost:19090": "localhost",
            "127.0.0.1:19090": "127.0.0.1",
            "[::1]:19090": "[::1]",
            "2001:db8::1:19090": "[2001:db8::1]",
            "fe80::1%lo0:19090": "[fe80::1%25lo0]",
            "2001:db8::1:8080": "[2001:db8::1:8080]",
            "fe80::1%lo0:8080": "[fe80::1%25lo0]",
            "2001:db8::1:1234": "[2001:db8::1:1234]",
            "fe80::443": "[fe80::443]",
        }
        for raw_host, expected_host in expected_hosts.items():
            with self.subTest(raw_host=raw_host):
                with patch.dict(
                    os.environ,
                    {
                        "APP_BASE_URL": "",
                        "PUBLIC_APP_URL": "",
                        "APP_HOST": raw_host,
                        "APP_PORT": "18080",
                    },
                ):
                    share_url = report_service_module.build_share_report_link(42)

                self.assertEqual(
                    share_url,
                    f"http://{expected_host}:18080/reports/42",
                )

    def test_share_report_link_brackets_ipv6_app_host(self) -> None:
        for raw_host in ("::1", "[::1]"):
            with self.subTest(raw_host=raw_host):
                with patch.dict(
                    os.environ,
                    {
                        "APP_BASE_URL": "",
                        "PUBLIC_APP_URL": "",
                        "APP_HOST": raw_host,
                        "APP_PORT": "18080",
                    },
                ):
                    share_url = report_service_module.build_share_report_link(42)

                    self.assertEqual(share_url, "http://[::1]:18080/reports/42")

    def test_share_report_link_escapes_scoped_ipv6_app_host_once(self) -> None:
        for raw_host in ("fe80::1%lo0", "fe80::1%25lo0", "[fe80::1%25lo0]"):
            with self.subTest(raw_host=raw_host):
                with patch.dict(
                    os.environ,
                    {
                        "APP_BASE_URL": "",
                        "PUBLIC_APP_URL": "",
                        "APP_HOST": raw_host,
                        "APP_PORT": "18080",
                    },
                ):
                    share_url = report_service_module.build_share_report_link(42)

                self.assertEqual(share_url, "http://[fe80::1%25lo0]:18080/reports/42")

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
        self.assertIn(
            "Artifact 2 changed after Artifact 1",
            shared_report["advisory"]["top_risk"],
        )

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
        self.assertTrue(fetched["context_completeness"]["partial_context"])
        self.assertTrue(fetched["advisory"]["partial_context"])
        self.assertIn("partial_context", fetched["advisory"]["uncertainty_flags"])
        self.assertEqual(fetched["audit"]["redaction_status"], "sensitive_blocked")
        self.assertEqual(
            fetched["audit"]["redaction"],
            {
                "filenames_redacted": False,
                "sensitive_content_excluded": True,
            },
        )

    def test_fetch_report_marks_filename_redacted_manifest_as_redacted(self) -> None:
        report = self._persist_shareable_report()
        manifest = dict(report["submission_manifest"])
        manifest["redaction"] = {
            "filenames_redacted": True,
            "sensitive_content_excluded": False,
        }
        manifest["items"] = [
            {**item, "redaction_status": "none"} for item in manifest["items"]
        ]
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id = ?",
                (json.dumps(manifest), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["audit"]["redaction_status"], "redacted")
        self.assertEqual(
            fetched["audit"]["redaction"],
            {
                "filenames_redacted": True,
                "sensitive_content_excluded": False,
            },
        )

    def test_fetch_report_marks_empty_legacy_manifest_redaction_unknown(self) -> None:
        report = self._persist_shareable_report()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports "
                "SET submission_manifest_json = ?, submission_manifest_fallback_json = ? "
                "WHERE id = ?",
                ("{}", "[]", report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["audit"]["redaction_status"], "unknown")
        self.assertEqual(fetched["audit"]["redaction"], {})

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

    def test_fetch_report_degrades_on_malformed_context_completeness_json(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE risk_assessments SET context_completeness_json = ? "
                "WHERE analysis_id = ?",
                ("{not-valid-json", report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["context_completeness"]["context_score"], 0.0)
        self.assertTrue(fetched["context_completeness"]["insufficient_context"])
        self.assertIn(
            "Re-run analysis to regenerate context completeness metadata.",
            fetched["context_completeness"]["context_todos"],
        )
        self.assertIn(
            "Context completeness metadata was unavailable because persisted JSON was malformed.",
            fetched["warnings"],
        )

    def test_fetch_report_degrades_on_wrong_shape_context_completeness_json(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE risk_assessments SET context_completeness_json = ? "
                "WHERE analysis_id = ?",
                ("[]", report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["context_completeness"]["context_score"], 0.0)
        self.assertTrue(fetched["context_completeness"]["insufficient_context"])
        self.assertIn(
            "Re-run analysis to regenerate context completeness metadata.",
            fetched["context_completeness"]["context_todos"],
        )
        self.assertIn(
            "Context completeness metadata was unavailable because persisted JSON had an unexpected shape.",
            fetched["warnings"],
        )

    def test_fetch_report_degrades_on_incomplete_context_completeness_json(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE risk_assessments SET context_completeness_json = ? "
                "WHERE analysis_id = ?",
                (json.dumps({"context_score": 0.96}), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["context_completeness"]["context_score"], 0.0)
        self.assertTrue(fetched["context_completeness"]["insufficient_context"])
        self.assertEqual(fetched["context_completeness"]["confidence_level"], "low")
        self.assertEqual(fetched["confidence"], 0.0)
        self.assertIn(
            "Context completeness metadata was unavailable because persisted values were incomplete.",
            fetched["warnings"],
        )

    def test_fetch_report_upgrades_legacy_context_completeness_json(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        legacy_context = {
            "topology_freshness_days": 3,
            "topology_last_imported_at": "2026-05-08T00:00:00Z",
            "incident_index_size": 8,
            "parser_success_rate": 1.0,
            "parser_success_by_tool": {"terraform": 1.0},
            "context_score": 0.82,
        }
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE risk_assessments SET confidence = ?, context_completeness_json = ? "
                "WHERE analysis_id = ?",
                (0.82, json.dumps(legacy_context), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        context = fetched["context_completeness"]
        self.assertEqual(context["context_score"], 0.82)
        self.assertFalse(context["insufficient_context"])
        self.assertEqual(context["evidence_success_rate"], 1.0)
        self.assertEqual(context["confidence_level"], "medium")
        self.assertEqual(context["incident_index_version"], "incidents:unknown")
        self.assertEqual(context["incident_index_freshness_status"], "unknown")
        self.assertEqual(fetched["confidence"], 0.82)
        self.assertNotIn(
            "Context completeness metadata was unavailable because persisted values were incomplete.",
            fetched["warnings"],
        )

    def test_fetch_report_normalizes_scalar_todos_and_missing_topology_guidance(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        context = {
            "topology_freshness_days": None,
            "topology_last_imported_at": None,
            "incident_index_size": 8,
            "evidence_success_rate": 1.0,
            "parser_success_rate": 1.0,
            "parser_success_by_tool": {"terraform": 1.0},
            "context_score": 0.92,
            "confidence_level": "high",
            "uncertainty": None,
            "context_todos": "Review parser errors and resubmit supported artifacts.",
            "insufficient_context": False,
        }
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE risk_assessments SET confidence = ?, context_completeness_json = ? "
                "WHERE analysis_id = ?",
                (0.92, json.dumps(context), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        todos = fetched["context_completeness"]["context_todos"]
        self.assertEqual(
            todos,
            ["Import or refresh topology context for this project/workspace."],
        )
        self.assertNotIn("R", todos)
        self.assertNotIn(
            "Review parser errors and resubmit supported artifacts.",
            todos,
        )
        self.assertNotIn(
            "Refresh stale topology context for this project/workspace.",
            todos,
        )

    def test_fetch_report_normalizes_inconsistent_context_completeness_json(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        inconsistent_context = {
            "topology_freshness_days": 3,
            "topology_last_imported_at": "2026-05-08T00:00:00Z",
            "incident_index_size": 8,
            "evidence_success_rate": 1.0,
            "parser_success_rate": 1.0,
            "parser_success_by_tool": {"terraform": 1.0},
            "context_score": 0.52,
            "confidence_level": "high",
            "uncertainty": None,
            "context_todos": [],
            "insufficient_context": False,
        }
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE risk_assessments SET confidence = ?, context_completeness_json = ? "
                "WHERE analysis_id = ?",
                (1.0, json.dumps(inconsistent_context), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])
        shared = report_service_module.fetch_shared_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        self.assertIsNotNone(shared)
        assert fetched is not None
        assert shared is not None
        for payload in (fetched, shared):
            context = payload["context_completeness"]
            self.assertEqual(context["context_score"], 0.52)
            self.assertTrue(context["insufficient_context"])
            self.assertEqual(context["confidence_level"], "low")
            self.assertIn("Insufficient context", context["uncertainty"])
            self.assertIn(
                "Re-run analysis to regenerate context completeness metadata.",
                context["context_todos"],
            )
            self.assertEqual(payload["confidence"], 0.52)

    def test_fetch_report_degrades_on_partially_populated_context_json(
        self,
    ) -> None:
        report = self._persist_shareable_report()
        legacy_context = {
            "evidence_success_rate": 1.0,
            "confidence_level": "high",
            "context_todos": [],
            "insufficient_context": False,
        }
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE risk_assessments SET confidence = ?, context_completeness_json = ? "
                "WHERE analysis_id = ?",
                (1.0, json.dumps(legacy_context), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["context_completeness"]["context_score"], 0.0)
        self.assertTrue(fetched["context_completeness"]["insufficient_context"])
        self.assertEqual(fetched["context_completeness"]["confidence_level"], "low")
        self.assertEqual(fetched["confidence"], 0.0)
        self.assertIn(
            "Context completeness metadata was unavailable because persisted values were incomplete.",
            fetched["warnings"],
        )

    def test_fetch_report_degrades_when_risk_assessment_is_missing(self) -> None:
        report = self._persist_shareable_report()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "DELETE FROM risk_assessments WHERE analysis_id = ?",
                (report["id"],),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched["confidence"], 0.0)
        self.assertEqual(fetched["context_completeness"]["context_score"], 0.0)
        self.assertTrue(fetched["context_completeness"]["insufficient_context"])
        self.assertIn(
            "Report confidence metadata was invalid and was reset to 0.0.",
            fetched["warnings"],
        )
        self.assertIn(
            "Context completeness metadata was unavailable because persisted values were invalid.",
            fetched["warnings"],
        )

    def test_missing_context_completeness_loader_falls_back_to_limited_context(
        self,
    ) -> None:
        context, warning = report_service_module._load_context_completeness_payload(
            None
        )

        self.assertEqual(context["context_score"], 0.0)
        self.assertEqual(context["confidence_level"], "low")
        self.assertTrue(context["insufficient_context"])
        self.assertEqual(
            warning,
            "Context completeness metadata was unavailable because persisted values were invalid.",
        )

    def test_invalid_report_confidence_loader_falls_back_to_unavailable(self) -> None:
        for value in (None, "invalid", float("nan"), float("inf"), -0.1, 1.1):
            with self.subTest(value=value):
                confidence, warning = report_service_module._load_report_confidence(
                    value
                )

                self.assertEqual(confidence, 0.0)
                self.assertEqual(
                    warning,
                    "Report confidence metadata was invalid and was reset to 0.0.",
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
                    description="Security group ingress now exposes database reachability.",
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
        self.assertEqual(comparison["current_report"]["risk_score"], 90)
        self.assertEqual(comparison["risk_score_delta"], 48)
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
        self.assertEqual(
            comparison["findings"]["persistent"][0]["title"],
            "CRITICAL: aws_security_group.main",
        )
        self.assertEqual(
            comparison["findings"]["context_changed"][0]["title"],
            "CRITICAL: aws_security_group.main",
        )
        self.assertIn(
            "Evidence changed",
            comparison["findings"]["context_changed"][0]["changes"],
        )
        self.assertIn(
            "Description changed",
            comparison["findings"]["context_changed"][0]["changes"],
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
        self.assertEqual(len(comparison["findings"]["persistent"]), 2)
        self.assertEqual(comparison["findings"]["context_changed"], [])
        self.assertEqual(comparison["findings"]["severity_changed"], [])
        self.assertEqual(comparison["evidence"]["added"], [])
        self.assertEqual(comparison["evidence"]["removed"], [])

    def test_fetch_report_comparison_does_not_mispair_duplicate_title_category_findings(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Two same-title findings exist.",
            findings=[
                Finding(
                    finding_id="finding-persistent",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Ingress exposure remains persistent.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-persistent"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-removed",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="SSH exposure was removed.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=["ev-removed"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-persistent",
                    analysis_id=0,
                    finding_id="pending:persistent",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-removed",
                    analysis_id=0,
                    finding_id="pending:removed",
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
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="One same-title finding persists and one is new.",
            findings=[
                Finding(
                    finding_id="finding-persistent",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.main",
                    description="Ingress exposure remains persistent.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-persistent"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-added",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Database exposure is newly reachable.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.93,
                    uncertainty_note=None,
                    evidence_refs=["ev-added"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-persistent",
                    analysis_id=0,
                    finding_id="pending:persistent",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-added",
                    analysis_id=0,
                    finding_id="pending:added",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L40",
                    summary="Port 3306 is newly reachable.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=0.93,
                    related_change_ids=["change-4"],
                ),
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])
        self.assertEqual(
            [item["description"] for item in comparison["findings"]["persistent"]],
            ["Ingress exposure remains persistent."],
        )
        self.assertEqual(
            [item["description"] for item in comparison["findings"]["removed"]],
            ["SSH exposure was removed."],
        )
        self.assertEqual(
            [item["description"] for item in comparison["findings"]["added"]],
            ["Database exposure is newly reachable."],
        )

    def test_fetch_report_comparison_matches_duplicate_same_description_by_evidence(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Two same-description findings exist.",
            findings=[
                Finding(
                    finding_id="finding-persistent",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-persistent"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-removed",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=["ev-removed"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-persistent",
                    analysis_id=0,
                    finding_id="pending:persistent",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-removed",
                    analysis_id=0,
                    finding_id="pending:removed",
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
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="One same-description finding persists and one is new.",
            findings=[
                Finding(
                    finding_id="finding-persistent",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-persistent"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-added",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.93,
                    uncertainty_note=None,
                    evidence_refs=["ev-added"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-persistent",
                    analysis_id=0,
                    finding_id="pending:persistent",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Ingress stays open to the VPC.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-added",
                    analysis_id=0,
                    finding_id="pending:added",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L40",
                    summary="Port 3306 is newly reachable.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=0.93,
                    related_change_ids=["change-4"],
                ),
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])
        self.assertEqual(len(comparison["findings"]["persistent"]), 1)
        self.assertEqual(len(comparison["findings"]["removed"]), 1)
        self.assertEqual(len(comparison["findings"]["added"]), 1)
        self.assertIn(
            "terraform://prod/network/plan.json#L22",
            {item["source_ref"] for item in comparison["evidence"]["removed"]},
        )
        self.assertIn(
            "terraform://prod/network/plan.json#L40",
            {item["source_ref"] for item in comparison["evidence"]["added"]},
        )

    def test_fetch_report_comparison_uses_optimal_evidence_matching(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Two overlapping findings require stable pairing.",
            findings=[
                Finding(
                    finding_id="finding-alpha",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.alpha",
                    description="Alpha ingress remains broad.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.92,
                    uncertainty_note=None,
                    evidence_refs=["ev-alpha-one", "ev-alpha-two"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-beta",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.beta",
                    description="Beta ingress remains broad.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=["ev-beta"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-alpha-one",
                    analysis_id=0,
                    finding_id="pending:alpha",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Alpha ingress includes SSH.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.92,
                    related_change_ids=["change-alpha-one"],
                ),
                EvidenceItem(
                    evidence_id="ev-alpha-two",
                    analysis_id=0,
                    finding_id="pending:alpha",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L18",
                    summary="Alpha ingress includes database access.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.92,
                    related_change_ids=["change-alpha-two"],
                ),
                EvidenceItem(
                    evidence_id="ev-beta",
                    analysis_id=0,
                    finding_id="pending:beta",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L22",
                    summary="Beta ingress includes admin access.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-beta"],
                ),
            ],
        )
        current = self._persist_comparison_report(
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="Both overlapping findings still require review.",
            findings=[
                Finding(
                    finding_id="finding-cross",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.cross",
                    description="Beta ingress remains broad.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.94,
                    uncertainty_note=None,
                    evidence_refs=["ev-cross-alpha", "ev-cross-beta"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-alpha-tail",
                    analysis_id=0,
                    title="HIGH: aws_security_group.alpha",
                    description="Database access remains broad.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.93,
                    uncertainty_note=None,
                    evidence_refs=["ev-alpha-two"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-cross-alpha",
                    analysis_id=0,
                    finding_id="pending:cross",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L14",
                    summary="Alpha ingress still includes SSH.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=0.94,
                    related_change_ids=["change-alpha-one"],
                ),
                EvidenceItem(
                    evidence_id="ev-cross-beta",
                    analysis_id=0,
                    finding_id="pending:cross",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L22",
                    summary="Beta ingress still includes admin access.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=0.94,
                    related_change_ids=["change-beta"],
                ),
                EvidenceItem(
                    evidence_id="ev-alpha-two",
                    analysis_id=0,
                    finding_id="pending:alpha-tail",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L18",
                    summary="Alpha ingress still includes database access.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=0.93,
                    related_change_ids=["change-alpha-two"],
                ),
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])
        self.assertEqual(comparison["findings"]["added"], [])
        self.assertEqual(comparison["findings"]["removed"], [])
        self.assertEqual(len(comparison["findings"]["persistent"]), 2)

    def test_fetch_report_comparison_caps_dense_evidence_matching(
        self,
    ) -> None:
        previous_findings = []
        previous_evidence = []
        current_findings = []
        current_evidence = []
        for index in range(9):
            description = f"Dense overlap finding {index} remains broad."
            previous_findings.append(
                Finding(
                    finding_id=f"previous-dense-{index}",
                    analysis_id=0,
                    title="MEDIUM: duplicate dense ingress",
                    description=description,
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=[f"previous-dense-ev-{index}"],
                    skill_id=None,
                )
            )
            previous_evidence.append(
                EvidenceItem(
                    evidence_id=f"previous-dense-ev-{index}",
                    analysis_id=0,
                    finding_id=f"pending:previous-dense-{index}",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#shared",
                    summary="Shared dense ingress evidence.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-dense"],
                )
            )
            current_findings.append(
                Finding(
                    finding_id=f"current-dense-{index}",
                    analysis_id=0,
                    title="MEDIUM: duplicate dense ingress",
                    description=description,
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=[f"current-dense-ev-{index}"],
                    skill_id=None,
                )
            )
            current_evidence.append(
                EvidenceItem(
                    evidence_id=f"current-dense-ev-{index}",
                    analysis_id=0,
                    finding_id=f"pending:current-dense-{index}",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#shared",
                    summary="Shared dense ingress evidence.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-dense"],
                )
            )
        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Dense overlap findings require bounded matching.",
            findings=previous_findings,
            evidence_items=previous_evidence,
        )
        current = self._persist_comparison_report(
            score=43,
            severity="medium",
            recommendation="caution",
            top_risk="Dense overlap findings remain bounded.",
            findings=current_findings,
            evidence_items=current_evidence,
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["findings"]["added"], [])
        self.assertEqual(comparison["findings"]["removed"], [])
        self.assertEqual(len(comparison["findings"]["persistent"]), 9)
        self.assertTrue(comparison["summary"]["approximate_matching"])
        self.assertEqual(
            comparison["summary"]["warnings"],
            [
                "Dense duplicate evidence matching used deterministic approximate pairing."
            ],
        )

    def test_evidence_identity_counts_preserve_repeated_identities(self) -> None:
        repeated_items = [
            {
                "source_type": "artifact",
                "source_ref": "terraform://prod/network/plan.json#shared",
                "artifact": "",
                "location": "",
                "resource": "aws_security_group.main",
                "operation": "modify",
                "related_change_ids": ["change-dense"],
                "summary": f"Repeated occurrence {index}",
            }
            for index in range(2)
        ]

        identity_counts = report_service_module._evidence_identity_counts(
            repeated_items
        )

        self.assertEqual(sum(identity_counts.values()), 2)
        self.assertEqual(len(identity_counts), 1)

    def test_fetch_report_comparison_pairs_title_category_drift_by_evidence(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Security group ingress requires review.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
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
                    confidence=0.91,
                    related_change_ids=["change-1"],
                )
            ],
        )
        current = self._persist_comparison_report(
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="Public ingress now requires release review.",
            findings=[
                Finding(
                    finding_id="finding-shared",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.public",
                    description="Security group ingress is broader than expected.",
                    severity="critical",
                    category="security/network",
                    deterministic=True,
                    confidence=0.91,
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
                    confidence=0.91,
                    related_change_ids=["change-1"],
                )
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])
        self.assertEqual(comparison["findings"]["added"], [])
        self.assertEqual(comparison["findings"]["removed"], [])
        self.assertEqual(len(comparison["findings"]["persistent"]), 1)
        self.assertEqual(len(comparison["findings"]["context_changed"]), 1)
        self.assertEqual(
            comparison["findings"]["context_changed"][0]["changes"],
            ["Title changed", "Category changed"],
        )

    def test_fetch_report_comparison_does_not_pair_different_findings_on_same_evidence(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Database encryption requires review.",
            findings=[
                Finding(
                    finding_id="finding-encryption",
                    analysis_id=0,
                    title="MEDIUM: database encryption disabled",
                    description="Database encryption is disabled.",
                    severity="medium",
                    category="storage/encryption",
                    deterministic=True,
                    confidence=0.91,
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
                    source_ref="terraform://prod/database/plan.json#L14",
                    summary="Database resource changed.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-db"],
                )
            ],
        )
        current = self._persist_comparison_report(
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="Public database ingress requires review.",
            findings=[
                Finding(
                    finding_id="finding-ingress",
                    analysis_id=0,
                    title="CRITICAL: public database ingress",
                    description="Database ingress is public.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.94,
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
                    source_ref="terraform://prod/database/plan.json#L14",
                    summary="Database resource changed.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=0.94,
                    related_change_ids=["change-db"],
                )
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])
        self.assertEqual(comparison["findings"]["persistent"], [])
        self.assertEqual(comparison["findings"]["context_changed"], [])
        self.assertEqual(
            [item["description"] for item in comparison["findings"]["removed"]],
            ["Database encryption is disabled."],
        )
        self.assertEqual(
            [item["description"] for item in comparison["findings"]["added"]],
            ["Database ingress is public."],
        )

    def test_fetch_report_comparison_does_not_pair_singletons_without_identity(
        self,
    ) -> None:
        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Old singleton finding.",
            findings=[
                Finding(
                    finding_id="finding-old",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="SSH exposure was removed.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.91,
                    uncertainty_note=None,
                    evidence_refs=["ev-old"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-old",
                    analysis_id=0,
                    finding_id="pending:old",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L22",
                    summary="Port 22 remains reachable.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=0.91,
                    related_change_ids=["change-2"],
                )
            ],
        )
        current = self._persist_comparison_report(
            score=71,
            severity="critical",
            recommendation="no-go",
            top_risk="New singleton finding.",
            findings=[
                Finding(
                    finding_id="finding-new",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Database exposure is newly reachable.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=0.93,
                    uncertainty_note=None,
                    evidence_refs=["ev-new"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-new",
                    analysis_id=0,
                    finding_id="pending:new",
                    source_type="artifact",
                    source_ref="terraform://prod/network/plan.json#L40",
                    summary="Port 3306 is newly reachable.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=0.93,
                    related_change_ids=["change-4"],
                )
            ],
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["findings"]["persistent"], [])
        self.assertEqual(
            [item["description"] for item in comparison["findings"]["removed"]],
            ["SSH exposure was removed."],
        )
        self.assertEqual(
            [item["description"] for item in comparison["findings"]["added"]],
            ["Database exposure is newly reachable."],
        )

    def test_fetch_report_comparison_ignores_guidance_reordering(self) -> None:
        self._persist_comparison_report(
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Guidance order one.",
            findings=[
                Finding(
                    finding_id="finding-guidance",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    guidance=["Review ingress.", "Confirm owner."],
                    evidence_refs=["ev-guidance"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-guidance",
                    analysis_id=0,
                    finding_id="pending:guidance",
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
            score=42,
            severity="medium",
            recommendation="caution",
            top_risk="Guidance order two.",
            findings=[
                Finding(
                    finding_id="finding-guidance",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group ingress is broader than expected.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    guidance=["Confirm owner.", "Review ingress."],
                    evidence_refs=["ev-guidance"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-guidance",
                    analysis_id=0,
                    finding_id="pending:guidance",
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

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["findings"]["context_changed"], [])

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
        self.assertEqual(
            report_service_module.normalize_report_schema_version("v02"), "v2"
        )
        self.assertEqual(
            report_service_module.normalize_report_schema_version("v10"), "v10"
        )
        with self.assertRaises(ValueError):
            report_service_module.normalize_report_schema_version("legacy")
        with self.assertRaises(ValueError):
            report_service_module.normalize_report_schema_version(False)
        self.assertEqual(
            report_service_module.readable_report_schema_version("v2"), "v2"
        )
        with self.assertRaises(ValueError):
            report_service_module.readable_report_schema_version("v3")
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
        self.assertTrue(persisted["narrative_degraded"])
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

    def test_persist_analysis_report_uses_narrative_provider_metadata(self) -> None:
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
            contributors=[
                RiskContributor(
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
            available=False,
            opening_sentence="",
            explanation="",
            guidance=[],
            degraded=True,
            warnings=["Narrative provider unavailable: provider timed out"],
            failure_notice="Narrative provider unavailable: provider timed out",
            source="fallback",
            provider="openai",
            model="gpt-4.1-mini",
            local_mode=False,
            skills_applied=["terraform"],
        )

        with patch(
            "services.report_service.resolve_provider_runtime",
            return_value={
                "provider": "ollama",
                "model": "ollama/llama3",
                "api_base": "http://localhost:11434",
                "api_key": None,
                "local_mode": True,
            },
        ):
            persisted = report_service_module.persist_analysis_report(
                parse_batch, assessment, narrative
            )

        self.assertEqual(persisted["audit"]["llm_provider"], "openai")
        self.assertEqual(persisted["audit"]["llm_model"], "gpt-4.1-mini")
        self.assertFalse(persisted["audit"]["llm_local_mode"])
        self.assertEqual(persisted["narrative_provider"], "openai")
        self.assertEqual(persisted["narrative_model"], "gpt-4.1-mini")
        self.assertFalse(persisted["narrative_local_mode"])

    def test_persist_analysis_report_preserves_explicit_narrative_state(self) -> None:
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
            contributors=[
                RiskContributor(
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
            available=True,
            opening_sentence="CAUTION: visible fallback summary.",
            explanation="Visible fallback explanation survives persistence.",
            guidance=[],
            degraded=True,
            warnings=[],
            failure_notice="Narrative provider unavailable: timeout",
            source="llm",
            provider="openai",
            model="gpt-4.1-mini",
            local_mode=False,
            skills_applied=["terraform"],
        )

        persisted = report_service_module.persist_analysis_report(
            parse_batch, assessment, narrative
        )
        fetched = report_service_module.fetch_analysis_report(persisted["id"])

        self.assertTrue(persisted["narrative_available"])
        self.assertTrue(persisted["narrative_degraded"])
        self.assertEqual(
            persisted["narrative_failure_notice"],
            "Narrative provider unavailable: timeout",
        )
        self.assertTrue(fetched["narrative_degraded"])
        self.assertEqual(
            fetched["narrative_failure_notice"],
            "Narrative provider unavailable: timeout",
        )
        self.assertEqual(fetched["narrative_source"], "llm")

        contradictory_narrative = narrative.model_copy(
            update={
                "degraded": False,
                "source": "fallback",
                "failure_notice": "Narrative provider unavailable: timeout",
                "warnings": ["Narrative provider unavailable: timeout"],
            }
        )
        persisted = report_service_module.persist_analysis_report(
            parse_batch, assessment, contradictory_narrative
        )
        fetched = report_service_module.fetch_analysis_report(persisted["id"])

        self.assertTrue(persisted["narrative_degraded"])
        assert fetched is not None
        self.assertTrue(fetched["narrative_degraded"])
        self.assertEqual(fetched["narrative_source"], "fallback")
        self.assertEqual(
            fetched["narrative_failure_notice"],
            "Narrative provider unavailable: timeout",
        )

    def test_fetch_analysis_report_marks_legacy_unavailable_narrative_degraded(
        self,
    ) -> None:
        warning_cases = [
            (
                ["Narrative provider unavailable: provider offline"],
                "Narrative provider unavailable: provider offline",
            ),
            (
                ["Narrative setup unavailable: skill context failed"],
                "Narrative setup unavailable: skill context failed",
            ),
            ([], None),
        ]
        for warnings, expected_notice in warning_cases:
            for narrative_source, expected_source in (
                (None, None),
                ("", None),
                ("legacy-provider", None),
            ):
                with self.subTest(
                    warnings=warnings,
                    narrative_source=narrative_source,
                ):
                    project = project_service_module.ensure_default_project()
                    with database_module.SessionLocal() as session:
                        report = analysis_reports_repository_module.create_analysis_report(
                            session,
                            project_id=project.id,
                            risk_score=42,
                            severity="medium",
                            recommendation="caution",
                            top_risk="Terraform changed a security group.",
                            report_schema_version="v2",
                            parse_summary="1 parsed, 0 failed, 0 skipped, 1 normalized change",
                            narrative_opening="",
                            narrative_explanation="",
                            warnings_json=json.dumps(warnings),
                            contributors_json="[]",
                            analyzed_files_json='["plan.json"]',
                            submission_manifest_json="{}",
                            submission_manifest_fallback_json="[]",
                            blast_radius_json="{}",
                            rollback_plan_json="{}",
                            llm_provider="ollama",
                            llm_model="ollama/llama3",
                            llm_local_mode="true",
                            assessment_source="heuristic-only",
                            narrative_source=narrative_source,
                            narrative_skills_json="[]",
                            source_interface="api",
                            trigger_type="session",
                            trigger_id="legacy-narrative-source",
                            dashboard_display_duration_seconds=None,
                            findings_payload=[],
                            evidence_payload=[],
                        )
                        report_id = report.id

                    fetched = report_service_module.fetch_analysis_report(report_id)

                    assert fetched is not None
                    self.assertFalse(fetched["narrative_available"])
                    self.assertTrue(fetched["narrative_degraded"])
                    self.assertEqual(fetched["narrative_source"], expected_source)
                    self.assertEqual(
                        fetched["narrative_failure_notice"],
                        expected_notice,
                    )

    def test_fetch_analysis_report_does_not_allow_stored_false_to_mask_failure(
        self,
    ) -> None:
        project = project_service_module.ensure_default_project()
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                project_id=project.id,
                risk_score=42,
                severity="medium",
                recommendation="caution",
                top_risk="Terraform changed a security group.",
                report_schema_version="v2",
                parse_summary="1 parsed, 0 failed, 0 skipped, 1 normalized change",
                narrative_opening="",
                narrative_explanation="",
                narrative_degraded=False,
                narrative_failure_notice="Narrative provider unavailable: timeout",
                warnings_json=json.dumps(["Narrative provider unavailable: timeout"]),
                contributors_json="[]",
                analyzed_files_json='["plan.json"]',
                submission_manifest_json="{}",
                submission_manifest_fallback_json="[]",
                blast_radius_json="{}",
                rollback_plan_json="{}",
                llm_provider="openai",
                llm_model="gpt-4.1-mini",
                llm_local_mode="false",
                assessment_source="heuristic-only",
                narrative_source="fallback",
                narrative_skills_json="[]",
                source_interface="api",
                trigger_type="session",
                trigger_id="stored-false-fallback",
                dashboard_display_duration_seconds=None,
                findings_payload=[],
                evidence_payload=[],
            )
            report_id = report.id

        fetched = report_service_module.fetch_analysis_report(report_id)

        assert fetched is not None
        self.assertFalse(fetched["narrative_available"])
        self.assertTrue(fetched["narrative_degraded"])
        self.assertEqual(fetched["narrative_source"], "fallback")
        self.assertEqual(
            fetched["narrative_failure_notice"],
            "Narrative provider unavailable: timeout",
        )

    def test_fetch_analysis_report_marks_invisible_narrative_text_degraded(
        self,
    ) -> None:
        project = project_service_module.ensure_default_project()
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                project_id=project.id,
                risk_score=42,
                severity="medium",
                recommendation="caution",
                top_risk="Terraform changed a security group.",
                report_schema_version="v2",
                parse_summary="1 parsed, 0 failed, 0 skipped, 1 normalized change",
                narrative_opening="\u200b",
                narrative_explanation="\u0301",
                warnings_json="[]",
                contributors_json="[]",
                analyzed_files_json='["plan.json"]',
                submission_manifest_json="{}",
                submission_manifest_fallback_json="[]",
                blast_radius_json="{}",
                rollback_plan_json="{}",
                llm_provider="openai",
                llm_model="gpt-4.1-mini",
                llm_local_mode="false",
                assessment_source="heuristic-only",
                narrative_source="llm",
                narrative_skills_json="[]",
                source_interface="api",
                trigger_type="session",
                trigger_id="legacy-invisible-narrative",
                dashboard_display_duration_seconds=None,
                findings_payload=[],
                evidence_payload=[],
            )
            report_id = report.id

        fetched = report_service_module.fetch_analysis_report(report_id)

        assert fetched is not None
        self.assertFalse(fetched["narrative_available"])
        self.assertTrue(fetched["narrative_degraded"])
        self.assertEqual(fetched["narrative_source"], "llm")

    def test_fetch_analysis_report_marks_failure_notice_with_visible_text_degraded(
        self,
    ) -> None:
        project = project_service_module.ensure_default_project()
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.create_analysis_report(
                session,
                project_id=project.id,
                risk_score=42,
                severity="medium",
                recommendation="caution",
                top_risk="Terraform changed a security group.",
                report_schema_version="v2",
                parse_summary="1 parsed, 0 failed, 0 skipped, 1 normalized change",
                narrative_opening="Fallback summary text",
                narrative_explanation="Fallback explanation text",
                warnings_json=json.dumps(
                    ["Narrative provider unavailable: provider offline"]
                ),
                contributors_json="[]",
                analyzed_files_json='["plan.json"]',
                submission_manifest_json="{}",
                submission_manifest_fallback_json="[]",
                blast_radius_json="{}",
                rollback_plan_json="{}",
                llm_provider="ollama",
                llm_model="ollama/llama3",
                llm_local_mode="true",
                assessment_source="heuristic-only",
                narrative_source=None,
                narrative_skills_json="[]",
                source_interface="api",
                trigger_type="session",
                trigger_id="legacy-visible-fallback",
                dashboard_display_duration_seconds=None,
                findings_payload=[],
                evidence_payload=[],
            )
            report_id = report.id

        fetched = report_service_module.fetch_analysis_report(report_id)

        assert fetched is not None
        self.assertTrue(fetched["narrative_available"])
        self.assertTrue(fetched["narrative_degraded"])
        self.assertEqual(fetched["narrative_source"], None)
        self.assertEqual(
            fetched["narrative_failure_notice"],
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
            findings=[
                Finding(
                    finding_id="finding-dashboard-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Security group changes can affect production ingress.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-dashboard-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-dashboard-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
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

    def test_persist_analysis_report_backfills_supported_severe_top_risk_contributors(
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
            score=75,
            severity="high",
            recommendation="no-go",
            top_risk="HIGH: security group exposure risk.",
            top_risk_contributors=[],
            contributors=[
                RiskContributor(
                    evidence_id="ev-high",
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
            opening_sentence="NO-GO: deterministic severe risk.",
            explanation="The linked plan evidence supports the severe finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-high",
                    analysis_id=0,
                    title="HIGH: aws_security_group.main",
                    description="Security group changes can affect production ingress.",
                    severity="high",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-high"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-high",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        persisted_evidence_id = report["evidence_items"][0]["evidence_id"]
        self.assertEqual(report["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(
            report["contributors"][0]["evidence_id"], persisted_evidence_id
        )

    def test_persist_analysis_report_rewrites_cross_finding_top_risk_contributors(
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
                        ),
                        UnifiedChange(
                            source_file="plan.json",
                            tool="terraform",
                            resource_id="aws_db_instance.primary",
                            action="modify",
                            summary="Terraform changed a database.",
                        ),
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=92,
            severity="critical",
            recommendation="no-go",
            top_risk="CRITICAL: security group exposure risk.",
            top_risk_contributors=["ev-critical", "ev-high"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-critical",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=80,
                    summary="Terraform changed a security group.",
                    severity="critical",
                    reasoning="Critical ingress exposure.",
                ),
                RiskContributor(
                    evidence_id="ev-high",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_db_instance.primary",
                    action="modify",
                    contribution=50,
                    summary="Terraform changed a database.",
                    severity="high",
                    reasoning="High database exposure.",
                ),
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_iam_role.unlinked",
                    action="modify",
                    contribution=40,
                    summary="Unlinked stale severe rationale.",
                    severity="critical",
                    reasoning="This contributor is not tied to selected evidence.",
                ),
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_iam_policy.unlinked",
                    action="modify",
                    contribution=0,
                    summary="CRITICAL: unsupported inferred admin access.",
                    reasoning="This zero-impact stale rationale is not parser metadata.",
                ),
                RiskContributor(
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="data.aws_ami.selected",
                    action="read",
                    contribution=0,
                    summary="Terraform read a data source.",
                    metadata={"unknown_after_apply": ["id"]},
                ),
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="NO-GO: deterministic critical risk.",
            explanation="The linked plan evidence supports the critical finding.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-critical",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.main",
                    description="Security group changes can affect production ingress.",
                    severity="critical",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-critical"],
                    skill_id=None,
                ),
                Finding(
                    finding_id="finding-high",
                    analysis_id=0,
                    title="HIGH: aws_db_instance.primary",
                    description="Database changes can affect production data.",
                    severity="high",
                    category="data/service",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-high"],
                    skill_id=None,
                ),
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-critical",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="critical",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                ),
                EvidenceItem(
                    evidence_id="ev-high",
                    analysis_id=0,
                    finding_id="pending:change-2",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_db_instance.primary?action=modify"
                    ),
                    summary="Terraform changed a database.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-2"],
                ),
            ],
        )

        critical_evidence_id = next(
            item["evidence_id"]
            for item in report["evidence_items"]
            if item["resource"] == "aws_security_group.main"
        )
        self.assertEqual(report["top_risk_contributors"], [critical_evidence_id])
        self.assertEqual(
            [contributor["evidence_id"] for contributor in report["contributors"]],
            [critical_evidence_id, None],
        )
        self.assertNotIn(
            "unsupported inferred admin access",
            " ".join(
                str(contributor.get("summary") or "")
                for contributor in report["contributors"]
            ),
        )
        self.assertEqual(
            report["contributors"][1]["metadata"]["unknown_after_apply"],
            ["id"],
        )

    def test_persist_analysis_report_preserves_medium_evidence_links_when_cleaning_verdict_text(
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
            score=50,
            severity="medium",
            recommendation="caution",
            top_risk="NO-GO because security group review remains pending.",
            top_risk_contributors=["ev-medium"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-medium",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id="aws_security_group.main",
                    action="modify",
                    contribution=20,
                    summary="Terraform changed a security group.",
                    severity="medium",
                    reasoning="Review remains pending.",
                )
            ],
            interaction_risks=[],
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="CRITICAL due to stale narrative copy.",
            explanation="NO-GO because stale narrative copy remains.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        report = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            findings=[
                Finding(
                    finding_id="finding-medium",
                    analysis_id=0,
                    title="MEDIUM: aws_security_group.main",
                    description="Security group changes require review.",
                    severity="medium",
                    category="networking/ingress",
                    deterministic=True,
                    confidence=1.0,
                    uncertainty_note=None,
                    evidence_refs=["ev-medium"],
                    skill_id=None,
                )
            ],
            evidence_items=[
                EvidenceItem(
                    evidence_id="ev-medium",
                    analysis_id=0,
                    finding_id="pending:change-1",
                    source_type="artifact",
                    source_ref=(
                        "terraform://plan.json#aws_security_group.main?action=modify"
                    ),
                    summary="Terraform changed a security group.",
                    severity_hint="medium",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
        )

        persisted_evidence_id = report["evidence_items"][0]["evidence_id"]
        self.assertNotIn("NO-GO", report["top_risk"])
        self.assertNotIn("CRITICAL due to", report["narrative_opening"])
        self.assertEqual(report["top_risk_contributors"], [persisted_evidence_id])
        self.assertEqual(
            report["contributors"][0]["evidence_id"], persisted_evidence_id
        )

    def test_fetch_filtered_history_page_includes_evidence_payloads(self) -> None:
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

        self.assertEqual(
            page["items"][0]["evidence_items"][0]["source_ref"],
            "terraform://plan.json#aws_security_group.main?action=modify",
        )

    def test_fetch_filtered_history_page_uses_lightweight_scope_for_diff_candidates(
        self,
    ) -> None:
        scope_report = object()
        page_report = object()

        def serialize(report: object, *, include_evidence: bool = True) -> dict:
            evidence_items = [{"evidence_id": "page-ev"}] if include_evidence else []
            return {
                "id": 2 if report is page_report else 1,
                "project": {"id": 1, "project_key": "unassigned"},
                "workspace": None,
                "risk_score": 12,
                "severity": "low",
                "recommendation": "go",
                "created_at": "2026-05-25T00:00:00+00:00",
                "audit": {
                    "files_analyzed": ["plan.json"],
                    "source_interface": "api",
                    "trigger_type": "api_request",
                    "trigger_id": "review-fix",
                },
                "submission_manifest": {
                    "items": [
                        {
                            "name": "plan.json",
                            "tool": "terraform",
                            "status": "accepted",
                            "intake_status": "ready",
                            "parse_status": "parsed",
                            "partial": False,
                        }
                    ]
                },
                "evidence_items": evidence_items,
            }

        with (
            patch.object(
                report_service_module,
                "list_analysis_reports",
                side_effect=[[scope_report], [page_report]],
            ) as list_reports,
            patch.object(
                report_service_module,
                "_serialize_report",
                side_effect=serialize,
            ) as serialize_report,
            patch.object(
                report_service_module,
                "count_analysis_reports",
                return_value=1,
            ),
        ):
            page = report_service_module.fetch_filtered_analysis_history_page(
                page=1, page_size=1
            )

        self.assertEqual(
            page["items"][0]["evidence_items"], [{"evidence_id": "page-ev"}]
        )
        self.assertFalse(list_reports.call_args_list[0].kwargs["include_evidence"])
        self.assertTrue(list_reports.call_args_list[1].kwargs["include_evidence"])
        self.assertTrue(serialize_report.call_args_list[0].kwargs["include_evidence"])
        self.assertFalse(serialize_report.call_args_list[1].kwargs["include_evidence"])

    def test_persisted_advisory_keeps_evidence_gap_separate_from_partial_context(
        self,
    ) -> None:
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[
                            UnifiedChange(
                                source_file="plan.json",
                                tool="terraform",
                                resource_id="aws_s3_bucket.logs",
                                action="modify",
                                summary="Terraform adjusted log bucket tags.",
                            )
                        ],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Low risk tag update.",
                contributors=[],
                interaction_risks=[],
                context_completeness=ContextCompleteness(
                    context_score=0.8,
                    parser_success_rate=1.0,
                    evidence_success_rate=0.5,
                ),
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low risk tag update.",
                explanation="Review can follow the standard approval flow.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )

        advisory = report_service_module.fetch_analysis_report(report["id"])["advisory"]

        self.assertFalse(advisory["partial_context"])
        self.assertNotIn("partial_context", advisory["uncertainty_flags"])
        self.assertIn("evidence_gaps", advisory["uncertainty_flags"])
        self.assertTrue(advisory["requires_attention"])

    def test_persisted_advisory_honors_manifest_item_partial_context(
        self,
    ) -> None:
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[
                            UnifiedChange(
                                source_file="plan.json",
                                tool="terraform",
                                resource_id="aws_s3_bucket.logs",
                                action="modify",
                                summary="Terraform adjusted log bucket tags.",
                            )
                        ],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Low risk tag update.",
                contributors=[],
                interaction_risks=[],
                context_completeness=ContextCompleteness(
                    context_score=1.0,
                    parser_success_rate=1.0,
                    evidence_success_rate=1.0,
                ),
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low risk tag update.",
                explanation="Review can follow the standard approval flow.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )
        manifest = dict(report["submission_manifest"])
        manifest["partial_analysis"] = False
        manifest["items"][0]["partial"] = True
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id = ?",
                (json.dumps(manifest), report["id"]),
            )

        advisory = report_service_module.fetch_analysis_report(report["id"])["advisory"]

        self.assertTrue(advisory["partial_context"])
        self.assertIn("partial_context", advisory["uncertainty_flags"])
        self.assertTrue(advisory["requires_attention"])

    def test_persisted_advisory_honors_stored_partial_context_signal(self) -> None:
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[
                            UnifiedChange(
                                source_file="plan.json",
                                tool="terraform",
                                resource_id="aws_s3_bucket.logs",
                                action="modify",
                                summary="Terraform adjusted log bucket tags.",
                            )
                        ],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Low risk tag update.",
                contributors=[],
                interaction_risks=[],
                context_completeness=ContextCompleteness(
                    context_score=1.0,
                    parser_success_rate=1.0,
                    evidence_success_rate=1.0,
                ),
                partial_context=True,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low risk tag update.",
                explanation="Review can follow the standard approval flow.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )

        fetched = report_service_module.fetch_analysis_report(report["id"])
        advisory = fetched["advisory"]

        self.assertTrue(fetched["context_completeness"]["partial_context"])
        self.assertTrue(advisory["partial_context"])
        self.assertIn("partial_context", advisory["uncertainty_flags"])
        self.assertTrue(advisory["requires_attention"])

    def test_persisted_advisory_treats_false_like_strings_as_false(self) -> None:
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Low risk metadata-only update.",
                contributors=[],
                interaction_risks=[],
                context_completeness=ContextCompleteness(
                    context_score=1.0,
                    parser_success_rate=1.0,
                    evidence_success_rate=1.0,
                ),
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low risk metadata-only update.",
                explanation="Review can follow the standard approval flow.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )
        context = dict(report["context_completeness"])
        context["partial_context"] = "false"
        fallback_items = [
            {
                "name": "plan.json",
                "tool": "terraform",
                "status": "accepted",
                "intake_status": "accepted",
                "parse_status": "parsed",
                "partial": "0",
            }
        ]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE risk_assessments SET context_completeness_json = ? "
                "WHERE analysis_id = ?",
                (json.dumps(context), report["id"]),
            )
            conn.execute(
                "UPDATE analysis_reports "
                "SET submission_manifest_json = ?, submission_manifest_fallback_json = ? "
                "WHERE id = ?",
                ("{not-valid-json", json.dumps(fallback_items), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])
        advisory = fetched["advisory"]

        self.assertFalse(fetched["context_completeness"]["partial_context"])
        self.assertFalse(fetched["submission_manifest_fallback"][0]["partial"])
        self.assertFalse(advisory["partial_context"])
        self.assertNotIn("partial_context", advisory["uncertainty_flags"])

    def test_report_advisory_builder_normalizes_false_like_boolean_strings(
        self,
    ) -> None:
        advisory = report_service_module.build_report_advisory_payload(
            {
                "severity": "low",
                "recommendation": "go",
                "top_risk": "Low risk metadata-only update.",
                "context_completeness": {
                    "context_score": 1.0,
                    "parser_success_rate": 1.0,
                    "evidence_success_rate": 1.0,
                    "insufficient_context": "false",
                    "partial_context": "false",
                },
                "narrative_available": "true",
                "narrative_degraded": "false",
                "warnings": [],
            }
        )

        self.assertFalse(advisory["requires_attention"])
        self.assertFalse(advisory["narrative_degraded"])
        self.assertNotIn("insufficient_context", advisory["uncertainty_flags"])
        self.assertNotIn("narrative_degraded", advisory["uncertainty_flags"])

    def test_report_advisory_builder_ignores_non_finite_boolean_signals(
        self,
    ) -> None:
        advisory = report_service_module.build_report_advisory_payload(
            {
                "severity": "low",
                "recommendation": "go",
                "top_risk": "Low risk metadata-only update.",
                "context_completeness": {
                    "context_score": 1.0,
                    "parser_success_rate": 1.0,
                    "evidence_success_rate": 1.0,
                    "insufficient_context": math.inf,
                    "partial_context": math.nan,
                },
                "narrative_available": "true",
                "narrative_degraded": math.nan,
                "warnings": [],
            }
        )

        self.assertFalse(advisory["requires_attention"])
        self.assertFalse(advisory["partial_context"])
        self.assertFalse(advisory["narrative_degraded"])
        self.assertNotIn("insufficient_context", advisory["uncertainty_flags"])
        self.assertNotIn("partial_context", advisory["uncertainty_flags"])
        self.assertNotIn("narrative_degraded", advisory["uncertainty_flags"])

    def test_legacy_context_partial_context_matches_recovered_manifest_signal(
        self,
    ) -> None:
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=12,
                severity="low",
                recommendation="go",
                top_risk="Low risk metadata-only update.",
                contributors=[],
                interaction_risks=[],
                context_completeness=ContextCompleteness(
                    context_score=1.0,
                    parser_success_rate=1.0,
                    evidence_success_rate=1.0,
                ),
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low risk metadata-only update.",
                explanation="Review can follow the standard approval flow.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )
        context = dict(report["context_completeness"])
        context.pop("partial_context", None)
        fallback_items = [
            {
                "name": "broken.tf",
                "tool": "terraform",
                "status": "failed",
                "intake_status": "accepted",
                "parse_status": "failed",
            }
        ]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE risk_assessments SET context_completeness_json = ? "
                "WHERE analysis_id = ?",
                (json.dumps(context), report["id"]),
            )
            conn.execute(
                "UPDATE analysis_reports "
                "SET submission_manifest_json = ?, submission_manifest_fallback_json = ? "
                "WHERE id = ?",
                ("{not-valid-json", json.dumps(fallback_items), report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])

        self.assertTrue(fetched["context_completeness"]["partial_context"])
        self.assertTrue(fetched["advisory"]["partial_context"])
        self.assertIn("partial_context", fetched["advisory"]["uncertainty_flags"])

    def test_persisted_advisory_normalizes_legacy_severity_values(self) -> None:
        report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=75,
                severity="high",
                recommendation="no-go",
                top_risk="Security group exposure.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="NO-GO: security group exposure.",
                explanation="Review before deployment.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET severity = ?, recommendation = ? WHERE id = ?",
                ("HIGH", "NO-GO", report["id"]),
            )

        fetched = report_service_module.fetch_analysis_report(report["id"])
        advisory = fetched["advisory"]

        self.assertEqual(fetched["severity"], "high")
        self.assertEqual(fetched["recommendation"], "no-go")
        self.assertEqual(advisory["severity"], "high")
        self.assertEqual(advisory["recommendation"], "no-go")

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

    def test_fetch_history_filters_by_time_toolchain_and_analysis_status(self) -> None:
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
                        file_name="prod-plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=91,
                severity="critical",
                recommendation="no-go",
                top_risk="Production ingress widened.",
                contributors=[
                    RiskContributor(
                        source_file="prod-plan.json",
                        tool="terraform",
                        resource_id="aws_security_group.main",
                        action="modify",
                        contribution=20,
                        summary="Production ingress widened.",
                    )
                ],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="NO-GO: production ingress widened.",
                explanation="Production report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
            project_id=project.id,
            workspace_id=prod.id,
            audit_context={"source_interface": "api"},
        )
        staging_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="staging-rollout.yaml",
                        tool="kubernetes",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=35,
                severity="medium",
                recommendation="caution",
                top_risk="Staging rollout image changed.",
                contributors=[
                    RiskContributor(
                        source_file="staging-rollout.yaml",
                        tool="kubernetes",
                        resource_id="deployment/payments",
                        action="modify",
                        contribution=12,
                        summary="Staging rollout image changed.",
                    )
                ],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: staging rollout image changed.",
                explanation="Fallback report.",
                guidance=[],
                degraded=True,
                warnings=["Narrative used fallback mode."],
                source="fallback",
            ),
            project_id=project.id,
            workspace_id=staging.id,
            audit_context={"source_interface": "api"},
        )
        degraded_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="staging-policy.yaml",
                        tool="kubernetes",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=44,
                severity="medium",
                recommendation="caution",
                top_risk="Staging policy degraded narrative.",
                contributors=[
                    RiskContributor(
                        source_file="staging-policy.yaml",
                        tool="kubernetes",
                        resource_id="network-policy/payments",
                        action="modify",
                        contribution=10,
                        summary="Staging policy degraded narrative.",
                    )
                ],
                interaction_risks=[],
                partial_context=True,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: degraded narrative.",
                explanation="LLM report degraded by partial context.",
                guidance=[],
                degraded=True,
                warnings=["Narrative degraded by partial context."],
                source="llm",
            ),
            project_id=project.id,
            workspace_id=staging.id,
            audit_context={"source_interface": "api"},
        )
        legacy_degraded_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="legacy-policy.yaml",
                        tool="kubernetes",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=46,
                severity="medium",
                recommendation="caution",
                top_risk="Legacy narrative failure notice.",
                contributors=[
                    RiskContributor(
                        source_file="legacy-policy.yaml",
                        tool="kubernetes",
                        resource_id="network-policy/legacy",
                        action="modify",
                        contribution=10,
                        summary="Legacy narrative failure notice.",
                    )
                ],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: legacy narrative failure notice.",
                explanation="Legacy report serialized as degraded by failure notice.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
            project_id=project.id,
            workspace_id=staging.id,
            audit_context={"source_interface": "api"},
        )
        misleading_tool_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="terraform-notes.yaml",
                        tool="kubernetes",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=43,
                severity="medium",
                recommendation="caution",
                top_risk="Kubernetes notes changed.",
                contributors=[
                    RiskContributor(
                        source_file="terraform-notes.yaml",
                        tool="kubernetes",
                        resource_id="deployment/notes",
                        action="modify",
                        contribution=8,
                        summary="Kubernetes notes changed.",
                    )
                ],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: kubernetes notes changed.",
                explanation="Kubernetes report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
            project_id=project.id,
            workspace_id=prod.id,
            audit_context={"source_interface": "api"},
        )
        old_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="old-plan.json",
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
                top_risk="Old production review.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: old production review.",
                explanation="Old report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
            project_id=project.id,
            workspace_id=prod.id,
            audit_context={"source_interface": "api"},
        )
        unreadable_schema_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="legacy-release.yaml",
                        tool="ansible",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=63,
                severity="high",
                recommendation="caution",
                top_risk="Legacy release metadata changed.",
                contributors=[
                    RiskContributor(
                        source_file="legacy-release.yaml",
                        tool="ansible",
                        resource_id="release/payments",
                        action="modify",
                        contribution=12,
                        summary="Legacy release metadata changed.",
                    )
                ],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: legacy release metadata changed.",
                explanation="Legacy report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
            project_id=project.id,
            workspace_id=prod.id,
            audit_context={"source_interface": "api"},
        )
        with database_module.SessionLocal() as session:
            session.get(
                tables_module.AnalysisReport, prod_report["id"]
            ).created_at = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
            session.get(
                tables_module.AnalysisReport, staging_report["id"]
            ).created_at = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
            session.get(
                tables_module.AnalysisReport, degraded_report["id"]
            ).created_at = datetime(2026, 5, 19, 13, 0, tzinfo=UTC)
            legacy_degraded = session.get(
                tables_module.AnalysisReport, legacy_degraded_report["id"]
            )
            legacy_degraded.created_at = datetime(2026, 5, 19, 13, 30, tzinfo=UTC)
            legacy_degraded.narrative_degraded = None
            legacy_degraded.narrative_failure_notice = "LLM narrative unavailable."
            session.get(
                tables_module.AnalysisReport, misleading_tool_report["id"]
            ).created_at = datetime(2026, 5, 19, 14, 0, tzinfo=UTC)
            old = session.get(tables_module.AnalysisReport, old_report["id"])
            old.created_at = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
            old.contributors_json = "[]"
            old.analyzed_files_json = "[]"
            old.submission_manifest_json = "{}"
            old.submission_manifest_fallback_json = json.dumps(
                [
                    {
                        "name": "legacy-template.yaml",
                        "tool": "cloudformation",
                        "status": "accepted",
                    }
                ]
            )
            legacy = session.get(
                tables_module.AnalysisReport, unreadable_schema_report["id"]
            )
            legacy.created_at = datetime(2026, 5, 19, 15, 0, tzinfo=UTC)
            legacy.report_schema_version = "v999"
            session.commit()

        filtered = report_service_module.fetch_filtered_analysis_history_page(
            project_key=project.project_key,
            workspace_key=prod.workspace_key,
            severity="medium",
            recommendation="caution",
            toolchain="terraform",
            analysis_status="complete",
            created_from=datetime(2026, 5, 1, tzinfo=UTC),
            created_to=datetime(2026, 5, 20, tzinfo=UTC),
            skip_unreadable_schema=True,
        )
        degraded = report_service_module.fetch_filtered_analysis_history_page(
            project_key=project.project_key,
            toolchain="kubernetes",
            analysis_status="degraded",
            skip_unreadable_schema=True,
        )
        fallback = report_service_module.fetch_filtered_analysis_history_page(
            project_key=project.project_key,
            toolchain="kubernetes",
            analysis_status="fallback",
            skip_unreadable_schema=True,
        )
        fallback_manifest_tool = (
            report_service_module.fetch_filtered_analysis_history_page(
                project_key=project.project_key,
                toolchain="cloudformation",
                skip_unreadable_schema=True,
            )
        )
        toolchains = report_service_module.fetch_history_toolchains(
            project_key=project.project_key,
        )
        readable_toolchains = report_service_module.fetch_history_toolchains(
            project_key=project.project_key,
            skip_unreadable_schema=True,
        )
        staging_toolchains = report_service_module.fetch_history_toolchains(
            project_key=project.project_key,
            workspace_key=staging.workspace_key,
            skip_unreadable_schema=True,
        )

        self.assertEqual(filtered["total_count"], 1)
        self.assertEqual(filtered["items"][0]["id"], prod_report["id"])
        self.assertEqual(filtered["items"][0]["tool_mix"], ["terraform"])
        self.assertEqual(filtered["items"][0]["analysis_status"], "complete")
        self.assertEqual(degraded["total_count"], 2)
        self.assertEqual(
            {item["id"] for item in degraded["items"]},
            {degraded_report["id"], legacy_degraded_report["id"]},
        )
        self.assertTrue(
            all(item["tool_mix"] == ["kubernetes"] for item in degraded["items"])
        )
        self.assertTrue(
            all(item["analysis_status"] == "degraded" for item in degraded["items"])
        )
        self.assertEqual(fallback["total_count"], 1)
        self.assertEqual(fallback["items"][0]["id"], staging_report["id"])
        self.assertEqual(fallback["items"][0]["tool_mix"], ["kubernetes"])
        self.assertEqual(fallback["items"][0]["analysis_status"], "fallback")
        self.assertEqual(fallback_manifest_tool["total_count"], 1)
        self.assertEqual(fallback_manifest_tool["items"][0]["id"], old_report["id"])
        self.assertEqual(
            fallback_manifest_tool["items"][0]["tool_mix"],
            ["cloudformation"],
        )
        self.assertEqual(
            toolchains,
            ["ansible", "cloudformation", "kubernetes", "terraform"],
        )
        self.assertEqual(
            readable_toolchains,
            ["cloudformation", "kubernetes", "terraform"],
        )
        self.assertEqual(staging_toolchains, ["kubernetes"])

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

    def test_previous_scan_diffs_do_not_cross_workflow_contexts(self) -> None:
        first = self._persist_comparison_report(
            score=40,
            severity="medium",
            recommendation="caution",
            top_risk="Interactive review",
            findings=[],
            evidence_items=[],
            audit_context={"source_interface": "api", "trigger_type": "session"},
        )
        second = self._persist_comparison_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Pull request review",
            findings=[],
            evidence_items=[],
            audit_context={"source_interface": "api", "trigger_type": "pull_request"},
        )

        comparison = report_service_module.fetch_report_comparison(second["id"])
        explicit_comparison = report_service_module.fetch_report_comparison(
            second["id"],
            previous_report_id=first["id"],
        )
        history = report_service_module.fetch_filtered_analysis_history_page()
        by_id = {item["id"]: item for item in history["items"]}

        self.assertIsNone(comparison)
        self.assertIsNone(explicit_comparison)
        self.assertNotIn("previous_scan_diff", by_id[int(second["id"])])

    def test_previous_scan_diffs_do_not_cross_trigger_ids(self) -> None:
        first = self._persist_comparison_report(
            score=40,
            severity="medium",
            recommendation="caution",
            top_risk="First pull request review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "pull_request",
                "trigger_id": "pr-41",
            },
        )
        second = self._persist_comparison_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Second pull request review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "pull_request",
                "trigger_id": "pr-42",
            },
        )

        comparison = report_service_module.fetch_report_comparison(second["id"])
        explicit_comparison = report_service_module.fetch_report_comparison(
            second["id"],
            previous_report_id=first["id"],
        )
        history = report_service_module.fetch_filtered_analysis_history_page()
        by_id = {item["id"]: item for item in history["items"]}

        self.assertIsNone(comparison)
        self.assertIsNone(explicit_comparison)
        self.assertNotIn("previous_scan_diff", by_id[int(second["id"])])

    def test_previous_scan_diffs_normalize_workflow_contexts(self) -> None:
        first = self._persist_comparison_report(
            score=40,
            severity="medium",
            recommendation="caution",
            top_risk="Interactive review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": " API ",
                "trigger_type": " Session ",
                "trigger_id": " RUN-123 ",
            },
        )
        second = self._persist_comparison_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Same workflow review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "session",
                "trigger_id": "run-123",
            },
        )

        comparison = report_service_module.fetch_report_comparison(second["id"])
        explicit_comparison = report_service_module.fetch_report_comparison(
            second["id"],
            previous_report_id=first["id"],
        )
        history = report_service_module.fetch_filtered_analysis_history_page()
        by_id = {item["id"]: item for item in history["items"]}

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], first["id"])
        self.assertIsNotNone(explicit_comparison)
        self.assertEqual(
            by_id[int(second["id"])]["previous_scan_diff"]["previous_report_id"],
            first["id"],
        )

    def test_previous_scan_diffs_match_legacy_blank_workflow_context(
        self,
    ) -> None:
        first = self._persist_comparison_report(
            score=40,
            severity="medium",
            recommendation="caution",
            top_risk="Legacy review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session,
                int(first["id"]),
                include_evidence=True,
            )
            assert report is not None
            report.source_interface = None
            report.trigger_type = None
            report.trigger_id = None
            report.submission_manifest_json = "{}"
            session.commit()
        second = self._persist_comparison_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Current workflow review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "pull_request",
                "trigger_id": "pr-42",
            },
        )

        comparison = report_service_module.fetch_report_comparison(second["id"])
        explicit_comparison = report_service_module.fetch_report_comparison(
            second["id"],
            previous_report_id=first["id"],
        )
        history = report_service_module.fetch_filtered_analysis_history_page()
        by_id = {item["id"]: item for item in history["items"]}

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], first["id"])
        self.assertIsNotNone(explicit_comparison)
        self.assertEqual(
            by_id[int(second["id"])]["previous_scan_diff"]["previous_report_id"],
            first["id"],
        )

    def test_previous_scan_diffs_prefer_exact_context_over_legacy_blank(
        self,
    ) -> None:
        exact = self._persist_comparison_report(
            score=40,
            severity="medium",
            recommendation="caution",
            top_risk="Exact workflow review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "pull_request",
                "trigger_id": "pr-42",
            },
        )
        legacy = self._persist_comparison_report(
            score=55,
            severity="medium",
            recommendation="caution",
            top_risk="Legacy blank workflow review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session,
                int(legacy["id"]),
                include_evidence=True,
            )
            assert report is not None
            report.source_interface = None
            report.trigger_type = None
            report.trigger_id = None
            report.submission_manifest_json = "{}"
            session.commit()
        current = self._persist_comparison_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Current workflow review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "pull_request",
                "trigger_id": "pr-42",
            },
        )

        comparison = report_service_module.fetch_report_comparison(current["id"])
        history = report_service_module.fetch_filtered_analysis_history_page()
        by_id = {item["id"]: item for item in history["items"]}

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], exact["id"])
        self.assertEqual(
            by_id[int(current["id"])]["previous_scan_diff"]["previous_report_id"],
            exact["id"],
        )

    def test_previous_scan_diffs_do_not_treat_partial_context_as_wildcard(
        self,
    ) -> None:
        first = self._persist_comparison_report(
            score=40,
            severity="medium",
            recommendation="caution",
            top_risk="Pull request review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "pull_request",
                "trigger_id": "pr-42",
            },
        )
        second = self._persist_comparison_report(
            score=88,
            severity="critical",
            recommendation="no-go",
            top_risk="Partial workflow review",
            findings=[],
            evidence_items=[],
            audit_context={
                "source_interface": "api",
                "trigger_type": "pull_request",
                "trigger_id": "",
            },
        )

        comparison = report_service_module.fetch_report_comparison(second["id"])
        explicit_comparison = report_service_module.fetch_report_comparison(
            second["id"],
            previous_report_id=first["id"],
        )
        history = report_service_module.fetch_filtered_analysis_history_page()
        by_id = {item["id"]: item for item in history["items"]}

        self.assertIsNone(comparison)
        self.assertIsNone(explicit_comparison)
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

    def test_filtered_history_ignores_unreadable_off_page_reports_for_diffs(
        self,
    ) -> None:
        readable = self._persist_comparison_report(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="Readable review",
            findings=[],
            evidence_items=[],
        )
        unreadable = self._persist_comparison_report(
            score=90,
            severity="critical",
            recommendation="no-go",
            top_risk="Future schema review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session, int(unreadable["id"]), include_evidence=True
            )
            assert report is not None
            report.report_schema_version = "v3"
            session.commit()

        history = report_service_module.fetch_filtered_analysis_history_page(
            severity="low",
            skip_unreadable_schema=True,
        )

        self.assertEqual(history["total_count"], 1)
        self.assertEqual(history["items"][0]["id"], readable["id"])

    def test_filtered_history_ignores_visible_unreadable_reports(self) -> None:
        readable = self._persist_comparison_report(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="Readable review",
            findings=[],
            evidence_items=[],
        )
        unreadable = self._persist_comparison_report(
            score=90,
            severity="critical",
            recommendation="no-go",
            top_risk="Future schema review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session,
                int(unreadable["id"]),
                include_evidence=True,
            )
            assert report is not None
            report.report_schema_version = "v3"
            session.commit()

        history = report_service_module.fetch_filtered_analysis_history_page(
            skip_unreadable_schema=True
        )

        item_ids = {item["id"] for item in history["items"]}
        self.assertIn(readable["id"], item_ids)
        self.assertNotIn(unreadable["id"], item_ids)

    def test_filtered_history_backfills_after_visible_unreadable_reports(
        self,
    ) -> None:
        readable = self._persist_comparison_report(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="Readable review",
            findings=[],
            evidence_items=[],
        )
        unreadable = self._persist_comparison_report(
            score=90,
            severity="critical",
            recommendation="no-go",
            top_risk="Future schema review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session,
                int(unreadable["id"]),
                include_evidence=True,
            )
            assert report is not None
            report.report_schema_version = "v3"
            session.commit()

        history = report_service_module.fetch_filtered_analysis_history_page(
            page=1,
            page_size=1,
            skip_unreadable_schema=True,
        )

        self.assertEqual(history["total_count"], 1)
        self.assertEqual([item["id"] for item in history["items"]], [readable["id"]])

    def test_filtered_history_includes_legacy_blank_schema_reports(self) -> None:
        blank_schema = self._persist_comparison_report(
            score=31,
            severity="low",
            recommendation="go",
            top_risk="Blank schema legacy review",
            findings=[],
            evidence_items=[],
        )
        future_schema = self._persist_comparison_report(
            score=90,
            severity="critical",
            recommendation="no-go",
            top_risk="Future schema review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            for report_id, schema_version in (
                (blank_schema["id"], ""),
                (future_schema["id"], "v3"),
            ):
                report = analysis_reports_repository_module.get_analysis_report(
                    session,
                    int(report_id),
                    include_evidence=True,
                )
                assert report is not None
                report.report_schema_version = schema_version
            session.commit()

        history = report_service_module.fetch_filtered_analysis_history_page(
            skip_unreadable_schema=True
        )

        self.assertEqual(history["total_count"], 1)
        self.assertEqual(
            {item["id"] for item in history["items"]},
            {blank_schema["id"]},
        )

    def test_fetch_report_comparison_uses_legacy_blank_schema_previous_report(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="Legacy previous review",
            findings=[],
            evidence_items=[],
        )
        current = self._persist_comparison_report(
            score=45,
            severity="medium",
            recommendation="caution",
            top_risk="Current readable review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session,
                int(previous["id"]),
                include_evidence=True,
            )
            assert report is not None
            report.report_schema_version = ""
            session.commit()

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])

    def test_filtered_history_skip_unreadable_keeps_database_pagination(
        self,
    ) -> None:
        for index in range(3):
            self._persist_comparison_report(
                score=30 + index,
                severity="low",
                recommendation="go",
                top_risk=f"Readable review {index}",
                findings=[],
                evidence_items=[],
            )
        original_list_analysis_reports = report_service_module.list_analysis_reports
        list_calls: list[dict[str, object]] = []

        def recording_list_analysis_reports(*args, **kwargs):
            list_calls.append(dict(kwargs))
            return original_list_analysis_reports(*args, **kwargs)

        with patch.object(
            report_service_module,
            "list_analysis_reports",
            side_effect=recording_list_analysis_reports,
        ):
            history = report_service_module.fetch_filtered_analysis_history_page(
                page=2,
                page_size=1,
                skip_unreadable_schema=True,
            )

        paged_calls = [
            call
            for call in list_calls
            if call.get("limit") == 1 and call.get("offset") == 1
        ]
        self.assertEqual(history["total_count"], 3)
        self.assertEqual(len(history["items"]), 1)
        self.assertEqual(len(paged_calls), 1)
        self.assertIsNotNone(paged_calls[0].get("report_schema_versions"))

    def test_fetch_report_comparison_ignores_unreadable_off_path_reports(
        self,
    ) -> None:
        previous = self._persist_comparison_report(
            score=30,
            severity="low",
            recommendation="go",
            top_risk="Readable previous review",
            findings=[],
            evidence_items=[],
        )
        unreadable = self._persist_comparison_report(
            score=90,
            severity="critical",
            recommendation="no-go",
            top_risk="Future schema review",
            findings=[],
            evidence_items=[],
        )
        current = self._persist_comparison_report(
            score=45,
            severity="medium",
            recommendation="caution",
            top_risk="Readable current review",
            findings=[],
            evidence_items=[],
        )
        with database_module.SessionLocal() as session:
            report = analysis_reports_repository_module.get_analysis_report(
                session,
                int(unreadable["id"]),
                include_evidence=True,
            )
            assert report is not None
            report.report_schema_version = "v3"
            session.commit()

        comparison = report_service_module.fetch_report_comparison(current["id"])

        self.assertIsNotNone(comparison)
        assert comparison is not None
        self.assertEqual(comparison["previous_report"]["id"], previous["id"])

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
