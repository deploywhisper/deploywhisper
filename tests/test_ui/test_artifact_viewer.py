"""Tests for the report artifact viewer route."""

from __future__ import annotations

import os
import tempfile
import unittest
from importlib import reload

import app as app_module
import config as config_module
import models.database as database_module
import models.repositories.analysis_reports as analysis_reports_repository_module
import models.tables as tables_module
import services.report_service as report_service_module
from analysis.risk_scorer import RiskAssessment
from evidence.models import EvidenceItem, Finding
from fastapi.testclient import TestClient
from llm.narrator import NarrativeResult
from parsers.base import ParseBatchResult, ParsedFileResult, UnifiedChange


class ArtifactViewerRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, "ui.db")
        self.snapshot_dir = os.path.join(self.tempdir.name, "artifacts")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        os.environ["ARTIFACT_SNAPSHOT_DIR"] = self.snapshot_dir
        reload(config_module)
        reload(tables_module)
        reload(database_module)
        reload(analysis_reports_repository_module)
        reload(report_service_module)
        reload(app_module)
        database_module.init_db()
        self.client = TestClient(app_module.create_app())

    def tearDown(self) -> None:
        database_module.engine.dispose()
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("ARTIFACT_SNAPSHOT_DIR", None)
        self.tempdir.cleanup()

    def test_artifact_viewer_renders_saved_artifact_content(self) -> None:
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
                                resource_id="aws_security_group.main",
                                action="modify",
                                summary="Terraform changed a security group.",
                            )
                        ],
                    )
                ]
            ),
            RiskAssessment(
                score=88,
                severity="critical",
                recommendation="no-go",
                top_risk="Security group exposure risk",
                contributors=[],
                interaction_risks=[],
                partial_context=False,
                warnings=[],
                source="heuristic-only",
            ),
            NarrativeResult(
                opening_sentence="NO-GO: review the security group update.",
                explanation="The deployment widens database access and should be reviewed.",
                guidance=[],
                degraded=False,
                warnings=[],
                source="llm",
                provider="ollama",
                model="ollama/llama3",
                local_mode=True,
                skills_applied=["terraform"],
            ),
            findings=[
                Finding(
                    finding_id="finding-001",
                    analysis_id=0,
                    title="CRITICAL: aws_security_group.main",
                    description="Security group exposure risk",
                    severity="critical",
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
                    finding_id="finding-001",
                    source_type="artifact",
                    source_ref="terraform://plan.json#L2",
                    summary="Terraform changed a security group.",
                    severity_hint="high",
                    deterministic=True,
                    confidence=1.0,
                    related_change_ids=["change-1"],
                )
            ],
            artifact_snapshots={
                "plan.json": b'resource "aws_security_group" "main" {\n  name = "web"\n}\n'
            },
            audit_context={
                "source_interface": "ui",
                "trigger_type": "dashboard_upload",
            },
        )

        response = self.client.get(f"/history/{report['id']}/artifacts?name=plan.json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("plan.json", response.text)
        self.assertIn("aws_security_group", response.text)
        self.assertIn('id="L2"', response.text)

    def test_artifact_viewer_returns_not_found_for_missing_snapshot(self) -> None:
        response = self.client.get("/history/999/artifacts?name=missing.tf")

        self.assertEqual(response.status_code, 404)

    def test_public_share_artifact_route_is_not_available(self) -> None:
        response = self.client.get("/reports/1/artifacts?name=plan.json")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
