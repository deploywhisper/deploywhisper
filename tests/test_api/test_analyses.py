"""Tests for analysis history API routes."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from importlib import reload
from pathlib import Path
from unittest.mock import patch

import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.deployment_outcome_service as deployment_outcome_service_module
import services.project_service as project_service_module
import services.report_service as report_service_module
from analysis.blast_radius import BlastRadiusResult, ImpactNode
from api.schemas import BlastRadiusData, ContextCompletenessData, PersistedReportData
from services.analysis_service import AnalysisPersistenceError
from services.analysis_service import AnalysisRunResult
from analysis.rollback_planner import RollbackPlan
from analysis.incident_matcher import IncidentMatch
from analysis.risk_scorer import (
    INSUFFICIENT_CONTEXT_WARNING,
    RiskAssessment,
    RiskContributor,
)
from app import create_app
from evidence.models import ContextCompleteness, EvidenceItem
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange
from pydantic import ValidationError


class AnalysesApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "reports.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["APP_BASE_URL"] = "https://deploywhisper.example.com"
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(project_service_module)
        reload(report_service_module)
        reload(deployment_outcome_service_module)
        database_module.init_db()
        self.client = TestClient(create_app())

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
            context_completeness=ContextCompleteness(
                topology_freshness_days=0,
                topology_last_imported_at="2026-05-25T00:00:00Z",
                incident_index_size=1,
                incident_index_version="incidents:unknown",
                incident_index_freshness_status="current",
            ),
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
        self.persisted = report_service_module.persist_analysis_report(
            parse_batch, assessment, narrative
        )

    @staticmethod
    def _analysis_assessment(
        *,
        severity: str = "high",
        recommendation: str = "no-go",
        top_risk: str = "Security group exposure risk",
        resource_id: str = "aws_security_group.main",
        partial_context: bool = False,
    ) -> RiskAssessment:
        return RiskAssessment(
            score=72,
            severity=severity,
            recommendation=recommendation,
            top_risk=top_risk,
            top_risk_contributors=["ev-001"],
            contributors=[
                RiskContributor(
                    evidence_id="ev-001",
                    source_file="plan.json",
                    tool="terraform",
                    resource_id=resource_id,
                    action="modify",
                    contribution=20,
                    summary=top_risk,
                    severity=severity,
                    reasoning=top_risk,
                )
            ],
            interaction_risks=[],
            partial_context=partial_context,
            warnings=[],
            source="heuristic+llm",
        )

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("APP_BASE_URL", None)
        os.environ.pop("DEPLOYWHISPER_SHARE_TOKEN", None)
        self.tempdir.cleanup()

    def _analysis_result_with_persisted_report(
        self,
        persisted_report: dict,
        *,
        assessment: RiskAssessment | None = None,
        narrative: NarrativeResult | None = None,
    ) -> AnalysisRunResult:
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
        return AnalysisRunResult(
            parse_batch=parse_batch,
            evidence_items=[],
            findings=[],
            assessment=assessment
            or self._analysis_assessment(
                severity="low",
                recommendation="go",
                top_risk="Low risk metadata-only update.",
            ),
            blast_radius=BlastRadiusResult(
                affected=[],
                direct_count=0,
                transitive_count=0,
            ),
            rollback_plan=RollbackPlan(
                steps=[],
                complexity="low",
                complexity_score=1,
            ),
            incident_matches=[],
            narrative=narrative
            or NarrativeResult(
                opening_sentence="GO: low risk metadata-only update.",
                explanation="Review can follow the standard approval flow.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            persisted_report=persisted_report,
        )

    def test_list_analyses_returns_persisted_reports(self) -> None:
        response = self.client.get("/api/v1/analyses")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["api_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertEqual(payload["meta"]["report_schema_versions"], ["v2"])
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["meta"]["page"], 1)
        self.assertEqual(payload["meta"]["page_size"], 50)
        self.assertEqual(payload["data"][0]["advisory"]["advisory_only"], True)
        self.assertFalse(payload["data"][0]["advisory"]["should_block"])
        self.assertEqual(payload["data"][0]["advisory"]["recommendation"], "caution")
        self.assertEqual(payload["data"][0]["score"], 42)
        self.assertEqual(payload["data"][0]["verdict"], "caution")
        self.assertEqual(payload["data"][0]["filenames"], ["plan.json"])
        self.assertEqual(payload["data"][0]["workspace_label"], "Unassigned")
        self.assertEqual(payload["data"][0]["env_label"], "default")
        self.assertIsNone(payload["data"][0]["trigger_ref"])
        self.assertIsNone(payload["data"][0]["pr_ref"])

    def test_list_analyses_rejects_reversed_activity_window(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={
                "created_from": "2026-06-08T00:00:00Z",
                "created_to": "2026-06-01T00:00:00Z",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_time_window")
        self.assertIn("created_from", payload["error"]["message"])

    def test_list_analyses_meta_matches_legacy_report_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET report_schema_version = '' WHERE id = ?",
                (self.persisted["id"],),
            )

        response = self.client.get("/api/v1/analyses")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"][0]["report_schema_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_versions"], ["v1"])

    def test_list_analyses_meta_reports_mixed_schema_versions(self) -> None:
        report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="next-plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=10,
                severity="low",
                recommendation="go",
                top_risk="Second report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: second report.",
                explanation="Second report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET report_schema_version = '' WHERE id = ?",
                (self.persisted["id"],),
            )

        response = self.client.get("/api/v1/analyses")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertEqual(payload["meta"]["report_schema_versions"], ["v1", "v2"])
        self.assertEqual(
            {report["report_schema_version"] for report in payload["data"]},
            {"v1", "v2"},
        )

    def test_list_analyses_rejects_newer_report_schema_versions(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET report_schema_version = 'v3' WHERE id = ?",
                (self.persisted["id"],),
            )

        response = self.client.get("/api/v1/analyses")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["code"], "unsupported_report_schema_version"
        )

    def test_list_analyses_defaults_to_unassigned_scope(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        report_service_module.persist_analysis_report(
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
                top_risk="Scoped project report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: scoped project report.",
                explanation="Scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )

        response = self.client.get("/api/v1/analyses")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["data"][0]["project"]["project_key"], "unassigned")

    def test_get_analysis_returns_single_report(self) -> None:
        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["id"], self.persisted["id"])
        self.assertEqual(payload["meta"]["api_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertEqual(payload["data"]["report_schema_version"], "v2")
        self.assertEqual(payload["data"]["advisory"]["advisory_only"], True)
        self.assertFalse(payload["data"]["advisory"]["should_block"])
        self.assertTrue(payload["data"]["advisory"]["requires_attention"])
        self.assertEqual(payload["data"]["advisory"]["recommendation"], "caution")
        self.assertEqual(payload["data"]["audit"]["llm_provider"], "ollama")
        self.assertEqual(payload["data"]["blast_radius"]["direct_count"], 0)

    def test_blast_radius_api_schema_preserves_topology_context_fields(self) -> None:
        blast_radius = BlastRadiusData.model_validate(
            BlastRadiusResult(
                affected=[
                    ImpactNode(
                        service_id="api",
                        label="API Service",
                        depth=1,
                        dependencies=["database"],
                        owners=["payments"],
                    )
                ],
                direct_count=0,
                transitive_count=1,
                context_source={"type": "custom", "ref": "topology.json"},
                freshness={"updated_at": "2026-06-08T12:00:00Z", "age_days": 1},
                context_state="current",
                context_limitations=[],
            ).model_dump()
        )

        payload = blast_radius.model_dump()
        self.assertEqual(payload["affected"][0]["dependencies"], ["database"])
        self.assertEqual(payload["affected"][0]["owners"], ["payments"])
        self.assertEqual(
            payload["context_source"],
            {"type": "custom", "ref": "topology.json"},
        )
        self.assertEqual(
            payload["freshness"],
            {"updated_at": "2026-06-08T12:00:00Z", "age_days": 1},
        )
        self.assertEqual(payload["context_state"], "current")
        self.assertEqual(payload["context_limitations"], [])

    def test_blast_radius_api_schema_fills_partial_context_defaults(self) -> None:
        blast_radius = BlastRadiusData.model_validate(
            {
                "affected": [],
                "direct_count": 0,
                "transitive_count": 0,
                "context_source": {"type": "custom"},
                "freshness": {"updated_at": "2026-06-08T12:00:00Z"},
            }
        )

        payload = blast_radius.model_dump()
        self.assertEqual(payload["context_source"], {"type": "custom", "ref": None})
        self.assertEqual(
            payload["freshness"],
            {"updated_at": "2026-06-08T12:00:00Z", "age_days": None},
        )

    def test_blast_radius_api_schema_drops_malformed_additive_fields(self) -> None:
        blast_radius = BlastRadiusData.model_validate(
            {
                "affected": [
                    {
                        "service_id": "api",
                        "label": "API Service",
                        "depth": 0,
                        "dependencies": None,
                        "owners": None,
                    }
                ],
                "direct_count": 1,
                "transitive_count": 0,
                "context_source": "legacy",
                "freshness": "unknown",
                "context_limitations": "legacy",
            }
        )

        payload = blast_radius.model_dump()
        self.assertEqual(payload["affected"][0]["dependencies"], [])
        self.assertEqual(payload["affected"][0]["owners"], [])
        self.assertEqual(payload["context_source"], {"type": None, "ref": None})
        self.assertEqual(payload["freshness"], {"updated_at": None, "age_days": None})
        self.assertEqual(payload["context_limitations"], [])

    def test_blast_radius_api_schema_drops_malformed_nested_additive_fields(
        self,
    ) -> None:
        blast_radius = BlastRadiusData.model_validate(
            {
                "affected": [],
                "direct_count": 0,
                "transitive_count": 0,
                "context_source": {"type": {"kind": "custom"}, "ref": "topology.json"},
                "freshness": {"updated_at": {"bad": "value"}, "age_days": []},
                "context_state": {"state": "missing"},
            }
        )

        payload = blast_radius.model_dump()
        self.assertEqual(
            payload["context_source"], {"type": None, "ref": "topology.json"}
        )
        self.assertEqual(payload["freshness"], {"updated_at": None, "age_days": None})
        self.assertEqual(payload["context_state"], "unknown")

    def test_blast_radius_api_schema_normalizes_null_context_state(self) -> None:
        blast_radius = BlastRadiusData.model_validate(
            {
                "affected": [],
                "direct_count": 0,
                "transitive_count": 0,
                "context_state": None,
            }
        )

        self.assertEqual(blast_radius.model_dump()["context_state"], "unknown")

    def test_get_analysis_preserves_go_advisory_with_narrative_warning(self) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="low-risk-plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="low-risk-plan.json",
                            tool="terraform",
                            resource_id="aws_s3_bucket.logs",
                            action="modify",
                            summary="Terraform adjusted log bucket tags.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=12,
            severity="low",
            recommendation="go",
            top_risk="Low risk tag update.",
            contributors=[
                RiskContributor(
                    source_file="low-risk-plan.json",
                    tool="terraform",
                    resource_id="aws_s3_bucket.logs",
                    action="modify",
                    contribution=12,
                    summary="Terraform adjusted log bucket tags.",
                    severity="low",
                    reasoning="Low risk tag update.",
                )
            ],
            interaction_risks=[],
            context_completeness=ContextCompleteness(
                topology_freshness_days=0,
                topology_last_imported_at="2026-05-25T00:00:00Z",
                incident_index_size=1,
                incident_index_version="incidents:unknown",
                incident_index_freshness_status="current",
            ),
            partial_context=False,
            warnings=[],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk tag update.",
            explanation="Review can follow the standard approval flow.",
            guidance=[],
            degraded=False,
            warnings=["Narrative provider warning."],
            source="llm",
        )
        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            submitted_artifacts=[("low-risk-plan.json", b"{}")],
        )

        response = self.client.get(f"/api/v1/analyses/{persisted['id']}")

        self.assertEqual(response.status_code, 200)
        advisory = response.json()["data"]["advisory"]
        self.assertEqual(advisory["recommendation"], "go")
        self.assertFalse(advisory["should_block"])
        self.assertFalse(advisory["requires_attention"])
        self.assertNotIn("assessment_warnings", advisory["uncertainty_flags"])
        self.assertIn("narrative_warnings", advisory["uncertainty_flags"])

    def test_list_analyses_preserves_go_advisory_with_narrative_warning(self) -> None:
        persisted = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="low-risk-list-plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[
                            UnifiedChange(
                                source_file="low-risk-list-plan.json",
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
                    topology_freshness_days=0,
                    topology_last_imported_at="2026-05-25T00:00:00Z",
                    incident_index_size=1,
                    incident_index_version="incidents:unknown",
                    incident_index_freshness_status="current",
                ),
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: low risk tag update.",
                explanation="Review can follow the standard approval flow.",
                guidance=[],
                degraded=False,
                warnings=["Narrative provider warning."],
                source="llm",
            ),
            submitted_artifacts=[("low-risk-list-plan.json", b"{}")],
        )

        response = self.client.get("/api/v1/analyses")

        self.assertEqual(response.status_code, 200)
        reports = response.json()["data"]
        report = next(item for item in reports if item["id"] == persisted["id"])
        advisory = report["advisory"]
        self.assertEqual(advisory["recommendation"], "go")
        self.assertFalse(advisory["requires_attention"])
        self.assertNotIn("assessment_warnings", advisory["uncertainty_flags"])
        self.assertIn("narrative_warnings", advisory["uncertainty_flags"])

    def test_get_analysis_flags_insufficient_context_as_assessment_warning(
        self,
    ) -> None:
        parse_batch = ParseBatchResult(
            files=[
                ParsedFileResult(
                    file_name="low-context-plan.json",
                    tool="terraform",
                    status="parsed",
                    changes=[
                        UnifiedChange(
                            source_file="low-context-plan.json",
                            tool="terraform",
                            resource_id="aws_s3_bucket.logs",
                            action="modify",
                            summary="Terraform adjusted log bucket tags.",
                        )
                    ],
                )
            ]
        )
        assessment = RiskAssessment(
            score=12,
            severity="low",
            recommendation="go",
            top_risk="Low risk tag update.",
            contributors=[
                RiskContributor(
                    source_file="low-context-plan.json",
                    tool="terraform",
                    resource_id="aws_s3_bucket.logs",
                    action="modify",
                    contribution=12,
                    summary="Terraform adjusted log bucket tags.",
                    severity="low",
                    reasoning="Low risk tag update.",
                )
            ],
            interaction_risks=[],
            context_completeness=ContextCompleteness(
                context_score=0.4,
                confidence_level="low",
                insufficient_context=True,
            ),
            partial_context=False,
            warnings=[INSUFFICIENT_CONTEXT_WARNING],
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk tag update.",
            explanation="Review can follow the standard approval flow.",
            guidance=[],
            degraded=False,
            warnings=[],
            source="llm",
        )
        persisted = report_service_module.persist_analysis_report(
            parse_batch,
            assessment,
            narrative,
            submitted_artifacts=[("low-context-plan.json", b"{}")],
        )

        response = self.client.get(f"/api/v1/analyses/{persisted['id']}")

        self.assertEqual(response.status_code, 200)
        advisory = response.json()["data"]["advisory"]
        self.assertTrue(advisory["requires_attention"])
        self.assertIn("assessment_warnings", advisory["uncertainty_flags"])
        self.assertNotIn(
            "narrative_warnings",
            advisory["uncertainty_flags"],
            response.json()["data"]["warnings"],
        )

    def test_get_analysis_meta_matches_legacy_report_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET report_schema_version = '' WHERE id = ?",
                (self.persisted["id"],),
            )

        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["report_schema_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_version"], "v1")

    def test_get_analysis_canonicalizes_zero_padded_report_schema_version(
        self,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET report_schema_version = 'v02' WHERE id = ?",
                (self.persisted["id"],),
            )

        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["report_schema_version"], "v2")
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")

    def test_get_analysis_rejects_malformed_report_schema_version(
        self,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET report_schema_version = 'legacy' WHERE id = ?",
                (self.persisted["id"],),
            )

        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"], "invalid_report_schema_version"
        )

    def test_get_analysis_rejects_newer_report_schema_version(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE analysis_reports SET report_schema_version = 'v3' WHERE id = ?",
                (self.persisted["id"],),
            )

        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["error"]["code"], "unsupported_report_schema_version"
        )

    def test_get_analysis_rejects_unknown_project_reference(self) -> None:
        response = self.client.get(
            f"/api/v1/analyses/{self.persisted['id']}",
            params={"project_key": "missing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_get_analysis_allows_unscoped_id_lookup(self) -> None:
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

        response = self.client.get(f"/api/v1/analyses/{scoped['id']}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["id"], scoped["id"])
        self.assertEqual(payload["project"]["project_key"], "payments")

    def test_workspace_query_prevents_cross_workspace_report_lookup(self) -> None:
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
        scoped = report_service_module.persist_analysis_report(
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

        wrong_workspace_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={
                "project_key": project.project_key,
                "workspace_key": staging.workspace_key,
            },
        )
        unscoped_workspace_id_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={"workspace_id": prod.id},
        )
        unscoped_workspace_id_list_response = self.client.get(
            "/api/v1/analyses",
            params={"workspace_id": prod.id},
        )
        scoped_id_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={"project_id": project.id, "workspace_id": prod.id},
        )
        scoped_list_response = self.client.get(
            "/api/v1/analyses",
            params={
                "project_key": project.project_key,
                "workspace_key": prod.workspace_key,
            },
        )

        self.assertEqual(wrong_workspace_response.status_code, 404)
        self.assertEqual(
            wrong_workspace_response.json()["error"]["code"], "analysis_not_found"
        )
        self.assertEqual(unscoped_workspace_id_response.status_code, 400)
        self.assertEqual(
            unscoped_workspace_id_response.json()["error"]["code"],
            "missing_project_scope",
        )
        self.assertEqual(unscoped_workspace_id_list_response.status_code, 400)
        self.assertEqual(
            unscoped_workspace_id_list_response.json()["error"]["code"],
            "missing_project_scope",
        )
        self.assertEqual(scoped_id_response.status_code, 200)
        self.assertEqual(scoped_id_response.json()["data"]["id"], scoped["id"])
        self.assertEqual(scoped_list_response.status_code, 200)
        payload = scoped_list_response.json()
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["data"][0]["workspace"]["workspace_key"], "prod")

    def test_list_analyses_filters_history_facets_without_cross_project_leaks(
        self,
    ) -> None:
        payments = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        prod = project_service_module.create_workspace(
            project_key=payments.project_key,
            workspace_key="prod",
            display_name="Production",
            environment="prod",
        )
        platform = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        payments_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="payments-prod.tfplan",
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
                top_risk="Payments production ingress widened.",
                contributors=[
                    RiskContributor(
                        source_file="payments-prod.tfplan",
                        tool="terraform",
                        resource_id="aws_security_group.payments",
                        action="modify",
                        contribution=30,
                        summary="Payments production ingress widened.",
                    )
                ],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="NO-GO: payments production ingress widened.",
                explanation="Payments production report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
            project_id=payments.id,
            workspace_id=prod.id,
            audit_context={"source_interface": "api"},
        )
        report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="platform-rollout.yaml",
                        tool="kubernetes",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=92,
                severity="critical",
                recommendation="no-go",
                top_risk="Platform production ingress widened.",
                contributors=[
                    RiskContributor(
                        source_file="platform-rollout.yaml",
                        tool="kubernetes",
                        resource_id="deployment/platform",
                        action="modify",
                        contribution=30,
                        summary="Platform production ingress widened.",
                    )
                ],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="NO-GO: platform production ingress widened.",
                explanation="Platform production report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
            project_id=platform.id,
            audit_context={"source_interface": "api"},
        )
        with database_module.SessionLocal() as session:
            session.get(
                tables_module.AnalysisReport, payments_report["id"]
            ).created_at = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
            session.commit()

        response = self.client.get(
            "/api/v1/analyses",
            params={
                "project_key": payments.project_key,
                "workspace_key": prod.workspace_key,
                "severity": "medium",
                "recommendation": "caution",
                "toolchain": "terraform",
                "analysis_status": "complete",
                "created_from": "2026-05-01T00:00:00Z",
                "created_to": "2026-05-20T00:00:00Z",
            },
        )
        foreign_response = self.client.get(
            "/api/v1/analyses",
            params={"project_key": platform.project_key},
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": payments.project_key,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["data"][0]["id"], payments_report["id"])
        self.assertEqual(payload["data"][0]["project"]["project_key"], "payments")
        self.assertEqual(payload["data"][0]["workspace"]["workspace_key"], "prod")
        self.assertEqual(payload["data"][0]["tool_mix"], ["terraform"])
        self.assertEqual(payload["data"][0]["analysis_status"], "complete")
        self.assertNotIn("Platform production ingress widened.", response.text)
        self.assertEqual(foreign_response.status_code, 200)
        self.assertEqual(foreign_response.json()["meta"]["total_count"], 0)
        self.assertEqual(foreign_response.json()["data"], [])
        self.assertNotIn("Platform production ingress widened.", foreign_response.text)

    def test_list_analyses_filters_by_deployment_outcome(self) -> None:
        failure_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="failure-plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=45,
                severity="medium",
                recommendation="caution",
                top_risk="Failure-linked report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="CAUTION: failure-linked report.",
                explanation="Failure report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
        )
        success_report = report_service_module.persist_analysis_report(
            ParseBatchResult(
                files=[
                    ParsedFileResult(
                        file_name="success-plan.json",
                        tool="terraform",
                        status="parsed",
                        changes=[],
                    )
                ]
            ),
            RiskAssessment(
                score=10,
                severity="low",
                recommendation="go",
                top_risk="Success-linked report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: success-linked report.",
                explanation="Success report.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
            ),
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=failure_report["id"],
            outcome="failure",
            deployed_at="2026-06-07T09:00:00Z",
        )
        deployment_outcome_service_module.record_deployment_outcome(
            analysis_id=success_report["id"],
            outcome="success",
            deployed_at="2026-06-07T10:00:00Z",
        )

        response = self.client.get(
            "/api/v1/analyses",
            params={"outcome": "failure"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["total_count"], 1)
        self.assertEqual(payload["data"][0]["id"], failure_report["id"])
        self.assertNotIn("Success-linked report.", response.text)

    def test_list_analyses_rejects_invalid_deployment_outcome_filter(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={"outcome": "failed"},
        )

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "request_validation_failed")
        self.assertEqual(
            payload["error"]["details"]["issues"][0]["loc"],
            ["query", "outcome"],
        )

    def test_list_analyses_rejects_naive_history_time_bounds(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={"created_from": "2026-05-01T00:00:00"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "invalid_history_time_bound",
        )

    def test_list_analyses_rejects_invalid_analysis_status(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={"analysis_status": "degradded"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "invalid_analysis_status",
        )

    def test_configure_share_is_disabled_without_management_token(self) -> None:
        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
        )

        self.assertEqual(response.status_code, 405)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "share_configuration_disabled")

    def test_configure_share_requires_valid_management_token(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "share_configuration_forbidden")

    def test_configure_share_returns_public_report_settings(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={"X-DeployWhisper-Share-Token": "review-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["share_url"],
            f"https://deploywhisper.example.com/reports/{self.persisted['id']}",
        )
        self.assertTrue(payload["data"]["password_protected"])
        self.assertTrue(payload["data"]["redact_filenames"])

    def test_configure_share_denies_project_outside_actor_scope(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "maintainer",
                "X-DeployWhisper-Project-Keys": "payments",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")
        self.assertNotIn("unassigned", payload["error"]["message"])

    def test_configure_share_denies_reviewer_within_actor_scope(self) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "reviewer",
                "X-DeployWhisper-Project-Keys": "unassigned",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_permission_denied")

    def test_configure_share_validates_missing_scope_before_missing_report(
        self,
    ) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            "/api/v1/analyses/999999/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "maintainer",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_required")

    def test_configure_share_validates_invalid_actor_before_missing_report(
        self,
    ) -> None:
        os.environ["DEPLOYWHISPER_SHARE_TOKEN"] = "review-secret"
        self.client = TestClient(create_app())

        response = self.client.post(
            "/api/v1/analyses/999999/share",
            json={"password": "s3cret-pass", "redact_filenames": True},
            headers={
                "X-DeployWhisper-Share-Token": "review-secret",
                "X-DeployWhisper-Project-Role": "unknown-role",
                "X-DeployWhisper-Project-Keys": "unassigned",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "invalid_project_role")

    def test_configure_share_rejects_unauthorized_reset_of_public_protection(
        self,
    ) -> None:
        report_service_module.configure_report_share(
            self.persisted["id"],
            password="s3cret-pass",
            redact_filenames=True,
        )

        reset_response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/share",
            json={"password": "", "redact_filenames": False},
        )
        report_response = self.client.get(f"/reports/{self.persisted['id']}")
        shared_response = self.client.get(
            f"/api/v1/analyses/{self.persisted['id']}/shared"
        )
        invalid_unlock_response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/shared/unlock",
            json={"password": "wrong"},
        )
        unlock_response = self.client.post(
            f"/api/v1/analyses/{self.persisted['id']}/shared/unlock",
            json={"password": "s3cret-pass"},
        )
        share_cookie_name = f"dw_share_{self.persisted['id']}"
        unlocked_response = self.client.get(
            f"/api/v1/analyses/{self.persisted['id']}/shared",
            cookies={share_cookie_name: unlock_response.cookies.get(share_cookie_name)},
        )

        self.assertEqual(reset_response.status_code, 405)
        self.assertIn('<div id="root"></div>', report_response.text)
        self.assertEqual(shared_response.status_code, 401)
        self.assertEqual(
            shared_response.json()["error"]["code"],
            "shared_report_password_required",
        )
        self.assertEqual(invalid_unlock_response.status_code, 401)
        self.assertEqual(unlock_response.status_code, 200)
        self.assertIn(share_cookie_name, unlock_response.cookies)
        self.assertEqual(unlocked_response.status_code, 200)
        self.assertTrue(unlocked_response.json()["data"]["share"]["redact_filenames"])

    def test_create_analysis_masks_foreign_workspace_for_scoped_actor(self) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        workspace = project_service_module.create_workspace(
            project_key=forbidden.project_key,
            workspace_key="prod",
            display_name="Production",
        )

        response = self.client.post(
            "/api/v1/analyses",
            data={
                "project_key": allowed.project_key,
                "workspace_id": str(workspace.id),
            },
            files=[
                (
                    "files",
                    (
                        "plan.json",
                        b'{"resource_changes": []}',
                        "application/json",
                    ),
                )
            ],
            headers={
                "X-DeployWhisper-Project-Role": "contributor",
                "X-DeployWhisper-Project-Keys": allowed.project_key,
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_scope_forbidden")

    def test_create_analysis_returns_structured_result(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=0,
                finding_id="pending:change-001",
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                summary="Terraform changed a security group.",
                severity_hint="high",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-001"],
            )
        ]

        incident_match = IncidentMatch(
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
            evidence=["plan.json: aws_security_group.main (modify) - public SSH"],
            matched_signals=["0.0.0.0/0", "ssh"],
            affected_services=["aws_security_group.main"],
            prevention_notes=["Use trusted administrative access."],
            verification_guidance=[
                "Confirm public CIDR is intentional.",
                "Restrict ingress to trusted networks.",
            ],
            summary="Public risk pattern match: wide-open administrative ingress.",
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.extract_batch_evidence",
                return_value=evidence_items,
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch(
                "services.analysis_service.find_incident_matches",
                return_value=[incident_match],
            ),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
                headers={"X-DeployWhisper-Actor": "api-reviewer@example.com"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["api_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        self.assertTrue(payload["meta"]["advisory_only"])
        self.assertEqual(payload["meta"]["accepted_artifact_count"], 1)
        self.assertEqual(payload["data"]["intake"]["items"][0]["status"], "ready")
        self.assertEqual(payload["data"]["assessment"]["source"], "heuristic+llm")
        self.assertLess(payload["data"]["assessment"]["confidence"], 0.7)
        self.assertIn("context_completeness", payload["data"]["assessment"])
        self.assertTrue(
            payload["data"]["assessment"]["context_completeness"][
                "insufficient_context"
            ]
        )
        self.assertTrue(
            payload["data"]["assessment"]["context_completeness"]["context_todos"]
        )
        self.assertEqual(
            payload["data"]["assessment"]["top_risk_contributors"],
            payload["data"]["persisted_report"]["top_risk_contributors"],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["confidence"],
            payload["data"]["assessment"]["confidence"],
        )
        self.assertEqual(
            payload["data"]["incident_matches"][0]["public_pattern_id"],
            "public-ingress-wide-open",
        )
        self.assertEqual(
            payload["data"]["incident_matches"][0]["confidence"],
            0.86,
        )
        self.assertEqual(
            payload["data"]["incident_matches"][0]["confidence_label"],
            "high",
        )
        self.assertEqual(
            payload["data"]["incident_matches"][0]["matched_signals"],
            ["0.0.0.0/0", "ssh"],
        )
        self.assertEqual(
            payload["data"]["incident_matches"][0]["affected_services"],
            ["aws_security_group.main"],
        )
        self.assertEqual(
            payload["data"]["incident_matches"][0]["prevention_notes"],
            ["Use trusted administrative access."],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["incident_matches"][0][
                "public_pattern_id"
            ],
            "public-ingress-wide-open",
        )
        self.assertTrue(
            payload["data"]["persisted_report"]["incident_matches"][0]["evidence"]
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["incident_matches"][0][
                "confidence_label"
            ],
            "high",
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["incident_matches"][0][
                "matched_signals"
            ],
            ["0.0.0.0/0", "ssh"],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["incident_matches"][0][
                "affected_services"
            ],
            ["aws_security_group.main"],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["incident_matches"][0][
                "prevention_notes"
            ],
            ["Use trusted administrative access."],
        )
        self.assertFalse(payload["data"]["persisted_report"]["narrative_degraded"])
        self.assertEqual(
            payload["data"]["assessment"]["contributors"],
            payload["data"]["persisted_report"]["contributors"],
        )
        self.assertTrue(payload["data"]["findings"])
        self.assertTrue(payload["data"]["evidence_items"])
        self.assertEqual(
            payload["data"]["findings"],
            payload["data"]["persisted_report"]["findings"],
        )
        self.assertEqual(
            payload["data"]["evidence_items"],
            payload["data"]["persisted_report"]["evidence_items"],
        )
        self.assertEqual(
            payload["data"]["assessment"]["context_completeness"],
            payload["data"]["persisted_report"]["context_completeness"],
        )
        self.assertEqual(
            payload["data"]["evidence_items"][0]["analysis_id"],
            payload["data"]["persisted_report"]["id"],
        )
        self.assertEqual(payload["data"]["findings"][0]["confidence"], 1.0)
        self.assertEqual(
            payload["data"]["findings"][0]["evidence_classification"],
            "deterministic",
        )
        self.assertEqual(
            payload["data"]["findings"][0]["evidence_refs"],
            payload["data"]["persisted_report"]["findings"][0]["evidence_refs"],
        )
        self.assertEqual(
            payload["data"]["findings"][0]["explanation"],
            "Security group exposure risk",
        )
        report_id = payload["data"]["persisted_report"]["id"]
        finding_id = payload["data"]["findings"][0]["finding_id"]

        detail = self.client.get(
            f"/api/v1/analyses/{report_id}",
            params={"project_key": "payments"},
        )
        self.assertEqual(detail.status_code, 200)
        detail_payload = detail.json()
        self.assertIn("share_summary", detail_payload["data"])
        self.assertIn("markdown", detail_payload["data"]["share_summary"])
        self.assertEqual(
            detail_payload["data"]["feedback_state"]["finding_feedback"], {}
        )

        feedback_response = self.client.post(
            f"/api/v1/analyses/{report_id}/findings/{finding_id}/feedback",
            json={"outcome": "useful"},
        )
        self.assertEqual(feedback_response.status_code, 200)
        self.assertEqual(feedback_response.json()["data"]["outcome_label"], "useful")

        updated_detail = self.client.get(
            f"/api/v1/analyses/{report_id}",
            params={"project_key": "payments"},
        )
        self.assertEqual(updated_detail.status_code, 200)
        feedback_state = updated_detail.json()["data"]["feedback_state"]
        self.assertEqual(
            feedback_state["finding_feedback"][finding_id]["outcome_label"],
            "useful",
        )
        self.assertTrue(payload["data"]["findings"][0]["guidance"])
        self.assertIn(payload["data"]["assessment"]["severity"], {"high", "critical"})
        self.assertEqual(payload["data"]["narrative"]["source"], "llm")
        self.assertTrue(payload["data"]["narrative"]["skills_applied"])
        self.assertFalse(payload["data"]["advisory"]["should_block"])
        self.assertTrue(payload["data"]["advisory"]["requires_attention"])
        self.assertEqual(
            payload["data"]["advisory"],
            payload["data"]["persisted_report"]["advisory"],
        )
        self.assertIn("context_todos", payload["data"]["advisory"]["uncertainty_flags"])
        self.assertIn(
            "assessment_warnings", payload["data"]["advisory"]["uncertainty_flags"]
        )
        self.assertIn("Advisory only", payload["data"]["share_summary"]["markdown"])
        self.assertEqual(payload["data"]["share_summary"]["recommendation"], "no-go")
        self.assertLessEqual(len(payload["data"]["share_summary"]["markdown"]), 1500)
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["version"], "v1"
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["report_schema_version"],
            "v2",
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["evidence_law_status"],
            "Reconciled",
        )
        self.assertIn(
            "adjusted unsupported or inconsistent severe claims",
            payload["data"]["share_summary"]["json_payload"]["evidence_law_detail"],
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["report_id"],
            payload["data"]["persisted_report"]["id"],
        )
        expected_report_link = (
            "https://deploywhisper.example.com/reports/"
            f"{payload['data']['persisted_report']['id']}"
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["report_link"],
            expected_report_link,
        )
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["rollback_link"],
            expected_report_link,
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["source_interface"], "api"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["actor"],
            "api-reviewer@example.com",
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["persisted_at"],
            payload["data"]["persisted_report"]["created_at"],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["redaction_status"], "none"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "api_request"
        )
        persisted_evidence_id = payload["data"]["persisted_report"]["evidence_items"][
            0
        ]["evidence_id"]
        self.assertEqual(
            payload["data"]["persisted_report"]["top_risk_contributors"],
            [persisted_evidence_id],
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["report_schema_version"], "v2"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["advisory"]["advisory_only"],
            True,
        )
        self.assertFalse(
            payload["data"]["persisted_report"]["advisory"]["should_block"]
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["advisory"]["recommendation"],
            payload["data"]["advisory"]["recommendation"],
        )
        self.assertIn("blast_radius", payload["data"]["persisted_report"])
        self.assertEqual(payload["data"]["blast_radius"]["context_state"], "missing")
        self.assertIn(
            "missing_topology",
            payload["data"]["blast_radius"]["context_limitations"],
        )
        self.assertEqual(
            payload["data"]["blast_radius"]["context_source"],
            {"type": None, "ref": None},
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["blast_radius"]["context_state"],
            "missing",
        )
        self.assertTrue(payload["data"]["persisted_report"]["findings"])
        self.assertTrue(payload["data"]["persisted_report"]["evidence_items"])
        self.assertEqual(
            payload["data"]["persisted_report"]["contributors"][0]["evidence_id"],
            persisted_evidence_id,
        )
        self.assertEqual(payload["data"]["persisted_report"]["id"], 2)

    def test_create_analysis_preserves_ownership_context_in_api_schema(self) -> None:
        project_service_module.create_project(
            project_key="payments-owners",
            display_name="Payments Owners",
        )
        persisted_report = dict(self.persisted)
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "incident_index_version": "incidents:unknown",
            "incident_index_last_indexed_at": "2026-05-25T00:00:00Z",
            "incident_index_freshness_status": "current",
            "owner_signals": [
                {
                    "scope": "file",
                    "subject": "services/payments/plan.json",
                    "owners": ["@payments-sre"],
                    "source": "CODEOWNERS",
                    "source_ref": ".github/CODEOWNERS",
                    "matched_pattern": "/services/payments/",
                    "resource_id": None,
                    "service_id": None,
                    "escalation_hint": "Escalate file review for services/payments/plan.json to @payments-sre.",
                }
            ],
            "escalation_hints": [
                "Escalate file review for services/payments/plan.json to @payments-sre."
            ],
            "ownership_unmapped_subjects": ["aws_security_group.unmapped"],
        }

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files={"files": ("plan.json", b'{"resource_changes": []}')},
                data={"project_key": "payments-owners"},
            )

        self.assertEqual(response.status_code, 200)
        context = response.json()["data"]["assessment"]["context_completeness"]
        self.assertEqual(context["incident_index_version"], "incidents:unknown")
        self.assertEqual(
            context["incident_index_last_indexed_at"],
            "2026-05-25T00:00:00Z",
        )
        self.assertEqual(context["incident_index_freshness_status"], "current")
        self.assertEqual(context["owner_signals"][0]["owners"], ["@payments-sre"])
        self.assertEqual(
            context["escalation_hints"],
            ["Escalate file review for services/payments/plan.json to @payments-sre."],
        )
        self.assertEqual(
            context["ownership_unmapped_subjects"],
            ["aws_security_group.unmapped"],
        )
        self.assertEqual(
            context,
            response.json()["data"]["persisted_report"]["context_completeness"],
        )

    def test_create_analysis_uses_trusted_relative_artifact_paths_for_api_uploads(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-paths",
            display_name="Payments API Paths",
        )
        persisted_report = dict(self.persisted)

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ) as analyze_uploaded_files:
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    ("files", ("CODEOWNERS", b"/services/payments/ @payments-sre")),
                    ("files", ("plan.json", b'{"resource_changes": []}')),
                ],
                data={
                    "project_key": "payments-api-paths",
                    "artifact_paths": [
                        ".github/CODEOWNERS",
                        "services/payments/plan.json",
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        raw_files = analyze_uploaded_files.call_args.args[0]
        self.assertEqual(
            [name for name, _ in raw_files],
            [".github/CODEOWNERS", "services/payments/plan.json"],
        )

    def test_create_analysis_does_not_trust_pathlike_filenames_without_metadata(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-untrusted-paths",
            display_name="Payments API Untrusted Paths",
        )
        persisted_report = dict(self.persisted)

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ) as analyze_uploaded_files:
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    (
                        "files",
                        (
                            ".github/CODEOWNERS",
                            b"/services/payments/ @payments-sre",
                        ),
                    ),
                    (
                        "files",
                        (
                            "services/payments/plan.json",
                            b'{"resource_changes": []}',
                        ),
                    ),
                ],
                data={"project_key": "payments-api-untrusted-paths"},
            )

        self.assertEqual(response.status_code, 200)
        raw_files = analyze_uploaded_files.call_args.args[0]
        self.assertEqual(
            [name for name, _ in raw_files],
            [
                "__unsafe_path__/.github/CODEOWNERS",
                "__unsafe_path__/services/payments/plan.json",
            ],
        )

    def test_create_analysis_does_not_trust_bare_codeowners_without_metadata(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-untrusted-codeowners",
            display_name="Payments API Untrusted CODEOWNERS",
        )
        persisted_report = dict(self.persisted)

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ) as analyze_uploaded_files:
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    (
                        "files",
                        (
                            "CODEOWNERS",
                            b"/services/payments/ @payments-sre",
                        ),
                    ),
                    (
                        "files",
                        (
                            "plan.json",
                            b'{"resource_changes": []}',
                        ),
                    ),
                ],
                data={"project_key": "payments-api-untrusted-codeowners"},
            )

        self.assertEqual(response.status_code, 200)
        raw_files = analyze_uploaded_files.call_args.args[0]
        self.assertEqual(
            [name for name, _ in raw_files],
            ["__unsafe_path__/CODEOWNERS", "plan.json"],
        )

    def test_create_analysis_rejects_mismatched_artifact_paths_for_api_uploads(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-path-mismatch",
            display_name="Payments API Path Mismatch",
        )

        with patch("api.routes.analyses.analyze_uploaded_files") as analyze_mock:
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    ("files", ("CODEOWNERS", b"/services/payments/ @payments-sre")),
                    ("files", ("plan.json", b'{"resource_changes": []}')),
                ],
                data={
                    "project_key": "payments-api-path-mismatch",
                    "artifact_paths": [".github/CODEOWNERS"],
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "artifact_path_mismatch")
        analyze_mock.assert_not_called()

    def test_create_analysis_rejects_reordered_artifact_paths_for_api_uploads(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-path-reorder",
            display_name="Payments API Path Reorder",
        )

        with patch("api.routes.analyses.analyze_uploaded_files") as analyze_mock:
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    ("files", ("CODEOWNERS", b"/services/payments/ @payments-sre")),
                    ("files", ("plan.json", b'{"resource_changes": []}')),
                ],
                data={
                    "project_key": "payments-api-path-reorder",
                    "artifact_paths": [
                        "services/payments/plan.json",
                        ".github/CODEOWNERS",
                    ],
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "artifact_path_mismatch")
        analyze_mock.assert_not_called()

    def test_create_analysis_supports_duplicate_artifact_path_filenames(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-path-duplicate",
            display_name="Payments API Path Duplicate",
        )
        persisted_report = dict(self.persisted)

        with patch("api.routes.analyses.analyze_uploaded_files") as analyze_mock:
            analyze_mock.return_value = self._analysis_result_with_persisted_report(
                persisted_report
            )
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    (
                        "files",
                        (
                            "services/payments/plan.json",
                            b'{"resource_changes": []}',
                        ),
                    ),
                    (
                        "files",
                        (
                            "services/billing/plan.json",
                            b'{"resource_changes": []}',
                        ),
                    ),
                ],
                data={
                    "project_key": "payments-api-path-duplicate",
                    "artifact_paths": [
                        "services/payments/plan.json",
                        "services/billing/plan.json",
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        raw_files = analyze_mock.call_args.args[0]
        self.assertEqual(
            [name for name, _ in raw_files],
            ["services/payments/plan.json", "services/billing/plan.json"],
        )

    def test_create_analysis_rejects_duplicate_basenames_without_path_binding(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-path-duplicate-bare",
            display_name="Payments API Path Duplicate Bare",
        )

        with patch("api.routes.analyses.analyze_uploaded_files") as analyze_mock:
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    ("files", ("plan.json", b'{"resource_changes": []}')),
                    ("files", ("plan.json", b'{"resource_changes": []}')),
                ],
                data={
                    "project_key": "payments-api-path-duplicate-bare",
                    "artifact_paths": [
                        "services/payments/plan.json",
                        "services/billing/plan.json",
                    ],
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "artifact_path_ambiguous")
        analyze_mock.assert_not_called()

    def test_create_analysis_rejects_duplicate_artifact_paths_for_api_uploads(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-path-exact-duplicate",
            display_name="Payments API Path Exact Duplicate",
        )

        with patch("api.routes.analyses.analyze_uploaded_files") as analyze_mock:
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    ("files", ("plan.json", b'{"resource_changes": []}')),
                    ("files", ("plan.json", b'{"resource_changes": []}')),
                ],
                data={
                    "project_key": "payments-api-path-exact-duplicate",
                    "artifact_paths": [
                        "services/payments/plan.json",
                        "services/payments/plan.json",
                    ],
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "artifact_path_ambiguous")
        analyze_mock.assert_not_called()

    def test_create_analysis_rejects_invalid_artifact_paths_at_request_layer(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-api-path-invalid",
            display_name="Payments API Path Invalid",
        )

        invalid_values = (
            "/Users/alice/repo/services/payments/plan.json",
            "services/../payments/plan.json",
            "__unsafe_path__/services/payments/plan.json",
            "__external_path__/services/payments/plan.json",
        )
        for artifact_path in invalid_values:
            with self.subTest(artifact_path=artifact_path):
                with patch(
                    "api.routes.analyses.analyze_uploaded_files"
                ) as analyze_mock:
                    response = self.client.post(
                        "/api/v1/analyses",
                        files=[
                            ("files", ("plan.json", b'{"resource_changes": []}')),
                        ],
                        data={
                            "project_key": "payments-api-path-invalid",
                            "artifact_paths": [artifact_path],
                        },
                    )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["error"]["code"],
                    "invalid_artifact_path",
                )
                analyze_mock.assert_not_called()

    def test_context_completeness_api_schema_rejects_invalid_scalar_values(
        self,
    ) -> None:
        invalid_payloads = (
            {"topology_freshness_days": -1},
            {"incident_index_size": -1},
            {"parser_success_rate": float("nan")},
            {"parser_success_rate": -0.1},
            {"parser_success_by_tool": {"terraform": float("inf")}},
            {"parser_success_by_tool": {"terraform": 1.2}},
            {"context_score": float("-inf")},
            {"context_score": -0.1},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    ContextCompletenessData.model_validate(payload)

    def test_persisted_report_salvages_nonfinite_and_negative_context_scalars(
        self,
    ) -> None:
        persisted_report = dict(self.persisted)
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "topology_freshness_days": -7,
            "incident_index_size": -3,
            "evidence_success_rate": float("nan"),
            "parser_success_rate": float("inf"),
            "parser_success_by_tool": {"terraform": -0.2, "kubernetes": float("nan")},
            "context_score": float("-inf"),
            "confidence_level": "medium",
            "owner_signals": [
                {
                    "scope": "file",
                    "subject": "services/payments/plan.json",
                    "owners": ["@payments-sre"],
                    "source": "CODEOWNERS",
                    "source_ref": ".github/CODEOWNERS",
                    "escalation_hint": "Escalate file review for services/payments/plan.json to @payments-sre.",
                }
            ],
        }

        report = PersistedReportData.model_validate(persisted_report)

        self.assertIsNone(report.context_completeness.topology_freshness_days)
        self.assertEqual(report.context_completeness.incident_index_size, 0)
        self.assertEqual(report.context_completeness.evidence_success_rate, 0.0)
        self.assertEqual(report.context_completeness.parser_success_rate, 0.0)
        self.assertEqual(
            report.context_completeness.parser_success_by_tool,
            {"terraform": 0.0, "kubernetes": 0.0},
        )
        self.assertEqual(report.context_completeness.context_score, 0.69)
        self.assertEqual(report.context_completeness.confidence_level, "low")
        self.assertTrue(report.context_completeness.insufficient_context)
        self.assertTrue(report.context_completeness.partial_context)
        self.assertEqual(len(report.context_completeness.owner_signals), 1)

    def test_context_completeness_api_schema_rejects_malformed_owner_signals(
        self,
    ) -> None:
        with self.assertRaises(ValidationError):
            ContextCompletenessData.model_validate(
                {
                    "owner_signals": [
                        {
                            "scope": "file",
                            "subject": "",
                            "owners": [""],
                            "source": "",
                            "escalation_hint": "",
                        }
                    ],
                    "escalation_hints": [""],
                    "ownership_unmapped_subjects": [""],
                }
            )
        with self.assertRaises(ValidationError):
            ContextCompletenessData.model_validate(
                {
                    "owner_signals": [
                        {
                            "scope": "file",
                            "subject": "services/payments/plan.json",
                            "owners": ["@payments-sre"],
                            "source": "CODEOWNERS",
                            "escalation_hint": "Escalate file review to @payments-sre.",
                            "unexpected": "not allowed",
                        }
                    ],
                    "unexpected_context": "not allowed",
                }
            )

    def test_persisted_report_degrades_malformed_context_payload(self) -> None:
        malformed_contexts = (
            "oops",
            {"future_context_field": "unknown"},
            {"context_score": "oops"},
        )
        for malformed_context in malformed_contexts:
            persisted_report = dict(self.persisted)
            persisted_report["context_completeness"] = malformed_context

            report = PersistedReportData.model_validate(persisted_report)

            self.assertEqual(report.context_completeness.context_score, 0.0)
            self.assertEqual(report.context_completeness.confidence_level, "low")
            self.assertTrue(report.context_completeness.insufficient_context)
            self.assertIn(
                "Context completeness payload was unavailable or unreadable.",
                report.context_completeness.uncertainty,
            )

    def test_persisted_report_degrades_missing_context_payload(self) -> None:
        persisted_report = dict(self.persisted)
        persisted_report.pop("context_completeness", None)

        report = PersistedReportData.model_validate(persisted_report)

        self.assertEqual(report.context_completeness.context_score, 0.0)
        self.assertEqual(report.context_completeness.confidence_level, "low")
        self.assertTrue(report.context_completeness.insufficient_context)
        self.assertIn(
            "Context completeness payload was unavailable or unreadable.",
            report.context_completeness.uncertainty,
        )

    def test_persisted_report_salvages_malformed_ownership_context_fields(
        self,
    ) -> None:
        persisted_report = dict(self.persisted)
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "context_score": 0.84,
            "confidence_level": "medium",
            "owner_signals": [
                {
                    "scope": "file",
                    "subject": "services/payments/plan.json",
                    "owners": ["@payments-sre", "", {"handle": "@fake-owner"}],
                    "source": "CODEOWNERS",
                    "source_ref": ".github/CODEOWNERS",
                    "unexpected": "not allowed",
                },
                {
                    "scope": "file",
                    "subject": "",
                    "owners": ["@broken"],
                    "source": "CODEOWNERS",
                    "escalation_hint": "Broken owner signal.",
                },
            ],
            "context_todos": ["Review missing ownership before deploy.", "", 42],
            "escalation_hints": [
                "Escalate service review for Payments API to @payments-runtime.",
                "",
                {"hint": "fake escalation"},
            ],
            "ownership_unmapped_subjects": [
                "aws_security_group.unmapped",
                "",
                123,
            ],
        }

        report = PersistedReportData.model_validate(persisted_report)

        self.assertEqual(report.context_completeness.context_score, 0.69)
        self.assertEqual(report.context_completeness.confidence_level, "low")
        self.assertTrue(report.context_completeness.insufficient_context)
        self.assertTrue(report.context_completeness.partial_context)
        self.assertIn(
            "Ownership context payload was partially unreadable.",
            report.context_completeness.uncertainty,
        )
        self.assertIn(
            "Regenerate this report to restore ownership context metadata.",
            report.context_completeness.context_todos,
        )
        self.assertEqual(len(report.context_completeness.owner_signals), 1)
        self.assertEqual(
            report.context_completeness.owner_signals[0].owners,
            ["@payments-sre"],
        )
        self.assertEqual(
            report.context_completeness.owner_signals[0].escalation_hint,
            "Escalate file review for services/payments/plan.json to @payments-sre.",
        )
        self.assertIn(
            "Review missing ownership before deploy.",
            report.context_completeness.context_todos,
        )
        self.assertEqual(
            report.context_completeness.escalation_hints,
            ["Escalate service review for Payments API to @payments-runtime."],
        )
        self.assertEqual(
            report.context_completeness.ownership_unmapped_subjects,
            ["aws_security_group.unmapped"],
        )

    def test_persisted_report_marks_partial_when_owner_entries_are_cleaned(
        self,
    ) -> None:
        persisted_report = dict(self.persisted)
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "context_score": 0.84,
            "confidence_level": "medium",
            "owner_signals": [
                {
                    "scope": "file",
                    "subject": "services/payments/plan.json",
                    "owners": ["@payments-sre", ""],
                    "source": "CODEOWNERS",
                    "source_ref": ".github/CODEOWNERS",
                }
            ],
        }

        report = PersistedReportData.model_validate(persisted_report)

        self.assertEqual(report.context_completeness.context_score, 0.69)
        self.assertEqual(report.context_completeness.confidence_level, "low")
        self.assertTrue(report.context_completeness.insufficient_context)
        self.assertTrue(report.context_completeness.partial_context)
        self.assertEqual(len(report.context_completeness.owner_signals), 1)
        self.assertEqual(
            report.context_completeness.owner_signals[0].owners,
            ["@payments-sre"],
        )
        self.assertIn(
            "Regenerate this report to restore ownership context metadata.",
            report.context_completeness.context_todos,
        )

    def test_persisted_report_salvages_ownership_when_scalar_context_is_malformed(
        self,
    ) -> None:
        persisted_report = dict(self.persisted)
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "context_score": "oops",
            "confidence_level": "medium",
            "owner_signals": [
                {
                    "scope": "file",
                    "subject": "services/payments/plan.json",
                    "owners": ["@payments-sre"],
                    "source": "CODEOWNERS",
                    "source_ref": ".github/CODEOWNERS",
                    "escalation_hint": "Escalate file review for services/payments/plan.json to @payments-sre.",
                }
            ],
            "escalation_hints": [
                "Escalate file review for services/payments/plan.json to @payments-sre."
            ],
            "ownership_unmapped_subjects": ["aws_security_group.unmapped"],
        }

        report = PersistedReportData.model_validate(persisted_report)

        self.assertEqual(report.context_completeness.context_score, 0.69)
        self.assertEqual(report.context_completeness.confidence_level, "low")
        self.assertTrue(report.context_completeness.insufficient_context)
        self.assertTrue(report.context_completeness.partial_context)
        self.assertEqual(len(report.context_completeness.owner_signals), 1)
        self.assertEqual(
            report.context_completeness.owner_signals[0].owners,
            ["@payments-sre"],
        )
        self.assertEqual(
            report.context_completeness.escalation_hints,
            ["Escalate file review for services/payments/plan.json to @payments-sre."],
        )
        self.assertEqual(
            report.context_completeness.ownership_unmapped_subjects,
            ["aws_security_group.unmapped"],
        )

    def test_create_analysis_preserves_go_advisory_with_narrative_warning(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="safe-change",
            display_name="Safe Change",
        )
        narrative = NarrativeResult(
            opening_sentence="GO: low risk tag update.",
            explanation="Review can follow the standard approval flow.",
            guidance=[],
            degraded=False,
            warnings=["Narrative provider warning."],
            source="llm",
        )
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=0,
                finding_id="pending:change-001",
                source_type="artifact",
                source_ref="terraform://low-risk-plan.json#aws_s3_bucket.logs?action=modify",
                summary="Terraform adjusted log bucket tags.",
                severity_hint="low",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-001"],
            )
        ]

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=RiskAssessment(
                    score=12,
                    severity="low",
                    recommendation="go",
                    top_risk="Low risk tag update.",
                    top_risk_contributors=["ev-001"],
                    contributors=[
                        RiskContributor(
                            evidence_id="ev-001",
                            source_file="low-risk-plan.json",
                            tool="terraform",
                            resource_id="aws_s3_bucket.logs",
                            action="modify",
                            contribution=12,
                            summary="Terraform adjusted log bucket tags.",
                            severity="low",
                            reasoning="Low risk tag update.",
                        )
                    ],
                    interaction_risks=[],
                    context_completeness=ContextCompleteness(
                        topology_freshness_days=0,
                        topology_last_imported_at="2026-05-25T00:00:00Z",
                        incident_index_size=1,
                        incident_index_version="incidents:unknown",
                        incident_index_freshness_status="current",
                    ),
                    partial_context=False,
                    warnings=[],
                    source="heuristic+llm",
                ),
            ),
            patch(
                "services.analysis_service.extract_batch_evidence",
                return_value=evidence_items,
            ),
            patch(
                "services.analysis_service._build_context_completeness",
                return_value=ContextCompleteness(
                    topology_freshness_days=0,
                    topology_last_imported_at="2026-05-25T00:00:00Z",
                    incident_index_size=1,
                    incident_index_version="incidents:unknown",
                    incident_index_freshness_status="current",
                ),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=[
                    (
                        "files",
                        (
                            "low-risk-plan.json",
                            b'{"resource_changes": []}',
                            "application/json",
                        ),
                    )
                ],
                data={"project_key": "safe-change"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["api_version"], "v1")
        self.assertEqual(payload["meta"]["report_schema_version"], "v2")
        advisory = payload["data"]["advisory"]
        self.assertEqual(advisory, payload["data"]["persisted_report"]["advisory"])
        self.assertEqual(advisory["recommendation"], "go")
        self.assertFalse(advisory["requires_attention"])
        self.assertNotIn("assessment_warnings", advisory["uncertainty_flags"])
        self.assertIn("narrative_warnings", advisory["uncertainty_flags"])
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["advisory_summary"],
            "Standard approval flow is sufficient.",
        )
        self.assertNotIn(
            "requires additional human review",
            payload["data"]["share_summary"]["plain_text"].lower(),
        )

    def test_create_analysis_rebuilds_stale_valid_persisted_advisory(self) -> None:
        project_service_module.create_project(
            project_key="payments-stale-advisory",
            display_name="Payments Stale Advisory",
        )
        persisted_report = dict(self.persisted)
        persisted_report["severity"] = "low"
        persisted_report["recommendation"] = "go"
        persisted_report["top_risk"] = "Low risk metadata-only update."
        persisted_report["warnings"] = []
        persisted_report["narrative_available"] = True
        persisted_report["narrative_degraded"] = False
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "context_score": 0.95,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": False,
            "partial_context": False,
        }
        persisted_report["advisory"] = {
            "advisory_only": True,
            "should_block": False,
            "requires_attention": True,
            "severity": "high",
            "recommendation": "no-go",
            "top_risk": "Stale advisory from an older report state.",
            "partial_context": True,
            "narrative_degraded": False,
            "uncertainty_flags": ["partial_context"],
        }

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files={"files": ("plan.json", b'{"resource_changes": []}')},
                data={"project_key": "payments-stale-advisory"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        advisory = payload["data"]["advisory"]
        self.assertEqual(advisory["severity"], "low")
        self.assertEqual(advisory["recommendation"], "go")
        self.assertFalse(advisory["requires_attention"])
        self.assertFalse(advisory["partial_context"])
        self.assertEqual(payload["data"]["persisted_report"]["advisory"], advisory)

    def test_create_analysis_share_summary_matches_advisory_partial_context(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-partial-summary",
            display_name="Payments Partial Summary",
        )
        persisted_report = dict(self.persisted)
        persisted_report["severity"] = "low"
        persisted_report["recommendation"] = "go"
        persisted_report["top_risk"] = "Low risk metadata-only update."
        persisted_report["warnings"] = []
        persisted_report["narrative_available"] = True
        persisted_report["narrative_degraded"] = False
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "context_score": 0.95,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 1.0,
            "insufficient_context": False,
            "partial_context": False,
        }
        persisted_report["submission_manifest_fallback"] = [
            {
                "name": "plan.json",
                "tool": "terraform",
                "status": "accepted",
                "intake_status": "accepted",
                "parse_status": "failed",
                "partial": False,
                "redaction_status": "none",
            }
        ]

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files={"files": ("plan.json", b'{"resource_changes": []}')},
                data={"project_key": "payments-partial-summary"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["data"]["advisory"]["partial_context"])
        self.assertEqual(
            payload["data"]["share_summary"]["json_payload"]["context_completeness"][
                "label"
            ],
            "LIMITED CONTEXT",
        )
        self.assertIn(
            "submitted artifacts were not analyzed",
            payload["data"]["share_summary"]["plain_text"],
        )

    def test_create_analysis_returns_degraded_narrative_provider_metadata(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-degraded",
            display_name="Payments Degraded",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            available=False,
            opening_sentence="",
            explanation="",
            guidance=[],
            degraded=True,
            warnings=["Narrative provider unavailable: timeout"],
            failure_notice="Narrative provider unavailable: timeout",
            source="fallback",
            provider="openai",
            model="gpt-4.1-mini",
            local_mode=False,
            skills_applied=["terraform"],
        )
        evidence_items = [
            EvidenceItem(
                evidence_id="ev-001",
                analysis_id=0,
                finding_id="pending:change-001",
                source_type="artifact",
                source_ref="terraform://plan.json#aws_security_group.main?action=modify",
                summary="Terraform changed a security group.",
                severity_hint="high",
                deterministic=True,
                confidence=1.0,
                related_change_ids=["change-001"],
            )
        ]

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.extract_batch_evidence",
                return_value=evidence_items,
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=narrative,
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments-degraded"},
            )

        self.assertEqual(response.status_code, 200)
        persisted_report = response.json()["data"]["persisted_report"]
        self.assertFalse(persisted_report["narrative_available"])
        self.assertTrue(persisted_report["narrative_degraded"])
        self.assertEqual(persisted_report["narrative_source"], "fallback")
        self.assertEqual(persisted_report["narrative_provider"], "openai")
        self.assertEqual(persisted_report["narrative_model"], "gpt-4.1-mini")
        self.assertFalse(persisted_report["narrative_local_mode"])
        self.assertEqual(
            persisted_report["narrative_failure_notice"],
            "Narrative provider unavailable: timeout",
        )

    def test_create_analysis_preserves_real_pipeline_metadata_in_persisted_contributors(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    (
                        b'{"planned_values": {}, "resource_changes": ['
                        b'{"address": "data.aws_ami.selected", "mode": "data", '
                        b'"change": {"actions": ["read"], "after_unknown": {"id": true}}}, '
                        b'{"address": '
                        b'"module.network.aws_security_group.main", "module_address": '
                        b'"module.network", "provider_name": '
                        b'"registry.terraform.io/hashicorp/aws", "type": '
                        b'"aws_security_group", "name": "main", "change": '
                        b'{"actions": ["update"]}}]}'
                    ),
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "analysis.risk_scorer.generate_completion_with_settings",
                return_value='{"change_scores": []}',
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for ledger in (
            payload["data"]["assessment"]["confidence_ledger"],
            payload["data"]["persisted_report"]["confidence_ledger"],
        ):
            self.assertGreater(len(ledger["contributors"]), 0)
            self.assertGreater(len(ledger["confidence_factors"]), 0)
            self.assertGreater(len(ledger["why_not_lower"]), 0)
            self.assertGreater(len(ledger["why_not_higher"]), 0)
            self.assertGreater(len(ledger["uncertainty_drivers"]), 0)
        contributors = {
            contributor["resource_id"]: contributor
            for contributor in payload["data"]["persisted_report"]["contributors"]
        }
        metadata = contributors["module.network.aws_security_group.main"]["metadata"]
        self.assertEqual(metadata["module_address"], "module.network")
        self.assertEqual(
            metadata["provider_name"], "registry.terraform.io/hashicorp/aws"
        )
        self.assertEqual(metadata["plan_unsupported_fields"], ["plan.planned_values"])
        self.assertEqual(
            contributors["data.aws_ami.selected"]["metadata"]["unknown_after_apply"],
            ["id"],
        )
        self.assertIsNone(contributors["data.aws_ami.selected"]["evidence_id"])
        self.assertEqual(contributors["data.aws_ami.selected"]["contribution"], 0)

        detail = self.client.get(
            f"/api/v1/analyses/{payload['data']['persisted_report']['id']}",
            params={"project_key": "payments"},
        )
        self.assertEqual(detail.status_code, 200)
        detail_ledger = detail.json()["data"]["confidence_ledger"]
        self.assertGreater(len(detail_ledger["contributors"]), 0)
        self.assertGreater(len(detail_ledger["confidence_factors"]), 0)
        self.assertGreater(len(detail_ledger["why_not_lower"]), 0)
        self.assertGreater(len(detail_ledger["why_not_higher"]), 0)
        self.assertGreater(len(detail_ledger["uncertainty_drivers"]), 0)
        detail_contributors = {
            contributor["resource_id"]: contributor
            for contributor in detail.json()["data"]["contributors"]
        }
        self.assertEqual(
            detail_contributors["module.network.aws_security_group.main"]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )
        self.assertEqual(
            detail_contributors["data.aws_ami.selected"]["metadata"][
                "unknown_after_apply"
            ],
            ["id"],
        )

        history = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
        )
        self.assertEqual(history.status_code, 200)
        history_contributors = {
            contributor["resource_id"]: contributor
            for contributor in history.json()["data"][0]["contributors"]
        }
        self.assertEqual(
            history_contributors["module.network.aws_security_group.main"]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )
        self.assertEqual(
            history_contributors["data.aws_ami.selected"]["metadata"][
                "unknown_after_apply"
            ],
            ["id"],
        )

    def test_create_analysis_preserves_all_non_mutating_plan_metadata(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "empty-plan.json",
                    (
                        b'{"format_version": "1.2", "terraform_version": "1.8.5", '
                        b'"planned_values": {}, "resource_changes": []}'
                    ),
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="GO: no planned infrastructure changes.",
            explanation="The submitted Terraform plan contains no resource changes.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        contributor = payload["data"]["persisted_report"]["contributors"][0]
        self.assertEqual(contributor["resource_id"], "terraform-plan")
        self.assertEqual(contributor["contribution"], 0)
        self.assertEqual(
            contributor["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )

        detail = self.client.get(
            f"/api/v1/analyses/{payload['data']['persisted_report']['id']}",
            params={"project_key": "payments"},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["data"]["contributors"][0]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )

        history = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(
            history.json()["data"][0]["contributors"][0]["metadata"][
                "plan_unsupported_fields"
            ],
            ["plan.planned_values"],
        )

    def test_create_analysis_persists_submission_manifest_with_partial_coverage(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    (
                        b'{"planned_values": {}, "resource_changes": [{"address": "module.network.aws_security_group.main", '
                        b'"module_address": "module.network", "type": "aws_security_group", '
                        b'"name": "main", "provider_name": "registry.terraform.io/hashicorp/aws", '
                        b'"change": {"actions": ["update"], "after_unknown": {"arn": true}, '
                        b'"after_sensitive": {"ingress": [{"description": true}]}, '
                        b'"replace_paths": [["ingress", 0, "cidr_blocks"]], '
                        b'"importing": {"id": "sg-123"}}, "deposed": "legacy"}]}'
                    ),
                    "application/json",
                ),
            ),
            (
                "files",
                (
                    "broken.tf",
                    b"resource {",
                    "application/octet-stream",
                ),
            ),
            (
                "files",
                (
                    ".env",
                    b"SECRET=1",
                    "text/plain",
                ),
            ),
            (
                "files",
                (
                    "notes.txt",
                    b"deployment notes",
                    "text/plain",
                ),
            ),
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review partial analysis.",
            explanation="One artifact failed to parse.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(
                    resource_id="module.network.aws_security_group.main",
                    partial_context=True,
                ),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
                headers={"X-DeployWhisper-Trigger-Id": "build-77"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        manifest = payload["data"]["persisted_report"]["submission_manifest"]
        self.assertEqual(manifest["submitted_artifact_count"], 4)
        self.assertEqual(manifest["accepted_artifact_count"], 2)
        self.assertEqual(manifest["analyzed_artifact_count"], 1)
        self.assertEqual(manifest["excluded_artifact_count"], 1)
        self.assertEqual(manifest["sensitive_artifact_count"], 1)
        self.assertEqual(manifest["failed_artifact_count"], 1)
        self.assertEqual(manifest["partial_artifact_count"], 3)
        self.assertTrue(manifest["partial_analysis"])
        by_name = {item["name"]: item for item in manifest["items"]}
        self.assertEqual(by_name["plan.json"]["status"], "accepted")
        self.assertEqual(by_name["broken.tf"]["status"], "failed")
        self.assertTrue(by_name["broken.tf"]["partial"])
        self.assertEqual(by_name[".env"]["status"], "sensitive")
        self.assertTrue(by_name[".env"]["partial"])
        self.assertEqual(by_name["notes.txt"]["status"], "excluded")
        self.assertTrue(by_name["notes.txt"]["partial"])
        self.assertEqual(by_name["plan.json"]["provenance"]["source_interface"], "api")
        self.assertEqual(by_name["plan.json"]["provenance"]["trigger_id"], "build-77")
        change = payload["data"]["parse_batch"]["files"][0]["changes"][0]
        self.assertEqual(
            change["resource_id"], "module.network.aws_security_group.main"
        )
        self.assertEqual(change["metadata"]["module_address"], "module.network")
        self.assertEqual(change["metadata"]["unknown_after_apply"], ["arn"])
        self.assertEqual(
            change["metadata"]["redacted_fields"], ["ingress.0.description"]
        )
        self.assertEqual(
            change["metadata"]["unsupported_fields"],
            ["change.importing", "resource_change.deposed"],
        )
        self.assertEqual(
            change["metadata"]["plan_unsupported_fields"],
            ["plan.planned_values"],
        )
        self.assertTrue(payload["data"]["assessment"]["partial_context"])

        detail = self.client.get(
            f"/api/v1/analyses/{payload['data']['persisted_report']['id']}",
            params={"project_key": "payments"},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            detail.json()["data"]["submission_manifest"]["failed_artifact_count"],
            1,
        )

    def test_create_analysis_surfaces_duplicate_terraform_action_parse_failure(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            ),
            (
                "files",
                (
                    "duplicate-plan.json",
                    b'{"resource_changes": [{"address": "aws_instance.web", "change": {"actions": ["create", "create"]}}]}',
                    "application/json",
                ),
            ),
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review partial analysis.",
            explanation="One Terraform plan could not be parsed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        by_name = {
            file_result["file_name"]: file_result
            for file_result in payload["data"]["parse_batch"]["files"]
        }
        self.assertEqual(by_name["plan.json"]["status"], "parsed")
        self.assertEqual(by_name["duplicate-plan.json"]["status"], "failed")
        self.assertIn(
            "Duplicate Terraform action",
            by_name["duplicate-plan.json"]["issue"]["message"],
        )
        manifest = payload["data"]["persisted_report"]["submission_manifest"]
        self.assertEqual(manifest["accepted_artifact_count"], 2)
        self.assertEqual(manifest["failed_artifact_count"], 1)
        self.assertTrue(manifest["partial_analysis"])

    def test_create_analysis_denies_role_without_submit_capability(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": []}',
                    "application/json",
                ),
            )
        ]

        response = self.client.post(
            "/api/v1/analyses",
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": "payments",
            },
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "project_permission_denied")
        self.assertNotIn("payments", payload["error"]["message"])

    def test_project_role_header_requires_nonblank_role(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": []}',
                    "application/json",
                ),
            )
        ]

        response = self.client.post(
            "/api/v1/analyses",
            headers={"X-DeployWhisper-Project-Role": " "},
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "invalid_project_role")

    def test_non_admin_role_requires_project_scope_header(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )

        response = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
            headers={"X-DeployWhisper-Project-Role": "read-only"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "project_scope_required")

    def test_analysis_reads_mask_missing_project_id_for_scoped_actor(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={"project_id": 999},
            headers={
                "X-DeployWhisper-Project-Role": "read-only",
                "X-DeployWhisper-Project-Keys": "payments",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["meta"]["total_count"], 0)
        self.assertEqual(response.json()["data"], [])

    def test_analysis_reads_mask_conflicting_project_reference_for_scoped_actor(
        self,
    ) -> None:
        allowed = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        forbidden = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        headers = {
            "X-DeployWhisper-Project-Role": "read-only",
            "X-DeployWhisper-Project-Keys": allowed.project_key,
        }

        list_response = self.client.get(
            "/api/v1/analyses",
            params={
                "project_key": allowed.project_key,
                "project_id": forbidden.id,
            },
            headers=headers,
        )
        detail_response = self.client.get(
            f"/api/v1/analyses/{self.persisted['id']}",
            params={
                "project_key": allowed.project_key,
                "project_id": forbidden.id,
            },
            headers=headers,
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["meta"]["total_count"], 0)
        self.assertEqual(list_response.json()["data"], [])
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(
            detail_response.json()["error"]["code"], "project_scope_forbidden"
        )
        self.assertNotIn("payments", detail_response.json()["error"]["message"])

    def test_analysis_reads_deny_project_outside_actor_scope(self) -> None:
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
                top_risk="Scoped project report.",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
            ),
            NarrativeResult(
                opening_sentence="GO: scoped project report.",
                explanation="Scoped report.",
                guidance=[],
                degraded=False,
                warnings=[],
            ),
            project_id=project.id,
            audit_context={"source_interface": "api"},
        )
        headers = {
            "X-DeployWhisper-Project-Role": "read-only",
            "X-DeployWhisper-Project-Keys": "platform",
        }

        list_response = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "payments"},
            headers=headers,
        )
        detail_response = self.client.get(
            f"/api/v1/analyses/{scoped['id']}",
            params={"project_key": "payments"},
            headers=headers,
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["meta"]["total_count"], 0)
        self.assertEqual(list_response.json()["data"], [])
        self.assertEqual(detail_response.status_code, 403)
        self.assertEqual(
            detail_response.json()["error"]["code"], "project_scope_forbidden"
        )
        self.assertNotIn("payments", detail_response.json()["error"]["message"])

    def test_analysis_detail_returns_null_manifest_when_persisted_json_is_malformed(
        self,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE analysis_reports SET submission_manifest_json = ? WHERE id = ?",
                ("{not-valid-json", self.persisted["id"]),
            )

        response = self.client.get(f"/api/v1/analyses/{self.persisted['id']}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIsNone(payload["submission_manifest"])
        self.assertEqual(
            payload["submission_manifest_fallback"][0]["name"], "plan.json"
        )
        self.assertEqual(
            payload["submission_manifest_fallback"][0]["status"], "accepted"
        )
        self.assertIn(
            "Submission manifest metadata was unavailable because persisted JSON was malformed.",
            payload["warnings"],
        )

    def test_create_analysis_accepts_project_id(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_id": str(project.id)},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )

    def test_create_analysis_accepts_project_id_with_blank_project_key(self) -> None:
        project = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=[],
            degraded=False,
            warnings=[],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_id": str(project.id), "project_key": "   "},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["persisted_report"]["project"]["project_key"], "payments"
        )

    def test_create_analysis_rejects_unknown_project_reference(self) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]

        response = self.client.post(
            "/api/v1/analyses",
            files=files,
            data={"project_key": "missing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_create_analysis_rejects_unknown_project_before_parsing(self) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "missing"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")
        build_parse_batch.assert_not_called()
        list_response = self.client.get("/api/v1/analyses")
        self.assertEqual(list_response.json()["meta"]["total_count"], 1)

    def test_create_analysis_rejects_missing_project_scope_before_parsing(
        self,
    ) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "missing_project_scope")
        build_parse_batch.assert_not_called()

    def test_create_analysis_rejects_blank_explicit_project_key_before_parsing(
        self,
    ) -> None:
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "   "},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_project_reference")
        build_parse_batch.assert_not_called()

    def test_list_analyses_rejects_unknown_project_reference(self) -> None:
        response = self.client.get(
            "/api/v1/analyses",
            params={"project_key": "missing"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "project_not_found")

    def test_create_analysis_rejects_conflicting_project_reference(self) -> None:
        first = project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        second = project_service_module.create_project(
            project_key="platform",
            display_name="Platform",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]

        with patch(
            "services.analysis_service.build_parse_batch",
            side_effect=AssertionError("project must resolve before parsing"),
        ) as build_parse_batch:
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_id": str(first.id), "project_key": second.project_key},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "conflicting_project_reference",
        )
        build_parse_batch.assert_not_called()
        list_response = self.client.get("/api/v1/analyses")
        self.assertEqual(list_response.json()["meta"]["total_count"], 1)

    def test_create_analysis_captures_trigger_headers_when_present(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group update.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review the security group change before deploy."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
                headers={
                    "X-DeployWhisper-Trigger-Type": "user_session",
                    "X-DeployWhisper-Trigger-Id": "sess-456",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_type"], "user_session"
        )
        self.assertEqual(
            payload["data"]["persisted_report"]["audit"]["trigger_id"], "sess-456"
        )

    def test_create_analysis_preserves_distinct_artifacts_with_same_basename(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.first", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            ),
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.second", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            ),
        ]
        narrative = NarrativeResult(
            opening_sentence="CAUTION: review the security group updates.",
            explanation="The deployment widens database access and should be reviewed.",
            guidance=["Review both security group changes before deploy."],
            degraded=False,
            warnings=[],
            source="llm",
            provider="ollama",
            model="ollama/llama3",
            local_mode=True,
            skills_applied=["git", "terraform"],
        )

        with (
            patch(
                "services.analysis_service.generate_narrative", return_value=narrative
            ),
            patch("services.analysis_service.find_incident_matches", return_value=[]),
        ):
            response = self.client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        intake_names = [item["name"] for item in payload["data"]["intake"]["items"]]
        self.assertEqual(intake_names, ["plan.json", "plan#2.json"])

    def test_create_analysis_rejects_payloads_over_50_mb(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        oversized = b"x" * 50_000_001
        files = [("files", ("plan.json", oversized, "application/json"))]

        response = self.client.post(
            "/api/v1/analyses",
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 413)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "upload_limit_exceeded")

    def test_create_analysis_rejects_requests_without_supported_artifacts(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [("files", ("README.txt", b"hello", "text/plain"))]

        response = self.client.post(
            "/api/v1/analyses",
            files=files,
            data={"project_key": "payments"},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "no_supported_artifacts")
        self.assertEqual(
            payload["error"]["details"]["items"][0]["status"], "unsupported"
        )

    def test_create_analysis_rejects_missing_scope_before_unsupported_preflight(
        self,
    ) -> None:
        files = [("files", ("README.txt", b"hello", "text/plain"))]

        response = self.client.post("/api/v1/analyses", files=files)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "missing_project_scope")

    def test_get_analysis_returns_standard_error_envelope_for_missing_report(
        self,
    ) -> None:
        response = self.client.get("/api/v1/analyses/9999")

        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "analysis_not_found")
        self.assertEqual(payload["error"]["message"], "Analysis report not found.")

    def test_invalid_analysis_id_uses_standard_error_envelope(self) -> None:
        response = self.client.get("/api/v1/analyses/not-an-int")

        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "request_validation_failed")
        self.assertEqual(
            payload["error"]["details"]["issues"][0]["loc"], ["path", "report_id"]
        )

    def test_method_not_allowed_uses_standard_error_envelope(self) -> None:
        response = self.client.patch("/api/v1/analyses")

        self.assertEqual(response.status_code, 405)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "method_not_allowed")
        self.assertEqual(payload["error"]["message"], "Method Not Allowed")

    def test_analysis_pipeline_failure_uses_standard_error_envelope(self) -> None:
        project_service_module.create_project(
            project_key="payments",
            display_name="Payments",
        )
        files = [
            (
                "files",
                (
                    "plan.json",
                    b'{"resource_changes": [{"address": "aws_security_group.main", "change": {"actions": ["update"]}}]}',
                    "application/json",
                ),
            )
        ]
        client = TestClient(create_app(), raise_server_exceptions=False)

        with (
            patch(
                "services.analysis_service.evaluate_parse_batch",
                return_value=self._analysis_assessment(),
            ),
            patch(
                "services.analysis_service.generate_narrative",
                return_value=NarrativeResult(
                    opening_sentence="CAUTION: review the security group update.",
                    explanation="The deployment widens database access and should be reviewed.",
                    guidance=["Review the security group change before deploy."],
                    degraded=False,
                    warnings=[],
                    source="llm",
                    provider="ollama",
                    model="ollama/llama3",
                    local_mode=True,
                    skills_applied=["git", "terraform"],
                ),
            ),
            patch(
                "services.analysis_service.find_incident_matches",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = client.post(
                "/api/v1/analyses",
                files=files,
                data={"project_key": "payments"},
            )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "internal_error")
        self.assertEqual(payload["error"]["message"], "Internal server error.")

    def test_analysis_persistence_failure_uses_actionable_error_envelope(self) -> None:
        project_service_module.create_project(
            project_key="payments-persist-failed",
            display_name="Payments Persist Failed",
        )
        client = TestClient(create_app(), raise_server_exceptions=False)

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            side_effect=AnalysisPersistenceError("database is read-only"),
        ):
            response = client.post(
                "/api/v1/analyses",
                files={"files": ("plan.json", b'{"resource_changes": []}')},
                data={"project_key": "payments-persist-failed"},
            )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "report_persistence_failed")
        self.assertEqual(
            payload["error"]["message"],
            "Report persistence failed; final analysis success was not returned.",
        )
        self.assertEqual(
            payload["error"]["details"]["reason"],
            AnalysisPersistenceError.public_reason,
        )
        self.assertNotIn("database is read-only", response.text)

    def test_create_analysis_falls_back_when_persisted_advisory_is_invalid(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-invalid-advisory",
            display_name="Payments Invalid Advisory",
        )
        persisted_report = dict(self.persisted)
        persisted_report["severity"] = "low"
        persisted_report["recommendation"] = "go"
        persisted_report["top_risk"] = "Low risk metadata-only update."
        persisted_report["context_completeness"] = {
            **dict(persisted_report["context_completeness"]),
            "context_score": 0.92,
            "parser_success_rate": 1.0,
            "evidence_success_rate": 0.5,
            "insufficient_context": False,
            "partial_context": False,
        }
        persisted_report["advisory"] = {
            "advisory_only": True,
            "should_block": False,
            "requires_attention": False,
            "severity": "minor",
            "recommendation": "ship",
            "top_risk": "Invalid legacy advisory.",
            "partial_context": False,
            "narrative_degraded": False,
            "uncertainty_flags": [],
        }
        client = TestClient(create_app(), raise_server_exceptions=False)

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ):
            response = client.post(
                "/api/v1/analyses",
                files={"files": ("plan.json", b'{"resource_changes": []}')},
                data={"project_key": "payments-invalid-advisory"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["data"]["advisory"]["severity"], "low")
        self.assertEqual(payload["data"]["advisory"]["recommendation"], "go")
        self.assertTrue(payload["data"]["advisory"]["requires_attention"])
        self.assertFalse(payload["data"]["advisory"]["partial_context"])
        self.assertIn("evidence_gaps", payload["data"]["advisory"]["uncertainty_flags"])
        self.assertEqual(
            payload["data"]["persisted_report"]["advisory"],
            payload["data"]["advisory"],
        )

    def test_create_analysis_invalid_advisory_context_uses_error_envelope(
        self,
    ) -> None:
        project_service_module.create_project(
            project_key="payments-invalid-advisory-context",
            display_name="Payments Invalid Advisory Context",
        )
        persisted_report = dict(self.persisted)
        persisted_report["context_completeness"] = ["bad"]
        persisted_report["advisory"] = {
            "advisory_only": True,
            "should_block": False,
            "requires_attention": False,
            "severity": "minor",
            "recommendation": "ship",
            "top_risk": "Invalid legacy advisory.",
            "partial_context": False,
            "narrative_degraded": False,
            "uncertainty_flags": [],
        }
        client = TestClient(create_app(), raise_server_exceptions=False)

        with patch(
            "api.routes.analyses.analyze_uploaded_files",
            return_value=self._analysis_result_with_persisted_report(persisted_report),
        ):
            response = client.post(
                "/api/v1/analyses",
                files={"files": ("plan.json", b'{"resource_changes": []}')},
                data={"project_key": "payments-invalid-advisory-context"},
            )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "analysis_advisory_contract_invalid")

    def test_openapi_documents_analysis_submission_contract(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()

        def schema_enum_values(schema_part: dict) -> set[str]:
            values = set(schema_part.get("enum") or [])
            for branch_key in ("anyOf", "oneOf", "allOf"):
                for branch in schema_part.get(branch_key) or []:
                    values.update(schema_enum_values(branch))
            return values

        analyses_get = schema["paths"]["/api/v1/analyses"]["get"]
        analyses_post = schema["paths"]["/api/v1/analyses"]["post"]
        analyses_detail = schema["paths"]["/api/v1/analyses/{report_id}"]["get"]
        request_body_schema = analyses_post["requestBody"]["content"][
            "multipart/form-data"
        ]["schema"]
        analyses_get_parameters = {
            parameter["name"]: parameter for parameter in analyses_get["parameters"]
        }
        self.assertIn("$ref", request_body_schema)
        component_name = request_body_schema["$ref"].split("/")[-1]
        self.assertEqual(
            schema["components"]["schemas"][component_name]["type"], "object"
        )
        self.assertIn(
            "activity-window start timestamp",
            analyses_get_parameters["created_from"]["description"],
        )
        self.assertIn(
            "deployment-outcome/reviewer-feedback activity",
            analyses_get_parameters["created_to"]["description"],
        )
        self.assertIn(
            "deployment outcome filter",
            analyses_get_parameters["outcome"]["description"],
        )
        self.assertEqual(
            schema_enum_values(analyses_get_parameters["outcome"]["schema"]),
            {"success", "failure", "rolled_back", "rollback"},
        )
        self.assertIn("AnalysisRunResponse", str(analyses_post["responses"]["200"]))
        self.assertIn("ErrorResponse", str(analyses_post["responses"]["400"]))
        for responses in (
            analyses_get["responses"],
            analyses_post["responses"],
            analyses_detail["responses"],
        ):
            with self.subTest(responses=responses):
                self.assertIn("ErrorResponse", str(responses["400"]))
                self.assertIn("ErrorResponse", str(responses["403"]))
                self.assertIn("ErrorResponse", str(responses["422"]))
                self.assertIn("ErrorResponse", str(responses["500"]))
        self.assertNotIn("ParseBatchResult", schema["components"]["schemas"])
        self.assertNotIn("RiskAssessment", schema["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
